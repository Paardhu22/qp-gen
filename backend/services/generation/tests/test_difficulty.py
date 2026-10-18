"""The difficulty slider: a level becomes a mix, and the mix becomes per-slot tiers."""

import random
from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace

from django.test import SimpleTestCase

from services.generation import difficulty as D
from services.generation.planner.plan import build_question_plan
from services.generation.planner.slots import QuestionGenerationSlot
from services.generation.pool.model2 import _score_question, build_candidates
from services.generation.pool.recipes import Batch, TypeQuota, batches_for_subject, with_difficulty_mix
from services.generation.pool.schema import PoolQuestion

RANK = {"easy": 0, "medium": 1, "hard": 2}
BANDS = (1, 4, 7, 10)


def _slot(marks=1, question_type="MCQ", **kwargs):
    return SimpleNamespace(marks=marks, question_type=question_type, hots=False, competency=False, **kwargs)


def _paper():
    """A board-shaped paper: 20 one-markers, then 2-, 3-, 4- and 5-mark questions."""
    return (
        [_slot(1, "MCQ") for _ in range(20)]
        + [_slot(2, "SHORT_ANSWER") for _ in range(5)]
        + [_slot(3, "SHORT_ANSWER") for _ in range(6)]
        + [_slot(4, "CASE_STUDY") for _ in range(3)]
        + [_slot(5, "LONG_ANSWER") for _ in range(4)]
    )


class LevelTests(SimpleTestCase):
    def test_numbers_are_clamped_and_rounded(self):
        self.assertEqual(D.normalize_level(72), 72)
        self.assertEqual(D.normalize_level(72.6), 73)
        self.assertEqual(D.normalize_level(-5), 0)
        self.assertEqual(D.normalize_level(400), 100)
        self.assertEqual(D.normalize_level("35"), 35)

    def test_the_old_labels_map_to_their_anchors(self):
        self.assertEqual(
            [D.normalize_level(w) for w in ("easy", "Medium", " HARD ")], [15, 50, 85]
        )

    def test_anything_unreadable_is_the_default_not_an_error(self):
        for junk in (None, "", "tricky", True, [], {}):
            self.assertEqual(D.normalize_level(junk), D.DEFAULT_LEVEL, junk)

    def test_the_slider_wins_over_the_label(self):
        self.assertEqual(D.resolve_level({"difficultyLevel": 90, "difficulty": "easy"}), 90)
        self.assertEqual(D.resolve_level({"difficulty": "hard"}), 85)
        self.assertEqual(D.resolve_level({}, "easy"), 15)
        self.assertEqual(D.resolve_level({"difficultyLevel": 0}), 0)  # zero is a level, not "unset"

    def test_the_label_follows_the_level(self):
        self.assertEqual([D.label_for_level(n) for n in (0, 33, 34, 66, 67, 100)],
                         ["easy", "easy", "medium", "medium", "hard", "hard"])


class SharesTests(SimpleTestCase):
    def test_shares_always_sum_to_one_and_are_never_negative(self):
        for band in BANDS:
            for level in range(0, 101, 5):
                shares = D.shares_for(level, band)
                self.assertAlmostEqual(sum(shares.values()), 1.0, places=4)
                self.assertTrue(all(v >= 0 for v in shares.values()), (band, level))

    def test_the_anchors_are_the_end_and_middle_of_the_slider(self):
        for band_class, band in ((10, "9-10"), (7, "6-8"), (4, "3-5"), (1, "1-2")):
            for level, anchor in ((0, "low"), (50, "mid"), (100, "high")):
                got = tuple(D.shares_for(level, band_class).values())
                self.assertEqual(got, D.ANCHORS[band][anchor])

    def test_moving_the_slider_moves_the_mix_progressively(self):
        for band in BANDS:
            previous = D.shares_for(0, band)
            for level in range(1, 101):
                current = D.shares_for(level, band)
                self.assertGreaterEqual(current["hard"], previous["hard"] - 1e-9, (band, level))
                self.assertLessEqual(current["easy"], previous["easy"] + 1e-9, (band, level))
                previous = current

    def test_a_small_step_is_a_small_change(self):
        for band in BANDS:
            for level in range(0, 100):
                a, b = D.shares_for(level, band), D.shares_for(level + 1, band)
                self.assertLess(max(abs(a[t] - b[t]) for t in D.TIERS), 0.01)

    def test_the_low_end_is_mostly_straightforward_but_not_all_basic(self):
        low = D.shares_for(0, 10)
        self.assertGreater(low["easy"] + low["medium"], 0.85)
        self.assertLess(low["easy"], 1.0)

    def test_the_middle_is_a_balanced_mixture(self):
        mid = D.shares_for(50, 10)
        self.assertGreaterEqual(min(mid.values()), 0.2 - 1e-9)
        self.assertGreater(mid["medium"], mid["easy"])
        self.assertGreater(mid["medium"], mid["hard"])

    def test_the_top_is_demanding_but_board_appropriate(self):
        """Challenging tops out below half the paper and basic questions never vanish."""
        for band in BANDS:
            top = D.shares_for(100, band)
            self.assertLessEqual(top["hard"], 0.45 + 1e-9, band)
            self.assertGreaterEqual(top["easy"], 0.12 - 1e-9, band)
        top = D.shares_for(100, 10)
        self.assertGreater(top["hard"], top["easy"] * 3)

    def test_the_top_end_really_differs_from_the_bottom(self):
        """The complaint: easy and hard came out alike. The mix must differ a lot."""
        low, high = D.shares_for(0, 10), D.shares_for(100, 10)
        self.assertGreaterEqual(high["hard"] / low["hard"], 4)
        self.assertGreaterEqual(low["easy"] / high["easy"], 4)

    def test_younger_classes_lean_easier_at_the_same_level(self):
        for level in (50, 100):
            self.assertLess(D.shares_for(level, 2)["hard"], D.shares_for(level, 5)["hard"])
            self.assertLess(D.shares_for(level, 5)["hard"], D.shares_for(level, 10)["hard"])

    def test_no_class_means_the_board_year(self):
        self.assertEqual(D.shares_for(70, None), D.shares_for(70, 10))


class TierCountsTests(SimpleTestCase):
    def test_counts_always_add_up(self):
        for total in (0, 1, 2, 5, 7, 20, 38, 100):
            for level in range(0, 101, 7):
                counts = D.tier_counts(total, D.shares_for(level, 10))
                self.assertEqual(sum(counts), total)
                self.assertTrue(all(c >= 0 for c in counts))

    def test_hard_never_shrinks_and_easy_never_grows_as_the_level_rises(self):
        for total in (3, 5, 12, 38, 50):
            previous = D.tier_counts(total, D.shares_for(0, 10))
            for level in range(1, 101):
                current = D.tier_counts(total, D.shares_for(level, 10))
                self.assertGreaterEqual(current[2], previous[2], (total, level))
                self.assertLessEqual(current[0], previous[0], (total, level))
                previous = current


class AssignTiersTests(SimpleTestCase):
    def test_every_slot_gets_a_tier_in_order(self):
        slots = _paper()
        tiers = D.assign_tiers(slots, 50, 10)
        self.assertEqual(len(tiers), len(slots))
        self.assertTrue(set(tiers) <= set(D.TIERS))

    def test_the_paper_holds_the_mix_that_was_asked_for(self):
        slots = _paper()
        for level in (0, 25, 50, 75, 100):
            counts = Counter(D.assign_tiers(slots, level, 10))
            expected = D.tier_counts(len(slots), D.shares_for(level, 10))
            self.assertEqual((counts["easy"], counts["medium"], counts["hard"]), expected, level)

    def test_raising_the_level_never_makes_a_slot_easier(self):
        for slots in (_paper(), [_slot(1)] * 7, [_slot(5, "LONG_ANSWER")] * 4):
            previous = D.assign_tiers(slots, 0, 10)
            for level in range(1, 101):
                current = D.assign_tiers(slots, level, 10)
                for before, after in zip(previous, current):
                    self.assertGreaterEqual(RANK[after], RANK[before], level)
                previous = current

    def test_the_paper_shifts_progressively(self):
        """Each step of the slider changes at most a couple of slots."""
        slots = _paper()
        previous = D.assign_tiers(slots, 0, 10)
        for level in range(1, 101):
            current = D.assign_tiers(slots, level, 10)
            self.assertLessEqual(sum(a != b for a, b in zip(previous, current)), 3, level)
            previous = current

    def test_hard_questions_grow_in_number_with_the_level(self):
        slots = _paper()
        hard = [Counter(D.assign_tiers(slots, level, 10))["hard"] for level in (0, 25, 50, 75, 100)]
        self.assertEqual(hard, sorted(hard))
        self.assertGreater(hard[-1], 3 * hard[0])

    def test_the_mix_is_carried_through_the_paper_not_parked_in_one_section(self):
        slots = _paper()
        tiers = D.assign_tiers(slots, 60, 10)
        one_markers = tiers[:20]
        self.assertGreater(Counter(one_markers)["hard"], 0)
        self.assertGreater(Counter(one_markers)["easy"], 0)
        self.assertGreater(Counter(one_markers)["medium"], 0)

    def test_hard_slots_are_spread_out_not_clumped(self):
        tiers = D.assign_tiers([_slot(1) for _ in range(20)], 60, 10)
        longest = run = 0
        for tier in tiers:
            run = run + 1 if tier == "hard" else 0
            longest = max(longest, run)
        self.assertLessEqual(longest, 2)

    def test_higher_marks_lean_harder_without_taking_every_hard_question(self):
        slots = _paper()
        hard_by_marks = Counter()
        total_by_marks = Counter()
        for level in range(30, 71, 5):
            for slot, tier in zip(slots, D.assign_tiers(slots, level, 10)):
                total_by_marks[slot.marks] += 1
                hard_by_marks[slot.marks] += tier == "hard"
        rate = {m: hard_by_marks[m] / total_by_marks[m] for m in total_by_marks}
        self.assertGreater(rate[5], rate[1])
        self.assertGreater(rate[1], 0)

    def test_higher_order_slots_lean_harder(self):
        self.assertGreater(
            D.slot_affinity(SimpleNamespace(marks=3, question_type="SHORT_ANSWER", hots=True)),
            D.slot_affinity(SimpleNamespace(marks=3, question_type="SHORT_ANSWER", hots=False)),
        )
        self.assertLess(D.slot_affinity(_slot(1, "TRUE_FALSE")), D.slot_affinity(_slot(1, "MCQ")))

    def test_it_is_deterministic(self):
        slots = _paper()
        self.assertEqual(D.assign_tiers(slots, 63, 10), D.assign_tiers(list(slots), 63, 10))

    def test_degenerate_plans_do_not_fail(self):
        self.assertEqual(D.assign_tiers([], 50, 10), [])
        self.assertEqual(len(D.assign_tiers([_slot()], 100, 10)), 1)
        self.assertTrue(set(D.assign_tiers([_slot(), _slot()], 100, 10)) <= set(D.TIERS))

    def test_a_real_class_10_maths_plan_holds_the_requested_mix_at_every_level(self):
        plan = list(build_question_plan(
            topic="", difficulty="medium", count=-1, class_num=10,
            subject="Mathematics", instructions="", count_variation="cbse",
        ))
        self.assertGreater(len(plan), 30)
        for level in (0, 20, 50, 80, 100):
            counts = Counter(D.assign_tiers(plan, level, 10))
            expected = D.tier_counts(len(plan), D.shares_for(level, 10))
            self.assertEqual((counts["easy"], counts["medium"], counts["hard"]), expected, level)


class ApplyProfileTests(SimpleTestCase):
    def _real_plan(self):
        return list(build_question_plan(
            topic="", difficulty="medium", count=-1, class_num=10,
            subject="Science", instructions="", count_variation="cbse",
        ))

    def test_every_slot_is_stamped_with_a_tier_and_its_difficulty(self):
        plan = self._real_plan()
        stamped = D.apply_profile(plan, 100, 10)
        self.assertEqual(len(stamped), len(plan))
        for slot in stamped:
            self.assertIn(slot.tier, D.TIERS)
            self.assertEqual(slot.difficulty, slot.tier)
        self.assertGreater(D.mix_of(stamped)["hard"], 0)

    def test_nothing_else_about_a_slot_changes(self):
        plan = self._real_plan()
        for before, after in zip(plan, D.apply_profile(plan, 70, 10)):
            self.assertEqual((before.marks, before.question_type, before.section_title, before.index),
                             (after.marks, after.question_type, after.section_title, after.index))

    def test_the_original_plan_is_left_alone(self):
        plan = self._real_plan()
        D.apply_profile(plan, 100, 10)
        self.assertTrue(all(slot.tier == "" for slot in plan))

    def test_a_slot_that_cannot_take_a_tier_is_left_as_it_is(self):
        plain = SimpleNamespace(marks=1, question_type="MCQ")
        self.assertEqual(D.apply_profile([plain], 50, 10), [plain])

    def test_the_summary_says_what_was_asked_and_dealt(self):
        stamped = D.apply_profile(self._real_plan(), 85, 10)
        summary = D.profile_summary(stamped, 85, 10)
        self.assertEqual((summary["level"], summary["label"], summary["band"]), (85, "hard", "9-10"))
        self.assertAlmostEqual(sum(summary["shares"].values()), 1.0, places=4)
        self.assertEqual(sum(summary["counts"].values()), len(stamped))


class DifficultyMixTests(SimpleTestCase):
    """`with_difficulty_mix` hands each Model 1 quota the mix its slots were dealt."""

    def _stamped(self, level=100):
        plan = list(build_question_plan(
            topic="", difficulty="medium", count=-1, class_num=10,
            subject="Mathematics", instructions="", count_variation="cbse",
        ))
        return D.apply_profile(plan, level, 10)

    def test_a_plan_without_tiers_leaves_the_batches_untouched(self):
        batches = batches_for_subject("mathematics", target_total=50)
        plan = list(build_question_plan(
            topic="", difficulty="medium", count=-1, class_num=10,
            subject="Mathematics", instructions="", count_variation="cbse",
        ))
        self.assertEqual(with_difficulty_mix(batches, plan), batches)
        self.assertEqual(with_difficulty_mix(batches, None), batches)

    def test_every_fixed_recipe_quota_gets_a_mix_that_adds_up_to_its_count(self):
        batches = with_difficulty_mix(batches_for_subject("mathematics", target_total=60), self._stamped())
        for batch in batches:
            for quota in batch.quotas:
                self.assertEqual(sum(quota.tiers), quota.count, (batch.name, quota))

    def test_scaling_a_quota_up_keeps_its_proportions(self):
        slots = [_slot(1, "MCQ", tier=t) for t in ("easy", "easy", "medium", "hard")]
        quota = TypeQuota("MCQ", 1, 8)  # the pool is twice the paper
        (batch,) = with_difficulty_mix([Batch("mcq_1m", [quota])], slots)
        self.assertEqual(batch.quotas[0].tiers, (4, 2, 2))

    def test_a_shape_the_plan_does_not_have_takes_the_whole_papers_mix(self):
        slots = [_slot(1, "MCQ", tier="hard"), _slot(1, "MCQ", tier="hard")]
        (batch,) = with_difficulty_mix([Batch("x", [TypeQuota("LONG_ANSWER", 5, 4)])], slots)
        self.assertEqual(batch.quotas[0].tiers, (0, 0, 4))

    def test_marks_and_shape_pick_which_slots_set_the_mix(self):
        slots = (
            [_slot(1, "MCQ", tier="easy") for _ in range(4)]
            + [_slot(5, "LONG_ANSWER", tier="hard") for _ in range(4)]
        )
        batches = with_difficulty_mix(
            [Batch("a", [TypeQuota("MCQ", 1, 4)]), Batch("b", [TypeQuota("LONG_ANSWER", 5, 4)])], slots
        )
        self.assertEqual(batches[0].quotas[0].tiers, (4, 0, 0))
        self.assertEqual(batches[1].quotas[0].tiers, (0, 0, 4))

    def test_the_paper_wide_mix_survives_the_split_across_quotas(self):
        stamped = self._stamped(100)
        batches = with_difficulty_mix(batches_for_subject("mathematics", target_total=len(stamped)), stamped)
        totals = [sum(q.tiers[i] for b in batches for q in b.quotas) for i in range(3)]
        self.assertGreater(totals[2], totals[0])  # at the top of the slider, more hard than easy


class PromptTests(SimpleTestCase):
    def test_the_rule_defines_all_three_tiers(self):
        text = D.rule_text(50, 10, "Mathematics")
        for needle in ("easy (basic)", "medium (moderate)", "hard (challenging)"):
            self.assertIn(needle, text)

    def test_easy_is_basic_but_not_trivial(self):
        text = D.rule_text(0, 10, "Science")
        self.assertIn("never a bare lookup", text)
        self.assertIn("single concept and a single step", text)

    def test_hard_stays_inside_the_syllabus(self):
        text = D.rule_text(100, 9, "Science")
        self.assertIn("Class 9 syllabus", text)
        self.assertIn("no off-syllabus topics", text)
        self.assertIn("competition-style", text)
        self.assertIn("not impossible", text)

    def test_a_harder_question_must_be_harder_in_thinking_not_in_numbers(self):
        self.assertIn("never write a harder question by changing the numbers", D.rule_text(50, 10, "Mathematics"))

    def test_the_rule_states_the_papers_overall_mix(self):
        self.assertIn(D.describe_mix(100, 10), D.rule_text(100, 10, "Science"))
        self.assertNotEqual(D.describe_mix(0, 10), D.describe_mix(100, 10))

    def test_the_hard_tier_is_worded_for_the_subject(self):
        self.assertIn("coordinate-geometry", D.rule_text(50, 10, "Mathematics"))
        self.assertIn("causes and consequences", D.rule_text(50, 10, "Social Science"))
        self.assertIn("inference", D.rule_text(50, 10, "English Language & Literature"))
        self.assertIn("unfamiliar situation", D.rule_text(50, 10, "Science"))

    def test_subject_families(self):
        self.assertEqual(
            [D.subject_family(s) for s in ("Mathematics Standard", "Social Science", "Hindi Course B", "Physics")],
            ["maths", "social", "language", "science"],
        )

    def test_the_batch_line_counts_each_tier_and_skips_empty_ones(self):
        self.assertEqual(D.mix_instruction((0, 0, 0)), "")
        line = D.mix_instruction((3, 0, 2))
        self.assertIn("3 basic (`easy`)", line)
        self.assertIn("2 challenging (`hard`)", line)
        self.assertNotIn("moderate", line)

    def test_the_asset_generators_are_told_the_papers_mix(self):
        brief = D.paper_brief(85, 10)
        self.assertIn("level 85/100", brief)
        self.assertIn(D.describe_mix(85, 10), brief)
        self.assertIn("syllabus", brief)


@dataclass
class _TierSlot:
    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str = "Section A"
    tier: str = ""
    difficulty: str = ""
    type_code: str = ""
    hots: bool = False
    competency: bool = False
    asset_type: str = ""
    source: str = ""
    generator: str = "question_pool"


def _pool_question(qid, difficulty, topic=None):
    return PoolQuestion(
        id=qid, subject="Science", chapter="C", topic=topic or f"topic {qid}", type="MCQ",
        blooms="UNDERSTAND", difficulty=difficulty, marks=1, question=f"Q {qid}?",
        options=["a", "b", "c", "d"], answer="a", explanation="because",
    )


class SelectionTests(SimpleTestCase):
    @staticmethod
    def _score(question, **kwargs):
        return _score_question(
            question, used_topics=Counter(), used_blooms=Counter(), used_difficulty=Counter(),
            used_chapters=Counter(), total_slots=10, difficulty_target="medium",
            rng=random.Random(0), **kwargs,
        )

    def test_a_slot_prefers_the_question_written_at_its_tier(self):
        for tier in D.TIERS:
            scores = {d: self._score(_pool_question("q", d), slot_tier=tier) for d in D.TIERS}
            self.assertEqual(max(scores, key=scores.get), tier, tier)

    def test_the_next_tier_over_is_a_fallback_and_the_far_end_is_penalised(self):
        near = self._score(_pool_question("q", "medium"), slot_tier="hard")
        far = self._score(_pool_question("q", "easy"), slot_tier="hard")
        match = self._score(_pool_question("q", "hard"), slot_tier="hard")
        self.assertGreater(match, near)
        self.assertGreater(near, far)
        self.assertGreaterEqual(match - far, 2 * (match - near) - 1e-9)

    def test_the_tier_preference_is_stronger_than_the_old_spread_nudge(self):
        self.assertGreater(self._score(_pool_question("q", "hard"), slot_tier="hard")
                           - self._score(_pool_question("q", "easy"), slot_tier="hard"), 10)

    def test_without_a_tier_the_old_behaviour_applies(self):
        a = self._score(_pool_question("q", "medium"))
        b = self._score(_pool_question("q", "hard"), slot_tier="")
        self.assertLess(abs(a - b), 2.0)

    def test_a_paper_is_assembled_at_the_mix_the_slots_were_dealt(self):
        """Selection follows the tiers, so a 'hard' paper really picks harder questions."""
        pool = (
            [_pool_question(f"e{i}", "easy") for i in range(12)]
            + [_pool_question(f"m{i}", "medium") for i in range(12)]
            + [_pool_question(f"h{i}", "hard") for i in range(12)]
        )

        def assemble(level):
            slots = [
                _TierSlot(index=i + 1, marks=1, question_type="MCQ", legacy_type="MCQ")
                for i in range(12)
            ]
            slots = D.apply_profile(slots, level, 10)
            assigned, unfilled = build_candidates(pool, slots, class_num=10, seed=1)
            self.assertEqual(unfilled, [])
            return Counter(a.question.difficulty for a in assigned)

        gentle, demanding = assemble(0), assemble(100)
        self.assertGreater(gentle["easy"], gentle["hard"])
        self.assertGreater(demanding["hard"], demanding["easy"])
        self.assertGreater(demanding["hard"], gentle["hard"])
        self.assertGreater(gentle["easy"], demanding["easy"])

    def test_a_thin_pool_still_fills_every_slot(self):
        pool = [_pool_question(f"m{i}", "medium") for i in range(6)]
        slots = D.apply_profile(
            [_TierSlot(index=i + 1, marks=1, question_type="MCQ", legacy_type="MCQ") for i in range(6)], 100, 10
        )
        assigned, unfilled = build_candidates(pool, slots, class_num=10, seed=1)
        self.assertEqual((len(assigned), unfilled), (6, []))


class SlotFieldTests(SimpleTestCase):
    def test_the_planners_slot_carries_a_tier_that_defaults_to_empty(self):
        fields = {f.name for f in QuestionGenerationSlot.__dataclass_fields__.values()}
        self.assertIn("tier", fields)
        self.assertEqual(QuestionGenerationSlot.__dataclass_fields__["tier"].default, "")


class FrontendMirrorTests(SimpleTestCase):
    """The slider previews the curve in the browser; the two copies must agree."""

    @staticmethod
    def _source():
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR).parent / "frontend" / "features" / "generation" / "difficulty-profile.ts"
        return path.read_text(encoding="utf-8")

    def test_the_anchors_are_identical(self):
        import re

        source = self._source()
        found = {}
        for band, low, mid, high in re.findall(
            r'"(\d-\d+)":\s*\{\s*low:\s*\[([^\]]*)\],\s*mid:\s*\[([^\]]*)\],\s*high:\s*\[([^\]]*)\]\s*\}', source
        ):
            found[band] = {
                key: tuple(float(x) for x in values.split(","))
                for key, values in (("low", low), ("mid", mid), ("high", high))
            }
        self.assertEqual(set(found), set(D.ANCHORS), "a class band is missing from one side")
        for band, anchors in D.ANCHORS.items():
            for key, python_values in anchors.items():
                self.assertEqual(found[band][key], python_values, (band, key))

    def test_the_old_labels_mean_the_same_level(self):
        import re

        source = self._source()
        match = re.search(r"LABEL_LEVELS[^=]*=\s*\{\s*easy:\s*(\d+),\s*medium:\s*(\d+),\s*hard:\s*(\d+)", source)
        self.assertIsNotNone(match)
        self.assertEqual(tuple(int(x) for x in match.groups()), tuple(D.LABEL_LEVELS[t] for t in D.TIERS))

    def test_the_label_thresholds_are_identical(self):
        source = self._source()
        self.assertIn(f"n < {D._MEDIUM_FROM}", source)
        self.assertIn(f"n < {D._HARD_FROM}", source)
