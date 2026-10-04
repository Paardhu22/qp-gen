"""Family H — practical, computer and skill."""

from __future__ import annotations

from services.question_types.catalog._build import FOUR, family_builder

_ = family_builder("PRACTICAL")

#: Application-skill types: set in ICT and Computer Science, nowhere else.
_COMPUTING = ("ict", "computer science")

ENTRIES = [
    _("EXPERIMENT_BASED", "Experiment Based", "H1", "LIVE", "EXPERIMENTAL",
      "Procedure, apparatus and observation.", 3, (6, 10), "SHORT_TEXT", "APPLY",
      marks_range=(2, 5), marking="SCHEME", subjects=("science",),
      aliases=("EXPERIMENTAL", "EXPERIMENT", "EXPERIMENT BASED"),
      brief="Ask the student to describe an experiment: aim, apparatus, procedure and observation. Never refer to a pictured set-up.",
      example="Describe an experiment to show that carbon dioxide is released during respiration. State the apparatus used and the observation.",
      answer="Apparatus 1 · procedure 2 · observation 1 · conclusion 1"),
    _("EXPERIMENT_DESIGN", "Design an Experiment", "H2", "NEW", "SHORT_ANSWER",
      "Variable control and method design.", 3, (6, 10), "LONG_TEXT", "CREATE",
      marks_range=(3, 5), marking="SCHEME", subjects=("science",), aliases=("DESIGN AN EXPERIMENT",),
      brief="A question to investigate; the student designs a simple experiment, naming the control and the variable changed.",
      example="Design a simple experiment to find out whether sunlight is necessary for photosynthesis. State your control and the variable you would change.",
      answer="Destarched plant 1 · cover part of a leaf (variable) 1 · uncovered leaf as control, iodine test 1"),
    _("OBSERVATION_RUBRIC", "Observation Rubric", "H3", "DB", "SHORT_ANSWER",
      "Internal assessment.", 1, (1, 10), "SHORT_TEXT", "APPLY",
      marks_range=(1, 10), marking="RUBRIC", availability="internal",
      reason="Internal assessment, not a printed paper item."),
    _("PORTFOLIO_ARTEFACT", "Portfolio Artefact", "H4", "DB", "SHORT_ANSWER",
      "Project and assignment tracking.", 1, (1, 10), "LONG_TEXT", "CREATE",
      marks_range=(1, 10), marking="RUBRIC", availability="internal",
      reason="Project tracking, not a printed paper item."),
    _("CODE_OUTPUT", "Predict the Code Output", "H5", "DB", "SHORT_ANSWER",
      "Tracing a program.", 2, (6, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(1, 3), stimulus="CODE", aliases=("OUTPUT OF THE CODE", "PREDICT THE OUTPUT"),
      brief="A short program (Python unless stated) in a code block; the student writes its exact output.",
      example="What will be the output of the following Python code?\nx = 5\nfor i in range(3):\n    x = x + i\nprint(x)",
      answer="8"),
    _("ALGORITHM_DESIGN", "Algorithm Design", "H6", "DB", "SHORT_ANSWER",
      "Step-by-step problem solving.", 3, (5, 10), "LONG_TEXT", "CREATE",
      marks_range=(2, 4), marking="SCHEME", aliases=("WRITE AN ALGORITHM",),
      brief="A small problem; the student writes numbered algorithm steps.",
      example="Write an algorithm to find the largest of three numbers."),
    _("FLOWCHART_DRAW", "Draw a Flowchart", "H7", "NEW", "DIAGRAM",
      "Representing an algorithm with flowchart symbols.", 3, (5, 10), "DRAW", "CREATE",
      marks_range=(3, 4), marking="SCHEME", aliases=("DRAW A FLOWCHART",),
      brief="A small problem; the student draws a flowchart with standard symbols. Never refer to a printed figure.",
      example="Draw a flowchart to check whether a number is even or odd."),
    _("CODE_DEBUG", "Debug the Code", "H8", "NEW", "SHORT_ANSWER",
      "Finding and fixing errors in code.", 2, (7, 10), "SHORT_TEXT", "CORRECT",
      marks_range=(2, 3), stimulus="CODE", aliases=("DEBUG", "FIND THE ERRORS"),
      brief="A short program with a stated number of errors in a code block; the student identifies and corrects each.",
      example="The following code has two errors. Identify and correct them.\nfor i in range(5)\nprint(i)",
      answer="Missing colon after range(5); print(i) must be indented."),
    _("CODE_WRITE", "Write the Code", "H9", "NEW", "SHORT_ANSWER",
      "Writing a small program.", 3, (7, 10), "LONG_TEXT", "CREATE",
      marks_range=(3, 5), marking="SCHEME", aliases=("WRITE A PROGRAM",),
      brief="A small task; the student writes a program. The answer is a sample program plus a marking scheme.",
      example="Write a Python program to print the multiplication table of a number entered by the user."),
    # Class 10 too: the CBSE IT (402) paper asks shortcut and menu MCQs.
    _("TOOL_IDENTIFY", "Identify Tool / Shortcut", "H10", "NEW", "MCQ",
      "Software tools and shortcuts.", 1, (3, 10), "MCQ_4", "IDENTIFY",
      options=FOUR, aliases=("KEYBOARD SHORTCUT",),
      brief="A question about a software tool or keyboard shortcut, with four options.",
      example="Which keyboard shortcut is used to copy selected text?\n(a) Ctrl + X  (b) Ctrl + C  (c) Ctrl + V  (d) Ctrl + Z",
      answer="(b) Ctrl + C"),
    _("SAFETY_PROCEDURE", "Safety / Procedure", "H11", "NEW", "SHORT_ANSWER",
      "Safe practice.", 3, (4, 10), "SHORT_TEXT", "RECALL",
      marks_range=(1, 3), marking="KEYWORD_SET", aliases=("SAFETY PRECAUTIONS",),
      brief="Ask for N safety precautions or procedure steps for a stated setting; one mark each.",
      example="State three safety precautions to be followed while working in a science laboratory."),
    # ICT application skills, from the CBSE IT (402) and Cambridge IGCSE ICT papers.
    _("SHORTCUT_KEY", "Write the Shortcut Key", "H12", "NEW", "ONE_WORD",
      "Keyboard shortcut recall.", 1, (3, 10), "SHORT_TEXT", "RECALL",
      subjects=_COMPUTING, aliases=("SHORTCUT KEY", "WRITE THE SHORTCUT KEY"),
      brief=("A task in a named application or the operating system; the student writes its "
             "keyboard shortcut, keys joined with +. Use the shortcut the chapter teaches."),
      example="Write the shortcut key to undo the last action.",
      answer="Ctrl + Z"),
    _("SOFTWARE_STEPS", "Write the Steps (Software)", "H13", "NEW", "SHORT_ANSWER",
      "Carrying out a task in an application.", 3, (3, 10), "LONG_TEXT", "SEQUENCE",
      marks_range=(2, 5), marking="SCHEME", subjects=_COMPUTING,
      aliases=("SOFTWARE STEPS", "MENU PATH"),
      brief=("A task in a named application (word processor, spreadsheet, presentation, browser, "
             "email); the student writes the numbered steps, giving each menu path as Menu → Option. "
             "One mark per key step."),
      example="Write the steps to insert a table with 4 rows and 3 columns in a Writer document.",
      answer="Place the cursor 1 · Table → Insert Table 1 · set 3 columns and 4 rows, click Insert 1"),
    _("SPREADSHEET_FORMULA", "Write the Spreadsheet Formula", "H14", "NEW", "SHORT_ANSWER",
      "Formulas and functions on a worksheet.", 4, (5, 10), "SHORT_TEXT", "APPLY",
      marks_range=(2, 5), stimulus="TABLE", container="SUB_PARTS", marking="SCHEME",
      subjects=_COMPUTING, aliases=("EXCEL FORMULA", "CALC FORMULA", "SPREADSHEET FUNCTION"),
      brief=("A small worksheet as a table: the header row is the column letters and the first "
             "column the row numbers. Parts (i), (ii)… each name a cell and a result; the student "
             "writes the formula or function, starting with =, that goes in it. 1 mark each."),
      example=("The worksheet shows the marks of three students.\n|   | A | B | C | D |\n"
               "| 1 | Name | Maths | Science | Total |\n| 2 | Anu | 78 | 85 |  |\n"
               "| 3 | Ravi | 64 | 72 |  |\n| 4 | Meena | 91 | 88 |  |\n"
               "(i) Write the formula in D2 to find Anu's total marks.\n"
               "(ii) Write the function in B5 to find the highest marks in Maths."),
      answer="(i) =B2+C2 or =SUM(B2:C2) (ii) =MAX(B2:B4)"),
    # Seeded by migration 0012 but not in Draft 1 of the catalogue.
    _("PRACTICAL_TASK", "Practical Task", "H+1", "DB", "SHORT_ANSWER",
      "Hands-on skill.", 1, (1, 10), "SHORT_TEXT", "APPLY",
      marks_range=(1, 10), marking="RUBRIC", availability="internal",
      reason="Internal assessment, not a printed paper item.", notes="Seeded by migration 0012."),
    _("PROJECT_WORK", "Project Work", "H+2", "DB", "LONG_ANSWER",
      "Extended project.", 5, (1, 10), "LONG_TEXT", "CREATE",
      marks_range=(1, 20), marking="RUBRIC", availability="internal",
      reason="Project work, not a printed paper item.", notes="Seeded by migration 0012."),
]
