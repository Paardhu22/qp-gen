"""Tests for the template layer that replaced the QP Type fork.

The things that must not drift:
  * a blueprint's totals are always computed from its slots, never trusted
    from the client;
  * a round trip through the Builder does not lose what the blueprint engine
    decided but the Builder does not show;
  * every built-in the picker offers can actually be resolved.
"""

from __future__ import annotations

from django.test import TestCase

from services.template_catalog import (
    KIND_BLANK,
    KIND_CBSE,
    KIND_INSTRUCTIONS,
    get_entry,
    list_templates,
    resolve_builtin,
    resolve_detailed,
)
from services.templates import (
    SOURCE_GENERATE,
    SOURCE_SAVED,
    SlotSpec,
    TemplateBlueprint,
    apply_source_ratio,
    default_marks_for,
    question_types_for,
)


class _FakeSlot:
    """Stands in for QuestionGenerationSlot without importing the engine."""

    def __init__(self, **kwargs):
        self.index = kwargs.get("index", 1)
        self.marks = kwargs.get("marks", 1)
        self.question_type = kwargs.get("question_type", "MCQ")
        self.legacy_type = kwargs.get("legacy_type", "MCQ")
        self.section_title = kwargs.get("section_title", "Section A")
        self.choice_required = kwargs.get("choice_required", False)
        self.generator = kwargs.get("generator", "question_pool")
        self.asset_type = kwargs.get("asset_type", "")
        self.constraints = kwargs.get("constraints", {})
        self.validation = kwargs.get("validation", ())
        self.instruction_hint = kwargs.get("instruction_hint", "")


class BlueprintTotalsTests(TestCase):
    def test_totals_are_computed_from_slots_not_read_from_the_client(self):
        # The single most likely thing to arrive from an editing UI is a stale
        # total. A paper whose header contradicts its own contents is worse
        # than one that recomputes.
        blueprint = TemplateBlueprint.from_dict(
            {
                "slots": [
                    {"questionType": "MCQ", "marks": 1},
                    {"questionType": "SHORT_ANSWER", "marks": 3},
                ],
                "totalMarks": 999,
                "totalQuestions": 42,
            }
        )
        self.assertEqual(blueprint.total_questions, 2)
        self.assertEqual(blueprint.total_marks, 4)
        self.assertEqual(blueprint.as_dict()["totalMarks"], 4)

    def test_slots_are_reindexed_in_order(self):
        blueprint = TemplateBlueprint.from_dict(
            {"slots": [{"index": 77}, {"index": 3}, {"index": 12}]}
        )
        self.assertEqual([s.index for s in blueprint.slots], [1, 2, 3])

    def test_a_malformed_slot_is_dropped_not_fatal(self):
        # One bad slot must not cost the teacher the whole blueprint.
        blueprint = TemplateBlueprint.from_dict(
            {"slots": [{"questionType": "MCQ"}, "not a slot", {"questionType": "MCQ"}]}
        )
        self.assertEqual(blueprint.total_questions, 2)

    def test_section_order_follows_first_appearance(self):
        blueprint = TemplateBlueprint.from_dict(
            {
                "slots": [
                    {"sectionTitle": "Section A"},
                    {"sectionTitle": "Section B"},
                    {"sectionTitle": "Section A"},
                ]
            }
        )
        self.assertEqual(blueprint.section_order(), ["Section A", "Section B"])


class SlotSpecTests(TestCase):
    def test_an_unknown_question_type_falls_back_rather_than_rejecting(self):
        slot = SlotSpec.from_dict({"questionType": "INTERPRETIVE_DANCE"}, index=1)
        self.assertEqual(slot.question_type, "SHORT_ANSWER")

    def test_type_aliases_are_folded(self):
        # The Builder may send what a teacher's saved template recorded years
        # ago; normalize_type is the one authority on what a type string means.
        self.assertEqual(
            SlotSpec.from_dict({"questionType": "multiple choice"}, index=1).question_type,
            "MCQ",
        )

    def test_marks_default_to_the_type_when_absent(self):
        slot = SlotSpec.from_dict({"questionType": "LONG_ANSWER"}, index=1)
        self.assertEqual(slot.marks, default_marks_for("LONG_ANSWER"))

    def test_zero_marks_falls_back_to_the_type_default_not_to_one(self):
        # A 0-mark slot is a data error, and the type's natural mark value is a
        # better recovery than the smallest legal number — a "short answer"
        # that silently became 1 mark is a wrong paper, not a fixed one.
        slot = SlotSpec.from_dict({"questionType": "SHORT_ANSWER", "marks": 0}, index=1)
        self.assertEqual(slot.marks, default_marks_for("SHORT_ANSWER"))

    def test_marks_are_clamped_to_a_sane_range(self):
        self.assertEqual(SlotSpec.from_dict({"marks": -5}, index=1).marks, 1)
        self.assertEqual(SlotSpec.from_dict({"marks": 5000}, index=1).marks, 20)
        self.assertEqual(SlotSpec.from_dict({"marks": "four"}, index=1).marks,
                         default_marks_for("SHORT_ANSWER"))

    def test_an_unknown_source_falls_back_to_generate(self):
        slot = SlotSpec.from_dict({"source": "telepathy"}, index=1)
        self.assertEqual(slot.source, SOURCE_GENERATE)

    def test_engine_fields_survive_a_builder_round_trip(self):
        # The Builder does not show `generator`, so nothing in the UI can
        # preserve it — the passthrough is what stops an edited slot losing
        # its routing.
        original = TemplateBlueprint.from_plan(
            [_FakeSlot(generator="reading", question_type="MCQ")]
        )
        self.assertEqual(original.slots[0].passthrough["generator"], "reading")

        round_tripped = TemplateBlueprint.from_dict(original.as_dict())
        self.assertEqual(round_tripped.slots[0].passthrough["generator"], "reading")

    def test_structural_detail_survives_a_builder_round_trip(self):
        # `constraints`, `validation` and `instruction_hint` are not routing
        # decisions like `generator` — they are the word counts, sub-question
        # patterns and validation-rule names an asset generator needs, and the
        # CBSE composite-question notes Model 1 needs. A Builder round trip
        # that drops them makes an asset generator fall back to hardcoded
        # defaults and a validation rule a permanent no-op.
        engine_slot = _FakeSlot(
            generator="reading",
            question_type="READING_COMP",
            asset_type="discursive_passage",
            constraints={"word_count": (350, 450), "sub_questions": 8},
            validation=("passage_word_count", "sub_question_count"),
            instruction_hint="Q1 (10m): an unseen discursive passage.",
        )
        original = TemplateBlueprint.from_plan([engine_slot])
        passthrough = original.slots[0].passthrough
        self.assertEqual(
            passthrough["constraints"], {"word_count": (350, 450), "sub_questions": 8}
        )
        self.assertEqual(
            passthrough["validation"], ("passage_word_count", "sub_question_count")
        )
        self.assertEqual(
            passthrough["instruction_hint"],
            "Q1 (10m): an unseen discursive passage.",
        )

        # And through an actual JSON round trip — the shape the Builder
        # travels over the wire in, which turns tuples into lists.
        import json

        wire = json.loads(json.dumps(original.as_dict()))
        round_tripped = TemplateBlueprint.from_dict(wire)
        rt_passthrough = round_tripped.slots[0].passthrough
        self.assertEqual(rt_passthrough["validation"], [
            "passage_word_count", "sub_question_count",
        ])
        self.assertEqual(rt_passthrough["instruction_hint"], engine_slot.instruction_hint)


class SourceRatioTests(TestCase):
    def _blueprint(self, count):
        return TemplateBlueprint.from_dict(
            {"slots": [{"questionType": "MCQ", "marks": 1} for _ in range(count)]}
        )

    def test_the_ratio_is_stored_per_slot(self):
        blueprint = apply_source_ratio(self._blueprint(10), saved=4)
        self.assertEqual(blueprint.saved_count, 4)
        self.assertEqual(blueprint.generated_count, 6)
        self.assertEqual(
            [s.source for s in blueprint.slots[:4]], [SOURCE_SAVED] * 4
        )

    def test_asking_for_more_saved_than_slots_is_clamped(self):
        blueprint = apply_source_ratio(self._blueprint(5), saved=99)
        self.assertEqual(blueprint.saved_count, 5)
        self.assertEqual(blueprint.generated_count, 0)

    def test_a_contradictory_pair_honours_saved(self):
        # One number cannot contradict the other; saved is the authority.
        blueprint = apply_source_ratio(self._blueprint(10), saved=3, generated=99)
        self.assertEqual(blueprint.saved_count, 3)
        self.assertEqual(blueprint.generated_count, 7)

    def test_reapplying_a_smaller_ratio_releases_slots(self):
        blueprint = apply_source_ratio(self._blueprint(10), saved=8)
        apply_source_ratio(blueprint, saved=2)
        self.assertEqual(blueprint.saved_count, 2)


class CatalogTests(TestCase):
    def test_the_two_old_modes_both_exist_as_templates(self):
        ids = {entry["id"] for entry in list_templates()}
        # "General Instructions Mode" and "Board Mode" are gone as modes; both
        # have to be reachable as starting points or the merge lost a feature.
        self.assertIn("describe-it-yourself", ids)
        self.assertIn("cbse-science-10", ids)

    def test_every_listed_template_can_be_resolved(self):
        # A card the picker offers but the Builder cannot open is the worst
        # failure this layer has, and it is invisible until someone clicks it.
        for entry in list_templates():
            self.assertIsNotNone(
                get_entry(entry["id"]), f"{entry['id']} is listed but unknown"
            )

    def test_blank_resolves_to_an_empty_blueprint(self):
        blueprint = resolve_builtin("blank")
        self.assertEqual(blueprint.total_questions, 0)

    def test_describe_it_yourself_with_no_prose_costs_no_model_call(self):
        # Opening the Builder before typing must not spend a model call to be
        # told there is nothing to design.
        blueprint = resolve_builtin("describe-it-yourself", instructions="")
        self.assertEqual(blueprint.total_questions, 0)

    def test_an_unknown_template_id_raises(self):
        with self.assertRaises(ValueError):
            resolve_builtin("no-such-template")

    def test_a_board_card_reports_the_class_and_subject_it_stands_for(self):
        # The Builder adopts these into its rail. Before they were returned,
        # the client kept its own copy of "a CBSE card carries a class", and a
        # card whose class disagreed with the rail resolved one paper and
        # generated another.
        resolved = resolve_detailed("cbse-science-10")
        self.assertEqual(resolved.detected["subject"], "Science")
        self.assertEqual(resolved.detected["academicClass"], "10")

    def test_templates_with_nothing_to_say_report_nothing(self):
        # Absent, not blank: the Builder reads a missing key as "leave the
        # teacher's own setting alone".
        self.assertEqual(resolve_detailed("blank").detected, {})
        self.assertEqual(
            resolve_detailed("describe-it-yourself", instructions="").detected, {}
        )

    def test_resolve_builtin_still_hands_back_a_bare_blueprint(self):
        # The narrow entry point is what most callers use; it must not start
        # returning the richer object underneath them.
        self.assertIsInstance(resolve_builtin("cbse-science-10"), TemplateBlueprint)

    def test_the_catalog_covers_the_engine_matrix(self):
        # The catalog is derived from _NEW_ENGINE_ELIGIBILITY precisely so a
        # supported subject can never be missing from the picker.
        from services.generation_router import _NEW_ENGINE_ELIGIBILITY

        ids = {entry["id"] for entry in list_templates()}
        for subject_norm, classes in _NEW_ENGINE_ELIGIBILITY.items():
            for class_num in classes:
                expected = f"cbse-{subject_norm.replace(' ', '-')}-{class_num}"
                self.assertIn(expected, ids, f"{expected} missing from the picker")

    def test_filtering_narrows_board_templates_but_keeps_the_universal_ones(self):
        listed = list_templates(subject="Science", academic_class="10")
        ids = {entry["id"] for entry in listed}
        self.assertIn("cbse-science-10", ids)
        self.assertNotIn("cbse-mathematics-10", ids)
        # "Describe It Yourself" is valid for a subject with no blueprint at
        # all, so a filter must never remove it.
        self.assertIn("describe-it-yourself", ids)

    def test_kinds_are_what_the_client_switches_on(self):
        by_id = {e["id"]: e for e in list_templates()}
        self.assertEqual(by_id["blank"]["kind"], KIND_BLANK)
        self.assertEqual(by_id["describe-it-yourself"]["kind"], KIND_INSTRUCTIONS)
        self.assertEqual(by_id["cbse-science-10"]["kind"], KIND_CBSE)


class QuestionTypeMenuTests(TestCase):
    def test_the_menu_is_grouped_for_scanning(self):
        groups = {option["group"] for option in question_types_for("Science")}
        self.assertIn("Objective", groups)
        self.assertIn("Descriptive", groups)

    def test_every_option_carries_a_default_mark_value(self):
        # Changing a slot's type must be able to fill in sensible marks, or
        # every type change becomes two edits.
        for option in question_types_for():
            self.assertGreaterEqual(option["defaultMarks"], 1)

    def test_placeholder_mapping_offers_every_type_to_every_subject(self):
        # The subject-appropriate mapping is specified as coming later; until
        # it does this must not silently filter anything out.
        self.assertEqual(
            len(question_types_for("Science")), len(question_types_for("English"))
        )


class BlueprintToPlanTests(TestCase):
    """The Builder's edits have to survive into the paper.

    A modal that lets a teacher change question 7 to an MCQ and then produces
    a long answer is worse than one that never offered the control.
    """

    def _blueprint(self, slots):
        return TemplateBlueprint.from_dict({"slots": slots})

    def test_edited_types_and_marks_reach_the_plan(self):
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(
            self._blueprint(
                [
                    {"questionType": "MCQ", "marks": 1, "sectionTitle": "A"},
                    {"questionType": "LONG_ANSWER", "marks": 5, "sectionTitle": "B"},
                ]
            )
        )
        self.assertEqual([s.question_type for s in plan], ["MCQ", "LONG_ANSWER"])
        self.assertEqual([s.marks for s in plan], [1, 5])
        self.assertEqual([s.section_title for s in plan], ["A", "B"])

    def test_legacy_type_is_derived_so_model_2_can_fill_the_slot(self):
        # `legacy_type` is what `slot_accepts` gates on. A slot without one is
        # unfillable, which shows up as a silently short paper.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(
            self._blueprint([{"questionType": "LONG_ANSWER", "marks": 5}])
        )
        self.assertEqual(plan[0].legacy_type, "LONG")

    def test_changing_the_type_rebuckets_the_slot(self):
        # The engine said MCQ; the teacher changed it to a long answer. Keeping
        # the engine's "MCQ" bucket would let an MCQ fill a prose slot.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(
            self._blueprint(
                [
                    {
                        "questionType": "LONG_ANSWER",
                        "marks": 5,
                        "passthrough": {"legacy_type": "MCQ"},
                    }
                ]
            )
        )
        self.assertEqual(plan[0].legacy_type, "LONG")

    def test_an_untouched_slot_keeps_the_engines_own_bucket(self):
        # SHORT accepts more types than `legacy_type_for` would derive, so a
        # slot the teacher did not touch must keep what the engine decided.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(
            self._blueprint(
                [
                    {
                        "questionType": "SHORT_ANSWER",
                        "marks": 2,
                        "passthrough": {"legacy_type": "SHORT"},
                    }
                ]
            )
        )
        self.assertEqual(plan[0].legacy_type, "SHORT")

    def test_generator_routing_survives_an_edit(self):
        # An English Reading slot must still route to the reading generator
        # after the teacher changed its marks.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(
            self._blueprint(
                [
                    {
                        "questionType": "READING_COMP",
                        "marks": 12,
                        "passthrough": {"generator": "reading"},
                    }
                ]
            )
        )
        self.assertEqual(plan[0].generator, "reading")

    def test_structural_detail_survives_an_edit(self):
        # `constraints` and `validation` are what let `services.assets.reading`
        # write a real passage instead of falling back to its hardcoded
        # defaults, and what let `services.assets.validation` run real checks
        # instead of silently checking nothing. A slot the teacher only
        # touched the marks on must keep both — and `validation`, which
        # travels the wire as a JSON array, must come back as the tuple
        # `slot_accepts` and the asset generators expect.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(
            self._blueprint(
                [
                    {
                        "questionType": "READING_COMP",
                        "marks": 12,
                        "passthrough": {
                            "generator": "reading",
                            "asset_type": "discursive_passage",
                            "constraints": {"word_count": [350, 450], "sub_questions": 8},
                            "validation": ["passage_word_count", "sub_question_count"],
                            "instruction_hint": "Q1 (10m): an unseen discursive passage.",
                        },
                    }
                ]
            )
        )
        slot = plan[0]
        self.assertEqual(
            slot.constraints, {"word_count": [350, 450], "sub_questions": 8}
        )
        self.assertEqual(
            slot.validation, ("passage_word_count", "sub_question_count")
        )
        self.assertIsInstance(slot.validation, tuple)
        self.assertEqual(
            slot.instruction_hint, "Q1 (10m): an unseen discursive passage."
        )

    def test_a_slot_with_no_passthrough_gets_empty_structural_detail(self):
        # A hand-added Builder slot has no engine history to restore, so it
        # must default to empty rather than error — never `None`, since every
        # consumer does `getattr(slot, "constraints", {}) or {}`.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(self._blueprint([{"questionType": "MCQ"}]))
        self.assertEqual(plan[0].constraints, {})
        self.assertEqual(plan[0].validation, ())
        self.assertEqual(plan[0].instruction_hint, "")

    def test_a_slot_with_no_passthrough_defaults_to_the_textbook_pool(self):
        # Everything a teacher adds by hand in the Builder lands here, and it
        # must route somewhere real or the slot is dropped by partition_plan.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(self._blueprint([{"questionType": "MCQ"}]))
        self.assertEqual(plan[0].generator, "question_pool")

    def test_the_plan_exposes_every_attribute_model_2_reads(self):
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(self._blueprint([{"questionType": "MCQ"}]))
        for attribute in (
            "index", "marks", "question_type", "legacy_type", "section_title",
            "generator", "choice_required",
            "asset_type",
        ):
            self.assertTrue(
                hasattr(plan[0], attribute), f"slots must expose {attribute}"
            )

    def test_the_plan_exposes_every_attribute_asset_generators_read(self):
        # Distinct from the Model-2 attribute set above: `constraints` and
        # `validation` are read by services.assets.* and services.pool.recipes,
        # never by Model 2, so they earn their own contract test rather than
        # being folded into (or confused with) the Model-2 one.
        from services.templates import blueprint_to_plan

        plan = blueprint_to_plan(self._blueprint([{"questionType": "MCQ"}]))
        for attribute in ("constraints", "validation", "instruction_hint"):
            self.assertTrue(
                hasattr(plan[0], attribute), f"slots must expose {attribute}"
            )


class BuilderPipelineEndToEndTests(TestCase):
    """The full trip: an engine slot, through the Builder, into a real consumer.

    `BlueprintToPlanTests` proves the dataclasses carry the data. This proves
    it actually reaches something that acts on it — `batches_from_plan`, which
    is the reason `instruction_hint` exists at all (a 12-mark composite slot
    with no hint comes back from Model 1 as one plain essay instead of the
    five-sub-question bundle the blueprint asked for).
    """

    def test_instruction_hint_reaches_model_1s_recipe_after_a_builder_round_trip(self):
        import json

        from services.pool.recipes import batches_from_plan
        from services.templates import blueprint_to_plan

        engine_slot = _FakeSlot(
            question_type="SHORT_ANSWER",
            marks=12,
            asset_type="short_answer_bundle",
            instruction_hint=(
                "Q8 (12m): ONE question object containing FIVE numbered "
                "sub-questions of 3 marks each; answer any four."
            ),
        )

        # Project to the Builder, send it over the wire, and read it back —
        # exactly what happens when a teacher opens the Builder on this
        # template and saves it without touching this slot.
        blueprint = TemplateBlueprint.from_plan([engine_slot])
        wire = json.loads(json.dumps(blueprint.as_dict()))
        rebuilt = TemplateBlueprint.from_dict(wire)

        plan = blueprint_to_plan(rebuilt)
        batches = batches_from_plan(plan)

        self.assertEqual(len(batches), 1)
        quota = batches[0].quotas[0]
        self.assertIn(engine_slot.instruction_hint, quota.hints)

    def test_asset_constraints_reach_the_reading_generator_after_a_builder_round_trip(self):
        # The specific failure the audit named: "asset generators fall back to
        # hardcoded defaults" when the Builder drops `constraints`. Proven here
        # by calling the generator's real instruction builder and checking the
        # word count it actually asks for — 350-450 (the blueprint's own
        # figure) rather than 250-400 (`ReadingAssetGenerator`'s hardcoded
        # fallback for a slot with no constraints at all).
        import json

        from services.assets.base import AssetRequest
        from services.assets.reading import ReadingAssetGenerator
        from services.templates import blueprint_to_plan

        engine_slot = _FakeSlot(
            question_type="READING_COMP",
            marks=10,
            generator="reading_asset_pool",
            asset_type="discursive_passage",
            constraints={"word_count": [350, 450], "sub_questions": 8},
        )

        blueprint = TemplateBlueprint.from_plan([engine_slot])
        wire = json.loads(json.dumps(blueprint.as_dict()))
        rebuilt = TemplateBlueprint.from_dict(wire)
        plan = blueprint_to_plan(rebuilt)
        slot = plan[0]

        generator = ReadingAssetGenerator()
        request = AssetRequest(
            slots=(slot,), subject="English", subject_norm="english", class_num=10,
        )
        constraints = dict(getattr(slot, "constraints", {}) or {})
        instruction = generator._instruction(
            request, slot, constraints, wanted=1, avoid_topics=()
        )
        self.assertIn("350", instruction)
        self.assertIn("450", instruction)
        self.assertNotIn("250–400 words", instruction)
