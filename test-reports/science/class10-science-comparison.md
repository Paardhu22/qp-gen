# Class 10 Science — Generated Paper vs CBSE SQP (2025-26)

**Compared:** `qpgen-science.pdf` (our tool's output) vs `sqp-science.pdf` (official CBSE Class X Science Sample Question Paper, Code 086, 2025-26)
**Date:** 2026-07-28

Overall verdict: the **numeric blueprint** (question count, marks per question type, marks per section, total marks/questions) is reproduced almost perfectly. But the **subject-to-section mapping is broken** — questions are scattered into the wrong subject sections — and several formatting/rendering issues would make the exported paper look wrong or broken to an actual teacher/student. Details below.

---

## 1. Blueprint comparison

| | CBSE SQP | Our Generated Paper |
|---|---|---|
| Total questions | 39 | 39 ✅ |
| Total marks | 80 | 80 ✅ |
| Section A (Biology) | 16 Q / 30 M | 16 Q / 30 M ✅ |
| Section B (Chemistry) | 13 Q / 25 M | 13 Q / 25 M ✅ |
| Section C (Physics) | 10 Q / 25 M | 10 Q / 25 M ✅ |
| MCQ (1M) count | 16 (7+7+2) | 16 ✅ |
| Assertion-Reason (1M) count | 4 (2+1+1) | 4 ✅ |
| Short Answer (2M) count | 6 (3+1+2) | 6 ✅ |
| Short Answer (3M) count | 7 (2+2+3) | 7 ✅ |
| Case-based (4M) count | 3 (1 per section) | 3 ✅ |
| Long Answer (5M) count | 3 (1 per section) | 3 ✅ |

**The mark-scheme skeleton is an exact match.** Whatever logic assigns "16 MCQ, 4 AR, 6×2M, 7×3M, 3×4M, 3×5M split 30/25/25 across three sections of 16/13/10 questions" is working correctly and should not be touched.

The problem is what gets placed *inside* that skeleton.

---

## 2. Critical issue — Section headers don't match section content

The CBSE paper's own instructions state: *"Section A is Biology, Section B is Chemistry, and Section C is Physics."* Every single question in the real SQP obeys that. In our generated paper, the section headers say the same thing, but the actual question content is shuffled across all three sections almost at random. Examples:

**"Section A – Biology" contains Physics questions:**
- Q12 — hypermetropia / corrective lens (Physics, Human Eye chapter)
- Q13 — earth wire in domestic circuits (Physics, Electricity chapter)
- Q16 (OR option) — factors affecting resistance of a conductor (Physics, Electricity)

**"Section B – Chemistry" is mostly non-Chemistry:**
- Q17 — live/neutral/earth wires and 220V (Physics, Electricity)
- Q18 — synapse / gap between neurons (Biology, Control & Coordination)
- Q19 — myopia and corrective lens (Physics, Human Eye)
- Q22 — pyruvate breakdown in aerobic respiration (Biology, Life Processes)
- Q23 — magnetic field direction near a current-carrying wire (Physics, Magnetic Effects)
- Q24 — tungsten filament AR question (Physics, Electricity)
- Q25 — focal length from radius of curvature (Physics, Light)
- Q28 — puberty / adolescent changes (Biology, Heredity/Reproduction) — a full 4-mark case-based question with **zero chemistry content**
- Q29 (OR option) — myopia/hypermetropia/presbyopia (Physics)

**"Section C – Physics" is mostly non-Physics:**
- Q30 — characteristics of alkalis (Chemistry, Acids-Bases-Salts)
- Q31 — valid food chain (Biology, Our Environment)
- Q32 — AR question on translocation in phloem (Biology, Life Processes)
- Q34 — role of decomposers (Biology, Our Environment)
- Q35 — Mendel's independent inheritance experiment (Biology, Heredity)
- Q36 — why metals are stored under kerosene (Chemistry, Metals & Non-metals)
- Q37 — uterus lining / menstruation (Biology, Reproduction)
- Q38 — antacid/acidity case-based question (Chemistry) with OR option on pea-plant breeding (Biology) — again, **no actual physics** in this question at all
- Q39 — extraction of metals / neutralisation (Chemistry, 5 marks)

Net effect: a student or teacher opening "Section C – Physics" would find almost no physics in it. This is the single biggest defect — it will be immediately obvious to anyone reviewing the paper, and it means the section-assignment step of the generator isn't using subject/chapter metadata correctly even though it clearly *has* that metadata (each source PDF is chapter-tagged, e.g. CH11-Electricity.pdf, CH13-Our Environment.pdf).

**Fix needed:** the question placement logic must route Biology-chapter questions to Section A, Chemistry-chapter questions to Section B, and Physics-chapter questions to Section C — it currently ignores this and only seems to preserve the *count/mark* pattern per section, not the *subject* per section.

---

## 3. Internal choice ("OR") pairs mix unrelated subjects

In the real SQP, every internal choice is between two versions of *the same topic/chapter* — never across subjects. In our paper, several OR pairs splice together two completely unrelated topics:

- Q26: "2Cu + O2 → 2CuO, identify oxidised/reduced substance" (Chemistry) **OR** "role of adrenaline in fight-or-flight" (Biology)
- Q29: reflex action (Biology) **OR** myopia/hypermetropia/presbyopia (Physics)
- Q33: factors affecting resistance (Physics) **OR** major parts of the human brain (Biology)
- Q38: acidity/antacid case (Chemistry) **OR** pea-plant tall/short breeding experiment (Biology)

This is a separate bug from the section-mismatch issue above — even ignoring which section a question sits in, a student should never be offered "answer this Chemistry question, or instead answer this unrelated Biology question" as a choice. Real CBSE choices are same-chapter alternates (e.g., SQP Q11: heart chambers of fish vs. humans, OR water transport in plants — both stay within the Life Processes/Transportation topic family). The generator's OR-pairing step needs a same-subject (ideally same-chapter) constraint.

---

## 4. Question standard / difficulty

The CBSE SQP consistently favours **applied, multi-step, higher-order-thinking (HOTS) questions**, even at 1 mark:
- Statement-based MCQs requiring discrimination between several true/false claims (Q6: 5 statements about ozone; Q18: 4 statements about oxide reactions; Q30: 3 statements about curved mirrors).
- Numeric/data-driven case questions with tables and branching logic (Q8 titration data table with extrapolation; Q28 genetics with a 144-seedling ratio).
- Diagram-anchored reasoning (circuit diagrams, ray diagrams, magnetic field lines, atomic structure, alimentary canal figure, DSLR camera schematic).
- Real-world framed scenarios (Neha's breakfast digestion, Amrita's electrolysis experiment, Annie's watermelon pollination study, a photographer's DSLR lens).

Our generated paper leans much more toward **direct recall / short explanation**:
- MCQs are single-fact recall ("Which allotrope of carbon is a good conductor?", "What is the gap between two neurons called?") — none use the statement-based/"select the correct combination" format that appears repeatedly in the SQP.
- Short-answer questions ask for definitions/explanations ("Why is an earth wire necessary...", "What is the role of decomposers...") rather than data interpretation or calculation.
- Case-based (4M) questions are reasonably close in structure (Q15 pond ecosystem, Q38 antacid) but shorter and without any accompanying data table or diagram.
- No numeric/graphical circuit or optics problems requiring diagram interpretation, despite Electricity, Light, and Magnetic Effects chapters being in scope — the SQP leans heavily on this question style for exactly those chapters.

**Net:** the generated paper is answerable with straight textbook recall; the real SQP demands more analysis, justification, and diagram/data reading. This gap should be closed before treating a generated paper as SQP-equivalent in rigor.

---

## 5. Missing structural elements

- **No diagrams/figures anywhere.** The SQP uses 10+ diagrams (electric circuits, ray diagrams, magnetic field lines, atomic structure of P & Q, human alimentary canal, aluminium-wire-and-wax setup, electrolysis apparatus, DSLR camera schematic, optical instrument ray-trace). Our paper is 100% text — chapters like Electricity, Magnetic Effects, and Light lose an entire question style (diagram-based numericals) as a result.
- **"For visually impaired students" alternates are entirely absent.** The SQP provides an accessible alternate sub-question for every diagram-dependent question (7 instances: Q15, Q27, Q29, Q33, Q35, Q38, Q39). None of this appears in our output.
- **No visible header/general-instructions block.** The SQP opens with Max Marks (80), Time Allowed (3 hrs), and general instructions about the 39-question/3-section structure and internal choice. In the exported PDF we reviewed, Section A starts immediately on page 1 with no such header — and page 1 shows leftover editor placeholder text ("*Start writing your exam paper…*") that should never appear in an exported/final PDF. Worth checking whether this is just this particular export or a systemic export bug.

---

## 6. Rendering bug — marks column shows corrupted characters

In the exported PDF, every "1 mark" question correctly shows "1". But every question worth 2, 3, 4, or 5 marks shows a garbled, non-numeric glyph in the marks column instead of the digit (e.g. what should read "2" renders as an unrelated symbol, similarly for 3/4/5). The section-level totals still add up correctly (30/25/25/80), confirming the underlying mark values are correct — this is purely a **font/glyph rendering bug** in the PDF export for numerals other than "1", not a data problem. This should be flagged to engineering as a P1 — it makes every non-MCQ question's mark value unreadable in the exported paper.

---

## 7. What's actually working well

- Chapter coverage is broad and complete — all 13 uploaded chapters (Chemical Reactions, Acids-Bases-Salts, Metals & Non-metals, Carbon Compounds, Life Processes, Control & Coordination, How Do Organisms Reproduce, Heredity, Light, Human Eye, Electricity, Magnetic Effects, Our Environment) are represented somewhere in the 39 questions.
- The Assertion-Reason question format (option wording A–D) is reproduced exactly as CBSE phrases it.
- Case-based question sub-part structure (multi-part i/ii/iii under one scenario) is present and reasonably close in spirit, just less data/diagram-rich than the SQP.
- The mark-value-per-question-type blueprint (7 MCQ / 2 AR / 3×2M / 2×3M / 1×4M / 1×5M pattern per section, scaled correctly for each section) matches CBSE's structure exactly.

---

## Summary of action items (priority order)

1. **Fix subject→section routing** so Biology/Chemistry/Physics questions land in the section whose header matches their actual chapter/subject. This is the highest-impact fix.
2. **Constrain internal-choice (OR) pairing to same subject/chapter** — never pair a Chemistry question with a Biology or Physics alternate.
3. **Fix the marks-column glyph rendering bug** in PDF export for values 2–5.
4. Investigate the missing header/general-instructions block and the leftover "Start writing your exam paper…" placeholder text in the export.
5. Raise "question standard" — favor applied/data-driven/statement-based questions over pure recall, particularly for MCQs and short answers, to better match SQP rigor.
6. Consider whether diagram-based questions (circuits, ray diagrams, field lines) and visually-impaired-student alternates are in scope for this tool; if so, they're currently missing entirely.
