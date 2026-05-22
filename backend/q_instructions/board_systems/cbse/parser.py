"""
AOS CBSE — Sample Paper Parser
=================================
Lexes and parses raw CBSE sample papers into structured question nodes.
"""

import re
from typing import List

from q_instructions.core.enums import QuestionTypeCode, TokenKind
from q_instructions.core.datatypes import PaperToken, ParsedQuestionNode


class SamplePaperParser:
    """Lexes and parses raw CBSE sample papers into rich structural objects."""

    def __init__(self) -> None:
        self.section_regex = re.compile(r"^\s*SECTION\s+([A-E])", re.IGNORECASE)
        self.marks_regex = re.compile(
            r"\[\s*(\d+)\s*marks?\s*\]|(\d+)\s*marks?|\[\s*(\d+)\s*\]", re.IGNORECASE
        )
        self.q_num_regex = re.compile(r"^\s*Q?(\d+)[\.\\)]\s*(.*)", re.IGNORECASE)

    def tokenize(self, raw_text: str) -> List[PaperToken]:
        """Converts raw text into structural tokens."""
        tokens: List[PaperToken] = []
        for idx, line in enumerate(raw_text.split("\n")):
            cleaned = line.strip()
            if not cleaned:
                continue
            if self.section_regex.match(cleaned):
                tokens.append(PaperToken(TokenKind.SECTION_HEADER, cleaned, idx + 1))
            elif "general instructions" in cleaned.lower() or "instructions:" in cleaned.lower():
                tokens.append(PaperToken(TokenKind.GENERAL_INSTRUCTION, cleaned, idx + 1))
            elif self.q_num_regex.match(cleaned):
                tokens.append(PaperToken(TokenKind.QUESTION_NUM, cleaned, idx + 1))
            elif cleaned.strip() == "OR" or "[OR]" in cleaned:
                tokens.append(PaperToken(TokenKind.OR_SPLIT, cleaned, idx + 1))
            else:
                tokens.append(PaperToken(TokenKind.QUESTION_BODY, cleaned, idx + 1))
        return tokens

    def parse(self, raw_text: str) -> List[ParsedQuestionNode]:
        """Parses raw paper text into structured question nodes."""
        tokens = self.tokenize(raw_text)
        questions: List[ParsedQuestionNode] = []
        current_section = "A"

        for i, token in enumerate(tokens):
            if token.kind == TokenKind.SECTION_HEADER:
                match = self.section_regex.match(token.text)
                if match:
                    current_section = match.group(1).upper()

            elif token.kind == TokenKind.QUESTION_NUM:
                q_match = self.q_num_regex.match(token.text)
                if q_match:
                    q_num = int(q_match.group(1))
                    body_text = q_match.group(2).strip()

                    # Collect continuation lines
                    j = i + 1
                    while j < len(tokens) and tokens[j].kind == TokenKind.QUESTION_BODY:
                        body_text += " " + tokens[j].text
                        j += 1

                    # Extract marks
                    marks = self._extract_marks(body_text)

                    # Detect question type
                    qtype = self._detect_type(body_text)

                    # Extract keywords
                    keywords = self._extract_keywords(body_text)

                    questions.append(ParsedQuestionNode(
                        question_num=q_num,
                        raw_text=body_text,
                        assigned_marks=marks,
                        section_id=current_section,
                        detected_type=qtype,
                        extracted_keywords=keywords
                    ))

        return questions

    def _extract_marks(self, text: str) -> int:
        match = self.marks_regex.search(text)
        if match:
            for group in match.groups():
                if group:
                    return int(group)
        return 1

    def _detect_type(self, text: str) -> QuestionTypeCode:
        lower = text.lower()
        if "assertion" in lower and "reason" in lower:
            return QuestionTypeCode.ASSERTION_REASON
        if "diagram" in lower or "draw" in lower or "sketch" in lower:
            return QuestionTypeCode.DIAGRAM
        if "calculate" in lower or "find the value" in lower:
            return QuestionTypeCode.NUMERICAL
        if "case" in lower or "passage" in lower or "read" in lower:
            return QuestionTypeCode.CASE_STUDY
        if any(w in lower for w in ["differentiate", "explain", "describe"]):
            return QuestionTypeCode.SHORT_ANSWER
        return QuestionTypeCode.MCQ

    def _extract_keywords(self, text: str) -> List[str]:
        keywords: List[str] = []
        triggers = [
            "differentiate", "explain", "calculate", "justify", "diagram",
            "compare", "state", "define", "predict", "design", "balance"
        ]
        lower = text.lower()
        for trigger in triggers:
            if trigger in lower:
                keywords.append(trigger)
        return keywords
