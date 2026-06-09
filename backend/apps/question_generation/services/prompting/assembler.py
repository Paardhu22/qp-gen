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
        # Cluster B (figure pipeline): a stem must NEVER reference an
        # external figure the response did not supply. There are exactly
        # two valid shapes for a figure-bearing question:
        #
        #   OPTION 1 — emit a self-contained inline SVG in the `figure`
        #              field with labelled vertices / sides / angles.
        #              Cap: ~16 KB, no <script>, no <foreignObject>,
        #              no remote xlink:href.
        #   OPTION 2 — rewrite the stem so every relationship the
        #              question depends on is stated in words ("In right
        #              triangle ABC, right-angled at B, AB = 24 cm…").
        #
        # If neither option fits, omit the `figure` key AND remove every
        # phrase like "observe the figure / see the diagram / in the
        # figure / refer to the image / shown above / shown below" from
        # the stem before returning. A "see figure" stem with no figure
        # is rejected and regenerated.
        "Figure rule: emit a valid inline SVG in `figure` OR write a "
        "text-self-contained stem that cites no figure at all. Never "
        "mention 'figure', 'diagram', 'image', 'picture', 'circuit', "
        "'graph', or 'sketch' unless you ALSO populated `figure` with a "
        "valid SVG (or were given a real `image_url` to attach).",
        "You must analyze how sub-questions (A) and (B) are presented and format them according to these two strict rules:\n\n"
        "1. Standard Parts (No \"OR\"): > If you see questions labeled (A) and (B) sequentially, and there is NO \"OR\" separating them, treat them as completely separate questions.\n\n"
        "2. Internal Choice (With \"OR\" in a Single Block): > If you see questions (A) and (B) separated by the word \"OR\", they must be kept together as a single, unified question block (representing one cell). Format it exactly like this:\n\n"
        "Output the text for (A).\n"
        "Insert a standalone \" OR \" on a new line immediately following (A).\n"
        "Output the text for (B) immediately after the \"OR\".\n\n"
        "Safeguard: Apply this logic strictly. Make sure that correctly grouping the \"OR\" questions into a single block does not break or alter the formatting of standard multi-part questions or any previously established rules.",
    ]

    if constraints:
        base.append(f"Resolved paper count: {constraints.count} question objects.")

    return "\n".join(base)
