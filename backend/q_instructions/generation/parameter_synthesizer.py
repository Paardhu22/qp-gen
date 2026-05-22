import random
import re
import logging

from typing import Optional

logger = logging.getLogger("[PARAMETER_SYNTHESIS]")
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class ParameterSynthesizer:
    """Dynamically synthesizes realistic academic values for template placeholders."""
    
    def synthesize(self, text: str) -> str:
        # Check if there are any placeholders left
        if "[" not in text or "]" not in text:
            return text
            
        placeholders = list(set(re.findall(r'\[([^\]]+)\]', text)))
        
        for p in placeholders:
            val = self._generate_realistic_value(p)
            if val is not None:
                text = text.replace(f"[{p}]", val)
                
        return text
        
    def _generate_realistic_value(self, placeholder_name: str) -> Optional[str]:
        p = placeholder_name.lower()
        if p == "size":
            return f"{random.randint(2, 20)}"
        elif p == "distance":
            # Realistic optics distances
            return f"{random.choice([10, 15, 20, 25, 30, 40, 50])}"
        elif p == "resistance":
            return f"{random.choice([2, 4, 5, 10, 20, 50])}"
        elif p == "current":
            return f"{random.choice([1, 2, 5, 10])}"
        elif p == "time":
            return f"{random.choice([10, 30, 60, 120])}"
        elif p == "voltage":
            return f"{random.choice([1.5, 3, 6, 9, 12, 24])}"
        return None

    def validate_no_placeholders(self, text: str) -> bool:
        """Sanity validation: no unresolved brackets remain."""
        # Check if there's any remaining [Word]
        unresolved = re.findall(r'\[([^\]]+)\]', text)
        if unresolved:
            logger.warning(f"Unresolved placeholders remain: {unresolved}")
            return False
        return True
