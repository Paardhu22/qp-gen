"""Family J — structural containers. Shapes that hold questions, not types.

These are catalogued so every name in the spec has one home, and so the DB
seed and the picker agree on what exists — but they are `structural`, never
offered as a slot type. The mechanisms themselves live elsewhere:

* OR_GROUP — `choice_required` on a blueprint slot; `SlotAssignment.or_choice`.
* CHOICE_POOL, SUB_QUESTION_SET, WORD_BANK_GROUP — the `container` axis on a
  type (`SUB_PARTS`, with an attempt-any-K choice), see `services.pool.structure`.
* VI_ALTERNATIVE — the per-paper `include_vi_alternatives` flag.
* INSTRUCTION_BLOCK — the editor's `instructionBlock` node.

`OR_GROUP` and `CHOICE_POOL` are different mechanisms: one slot with N
alternatives of which exactly one is attempted, versus N items of which any K
are attempted (marks = K × per-item marks). Conflating them produces wrong
totals and missing OR lines.
"""

from __future__ import annotations

from services.question_types.catalog._build import family_builder

_ = family_builder("STRUCTURAL")


def _structure(code, label, ref, status, tests, container, *, stimulus="NONE", notes=""):
    return _(code, label, ref, status, "SHORT_ANSWER", tests, 1, (1, 10), "SHORT_TEXT", "APPLY",
             marks_range=(1, 100), container=container, stimulus=stimulus,
             availability="structural", notes=notes)


ENTRIES = [
    _structure("OR_GROUP", "OR Group", "J1", "LIVE",
               "One slot, N alternatives; the student attempts exactly one.", "OR_GROUP",
               notes="All alternatives carry identical marks and test comparable content."),
    _structure("CHOICE_POOL", "Choice Pool", "J2", "NEW",
               "N independent items; the student attempts any K.", "CHOICE_POOL",
               notes="Marks = K × per-item marks, never N × per-item marks."),
    _structure("SUB_QUESTION_SET", "Sub-Question Set", "J3", "NEW",
               "One parent item with parts whose marks sum to the parent's marks.", "SUB_PARTS"),
    _structure("COMMON_STEM_GROUP", "Common Stem Group", "J4", "NEW",
               "One shared stimulus serving several separately numbered questions.", "COMMON_STEM",
               notes="Not implemented this round."),
    _structure("WORD_BANK_GROUP", "Word Bank Group", "J5", "NEW",
               "A box of words shared by several fill-in-the-blank items.", "SUB_PARTS",
               stimulus="WORD_BANK",
               notes="The box must hold at least one distractor, or the last blank is free."),
    _structure("VI_ALTERNATIVE", "VI Alternative", "J6", "LIVE",
               "A text substitute for a figure-dependent question.", "NONE"),
    _structure("INSTRUCTION_BLOCK", "Instruction Block", "J7", "LIVE",
               "General instructions at the head of a paper or section.", "NONE"),
]
