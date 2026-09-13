"""Family E — visual and diagram. Draw, label, or read a figure.

Two halves that matter a great deal here:

* the STUDENT draws — the paper prints only words, so these work today;
* the PAPER prints a figure — blocked, except charts and grids, which the
  deterministic renderer in `services.figures` can draw from data.
"""

from __future__ import annotations

from services.question_types.catalog._build import family_builder

_ = family_builder("VISUAL")

_NO_FIGURE = (
    "The student draws — never refer to a figure printed on the paper ('study the given "
    "figure'), because there is none."
)

ENTRIES = [
    _("DIAGRAM_DRAW", "Draw a Diagram", "E1", "LIVE", "DIAGRAM",
      "Structural recall through drawing.", 3, (4, 10), "DRAW", "RECALL",
      marks_range=(2, 5), marking="SCHEME",
      aliases=("DRAW A DIAGRAM", "DRAW AND LABEL", "LABELLED DIAGRAM", "DIAGRAM"),
      brief=f"Ask the student to draw a neat labelled diagram and label N parts. {_NO_FIGURE} The answer is a marking scheme: diagram, labels, neatness.",
      example="Draw a neat labelled diagram of the human eye and label any four parts.",
      answer="Diagram 2 · four correct labels 2 · neatness 1"),
    _("DIAGRAM_LABEL", "Label the Diagram", "E2", "DB", "DIAGRAM",
      "Identifying the parts of a printed figure.", 5, (1, 10), "DRAW", "IDENTIFY",
      marks_range=(1, 5), stimulus="IMAGE", aliases=("LABEL THE DIAGRAM",)),
    _("RAY_CIRCUIT_DIAGRAM", "Ray / Circuit Diagram", "E3", "DB", "DIAGRAM",
      "Technical drawing to convention.", 5, (8, 10), "DRAW", "APPLY",
      marks_range=(3, 5), marking="SCHEME", subjects=("science",),
      aliases=("RAY DIAGRAM", "CIRCUIT DIAGRAM"),
      brief=f"Ask the student to draw a ray or circuit diagram for a stated arrangement and state characteristics of the result. {_NO_FIGURE}",
      example=("Draw a ray diagram to show the formation of an image by a concave mirror when the object is "
               "placed between the pole and the focus. State two characteristics of the image formed."),
      answer="Correct rays 3 · virtual, erect, magnified 2"),
    _("FLOWCHART_COMPLETE", "Complete the Flowchart", "E4", "DB", "SHORT_ANSWER",
      "Sequence and relationship.", 2, (3, 10), "SHORT_TEXT", "SEQUENCE",
      marks_range=(2, 4), aliases=("COMPLETE THE FLOWCHART", "FLOW CHART"),
      brief="A flowchart written as text with arrows and blanks, e.g. 'Evaporation → ________ → Precipitation → ________'. 1 mark per blank.",
      example="Complete the flowchart showing the water cycle.\nEvaporation → ________ → Precipitation → ________",
      answer="Condensation · Collection (run-off)"),
    _("TABLE_COMPLETE", "Complete the Table", "E5", "DB", "SHORT_ANSWER",
      "Structured recall.", 3, (2, 10), "SHORT_TEXT", "RECALL",
      marks_range=(1, 6), stimulus="TABLE", aliases=("COMPLETE THE TABLE", "FILL THE TABLE"),
      brief="A partially filled table (header row plus 3–5 rows) with some cells left blank; 1 mark per blank cell.",
      example="Complete the table.\n| Animal | Young one | Home |\n| Cow | Calf |  |\n| Hen |  | Coop |\n|  | Puppy | Kennel |",
      answer="Shed · Chick · Dog"),
    _("IMAGE_IDENTIFY", "Identify from Image", "E6", "DB", "SHORT_ANSWER",
      "Recognition.", 1, (1, 10), "SHORT_TEXT", "IDENTIFY",
      marks_range=(1, 2), stimulus="IMAGE", aliases=("IDENTIFY THE PICTURE",)),
    _("MAP_SKILL", "Map Skill", "E7", "DB", "DIAGRAM",
      "Locating and labelling on a map.", 3, (3, 10), "DRAW", "IDENTIFY",
      marks_range=(2, 5), stimulus="MAP", container="SUB_PARTS",
      aliases=("MAP WORK", "LOCATE AND LABEL", "MAP BASED"),
      notes="Mandatory in CBSE Class 10 Social Science. Needs a visually impaired alternative."),
    _("GRAPH_PLOT", "Plot a Graph", "E8", "DB", "DIAGRAM",
      "Representing data visually.", 3, (5, 10), "DRAW", "CREATE",
      marks_range=(3, 5), stimulus="TABLE", marking="SCHEME", aliases=("PLOT A GRAPH", "DRAW A GRAPH"),
      brief=("A small data table printed in the question; the student draws the graph on the graph "
             "paper supplied with the answer sheet. Never print or describe a plotted graph."),
      notes="Graph paper comes with the answer sheet, so only the data is printed.",
      example="The table shows the temperature recorded at different hours of a day. Draw a line graph.\n| Time | 6 a.m. | 9 a.m. | 12 noon | 3 p.m. | 6 p.m. |\n| Temp (°C) | 18 | 24 | 31 | 33 | 27 |",
      answer="Axes and scale 1 · points plotted 1 · line drawn 1"),
    _("GRAPH_READ", "Read the Graph", "E9", "NEW", "SHORT_ANSWER",
      "Interpreting a printed graph.", 2, (4, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(2, 4), stimulus="GRAPH", aliases=("READ THE GRAPH", "GRAPH READING"),
      brief="One graph supplied as data in `figure` (the paper prints it), then a single question answerable only by reading values or trends from it.",
      example="[LINE GRAPH: temperature through a day]\nAt what time was the temperature highest, and by how much did it fall by 6 p.m.?",
      answer="3 p.m.; it fell by 6 °C"),
    _("GEOM_CONSTRUCTION", "Geometric Construction", "E10", "DB", "DIAGRAM",
      "Compass-and-straightedge accuracy.", 5, (6, 10), "DRAW", "APPLY",
      marks_range=(3, 5), marking="SCHEME", subjects=("mathematics",), also_in=("G15",),
      aliases=("CONSTRUCTION", "CONSTRUCT A TRIANGLE"),
      brief=f"Give exact measurements and ask the student to construct the figure and write the steps of construction. {_NO_FIGURE}",
      example="Construct a triangle ABC in which BC = 7 cm, ∠B = 60° and AB + AC = 12 cm. Write the steps of construction.",
      answer="Steps 2 · accurate construction 3"),
    _("DRAW_COLOUR", "Draw and Colour", "E11", "DB", "DIAGRAM",
      "Recognition and fine motor skill.", 2, (1, 3), "DRAW", "CREATE",
      marks_range=(1, 2), aliases=("DRAW AND COLOUR", "DRAW_COLOUR_TRACE"),
      brief=f"A one-line instruction to draw a familiar object and colour it as told. {_NO_FIGURE}",
      example="Draw a mango and colour it yellow.",
      answer="A recognisable mango, coloured yellow"),
    _("TRACE_PATTERN", "Trace the Pattern", "E12", "NEW", "DIAGRAM",
      "Pencil control and letter/number formation.", 1, (1, 2), "DRAW", "CREATE",
      marks_range=(1, 2), stimulus="IMAGE", aliases=("TRACE",)),
    _("JOIN_DOTS", "Join the Dots", "E13", "NEW", "DIAGRAM",
      "Counting order and shape recognition.", 1, (1, 2), "DRAW", "SEQUENCE",
      marks_range=(1, 2), stimulus="IMAGE", also_in=("I14",), aliases=("JOIN THE DOTS",)),
    _("SYMMETRY_DRAW", "Symmetry / Reflection Drawing", "E14", "NEW", "DIAGRAM",
      "Spatial reasoning.", 2, (3, 8), "DRAW", "APPLY",
      marks_range=(2, 3), stimulus="IMAGE", subjects=("mathematics",), aliases=("LINE OF SYMMETRY",)),
    _("CIRCLE_PICTURE", "Circle / Tick on the Picture", "E15", "NEW", "ONE_WORD",
      "Visual discrimination with a non-verbal response.", 1, (1, 3), "MARK", "IDENTIFY",
      stimulus="IMAGE", also_in=("I2",), aliases=("CIRCLE THE PICTURE", "CIRCLE THE CORRECT PICTURE"),
      notes="The most common Class 1–2 item in Indian schools."),
    _("CLOCK_DRAW", "Draw the Hands on the Clock", "E16", "NEW", "DIAGRAM",
      "Time representation.", 1, (1, 4), "DRAW", "APPLY",
      marks_range=(1, 2), stimulus="IMAGE", subjects=("mathematics",), aliases=("DRAW THE HANDS",)),
]
