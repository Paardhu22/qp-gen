import unittest

from apps.question_generation.services.facade import AcademicGenerationFacade, GeneratePaperRequest
from services.generation_router import adapt_response_to_legacy


class ParityTests(unittest.TestCase):
    def test_parity_with_legacy_engine(self) -> None:
        try:
            from q_instructions.master.facade import AcademicGenerationFacade as LegacyFacade
            from q_instructions.master.facade import GeneratePaperRequest as LegacyRequest
        except Exception as exc:
            self.skipTest(f"Legacy engine unavailable: {exc}")

        legacy_facade = LegacyFacade()
        new_facade = AcademicGenerationFacade()

        legacy_request = LegacyRequest(
            board="CBSE",
            academic_class="CLASS_10",
            exam_type="FINAL",
            chapters=["Electricity"],
            difficulty="medium",
            count=10,
            institution_id="CBSE_OFFICIAL",
            seed=42,
        )

        new_request = GeneratePaperRequest(
            board="CBSE",
            academic_class="CLASS_10",
            exam_type="FINAL",
            chapters=["Electricity"],
            difficulty="medium",
            count=10,
            institution_id="CBSE_OFFICIAL",
            seed=42,
        )

        legacy_response = legacy_facade.generate_paper(legacy_request)
        legacy_payload = adapt_response_to_legacy(legacy_response)

        # New engine uses simple concept map, no external PDFs in parity test
        new_response = new_facade.generate_paper(new_request)
        new_payload = adapt_response_to_legacy(new_response)

        legacy_count = sum(len(section["questions"]) for section in legacy_payload["sections"])
        new_count = sum(len(section["questions"]) for section in new_payload["sections"])

        self.assertEqual(legacy_count, new_count)


if __name__ == "__main__":
    unittest.main()
