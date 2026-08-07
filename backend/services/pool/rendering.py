"""Turn a selected question into the text that gets printed on the paper.

The editor receives one `content` string per question, so an internal choice
("OR") has to be baked into that string rather than shipped alongside it. This
is the same convention the pre-pool engine used; the logic is ported here so
the pool package does not depend on the module it replaced.
"""

from __future__ import annotations

import re
from typing import Optional

from services.content_filters import remove_orphan_or_tokens

#: CBSE prints the internal-choice separator in the paper's own language.
_OR_LABELS = {
    "hindi": "अथवा",
    "telugu": "లేదా",
    "sanskrit": "अथवा",
}

def or_label_for(subject: str) -> str:
    return _OR_LABELS.get(str(subject or "").strip().lower(), "OR")


def _normalise(text: str) -> str:
    """Fold text for comparison.

    Apostrophes are DELETED rather than turned into spaces, so "Joule's law"
    and "Joules law" fold together. Collapsing them to a space instead makes
    those two read as "joule s law" vs "joules law" and the match is missed —
    which matters because the two spellings routinely appear in the same
    generated paper.
    """
    stripped = re.sub(r"['’ʼ]", "", (text or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def content_already_has_alternative(content: str, alternative: str) -> bool:
    """True when `content` already contains the alternative inline.

    A model that has been told to offer a choice will sometimes write both
    halves into one stem AND return the alternative separately. Appending
    blindly is what produced the "every OR question prints twice" bug, so the
    check stays even though the pool composes the two halves itself.
    """
    normalised_alt = _normalise(alternative)
    if not normalised_alt:
        return False
    probe = normalised_alt[:60]
    return bool(probe) and probe in _normalise(content)


def printable_content(
    content: str,
    *,
    or_alternative: Optional[str] = None,
    or_label: str = "OR",
) -> str:
    """Assemble the printed question text."""
    parts = [(content or "").strip()]

    if or_alternative:
        alternative = or_alternative.strip()
        if alternative and not content_already_has_alternative(content, alternative):
            parts.extend([or_label, alternative])

    assembled = "\n\n".join(part for part in parts if part)
    # Collapses an OR the content already ended with against the separator
    # just added, and drops any OR left dangling at the very top or bottom.
    # Per-field cleaning cannot see across that join.
    return remove_orphan_or_tokens(assembled)
