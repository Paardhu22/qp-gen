"""
AOS Retrieval — Vector Semantic Search Index
================================================
Binds textbook extracts to questions via cosine similarity matching.
"""

import math
from typing import List

from q_instructions.core.datatypes import SemanticTextbookChunk
from q_instructions.core.interfaces import IRetrievalEngine
from q_instructions.core.constants import MINIMUM_SIMILARITY_THRESHOLD


class SemanticSearchIndex(IRetrievalEngine):
    """In-memory vector index for textbook context retrieval."""

    def __init__(self) -> None:
        self._database: List[SemanticTextbookChunk] = []
        self._initialize()

    def _initialize(self) -> None:
        chunks = [
            ("CH1_C1", "C10_CH1", "C10_EQ_BAL",
             "Balancing a chemical equation involves adjusting coefficients so that "
             "the number of atoms of each element is equal on both sides. "
             "This satisfies the Law of Conservation of Mass.",
             [0.12, 0.85, 0.04, 0.11, 0.90, 0.02, 0.03, 0.01],
             ["CBSE.SC.10.1.1", "MassConservation"]),

            ("CH1_C2", "C10_CH1", "C10_RE_TYPE",
             "Chemical reactions can be classified into combination, decomposition, "
             "displacement, and double displacement reactions.",
             [0.08, 0.77, 0.12, 0.09, 0.65, 0.04, 0.02, 0.05],
             ["CBSE.SC.10.1.2", "ReactionCategories"]),

            ("CH2_C1", "C10_CH2", "C10_AC_PH",
             "pH is defined as the negative logarithm of hydronium ion concentration. "
             "Solutions below pH 7 are acidic; above 7 are basic.",
             [0.15, 0.92, 0.03, 0.22, 0.78, 0.01, 0.04, 0.02],
             ["CBSE.SC.10.2.2", "pHScale"]),

            ("CH3_C1", "C10_CH5", "C10_BIO_NUT",
             "Autotrophic nutrition involves synthesis of organic compounds from "
             "inorganic raw materials via photosynthesis.",
             [0.02, 0.04, 0.92, 0.05, 0.01, 0.88, 0.75, 0.03],
             ["CBSE.SC.10.5.1", "PhotosynthesisMechanism"]),

            ("CH3_C2", "C10_CH5", "C10_BIO_CIRC",
             "Double circulation in humans consists of systemic and pulmonary loops. "
             "The four-chambered heart prevents mixing of blood streams.",
             [0.01, 0.02, 0.95, 0.08, 0.03, 0.92, 0.85, 0.02],
             ["CBSE.SC.10.5.3", "DoubleCirculation"]),

            ("CH4_C1", "C10_CH9", "C10_PHY_REFR",
             "Refraction is the bending of light passing between optical media. "
             "Snell's Law: ratio of sin(i) to sin(r) equals refractive index.",
             [0.85, 0.03, 0.02, 0.92, 0.04, 0.01, 0.02, 0.88],
             ["CBSE.SC.10.9.2", "SnellsLaw"]),

            ("CH4_C2", "C10_CH11", "C10_PHY_OHM",
             "Ohm's Law: electric current through a conductor is directly proportional "
             "to potential difference, given constant physical conditions: V = IR.",
             [0.91, 0.02, 0.01, 0.98, 0.01, 0.02, 0.01, 0.95],
             ["CBSE.SC.10.11.1", "OhmsLaw"]),
        ]

        for cid, ch_id, c_id, text, vec, tags in chunks:
            self._database.append(
                SemanticTextbookChunk(cid, ch_id, c_id, text, vec, tags)
            )

    def retrieve(
        self, concept_id: str, query_embedding: List[float], max_chunks: int = 1
    ) -> List[SemanticTextbookChunk]:
        """Retrieves matching context chunks via cosine similarity."""
        matches = []
        for chunk in self._database:
            if chunk.concept_id == concept_id:
                sim = self._cosine_similarity(query_embedding, chunk.vector_embedding)
                matches.append((chunk, sim))

        matches.sort(key=lambda x: x[1], reverse=True)
        return [m[0] for m in matches[:max_chunks]]

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)
