import logging
import random
from typing import Set, List
from q_instructions.core.enums import QuestionTypeCode, BloomsLevel
from q_instructions.core.datatypes import QuestionTemplate
from q_instructions.board_systems.cbse.templates import QuestionTemplateLibrary

logger = logging.getLogger("[TEMPLATE_SELECTOR]")
# Ensure logger prints to stdout if not configured
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class IntelligentTemplateSelector:
    """Intelligently selects templates avoiding immediate repetition."""
    def __init__(self, library: QuestionTemplateLibrary):
        self._library = library
        self._used_ids: Set[str] = set()

    def select(self, qtype: QuestionTypeCode, target_bloom: BloomsLevel = None) -> QuestionTemplate:
        templates = self._library.get_templates_by_type(qtype)
        if not templates:
            fallback = self._library.get_all_templates()[0]
            logger.warning(f"No templates found for {qtype}. Falling back to {fallback.template_id}")
            return fallback

        # Score templates based on weighted rules
        scored = []
        for t in templates:
            score = 0
            if t.template_id not in self._used_ids:
                score += 100 # High priority for unused
            
            if target_bloom and t.target_bloom == target_bloom:
                score += 50  # Bonus for matching bloom
                
            scored.append((score, t))
            
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score = scored[0][0]
        
        # Randomize among all templates that share the best score
        best_templates = [t for s, t in scored if s == best_score]
        selected = random.choice(best_templates)
        
        if selected.template_id in self._used_ids:
            logger.warning(f"Rejected repeated template prevention (exhausted). Safely falling back to used template: {selected.template_id}")
        else:
            logger.info(f"Selected template: {selected.template_id}")
            
        self._used_ids.add(selected.template_id)
        return selected
