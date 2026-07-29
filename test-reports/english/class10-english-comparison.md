# Class 10 English Language & Literature — Generated Paper vs CBSE SQP (2025-26)

**Compared:** `qpgen-english.pdf` (our tool's output) vs `sqp-english.pdf` (official CBSE Class X English L&L Sample Question Paper, Code 184, 2025-26) vs `english-structure.pdf` (CBSE's official curriculum circular defining the section weightage, word limits and prescribed books)
**Date:** 2026-07-29

Overall verdict: this is a different failure pattern from Science, Social Science and Maths. The **numeric blueprint is a perfect match** — 11 questions, 80 marks, the exact 20/20/40 section split, and even the "10 of 12" grammar instruction reproduced correctly. The problems are entirely inside the content: one passage is far short of its required word count, the two literature "reference to context" questions have lost their either/or structure, and — most seriously — a full 12-mark question is built around a poem that isn't in the CBSE Class X syllabus at all.

---

## 1. Blueprint comparison

| | CBSE structure / SQP | Our Generated Paper |
|---|---|---|
| Total questions | 11 | 11 ✅ |
| Total marks | 80 | 80 ✅ |
| Section A — Reading Skills | 2 Q / 20 M | 2 Q / 20 M ✅ |
| Section B — Grammar & Writing | 3 Q / 20 M | 3 Q / 20 M ✅ |
| Section C — Literature Textbook | 6 Q / 40 M | 6 Q / 40 M ✅ |
| Grammar: "attempt any 10 of 12" | Yes | Yes ✅ |
| Discursive passage word count | 400–450 words | 246 words ❌ |
| Case-based passage word count | 200–250 words | 235 words ✅ |

This is the best structural match of the four subjects tested so far — question count, section marks, and even the specific "10 of 12" grammar instruction are reproduced exactly. The defects below are all about what's *inside* that correct skeleton.

---

## 2. Reading passage is well short of its required length

The in-app warning ("Q1 reading asset — passage is 246 words, blueprint asks for 350–450") was accurate, though worth flagging that the blueprint's own floor (350) is already looser than CBSE's actual published spec (400–450, per the structure document) — so even the tool's internal target undersells the real requirement.

- **Q1 (discursive passage, worth 10 marks):** 246 words. CBSE requires 400–450. That's roughly 40–45% short.
- **Q2 (case-based/statistical passage, worth 10 marks):** 235 words against a 200–250 target — **this one is correct.**

The two passages are correctly *typed* — Q1 reads as genuine discursive opinion writing (mirrors the SQP's own "indigenous crafts" essay), Q2 is genuinely data/statistics-driven prose (mirrors the SQP's own pen-preference study) — so the passage-type-to-slot assignment is right. It's specifically the discursive passage generator that's undershooting length. Combined passage length is 481 words against CBSE's 600–700-word combined target, and that shortfall is almost entirely attributable to Q1.

**Fix needed:** the discursive-passage generator (or its length constraint) needs to target the full 400–450 word range, not something closer to half that.

---

## 3. Reading comprehension question craft is genuinely strong

Worth calling out separately because it's a real positive, and a contrast with the recall-heavy MCQs seen in the Science report. Q1's eight sub-questions include an EXCEPT-format MCQ, a fill-in-context vocabulary item, a TRUE/FALSE statement judgment, an **analogy completion** ("sustainability : future generations :: technology : ___"), a **paragraph-main-idea matching table**, and two evidence-synthesis 2-mark questions. All of these formats are lifted directly from the SQP's own repertoire (the SQP uses the identical analogy format in its Q1-V and an identical matching-table format in its Q1-VII). This is a strong, faithful match to CBSE's actual question craft for this section.

---

## 4. Reference-to-Context questions (Q6, Q7) have lost their either/or structure

This is the most concrete formatting defect in the paper. Per the structure document, "Reference to the Context" is two separate 5-mark questions: **one** extract chosen from two Drama/Prose options, and **one** extract chosen from two Poetry options — each printed as "Extract A ... OR ... Extract B" with only one sub-question set to answer. The SQP does exactly this for its Q6 and Q7.

In the generated paper:

- **Q6** prints an unexplained, unlabelled prose excerpt (a short quote about "Richie" and his mother, presumably from *The Making of a Scientist*) with **no sub-questions of its own**, immediately followed — with no "OR," no "Extract A / Extract B" labelling, and no "answer ANY ONE of the two" instruction — by a second, fully-formed extract from *Tea from Assam* (*Glimpses of India*, FIRST FLIGHT) that does carry its own (a)–(d) sub-questions.
- **Q7** does the same thing with two full poems: *Fog* (with sub-questions i–iv) and *Dust of Snow* (with its own sub-questions a–d) are both printed in full, one after another, with no either/or choice between them.

Both cases look like the same underlying bug: whatever assembles this question type isn't correctly separating the two OR-alternatives into "print one, offer it as a choice" — it's printing both in full, and in Q6's case even seems to have dropped the first extract's sub-questions entirely. A student opening this paper would have no idea whether they're meant to answer one extract or both, and Q6/Q7's printed sub-question count doesn't cleanly reconcile with their declared 5-mark value.

**Fix needed:** the Reference-to-Context question type specifically needs the same "Extract A [sub-questions] OR Extract B [sub-questions]" treatment the Writing section (Q4, Q5) already gets correctly elsewhere in the same paper — this is clearly not a systemic OR-handling failure, since Q4 and Q5 render their either/or choice correctly. It's isolated to this one question type.

---

## 5. Q8 (12 marks — the single largest question in the paper) is built on a poem that isn't in the syllabus

Q8 asks students to answer 4 of 5 questions about "the poet['s] ... 'turning' to live with animals," "Walt Whitman's unconventional style in 'Song of Myself'," and related themes. **"Song of Myself" by Walt Whitman is not part of the CBSE Class X curriculum.** The prescribed FIRST FLIGHT poems are: *Dust of Snow, Fire and Ice, A Tiger in the Zoo, How to Tell Wild Animals, The Ball Poem, Amanda!, The Trees, Fog, The Tale of Custard the Dragon, For Anne Gregory* — Whitman appears nowhere in this list, nor in FOOTPRINTS WITHOUT FEET. This slot (structure doc item #8) is explicitly required to draw "from the book FIRST FLIGHT."

This means 12 of the paper's 80 marks — 15% of the entire exam — rest on content a CBSE Class X student would never have been taught. This is the single most serious defect found in this comparison, and mirrors (in a different form) the off-syllabus contamination already flagged in the Maths report (the Constitution/Civics question, the textbook-meta question) — a second, independent confirmation that the source-selection step for question generation isn't reliably staying inside the uploaded/prescribed syllabus.

---

## 6. Q9 (the "FOOTPRINTS WITHOUT FEET" slot) contains zero FOOTPRINTS content

Structure doc item #9 requires this 6-mark question ("2 of 3," 40–50 words each) to be sourced exclusively from FOOTPRINTS WITHOUT FEET. The SQP's own Q9 gets this right: it asks about *The Necklace*, *The Thief's Story*, and Griffin's invisibility (*Footprints Without Feet* itself) — all three genuinely from FOOTPRINTS.

The generated paper's Q9, by contrast, asks:
- Why Anne Frank named her diary "Kitty" — ***From the Diary of Anne Frank***, FIRST FLIGHT prose.
- What the parenthetical stanzas in "Amanda!" represent — ***Amanda!***, FIRST FLIGHT poetry.
- Why Mr. Keesing assigned Anne extra homework — again ***From the Diary of Anne Frank***, FIRST FLIGHT prose.

All three options in a slot that's supposed to be FOOTPRINTS-only are actually FIRST FLIGHT material. This is the same class of bug flagged repeatedly in the Science and Social Science reports — content tagged for one bucket (there, a subject; here, a prescribed book) lands in the wrong bucket — just showing up in a new place: the two literature textbooks instead of two chapters.

---

## 7. Q10 and Q11 each pair a correctly-sourced option with a wrong-book option

Structure doc items #10 and #11 require Q10 to be FIRST-FLIGHT-only and Q11 to be FOOTPRINTS-only (each "1 of 2," ~100–120 words, 6 marks) — matching the SQP's Q10 (*Baker from Goa/Coorg/Tea from Assam* OR *The Trees/A Tiger in the Zoo*, both FIRST FLIGHT) and Q11 (*The Midnight Visitor* OR *The Triumph of Surgery*, both FOOTPRINTS).

- **Generated Q10** (should be FIRST-FLIGHT-only): Option A is *The Midnight Visitor* — **FOOTPRINTS**, wrong book. Option B is *The Proposal* — FIRST FLIGHT, correct.
- **Generated Q11** (should be FOOTPRINTS-only): Option A is *The Book That Saved the Earth* — FOOTPRINTS, correct. Option B is *Mijbil the Otter* — **FIRST FLIGHT**, wrong book.

Same pattern as the internal-choice mixing already flagged in the Science and Social Science reports: real CBSE papers always pair two same-book (or same-chapter) alternatives inside one OR choice, never a book that belongs to a different slot's syllabus scope.

---

## 8. What's actually working well

- The paper's overall blueprint (11 questions, 80 marks, 20/20/40 split, "10 of 12" grammar instruction) is an exact match — the best of the four subjects tested.
- Grammar (Q3) covers determiners, tenses, modals, subject–verb concord, and all three reported-speech sub-types (commands, statements, questions) with well-constructed gap-fill/error-correction items comparable in quality to the SQP's own.
- Writing Skills (Q4 formal letter, Q5 analytical paragraph) are strongly matched in both format and theme to the SQP's own prompts (digital-security/civic-issue letters; data-driven comparison-and-recommend paragraphs) — genuinely close to CBSE's real question style.
- Reading comprehension question variety (analogy completion, paragraph-matching table, EXCEPT-format MCQs, evidence-synthesis questions) faithfully reproduces CBSE's actual craft, not just generic recall questions.
- Case-based passage (Q2) hits its word-count target and is correctly built around embedded statistical data, matching the structure doc's requirement and the SQP's own approach.

---

## 9. Confirmed again — issues shared with the Science, Social Science and Maths reports

- **Marks-column rendering bug**: 1-mark values render correctly; every other value (5, 6, 10, 12) shows as a garbled non-numeric glyph in the exported PDF. Now confirmed identically across all four subjects tested — this is a single systemic PDF-export bug, not a subject-specific issue.
- **Missing header / leftover placeholder text**: page 1 opens directly into "SECTION A" with no Max Marks / Time Allowed / General Instructions block, and shows the leftover editor placeholder "*Start writing your exam paper…*" — the same defect flagged in every prior report.

---

## Summary of action items (priority order)

1. **Fix the OR/either-choice rendering for the Reference-to-Context question type (Q6, Q7)** — currently prints both extract alternatives in full (and drops sub-questions for one of them in Q6) instead of the "Extract A [sub-Qs] OR Extract B [sub-Qs]" format that works correctly elsewhere in the same paper (Q4, Q5).
2. **Filter Q8's source content to the prescribed syllabus** — "Song of Myself" (Walt Whitman) is off-syllabus entirely and currently anchors a 12-mark question, the largest in the paper.
3. **Fix book-to-slot routing for Q9, Q10, Q11** — Q9 (should be FOOTPRINTS-only) is 100% FIRST FLIGHT content; Q10 and Q11 each pair one correctly-sourced option with one from the wrong book. Same class of bug as the subject-routing issue in Science/Social Science, here scoped to "which of the two prescribed books" instead of "which subject."
4. **Raise the discursive passage (Q1) to its required 400–450 word length** — currently 246 words, roughly 40% short, while the case-based passage (Q2) already correctly hits its target.
5. Fix the marks-column glyph rendering bug and the missing header/placeholder-text export bug — now confirmed across all four subjects tested; a single fix should resolve both everywhere.
