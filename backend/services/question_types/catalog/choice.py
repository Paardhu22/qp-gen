"""Family A — objective, choice based. The student picks from printed options.

Shared rules (every entry): options labelled (a)–(d); exactly one correct unless
stated; distractors plausible and similar in length; never "all of the above"
for Classes 1–8.
"""

from __future__ import annotations

from services.question_types.catalog._build import (
    ASSERTION_REASON_DIRECTIONS,
    FOUR,
    family_builder,
)
from services.question_types.spec import OptionRule

_ = family_builder("OBJECTIVE_CHOICE")

_SHARED = (
    "Label options (a)–(d). Distractors must be plausible and similar in length; "
    "never use 'all of the above' for Classes 1–8."
)

ENTRIES = [
    _("MCQ_SINGLE", "MCQ — Standard", "A1", "LIVE", "MCQ",
      "Direct recall or single-step understanding.", 1, (3, 10), "MCQ_4", "RECALL",
      options=FOUR, aliases=("MCQ STANDARD", "STANDARD MCQ"),
      brief=f"One question line and four options, exactly one correct. {_SHARED}",
      example="The SI unit of electric current is\n(a) volt  (b) ampere  (c) ohm  (d) watt",
      answer="(b) ampere"),
    _("MCQ_PICTURE", "MCQ — Picture Based", "A2", "NEW", "MCQ",
      "Visual recognition and identification.", 1, (1, 10), "MCQ_4", "IDENTIFY",
      stimulus="IMAGE", options=FOUR, aliases=("PICTURE MCQ", "IMAGE BASED MCQ"),
      notes="Backbone of Classes 1–5 assessment."),
    _("MCQ_MATCH", "MCQ — Matching", "A3", "NEW", "MCQ",
      "Association across two sets.", 1, (4, 10), "MCQ_4", "IDENTIFY",
      options=FOUR, aliases=("MATCHING MCQ",),
      brief=("Print two short columns — Column A items (i), (ii), (iii) and Column B items "
             "(1), (2), (3) — then four options, each a full pairing sequence such as "
             "'i-2, ii-3, iii-1'. Exactly one sequence is correct."),
      example=("Match Column A with Column B.\nColumn A: (i) Heart (ii) Lungs (iii) Kidney\n"
               "Column B: (1) Filters blood (2) Pumps blood (3) Exchanges gases\n"
               "(a) i-1, ii-2, iii-3  (b) i-2, ii-3, iii-1  (c) i-3, ii-1, iii-2  (d) i-2, ii-1, iii-3"),
      answer="(b) i-2, ii-3, iii-1",
      notes="Different from MATCH_FOLLOWING, where the student draws lines and no options are printed."),
    _("MCQ_FILL", "MCQ — Fill Up", "A4", "NEW", "MCQ",
      "Recall in sentence context, with recognition support.", 1, (2, 10), "MCQ_4", "RECALL",
      options=FOUR, aliases=("FILL UP MCQ", "MCQ FILL IN THE BLANK"),
      brief=f"A sentence with exactly one blank written as ________, then four options that could fill it. {_SHARED}",
      example=("The process by which plants make their food is called ________.\n"
               "(a) respiration  (b) transpiration  (c) photosynthesis  (d) germination"),
      answer="(c) photosynthesis"),
    _("MCQ_STATEMENT_EVAL", "MCQ — Statement Analysis", "A5", "DB", "MCQ",
      "Evaluating several claims at once.", 1, (8, 10), "MCQ_4", "JUSTIFY",
      options=FOUR, aliases=("STATEMENT_EVAL", "STATEMENT TYPE", "STATEMENT ANALYSIS"),
      brief=("Two or three statements numbered I, II, III, then 'Which of the statements given "
             "above are correct?' with four options naming combinations (e.g. 'I and III only')."),
      example=("Consider the following statements about the Indian Constitution.\n"
               "I. It came into effect on 26 January 1950.\nII. It is the shortest written constitution in the world.\n"
               "III. It establishes India as a sovereign socialist secular democratic republic.\n"
               "Which of the statements given above are correct?\n"
               "(a) I and II only  (b) I and III only  (c) II and III only  (d) I, II and III"),
      answer="(b) I and III only"),
    _("MCQ_CORRECT", "MCQ — Correct Statement", "A6", "NEW", "MCQ",
      "Discriminating true from false claims.", 1, (6, 10), "MCQ_4", "IDENTIFY",
      options=FOUR, aliases=("CORRECT STATEMENT", "WHICH IS CORRECT"),
      brief="Ask 'Which of the following statements is correct?' with four independent statements as options; exactly one is true.",
      example=("Which of the following statements is correct?\n(a) Sound travels faster in air than in water.\n"
               "(b) Sound cannot travel through a vacuum.\n(c) Sound is a transverse wave in air.\n"
               "(d) Sound travels at the same speed in all media."),
      answer="(b) Sound cannot travel through a vacuum."),
    _("MCQ_INCORRECT", "MCQ — Incorrect Statement", "A7", "NEW", "MCQ",
      "Discriminating true from false claims, inverted.", 1, (6, 10), "MCQ_4", "IDENTIFY",
      options=FOUR, aliases=("INCORRECT STATEMENT", "WHICH IS NOT", "NOT TRUE"),
      brief=("Four statements as options: three true, one false. The negative word in the stem "
             "MUST be written in capitals (NOT, INCORRECT, EXCEPT) so students cannot misread it."),
      example=("Which of the following is NOT a characteristic of metals?\n(a) They are good conductors of heat.\n"
               "(b) They are malleable and ductile.\n(c) They are brittle and break easily.\n(d) They have a shiny lustre."),
      answer="(c) They are brittle and break easily."),
    _("MCQ_IDENTIFY", "MCQ — Identify", "A8", "NEW", "MCQ",
      "Naming a thing from its properties.", 1, (3, 10), "MCQ_4", "IDENTIFY",
      options=FOUR, aliases=("WHO AM I", "IDENTIFY MCQ"),
      brief="A description or set of clues (a 'Who am I?' riddle works well for Classes 3–6), then four candidate names.",
      example=("I am a gas. I make up about 78% of the air around you. Plants cannot take me directly "
               "from the air. Who am I?\n(a) Oxygen  (b) Nitrogen  (c) Carbon dioxide  (d) Hydrogen"),
      answer="(b) Nitrogen"),
    _("MCQ_ODD_ONE_OUT", "MCQ — Odd One Out", "A9", "DB", "MCQ",
      "Classification — finding the shared property.", 1, (1, 10), "MCQ_4", "CLASSIFY",
      options=FOUR, aliases=("ODD_ONE_OUT", "ODD ONE OUT"),
      brief=("Four items from one category as options; exactly one does not belong. The answer "
             "MUST state the classifying rule, or the item is ambiguous and unmarkable."),
      example="Choose the odd one out.\n(a) Mango  (b) Banana  (c) Potato  (d) Apple",
      answer="(c) Potato — it is a vegetable (a stem tuber); the others are fruits."),
    _("MCQ_DATA", "MCQ — Data Interpretation", "A10", "DB", "MCQ",
      "Reading a table.", 1, (5, 10), "MCQ_4", "INTERPRET",
      stimulus="TABLE", options=FOUR, aliases=("DATA MCQ", "TABLE BASED MCQ"),
      brief=("Print a small data table (a header row plus 3–6 rows), then one MCQ answerable "
             "only by reading it. The table is part of the question."),
      example=("Study the table and answer the question.\n| City | Rainfall (cm) |\n| Chennai | 140 |\n"
               "| Mumbai | 242 |\n| Delhi | 79 |\n| Kolkata | 160 |\nWhich city received the least rainfall?\n"
               "(a) Chennai  (b) Mumbai  (c) Delhi  (d) Kolkata"),
      answer="(c) Delhi",
      notes="Core competency-based format in the current CBSE pattern."),
    _("ASSERTION_REASON", "Assertion & Reason", "A11", "LIVE", "ASSERTION_REASON",
      "Logical relationship between a claim and its explanation.", 1, (8, 10), "MCQ_4", "JUSTIFY",
      options=OptionRule(4, 4, fixed=ASSERTION_REASON_DIRECTIONS),
      aliases=("ASSERTION REASON", "A AND R"),
      brief=("State only the Assertion (A) and the Reason (R). The four standard CBSE directions "
             "are added automatically — never restate or paraphrase them."),
      example=("Assertion (A): Water is a compound.\nReason (R): Water can be broken down into hydrogen "
               "and oxygen by electrolysis."),
      answer="(a)",
      notes="Introduced at Class 8; prohibited below that. The four-option form is used throughout."),
    _("MCQ_MULTI", "MCQ — Multiple Correct", "A12", "DB", "MCQ",
      "Complete knowledge of a set, not just one member.", 2, (6, 10), "MCQ_MULTI", "IDENTIFY",
      marks_range=(2, 4), options=OptionRule(4, 5, multi_correct=True),
      aliases=("MULTIPLE CORRECT", "SELECT ALL THAT APPLY", "MULTI CORRECT"),
      brief=("Four or five options, two or more correct. The stem MUST end with '(Select all that "
             "apply.)'. The answer lists every correct option letter. Marking is all-or-nothing: "
             "full marks only when every correct option and no wrong one is chosen."),
      example=("Which of the following are renewable sources of energy? (Select all that apply.)\n"
               "(a) Solar energy  (b) Coal  (c) Wind energy  (d) Natural gas  (e) Biomass"),
      answer="(a), (c), (e) — all-or-nothing"),
    _("MATRIX_MATCH", "Matrix Match", "A13", "NEW", "MCQ",
      "Many-to-many association.", 4, (8, 10), "MCQ_4", "IDENTIFY",
      marks_range=(4, 8), options=FOUR, aliases=("MATRIX MATCH",),
      brief=("Column I entries (P), (Q), (R), (S) against Column II entries (1)–(4); an entry may "
             "match one or more. Then four options each giving a complete matching such as "
             "'P-2, Q-3, R-4, S-1'. Exactly one option is correct."),
      example=("Match the entries in Column I with those in Column II.\nColumn I: (P) Chlorophyll (Q) Stomata "
               "(R) Xylem (S) Root hair\nColumn II: (1) Found in root cells (2) Green pigment (3) Gas exchange "
               "in leaves (4) Transports water upward\n(a) P-2, Q-3, R-4, S-1  (b) P-3, Q-2, R-1, S-4  "
               "(c) P-2, Q-4, R-3, S-1  (d) P-1, Q-3, R-4, S-2"),
      answer="(a) P-2, Q-3, R-4, S-1"),
    _("MCQ_SEQUENCE", "MCQ — Sequencing", "A14", "DB", "MCQ",
      "Correct order of a process or events.", 1, (3, 10), "MCQ_4", "SEQUENCE",
      options=FOUR, aliases=("SEQUENCING", "SEQUENCE MCQ", "ARRANGE IN ORDER MCQ"),
      brief="Four shuffled steps labelled I–IV, then four options giving orderings such as 'II → IV → I → III'.",
      example=("Arrange the stages of the life cycle of a butterfly in the correct order.\nI. Pupa  II. Egg  "
               "III. Adult butterfly  IV. Larva\n(a) II → IV → I → III  (b) II → I → IV → III  "
               "(c) I → II → III → IV  (d) IV → II → I → III"),
      answer="(a) II → IV → I → III"),
    _("MCQ_NUMERICAL", "MCQ — Numerical", "A15", "NEW", "MCQ",
      "Calculation, with options as a check.", 1, (4, 10), "MCQ_4", "APPLY",
      options=FOUR, aliases=("NUMERICAL MCQ",),
      brief=("A problem, then four numerical options. Every distractor must be the result of a "
             "common error (adding instead of multiplying, area instead of perimeter), never a random number."),
      example=("A rectangular field is 24 m long and 15 m wide. What is its perimeter?\n"
               "(a) 39 m  (b) 78 m  (c) 360 m  (d) 156 m"),
      answer="(b) 78 m"),
    _("MCQ_CASE", "MCQ — Case / Passage Based", "A16", "NEW", "CASE_STUDY",
      "Applying a concept to a described situation.", 4, (6, 10), "MCQ_4", "INTERPRET",
      marks_range=(3, 5), stimulus="SCENARIO", container="SUB_PARTS", options=FOUR,
      aliases=("CASE BASED MCQ", "PASSAGE BASED MCQ"),
      brief=("A short scenario paragraph, then a set of 1-mark MCQs drawn only from it, each with "
             "four options. The part marks sum to the question's marks."),
      example=("Ravi noticed that the iron gate of his house had developed a reddish-brown layer during the "
               "monsoon.\n(i) The reddish-brown layer on the gate is (a) rust (b) soot (c) mould (d) dust\n"
               "(ii) The two substances necessary for this change are (a) oxygen and nitrogen "
               "(b) water and oxygen (c) carbon dioxide and water (d) nitrogen and water"),
      answer="(i) (a) rust · (ii) (b) water and oxygen"),
    _("MCQ_ANALOGY", "MCQ — Analogy", "A17", "NEW", "MCQ",
      "Relational reasoning.", 1, (4, 10), "MCQ_4", "COMPARE",
      options=FOUR, aliases=("ANALOGY",),
      brief="An analogy of the form 'A : B :: C : ?' with four options for the missing term.",
      example="Complete the analogy.\nDoctor : Hospital :: Teacher : ?\n(a) Book  (b) School  (c) Student  (d) Chalk",
      answer="(b) School"),
    _("MCQ_CAUSE_EFFECT", "MCQ — Cause and Effect", "A18", "NEW", "MCQ",
      "Causal reasoning.", 1, (6, 10), "MCQ_4", "JUSTIFY",
      options=FOUR, aliases=("CAUSE AND EFFECT",),
      brief="An event, then four candidate causes or consequences; the student picks the one that follows most directly.",
      example=("Deforestation in hilly regions most directly leads to\n(a) an increase in rainfall  "
               "(b) soil erosion and landslides  (c) a fall in average temperature  (d) an increase in groundwater level"),
      answer="(b) soil erosion and landslides"),
    _("MCQ_CHRONOLOGY", "MCQ — Chronology", "A19", "NEW", "MCQ",
      "Historical ordering.", 1, (6, 10), "MCQ_4", "SEQUENCE",
      options=FOUR, aliases=("CHRONOLOGY", "CHRONOLOGICAL ORDER"),
      subjects=("social science",),
      brief="Four historical events labelled I–IV, unordered; four options giving chronological sequences.",
      example=("Arrange the following events in chronological order.\nI. Jallianwala Bagh massacre  "
               "II. Non-Cooperation Movement  III. Quit India Movement  IV. Dandi March\n"
               "(a) I → II → IV → III  (b) II → I → III → IV  (c) I → III → II → IV  (d) IV → I → II → III"),
      answer="(a) I → II → IV → III"),
    _("MCQ_DIAGRAM_LABEL", "MCQ — Diagram Label", "A20", "NEW", "MCQ",
      "Reading a labelled figure.", 1, (4, 10), "MCQ_4", "INTERPRET",
      stimulus="IMAGE", options=FOUR, aliases=("DIAGRAM BASED MCQ",)),
    _("MCQ_TF_COMBO", "MCQ — True/False Combination", "A21", "NEW", "MCQ",
      "Several judgements in one item.", 1, (6, 10), "MCQ_4", "JUSTIFY",
      options=FOUR, aliases=("TRUE FALSE COMBINATION",),
      brief="Three or four statements labelled I–III, then four options giving True/False patterns for them.",
      example=("Read the statements and choose the correct combination.\nI. All squares are rectangles.\n"
               "II. All rectangles are squares.\nIII. All squares are rhombuses.\n"
               "(a) I-True, II-True, III-False  (b) I-True, II-False, III-True  "
               "(c) I-False, II-True, III-True  (d) I-True, II-False, III-False"),
      answer="(b)"),
    _("MCQ_MAP", "MCQ — Map Based", "A22", "NEW", "MCQ",
      "Map reading without drawing.", 1, (5, 10), "MCQ_4", "INTERPRET",
      stimulus="MAP", options=FOUR, aliases=("MAP BASED MCQ",),
      notes="Every map item in a CBSE paper needs a text substitute for visually impaired candidates."),
    _("MCQ_SERIES", "MCQ — Complete the Series", "A23", "NEW", "MCQ",
      "Pattern recognition.", 1, (1, 8), "MCQ_4", "SEQUENCE",
      options=FOUR, aliases=("COMPLETE THE SERIES", "WHAT COMES NEXT"),
      brief="A number, letter or shape-character series with one missing term, and four options. The answer MUST state the rule.",
      example="What comes next in the series?\n2, 6, 12, 20, 30, ____\n(a) 36  (b) 40  (c) 42  (d) 44",
      answer="(c) 42 — the differences increase by 2 each time."),
]
