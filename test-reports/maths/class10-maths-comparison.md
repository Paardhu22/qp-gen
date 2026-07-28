# Class 10 Maths (Standard) — Generated Paper vs CBSE SQP (2025-26)

**Compared:** `qpgen-maths.pdf` (our tool's output) vs `sqp-maths.pdf` (official CBSE Class X Mathematics Standard Sample Question Paper, Code 041, 2025-26)
**Date:** 2026-07-28

Overall verdict: unlike the Science and Social Science papers, Maths has no "subject" to misroute — but it has the same class of bug wearing a different hat. Instead of subject-mismatched sections, **almost the entire 80-mark paper got dumped into "Section A," leaving Sections B, C, D and E with exactly one question each** instead of the 5/6/4/3 questions CBSE requires. The overall totals (38 questions, 80 marks) are correct — it's the internal distribution that's badly broken.

---

## 1. Blueprint comparison

| Section | CBSE SQP | Our Generated Paper |
|---|---|---|
| Total questions | 38 | 38 ✅ (right total, wrong distribution) |
| Total marks | 80 | 80 ✅ (right total, wrong distribution) |
| Section A — Objective (MCQ + AR, 1M each) | 20 Q / 20 M | 28 Q / 60 M ❌ (should be 20/20) |
| Section B — Very Short Answer (2M each) | 5 Q / 10 M | 1 Q / 2 M ❌ |
| Section C — Short Answer (3M each) | 6 Q / 18 M | 1 Q / 3 M ❌ |
| Section D — Long Answer (5M each) | 4 Q / 20 M | 1 Q / 5 M ❌ |
| Section E — Case study (4M each, 3 sub-parts) | 3 Q / 12 M | 1 Q / 4 M ❌ |
| Un-sectioned "orphan" questions before any header | 0 | 6 Q / 6 M ❌ |

(Section totals above for the generated paper are taken directly from its own printed headers — "SECTION A - OBJECTIVE QUESTIONS (28 Questions = 60 Marks)," "SECTION B ... (1 x 2 = 2 Marks)," etc. — not estimated.)

**This is the headline finding.** The generator correctly hits 38 questions and 80 marks overall, and even gets the *question-type mix* roughly right somewhere in the paper (18ish MCQs, some AR, some VSA/SA/LA-style content, one case study) — but it fails to place that content into the correct CBSE section sizes. Practically, a student opening this paper would see one enormous "Section A" (28 questions) followed by four sections that each contain a single, lonely question. That's a completely different pacing and difficulty curve from the real exam, which spreads 1-mark → 2-mark → 3-mark → 5-mark → case-study questions across five roughly-proportional sections.

**What actually seems to have happened:** Section A is explicitly labeled "OBJECTIVE QUESTIONS," but only Q1–20 are genuinely objective (MCQ/AR, matching CBSE's 18+2 pattern exactly). Q21–34 — the 14 questions also stuffed into "Section A" — are not objective at all. They're free-response VSA/SA/LA/case-study-style questions (worked proofs, multi-part "find the volume / verify the relationship" problems, even a multi-part mark-recapture population estimate that reads exactly like a Section E case study). These 14 questions are exactly the kind of content that should have been split out into Sections B, C, D and E — instead they all got left inside a section explicitly labeled "objective," and B/C/D/E were each left with a single stray leftover question.

**Fix needed:** the section-boundary/header-placement logic needs to route questions to B/C/D/E based on their actual type and mark value (2M free-response → B, 3M → C, 5M → D, 4M multi-part case study → E), rather than defaulting almost everything into Section A. This is the same underlying class of bug as the subject-routing issue found in Science and Social Science — a metadata tag exists (mark value / question type here, subject/chapter there) but isn't being used to decide final placement.

---

## 2. Off-syllabus / wrong-subject content inside the Objective section

Three of the "orphan" and Section A questions aren't Class X Maths content at all:

- **Q1** — "What is the correct negation of the statement: 'All teachers are female'?" This is propositional logic / mathematical reasoning, which isn't part of the current CBSE Class X Maths (Standard) syllabus.
- **Q9** — "One of the broad guidelines followed in the creation of the Class X Mathematics textbook is: (A) Using complex language... (B) Presenting mathematical proofs only in a didactic way... (C) Including diverse solutions to encourage creativity... (D) Excluding geometric constructions..." — this is a meta-question about the *textbook's design philosophy*, not a maths problem. It reads like it was generated from the textbook's preface/introduction rather than its actual chapter content, which suggests the source-ingestion step is occasionally pulling front-matter text into the question pool.
- **Q16** — "Which Fundamental Duty, according to the Indian Constitution, was inserted by the Constitution (86th Amendment) Act, 2002?" This is Political Science / Civics content, not Mathematics, and has no business in this paper at all.

This is worth flagging separately from the section-distribution issue because it points to a second, distinct problem: whatever is selecting source material for question generation isn't reliably filtering to in-syllabus mathematical content — it's occasionally pulling in logic-puzzle style questions, textbook meta-commentary, and content from a completely unrelated subject.

---

## 3. Missing question formats

- **No diagrams/figures anywhere**, same as the Science and Social Science papers. SQP relies on several: the Olympic-rings dotted-area figure (Q7), an incircle-of-a-triangle diagram (Q25), a tangent-circle diagram (Q26), a plotted coordinate graph the student must read values off (Q37), and a photo of India Gate (Q38). None of these have an equivalent in the generated paper — in particular, there's no coordinate-geometry "read the graph" question anywhere, a distinct skill CBSE tests that's entirely missing here.
- **No "For Visually Impaired candidates" alternates.** SQP provides 5 of these (Q7, Q25, Q26, Q31, Q37), each replacing a diagram-dependent question with a fully-worded equivalent. None appear in the generated paper — same gap flagged in both prior subject reports, now confirmed a third time.
- **Internal-choice compliance is currently moot but worth flagging for later:** CBSE requires internal choice in 2 of 5 Section B questions, 2 of 6 Section C questions, and 2 of 4 Section D questions. Since generated Sections B/C/D each contain only one question, this requirement can't really be evaluated yet — but Section C's lone question (Q36) and Section D's lone question (Q37) currently have *no* internal choice at all, which will need to be revisited once section sizes are fixed.

---

## 4. Rendering bug — marks column shows corrupted characters

Same bug already flagged in the Science and Social Science reports, now confirmed a third time: every 1-mark question shows "1" correctly, but 2/3/4/5-mark values render as garbled non-numeric glyphs in the marks column. The section header text itself (which states marks in plain words, e.g. "1 x 5 = 5 Marks") is unaffected and renders correctly — it's specifically the per-question marks-column digit that's broken for any value above 1. This is now verified across all three subjects tested, confirming it's a systemic PDF-export font/glyph issue, not a subject-specific fluke.

Also consistent across all three exports: page 1 opens with leftover editor placeholder text ("*Start writing your exam paper…*") and no Max Marks / Time Allowed / General Instructions header block — in this Maths export the problem is even more visible, since 6 full questions (Q1–6) render with no section label above them at all before the reader hits any heading.

---

## 5. Question standard / content quality (where correctly in-syllabus)

Mixed picture — better than the Science paper's mostly-recall style, but with a weaker top layer:

- **The genuinely objective questions (Q1–20, minus the 3 off-syllabus ones) skew toward definition/formula recall** rather than SQP's applied-computation style. E.g. generated Q15 just asks "what is the formula for sector area" (recite the formula), whereas SQP's analogous Q13 requires actually computing a numeric sector area from a given radius and arc length. Generated Q11 just asks "which sequence is an AP" (recognition), where SQP tends to embed AP recognition inside a word problem.
- **The Assertion-Reason questions (Q19, Q20) are genuinely good** and closely mirror SQP's own AR style and topic choices (prime factorisation / Fundamental Theorem of Arithmetic for Q19, closely paralleling SQP's own number-theory AR question).
- **The misplaced Q21–34 content (which belongs in Sections B–E) is actually solid, CBSE-appropriate work once you look past the placement bug** — a hemisphere-and-cone solid-toy volume problem, a cone-on-hemisphere volume problem, chord-segment-area and tangent-length problems, a grouped-frequency assumed-mean-method mean calculation, the classic NCERT "Aftab and his daughter's ages" problem, a cubic-polynomial zeroes-and-coefficients verification, and a genuinely good mark-recapture population-estimation case study (arguably as strong as anything in the real SQP). These match CBSE's applied, multi-step standard well.
- **One weak spot even after accounting for placement:** Q36 (currently the sole Section C / 3-mark question) just asks for the probability of rolling a sum of 7 with two dice — a much lighter question than the 3-mark slot's difficulty in the real SQP (compare to SQP's Q30, a coin-flip strategy comparison requiring justification, or Q27, a multi-teacher LCM/HCF room-allocation problem).

**Net:** the content generation itself is closer to CBSE's actual rigor for Maths than it was for Science — the real problem here is almost entirely structural (section placement), not question quality.

---

## 6. What's actually working well

- Total question count (38) and total marks (80) match the SQP exactly.
- The 18 MCQ + 2 AR = 20 objective-question pattern (Q1–20, if you set aside the 3 off-syllabus items) matches CBSE's Section A composition exactly.
- Assertion-Reason format, count, and topic choice are a strong match to SQP.
- Once mis-filed content is mentally reassigned to the section it belongs in, most individual questions (mensuration, coordinate geometry, algebra, case-study-style modelling) are well-constructed and appropriately difficult for their mark value.

---

## Summary of action items (priority order)

1. **Fix section-boundary placement** so Sections B (VSA), C (SA), D (LA), and E (case study) each receive their required 5/6/4/3 questions instead of having nearly everything default into "Section A." This is the single highest-impact fix — right now the paper's shape is unrecognizable as a CBSE-style exam even though its total marks/questions are correct.
2. **Filter out off-syllabus/wrong-subject content** at the source-ingestion step — logic/reasoning questions (Q1), textbook-meta questions (Q9), and Civics content (Q16) should never reach the question pool for a Maths paper.
3. **Fix the marks-column glyph rendering bug** (now confirmed identically across Science, Social Science, and Maths exports — a single fix should resolve it everywhere).
4. Investigate the missing header/general-instructions block and leftover "Start writing your exam paper…" placeholder text — same bug flagged in both prior reports.
5. Raise difficulty on the plain MCQ layer (Section A) toward SQP's applied-computation style rather than formula/definition recall.
6. Once section sizes are fixed, re-check internal-choice compliance (2 choice-questions required in each of Sections B, C, D; choice required in the 2-mark sub-part of every Section E question).
7. Consider whether diagram-based questions (geometry figures, coordinate-graph reading) and visually-impaired-candidate alternates are in scope; if so, they're currently missing entirely, consistent with both prior subject reports.
