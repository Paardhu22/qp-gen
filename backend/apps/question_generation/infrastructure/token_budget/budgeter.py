from dataclasses import dataclass
from typing import Iterable, List, Tuple


@dataclass(frozen=True)
class BudgetResult:
    selected_chunks: List[str]
    estimated_tokens: int
    truncation_events: int


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def trim_chunks_to_budget(chunks: Iterable[str], max_tokens: int) -> BudgetResult:
    selected: List[str] = []
    running = 0
    truncations = 0

    for chunk in chunks:
        chunk_tokens = estimate_tokens(chunk)
        if running + chunk_tokens > max_tokens:
            truncations += 1
            break
        selected.append(chunk)
        running += chunk_tokens

    return BudgetResult(selected_chunks=selected, estimated_tokens=running, truncation_events=truncations)


def allocate_budget(total_max_tokens: int, reserved_system_tokens: int, max_output_tokens: int) -> Tuple[int, int]:
    available = max(total_max_tokens - reserved_system_tokens - max_output_tokens, 0)
    return available, max_output_tokens
