"""Storing and serving an organization's crest.

The rules here are the same ones `services/brand_kit.py` states at length, and
the constants are imported from it rather than restated — the allowed formats,
the size cap and the dimension probe are one policy, not two. In particular:
**a logo URL is never persisted.** `Organization.logo_storage_path` holds the
`default_storage` path, and every read mints a URL through
`media_urls.stable_media_url`.

Why this is separate from BrandKit at all: a `BrandKit` belongs to one *user*
and describes the masthead that teacher prints. An organization's crest belongs
to the *institution* and outlives any individual account, so it hangs off
`Organization` directly. A school that wants the crest on its papers copies it
into the kit; the two are related by intent, not by row.
"""

from __future__ import annotations

import logging
import re
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.organizations.models import Organization
from services.brand_kit import (
    ALLOWED_CONTENT_TYPES,
    MAX_LOGO_BYTES,
    # Underscored but already imported across modules by test_brand_kit; the
    # alternative is a second dimension probe that can disagree with the first.
    _image_dimensions,
)
from services.media_urls import stable_media_url

logger = logging.getLogger("[ORGANIZATION_LOGO]")

#: Distinct from `brand-assets` so an S3 lifecycle rule can tell an
#: institution's crest apart from a teacher's personal upload.
STORAGE_PREFIX = "organization-logos"

#: 15 characters: 2 state code, 10 PAN, 1 entity number, 1 'Z', 1 checksum.
#: Shape only — the checksum digit is not verified, because a wrong-but-
#: well-formed GSTIN is a data-entry problem for a human, not something worth
#: refusing an onboarding over.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


def normalize_gstin(raw: str) -> str:
    """Upper-case and strip a GSTIN, or raise ValueError with a human message.

    Returns "" for blank input: the field is optional, and an admin clearing it
    must not be treated the same as an admin typing nonsense.
    """
    value = (raw or "").strip().upper().replace(" ", "")
    if not value:
        return ""
    if not GSTIN_RE.match(value):
        raise ValueError(
            "That does not look like a GSTIN. It is 15 characters, "
            "e.g. 29ABCDE1234F1Z5. Leave it blank if you do not have one."
        )
    return value


def store_organization_logo(
    organization: Organization,
    *,
    data: bytes,
    content_type: str,
) -> Organization:
    """Persist an uploaded crest onto `organization` and return it.

    Raises `ValueError` with a message meant for the administrator — the caller
    turns it straight into a 400.
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

    # A random key rather than a hash of the bytes: two schools uploading the
    # same stock crest must not share one object, or deleting one would blank
    # the other's papers.
    key = f"{STORAGE_PREFIX}/{organization.id}/{uuid.uuid4().hex}.{extension}"
    stored_path = default_storage.save(key, ContentFile(data))

    previous = organization.logo_storage_path
    organization.logo_storage_path = stored_path
    organization.logo_width = width
    organization.logo_height = height
    organization.save(
        update_fields=["logo_storage_path", "logo_width", "logo_height", "updated_at"]
    )

    # Replacing a crest orphans the old object. Best-effort: a storage backend
    # that refuses the delete must not fail an upload that already succeeded.
    if previous and previous != stored_path:
        try:
            default_storage.delete(previous)
        except Exception as exc:
            logger.warning("Could not delete replaced logo %s: %s", previous, exc)

    return organization


def remove_organization_logo(organization: Organization) -> Organization:
    """Clear the crest and delete the stored object behind it. Idempotent."""
    path = organization.logo_storage_path
    organization.logo_storage_path = ""
    organization.logo_width = None
    organization.logo_height = None
    organization.save(
        update_fields=["logo_storage_path", "logo_width", "logo_height", "updated_at"]
    )

    if path:
        # Best-effort, as in store_: the row is already clear, and a storage
        # backend that refuses the delete must not turn this into a 500.
        try:
            default_storage.delete(path)
        except Exception as exc:
            logger.warning("Could not delete logo object %s: %s", path, exc)

    return organization


def organization_logo_url(organization: Organization) -> str | None:
    """App-stable URL for the crest, or None when none has been uploaded."""
    if not organization.logo_storage_path:
        return None
    return stable_media_url(organization.logo_storage_path)
