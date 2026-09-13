"""Family B — objective, supply based. No options printed; a short exact answer.

Shared rules: the answer is one word to one line; the answer space is sized to
the expected answer; no partial marks.
"""

from __future__ import annotations

from services.question_types.catalog._build import family_builder
from services.question_types.spec import OptionRule

_ = family_builder("OBJECTIVE_SUPPLY")

ENTRIES = [
    _("FILL_BLANK", "Fill in the Blank", "B1", "LIVE", "FILL_IN_THE_BLANK",
      "Precise recall in context.", 1, (1, 10), "SHORT_TEXT", "RECALL",
      aliases=("FILL IN THE BLANKS", "FILL UPS", "FILL_IN_BLANK"),
      brief=("One sentence with exactly one blank written as ________ — never two blanks, or "
             "marking becomes ambiguous. The answer lists accepted spellings and plural forms."),
      example="The powerhouse of the cell is the ________.",
      answer="mitochondrion (accept: mitochondria)"),
    _("FILL_BLANK_BANK", "Fill in the Blanks — Word Bank", "B2", "NEW", "FILL_IN_THE_BLANK",
      "Recall with recognition support.", 3, (1, 8), "SHORT_TEXT", "RECALL",
      marks_range=(2, 10), stimulus="WORD_BANK", container="SUB_PARTS",
      aliases=("WORD BANK", "FILL IN THE BLANKS USING THE WORDS GIVEN", "WORD BOX"),
      brief=("A box of words printed above, then numbered sentences each with one blank, 1 mark "
             "each. The box holds at least one extra word so the last blank is not free."),
      example=("Fill in the blanks using the words given in the box.\n[gills, lungs, scales, feathers, fins]\n"
               "(i) Fish breathe through ________.\n(ii) Birds have ________ on their body.\n"
               "(iii) Humans breathe using their ________."),
      answer="(i) gills (ii) feathers (iii) lungs",
      notes="The default worksheet format for Classes 1–5."),
    _("TRUE_FALSE", "True or False", "B3", "LIVE", "TRUE_FALSE",
      "Judging a single claim.", 1, (1, 10), "SHORT_TEXT", "IDENTIFY",
      options=OptionRule(2, 2, fixed=("True", "False")),
      aliases=("TRUE OR FALSE", "T/F", "TRUE_OR_FALSE"),
      brief=("One statement that is unambiguously true or false. Never use 'usually', 'mostly' "
             "or 'sometimes'."),
      example="State whether True or False: The Sun rises in the west.",
      answer="False"),
    _("TRUE_FALSE_CORRECT", "True or False — Correct the False", "B4", "NEW", "SHORT_ANSWER",
      "Judgement plus correction.", 2, (4, 10), "SHORT_TEXT", "CORRECT",
      marking="SCHEME", aliases=("TRUE FALSE CORRECT", "STATE TRUE OR FALSE AND CORRECT"),
      brief=("A statement the student marks True or False and, if false, rewrites correctly. "
             "1 mark for the judgement, 1 for the correction. The answer gives both parts."),
      example="State True or False. Rewrite the statement correctly if it is false.\nMercury is the largest planet in the solar system.",
      answer="False — Jupiter is the largest planet in the solar system."),
    _("ONE_WORD", "One Word Answer", "B5", "LIVE", "ONE_WORD",
      "Exact term recall.", 1, (2, 10), "SHORT_TEXT", "RECALL",
      aliases=("ONE WORD", "ANSWER IN ONE WORD"),
      brief="A definition or clue whose answer is exactly one word or term.",
      example="Answer in one word: The process by which a liquid changes into vapour on heating.",
      answer="Evaporation"),
    _("MATCH_FOLLOWING", "Match the Following", "B6", "LIVE", "MATCH_THE_FOLLOWING",
      "Association, without option support.", 4, (1, 10), "MATCH", "IDENTIFY",
      marks_range=(2, 8), aliases=("MATCH THE FOLLOWING", "MATCH THE COLUMNS"),
      brief=("Two columns; Column A items (i), (ii)… and Column B items (a), (b)… with ONE extra "
             "entry in Column B so the last pair is not free. Marks equal the number of pairs."),
      example=("Match the following.\nColumn A: (i) Cow (ii) Hen (iii) Goat (iv) Dog\n"
               "Column B: (a) Kid (b) Calf (c) Puppy (d) Chick (e) Cub"),
      answer="(i) b (ii) d (iii) a (iv) c"),
    _("NAME_FOLLOWING", "Name the Following", "B7", "NEW", "ONE_WORD",
      "Term recall from definitions, several at once.", 3, (3, 10), "SHORT_TEXT", "RECALL",
      marks_range=(2, 6), container="SUB_PARTS", aliases=("NAME THE FOLLOWING",),
      brief="Several one-line definitions numbered (i), (ii), (iii) under one instruction, 1 mark each; each answer is a single term.",
      example=("Name the following.\n(i) The gas released by plants during photosynthesis.\n"
               "(ii) The largest organ of the human body.\n(iii) The instrument used to measure temperature."),
      answer="(i) Oxygen (ii) Skin (iii) Thermometer"),
    _("NUMERIC_ENTRY", "Numeric Entry", "B8", "DB", "NUMERICAL",
      "Calculation with an exact numeric answer, no options.", 1, (3, 10), "NUMERIC", "APPLY",
      marks_range=(1, 2), aliases=("NUMERIC ANSWER", "NUMERIC_ENTRY"),
      brief="A short calculation with a single exact numeric answer and no options. The answer records the unit and any tolerance.",
      example="A shopkeeper sold 145 pens on Monday and 278 pens on Tuesday. How many pens did he sell in all?",
      answer="423"),
    _("CLASSIFY_SORT", "Classify / Sort", "B9", "DB", "SHORT_ANSWER",
      "Categorisation into given groups.", 2, (1, 8), "SHORT_TEXT", "CLASSIFY",
      marks_range=(1, 4), aliases=("CLASSIFY", "SORT INTO GROUPS", "CLASSIFY THE FOLLOWING"),
      brief="A list of 4–8 items and two or three named groups; the student writes each item under its group.",
      example="Classify the following into Living and Non-living things.\ncar, dog, tree, stone, bird, chair",
      answer="Living — dog, tree, bird · Non-living — car, stone, chair"),
    _("SEQUENCE_WRITE", "Arrange in Order", "B10", "NEW", "SHORT_ANSWER",
      "Ordering, supply version.", 2, (1, 10), "ORDER", "SEQUENCE",
      marks_range=(1, 2), aliases=("ARRANGE IN ORDER", "ARRANGE IN SEQUENCE", "ASCENDING ORDER"),
      brief=("Four to six shuffled steps, events or numbers; the student writes the correct order "
             "(1, 2, 3… in boxes, or ascending/chronological order)."),
      example=("Arrange the following in the correct order of a seed becoming a plant. Write 1, 2, 3, 4.\n"
               "[ ] Seedling appears above the soil\n[ ] Seed is sown in the soil\n[ ] Roots grow downward\n[ ] Plant bears leaves"),
      answer="2, 1, 3, 4"),
    _("ODD_ONE_OUT_JUSTIFY", "Odd One Out — with Reason", "B11", "NEW", "SHORT_ANSWER",
      "Classification plus articulating the rule.", 2, (3, 10), "SHORT_TEXT", "CLASSIFY",
      marking="SCHEME", auto_markable=False, aliases=("ODD ONE OUT WITH REASON",),
      brief="Four items; the student names the odd one and gives the reason. 1 mark for the item, 1 for the reason.",
      example="Find the odd one out and give a reason.\nIron, Copper, Aluminium, Sulphur",
      answer="Sulphur — the others are metals; sulphur is a non-metal."),
    _("FULL_FORM", "Full Form / Abbreviation", "B12", "NEW", "ONE_WORD",
      "Terminology recall.", 1, (4, 10), "SHORT_TEXT", "RECALL",
      aliases=("FULL FORM", "ABBREVIATION", "EXPAND THE ABBREVIATION"),
      brief="An abbreviation whose full form the student writes.",
      example="Write the full form of: ISRO",
      answer="Indian Space Research Organisation"),
    _("UNIT_SYMBOL", "SI Unit / Symbol", "B13", "NEW", "ONE_WORD",
      "Unit and symbol recall.", 1, (6, 10), "SHORT_TEXT", "RECALL",
      subjects=("science", "mathematics"), aliases=("SI UNIT", "UNIT AND SYMBOL"),
      brief="A physical quantity; the student writes its SI unit and symbol.",
      example="Write the SI unit and its symbol for: Force",
      answer="newton, N"),
    _("TICK_CROSS", "Tick (✓) or Cross (✗)", "B14", "NEW", "ONE_WORD",
      "Simple judgement with a non-verbal response.", 3, (1, 3), "MARK", "IDENTIFY",
      marks_range=(1, 5), container="SUB_PARTS", also_in=("I20",),
      aliases=("TICK OR CROSS", "GOOD HABIT BAD HABIT", "PUT A TICK"),
      brief=("Short statements numbered (i), (ii), (iii), each followed by an empty box [   ]; the "
             "student puts ✓ or ✗. 1 mark each. For children who cannot yet write fluently."),
      example=("Put a ✓ for good habits and a ✗ for bad habits.\n(i) Brushing your teeth twice a day. [   ]\n"
               "(ii) Throwing waste on the road. [   ]\n(iii) Washing hands before eating. [   ]"),
      answer="(i) ✓ (ii) ✗ (iii) ✓"),
]
