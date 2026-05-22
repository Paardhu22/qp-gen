"""
AOS Institution — Policy Override Engine
============================================
Manages customized guidelines for individual schools and networks.
"""

from typing import Dict

from q_instructions.core.enums import StreamType
from q_instructions.core.datatypes import InstitutionPolicy


class InstitutionOverrideEngine:
    """Registers and retrieves institution-specific policy overrides."""

    def __init__(self) -> None:
        self._policies: Dict[str, InstitutionPolicy] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._policies["CBSE_OFFICIAL"] = InstitutionPolicy(
            institution_id="CBSE_OFFICIAL",
            name="CBSE Guidelines Standard",
            comp_questions_minimum_ratio=0.50,
            mcq_ratio_allowance=0.20,
            long_answer_max_ratio=0.20,
            require_visual_alternate=True,
            allowed_streams={StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY, StreamType.INTEGRATED},
            custom_instruction_footer="This paper conforms to official CBSE board templates."
        )

        self._policies["DPS_E_DELHI"] = InstitutionPolicy(
            institution_id="DPS_E_DELHI",
            name="Delhi Public School - East Delhi",
            comp_questions_minimum_ratio=0.60,
            mcq_ratio_allowance=0.25,
            long_answer_max_ratio=0.15,
            require_visual_alternate=True,
            allowed_streams={StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY, StreamType.INTEGRATED},
            custom_instruction_footer="Generated for DPS internal diagnostics. Strictly confidential."
        )

        self._policies["RYAN_GLOBAL"] = InstitutionPolicy(
            institution_id="RYAN_GLOBAL",
            name="Ryan International School",
            comp_questions_minimum_ratio=0.55,
            mcq_ratio_allowance=0.30,
            long_answer_max_ratio=0.20,
            require_visual_alternate=True,
            allowed_streams={StreamType.PHYSICS, StreamType.CHEMISTRY, StreamType.BIOLOGY, StreamType.INTEGRATED},
            custom_instruction_footer="Administered by the Ryan Group of Institutions."
        )

    def register(self, policy: InstitutionPolicy) -> None:
        self._policies[policy.institution_id] = policy

    def get_policy(self, institution_id: str) -> InstitutionPolicy:
        return self._policies.get(institution_id, self._policies["CBSE_OFFICIAL"])
