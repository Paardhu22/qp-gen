"""Endpoints for General Instructions Mode: designing a paper, and templates.

`DesignPaperView` is the whole point of the flow. A teacher types what they
want and gets back the paper it describes — sections, counts, marks — plus the
constraints their instructions did not settle, BEFORE any generation starts.
Discovering that difficulty was never set should cost a second, not a
three-minute pipeline run and an OpenAI bill.

Templates are the same shape kept for next week; see `PaperTemplate`.
"""

from __future__ import annotations

import logging

from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.generation.models import PaperTemplate
from apps.generation.serializers import PaperTemplateSerializer
from services.paper_design import (
    apply_assumed,
    design_paper,
    find_gaps,
    header_lines,
    infer_settings,
    is_ready,
)

logger = logging.getLogger("[DESIGN]")

# Generous but finite. The designer reads the whole string, so an unbounded
# body is an unbounded prompt.
MAX_INSTRUCTIONS_CHARS = 8000


def _int_or_none(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


class DesignPaperView(APIView):
    """Read free-form instructions; return the paper and what is still missing.

    Cheap relative to generation (one small model call) and safe to call while
    the teacher is still typing — both surfaces debounce it. It writes nothing.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data or {}
        instructions = str(payload.get("instructions") or "").strip()
        if not instructions:
            return Response(
                {"error": "Describe the paper you want in the instructions box."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(instructions) > MAX_INSTRUCTIONS_CHARS:
            return Response(
                {
                    "error": (
                        "Those instructions are too long — keep them under "
                        f"{MAX_INSTRUCTIONS_CHARS} characters."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Settings already on the form/spec win; anything the teacher only said
        # in prose is read out of the text so the flow does not ask for
        # something they already told us.
        stated = {
            key: value
            for key, value in (payload.get("settings") or {}).items()
            if str(value or "").strip()
        }
        settings_in = {**infer_settings(instructions), **stated}

        source_count = len(payload.get("pdfSourceIds") or []) + len(
            payload.get("hsatSourceIds") or []
        )

        design = design_paper(
            instructions,
            subject=str(settings_in.get("subject") or ""),
            academic_class=str(settings_in.get("academicClass") or ""),
            total_marks=_int_or_none(settings_in.get("marks")),
            exact_count=_int_or_none(payload.get("numberOfQuestions")),
            source_count=source_count,
            user=request.user,
        )

        gaps = find_gaps(settings_in, design, source_count=source_count)
        resolved = apply_assumed(settings_in, gaps)

        return Response(
            {
                "design": design.to_dict(),
                "gaps": [gap.to_dict() for gap in gaps],
                "settings": resolved,
                "ready": is_ready(gaps),
                "generalInstructions": header_lines(
                    design, {**resolved, "instructions": instructions}
                ),
            }
        )


class PaperTemplateListView(APIView):
    """List the teacher's templates, or save a new one."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        templates = PaperTemplate.objects.filter(user=request.user)
        return Response({"templates": PaperTemplateSerializer(templates, many=True).data})

    def post(self, request):
        payload = request.data or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            return Response(
                {"error": "Give the template a name."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instructions = str(payload.get("instructions") or "").strip()
        if not instructions:
            return Response(
                {"error": "A template needs instructions to save."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(instructions) > MAX_INSTRUCTIONS_CHARS:
            return Response(
                {"error": "Those instructions are too long to save."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        settings_in = payload.get("settings")
        if not isinstance(settings_in, dict):
            settings_in = {}

        # Saving under an existing name overwrites it. Two templates called
        # "Weekly Test" are indistinguishable in the picker, and the teacher
        # who typed the name again meant this one.
        try:
            template, created = PaperTemplate.objects.update_or_create(
                user=request.user,
                name=name,
                defaults={"instructions": instructions, "settings": settings_in},
            )
        except IntegrityError:
            return Response(
                {"error": "Could not save that template. Try a different name."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"template": PaperTemplateSerializer(template).data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaperTemplateDetailView(APIView):
    """Apply (marking it used) or delete one template."""

    permission_classes = [IsAuthenticated]

    def _get(self, request, template_id):
        # Scoped to the requesting user, so an id from another account is a
        # 404 rather than someone else's paper recipe.
        return PaperTemplate.objects.filter(
            user=request.user, id=template_id
        ).first()

    def post(self, request, template_id):
        """Mark a template as used and hand back its contents to apply."""
        template = self._get(request, template_id)
        if not template:
            return Response(
                {"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )
        template.last_used_at = timezone.now()
        template.save(update_fields=["last_used_at", "updated_at"])
        return Response({"template": PaperTemplateSerializer(template).data})

    def delete(self, request, template_id):
        template = self._get(request, template_id)
        if not template:
            return Response(
                {"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )
        template.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
