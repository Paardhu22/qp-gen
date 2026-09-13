"""A compact constructor for catalogue entries.

The data files would otherwise repeat every default on every one of ~160
entries, which buries the few fields that actually distinguish a type.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from services.question_types.spec import OptionRule, TypeSpec

#: Four options, one correct — the CBSE default for a choice item.
FOUR = OptionRule(4, 4)

#: The four fixed Assertion–Reason directions, stored verbatim.
ASSERTION_REASON_DIRECTIONS: Tuple[str, ...] = (
    "Both Assertion (A) and Reason (R) are true and Reason (R) is the correct explanation of Assertion (A).",
    "Both Assertion (A) and Reason (R) are true but Reason (R) is not the correct explanation of Assertion (A).",
    "Assertion (A) is true but Reason (R) is false.",
    "Assertion (A) is false but Reason (R) is true.",
)


def family_builder(family: str) -> Callable[..., TypeSpec]:
    def entry(
        code: str,
        label: str,
        ref: str,
        status: str,
        shape: str,
        tests: str,
        marks: int,
        classes: Tuple[int, int],
        format: str,
        task: str,
        *,
        marks_range: Optional[Tuple[int, int]] = None,
        **fields,
    ) -> TypeSpec:
        return TypeSpec(
            code=code,
            label=label,
            family=family,
            ref=ref,
            status=status,
            shape=shape,
            tests=tests,
            marks=marks,
            marks_range=marks_range or (marks, marks),
            classes=classes,
            format=format,
            task=task,
            **fields,
        )

    return entry
