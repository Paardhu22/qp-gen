from typing import Dict, List


def adapt_questions_to_legacy(new_response) -> Dict[str, List[dict]]:
    answer_lookup = {}
    for ak in new_response.answer_keys:
        answer_lookup[ak["question_id"]] = ak.get("expected_answer", "Explanatory points with scientific reasoning.")

    legacy_questions: List[dict] = []
    for q in new_response.questions:
        q_id = q.question_id
        content = q.content_text
        q_type = q.question_type

        legacy_type = "SHORT"
        if q_type == "MCQ":
            legacy_type = "MCQ"
        elif q_type == "LONG_ANSWER":
            legacy_type = "LONG"
        elif q_type in ["SHORT_ANSWER", "NUMERICAL", "DIAGRAM", "CASE_STUDY"]:
            legacy_type = "SHORT"

        options = []
        if q_type == "MCQ":
            content, options = _extract_mcq_options(content)

        answer = answer_lookup.get(q_id, "Explanatory points with scientific reasoning.")

        metadata = {
            "gradeClass": "10th Grade",
            "subject": "Science",
            "inferredTopic": q.stream,
            "inferredChapter": q.metadata.get("inferredChapter", "Electricity"),
            "sourcePdf": q.metadata.get("sourcePdf", ""),
            "difficulty": q.metadata.get("difficulty", "Medium"),
        }

        legacy_questions.append(
            {
                "content": content,
                "type": legacy_type,
                "options": options,
                "answer": answer,
                "marks": q.assigned_marks,
                "metadata": metadata,
            }
        )

    sections_map: Dict[str, List[dict]] = {}
    for lq in legacy_questions:
        lq_type = lq["type"]
        if lq_type == "MCQ":
            sec_title = "Section A: Multiple Choice Questions (1 Mark)"
        elif lq_type == "LONG":
            sec_title = "Section C: Long Answer Questions (5 Marks)"
        else:
            sec_title = "Section B: Short Answer Questions"

        sections_map.setdefault(sec_title, []).append(lq)

    sections = [{"title": title, "questions": qs} for title, qs in sections_map.items()]
    return {"sections": sections}


def _extract_mcq_options(content_text: str) -> tuple:
    import re

    pattern = re.compile(r"\(([a-d])\)\s*(.*?)(?=\s*\([a-d]\)|$)")
    matches = pattern.findall(content_text)
    if len(matches) == 4:
        main_question = re.split(r"\s*\([a-d]\)", content_text)[0].strip()
        options = [m[1].strip() for m in matches]
        return main_question, options
    return content_text, []
