"""Tests for derived paper sets (Set B, Set C).

The load-bearing properties of a variant, straight from the feature spec:

  • MCQs are never replaced — every set shares them.
  • ~30% of the paper is replaced, highest marks first (5 → 3 → 2).
  • A replacement matches the displaced question on every pedagogical
    dimension (subject/chapter/topic/type/marks/difficulty/bloom).
  • Total marks and section structure are preserved; no id repeats in a set.
  • When no parallel question exists, the original is kept.
  • Questions are shuffled within their sections, never across them.
"""

from dataclasses import dataclass

from django.test import TestCase

from services.pool.model2 import SlotAssignment
from services.pool.schema import PoolQuestion
from services.pool.set_variants import (
    derive_variant,
    derive_variants,
)


@dataclass
class FakeSlot:
    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str = "Section A"


def _q(qid, qtype="SHORT_ANSWER", marks=3, topic="t", blooms="UNDERSTAND",
       difficulty="medium", chapter="Electricity", subject="Science"):
    return PoolQuestion(
        id=qid, subject=subject, chapter=chapter, topic=topic, type=qtype,
        blooms=blooms, difficulty=difficulty, marks=marks,
        question=f"Question {qid}?",
        options=["a", "b", "c", "d"] if qtype == "MCQ" else [],
        answer="a", explanation="because",
    )


def _assign(question, index, section="Section A"):
    slot = FakeSlot(
        index=index, marks=question.marks, question_type=question.type,
        legacy_type="MCQ" if question.type == "MCQ" else "SHORT",
        section_title=section,
    )
    return SlotAssignment(slot=slot, question=question)


def _ids(assignments):
    return [a.question.id for a in assignments]


class ReplacementRulesTests(TestCase):
    def test_mcqs_are_never_replaced(self):
        # Master: 4 MCQs. Pool has parallel MCQs available — they must stay.
        master = [_assign(_q(f"m{i}", qtype="MCQ", marks=1, topic="t"), i)
                  for i in range(1, 5)]
        pool = list(a.question for a in master) + [
            _q("alt1", qtype="MCQ", marks=1, topic="t"),
            _q("alt2", qtype="MCQ", marks=1, topic="t"),
        ]
        variant = derive_variant(master, pool, label="B", seed=1)
        self.assertEqual(variant.replaced_count, 0)
        self.assertEqual(set(_ids(variant.assignments)),
                         {"m1", "m2", "m3", "m4"})

    def test_replaces_roughly_thirty_percent(self):
        # 10 short-answer slots, each with a parallel in the pool.
        master = [_assign(_q(f"s{i}", topic=f"topic{i}"), i)
                  for i in range(1, 11)]
        pool = list(a.question for a in master) + [
            _q(f"alt{i}", topic=f"topic{i}") for i in range(1, 11)
        ]
        variant = derive_variant(master, pool, label="B", seed=1)
        # round(0.30 * 10) == 3
        self.assertEqual(variant.replaced_count, 3)

    def test_higher_marks_replaced_first(self):
        # One 5-mark, one 3-mark, one 2-mark; target is 1 replacement.
        master = [
            _assign(_q("five", marks=5, topic="a"), 1),
            _assign(_q("three", marks=3, topic="b"), 2),
            _assign(_q("two", marks=2, topic="c"), 3),
        ]
        pool = list(a.question for a in master) + [
            _q("five_alt", marks=5, topic="a"),
            _q("three_alt", marks=3, topic="b"),
            _q("two_alt", marks=2, topic="c"),
        ]
        variant = derive_variant(master, pool, label="B", seed=1)
        self.assertEqual(variant.replaced_count, 1)
        # The 5-mark slot is the one that changed.
        by_marks = {a.question.marks: a.question.id for a in variant.assignments}
        self.assertEqual(by_marks[5], "five_alt")
        self.assertEqual(by_marks[3], "three")
        self.assertEqual(by_marks[2], "two")

    def test_replacement_matches_every_dimension(self):
        master = [_assign(_q("orig", marks=5, topic="acids",
                             blooms="ANALYZE", difficulty="hard"), 1)]
        pool = [
            master[0].question,
            # Wrong bloom — must NOT be chosen.
            _q("wrong_bloom", marks=5, topic="acids",
               blooms="REMEMBER", difficulty="hard"),
            # Wrong topic — must NOT be chosen.
            _q("wrong_topic", marks=5, topic="bases",
               blooms="ANALYZE", difficulty="hard"),
            # The only true parallel.
            _q("parallel", marks=5, topic="acids",
               blooms="ANALYZE", difficulty="hard"),
        ]
        # Force the single slot to be targeted so this isolates the match rule.
        variant = derive_variant(master, pool, label="B", seed=3,
                                 replace_fraction=1.0)
        self.assertEqual(_ids(variant.assignments), ["parallel"])

    def test_retains_original_when_no_parallel_exists(self):
        master = [_assign(_q("orig", marks=5, topic="unique"), 1)]
        pool = [master[0].question]  # nothing to swap to
        # Even when 100% is targeted, a missing parallel keeps the original.
        variant = derive_variant(master, pool, label="B", seed=1,
                                 replace_fraction=1.0)
        self.assertEqual(variant.replaced_count, 0)
        self.assertEqual(_ids(variant.assignments), ["orig"])


class InvariantTests(TestCase):
    def _big_master(self):
        master = []
        for i in range(1, 7):
            master.append(_assign(_q(f"a{i}", qtype="MCQ", marks=1, topic=f"t{i}"),
                                   i, section="Section A"))
        for i in range(1, 7):
            master.append(_assign(_q(f"b{i}", marks=3, topic=f"u{i}"),
                                   6 + i, section="Section B"))
        return master

    def _big_pool(self, master):
        pool = [a.question for a in master]
        for i in range(1, 7):
            pool.append(_q(f"b{i}_alt", marks=3, topic=f"u{i}"))
        return pool

    def test_total_marks_preserved(self):
        master = self._big_master()
        pool = self._big_pool(master)
        original_marks = sum(a.question.marks for a in master)
        variant = derive_variant(master, pool, label="B", seed=2)
        self.assertEqual(
            sum(a.question.marks for a in variant.assignments), original_marks
        )

    def test_no_duplicate_ids_within_variant(self):
        master = self._big_master()
        pool = self._big_pool(master)
        variant = derive_variant(master, pool, label="B", seed=2)
        ids = _ids(variant.assignments)
        self.assertEqual(len(ids), len(set(ids)))

    def test_sections_preserved_and_not_mixed(self):
        master = self._big_master()
        pool = self._big_pool(master)
        variant = derive_variant(master, pool, label="B", seed=2)
        titles = [a.slot.section_title for a in variant.assignments]
        # Section A block, then Section B block — contiguous, in order.
        self.assertEqual(titles, ["Section A"] * 6 + ["Section B"] * 6)

    def test_order_differs_from_master(self):
        master = self._big_master()
        pool = self._big_pool(master)
        variant = derive_variant(master, pool, label="B", seed=2)
        self.assertNotEqual(_ids(variant.assignments), _ids(master))


class MultipleVariantsTests(TestCase):
    def test_two_variants_diverge_from_each_other(self):
        master = [_assign(_q(f"s{i}", marks=5, topic=f"topic{i}"), i)
                  for i in range(1, 9)]
        pool = [a.question for a in master] + [
            _q(f"alt{i}a", marks=5, topic=f"topic{i}") for i in range(1, 9)
        ] + [
            _q(f"alt{i}b", marks=5, topic=f"topic{i}") for i in range(1, 9)
        ]
        variants = derive_variants(master, pool, num_variants=2)
        self.assertEqual([v.label for v in variants], ["B", "C"])
        # B and C should not be identical selections.
        self.assertNotEqual(
            sorted(_ids(variants[0].assignments)),
            sorted(_ids(variants[1].assignments)),
        )
