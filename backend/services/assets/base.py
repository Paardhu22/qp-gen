"""The generator Strategy contract.

An `AssetGenerator` owns one *kind* of assessment material and knows nothing
about any other kind. It is handed the blueprint slots that named it and must
return `PoolQuestion` objects that can fill them.

The contract deliberately does NOT include the uploaded chapter. That is the
whole architectural point: a Reading passage cannot accidentally be drawn from
the textbook if the code that writes it was never given the textbook. The one
generator that does read uploads — Literature — is not an `AssetGenerator` at
all; it is the existing chapter pipeline, reached through the reserved
`question_pool` sentinel (see `registry.DEFAULT_GENERATOR`).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from services.pool.schema import PoolQuestion

logger = logging.getLogger("[ASSETS]")


@dataclass(frozen=True)
class AssetRequest:
    """Everything a generator is allowed to know.

    `slots` are the blueprint slots that routed to this generator, in paper
    order. A generator produces at least one question per slot and, where it
    can, a few spares so Model 2 has something to choose between and so an
    `OR` alternative can be reserved without a second call.
    """

    slots: Sequence[Any]
    subject: str
    subject_norm: str
    class_num: int
    difficulty: str = "medium"
    pool_id: str = ""
    user: Any = None
    #: Multiplier on the per-slot output. 2 means "write two candidates for
    #: every slot", which is what gives the assembler a real choice and covers
    #: slots that also need an OR alternative.
    over_provision: int = 2
    #: Reusable assets already in the bank, keyed by generator name. Supplied
    #: by the runner so a generator can decide how much it still needs to
    #: write. Never a substitute for generating — only an addition.
    existing: Sequence[PoolQuestion] = ()
    model: Optional[str] = None

    def target_for(self, slot: Any) -> int:
        """How many candidates to write for one slot."""
        base = max(1, int(self.over_provision or 1))
        if bool(getattr(slot, "choice_required", False)):
            base += 1
        return base


@dataclass
class AssetBatchResult:
    """What a generator produced, plus what went wrong on the way.

    Failures are collected rather than raised. One generator failing must
    degrade its own section — the paper still prints, and the pipeline reports
    the unfilled slots — instead of destroying a generation that has already
    produced good material elsewhere.
    """

    questions: List[PoolQuestion] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    reused: int = 0
    generated: int = 0
    validation_warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.questions)

    def merge(self, other: "AssetBatchResult") -> None:
        self.questions.extend(other.questions)
        self.failures.extend(other.failures)
        self.validation_warnings.extend(other.validation_warnings)
        self.reused += other.reused
        self.generated += other.generated

    def summary(self) -> Dict[str, Any]:
        return {
            "produced": len(self.questions),
            "generated": self.generated,
            "reused": self.reused,
            "failures": list(self.failures),
            "validationWarnings": list(self.validation_warnings),
        }


class AssetGenerator(ABC):
    """One independent assessment pipeline.

    Subclasses declare `name` (the string a blueprint slot's `generator` field
    names) and `source_type` (stamped onto every `PoolQuestion` they emit, so
    provenance survives persistence and reload).
    """

    #: Blueprint routing key. Must be unique across the registry.
    name: str = ""

    #: `PoolQuestion.source_type` for everything this generator emits.
    source_type: str = "asset"

    #: Asset types this generator understands. A slot naming an unknown asset
    #: type is still generated, using the generator's default shape, and the
    #: mismatch is logged — an unrecognised label should not lose a section.
    asset_types: Sequence[str] = ()

    #: Human label for status events.
    label: str = ""

    @abstractmethod
    def generate(self, request: AssetRequest) -> AssetBatchResult:
        """Produce candidates for `request.slots`. Never raises."""

    # ── shared helpers ──────────────────────────────────────────────────

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label or self.name,
            "sourceType": self.source_type,
            "assetTypes": list(self.asset_types),
        }

    def reusable(self, request: AssetRequest) -> List[PoolQuestion]:
        """Bank questions this generator produced on an earlier run."""
        return [q for q in (request.existing or []) if q.generator == self.name]
