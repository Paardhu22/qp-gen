import random
import re
from typing import Optional


class ParameterSynthesizer:
    def synthesize(self, text: str) -> str:
        if "[" not in text or "]" not in text:
            return text

        placeholders = list(set(re.findall(r"\[([^\]]+)\]", text)))
        for p in placeholders:
            val = self._generate_realistic_value(p)
            if val is not None:
                text = text.replace(f"[{p}]", val)
        return text

    def _generate_realistic_value(self, placeholder_name: str) -> Optional[str]:
        p = placeholder_name.lower()
        if p == "size":
            return f"{random.randint(2, 20)}"
        if p == "distance":
            return f"{random.choice([10, 15, 20, 25, 30, 40, 50])}"
        if p == "resistance":
            return f"{random.choice([2, 4, 5, 10, 20, 50])}"
        if p == "current":
            return f"{random.choice([1, 2, 5, 10])}"
        if p == "time":
            return f"{random.choice([10, 30, 60, 120])}"
        if p == "voltage":
            return f"{random.choice([1.5, 3, 6, 9, 12, 24])}"
        return None

    def validate_no_placeholders(self, text: str) -> bool:
        unresolved = re.findall(r"\[([^\]]+)\]", text)
        return not unresolved
