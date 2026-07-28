# Class 10 Social Science — Generated Paper vs CBSE SQP (2025-26)

**Compared:** `qpgen-social.pdf` (our tool's output) vs `sqp-social.pdf` (official CBSE Class X Social Science Sample Question Paper, Code 087, 2025-26)
**Date:** 2026-07-28

Overall verdict: same root problem as the Class 10 Science comparison — the mark-scheme skeleton per section is close to correct, but **section headers (History/Geography/Political Science/Economics) don't match the actual subject of the questions inside them**. On top of that, the generated paper is missing an entire mandated question category (map-based questions) and drops two of CBSE's characteristic question formats (column-matching MCQs, cited-source case questions).

---

## 1. Blueprint comparison

| | CBSE SQP | Our Generated Paper |
|---|---|---|
| Total questions | 38 | 36 ❌ (2 short) |
| Total marks | 80 | 75 ❌ (5 short) |
| Section A — History | 9 Q / 20 M | 8 Q / 18 M ❌ |
| Section B — Geography | 10 Q / 20 M | 9 Q / 17 M ❌ |
| Section C — Political Science | 9 Q / 20 M | 9 Q / 20 M ✅ |
| Section D — Economics | 10 Q / 20 M | 10 Q / 20 M ✅ |
| Map-based questions | 2 (Q9 = 2M History, Q19 = 3M Geography) | 0 ❌ |

The 2-question / 5-mark shortfall is fully explained by one thing: **the generated paper has no map-based questions at all.** CBSE's own general instructions (#8) require a dedicated 2-mark map question in the History section and a 3-mark map question in the Geography section. Both are simply absent — Section A is short exactly 1 question / 2 marks, Section B is short exactly 1 question / 3 marks, matching the missing map items precisely. Political Science and Economics (which don't require map questions) hit their 9Q/20M and 10Q/20M targets exactly.

**Fix needed:** map-skill questions need to be a required, non-optional slot in the paper-building logic for History and Geography sections specifically — right now they seem to be dropped entirely, likely because they depend on an actual outline-map asset the generator isn't producing or attaching.

---

## 2. Critical issue — Section headers don't match section content

Exactly the same defect found in the Science comparison: questions are not being routed to the section matching their actual subject/chapter.

**"Section A – History" contains mostly non-History questions:**
- Q1 — water pollution from industrial discharge (Geography/Environment)
- Q2 — best approach to managing social conflict in a democracy (Political Science)
- Q4 — exploring the local impact of globalisation on farmers (Economics)
- Q5 (OR option) — Sri Lanka ethnic conflict / dictatorship vs. democracy growth data (Political Science / Economics)
- Q6 — linguistic states & federalism, OR the RTI Act (both Political Science)
- Q8 — a 4-mark case-based question about credit and loan repayment, Salim & Swapna (Economics)

Only Q3 (silk routes) and half of Q7 (Salt March option) are genuinely History content. That's roughly 1.5 out of 8 questions actually belonging to the section they're filed under.

**"Section B – Geography" mixes in Political Science and Economics:**
- Q10 — functions NOT performed by political parties (Political Science)
- Q13 — how MNCs reduce production costs (Economics)
- Q14 — which is NOT a key feature of federalism (Political Science)
- Q15 — liberalisation of imports under WTO and its effect on a capacitor manufacturer (Economics)
- Q16 (OR option) — print culture and nationalism in India (History) — correct Geography alternate is fine, but the paired choice is History, not Geography

**"Section C – Political Science" is almost entirely History and Economics content:**
- Q18 — where Consumer Rights chapter case histories were collected from (Economics)
- Q19 — definition/focus of globalisation (Economics)
- Q20 — why Gandhi chose salt as a symbol in the Civil Disobedience Movement (History)
- Q21 — AR question about unorganised-sector workers (Economics)
- Q23 — why factories replaced village-household production during industrialisation (History)
- Q24 — bamboo drip irrigation in Meghalaya (Geography)
- Q25 (OR option) — proto-industrialisation in Britain (History)
- Q26 — a full 4-mark case question on the 1848 Frankfurt Parliament and German unification (History, not Political Science at all)

Only Q22 (areas where democracy's outcomes are examined) and the "democracy is accountable/responsive" half of Q25 are genuine Political Science content.

**"Section D – Economics" pulls in History, Geography, and Political Science:**
- Q27 — effects of the abolition of the Corn Laws in Britain (History)
- Q31 — which mineral forms by decomposition of rocks (Geography)
- Q32 — which allegorical figure represented the German nation in 1848 (History)
- Q35 — advantages and challenges of power sharing in a democracy (Political Science)
- Q36 (OR option) — community forest/wildlife conservation, or rainwater harvesting in Rajasthan (both Geography, not Economics)

Only Q28, 29, 30, 33, 34 (demand deposits, transport tech and trade, secondary sector classification, consumer movement, tourism as trade) are genuine Economics content.

**Net effect, same as the Science paper:** a teacher opening "Section C – Political Science" would find it's mostly a History and Economics quiz, and "Section D – Economics" is a grab-bag of all four subjects. This confirms the subject-routing bug identified in the Science report is not subject-specific — it's a general defect in how the generator assigns questions to sections, and it needs to be fixed once at the source rather than per-subject.

---

## 3. Internal choice ("OR") pairs mix unrelated subjects

Same issue as Science: real CBSE internal choices are always two versions of the *same* topic. Several OR pairs here splice unrelated subjects:

- Q5: Sri Lanka's Sinhala-majority policies (Political Science) **OR** dictatorship vs. democracy economic growth data (Economics)
- Q16: print culture and Indian nationalism (History) **OR** resource planning in India (Geography)
- Q25: democracy's accountability (Political Science) **OR** proto-industrialisation in Britain (History)
- Q36: community forest conservation **OR** rainwater harvesting in Rajasthan — these two are at least both Geography, so this pair is fine; flagged only because it sits under the "Economics" header

The generator's OR-pairing logic needs a same-subject (ideally same-chapter) constraint, same recommendation as the Science report.

---

## 4. Missing question formats

- **Map-based questions are entirely absent** (see §1) — this is the single biggest structural gap, since CBSE treats this as a mandatory, explicitly-weighted category (2M in History + 3M in Geography), not an optional style choice.
- **No column-matching / classification-table MCQs.** The SQP uses this format three times — Q1 (match artist/statue-of-liberty symbolism to descriptions), Q11 (fill in a soil-classification table), Q34 (match globalisation effects to outcomes). The generated paper has zero questions in this format; all MCQs are plain four-option recall/analysis questions.
- **No cited primary-source excerpts.** SQP case-based questions are built on real, cited material — a 19th-century newspaper excerpt with a publication date (Q8), a World Bank pollution report with a source link (Q18), an adapted NCERT passage on Sri Lanka/Belgium (Q28). The generated case questions (Q8 credit case, Q17 rat-hole mining, Q26 Frankfurt Parliament) are invented scenarios with no citation or source excerpt — reasonable in structure (short scenario + 3 sub-questions) but missing the "read and interpret an authentic source" skill the SQP is testing.
- **No visual sources at all** — no leader portraits, political cartoons, or maps (SQP uses a portrait for Q2, a political cartoon for Q21, and a full India outline map for Q9/Q19).
- **"For Visually Impaired candidates" alternates are entirely absent.** SQP provides these for every visually-dependent question (Q2, Q9, Q19, Q21 — 4 instances). None appear in the generated paper.
- **No visible header / general-instructions block**, and page 1 shows leftover editor placeholder text ("*Start writing your exam paper…*") — identical issue to the one flagged in the Science report, confirming this is a systemic export bug rather than a one-off.

---

## 5. Question standard / difficulty

This is one area where the generated Social Science paper does noticeably better than the generated Science paper. Several MCQs genuinely mirror CBSE's applied/analytical style rather than pure recall:

- Q10 ("which of these is NOT a function of political parties"), Q13 ("how do MNCs reduce production costs"), Q29 ("which technological advancement most directly reduced transport costs") — these are comparable in style to SQP's own "which of the following best explains/demonstrates" analytical MCQs (e.g. SQP Q12 tiger-poaching consequence, Q15 Krishi Sinchaee Yojana evaluation).
- The case-based questions (Q8, Q17, Q26) use the correct multi-part (i)/(ii)/(iii) scenario structure the SQP uses, even without a cited source.

Where it still falls short: no column-matching MCQs (a recurring CBSE format, see §4), and the case questions lack real-world sourcing/citation, which is part of what CBSE is testing (reading comprehension of an authentic document, not just a generic scenario).

---

## 6. What's actually working well

- Section-level mark totals for Political Science and Economics are an exact match (9Q/20M and 10Q/20M).
- The overall question-type mix (MCQ, VSA, SA, LA, CBQ) within each section is proportionally close to CBSE's pattern once the missing map questions are accounted for.
- Assertion-Reason format and count (1 instance, same as SQP) is correctly reproduced, including a properly "false reason" distractor design.
- Case-based question sub-part structure (short scenario + 3 graduated sub-questions) is present and matches CBSE's style reasonably well.
- MCQ difficulty/style for Political Science and Economics content leans appropriately analytical, closer to CBSE's standard than the Science paper's MCQs were.

---

## Summary of action items (priority order)

1. **Fix subject→section routing** (same root cause as the Science report) so History/Geography/Political Science/Economics questions land in the section matching their actual chapter/subject.
2. **Add map-based questions as a required slot** for History (2M) and Geography (3M) sections — currently dropped entirely, likely because there's no map asset being generated/attached.
3. **Constrain internal-choice (OR) pairing to same subject/chapter.**
4. **Add column-matching / classification-table MCQs** as a supported question format — currently 100% of MCQs are plain four-option questions, while CBSE uses matching-table MCQs multiple times per paper.
5. Investigate the missing header/general-instructions block and leftover "Start writing your exam paper…" placeholder text — same bug as flagged in the Science report, now confirmed across two subjects.
6. Consider whether cited-source case questions (with a real or realistic source attribution) and visual-source questions (portraits, cartoons, maps) are in scope; if so, they're currently missing entirely, along with the visually-impaired-candidate alternates tied to them.
