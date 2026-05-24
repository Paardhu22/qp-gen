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
        "Generate one CBSE question from the provided chunks only.",
        "Obey the exact slot contract and JSON schema.",
        "Never add extra question objects or split an OR choice into another question.",
        "Use provided image payloads only for image/map/diagram slots.",
    ]

    if constraints:
        base.append(f"Resolved paper count: {constraints.count} question objects.")

    return "\n".join(base)
