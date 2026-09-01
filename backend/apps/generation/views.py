from django.http import Http404, StreamingHttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.generation.models import GenerationHistory, GenerationRun
from apps.generation.serializers import (
    AnswerKeySerializer,
    GenerationHistorySerializer,
    PaperFromBankSerializer,
    QuestionGenerationSerializer,
    ReplaceQuestionSerializer,
)
from services.generation_runs import (
    follow,
    purge_expired_runs,
    resumable_runs,
    run_in_background,
    start_run,
)
from services.openai_service import generate_answer_key
from services.pool.keepalive import keepalive
from services.pool.pipeline import stream_pool_questions
from services.usage_limits import UsageLimitExceeded, check_monthly_token_limit


def _sse_response(stream):
    """The SSE response every generation endpoint returns.

    `keepalive` is still here on the reading side: it converts an exception
    raised after the headers went out into a terminal `error` frame (the socket
    can no longer become an error response), and it keeps a proxy from closing
    a connection that has been quiet. See services/pool/keepalive.py.
    """
    response = StreamingHttpResponse(keepalive(stream), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class QuestionGenerationStreamView(APIView):
    """POST /api/generation/questions/stream

    Starts a generation and streams it — but the stream is a *reader* of a
    recorded run, not the run itself. A teacher who closes the laptop, loses
    signal, or lets their phone sleep can re-attach at
    `/api/generation/runs/<id>/events?cursor=N` and pick up exactly where they
    dropped, instead of losing a paper that took four minutes to produce.

    The run id arrives as the first frame, so the client has something to
    re-attach to before any real work has happened. See
    services/generation_runs.py, including what this does and does not survive.
    """

    def post(self, request):
        serializer = QuestionGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Snapshotted before the thread starts. The producer outlives this
        # request, and reading `request.data` from another thread after the
        # response has been handed back is exactly the kind of thing that works
        # until a DRF upgrade decides the parsed body is request-scoped.
        payload = dict(request.data)
        user = request.user
        data = dict(serializer.validated_data)

        run = start_run(user, kind="questions", request=payload)
        run_in_background(
            run,
            lambda: stream_pool_questions(
                user=user,
                pdf_source_ids=data.get("pdfSourceIds") or [],
                topic=data["topic"],
                count=data["count"],
                difficulty=data["difficulty"],
                instructions=data["instructions"],
                payload=payload,
                hsat_source_ids=data.get("hsatSourceIds") or [],
            ),
        )
        return _sse_response(follow(run.id, request.user))


class GenerationRunListView(APIView):
    """GET /api/generation/runs — this account's recent generations.

    What it is for: a teacher whose connection dropped needs to find the run
    again. Listing settles any run whose producer died, so a worker restart
    does not leave a permanent "still generating…" in the UI.
    """

    def get(self, request):
        purge_expired_runs()
        runs = resumable_runs(request.user)[:20]
        return Response([
            {
                "id": run.id,
                "kind": run.kind,
                "status": run.status,
                "created_at": run.created_at,
                "finished_at": run.finished_at,
                "error": run.error,
                "eventCount": run.events.count(),
                "request": run.request,
            }
            for run in runs
        ])


class GenerationRunEventsView(APIView):
    """GET /api/generation/runs/<run_id>/events?cursor=N — re-attach to a run.

    Replays every frame after `cursor`, then follows the run live until it
    ends. A client that never disconnected can ignore this entirely; a client
    that did sends the last sequence number it saw and loses nothing.

    Scoped to the caller: a run id is not a capability, and one account must
    not be able to read another's paper by guessing one.
    """

    def get(self, request, run_id: str):
        if not GenerationRun.objects.filter(id=run_id, user=request.user).exists():
            raise Http404("Generation not found")
        try:
            cursor = max(0, int(request.query_params.get("cursor", 0)))
        except (TypeError, ValueError):
            cursor = 0
        return _sse_response(follow(run_id, request.user, cursor=cursor))


class PaperFromBankView(APIView):
    """POST /api/generation/paper-from-bank

    Assembles a paper from the user's saved questions. Model 1 never runs, so
    a chapter that has been generated once costs a single Model 2 call to
    re-paper — the reuse payoff of persisting the pool per-row.
    """

    def post(self, request):
        from services.pool.from_bank import stream_paper_from_bank

        serializer = PaperFromBankSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Recorded and resumable for the same reason the pool stream is: Model 2
        # assembly still takes minutes, and a dropped connection should not
        # cost the teacher the paper.
        payload = dict(request.data)
        user = request.user
        run = start_run(user, kind="paper_from_bank", request=payload)
        run_in_background(
            run,
            lambda: stream_paper_from_bank(
                user,
                subject=data.get("subject") or "",
                class_num=int(data.get("class") or 10),
                chapters=data.get("chapters") or [],
                project_ids=data.get("projectIds") or [],
                topic=data.get("topic") or "",
                difficulty=data.get("difficulty") or "medium",
                instructions=data.get("instructions") or "",
                count=int(data.get("count", -1)),
                count_variation=data.get("countVariation") or "cbse",
                qp_type=data.get("qp_type") or "board",
                deterministic=bool(data.get("deterministic")),
                payload=payload,
            ),
        )
        return _sse_response(follow(run.id, user))


class ReplaceQuestionView(APIView):
    """POST /api/generation/replace-question

    Regenerate exactly ONE question. The request carries the slot's blueprint
    identity (marks, type, section, generator, asset type, chapter,
    difficulty) — the same `slotMeta` the editor stamps on a generated question
    block — and the response is a single question eligible for that slot.

    Nothing else on the paper is touched, and the common case does not call a
    model at all: the pool over-provisions every slot, so a replacement is
    usually already in the teacher's bank.
    """

    def post(self, request):
        from services.pool.replace import ReplacementError, replace_question

        serializer = ReplaceQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("allowGeneration", True):
            try:
                check_monthly_token_limit(request.user)
            except UsageLimitExceeded as exc:
                return Response(exc.payload, status=402)

        try:
            result = replace_question(
                user=request.user,
                spec=data["slot"],
                exclude_ids=data.get("excludeIds") or [],
                exclude_hashes=data.get("excludeHashes") or [],
                pdf_source_ids=data.get("pdfSourceIds") or [],
                hsat_source_ids=data.get("hsatSourceIds") or [],
                allow_generation=data.get("allowGeneration", True),
            )
        except ReplacementError as exc:
            return Response({"error": str(exc)}, status=409)

        question = result.question
        return Response(
            {
                "source": result.source,
                "question": {
                    "content": question.question,
                    "type": question.type,
                    "options": list(question.options or []),
                    "answer": question.answer,
                    "marks": question.marks,
                    "explanation": question.explanation,
                    "image_url": question.image or "",
                    "metadata": {
                        **(question.metadata or {}),
                        "slotIndex": int(data["slot"].get("slotIndex") or 0),
                        "section": data["slot"].get("section") or "",
                        "questionId": question.id,
                        "generator": question.generator,
                        "assetType": question.asset_type,
                        "inferredChapter": question.chapter,
                        "inferredTopic": question.topic,
                        "difficulty": question.difficulty,
                        "subject": question.subject,
                        "replacedFrom": data["slot"].get("questionId") or "",
                    },
                },
            }
        )


class QuestionBankSummaryView(APIView):
    """GET /api/generation/bank-summary

    Per-chapter counts, so the "Create Paper from Saved Questions" picker can
    show what is available before the teacher commits to a selection.
    """

    def get(self, request):
        from services.pool.store import bank_summary

        return Response({"chapters": bank_summary(user=request.user)})


class AnswerKeyView(APIView):
    def post(self, request):
        serializer = AnswerKeySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            check_monthly_token_limit(request.user)
        except UsageLimitExceeded as exc:
            return Response(exc.payload, status=402)
        answer_key_html = generate_answer_key(serializer.validated_data["paperContentHTML"], user=request.user)
        return Response({"answerKeyHtml": answer_key_html})


class GenerationHistoryListView(APIView):
    def get(self, request):
        history = GenerationHistory.objects.filter(user=request.user).order_by("-created_at")
        serializer = GenerationHistorySerializer(history, many=True)
        return Response(serializer.data)

    def delete(self, request):
        deleted_count, _ = GenerationHistory.objects.filter(user=request.user).delete()
        return Response({"deleted": deleted_count})

class AnswerScriptGenerateView(APIView):
    """
    POST /api/generation/papers/<paper_id>/generate-answer-script/

    Generates a CBSE-style marking scheme / answer script for an existing
    paper. The answer script is saved as a NEW separate paper.

    Returns:
        { "answer_script_paper_id": "...", "editor_url": "/editor?paperId=..." }
    """
    def post(self, request, paper_id: str):
        from services.answer_script_service import generate_answer_script

        set_id = request.data.get("setId") if request.data else None

        try:
            check_monthly_token_limit(request.user)
            result = generate_answer_script(paper_id=paper_id, user=request.user, set_id=set_id)
            return Response(result, status=201)
        except UsageLimitExceeded as exc:
            return Response(exc.payload, status=402)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=400)
        except Exception as exc:
            import logging
            logging.getLogger("[ANSWER_SCRIPT_VIEW]").error(
                "Answer script generation failed: %s", exc, exc_info=True
            )
            return Response(
                {"error": "Failed to generate answer script. Please try again."},
                status=500,
            )
