from typing import List, Optional

from ...domain.context import GenerationConstraints, GenerationContext
from ...domain.prompts.spec import PromptDocument, PromptSection, PromptVersion


class PromptAssembler:
    def __init__(self, version_id: str = "v1") -> None:
        self._version = PromptVersion(version_id=version_id, description="Baseline deterministic prompt")

    def assemble(
        self,
        context: GenerationContext,
        system_rules: str,
        output_schema: str,
        blueprint_instructions: Optional[str] = None,
        extra_instructions: Optional[str] = None,
    ) -> PromptDocument:
        sections: List[PromptSection] = []

        sections.append(PromptSection(title="SYSTEM", content=system_rules))

        if blueprint_instructions:
            sections.append(PromptSection(title="BLUEPRINT", content=blueprint_instructions))

        if extra_instructions:
            sections.append(PromptSection(title="USER_CONSTRAINTS", content=extra_instructions))

        if context.retrieved_chunks:
            sections.append(
                PromptSection(
                    title="CONTEXT",
                    content="\n\n".join(context.retrieved_chunks),
                )
            )

        sections.append(PromptSection(title="OUTPUT_SCHEMA", content=output_schema))

        return PromptDocument(version=self._version, sections=sections)


def default_system_rules(constraints: Optional[GenerationConstraints]) -> str:
    base = [
        "You are an expert exam question generator.",
        "Generate high-quality exam questions based ONLY on the provided context.",
        "Do not hallucinate.",
        "If a question or its answer cannot be fully supported by the context, do not generate it.",
        "Distribute questions across realistic CBSE formats (MCQ, ASSERTION_REASON, SHORT, LONG, CASE_STUDY).",
        "For MCQ: Provide exactly 4 options in the options array.",
        "For ASSERTION_REASON: Format content as 'Assertion (A): ...\nReason (R): ...' and use the standard 4 options.",
        "For CASE_STUDY: Format as a passage followed by 3 sub-questions ((i), (ii), (iii)).",
    ]

    if constraints:
        base.append(
            f"Strict limits: max {constraints.max_case_study} CASE_STUDY and max {constraints.max_assertion_reason} ASSERTION_REASON questions."
        )

    return "\n".join(base)
