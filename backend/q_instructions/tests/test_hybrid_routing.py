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

from services.generation_router import should_use_new_engine, adapt_response_to_legacy, route_and_execute_new_engine
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
            {"board": "CBSE", "subject": "Science", "class": 9},
            {"board": "", "subject": "Science", "class": 10},
            {},
        ]
        for p in payloads:
            with self.subTest(payload=p):
                self.assertFalse(should_use_new_engine(p))

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
    @patch("services.openai_service._record_usage")
    @patch("services.generation_service.retrieve_relevant_chunks")
    @patch("services.generation_service.get_openai_client")
    @patch("services.generation_router.AcademicGenerationFacade")
    def test_routing_failure_fallback(self, mock_facade_class, mock_openai, mock_chunks, mock_record_usage, mock_create):
        # TEST 4: new engine forced failure -> MUST fallback safely
        
        # Make new engine throw an exception
        mock_facade = MagicMock()
        mock_facade_class.return_value = mock_facade
        mock_facade.generate_paper.side_effect = Exception("Forced Engine Failure")
        
        # Mock legacy client so it runs without raising HTTP errors
        mock_chunks.return_value = [{"content": "Electricity flows."}]
        
        # Simulate legacy client stream return
        mock_comp = MagicMock()
        mock_openai.return_value.chat.completions.create.return_value = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content='{"sections": []}'))])
        ]
        
        from services.generation_service import stream_generated_questions
        
        # Test routing and safe fallback
        payload = {"board": "CBSE", "subject": "Science", "class": 10}
        events = list(stream_generated_questions(
            user=MagicMock(),
            pdf_source_ids=["src1"],
            topic="Electricity",
            count=2,
            difficulty="medium",
            payload=payload
        ))
        
        # Confirm that despite the forced new engine crash, the generation did NOT fail,
        # it fell back and returned the legacy parsed object in event updates.
        self.assertTrue(any("event: done" in ev for ev in events))
        # Ensure fallback log occurred
        
if __name__ == "__main__":
    unittest.main()
