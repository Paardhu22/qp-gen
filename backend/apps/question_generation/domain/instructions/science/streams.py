"""
Science stream profiles.
"""

from typing import Dict, List

from ...enums import AcademicClass, CognitiveStyle, StreamType
from ...datatypes import StreamProfile, TheoryPracticalRatio


class StreamFoundationEngine:
    def __init__(self) -> None:
        self._profiles: Dict[StreamType, StreamProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._profiles[StreamType.PHYSICS] = StreamProfile(
            stream_type=StreamType.PHYSICS,
            cognitive_style=CognitiveStyle.MATHEMATICAL_MODELING,
            preferred_question_types=["NUMERICAL", "DIAGRAM", "HOTS", "MCQ"],
            diagram_frequency_coefficient=0.75,
            numerical_weightage_coefficient=0.60,
            theory_practical_ratio=TheoryPracticalRatio(60.0, 40.0),
            core_focus_description=(
                "Governs motion, force, electricity, light, and energy. Demands "
                "dimensional analysis, vector notation, algebraic extraction, and geometric optics."
            ),
        )

        self._profiles[StreamType.CHEMISTRY] = StreamProfile(
            stream_type=StreamType.CHEMISTRY,
            cognitive_style=CognitiveStyle.MICRO_MACRO_MAPPING,
            preferred_question_types=["EXPERIMENTAL", "ASSERTION_REASON", "MCQ", "SHORT_ANSWER"],
            diagram_frequency_coefficient=0.45,
            numerical_weightage_coefficient=0.30,
            theory_practical_ratio=TheoryPracticalRatio(50.0, 50.0),
            core_focus_description=(
                "Governs properties of matter, chemical equations, acids/bases, metals, "
                "and carbon compounds. Demands tracking physical changes and balancing reactions."
            ),
        )

        self._profiles[StreamType.BIOLOGY] = StreamProfile(
            stream_type=StreamType.BIOLOGY,
            cognitive_style=CognitiveStyle.SYSTEMIC_FUNCTIONAL,
            preferred_question_types=["DIAGRAM", "CASE_STUDY", "LONG_ANSWER", "COMPETENCY"],
            diagram_frequency_coefficient=0.90,
            numerical_weightage_coefficient=0.05,
            theory_practical_ratio=TheoryPracticalRatio(70.0, 30.0),
            core_focus_description=(
                "Governs life processes, cellular biology, genetic inheritance, ecosystems, "
                "and anatomy. Demands classification pathways, labeling, and structural reasoning."
            ),
        )

        self._profiles[StreamType.INTEGRATED] = StreamProfile(
            stream_type=StreamType.INTEGRATED,
            cognitive_style=CognitiveStyle.PHENOMENOLOGICAL,
            preferred_question_types=["MCQ", "SHORT_ANSWER", "DIAGRAM"],
            diagram_frequency_coefficient=0.50,
            numerical_weightage_coefficient=0.15,
            theory_practical_ratio=TheoryPracticalRatio(80.0, 20.0),
            core_focus_description=(
                "Unified natural science framework combining primary aspects of nature, energy, "
                "plants, and water cycles for observational curiosity."
            ),
        )

    def get_profile(self, stream_type: StreamType) -> StreamProfile:
        if stream_type not in self._profiles:
            raise ValueError(f"Stream {stream_type.name} not cataloged.")
        return self._profiles[stream_type]

    def get_recommended_stream(self, academic_class: AcademicClass, topic_hint: str) -> StreamType:
        if academic_class in [AcademicClass.CLASS_6, AcademicClass.CLASS_7]:
            return StreamType.INTEGRATED

        normalized = topic_hint.lower()
        triggers: Dict[StreamType, List[str]] = {
            StreamType.PHYSICS: [
                "force",
                "motion",
                "speed",
                "electricity",
                "circuit",
                "mirror",
                "lens",
                "refraction",
                "light",
                "watt",
                "ohm",
                "ampere",
                "magnetic",
            ],
            StreamType.CHEMISTRY: [
                "acid",
                "base",
                "salt",
                "reaction",
                "equation",
                "element",
                "metal",
                "non-metal",
                "carbon",
                "bond",
                "atom",
                "molecule",
                "solution",
            ],
            StreamType.BIOLOGY: [
                "cell",
                "tissue",
                "organ",
                "plant",
                "animal",
                "reproduction",
                "digestive",
                "respiration",
                "heredity",
                "gene",
                "neuron",
                "ecosystem",
            ],
        }
        for stream, words in triggers.items():
            if any(w in normalized for w in words):
                return stream

        if academic_class == AcademicClass.CLASS_8:
            return StreamType.INTEGRATED
        return StreamType.PHYSICS
