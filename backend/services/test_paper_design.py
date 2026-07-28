"""Tests for the free-form paper designer.

Everything here exercises the deterministic half — `validate_design`,
`find_gaps`, `infer_settings`, `normalize_question_type`. The model call
(`design_paper`) is only touched through its fallback and its parsing of a
canned response; what a model returns is not something a test can pin down,
which is precisely why the validator exists.
"""

from django.test import TestCase

from services.paper_design import (
    DesignSection,
    Gap,
    MAX_MARKS_PER_QUESTION,
    MAX_QUESTIONS,
    PaperDesign,
    QuestionGroup,
    apply_assumed,
    design_to_slot_specs,
    find_gaps,
    header_lines,
    infer_settings,
    is_ready,
    normalize_question_type,
    validate_design,
    _design_from_raw,
)


def group(question_type="SHORT_ANSWER", marks=2, count=3, **kwargs):
    return QuestionGroup(question_type=question_type, marks=marks, count=count, **kwargs)


def design(*sections):
    return PaperDesign(sections=list(sections))


class QuestionTypeVocabularyTests(TestCase):
    def test_canonical_types_pass_through(self):
        for name in ("MCQ", "SHORT_ANSWER", "LONG_ANSWER", "CASE_STUDY"):
            self.assertEqual(normalize_question_type(name), name)

    def test_common_phrasings_map_onto_the_vocabulary(self):
        cases = {
            "multiple choice": "MCQ",
            "Multiple-Choice": "MCQ",
            "objective": "MCQ",
            "short answer": "SHORT_ANSWER",
            "long answer": "LONG_ANSWER",
            "essay": "LONG_ANSWER",
            "case study": "CASE_STUDY",
            "assertion-reason": "ASSERTION_REASON",
            "fill in the blanks": "FILL_BLANK",
            "true/false": "TRUE_FALSE",
            "match the following": "MATCH_FOLLOWING",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_question_type(raw), expected, raw)

    def test_very_short_is_not_eaten_by_short(self):
        # Longest-alias-first matching. "very short answer" contains "short
        # answer"; a naive scan would still land on SHORT_ANSWER here, but the
        # ordering is what stops "assertion and reason" resolving as "reason".
        self.assertEqual(normalize_question_type("very short answer"), "SHORT_ANSWER")
        self.assertEqual(
            normalize_question_type("assertion and reason"), "ASSERTION_REASON"
        )

    def test_unknown_types_degrade_rather_than_fail(self):
        # An unfillable slot type would strand the whole paper. A wrong-but-
        # fillable one produces a question the teacher can replace.
        self.assertEqual(normalize_question_type("interpretive dance"), "SHORT_ANSWER")
        self.assertEqual(normalize_question_type(""), "SHORT_ANSWER")
        self.assertEqual(normalize_question_type(None), "SHORT_ANSWER")


class ValidateDesignTests(TestCase):
    def test_totals_are_recomputed_not_trusted(self):
        d = validate_design(
            design(DesignSection("Section A", [group(marks=2, count=5)]))
        )
        self.assertEqual(d.total_marks, 10)
        self.assertEqual(d.total_questions, 5)

    def test_zero_and_negative_counts_are_dropped(self):
        d = validate_design(
            design(
                DesignSection("Section A", [group(count=0), group(count=3)]),
            )
        )
        self.assertEqual(d.total_questions, 3)
        self.assertTrue(any("count of 0" in c for c in d.corrections))

    def test_missing_marks_get_the_type_default(self):
        d = validate_design(
            design(DesignSection("A", [group(question_type="MCQ", marks=0, count=4)]))
        )
        self.assertEqual(d.sections[0].groups[0].marks, 1)
        self.assertEqual(d.total_marks, 4)
        self.assertTrue(any("mark value" in c for c in d.corrections))

    def test_absurd_per_question_marks_are_capped(self):
        d = validate_design(design(DesignSection("A", [group(marks=500, count=1)])))
        self.assertEqual(d.sections[0].groups[0].marks, MAX_MARKS_PER_QUESTION)
        self.assertTrue(any("capped" in c for c in d.corrections))

    def test_a_runaway_design_is_trimmed(self):
        # The pool is sized off the slot count, so an unbounded design is an
        # unbounded OpenAI bill as well as an unusable paper.
        d = validate_design(design(DesignSection("A", [group(count=5000)])))
        self.assertLessEqual(d.total_questions, MAX_QUESTIONS)
        self.assertTrue(any("Trimmed" in c for c in d.corrections))

    def test_sections_left_empty_are_removed(self):
        d = validate_design(
            design(
                DesignSection("Section A", [group(count=0)]),
                DesignSection("Section B", [group(count=2)]),
            )
        )
        self.assertEqual([s.title for s in d.sections], ["Section B"])

    def test_a_mark_mismatch_is_reported_not_silently_fixed(self):
        # Which questions to drop to hit a number is a pedagogical choice.
        # Guessing it would quietly hand back a paper nobody designed.
        d = validate_design(
            design(DesignSection("A", [group(marks=2, count=5)])), total_marks=20
        )
        self.assertEqual(d.total_marks, 10, "the structure must be left alone")
        self.assertTrue(any("20 marks" in c and "10" in c for c in d.corrections))

    def test_a_matching_total_produces_no_complaint(self):
        d = validate_design(
            design(DesignSection("A", [group(marks=2, count=10)])), total_marks=20
        )
        self.assertEqual(d.corrections, [])

    def test_a_count_mismatch_is_reported(self):
        d = validate_design(
            design(DesignSection("A", [group(count=5)])), exact_count=8
        )
        self.assertTrue(any("8 questions" in c for c in d.corrections))

    def test_validation_is_idempotent(self):
        # The endpoint validates, then the pipeline validates again on the way
        # to generation. A second pass must not re-report or re-cap anything.
        once = validate_design(design(DesignSection("A", [group(marks=2, count=5)])))
        twice = validate_design(once)
        self.assertEqual(twice.corrections, once.corrections)
        self.assertEqual(twice.total_marks, once.total_marks)

    def test_an_empty_design_survives_validation(self):
        d = validate_design(PaperDesign())
        self.assertEqual(d.sections, [])
        self.assertEqual(d.total_marks, 0)


class DesignFromRawTests(TestCase):
    def test_a_well_formed_response_is_read_faithfully(self):
        d = _design_from_raw(
            {
                "title": "Weekly Test",
                "duration": "45 minutes",
                "generalInstructions": ["All questions are compulsory."],
                "sections": [
                    {
                        "title": "Section A",
                        "instruction": "Answer in one line.",
                        "groups": [
                            {
                                "type": "mcq",
                                "marks": 1,
                                "count": 5,
                                "topic": "Photosynthesis",
                                "choice": False,
                            }
                        ],
                    }
                ],
            }
        )
        self.assertEqual(d.title, "Weekly Test")
        self.assertEqual(d.duration, "45 minutes")
        self.assertEqual(d.general_instructions, ["All questions are compulsory."])
        self.assertEqual(d.sections[0].title, "Section A")
        self.assertEqual(d.sections[0].instruction, "Answer in one line.")
        self.assertEqual(d.sections[0].groups[0].question_type, "MCQ")
        self.assertEqual(d.sections[0].groups[0].topic, "Photosynthesis")

    def test_malformed_members_are_skipped_without_losing_the_rest(self):
        d = _design_from_raw(
            {
                "sections": [
                    "not a section",
                    {"title": "A", "groups": [{"type": "mcq", "marks": "x", "count": 2}]},
                    {"title": "B", "groups": [{"type": "mcq", "marks": 1, "count": 2}]},
                ]
            }
        )
        self.assertEqual([s.title for s in d.sections], ["B"])

    def test_a_section_with_no_usable_groups_is_dropped(self):
        d = _design_from_raw({"sections": [{"title": "A", "groups": []}]})
        self.assertEqual(d.sections, [])

    def test_non_dict_input_yields_an_empty_design(self):
        for raw in (None, [], "text", 7):
            self.assertEqual(_design_from_raw(raw).sections, [])


class SlotSpecTests(TestCase):
    def test_a_design_flattens_to_the_pipeline_slot_shape(self):
        specs = design_to_slot_specs(
            design(
                DesignSection("Section A", [group(question_type="MCQ", marks=1, count=5)]),
                DesignSection("Section B", [group(marks=3, count=2, topic="Light")]),
            )
        )
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0]["section_title"], "Section A")
        self.assertEqual(specs[0]["type"], "MCQ")
        self.assertEqual(specs[0]["count"], 5)
        self.assertEqual(specs[1]["topic"], "Light")
        # The keys the pool pipeline's General Instructions branch reads.
        for spec in specs:
            self.assertLessEqual(
                {"section_title", "type", "marks", "count"}, set(spec)
            )

    def test_section_order_is_preserved(self):
        specs = design_to_slot_specs(
            design(
                DesignSection("Part 3", [group()]),
                DesignSection("Part 1", [group()]),
                DesignSection("Part 2", [group()]),
            )
        )
        self.assertEqual(
            [s["section_title"] for s in specs], ["Part 3", "Part 1", "Part 2"]
        )


class GapTests(TestCase):
    def test_a_complete_setting_set_leaves_no_gaps(self):
        gaps = find_gaps(
            {
                "subject": "Science",
                "academicClass": "10",
                "difficulty": "easy",
                "numberOfSets": "1",
                "marks": "20",
            },
            source_count=1,
        )
        self.assertEqual(gaps, [])
        self.assertTrue(is_ready(gaps))

    def test_subject_class_and_content_are_the_only_blockers(self):
        gaps = find_gaps({}, source_count=0)
        required = {g.field for g in gaps if g.kind == "required"}
        self.assertEqual(required, {"subject", "academicClass", "sources"})

    def test_a_forgotten_difficulty_is_assumed_not_demanded(self):
        # The whole point of the flow: forgetting difficulty must not stop a
        # teacher generating, but it must be visible that medium was chosen.
        gaps = find_gaps(
            {"subject": "Science", "academicClass": "10", "marks": "20"},
            source_count=1,
        )
        self.assertTrue(is_ready(gaps), "an assumed gap must not block")
        difficulty = next(g for g in gaps if g.field == "difficulty")
        self.assertEqual(difficulty.kind, "assumed")
        self.assertEqual(difficulty.value, "medium")
        self.assertTrue(difficulty.note)
        self.assertTrue(difficulty.options, "the teacher must be able to change it")

    def test_marks_are_assumed_from_the_design_when_not_stated(self):
        d = validate_design(design(DesignSection("A", [group(marks=2, count=10)])))
        gaps = find_gaps(
            {"subject": "Science", "academicClass": "10"}, d, source_count=1
        )
        marks = next(g for g in gaps if g.field == "marks")
        self.assertEqual(marks.value, "20")
        self.assertIn("20", marks.note)

    def test_marks_fall_back_to_a_default_with_no_design(self):
        gaps = find_gaps({"subject": "Science", "academicClass": "10"}, source_count=1)
        marks = next(g for g in gaps if g.field == "marks")
        self.assertEqual(marks.value, "20")

    def test_every_required_gap_is_answerable(self):
        # A blocking question with no options and no note is a dead end.
        for gap in find_gaps({}, source_count=0):
            if gap.kind == "required":
                self.assertTrue(
                    gap.options or gap.note, f"{gap.field} blocks with no way forward"
                )

    def test_blank_strings_count_as_missing(self):
        gaps = find_gaps(
            {"subject": "   ", "academicClass": "", "difficulty": "\t"},
            source_count=1,
        )
        fields = {g.field for g in gaps}
        self.assertIn("subject", fields)
        self.assertIn("academicClass", fields)
        self.assertIn("difficulty", fields)

    def test_apply_assumed_fills_only_the_assumed_ones(self):
        base = {"subject": "Science", "academicClass": "10"}
        gaps = find_gaps(base, source_count=1)
        resolved = apply_assumed(base, gaps)
        self.assertEqual(resolved["difficulty"], "medium")
        self.assertEqual(resolved["numberOfSets"], "1")
        self.assertNotIn("sources", resolved, "a required gap is not invented")

    def test_apply_assumed_never_overwrites_a_stated_value(self):
        base = {"subject": "Science", "academicClass": "10", "difficulty": "hard"}
        resolved = apply_assumed(base, find_gaps(base, source_count=1))
        self.assertEqual(resolved["difficulty"], "hard")

    def test_apply_assumed_does_not_mutate_its_input(self):
        base = {"subject": "Science", "academicClass": "10"}
        apply_assumed(base, find_gaps(base, source_count=1))
        self.assertNotIn("difficulty", base)


class InferSettingsTests(TestCase):
    def test_a_full_sentence_yields_every_stated_setting(self):
        found = infer_settings(
            "Make a class 10 Science weekly test, 20 marks, easy, 2 sets"
        )
        self.assertEqual(found["academicClass"], "10")
        self.assertEqual(found["subject"], "Science")
        self.assertEqual(found["marks"], "20")
        self.assertEqual(found["difficulty"], "easy")
        self.assertEqual(found["numberOfSets"], "2")

    def test_per_question_marks_are_not_read_as_the_paper_total(self):
        # "5 short answers of 2 marks each" must not set the paper to 2 marks.
        self.assertNotIn("marks", infer_settings("5 short answers of 2 marks each"))
        self.assertEqual(infer_settings("total 40 marks")["marks"], "40")

    def test_maths_and_sst_shorthand_resolve(self):
        self.assertEqual(infer_settings("class 9 maths test")["subject"], "Mathematics")
        self.assertEqual(infer_settings("sst revision")["subject"], "Social Science")

    def test_an_out_of_range_class_is_not_claimed(self):
        self.assertNotIn("academicClass", infer_settings("class 12 physics"))

    def test_word_numbers_for_sets(self):
        self.assertEqual(infer_settings("three sets please")["numberOfSets"], "3")

    def test_nothing_is_invented_from_empty_or_unrelated_text(self):
        self.assertEqual(infer_settings(""), {})
        self.assertEqual(infer_settings("   "), {})
        self.assertEqual(infer_settings("hello there"), {})

    def test_inference_and_gaps_agree(self):
        # What was inferred must not then be asked for — that is the bug this
        # whole flow exists to avoid.
        text = "class 10 science test, 20 marks, hard, 1 set"
        gaps = find_gaps(infer_settings(text), source_count=1)
        self.assertEqual(
            [g.field for g in gaps], [], f"re-asked for something stated: {gaps}"
        )


class HeaderLineTests(TestCase):
    def test_the_question_count_leads_the_rubric(self):
        d = validate_design(design(DesignSection("A", [group(count=5)])))
        lines = header_lines(d, {})
        self.assertIn("5 questions", lines[0])

    def test_a_single_question_is_not_pluralised(self):
        d = validate_design(design(DesignSection("A", [group(count=1)])))
        self.assertIn("1 question.", header_lines(d, {})[0])

    def test_the_designs_own_instructions_follow(self):
        d = PaperDesign(
            sections=[DesignSection("A", [group(count=2)])],
            general_instructions=["Draw diagrams where asked."],
        )
        self.assertIn("Draw diagrams where asked.", header_lines(d, {}))

    def test_the_teachers_own_words_are_carried_through_once(self):
        d = PaperDesign(
            sections=[DesignSection("A", [group(count=2)])],
            general_instructions=["Use a pencil."],
        )
        lines = header_lines(d, {"instructions": "Use a pencil."})
        self.assertEqual(lines.count("Use a pencil."), 1)


class FallbackTests(TestCase):
    def test_the_offline_fallback_still_produces_a_usable_design(self):
        from services.paper_design import _fallback_design

        d = _fallback_design("Section A: 5 MCQs, Section B: 3 short answers", 0, None)
        self.assertTrue(d.degraded)
        self.assertTrue(d.corrections, "a degraded design must say so")
        self.assertEqual(d.total_questions, 8)
        self.assertEqual([s.title for s in d.sections], ["Section A", "Section B"])

    def test_the_fallback_output_survives_validation(self):
        from services.paper_design import _fallback_design

        d = validate_design(_fallback_design("10 short answers of 2 marks", 0, None))
        self.assertGreater(d.total_questions, 0)
        self.assertTrue(d.degraded)


class BloomTests(TestCase):
    def test_no_part_of_a_design_carries_a_bloom_target(self):
        # General Instructions Mode follows the teacher's template, not the
        # board's cognitive distribution. Pool questions still get a `blooms`
        # tag from Model 1; nothing here targets or selects on one.
        d = validate_design(design(DesignSection("A", [group()])))
        serialized = d.to_dict()
        self.assertNotIn("bloom", str(serialized).lower())
        for spec in design_to_slot_specs(d):
            self.assertNotIn("bloom", str(spec).lower())
