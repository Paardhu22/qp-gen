"""Family I — primary and worksheet activity (Classes 1–5).

Children in Classes 1–3 often cannot yet write fluently, so the response is a
mark — a circle, a tick, a line, a colour — rather than a sentence. Most of
this family needs something printed on the page (a picture, a dotted outline,
a grid of dots), and those entries carry `stimulus="IMAGE"` so the picker
shows them disabled rather than offering slots that can only come back empty.

Three items are catalogued elsewhere and not repeated: I2 is `CIRCLE_PICTURE`
(E15), I14 is `JOIN_DOTS` (E13) and I20 is `TICK_CROSS` (B14).
"""

from __future__ import annotations

from services.question_types.catalog._build import family_builder

_ = family_builder("PRIMARY_ACTIVITY")

_MATHS = ("mathematics",)
_LANGUAGES = ("english", "hindi", "telugu", "sanskrit")

ENTRIES = [
    _("CIRCLE_CORRECT", "Circle the Correct Answer", "I1", "NEW", "ONE_WORD",
      "Recognition with a non-verbal response.", 1, (1, 4), "MARK", "IDENTIFY",
      aliases=("CIRCLE THE CORRECT ANSWER", "CIRCLE THE CORRECT WORD"),
      brief=("One short sentence with two or three choices written inline in brackets and "
             "separated by slashes, e.g. '( kitten / puppy / calf )'. Exactly one choice is "
             "correct. Do not use an options list."),
      example="Circle the correct word.\nA baby dog is called a ( kitten / puppy / calf ).",
      answer="puppy"),
    _("COLOUR_INSTRUCTION", "Colour as Instructed", "I3", "NEW", "DIAGRAM",
      "Classification through colouring.", 1, (1, 3), "MARK", "CLASSIFY",
      marks_range=(1, 2), stimulus="IMAGE", aliases=("COLOUR THE PICTURES",)),
    _("TRACE_WRITE", "Trace and Write", "I4", "NEW", "DIAGRAM",
      "Letter and numeral formation.", 1, (1, 2), "DRAW", "CREATE",
      marks_range=(1, 2), stimulus="IMAGE", aliases=("TRACE AND WRITE",),
      notes="Needs dotted-outline letters or numerals."),
    _("JOIN_LINES", "Join with a Line", "I5", "NEW", "SHORT_ANSWER",
      "Association with a non-verbal response.", 3, (1, 5), "MATCH", "IDENTIFY",
      marks_range=(2, 5), stimulus="TABLE",
      aliases=("JOIN WITH A LINE", "JOIN THE FOLLOWING", "DRAW LINES TO MATCH"),
      brief=("A two-column table: things on the left, their matches on the right in shuffled "
             "order, with a dot • after each left item and before each right item. The student "
             "draws lines. 1 mark per pair."),
      example="Join the animal to its home.\n| Cow • | • Nest |\n| Bird • | • Kennel |\n| Dog • | • Shed |",
      answer="Cow — Shed · Bird — Nest · Dog — Kennel"),
    _("COUNT_WRITE", "Count and Write", "I6", "NEW", "ONE_WORD",
      "Counting objects.", 1, (1, 3), "NUMERIC", "RECALL",
      stimulus="IMAGE", subjects=_MATHS, aliases=("COUNT AND WRITE",),
      notes="A character-based variant (★ ★ ★ ★ ★) would unblock it without pictures — worth prototyping."),
    _("CROSS_OUT", "Cross Out the Wrong One", "I7", "NEW", "ONE_WORD",
      "Classification with a non-verbal response.", 1, (1, 4), "MARK", "CLASSIFY",
      aliases=("CROSS OUT", "CROSS OUT THE WORD THAT DOES NOT BELONG"),
      brief="Four or five simple words in one line; exactly one does not belong, and the student crosses it out. The answer names the word and why.",
      example="Cross out (✗) the word that does not belong.\napple, banana, chair, mango",
      answer="chair — the others are fruits"),
    _("PATTERN_COMPLETE", "Complete the Pattern", "I8", "NEW", "ONE_WORD",
      "Pattern recognition.", 1, (1, 5), "SHORT_TEXT", "SEQUENCE",
      aliases=("COMPLETE THE PATTERN", "WHAT COMES NEXT PATTERN"),
      brief=("A repeating pattern of shape characters (▲ ● ■ ★ ◆) or letters/numbers with a "
             "blank ____ for the next item. Use characters only — never describe a picture."),
      example="Complete the pattern.\n▲ ● ▲ ● ▲ ____",
      answer="●"),
    _("COMPARE_QUANTITY", "Bigger / Smaller / Compare", "I9", "NEW", "ONE_WORD",
      "Comparing numbers.", 1, (1, 4), "MARK", "COMPARE",
      subjects=_MATHS, aliases=("PUT GREATER THAN LESS THAN", "COMPARE NUMBERS", "PUT > < OR ="),
      brief="Two or three number pairs with a circle ◯ between each; the student writes >, < or = in the circle.",
      example="Put >, < or = in the circle.\n45 ◯ 54        128 ◯ 128",
      answer="<, ="),
    _("NAME_PICTURE", "Look and Write the Name", "I10", "NEW", "ONE_WORD",
      "Naming what is pictured.", 1, (1, 3), "SHORT_TEXT", "IDENTIFY",
      stimulus="IMAGE", aliases=("LOOK AND WRITE",)),
    _("WORD_SEARCH", "Find and Circle (Word Search)", "I11", "NEW", "ONE_WORD",
      "Word recognition.", 4, (2, 6), "MARK", "IDENTIFY",
      marks_range=(2, 6), stimulus="TABLE", aliases=("WORD SEARCH", "FIND AND CIRCLE"),
      brief=("A letter grid of 4–6 rows as a table, and 3–5 words to find. Place every word "
             "left-to-right inside a single row, then fill the remaining cells with letters. "
             "1 mark per word. The answer gives the row of each word."),
      example="Find and circle these words in the grid: SUN, RAIN, WIND, CLOUD\n| S | U | N | M | R |\n| K | R | A | I | N |\n| W | I | N | D | P |\n| C | L | O | U | D |",
      answer="SUN row 1 · RAIN row 2 · WIND row 3 · CLOUD row 4"),
    _("MAZE_PATH", "Maze / Find the Path", "I12", "NEW", "DIAGRAM",
      "Spatial problem solving.", 1, (1, 5), "DRAW", "APPLY",
      marks_range=(1, 2), stimulus="IMAGE", aliases=("MAZE",)),
    _("CUT_PASTE_SORT", "Cut and Paste / Sort into Boxes", "I13", "NEW", "DIAGRAM",
      "Sorting as a physical activity.", 2, (1, 5), "MARK", "CLASSIFY",
      marks_range=(1, 4), stimulus="IMAGE", aliases=("CUT AND PASTE",)),
    _("SEQUENCE_PICTURES", "Arrange the Picture Story", "I15", "NEW", "SHORT_ANSWER",
      "Ordering a picture story.", 2, (1, 5), "ORDER", "SEQUENCE",
      marks_range=(2, 4), stimulus="IMAGE", aliases=("PICTURE STORY",),
      notes="The text version is SEQUENCE_WRITE (B10), which tests the same skill."),
    _("OPPOSITE_WRITE", "Write the Opposite", "I16", "NEW", "ONE_WORD",
      "Opposites.", 1, (1, 5), "SHORT_TEXT", "RECALL",
      marks_range=(1, 3), aliases=("WRITE THE OPPOSITE",),
      brief="Two to four simple words each followed by × and a blank; the student writes the opposite.",
      example="Write the opposite.\n(i) big × ________  (ii) day × ________  (iii) hot × ________",
      answer="(i) small (ii) night (iii) cold"),
    _("NUMBER_GRID", "Complete the Number Grid", "I17", "NEW", "SHORT_ANSWER",
      "Number order.", 2, (1, 4), "NUMERIC", "SEQUENCE",
      marks_range=(1, 3), stimulus="TABLE", subjects=_MATHS, aliases=("NUMBER GRID", "FILL IN THE MISSING NUMBERS GRID"),
      brief="A table of consecutive numbers (two rows of five) with some cells left blank; ½ or 1 mark per blank as the marks allow.",
      example="Fill in the missing numbers.\n| 21 | 22 |  | 24 |  |\n| 26 |  | 28 |  | 30 |",
      answer="23, 25, 27, 29"),
    _("CROSSWORD", "Crossword", "I18", "NEW", "ONE_WORD",
      "Vocabulary through clues.", 4, (3, 8), "SHORT_TEXT", "RECALL",
      marks_range=(2, 8), stimulus="TABLE", availability="internal", aliases=("CROSSWORD",),
      reason="Needs a crossword grid builder — planned as a separate feature."),
    _("RHYMING_WORDS", "Rhyming Words", "I19", "NEW", "ONE_WORD",
      "Sound patterns in words.", 1, (1, 3), "SHORT_TEXT", "CREATE",
      marks_range=(1, 3), marking="KEYWORD_SET", subjects=_LANGUAGES, aliases=("RHYMING WORDS", "WORDS THAT RHYME"),
      brief="Two to four simple words; the student writes a word that rhymes with each. The answer lists acceptable rhymes.",
      example="Write a word that rhymes with each.\n(i) cat ________  (ii) tree ________",
      answer="(i) hat, mat, bat (ii) bee, sea, free"),
    _("PHONICS_MATCH", "Match the Sound / Beginning Letter", "I21", "NEW", "ONE_WORD",
      "Letter–sound correspondence.", 1, (1, 2), "SHORT_TEXT", "IDENTIFY",
      stimulus="IMAGE", subjects=_LANGUAGES, aliases=("BEGINNING LETTER", "PHONICS")),
]
