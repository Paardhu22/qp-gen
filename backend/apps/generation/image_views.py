"""Questions from a teacher's own image.

The endpoints behind the editor's "Question from image" dialog and its "Use my
own image" action on an existing question. The work is in
``services.generation.image_question``; these views only parse the multipart
request, check the monthly limit, and translate its two failure kinds:

* a request that cannot be done as sent (a bad file) is a 400 the teacher can fix;
* a model or storage failure is a 502 and worth retrying.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from services.generation.image_question import (
    MAX_IMAGE_BYTES,
    QUESTION_TYPES,
    ImageProviderError,
    ImageQuestionError,
    generate_image_question,
    plan_image_edits,
    store_images,
)
from services.organizations.usage_limits import UsageLimitExceeded, check_monthly_token_limit

logger = logging.getLogger(__name__)


def _file_bytes(request, field: str) -> Optional[bytes]:
    """The uploaded file's bytes, or None when the field was not sent.

    The size is checked before the read, so an oversized upload is refused
    without being held in memory.
    """
    upload = request.FILES.get(field)
    if upload is None:
        return None
    if upload.size > MAX_IMAGE_BYTES:
        raise ImageQuestionError(
            f"That image is {upload.size / (1024 * 1024):.1f} MB. Images up to "
            f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB are accepted — try a smaller or cropped copy."
        )
    return upload.read()


def _json_field(request, field: str) -> Any:
    """A JSON value sent as a form field; anything unreadable is simply absent."""
    raw = request.data.get(field)
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _failure(exc: ImageQuestionError) -> Response:
    code = status.HTTP_502_BAD_GATEWAY if isinstance(exc, ImageProviderError) else status.HTTP_400_BAD_REQUEST
    return Response({"error": str(exc)}, status=code)


class ImageQuestionView(APIView):
    """Write one question about an image.

    GET lists the question types the dialog offers, so adding one is a backend
    change rather than a frontend release.

    POST takes ``image`` (what will be printed — the edited copy when edits
    were made), optionally ``original`` (the upload as it arrived) and
    ``edits`` (the list of operations that turned one into the other), plus the
    teacher's ``description`` and ``instructions``. A request with neither
    still works: the model works out what the picture shows.
    """

    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        return Response({"types": [{"value": value, "label": label} for value, label in QUESTION_TYPES]})

    def post(self, request):
        try:
            image = _file_bytes(request, "image")
            if image is None:
                raise ImageQuestionError("Choose an image first.")
            original = _file_bytes(request, "original")
            data = request.data
            try:
                check_monthly_token_limit(request.user)
            except UsageLimitExceeded as exc:
                return Response(exc.payload, status=status.HTTP_402_PAYMENT_REQUIRED)

            result = generate_image_question(
                user=request.user,
                image=image,
                original=original,
                edits=_json_field(request, "edits"),
                description=data.get("description") or "",
                instructions=data.get("instructions") or "",
                subject=str(data.get("subject") or "").strip(),
                class_num=_int_or_none(data.get("class")) or 10,
                question_type=str(data.get("questionType") or "").strip().upper(),
                marks=_int_or_none(data.get("marks")),
                difficulty=str(data.get("difficulty") or "").strip().lower(),
            )
        except ImageQuestionError as exc:
            return _failure(exc)
        return Response(result)


class ImageEditPlanView(APIView):
    """Turn "crop to the circuit and highlight R2" into edits to review.

    A proposal, never an applied change: the browser draws it over the picture
    and the teacher adjusts or discards it.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            image = _file_bytes(request, "image")
            if image is None:
                raise ImageQuestionError("Choose an image first.")
            try:
                check_monthly_token_limit(request.user)
            except UsageLimitExceeded as exc:
                return Response(exc.payload, status=status.HTTP_402_PAYMENT_REQUIRED)
            result = plan_image_edits(
                user=request.user,
                image=image,
                instruction=request.data.get("instruction") or "",
                description=request.data.get("description") or "",
            )
        except ImageQuestionError as exc:
            return _failure(exc)
        return Response(result)


class ImageUploadView(APIView):
    """Store a picture for an existing question. No model is involved.

    ``image`` is what will be printed; ``original`` (when the picture was edited)
    is kept beside it unchanged. Returns the stable URLs to put in the paper.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            image = _file_bytes(request, "image")
            if image is None:
                raise ImageQuestionError("Choose an image first.")
            stored = store_images(
                request.user,
                image=image,
                original=_file_bytes(request, "original"),
                edits=_json_field(request, "edits"),
            )
        except ImageQuestionError as exc:
            return _failure(exc)
        description = " ".join(str(request.data.get("description") or "").split())[:200]
        return Response({**stored, "alt": description})
