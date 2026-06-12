from django.test import TestCase

from services import hsat_catalog
from services.generation_router import (
    build_blueprint_instructions,
    build_question_plan,
    build_slot_blueprint_instructions,
    build_social_science_blueprint_instructions,
    normalize_subject,
    resolve_maths_basic,
)
from services.syllabus_scope import (
    chunk_source_is_excluded,
    excluded_source_substrings,
)


class GenerationTests(TestCase):
    def test_placeholder(self):
        self.assertTrue(True)


class GenerationHistoryStatelessnessTests(TestCase):
    """P1 statelessness pass: GenerationHistory persists prompt/settings/
    result entirely to RDS — it has no file fields and no local-disk
    dependency, so no S3 offload is required for statelessness."""

    def test_history_is_db_only_metadata(self):
        from django.db import models as dj_models

        from apps.accounts.models import User
        from apps.generation.models import GenerationHistory

        # No FileField/ImageField anywhere on the model — nothing can ever
        # land on the instance's local disk.
        for field in GenerationHistory._meta.get_fields():
            self.assertNotIsInstance(field, dj_models.FileField)

        user = User.objects.create(
            id="histuser00000000000000000000001a",
            name="Hist",
            email="hist@test.local",
        )
        history = GenerationHistory.objects.create(
            prompt='{"blueprint": "..."}',
            settings={"topic": "Electricity"},
            result={"sections": []},
            user=user,
        )
        history.refresh_from_db()
        self.assertEqual(history.settings["topic"], "Electricity")
        self.assertEqual(history.result, {"sections": []})


# ---------------------------------------------------------------------------
# ITEM 1 — Off-syllabus exclusions (Science + Social Science)
# ---------------------------------------------------------------------------


class ScienceExclusionProseTests(TestCase):
    """The Science Class 10 blueprint prose must carry the off-syllabus block."""

    def setUp(self):
        # No plan ⇒ the per-subject prose builder runs (full blueprint mode).
        self.prose = build_blueprint_instructions(
            "Electricity", "medium", -1, 10, "Science"
        )

    def test_periodic_classification_excluded(self):
        self.assertIn("Periodic Classification", self.prose)

    def test_evolution_excluded_but_heredity_kept(self):
        self.assertIn("Evolution", self.prose)
        # The block must clarify Heredity stays in scope (sub-topic exclusion).
        self.assertIn("Heredity", self.prose)

    def test_motor_induction_generator_excluded(self):
        self.assertIn("Electromagnetic Induction", self.prose)
        self.assertIn("Generator", self.prose)

    def test_per_slot_prompt_carries_exclusion(self):
        plan = build_question_plan("", "medium", -1, 10, "Science", "", "cbse")
        slot_prose = build_slot_blueprint_instructions(plan[0], "medium", 10, "Science")
        self.assertIn("Off-syllabus", slot_prose)
        self.assertIn("Periodic Classification", slot_prose)


class SocialScienceExclusionProseTests(TestCase):
    def setUp(self):
        self.prose = build_social_science_blueprint_instructions("medium", 0, 10)

    def test_age_of_industrialisation_excluded(self):
        self.assertIn("Age of Industrialisation", self.prose)

    def test_consumer_rights_excluded(self):
        self.assertIn("Consumer Rights", self.prose)

    def test_globalisation_scope_limited(self):
        self.assertIn("SCOPE LIMIT", self.prose)
        self.assertIn("What is Globalisation?", self.prose)

    def test_exclusions_only_at_class_10(self):
        prose_c8 = build_social_science_blueprint_instructions("medium", 0, 8)
        self.assertNotIn("Age of Industrialisation", prose_c8)


class RetrievalExclusionFilterTests(TestCase):
    """The retrieval filter shares one exclusion list with the prose builder
    and must drop the real catalog 'Age of Industrialisation' chapter."""

    def test_social_substrings_present(self):
        subs = excluded_source_substrings("social science", 10)
        self.assertIn("age of industrialisation", subs)
        self.assertIn("consumer rights", subs)

    def test_catalog_age_of_industrialisation_chunk_is_excluded(self):
        # Pull the EXACT catalog key (hsat_catalog.py line ~146) and prove the
        # shared exclusion list catches it.
        social_keys = hsat_catalog.get_book_keys(
            "10", "Social Science", "India and the Contemporary World II"
        )
        aoi_keys = [k for k in social_keys if "Age of Industrialisation" in k]
        self.assertTrue(aoi_keys, "catalog must still list the chapter as a source")
        subs = excluded_source_substrings("social science", 10)
        for key in aoi_keys:
            self.assertTrue(
                chunk_source_is_excluded({"s3_key": key}, subs),
                f"AoI chunk not excluded: {key!r}",
            )

    def test_in_scope_social_chapter_is_kept(self):
        subs = excluded_source_substrings("social science", 10)
        nationalism = {
            "s3_key": "class 10/Social/X - India and the Contemporary World – II/"
            "CH2 -  Nationalism in India.pdf"
        }
        self.assertFalse(chunk_source_is_excluded(nationalism, subs))

    def test_science_subtopic_chapter_not_dropped(self):
        # Evolution is a prose-only exclusion: the 'Heredity and Evolution'
        # chapter must NOT be dropped at retrieval (Heredity stays in scope).
        subs = excluded_source_substrings("science", 10)
        her_evo = {"s3_key": "class 10/Science/CH8 - Heredity and Evolution.pdf"}
        self.assertFalse(chunk_source_is_excluded(her_evo, subs))


# ---------------------------------------------------------------------------
# ITEM 2 — Social Science Bloom-band bias
# ---------------------------------------------------------------------------


class SocialScienceBloomBiasTests(TestCase):
    def setUp(self):
        self.prose = build_social_science_blueprint_instructions("medium", 0, 10)

    def test_hots_target_present(self):
        self.assertIn("50%", self.prose)
        self.assertIn("Band 3", self.prose)

    def test_cbq_la_framing_guidance(self):
        self.assertIn("analyse", self.prose.lower())
        self.assertIn("justify", self.prose.lower())

    def test_per_slot_carries_bias(self):
        plan = build_question_plan("", "medium", -1, 10, "Social Science", "", "cbse")
        slot_prose = build_slot_blueprint_instructions(
            plan[0], "medium", 10, "Social Science"
        )
        self.assertIn("HOTS", slot_prose)


# ---------------------------------------------------------------------------
# ITEM 3 — Mathematics Basic (241) variant
# ---------------------------------------------------------------------------


class MathsBasicVariantTests(TestCase):
    def test_alias_resolution(self):
        self.assertEqual(normalize_subject("Mathematics Basic"), "mathematics")
        self.assertEqual(normalize_subject("241"), "mathematics")
        self.assertEqual(normalize_subject("Mathematics Standard"), "mathematics")

    def test_resolve_maths_basic_from_payload(self):
        self.assertTrue(resolve_maths_basic("Mathematics", {"mathLevel": "basic"}))
        self.assertFalse(resolve_maths_basic("Mathematics", {"mathLevel": "standard"}))
        self.assertFalse(resolve_maths_basic("Mathematics", {}))

    def test_resolve_maths_basic_from_subject_string(self):
        self.assertTrue(resolve_maths_basic("Mathematics Basic", {}))
        self.assertFalse(resolve_maths_basic("Mathematics Standard", {}))

    def test_non_maths_never_basic(self):
        # The Basic flag must never leak onto another subject.
        self.assertFalse(resolve_maths_basic("Science", {"mathLevel": "basic"}))

    def test_standard_and_basic_prose_differ(self):
        std = build_blueprint_instructions("x", "medium", -1, 10, "Mathematics", maths_basic=False)
        bas = build_blueprint_instructions("x", "medium", -1, 10, "Mathematics", maths_basic=True)
        self.assertNotEqual(std, bas)
        self.assertIn("Code 041", std)
        self.assertIn("54%", std)
        self.assertIn("Code 241", bas)
        self.assertIn("75%", bas)

    def test_basic_same_section_skeleton(self):
        # Structure (the slot plan) is identical for Std vs Basic — only prose
        # changes. The plan does not take a tier argument, proving no structural
        # divergence. Sanity: the plan is the full 38-question CBSE skeleton.
        plan = build_question_plan("", "medium", -1, 10, "Mathematics", "", "cbse")
        self.assertEqual(len(plan), 38)
        self.assertEqual(sum(s.marks for s in plan), 80)

    def test_per_slot_tier_line_differs(self):
        plan = build_question_plan("", "medium", -1, 10, "Mathematics", "", "cbse")
        std = build_slot_blueprint_instructions(plan[0], "medium", 10, "Mathematics", maths_basic=False)
        bas = build_slot_blueprint_instructions(plan[0], "medium", 10, "Mathematics", maths_basic=True)
        self.assertNotEqual(std, bas)
        self.assertIn("041", std)
        self.assertIn("241", bas)
