from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Count
from django.core.cache import cache
from django.http import Http404
from apps.projects.models import Paper
from apps.projects.serializers import (
    DraftDetailSerializer,
    DraftSummarySerializer,
    ProjectSerializer,
    SaveDraftSerializer,
    SaveQuestionsSerializer,
    SavePaperSerializer,
    PaperListSerializer,
    PaperDetailSerializer,
    QuestionTypeSerializer,
)

from apps.projects.models import QuestionType

from services.draft_service import (
    DraftRejected,
    delete_scope,
    get_scope,
    list_drafts,
    retention_days as draft_retention_days,
    upsert_draft,
)
from services.project_service import (
    get_paper_for_user,
    list_deleted_papers_for_user,
    list_papers_for_user,
    list_projects_for_user,
    purge_expired_papers,
    purge_paper,
    restore_paper,
    save_paper_to_project,
    save_questions_to_project,
    soft_delete_all_papers,
    soft_delete_paper,
    trash_retention_days,
)


#: Ceiling on `?limit=`. A library is unbounded and a client asking for all of
#: it should still get a bounded response — the point of paging is that one
#: request cannot be made arbitrarily expensive.
MAX_PAGE_SIZE = 200


def _paginate(request, queryset):
    """Apply `?limit=`/`?offset=`, returning `(rows, total, limit, offset)`.

    `limit` absent means "everything", which keeps the endpoint's existing
    contract intact for clients that never asked for paging — the response is
    a plain array either way, with the totals carried in headers. Changing the
    body shape would have broken every existing caller for the benefit of one.
    """
    total = queryset.count()
    try:
        offset = max(0, int(request.query_params.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0

    raw_limit = request.query_params.get("limit")
    if raw_limit is None:
        return queryset[offset:], total, None, offset
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = MAX_PAGE_SIZE
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    return queryset[offset : offset + limit], total, limit, offset


def _with_pagination_headers(response, total, limit, offset):
    response["X-Total-Count"] = str(total)
    response["X-Offset"] = str(offset)
    if limit is not None:
        response["X-Limit"] = str(limit)
    return response


def _bust_paper_caches(user_id, paper_id=None):
    cache.delete(f"user_papers:{user_id}")
    cache.delete(f"user_papers_trash:{user_id}")
    cache.delete(f"user_projects_full:{user_id}")
    cache.delete(f"user_projects_summary:{user_id}")
    if paper_id:
        cache.delete(f"user_paper:{user_id}:{paper_id}")


class ProjectListView(APIView):
    def get(self, request):
        # By default return a lightweight project summary (no nested questions)
        # Clients can request nested questions by setting ?withQuestions=true
        with_questions = str(request.query_params.get("withQuestions", "false")).lower() == "true"

        if with_questions:
            # Cache the full nested response for 30 seconds to reduce DB load on repeated requests
            cache_key = f"user_projects_full:{request.user.id}"
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return Response(cached_data)

            projects = list_projects_for_user(request.user)
            data = ProjectSerializer(projects, many=True).data
            cache.set(cache_key, data, timeout=30)
            return Response(data)

        # Lightweight summary path - cached for 20 seconds
        cache_key = f"user_projects_summary:{request.user.id}"
        data = cache.get(cache_key)
        if data is not None:
            return Response(data)

        # Return only essential fields to minimize serialization and DB work
        from apps.projects.models import Project
        qs = (
            Project.objects
            .filter(user=request.user)
            .annotate(question_count=Count("questions"))
            .order_by("-created_at")
            .values("id", "name", "description", "created_at", "updated_at", "question_count")
        )

        data = list(qs)
        # cache briefly to speed repeated simple requests
        cache.set(cache_key, data, timeout=20)
        return Response(data)


class SaveQuestionsView(APIView):
    def post(self, request):
        serializer = SaveQuestionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = save_questions_to_project(
            user=request.user,
            project_name=serializer.validated_data["projectName"],
            questions=serializer.validated_data["questions"],
        )
        return Response({"success": True, "projectId": project.id})


class PaperListView(APIView):
    def get(self, request):
        # Only the unpaginated response is cached. A per-page cache key would
        # multiply entries by however many offsets a client happens to scroll
        # through, for a 30-second window that would rarely be hit twice.
        cacheable = "limit" not in request.query_params and not request.query_params.get(
            "offset"
        )
        cache_key = f"user_papers:{request.user.id}"
        if cacheable:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                # Answered without touching the database at all — including the
                # count, which is why the cache is checked before paginating.
                return _with_pagination_headers(
                    Response(cached_data), len(cached_data), None, 0
                )

        page, total, limit, offset = _paginate(request, list_papers_for_user(request.user))
        data = PaperListSerializer(page, many=True).data
        if cacheable:
            cache.set(cache_key, data, timeout=30)
        return _with_pagination_headers(Response(data), total, limit, offset)

    def post(self, request):
        serializer = SavePaperSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        paper = save_paper_to_project(
            user=request.user,
            project_name=serializer.validated_data["projectName"],
            title=serializer.validated_data["title"],
            subject=serializer.validated_data.get("subject", ""),
            grade_class=serializer.validated_data.get("gradeClass", ""),
            board=serializer.validated_data.get("board", ""),
            instructions=serializer.validated_data.get("instructions", ""),
            blueprint=serializer.validated_data.get("blueprint"),
            question_pool_id=serializer.validated_data.get("questionPoolId", ""),
            sets=serializer.validated_data.get("sets", []),
            questions=serializer.validated_data.get("questions", []),
            hsat_source_ids=serializer.validated_data.get("hsatSourceIds"),
        )
        # Bust all relevant caches so the saved page reflects the new paper immediately
        _bust_paper_caches(request.user.id)
        return Response({"success": True, "paperId": paper.id}, status=201)


class PaperDetailView(APIView):
    def get(self, request, paper_id: str):
        cache_key = f"user_paper:{request.user.id}:{paper_id}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        try:
            paper = get_paper_for_user(request.user, paper_id)
        except Exception as exc:
            raise Http404("Paper not found") from exc

        # Dual-write sync removed from here, frontend will access sets via standard serializers
        data = PaperDetailSerializer(paper).data
        cache.set(cache_key, data, timeout=30)
        return Response(data)

    def put(self, request, paper_id: str):
        serializer = SavePaperSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            paper = save_paper_to_project(
                user=request.user,
                project_name=serializer.validated_data["projectName"],
                title=serializer.validated_data["title"],
                subject=serializer.validated_data.get("subject", ""),
                grade_class=serializer.validated_data.get("gradeClass", ""),
                board=serializer.validated_data.get("board", ""),
                instructions=serializer.validated_data.get("instructions", ""),
                blueprint=serializer.validated_data.get("blueprint"),
                question_pool_id=serializer.validated_data.get("questionPoolId", ""),
                sets=serializer.validated_data.get("sets", []),
                questions=serializer.validated_data.get("questions", []),
                paper_id=paper_id,
                hsat_source_ids=serializer.validated_data.get("hsatSourceIds"),
            )
        except Paper.DoesNotExist:
            raise Http404("Paper not found")
        # Bust caches
        _bust_paper_caches(request.user.id, paper_id)
        return Response({"success": True, "paperId": paper.id})

    def delete(self, request, paper_id: str):
        """Move the paper to the recycle bin.

        Not a hard delete. What this button destroys is a term's worth of work
        — blueprint, three set variants, answer key, every question — and it
        sits one row away from "open". `?permanent=true` is the deliberate
        second step, reachable only from the bin itself.
        """
        permanent = str(request.query_params.get("permanent", "")).lower() == "true"
        try:
            if permanent:
                purge_paper(request.user, paper_id)
            else:
                soft_delete_paper(request.user, paper_id)
        except Paper.DoesNotExist:
            raise Http404("Paper not found")
        _bust_paper_caches(request.user.id, paper_id)
        return Response({"success": True, "permanent": permanent})


class QuestionDetailView(APIView):
    def delete(self, request, question_id: str):
        from apps.projects.models import Question
        try:
            question = Question.objects.get(id=question_id, project__user=request.user)
        except Question.DoesNotExist:
            raise Http404("Question not found")
        question.delete()
        # Bust project caches so the questions list refreshes
        cache.delete(f"user_projects_full:{request.user.id}")
        cache.delete(f"user_projects_summary:{request.user.id}")
        return Response({"success": True})


class ClearAllQuestionsView(APIView):
    """Delete every question belonging to the current user across all projects."""
    def delete(self, request):
        from apps.projects.models import Question
        Question.objects.filter(project__user=request.user).delete()
        cache.delete(f"user_projects_full:{request.user.id}")
        cache.delete(f"user_projects_summary:{request.user.id}")
        return Response({"success": True})


class ClearAllPapersView(APIView):
    """Move every paper belonging to the current user to the recycle bin.

    Emphatically a soft delete: this is the single most destructive button in
    the product, and the one most likely to be pressed by accident.
    """

    def delete(self, request):
        moved = soft_delete_all_papers(request.user)
        _bust_paper_caches(request.user.id)
        return Response({"success": True, "moved_to_trash": moved})


class PaperTrashView(APIView):
    """The recycle bin: papers deleted but still recoverable.

    Listing purges what has aged out first, so a deployment with no scheduler
    still honours the retention promise the UI makes — the management command
    (`purge_deleted_papers`) is the belt, this is the braces.
    """

    def get(self, request):
        purge_expired_papers()
        page, total, limit, offset = _paginate(
            request, list_deleted_papers_for_user(request.user)
        )
        data = PaperListSerializer(page, many=True).data
        response = Response(
            {"retention_days": trash_retention_days(), "papers": data}
        )
        return _with_pagination_headers(response, total, limit, offset)

    def delete(self, request):
        """Empty the bin."""
        from apps.projects.models import Paper

        Paper.objects.filter(user=request.user, deleted_at__isnull=False).delete()
        _bust_paper_caches(request.user.id)
        return Response({"success": True})


class PaperRestoreView(APIView):
    """Take one paper back out of the bin."""

    def post(self, request, paper_id: str):
        try:
            paper = restore_paper(request.user, paper_id)
        except Paper.DoesNotExist:
            raise Http404("Paper not found in the recycle bin")
        _bust_paper_caches(request.user.id, paper_id)
        return Response({"success": True, "paperId": paper.id})


class QuestionTypeListView(APIView):
    def get(self, request):
        cache_key = "all_question_types"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        types = QuestionType.objects.select_related("family").all()
        data = QuestionTypeSerializer(types, many=True).data
        cache.set(cache_key, data, timeout=3600)  # cache for 1 hour since it rarely changes
        return Response(data)


class DraftListView(APIView):
    """The server's copy of a teacher's unsaved work.

    GET  — every live draft, bodies omitted, for the drafts strip.
    PUT  — one autosave push, from the editor's debounce.

    The local IndexedDB store remains the authority for speed; this exists so
    a draft outlives the browser that made it. Nothing here is on the
    keystroke path, and every failure is the caller's to shrug off — a server
    that cannot take the copy must never stop the teacher typing.
    """

    def get(self, request):
        drafts = list_drafts(request.user)
        return Response({
            "retention_days": draft_retention_days(),
            "drafts": DraftSummarySerializer(drafts, many=True).data,
        })

    def put(self, request):
        serializer = SaveDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            draft, stored = upsert_draft(
                request.user,
                scope=data["scope"],
                set_label=data.get("setLabel") or "",
                document=data["document"],
                client_updated_at=data["clientUpdatedAt"],
            )
        except DraftRejected as exc:
            return Response({"error": str(exc)}, status=400)

        # `stored: false` with the newer row attached, rather than a bare
        # conflict: the client needs the winning document to reconcile with,
        # and a 409 with no body would leave it typing into a stale copy.
        return Response(
            {"stored": stored, "draft": DraftDetailSerializer(draft).data},
            status=200 if stored else 409,
        )


class DraftScopeView(APIView):
    """One draft — every set tab of it.

    GET    — hydrate the editor from the server when this browser has no local
             copy (a different device, or a cleared cache).
    DELETE — drop it. Called when a teacher deletes a draft, and when one is
             saved as a paper: the Paper row is authoritative from then on,
             and a surviving draft would be a second copy diverging from it.
    """

    def get(self, request, scope: str):
        try:
            drafts = get_scope(request.user, scope)
        except DraftRejected as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(DraftDetailSerializer(drafts, many=True).data)

    def delete(self, request, scope: str):
        try:
            removed = delete_scope(request.user, scope)
        except DraftRejected as exc:
            return Response({"error": str(exc)}, status=400)
        return Response({"success": True, "removed": removed})
