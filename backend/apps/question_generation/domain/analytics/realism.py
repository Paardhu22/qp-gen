"""
Question Generation Domain - Realism Auditor
"""

from typing import List, Set

from ..datatypes import ParsedQuestionNode, QuestionInstance, RealismMetricsReport


class PaperRealismAuditor:
    def compare_realism(
        self,
        paper_id: str,
        generated_questions: List[QuestionInstance],
        official_nodes: List[ParsedQuestionNode],
    ) -> RealismMetricsReport:
        if not generated_questions or not official_nodes:
            return RealismMetricsReport(
                target_paper_id=paper_id,
                section_layout_similarity=0.0,
                marks_weight_similarity=0.0,
                keywords_phrasing_similarity=0.0,
                chronological_sequence_similarity=0.0,
                overall_realism_index=0.0,
            )

        gen_sections = {q.metadata.get("section_id", "A") for q in generated_questions}
        off_sections = {n.section_id for n in official_nodes}
        section_similarity = len(gen_sections.intersection(off_sections)) / max(
            len(gen_sections.union(off_sections)), 1
        )

        gen_marks = sum(q.assigned_marks for q in generated_questions)
        off_marks = sum(n.assigned_marks for n in official_nodes)
        marks_similarity = 1.0 - abs(gen_marks - off_marks) / max(off_marks, 1)
        marks_similarity = max(marks_similarity, 0.0)

        gen_keywords = self._extract_vocab(generated_questions)
        off_keywords = {k for n in official_nodes for k in n.extracted_keywords}
        keyword_similarity = len(gen_keywords.intersection(off_keywords)) / max(
            len(gen_keywords.union(off_keywords)), 1
        )

        gen_seq = [q.assigned_marks for q in generated_questions]
        off_seq = [n.assigned_marks for n in official_nodes]
        seq_similarity = self._cosine_similarity(gen_seq, off_seq)

        overall = (section_similarity + marks_similarity + keyword_similarity + seq_similarity) / 4.0

        return RealismMetricsReport(
            target_paper_id=paper_id,
            section_layout_similarity=round(section_similarity, 3),
            marks_weight_similarity=round(marks_similarity, 3),
            keywords_phrasing_similarity=round(keyword_similarity, 3),
            chronological_sequence_similarity=round(seq_similarity, 3),
            overall_realism_index=round(overall, 3),
        )

    def _extract_vocab(self, questions: List[QuestionInstance]) -> Set[str]:
        keywords = set()
        triggers = ["explain", "calculate", "draw", "justify", "differentiate", "predict"]
        for q in questions:
            lower = q.content_text.lower()
            for trigger in triggers:
                if trigger in lower:
                    keywords.add(trigger)
        return keywords

    def _cosine_similarity(self, seq_a: List[int], seq_b: List[int]) -> float:
        n = max(len(seq_a), len(seq_b))
        if n == 0:
            return 1.0
        pad_a = seq_a + [0] * (n - len(seq_a))
        pad_b = seq_b + [0] * (n - len(seq_b))

        dot = sum(a * b for a, b in zip(pad_a, pad_b))
        mag_a = sum(a * a for a in pad_a) ** 0.5
        mag_b = sum(b * b for b in pad_b) ** 0.5

        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
