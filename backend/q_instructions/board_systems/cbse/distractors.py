"""
AOS CBSE — Distractor Engine
================================
Models real cognitive misconceptions to generate high-fidelity MCQ distractors.
"""

from typing import List, Optional

from q_instructions.core.enums import MisconceptionType
from q_instructions.core.datatypes import DistractorOption


class DistractorEngine:
    """Generates misconception-modeled MCQ options for Physics, Chemistry, Biology."""

    def generate_circuit_distractors(
        self, voltage: float, resistance: float, correct_current: float
    ) -> List[DistractorOption]:
        """Generates Ohm's Law circuit MCQ distractors."""
        options = [
            DistractorOption("A", f"{correct_current:.2f} A", True),
            DistractorOption(
                "B", f"{correct_current - 0.5:.2f} A", False,
                MisconceptionType.ADDITIVE_CIRCUIT_ERROR
            ),
            DistractorOption(
                "C", f"{voltage * resistance:.2f} A", False,
                MisconceptionType.MATHEMATICAL_SLIP
            ),
            DistractorOption(
                "D", f"{voltage + resistance:.2f} A", False,
                MisconceptionType.MATHEMATICAL_SLIP
            ),
        ]
        return options

    def generate_ph_distractors(
        self, correct_ph: float
    ) -> List[DistractorOption]:
        """Generates pH scale MCQ distractors."""
        return [
            DistractorOption("A", f"pH {correct_ph:.1f}", True),
            DistractorOption(
                "B", f"pH {14.0 - correct_ph:.1f}", False,
                MisconceptionType.INVERSE_PH_SCALE
            ),
            DistractorOption(
                "C", f"pH {correct_ph + 2.0:.1f}", False,
                MisconceptionType.MATHEMATICAL_SLIP
            ),
            DistractorOption(
                "D", f"pH {correct_ph - 3.0:.1f}", False,
                MisconceptionType.ADDITIVE_CIRCUIT_ERROR
            ),
        ]

    def generate_optics_distractors(
        self, correct_focal_length: float
    ) -> List[DistractorOption]:
        """Generates optics sign convention MCQ distractors."""
        return [
            DistractorOption("A", f"{correct_focal_length:.1f} cm", True),
            DistractorOption(
                "B", f"{-correct_focal_length:.1f} cm", False,
                MisconceptionType.REVERSE_OPTICAL_SIGN
            ),
            DistractorOption(
                "C", f"{correct_focal_length * 2:.1f} cm", False,
                MisconceptionType.MATHEMATICAL_SLIP
            ),
            DistractorOption(
                "D", f"{correct_focal_length + 5:.1f} cm", False,
                MisconceptionType.ADDITIVE_CIRCUIT_ERROR
            ),
        ]
