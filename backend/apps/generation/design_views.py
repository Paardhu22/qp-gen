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
    """The template picker: built-in starting points + the teacher's own.

    One endpoint returns both because the picker shows them in one grid. The
    client tells them apart by the `builtin` flag, not by which endpoint it
    called — which is what lets "start from CBSE Class 10 Science" and "start
    from my Weekly Test" be the same interaction.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from services.template_catalog import list_templates

        templates = PaperTemplate.objects.filter(user=request.user)
        saved = PaperTemplateSerializer(templates, many=True).data
        builtin = list_templates(
            subject=request.query_params.get("subject", ""),
            academic_class=request.query_params.get("class", ""),
        )
        return Response({"templates": saved, "builtin": builtin})

    def post(self, request):
        payload = request.data or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            return Response(
                {"error": "Give the template a name."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instructions = str(payload.get("instructions") or "").strip()
        blueprint_in = payload.get("blueprint")

        # A template needs SOMETHING to reproduce a paper from. It used to be
        # instructions or nothing, because prose was the only way to describe a
        # paper. A blueprint edited in the Builder is now the other way, and
        # requiring prose alongside it would mean a teacher who dragged slots
        # around had to also write an essay about what they just did.
        from services.templates import TemplateBlueprint

        blueprint = TemplateBlueprint.from_dict(blueprint_in) if blueprint_in else None
        if not instructions and not (blueprint and blueprint.slots):
            return Response(
                {
                    "error": "A template needs either instructions or a blueprint "
                    "to save."
                },
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

        source_config = payload.get("sourceConfig")
        if not isinstance(source_config, dict):
            source_config = {}

        # Saving under an existing name overwrites it. Two templates called
        # "Weekly Test" are indistinguishable in the picker, and the teacher
        # who typed the name again meant this one.
        try:
            template, created = PaperTemplate.objects.update_or_create(
                user=request.user,
                name=name,
                defaults={
                    "instructions": instructions,
                    "settings": settings_in,
                    # Stored as slots only. Totals are recomputed on read, so
                    # persisting them would create a second source of truth
                    # that a later slot edit could silently contradict.
                    "blueprint": (
                        {"slots": [s.as_dict() for s in blueprint.slots]}
                        if blueprint and blueprint.slots
                        else {}
                    ),
                    "base_template_id": str(
                        payload.get("baseTemplateId") or ""
                    ).strip()[:64],
                    "source_config": source_config,
                },
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


class TemplateResolveView(APIView):
    """Compile a template into an editable blueprint.

    Listing the catalog is metadata only (see `services/template_catalog.py`),
    so this is where a blueprint is actually produced — when a teacher picks a
    card and the Builder needs slots to render.

    Writes nothing. Picking a template, looking at what it contains and backing
    out must cost nothing but the compile, or the picker becomes a commitment
    rather than a browse.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from services.template_catalog import resolve_builtin
        from services.templates import TemplateBlueprint, apply_source_ratio

        payload = request.data or {}
        template_id = str(payload.get("templateId") or "").strip()
        if not template_id:
            return Response(
                {"error": "Pick a template to start from."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subject = str(payload.get("subject") or "").strip()
        academic_class = str(payload.get("academicClass") or payload.get("class") or "")
        instructions = str(payload.get("instructions") or "").strip()
        if len(instructions) > MAX_INSTRUCTIONS_CHARS:
            return Response(
                {"error": "Those instructions are too long."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A saved template resolves from its own stored blueprint when it has
        # one, and otherwise falls through to the built-in path — which is
        # exactly the pinned/instruction-driven split in services/templates.py.
        saved = PaperTemplate.objects.filter(
            user=request.user, id=template_id
        ).first()
        if saved is not None:
            if (saved.blueprint or {}).get("slots"):
                blueprint = TemplateBlueprint.from_dict(saved.blueprint)
            else:
                base = saved.base_template_id or "describe-it-yourself"
                try:
                    blueprint = resolve_builtin(
                        base,
                        subject=subject or (saved.settings or {}).get("subject", ""),
                        academic_class=academic_class
                        or (saved.settings or {}).get("academicClass", ""),
                        instructions=instructions or saved.instructions,
                        user=request.user,
                    )
                except ValueError as exc:
                    return Response(
                        {"error": str(exc)}, status=status.HTTP_404_NOT_FOUND
                    )
            return Response(
                {
                    "blueprint": blueprint.as_dict(),
                    "template": PaperTemplateSerializer(saved).data,
                }
            )

        try:
            blueprint = resolve_builtin(
                template_id,
                subject=subject,
                academic_class=academic_class,
                difficulty=str(payload.get("difficulty") or "medium"),
                instructions=instructions,
                user=request.user,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:  # pragma: no cover - engine failure
            logger.error("Template %s failed to resolve: %s", template_id, exc,
                         exc_info=True)
            return Response(
                {
                    "error": "That template could not be prepared. Try another, "
                    "or describe the paper yourself."
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        saved_count = payload.get("savedCount")
        if saved_count is not None:
            apply_source_ratio(blueprint, saved=saved_count)

        return Response({"blueprint": blueprint.as_dict()})


class QuestionTypeCatalogView(APIView):
    """The per-slot question-type menu the Blueprint Builder renders.

    Served rather than hard-coded on the client so the subject-appropriate
    mapping (coming later) ships without a frontend release.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from services.templates import question_types_for

        return Response(
            {"questionTypes": question_types_for(request.query_params.get("subject", ""))}
        )


class QuestionImageView(APIView):
    """Draw one figure for one question, on the teacher's explicit request.

    GET lists the styles the picker offers, so adding a style is a backend
    change rather than a frontend release.

    POST draws. Slow (image generation is tens of seconds) and billable, which
    is exactly why it is a deliberate per-question action rather than something
    the pipeline does speculatively — the teacher has read the question and
    decided a figure helps before a single cent is spent.
    """

    permission_classes = [IsAuthenticated]

    #: Long enough for a real question, short enough that the prompt cannot be
    #: used as a free text channel to the image model.
    MAX_QUESTION_CHARS = 2000

    def get(self, request):
        from services.question_image import STYLE_CHOICES

        return Response({"styles": list(STYLE_CHOICES)})

    def post(self, request):
        from services.question_image import (
            QuestionImageError,
            generate_question_image,
        )

        payload = request.data or {}
        question_text = str(payload.get("questionText") or "").strip()
        if not question_text:
            return Response(
                {"error": "There is no question text to draw from."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(question_text) > self.MAX_QUESTION_CHARS:
            question_text = question_text[: self.MAX_QUESTION_CHARS]

        try:
            result = generate_question_image(
                question_text=question_text,
                style=payload.get("style"),
                user=request.user,
            )
        except QuestionImageError as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY
            )

        return Response(result)


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
