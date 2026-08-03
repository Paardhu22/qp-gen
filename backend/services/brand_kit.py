"""Storing and serving a school's branding.

Two things live here that the views should not own: where a logo's bytes go,
and how a stored asset turns back into something a browser can render.

The second is the one worth stating plainly. **A logo URL is never persisted.**
`BrandAsset` keeps the `default_storage` path, and every read mints the URL
through `services/media_urls.stable_media_url`, which resolves to the app's own
`/media/<path>` route rather than to S3 directly. Persisting a URL instead would
fail one of two ways: a literal `/media/...` breaks the moment storage moves to
S3, and a presigned S3 link expires — leaving a saved paper with a broken crest
some hours after it was made, which is exactly when nobody is looking.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, Optional, Tuple

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.accounts.models import BrandAsset, BrandKit
from services.media_urls import stable_media_url

logger = logging.getLogger("[BRAND_KIT]")

#: Where logos land under `default_storage`. A distinct prefix from
#: question-image output so an S3 lifecycle rule can treat them differently —
#: a generated figure is a cache, a school crest is not.
STORAGE_PREFIX = "brand-assets"

#: Raster formats a browser and both export paths can all render. SVG is
#: deliberately absent: it is a script-bearing document, and an <svg> that a
#: teacher uploads is later inlined into an exported page.
ALLOWED_CONTENT_TYPES: Dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

#: A crest is a few hundred KB at most. The cap is about what ends up embedded
#: in every exported PDF, not about disk.
MAX_LOGO_BYTES = 4 * 1024 * 1024

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def get_or_create_kit(user) -> BrandKit:
    """The user's kit, created empty on first touch.

    Creating on read rather than at signup keeps the table free of rows for
    every account that never opens the settings page, and means the frontend
    never has to distinguish "no kit yet" from "an empty kit".
    """
    kit, _ = BrandKit.objects.get_or_create(user=user)
    return kit


def valid_accent_color(value: str) -> bool:
    """Is this a hex colour we are willing to store?

    Checked at the API edge and nowhere else. The column stays permissive so a
    row written by an older build, or by hand, can never make a paper
    unloadable — the frontend treats anything unusable as "no accent".
    """
    return bool(_HEX_COLOR.match(value.strip())) if value else True


def _image_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    """Intrinsic pixel size, read straight from the file header.

    Two things need this. The editor reserves the right box before the image
    loads, so a header does not reflow under the teacher mid-edit; and the DOCX
    export must state an explicit size for every embedded image, because the
    `docx` package has no way to ask a picture how big it is.

    Parsed by hand rather than with Pillow, which is not a dependency of this
    project — pulling in an imaging library to read four integers out of a
    header would be a poor trade. Every format below stores its dimensions in a
    fixed place near the start of the file.

    Failure is never an error: an unmeasurable image is still a perfectly good
    logo. Callers must cope with (None, None).
    """
    try:
        # PNG — IHDR is always the first chunk, at a fixed offset.
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            return (
                int.from_bytes(data[16:20], "big"),
                int.from_bytes(data[20:24], "big"),
            )

        # GIF — logical screen descriptor, little-endian, right after the magic.
        if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
            return (
                int.from_bytes(data[6:8], "little"),
                int.from_bytes(data[8:10], "little"),
            )

        # WebP — three sub-formats, each with its own header layout.
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
            chunk = data[12:16]
            if chunk == b"VP8X":
                # 24-bit little-endian, stored as (value - 1).
                return (
                    int.from_bytes(data[24:27], "little") + 1,
                    int.from_bytes(data[27:30], "little") + 1,
                )
            if chunk == b"VP8 ":
                return (
                    int.from_bytes(data[26:28], "little") & 0x3FFF,
                    int.from_bytes(data[28:30], "little") & 0x3FFF,
                )
            if chunk == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)

        # JPEG — no fixed offset: walk the marker segments to the frame header.
        if data[:2] == b"\xff\xd8":
            index = 2
            end = len(data)
            while index + 9 < end:
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                # Standalone markers carry no length field.
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                    index += 2
                    continue
                length = int.from_bytes(data[index + 2 : index + 4], "big")
                # SOF0..SOF15, excluding the four that are not frame headers.
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    return (
                        int.from_bytes(data[index + 7 : index + 9], "big"),
                        int.from_bytes(data[index + 5 : index + 7], "big"),
                    )
                if length <= 0:
                    break
                index += 2 + length
    except Exception:
        logger.debug("Could not measure uploaded logo", exc_info=True)

    return None, None


def store_logo(
    kit: BrandKit,
    *,
    data: bytes,
    content_type: str,
    name: str = "",
) -> BrandAsset:
    """Persist an uploaded logo and return its row.

    Raises `ValueError` with a message meant for the teacher — the caller turns
    it straight into a 400.
    """
    if not data:
        raise ValueError("That file was empty.")
    if len(data) > MAX_LOGO_BYTES:
        raise ValueError(
            f"That image is larger than {MAX_LOGO_BYTES // (1024 * 1024)} MB. "
            "A logo only needs to be a few hundred kilobytes."
        )

    extension = ALLOWED_CONTENT_TYPES.get((content_type or "").lower().strip())
    if not extension:
        raise ValueError(
            "That file is not an image we can print. Use a PNG, JPEG, WebP or GIF."
        )

    width, height = _image_dimensions(data)

    # A random key, not a hash of the bytes: two schools uploading the same
    # stock crest must not share one object, because deleting one would blank
    # the other's papers.
    key = f"{STORAGE_PREFIX}/{kit.user_id}/{uuid.uuid4().hex}.{extension}"
    stored_path = default_storage.save(key, ContentFile(data))

    return BrandAsset.objects.create(
        kit=kit,
        name=(name or "").strip()[:120],
        kind=BrandAsset.KIND_LOGO,
        storage_path=stored_path,
        width=width,
        height=height,
    )


def delete_logo(asset: BrandAsset) -> None:
    """Remove the row, and the stored object behind it.

    The row goes even if the storage delete fails. An orphaned object costs a
    fraction of a cent; a row pointing at bytes that are gone renders as a
    broken image on every paper that used it, which is worse and much more
    confusing.
    """
    path = asset.storage_path
    asset.delete()
    try:
        if path and default_storage.exists(path):
            default_storage.delete(path)
    except Exception:
        logger.warning("Could not delete brand asset object %s", path, exc_info=True)


def serialize_asset(asset: BrandAsset) -> Dict[str, Any]:
    return {
        "id": asset.id,
        "name": asset.name,
        "kind": asset.kind,
        # Minted per read — see the module docstring for why this is never
        # stored.
        "url": stable_media_url(asset.storage_path),
        "width": asset.width,
        "height": asset.height,
    }


def serialize_kit(kit: BrandKit) -> Dict[str, Any]:
    return {
        "instituteName": kit.institute_name,
        "instituteAddress": kit.institute_address,
        "accentColor": kit.accent_color,
        "fontFamily": kit.font_family,
        "headerLayout": kit.header_layout or {},
        "logos": [serialize_asset(a) for a in kit.assets.all()],
    }
