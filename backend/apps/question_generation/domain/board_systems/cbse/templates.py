"""
CBSE question template library.
"""

from typing import List

from ...datatypes import QuestionTemplate
from ...enums import BloomsLevel, QuestionTypeCode


class QuestionTemplateLibrary:
    def __init__(self) -> None:
        self._templates: List[QuestionTemplate] = []
        self._initialize()

    def _initialize(self) -> None:
        self._templates = [
            QuestionTemplate(
                "AR_CHEM_01",
                QuestionTypeCode.ASSERTION_REASON,
                BloomsLevel.ANALYZE,
                "Assertion (A): [Chemical compound] when heated decomposes into [Product].\n"
                "Reason (R): This is an example of [Reaction type] which releases gas.",
                ["Chemical compound", "Product", "Reaction type"],
            ),
            QuestionTemplate(
                "NUM_PHY_01",
                QuestionTypeCode.NUMERICAL,
                BloomsLevel.APPLY,
                "An object of size [Size] cm is placed at [Distance] cm in front of a concave mirror.\n"
                "Find position, nature, and magnification of image.",
                ["Size", "Distance"],
            ),
            QuestionTemplate(
                "NUM_PHY_02",
                QuestionTypeCode.NUMERICAL,
                BloomsLevel.APPLY,
                "A resistor of [Resistance] ohm is connected to a battery. If a current of [Current] A "
                "flows for [Time] seconds, calculate the heat dissipated.",
                ["Resistance", "Current", "Time"],
            ),
            QuestionTemplate(
                "DIA_BIO_01",
                QuestionTypeCode.DIAGRAM,
                BloomsLevel.UNDERSTAND,
                "Draw a neat labelled diagram of the human heart showing:\n"
                "(a) Four chambers\n(b) Major blood vessels\n(c) Direction of blood flow.",
                [],
            ),
            QuestionTemplate(
                "DIA_PHY_01",
                QuestionTypeCode.DIAGRAM,
                BloomsLevel.APPLY,
                "Draw a ray diagram showing refraction of light through a glass prism.\n"
                "Label the angle of incidence, angle of emergence, and angle of deviation.",
                [],
            ),
            QuestionTemplate(
                "SA_CHEM_01",
                QuestionTypeCode.SHORT_ANSWER,
                BloomsLevel.UNDERSTAND,
                "Differentiate between combination and decomposition reactions with examples.",
                [],
            ),
            QuestionTemplate(
                "SA_BIO_01",
                QuestionTypeCode.SHORT_ANSWER,
                BloomsLevel.ANALYZE,
                "Explain the mechanism of double circulation in humans. Why is it necessary?",
                [],
            ),
            QuestionTemplate(
                "CS_PHY_01",
                QuestionTypeCode.CASE_STUDY,
                BloomsLevel.ANALYZE,
                "[Technical passage detailing resistivity]\n"
                "(a) What is the relationship between resistance and length?\n"
                "(b) Calculate resistance if length doubles.\n"
                "(c) Which material has highest resistivity?",
                ["Technical passage detailing resistivity"],
            ),
            QuestionTemplate(
                "LA_BIO_01",
                QuestionTypeCode.LONG_ANSWER,
                BloomsLevel.EVALUATE,
                "Describe the process of digestion in humans. Include the role of:\n"
                "(a) Salivary amylase\n(b) Pepsin\n(c) Bile salts\n(d) Pancreatic enzymes\n"
                "Draw a labelled diagram of the human digestive system.",
                [],
            ),
            QuestionTemplate(
                "MCQ_CHEM_01",
                QuestionTypeCode.MCQ,
                BloomsLevel.REMEMBER,
                "Which of the following is an endothermic reaction?\n"
                "(a) Combustion of methane\n(b) Decomposition of calcium carbonate\n"
                "(c) Neutralization of HCl with NaOH\n(d) Respiration",
                [],
            ),
        ]

    def get_templates_by_type(self, qtype: QuestionTypeCode) -> List[QuestionTemplate]:
        return [t for t in self._templates if t.target_type == qtype]

    def get_all_templates(self) -> List[QuestionTemplate]:
        return list(self._templates)
