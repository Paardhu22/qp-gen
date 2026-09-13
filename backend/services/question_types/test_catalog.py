"""The catalogue is data. These tests keep the data honest.

Two jobs:

* **Integrity** — every entry obeys the catalogue's own rules, and every name
  the product has ever stored still resolves.
* **Parity** — the type lists that used to be typed out in five places are now
  derived from the catalogue. The `_OLD_*` literals below are the values those
  lists held before it existed (copied 2026-09-13). A data edit that silently
  changes today's behaviour fails here, not in a generated paper.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from services import question_types as qt
from services.question_types.catalog import ALL_ENTRIES

_OLD_QUESTION_TYPES = {
    "MCQ", "ASSERTION_REASON", "CASE_STUDY", "NUMERICAL", "DIAGRAM", "EXPERIMENTAL",
    "HOTS", "COMPETENCY", "VERY_SHORT_ANSWER", "SHORT_ANSWER", "LONG_ANSWER",
    "READING_COMP", "EXTRACT_PROSE", "EXTRACT_POETRY", "ANALYTICAL_PARAGRAPH",
    "GRAMMAR", "LETTER", "COMPOSITION", "FILL_IN_THE_BLANK", "TRUE_FALSE",
    "MATCH_THE_FOLLOWING", "ONE_WORD",
}

_OLD_OPTION_BEARING = {"MCQ", "ASSERTION_REASON", "TRUE_FALSE", "MATCH_THE_FOLLOWING"}

_OLD_LEGACY_TYPE_ACCEPTS = {
    "MCQ": {"MCQ"},
    "ASSERTION_REASON": {"ASSERTION_REASON"},
    "CASE_STUDY": {"CASE_STUDY", "READING_COMP"},
    "DIAGRAM": {"DIAGRAM"},
    "SHORT": {
        "SHORT_ANSWER", "VERY_SHORT_ANSWER", "NUMERICAL", "EXPERIMENTAL",
        "COMPETENCY", "HOTS", "GRAMMAR", "EXTRACT_PROSE", "EXTRACT_POETRY",
        "ANALYTICAL_PARAGRAPH", "FILL_IN_THE_BLANK", "TRUE_FALSE",
        "MATCH_THE_FOLLOWING", "ONE_WORD",
    },
    "LONG": {"LONG_ANSWER", "CASE_STUDY", "LETTER", "COMPOSITION", "HOTS"},
}

_OLD_TYPE_ALIASES = {
    "MULTIPLE_CHOICE": "MCQ", "MULTIPLE CHOICE": "MCQ", "MCQS": "MCQ", "OBJECTIVE": "MCQ",
    "ASSERTION": "ASSERTION_REASON", "ASSERTION_AND_REASON": "ASSERTION_REASON",
    "ASSERTION-REASON": "ASSERTION_REASON", "AR": "ASSERTION_REASON",
    "CASE": "CASE_STUDY", "CASE_BASED": "CASE_STUDY", "CBQ": "CASE_STUDY",
    "SOURCE_BASED": "CASE_STUDY", "VSA": "VERY_SHORT_ANSWER",
    "VERY_SHORT": "VERY_SHORT_ANSWER", "SA": "SHORT_ANSWER", "SHORT": "SHORT_ANSWER",
    "LA": "LONG_ANSWER", "LONG": "LONG_ANSWER", "ESSAY": "LONG_ANSWER",
    "NUMERIC": "NUMERICAL", "CALCULATION": "NUMERICAL",
    "FILL_IN_THE_BLANKS": "FILL_IN_THE_BLANK", "FILL_IN_BLANK": "FILL_IN_THE_BLANK",
    "TRUE_OR_FALSE": "TRUE_FALSE", "MATCH": "MATCH_THE_FOLLOWING",
    "MATCHING": "MATCH_THE_FOLLOWING", "DIAGRAM_BASED": "DIAGRAM", "IMAGE": "DIAGRAM",
    "IMAGE_BASED": "DIAGRAM", "PICTURE_BASED": "DIAGRAM", "GRAPH": "DIAGRAM",
}

_OLD_TOKENS = {
    "MCQ": 130, "ASSERTION_REASON": 170, "TRUE_FALSE": 90, "FILL_IN_THE_BLANK": 90,
    "ONE_WORD": 80, "MATCH_THE_FOLLOWING": 200, "VERY_SHORT_ANSWER": 130,
    "SHORT_ANSWER": 220, "NUMERICAL": 260, "EXPERIMENTAL": 260, "LONG_ANSWER": 400,
    "HOTS": 300, "COMPETENCY": 320, "CASE_STUDY": 650, "READING_COMP": 650,
    "DIAGRAM": 220, "GRAMMAR": 120, "EXTRACT_PROSE": 300, "EXTRACT_POETRY": 300,
    "ANALYTICAL_PARAGRAPH": 320, "LETTER": 400, "COMPOSITION": 400,
}

#: What the pipeline, the Builder and the replace path bucketed each type as.
#: Anything not listed was SHORT. (The router alone said SHORT for COMPOSITION.)
_OLD_BUCKETS = {
    "MCQ": "MCQ", "ASSERTION_REASON": "ASSERTION_REASON", "CASE_STUDY": "CASE_STUDY",
    "READING_COMP": "CASE_STUDY", "DIAGRAM": "DIAGRAM", "LONG_ANSWER": "LONG",
    "LETTER": "LONG", "COMPOSITION": "LONG",
}

#: `apps.projects.question_types.LEGACY_TYPE_CODE_MAP`: pool type → stored code.
_OLD_POOL_TO_STORED = {
    "MCQ": "MCQ_SINGLE", "MULTIPLE_CHOICE": "MCQ_SINGLE", "ASSERTION_REASON": "ASSERTION_REASON",
    "TRUE_FALSE": "TRUE_FALSE", "FILL_IN_THE_BLANK": "FILL_BLANK", "FILL_IN_THE_BLANKS": "FILL_BLANK",
    "MATCH_THE_FOLLOWING": "MATCH_FOLLOWING", "ONE_WORD": "ONE_WORD", "VERY_SHORT_ANSWER": "VSA",
    "SHORT_ANSWER": "SA", "LONG_ANSWER": "LA", "HOTS": "SA", "NUMERICAL": "NUMERICAL",
    "CASE_STUDY": "CASE_STUDY", "SOURCE_BASED": "SOURCE_BASED", "READING_COMP": "PASSAGE_UNSEEN",
    "EXTRACT_PROSE": "EXTRACT_SEEN", "EXTRACT_POETRY": "POETRY_APPRECIATION",
    "DIAGRAM": "DIAGRAM_DRAW", "EXPERIMENTAL": "EXPERIMENT_BASED", "GRAMMAR": "GRAMMAR_ITEM",
    "LETTER": "LETTER_WRITING", "COMPOSITION": "ESSAY_WRITING",
    "ANALYTICAL_PARAGRAPH": "ANALYTICAL_PARAGRAPH",
}

#: `apps.projects.question_types.CANONICAL_TO_POOL_TYPE`: stored code → pool type.
_OLD_STORED_TO_POOL = {
    "MCQ_SINGLE": "MCQ", "MCQ_MULTI": "MCQ", "ASSERTION_REASON": "ASSERTION_REASON",
    "TRUE_FALSE": "TRUE_FALSE", "FILL_BLANK": "FILL_IN_THE_BLANK",
    "MATCH_FOLLOWING": "MATCH_THE_FOLLOWING", "ONE_WORD": "ONE_WORD", "VSA": "VERY_SHORT_ANSWER",
    "SA": "SHORT_ANSWER", "LA": "LONG_ANSWER", "VLA": "LONG_ANSWER", "NUMERICAL": "NUMERICAL",
    "CASE_STUDY": "CASE_STUDY", "SOURCE_BASED": "CASE_STUDY", "PASSAGE_UNSEEN": "READING_COMP",
    "EXTRACT_SEEN": "EXTRACT_PROSE", "POETRY_APPRECIATION": "EXTRACT_POETRY",
    "DIAGRAM_DRAW": "DIAGRAM", "DIAGRAM_LABEL": "DIAGRAM", "EXPERIMENT_BASED": "EXPERIMENTAL",
    "GRAMMAR_ITEM": "GRAMMAR", "LETTER_WRITING": "LETTER", "EMAIL_WRITING": "LETTER",
    "ESSAY_WRITING": "COMPOSITION", "ANALYTICAL_PARAGRAPH": "ANALYTICAL_PARAGRAPH",
}

#: Every `QuestionType.code` seeded by migration 0012. Bank rows may hold any.
_SEEDED_0012 = (
    "MCQ_SINGLE", "MCQ_MULTI", "ASSERTION_REASON", "STATEMENT_EVAL", "TRUE_FALSE",
    "FILL_BLANK", "MATCH_FOLLOWING", "ONE_WORD", "ODD_ONE_OUT", "SEQUENCING",
    "CLASSIFY_SORT", "NUMERIC_ENTRY", "VSA", "SA", "LA", "VLA", "NUMERICAL",
    "PROOF_DERIVATION", "SHORT_JUSTIFY", "CASE_STUDY", "SOURCE_BASED", "PASSAGE_UNSEEN",
    "EXTRACT_SEEN", "DATA_INTERPRETATION", "CARTOON_BASED", "PICTURE_BASED",
    "AUDIO_VISUAL_STIM", "DIAGRAM_LABEL", "DIAGRAM_DRAW", "RAY_CIRCUIT_DIAGRAM",
    "MAP_SKILL", "GRAPH_PLOT", "GEOM_CONSTRUCTION", "FLOWCHART_COMPLETE",
    "TABLE_COMPLETE", "IMAGE_IDENTIFY", "DRAW_COLOUR_TRACE", "INFOGRAPHIC_BASED",
    "GRAMMAR_ITEM", "ERROR_CORRECTION", "SENTENCE_TRANSFORM", "REARRANGE_WORDS",
    "VOCABULARY_ITEM", "TRANSLATION", "LETTER_WRITING", "EMAIL_WRITING",
    "NOTICE_WRITING", "ARTICLE_WRITING", "REPORT_WRITING", "ANALYTICAL_PARAGRAPH",
    "ESSAY_WRITING", "STORY_WRITING", "DIALOGUE_WRITING", "ADVERTISEMENT_WRITING",
    "SPEECH_DEBATE_WRITING", "NOTE_MAKING_SUMMARY", "POETRY_APPRECIATION", "ORAL_TASK",
    "EXPERIMENT_BASED", "PRACTICAL_TASK", "PROJECT_WORK", "PORTFOLIO_ARTEFACT",
    "OBSERVATION_RUBRIC", "CODE_OUTPUT", "ALGORITHM_DESIGN",
)


class CatalogueIntegrityTests(SimpleTestCase):
    def test_every_entry_is_catalogued_exactly_once(self):
        self.assertEqual(len(qt.CATALOG), len(ALL_ENTRIES))

    def test_every_available_type_can_brief_model1_and_the_picker(self):
        for spec in qt.available_types():
            with self.subTest(code=spec.code):
                self.assertTrue(spec.brief.strip(), "missing brief")
                self.assertTrue(spec.example.strip(), "missing example")
                self.assertTrue(spec.tests.strip(), "missing tests")

    def test_every_code_seeded_by_0012_still_resolves(self):
        for code in _SEEDED_0012:
            with self.subTest(code=code):
                self.assertIsNotNone(qt.resolve(code))

    def test_renamed_db_codes_resolve_to_their_new_names(self):
        renamed = {
            "STATEMENT_EVAL": "MCQ_STATEMENT_EVAL",
            "ODD_ONE_OUT": "MCQ_ODD_ONE_OUT",
            "SEQUENCING": "MCQ_SEQUENCE",
            "DRAW_COLOUR_TRACE": "DRAW_COLOUR",
            "SPEECH_DEBATE_WRITING": "SPEECH_DEBATE",
        }
        for old, new in renamed.items():
            with self.subTest(old=old):
                self.assertEqual(qt.normalize_type_code(old), new)

    def test_every_runtime_shape_resolves_to_its_default_type(self):
        for shape in qt.SHAPES:
            with self.subTest(shape=shape.code):
                resolution = qt.resolve(shape.code)
                self.assertEqual(resolution.code, shape.default_type)
                self.assertEqual(set(resolution.attributes), set(shape.implies))

    def test_hots_and_competency_are_attributes_not_types(self):
        self.assertNotIn("HOTS", qt.CATALOG)
        self.assertNotIn("COMPETENCY", qt.CATALOG)
        self.assertEqual(qt.resolve("HOTS").attributes, frozenset({"hots"}))
        self.assertEqual(qt.resolve("COMPETENCY").code, "APPLICATION_SCENARIO")

    def test_structural_types_are_never_offered(self):
        for spec in qt.all_types():
            if spec.family == "STRUCTURAL":
                with self.subTest(code=spec.code):
                    self.assertFalse(spec.is_available)

    def test_picture_types_are_disabled_with_a_reason(self):
        for spec in qt.all_types():
            if spec.stimulus in {"IMAGE", "MAP", "CARTOON"}:
                with self.subTest(code=spec.code):
                    self.assertFalse(spec.is_available)
                    self.assertTrue(spec.unavailable_reason)

    def test_charts_are_available(self):
        for code in ("DATA_INTERPRETATION", "GRAPH_READ", "GRAPH_PLOT", "GRAPHICAL_SOLUTION"):
            with self.subTest(code=code):
                self.assertTrue(qt.CATALOG[code].is_available)
                self.assertTrue(qt.CATALOG[code].produces_figure)

    def test_cross_referenced_types_live_in_one_family(self):
        self.assertEqual(qt.CATALOG["CIRCLE_PICTURE"].also_in, ("I2",))
        self.assertEqual(qt.CATALOG["JOIN_DOTS"].also_in, ("I14",))
        self.assertEqual(qt.CATALOG["TICK_CROSS"].also_in, ("I20",))
        self.assertEqual(qt.CATALOG["GEOM_CONSTRUCTION"].also_in, ("G15",))

    def test_routes_name_generators_and_formats_that_exist(self):
        from services.assets.grammar import GRAMMAR_TASK_GLOSS  # noqa: F401 — registers
        from services.assets.registry import is_asset_generator
        from services.assets.writing import WRITING_FORMAT_GLOSS

        for spec in qt.all_types():
            if spec.route is None:
                continue
            with self.subTest(code=spec.code):
                self.assertTrue(is_asset_generator(spec.route.generator))
                if spec.route.generator == "writing_asset_pool":
                    self.assertIn(spec.route.asset_type, WRITING_FORMAT_GLOSS)

    def test_multi_correct_is_all_or_nothing(self):
        spec = qt.CATALOG["MCQ_MULTI"]
        self.assertTrue(spec.options.multi_correct)
        self.assertIn("all-or-nothing", spec.brief)


class DerivedListParityTests(SimpleTestCase):
    """The derived lists equal what was typed out before the catalogue."""

    def test_pool_schema_lists(self):
        from services.pool import schema

        self.assertEqual(schema.QUESTION_TYPES, _OLD_QUESTION_TYPES)
        self.assertEqual(schema.OPTION_BEARING_TYPES, _OLD_OPTION_BEARING)
        self.assertEqual(schema.LEGACY_TYPE_ACCEPTS, _OLD_LEGACY_TYPE_ACCEPTS)
        self.assertEqual(schema._TYPE_ALIASES, _OLD_TYPE_ALIASES)

    def test_assertion_reason_directions_are_unchanged(self):
        from services.pool.schema import ASSERTION_REASON_OPTIONS

        self.assertEqual(len(ASSERTION_REASON_OPTIONS), 4)
        self.assertTrue(ASSERTION_REASON_OPTIONS[0].startswith("Both Assertion (A) and Reason (R) are true and"))

    def test_model1_token_budget(self):
        from services.pool.recipes import _TOKENS_PER_QUESTION

        self.assertEqual(_TOKENS_PER_QUESTION, _OLD_TOKENS)

    def test_legacy_buckets(self):
        from services.generation_router import _legacy_question_type
        from services.pool.pipeline import _legacy_type_for as pipeline_bucket
        from services.pool.replace import _legacy_type_for as replace_bucket
        from services.templates import legacy_type_for

        for shape in _OLD_QUESTION_TYPES | {"", "UNKNOWN"}:
            expected = _OLD_BUCKETS.get(shape, "SHORT")
            for bucket in (_legacy_question_type, pipeline_bucket, replace_bucket, legacy_type_for):
                with self.subTest(shape=shape, via=bucket.__module__):
                    self.assertEqual(bucket(shape), expected)

    def test_normalize_type_agrees_with_the_old_lookup(self):
        from services.pool.schema import normalize_type

        for raw, shape in {**{s: s for s in _OLD_QUESTION_TYPES}, **_OLD_TYPE_ALIASES}.items():
            key = raw.upper().replace(" ", "_").replace("-", "_")
            if key not in _OLD_QUESTION_TYPES and key not in _OLD_TYPE_ALIASES:
                continue  # an alias written with a space was never reachable
            with self.subTest(raw=raw):
                self.assertEqual(normalize_type(raw), shape)

    def test_model_synonyms_outrank_catalogue_aliases_for_shapes(self):
        # A model writing "ESSAY" has always meant a long answer; a teacher
        # searching "essay" means the writing type.
        self.assertEqual(qt.shape_of("ESSAY"), "LONG_ANSWER")
        self.assertEqual(qt.normalize_type_code("essay"), "ESSAY_WRITING")

    def test_bank_codes_round_trip_as_before(self):
        from apps.projects.question_types import resolve_type_code, to_pool_type

        seeded = set(_SEEDED_0012)
        for pool_type, stored in _OLD_POOL_TO_STORED.items():
            with self.subTest(pool_type=pool_type):
                self.assertEqual(resolve_type_code(pool_type, valid=seeded), stored)
        for stored, pool_type in _OLD_STORED_TO_POOL.items():
            with self.subTest(stored=stored):
                self.assertEqual(to_pool_type(stored), pool_type)

    def test_a_type_the_db_lacks_falls_back_to_its_shape_default(self):
        from apps.projects.question_types import resolve_type_code

        seeded = set(_SEEDED_0012)
        self.assertEqual(resolve_type_code("COMPETENCY", valid=seeded), "SA")
        self.assertEqual(resolve_type_code("MCQ_CORRECT", valid=seeded), "MCQ_SINGLE")
