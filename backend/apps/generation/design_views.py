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

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.generation.models import PaperTemplate, TemplateFolder
from apps.generation.serializers import (
    PaperTemplateSerializer,
    TemplateFolderSerializer,
)
from utils.ids import generate_id
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

#: Long enough for "Class 10 Boards — Revision", short enough to render in the
#: folder rail without truncation being the normal case.
MAX_FOLDER_NAME_CHARS = 80

#: "Term 1 / Unit tests / Chapter 3" is a real filing structure; anything past
#: that is a tree nobody can navigate in a sidebar. Enforced in the API rather
#: than the schema — a self-FK cannot express a depth limit.
MAX_FOLDER_DEPTH = 3

FOLDER_TOO_DEEP = (
    f"Folders can only be nested {MAX_FOLDER_DEPTH} deep. "
    "Move this somewhere shallower."
)


def _folder_for(user, folder_id: str):
    """One folder, scoped to its owner.

    Scoping here rather than at each call site is what makes another account's
    folder id a 404 instead of a window into their filing.
    """
    if not folder_id:
        return None
    return TemplateFolder.objects.filter(user=user, id=folder_id).first()


def _depth_of(folder) -> int:
    """How many ancestors `folder` has. A root folder is depth 0.

    Walks with a hard step limit rather than trusting the tree to be acyclic:
    the move guard below is what keeps cycles out, and a bug there must not
    turn into an infinite loop inside a request.
    """
    depth = 0
    cursor = folder.parent
    while cursor is not None and depth <= MAX_FOLDER_DEPTH + 1:
        depth += 1
        cursor = cursor.parent
    return depth


def _height_of(folder) -> int:
    """Depth of the deepest subfolder beneath `folder`; 0 when it is a leaf.

    Needed when moving a folder: the thing that must fit under the depth cap
    is the whole subtree being dragged, not just its root.
    """
    children = list(folder.children.all())
    if not children:
        return 0
    return 1 + max(_height_of(child) for child in children)


def _is_descendant(candidate, ancestor) -> bool:
    """Is `candidate` somewhere below `ancestor` in the tree?"""
    cursor = candidate.parent
    steps = 0
    while cursor is not None and steps <= MAX_FOLDER_DEPTH + 1:
        if cursor.id == ancestor.id:
            return True
        cursor = cursor.parent
        steps += 1
    return False


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
            # Savepointed so a constraint violation stays a 400 instead of
            # poisoning the transaction — see TemplateFolderListView.post.
            with transaction.atomic():
                template, created = PaperTemplate.objects.update_or_create(
                    user=request.user,
                    name=name,
                    defaults={
                        "instructions": instructions,
                        "settings": settings_in,
                        # Stored as slots only. Totals are recomputed on read,
                        # so persisting them would create a second source of
                        # truth that a later slot edit could silently
                        # contradict.
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


class TemplateFolderListView(APIView):
    """List and create the teacher's template folders."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        folders = (
            TemplateFolder.objects.filter(user=request.user)
            .annotate(template_count=Count("templates"))
            .order_by("name")
        )
        return Response({"folders": TemplateFolderSerializer(folders, many=True).data})

    def post(self, request):
        payload = request.data or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            return Response(
                {"error": "Give the folder a name."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(name) > MAX_FOLDER_NAME_CHARS:
            return Response(
                {"error": "That folder name is too long."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parent = None
        parent_id = str(payload.get("parentId") or "").strip()
        if parent_id:
            parent = _folder_for(request.user, parent_id)
            if parent is None:
                return Response(
                    {"error": "That parent folder no longer exists."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if _depth_of(parent) + 1 >= MAX_FOLDER_DEPTH:
                return Response(
                    {"error": FOLDER_TOO_DEEP},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            # The savepoint is load-bearing, not decoration. A constraint
            # violation marks the surrounding transaction unusable, so catching
            # IntegrityError without one leaves every later query in the same
            # atomic block raising TransactionManagementError instead of doing
            # its job — the error message would be about the wrong thing
            # entirely. `atomic()` gives the failing INSERT its own savepoint
            # to roll back to.
            with transaction.atomic():
                folder = TemplateFolder.objects.create(
                    user=request.user, name=name, parent=parent
                )
        except IntegrityError:
            # The unique constraints, not a race: a folder by this name already
            # sits beside the one being created.
            return Response(
                {"error": f'You already have a folder called "{name}" here.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"folder": TemplateFolderSerializer(folder).data},
            status=status.HTTP_201_CREATED,
        )


class TemplateFolderDetailView(APIView):
    """Rename, move or delete one folder."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, folder_id):
        folder = _folder_for(request.user, folder_id)
        if folder is None:
            return Response(
                {"error": "Folder not found."}, status=status.HTTP_404_NOT_FOUND
            )

        payload = request.data or {}
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                return Response(
                    {"error": "A folder needs a name."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if len(name) > MAX_FOLDER_NAME_CHARS:
                return Response(
                    {"error": "That folder name is too long."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            folder.name = name

        if "parentId" in payload:
            raw_parent = payload.get("parentId")
            if raw_parent in (None, ""):
                folder.parent = None
            else:
                parent = _folder_for(request.user, str(raw_parent).strip())
                if parent is None:
                    return Response(
                        {"error": "That parent folder no longer exists."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                # A folder cannot be filed inside itself or its own descendant.
                # Nothing in the schema prevents it — a self-FK is happy to
                # form a ring — and the resulting cycle would be invisible in
                # the API and unrenderable in the rail, so it has to be
                # rejected here.
                if parent.id == folder.id or _is_descendant(parent, folder):
                    return Response(
                        {"error": "A folder cannot be moved inside itself."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # What must fit is the deepest folder in the subtree being
                # moved, not its root — dragging a parent drags its children.
                # Same `>=` as the create path: depths run 0..MAX-1.
                if _depth_of(parent) + 1 + _height_of(folder) >= MAX_FOLDER_DEPTH:
                    return Response(
                        {"error": FOLDER_TOO_DEEP},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                folder.parent = parent

        try:
            # Savepointed for the same reason as the create path above.
            with transaction.atomic():
                folder.save(update_fields=["name", "parent", "updated_at"])
        except IntegrityError:
            return Response(
                {"error": f'You already have a folder called "{folder.name}" here.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"folder": TemplateFolderSerializer(folder).data})

    def delete(self, request, folder_id):
        folder = _folder_for(request.user, folder_id)
        if folder is None:
            return Response(
                {"error": "Folder not found."}, status=status.HTTP_404_NOT_FOUND
            )
        # Subfolders go with it (CASCADE); the templates inside do not — they
        # fall back to unfiled via SET_NULL. Deleting a folder is tidying, and
        # tidying must not be able to destroy a paper recipe. See
        # `TemplateFolder` for the full argument.
        folder.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
    """Apply (marking it used), edit, or delete one template.

    POST and PATCH are deliberately different verbs for different acts. POST
    means "I am using this now" and touches only `last_used_at`; PATCH means
    "this recipe is wrong, change it". Collapsing them would make opening a
    template in the editor silently rewrite it.
    """

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

    def patch(self, request, template_id):
        """Edit a saved template in place.

        Every field is optional and only what the body names is touched — a
        rename must not blank the blueprint, and re-filing must not disturb the
        instructions. Absent key means "leave alone"; that is why each field is
        tested with `in payload` rather than for truthiness, which would make
        clearing a field impossible.
        """
        template = self._get(request, template_id)
        if not template:
            return Response(
                {"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )

        payload = request.data or {}
        changed: list[str] = []

        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                return Response(
                    {"error": "A template needs a name."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            template.name = name[:120]
            changed.append("name")

        if "instructions" in payload:
            instructions = str(payload.get("instructions") or "").strip()
            if len(instructions) > MAX_INSTRUCTIONS_CHARS:
                return Response(
                    {"error": "Those instructions are too long to save."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            template.instructions = instructions
            changed.append("instructions")

        if "blueprint" in payload:
            from services.templates import TemplateBlueprint

            raw = payload.get("blueprint")
            if raw in (None, {}, ""):
                # Explicitly clearing the slots reverts this to an
                # instruction-driven template, which is a real thing a teacher
                # may want: "stop pinning this, re-resolve it every time".
                template.blueprint = {}
            else:
                try:
                    blueprint = TemplateBlueprint.from_dict(raw)
                except (ValueError, TypeError) as exc:
                    return Response(
                        {"error": f"That blueprint could not be read: {exc}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Slots only. Totals stay computed on read — storing them would
                # create a second source of truth that a later slot edit could
                # silently contradict.
                template.blueprint = (
                    {"slots": [s.as_dict() for s in blueprint.slots]}
                    if blueprint.slots
                    else {}
                )
            changed.append("blueprint")

        if "settings" in payload:
            settings_in = payload.get("settings")
            template.settings = settings_in if isinstance(settings_in, dict) else {}
            changed.append("settings")

        if "sourceConfig" in payload:
            source_config = payload.get("sourceConfig")
            template.source_config = (
                source_config if isinstance(source_config, dict) else {}
            )
            changed.append("source_config")

        if "folderId" in payload:
            raw_folder = payload.get("folderId")
            if raw_folder in (None, ""):
                template.folder = None
            else:
                folder = _folder_for(request.user, str(raw_folder).strip())
                if folder is None:
                    return Response(
                        {"error": "That folder no longer exists."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                template.folder = folder
            changed.append("folder")

        if not changed:
            return Response(
                {"error": "Nothing to update."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A template still has to be reproducible after the edit. Stripping the
        # blueprint from a template that never had instructions would leave a
        # row that names a paper it cannot rebuild.
        if not template.instructions and not (template.blueprint or {}).get("slots"):
            return Response(
                {
                    "error": "A template needs either instructions or a blueprint "
                    "to save."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Savepointed: see TemplateFolderListView.post for why catching
            # IntegrityError without one breaks the rest of the transaction.
            with transaction.atomic():
                template.save(update_fields=[*changed, "updated_at"])
        except IntegrityError:
            return Response(
                {"error": f'You already have a template called "{template.name}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"template": PaperTemplateSerializer(template).data})

    def delete(self, request, template_id):
        template = self._get(request, template_id)
        if not template:
            return Response(
                {"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )
        template.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _available_name(user, wanted: str) -> str:
    """`wanted`, or the first "wanted (2)", "wanted (3)"… that is free.

    `unique_template_name_per_user` exists so the picker never shows two
    identical cards, which is right for a deliberate save — the teacher who
    typed the name again meant to overwrite. But fork and duplicate are not
    that: forking the same built-in twice is a normal thing to do, and failing
    with "name taken" for an id the teacher never typed would be nonsense. So
    those two paths suffix instead of colliding.
    """
    base = (wanted or "Untitled template").strip()[:120]
    taken = set(
        PaperTemplate.objects.filter(user=user, name__startswith=base[:100]).values_list(
            "name", flat=True
        )
    )
    if base not in taken:
        return base
    # Bounded: a teacher with 99 copies of one template has a different
    # problem, and an unbounded loop here is a request that never returns.
    for suffix in range(2, 100):
        candidate = f"{base[:114]} ({suffix})"
        if candidate not in taken:
            return candidate
    return f"{base[:110]} ({generate_id()[:6]})"


class PaperTemplateForkView(APIView):
    """Turn a built-in catalog entry into a row the teacher owns.

    Built-ins are generated from `_NEW_ENGINE_ELIGIBILITY` (see
    `services/template_catalog.py`) — code, not rows — which is what keeps the
    picker in step with the engine for free. The cost is that a built-in has
    nothing to edit and nowhere to be filed. Forking resolves it once and
    writes the result down, and from that point it is an ordinary
    `PaperTemplate`: editable, fileable, deletable.

    The fork is pinned (it carries slots) on purpose. A teacher who forks
    "CBSE Class 10 Science" to change it wants the structure they were looking
    at, not one re-derived later from prose that no longer describes it.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from services.template_catalog import get_entry, resolve_builtin

        payload = request.data or {}
        template_id = str(payload.get("templateId") or "").strip()
        if not template_id:
            return Response(
                {"error": "Say which template to fork."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entry = get_entry(template_id)
        if entry is None:
            return Response(
                {"error": "That template is not in the catalog."},
                status=status.HTTP_404_NOT_FOUND,
            )

        subject = str(payload.get("subject") or entry.subject or "").strip()
        academic_class = str(
            payload.get("academicClass")
            or payload.get("class")
            or entry.academic_class
            or ""
        ).strip()
        instructions = str(payload.get("instructions") or "").strip()
        if len(instructions) > MAX_INSTRUCTIONS_CHARS:
            return Response(
                {"error": "Those instructions are too long."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            blueprint = resolve_builtin(
                template_id,
                subject=subject,
                academic_class=academic_class,
                instructions=instructions,
                user=request.user,
            )
        except ValueError as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        # "Describe It Yourself" and "Blank Paper" resolve to nothing until a
        # teacher says something. Forking one would write a row that cannot
        # rebuild a paper, which the same rule rejects on save and edit.
        if not blueprint.slots and not instructions:
            return Response(
                {
                    "error": (
                        f'"{entry.name}" has nothing to fork yet — describe the '
                        "paper you want first, then save it as a template."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        folder = None
        raw_folder = payload.get("folderId")
        if raw_folder:
            folder = _folder_for(request.user, str(raw_folder).strip())
            if folder is None:
                return Response(
                    {"error": "That folder no longer exists."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        template = PaperTemplate.objects.create(
            user=request.user,
            name=_available_name(request.user, payload.get("name") or entry.name),
            instructions=instructions,
            settings={
                "board": entry.board,
                "academicClass": academic_class,
                "subject": subject,
            },
            blueprint=(
                {"slots": [s.as_dict() for s in blueprint.slots]}
                if blueprint.slots
                else {}
            ),
            base_template_id=template_id[:64],
            folder=folder,
        )
        return Response(
            {"template": PaperTemplateSerializer(template).data},
            status=status.HTTP_201_CREATED,
        )


class PaperTemplateDuplicateView(APIView):
    """Copy one of the teacher's own templates.

    The copy starts unused (`last_used_at` null) rather than inheriting the
    original's, so a duplicate made to experiment with does not immediately
    outrank the template it was copied from in the picker.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, template_id):
        source = PaperTemplate.objects.filter(
            user=request.user, id=template_id
        ).first()
        if not source:
            return Response(
                {"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND
            )

        payload = request.data or {}
        folder = source.folder
        if "folderId" in payload:
            raw_folder = payload.get("folderId")
            if raw_folder in (None, ""):
                folder = None
            else:
                folder = _folder_for(request.user, str(raw_folder).strip())
                if folder is None:
                    return Response(
                        {"error": "That folder no longer exists."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

        copy = PaperTemplate.objects.create(
            user=request.user,
            name=_available_name(request.user, payload.get("name") or source.name),
            instructions=source.instructions,
            settings=dict(source.settings or {}),
            blueprint=dict(source.blueprint or {}),
            base_template_id=source.base_template_id,
            source_config=dict(source.source_config or {}),
            folder=folder,
        )
        return Response(
            {"template": PaperTemplateSerializer(copy).data},
            status=status.HTTP_201_CREATED,
        )
