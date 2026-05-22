from dataclasses import asdict, dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class GenerationMetrics:
    prompt_version: str
    model: str
    chunk_count: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    truncation_events: int
    provider_failures: int
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
