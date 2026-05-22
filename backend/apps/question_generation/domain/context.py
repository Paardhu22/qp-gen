from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .enums import AcademicClass, BloomsLevel, EducationBoard
from .datatypes import CompiledPaperBlueprint


@dataclass(frozen=True)
class TokenBudget:
    model: str
    max_input_tokens: int
    max_output_tokens: int
    reserved_system_tokens: int = 0


@dataclass(frozen=True)
class GenerationConstraints:
    count: int
    difficulty: str
    enforce_strict_context: bool = True
    max_case_study: int = 3
    max_assertion_reason: int = 4


@dataclass(frozen=True)
class GenerationContext:
    subject: str
    board: EducationBoard
    academic_class: AcademicClass
    difficulty: str
    blueprint: Optional[CompiledPaperBlueprint] = None
    bloom_distribution: Dict[BloomsLevel, float] = field(default_factory=dict)
    extracted_markdown: Optional[str] = None
    retrieved_chunks: List[str] = field(default_factory=list)
    token_budget: Optional[TokenBudget] = None
    prompt_version: str = "v1"
    generation_constraints: Optional[GenerationConstraints] = None
    user_settings: Dict[str, str] = field(default_factory=dict)
