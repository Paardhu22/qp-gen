from typing import Dict, List

from ...infrastructure.retrieval.semantic_index import SemanticSearchIndex


class ConceptContextService:
    def __init__(self) -> None:
        self._index = SemanticSearchIndex()

    def build_context_map(self, concept_ids: List[str]) -> Dict[str, str]:
        context_map: Dict[str, str] = {}
        for cid in concept_ids:
            chunks = self._index.retrieve(cid, [0.1, 0.8, 0.05, 0.15, 0.85, 0.02, 0.02, 0.01], max_chunks=1)
            if chunks:
                context_map[cid] = chunks[0].text_content
        return context_map
