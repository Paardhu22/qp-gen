import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure backend path is on system path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# Ensure the database URL doesn't crash on parse if not loaded, load dotenv
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))
django.setup()

from services.generation_router import (
    adapt_response_to_legacy,
    build_question_plan,
    route_and_execute_new_engine,
    should_use_new_engine,
    summarize_question_plan,
)
from q_instructions.master.facade import GeneratedPaperResponse, QuestionDTO, AnalyticsDTO


class TestHybridRouting(unittest.TestCase):
    
    def test_should_use_new_engine_eligible(self):
        # TEST 1: CBSE + Science + Class 10 -> MUST use new engine
        payloads = [
            {"board": "CBSE", "subject": "Science", "class": 10},
            {"board": "cbse", "subject": "science", "class": "10"},
            {"board": "  CBSE  ", "subject": "SCIENCE", "gradeClass": "Class 10"},
            {"board": "CBSE", "subject": "science", "class_level": "10th Grade"},
        ]
        for p in payloads:
            with self.subTest(payload=p):
                self.assertTrue(should_use_new_engine(p))

    def test_should_use_new_engine_ineligible(self):
        # TEST 2: CBSE + Math + Class 10 -> MUST use legacy
        # TEST 3: ICSE + Science -> MUST use legacy
        payloads = [
            {"board": "CBSE", "subject": "Math", "class": 10},
            {"board": "ICSE", "subject": "Science", "class": 10},
            {"board": "", "subject": "Science", "class": 10},
            {},
        ]
        for p in payloads:
            with self.subTest(payload=p):
                self.assertFalse(should_use_new_engine(p))

    def test_cbse_exact_science_plan_is_80_marks(self):
        plan = build_question_plan("", "medium", -1, class_num=10, subject="Science")
        summary = summarize_question_plan(plan)

        self.assertEqual(summary["total_questions"], 39)
        self.assertEqual(summary["total_marks"], 80)
        self.assertEqual(summary["or_choices"], 8)
        self.assertEqual(summary["section_marks"]["Section A - Biology"], 30)
        self.assertEqual(summary["section_marks"]["Section B - Chemistry"], 25)
        self.assertEqual(summary["section_marks"]["Section C - Physics"], 25)

    def test_cbse_exact_social_science_plan_is_80_marks(self):
        plan = build_question_plan("", "medium", -1, class_num=10, subject="Social Science")
        summary = summarize_question_plan(plan)

        self.assertEqual(summary["total_questions"], 38)
        self.assertEqual(summary["total_marks"], 80)
        self.assertEqual(summary["or_choices"], 7)
        self.assertEqual(summary["image_questions"], 4)
        self.assertTrue(all(marks == 20 for marks in summary["section_marks"].values()))

    @patch("services.generation_router.AcademicGenerationFacade")
    def test_route_and_execute_new_engine_success(self, mock_facade_class):
        # Setup mock facade response
        mock_facade = MagicMock()
        mock_facade_class.return_value = mock_facade
        
        mock_response = GeneratedPaperResponse(
            paper_id="BP_TEST",
            school_name="Test School",
            board="CBSE",
            general_instructions=[],
            questions=[
                QuestionDTO(
                    question_id="Q1",
                    academic_class="CLASS_10",
                    stream="PHYSICS",
                    question_type="MCQ",
                    blooms_level="REMEMBER",
                    assigned_marks=1,
                    content_text="Sample MCQ question?\n(a) Option A\n(b) Option B\n(c) Option C\n(d) Option D",
                    expected_word_count=50,
                    metadata={"inferredChapter": "Electricity", "sourcePdf": "file.pdf", "difficulty": "Medium"}
                ),
                QuestionDTO(
                    question_id="Q2",
                    academic_class="CLASS_10",
                    stream="PHYSICS",
                    question_type="SHORT_ANSWER",
                    blooms_level="APPLY",
                    assigned_marks=3,
                    content_text="Sample short answer question?",
                    expected_word_count=150,
                    metadata={"inferredChapter": "Electricity", "sourcePdf": "file.pdf", "difficulty": "Medium"}
                )
            ],
            vi_accessible_questions=[],
            answer_keys=[
                {"question_id": "Q1", "expected_answer": "Option A"},
                {"question_id": "Q2", "expected_answer": "Expected step-by-step math proof."}
            ],
            analytics=AnalyticsDTO(
                total_marks=4,
                total_questions=2,
                average_difficulty=0.5,
                difficulty_skewness="Balanced",
                blooms_distribution={},
                stream_distribution={},
                competencies_covered=[]
            ),
            observability_metrics={}
        )
        mock_facade.generate_paper.return_value = mock_response

        # Execute
        res = route_and_execute_new_engine("Electricity", "medium", 2)
        
        # Verify adaptation format matches legacy expectations
        self.assertIn("sections", res)
        sections = res["sections"]
        self.assertEqual(len(sections), 2)  # Section A (MCQ) and Section B (Short Answer)
        
        sec_a = next(s for s in sections if "Section A" in s["title"])
        self.assertEqual(len(sec_a["questions"]), 1)
        q1 = sec_a["questions"][0]
        self.assertEqual(q1["content"], "Sample MCQ question?")
        self.assertEqual(q1["type"], "MCQ")
        self.assertEqual(q1["options"], ["Option A", "Option B", "Option C", "Option D"])
        self.assertEqual(q1["answer"], "Option A")
        self.assertEqual(q1["marks"], 1)
        self.assertEqual(q1["metadata"]["gradeClass"], "10th Grade")

    @patch("apps.generation.models.GenerationHistory.objects.create")
    @patch("services.generation_service.retrieve_relevant_chunks")
    @patch("services.generation_service.OpenAIProvider")
    def test_streaming_generation_emits_question_events(self, mock_provider_class, mock_chunks, mock_create):
        class FakeProvider:
            def stream_chat(self, request):
                yield (
                    '{"question":{"content":"What is Ohm law?",'
                    '"type":"SHORT","options":[],"answer":"V = IR.",'
                    '"marks":3,"metadata":{}}}'
                )

        mock_provider_class.return_value = FakeProvider()
        mock_chunks.return_value = [
            {
                "content": "Ohm's law states that potential difference equals current multiplied by resistance.",
                "page": 1,
                "similarity": 0.9,
                "metadata": {"chapter": "Electricity"},
            }
        ]

        from services.generation_service import stream_generated_questions

        payload = {"board": "CBSE", "subject": "Science", "class": 10}
        events = list(stream_generated_questions(
            user=MagicMock(),
            pdf_source_ids=["src1"],
            topic="Electricity",
            count=1,
            difficulty="medium",
            payload=payload
        ))

        self.assertTrue(any("event: plan" in ev for ev in events))
        self.assertTrue(any("event: question" in ev for ev in events))
        self.assertTrue(any("event: update" in ev for ev in events))
        self.assertTrue(any("event: done" in ev for ev in events))
        self.assertTrue(any("Section A - Biology" in ev for ev in events))
        
    def test_custom_count_parses_general_instructions(self):
        from services.generation_router import build_question_plan
        from q_instructions.core.enums import QuestionTypeCode

        plan = build_question_plan(
            topic="French Revolution",
            difficulty="medium",
            count=10,
            class_num=9,
            subject="Social Science",
            instructions="just 3 mcq's and 5 short and 2 long",
            count_variation="custom"
        )
        
        # Verify counts
        mcqs = [s for s in plan if s.question_type == QuestionTypeCode.MCQ.name]
        shorts = [s for s in plan if s.question_type == QuestionTypeCode.SHORT_ANSWER.name]
        longs = [s for s in plan if s.question_type == QuestionTypeCode.LONG_ANSWER.name]

        
        self.assertEqual(len(plan), 10)
        self.assertEqual(len(mcqs), 3)
        self.assertCountEqual([s.marks for s in mcqs], [1, 1, 1])
        
        self.assertEqual(len(shorts), 5)
        self.assertCountEqual([s.marks for s in shorts], [3, 3, 3, 3, 3])
        
        self.assertEqual(len(longs), 2)
        self.assertCountEqual([s.marks for s in longs], [5, 5])
        
        # Verify that they are INTEGRATED stream
        for slot in plan:
            self.assertEqual(slot.stream, "INTEGRATED")
            self.assertNotEqual(slot.section_title, "Section A - History")

         
if __name__ == "__main__":
    unittest.main()

