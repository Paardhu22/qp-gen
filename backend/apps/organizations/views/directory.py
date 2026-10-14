"""Organizations themselves: public list, detail, logo, switching list and usage summary."""

import logging
from django.db.models import Sum
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsOrgAdminOrSuperAdmin, IsSuperAdmin, has_org_admin_membership
from apps.generation.models import ApiUsage
from services.organizations.logo import remove_organization_logo, store_organization_logo
from services.organizations.usage_pricing import inr_cost_of_usage
from ..domains import domain_of_email
from ..models import Organization
from ..selectors import with_usage
from ..serializers import (
    OrganizationDetailSerializer,
    OrganizationListSerializer,
    OrganizationProfileSerializer,
    PublicOrganizationSerializer,
)
from apps.organizations.views.common import _first_error, _get_organization_or_404

logger = logging.getLogger("[ORGANIZATIONS_VIEWS]")


class PublicOrganizationListView(APIView):
    """Unauthenticated list of active organizations, for the signup dropdown.

    `?email=` is the difference between a usable dropdown and an alphabetical
    list of every school on the platform. When the signup form has already
    collected an address, the school claiming that email domain is flagged and
    sorted to the top so the teacher confirms a choice rather than hunting for
    one — picking the wrong "St. Mary's" strands them in a pending queue that
    nobody at that school will ever action.

    Matching is a hint and grants nothing: the membership still starts pending.
    Domains are spoofable at signup, so the only thing this may safely do is
    change the order of a list that was already public.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        email_domain = domain_of_email(request.query_params.get("email") or "")
        orgs = list(Organization.objects.filter(is_active=True).order_by("name"))
        data = PublicOrganizationSerializer(
            orgs, many=True, context={"email_domain": email_domain}
        ).data
        if email_domain:
            # Stable within each group: matches keep their alphabetical order,
            # and so does everything else.
            data = sorted(data, key=lambda row: not row["matches_email_domain"])
        return Response(data)


class OrganizationListView(APIView):
    """Superadmin: list every organization with member count + token usage.

    `with_usage` computes all four per-row numbers for the whole page in a
    fixed five queries. Read straight off the queryset, the serializer fired
    one query per number per organization — forty-odd queries for a dozen
    schools, growing linearly with the account.
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        orgs = with_usage(Organization.objects.all().order_by("name"))
        return Response(OrganizationListSerializer(orgs, many=True).data)


class OrganizationUsageSummaryView(APIView):
    """Superadmin: flat token-usage rollup across all organizations."""
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        total_tokens = ApiUsage.objects.aggregate(total=Sum("total_tokens"))["total"] or 0
        unassigned = ApiUsage.objects.filter(organization__isnull=True)
        unassigned_tokens = unassigned.aggregate(total=Sum("total_tokens"))["total"] or 0
        orgs = with_usage(Organization.objects.all().order_by("name"))
        return Response({
            "total_tokens": total_tokens,
            "unassigned_tokens": unassigned_tokens,
            # Rupees alongside tokens throughout — see services/organizations/usage_pricing.py
            # for why this is an estimate and must be labelled as one.
            "total_cost_inr": inr_cost_of_usage(ApiUsage.objects.all()),
            "unassigned_cost_inr": inr_cost_of_usage(unassigned),
            "organizations": OrganizationListSerializer(orgs, many=True).data,
        })


class OrganizationDetailView(APIView):
    """Org admin (own org) or superadmin: organization detail + members."""
    permission_classes = [IsOrgAdminOrSuperAdmin]

    def get(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not request.user.is_superadmin and not self._is_admin_of(request.user, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)
        return Response(OrganizationDetailSerializer(org).data)

    def patch(self, request, org_id):
        """Edit the institute profile after onboarding.

        This is what makes step 2 skippable: an admin who had no GSTIN on
        signup day fills it in here instead.
        """
        org = _get_organization_or_404(org_id)
        if not request.user.is_superadmin and not self._is_admin_of(request.user, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)

        serializer = OrganizationProfileSerializer(org, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({"error": _first_error(serializer.errors)}, status=400)
        serializer.save()

        # Two fields a school's own admin must not be able to set on themselves:
        # the spend cap they are capped by, and whether the school is switched
        # on at all. Superadmin only, and handled outside the profile serializer
        # so they can never be reached by a stray key in an ordinary profile
        # PATCH from the Settings page.
        if request.user.is_superadmin:
            changed = []
            if "monthly_token_limit" in request.data:
                try:
                    limit = int(request.data.get("monthly_token_limit") or 0)
                except (TypeError, ValueError):
                    return Response(
                        {"error": "The monthly token limit must be a whole number."},
                        status=400,
                    )
                if limit < 0:
                    return Response(
                        {"error": "The monthly token limit cannot be negative. Use 0 for no cap."},
                        status=400,
                    )
                org.monthly_token_limit = limit
                changed.append("monthly_token_limit")
            if "is_active" in request.data:
                org.is_active = bool(request.data.get("is_active"))
                changed.append("is_active")
            if changed:
                org.save(update_fields=[*changed, "updated_at"])
                logger.info(
                    "Superadmin %s changed %s on organization %s",
                    request.user.email,
                    ", ".join(changed),
                    org.id,
                )

        logger.info("%s updated organization %s profile", request.user.email, org.id)
        return Response(OrganizationDetailSerializer(org).data)

    @staticmethod
    def _is_admin_of(user, org_id):
        # Asks about THIS school specifically, via the user's membership there
        # — not via whichever school happens to be active. An admin of two
        # schools manages both without switching, and an admin of one still
        # gets a 403 at the other.
        #
        # Membership only: every caller pairs this with its own superadmin
        # check, so folding the superadmin in here would make those reads say
        # something they do not mean.
        return has_org_admin_membership(user, org_id)


class OrganizationLogoView(APIView):
    """Upload or remove an organization's crest.

    Multipart rather than a presigned direct-to-S3 PUT, for the same reason
    BrandAssetListView is: a crest is a few hundred kilobytes, and the round
    trip through the API buys per-format validation and the dimension read that
    a browser uploading straight to a bucket cannot do.
    """

    permission_classes = [IsOrgAdminOrSuperAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def _authorized(self, request, org_id) -> bool:
        return request.user.is_superadmin or OrganizationDetailView._is_admin_of(
            request.user, org_id
        )

    def post(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not self._authorized(request, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": "Choose an image to upload."}, status=400)

        try:
            store_organization_logo(
                org,
                data=upload.read(),
                content_type=getattr(upload, "content_type", "") or "",
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        logger.info("%s uploaded a logo for organization %s", request.user.email, org.id)
        return Response(OrganizationDetailSerializer(org).data, status=201)

    def delete(self, request, org_id):
        org = _get_organization_or_404(org_id)
        if not self._authorized(request, org_id):
            return Response({"error": "You do not manage this organization"}, status=403)

        remove_organization_logo(org)
        return Response(OrganizationDetailSerializer(org).data)
