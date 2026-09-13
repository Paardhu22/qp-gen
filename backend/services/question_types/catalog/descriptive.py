"""Family C — descriptive. The student writes in their own words.

HOTS and COMPETENCY are deliberately absent: they were never question types.
HOTS is a Bloom level that applies to any type and COMPETENCY is a real-world
framing — both are slot attributes now. Old data carrying either name still
reads, through `shapes.SHAPES` (`retired=True`).

CBSE word limits: VSA 30–40, SA 40–60, LA 100–120.
"""

from __future__ import annotations

from services.question_types.catalog._build import family_builder

_ = family_builder("DESCRIPTIVE")

ENTRIES = [
    _("VSA", "Very Short Answer", "C1", "LIVE", "VERY_SHORT_ANSWER",
      "Single-fact recall or a one-step idea.", 1, (3, 10), "SHORT_TEXT", "RECALL",
      marks_range=(1, 2), marking="KEYWORD_SET", answer_lines=2,
      aliases=("VERY SHORT ANSWER", "VERY_SHORT_ANSWER"),
      brief="A question answerable in about 30 words.",
      example="What is meant by the term 'habitat'?",
      answer="The place where a plant or animal lives naturally and gets its food, air, water and shelter."),
    _("SA", "Short Answer", "C2", "LIVE", "SHORT_ANSWER",
      "Explanation of a single concept.", 2, (3, 10), "SHORT_TEXT", "APPLY",
      marks_range=(2, 3), marking="SCHEME", answer_lines=4,
      aliases=("SHORT ANSWER", "SHORT_ANSWER"),
      brief="A question answerable in 40–60 words. The answer is a marking scheme with one point per mark.",
      example="Why is the Sun called a natural source of energy? Give two reasons.",
      answer="(i) It gives light and heat without human effort. (ii) It is the original source of almost all other energy on Earth."),
    _("LA", "Long Answer", "C3", "LIVE", "LONG_ANSWER",
      "Multi-part explanation, often with a diagram.", 5, (6, 10), "LONG_TEXT", "APPLY",
      marks_range=(4, 6), marking="SCHEME", answer_lines=10,
      aliases=("LONG ANSWER", "LONG_ANSWER"),
      brief=("A question answerable in 100–120 words. The answer MUST be a marking scheme broken "
             "into sub-points with their marks, never one flat paragraph."),
      example=("Describe the process of digestion of food in the human body from the mouth to the small "
               "intestine. Mention the role of any two digestive juices."),
      answer="Mouth/saliva 1 · oesophagus 0.5 · stomach/gastric juice 1.5 · small intestine/bile and pancreatic juice 2"),
    _("VLA", "Very Long Answer / Essay Answer", "C4", "DB", "LONG_ANSWER",
      "Sustained argument across a whole topic.", 6, (9, 10), "LONG_TEXT", "JUSTIFY",
      marks_range=(6, 8), marking="SCHEME", answer_lines=14,
      aliases=("VERY LONG ANSWER", "ESSAY ANSWER"),
      brief="A question needing 150–200 words of sustained argument, e.g. examining a statement with reference to causes, programme and outcome. The answer is a marking scheme.",
      example=("\"The Non-Cooperation Movement marked a turning point in the Indian freedom struggle.\" "
               "Examine this statement with reference to its causes, programme and outcome."),
      answer="Causes 2 · programme 2 · outcome and significance 2"),
    _("DEFINE", "Define the Term", "C5", "NEW", "VERY_SHORT_ANSWER",
      "Precise definitional recall.", 1, (3, 10), "SHORT_TEXT", "RECALL",
      marks_range=(1, 2), marking="KEYWORD_SET", aliases=("DEFINE", "DEFINITION"),
      brief="Ask the student to define one term in about 25 words. The answer is the near-verbatim definition and its key words.",
      example="Define: Evaporation",
      answer="The process by which a liquid changes into vapour below its boiling point."),
    _("SHORT_JUSTIFY", "Give a Reason", "C6", "DB", "SHORT_ANSWER",
      "Causal explanation of a stated fact.", 2, (4, 10), "SHORT_TEXT", "JUSTIFY",
      marks_range=(1, 2), marking="SCHEME",
      aliases=("GIVE REASON", "GIVE REASONS", "GIVE REASONS FOR THE FOLLOWING"),
      brief="State a fact and ask 'Give a reason'. The answer MUST be a because-explanation, not a description.",
      example="Give a reason: Woollen clothes are worn in winter.",
      answer="Wool traps air, which is a poor conductor of heat, so body heat is not lost."),
    _("DIFFERENTIATE", "Differentiate / Distinguish Between", "C7", "NEW", "SHORT_ANSWER",
      "Contrastive understanding.", 3, (4, 10), "SHORT_TEXT", "COMPARE",
      marks_range=(2, 3), marking="SCHEME",
      aliases=("DIFFERENTIATE", "DISTINGUISH BETWEEN", "DIFFERENCE BETWEEN"),
      brief=("Ask for differences between two things, one point per mark ('any three points'). The "
             "answer MUST be paired contrasts — each point states both sides."),
      example="Differentiate between a mixture and a compound. (Any three points.)",
      answer="Composition variable/fixed · properties retained/changed · separation physical/chemical"),
    _("COMPARE_TABLE", "Differentiate — Tabular Form", "C8", "NEW", "SHORT_ANSWER",
      "Contrastive understanding in a required layout.", 3, (5, 10), "SHORT_TEXT", "COMPARE",
      stimulus="TABLE", marking="SCHEME", aliases=("TABULAR FORM", "DISTINGUISH IN TABULAR FORM"),
      brief=("Ask for differences 'in tabular form'. Print the empty table as part of the question: "
             "a header row 'Basis | X | Y' plus one empty row per point."),
      example="Distinguish between Xylem and Phloem in tabular form. (Any three points.)\n| Basis | Xylem | Phloem |\n|  |  |  |\n|  |  |  |\n|  |  |  |",
      answer="Function: water/food · direction: upward/both ways · cells: dead/living"),
    _("EXPLAIN_PROCESS", "Explain the Process", "C9", "NEW", "LONG_ANSWER",
      "A sequential mechanism.", 5, (5, 10), "LONG_TEXT", "SEQUENCE",
      marks_range=(3, 5), marking="SCHEME", aliases=("EXPLAIN THE PROCESS", "DESCRIBE THE PROCESS"),
      brief="Ask how a process happens, stage by stage, in 80–120 words. The marking scheme is ORDERED: stages must appear in sequence.",
      example="Explain how rain is formed. Mention the stages of the water cycle involved.",
      answer="Evaporation 1 · condensation 1 · cloud formation 1 · precipitation 1 · collection 1"),
    _("LIST_STATE", "List / State", "C10", "NEW", "SHORT_ANSWER",
      "Enumeration.", 2, (2, 10), "SHORT_TEXT", "RECALL",
      marks_range=(1, 4), marking="KEYWORD_SET", aliases=("LIST", "STATE", "LIST ANY", "WRITE ANY"),
      brief="'List any N…' where N matches the marks (½ or 1 mark per item). The answer lists valid items.",
      example="List any four uses of water in our daily life.",
      answer="Drinking, cooking, bathing/washing, irrigation (any four)"),
    _("APPLICATION_SCENARIO", "Application / Real-life Scenario", "C11", "NEW", "SHORT_ANSWER",
      "Transferring a concept to an unfamiliar situation.", 3, (5, 10), "SHORT_TEXT", "APPLY",
      marks_range=(3, 5), stimulus="SCENARIO", marking="SCHEME",
      aliases=("COMPETENCY BASED", "COMPETENCY", "REAL LIFE", "APPLICATION BASED", "SCENARIO BASED"),
      brief=("A short realistic scenario (two or three sentences, named people, everyday setting) "
             "followed by a question that needs the concept to explain or solve it."),
      example=("Meena's mother asked her to keep the milk in the refrigerator during summer but said it was not "
               "necessary in winter. Using what you know about microorganisms, explain her reasoning. "
               "Suggest one other way to preserve milk without a refrigerator."),
      answer="Microbes multiply faster in warmth 2 · one valid method (boiling, pasteurising) 1"),
    _("OPINION_JUSTIFY", "Justify Your Opinion", "C12", "NEW", "SHORT_ANSWER",
      "Taking a position and supporting it.", 3, (6, 10), "LONG_TEXT", "JUSTIFY",
      marks_range=(3, 5), marking="RUBRIC", aliases=("DO YOU AGREE", "JUSTIFY YOUR OPINION"),
      brief="A debatable claim in quotes, then 'Do you agree? Give N arguments to support your view.' The answer is a rubric (position, arguments, evidence), not one right answer.",
      example="\"Plastic should be completely banned in schools.\" Do you agree? Give three arguments to support your view.",
      answer="Rubric: clear position 1 · three relevant arguments 2"),
    _("PREDICT_OUTCOME", "Predict the Outcome", "C13", "NEW", "SHORT_ANSWER",
      "Applying a rule forward to a new case.", 2, (4, 10), "SHORT_TEXT", "APPLY",
      marks_range=(2, 3), marking="SCHEME", aliases=("WHAT WOULD HAPPEN IF", "PREDICT"),
      brief="'What would happen if…' about a change to a system, asking for N consequences.",
      example="What would happen if all the decomposers on Earth disappeared? Give two consequences.",
      answer="Dead matter would pile up 1 · nutrients would not return to the soil 1"),
    _("EXAMPLE_GIVE", "Give Examples", "C14", "NEW", "VERY_SHORT_ANSWER",
      "Instantiating a category.", 1, (1, 10), "SHORT_TEXT", "CLASSIFY",
      marks_range=(1, 2), marking="KEYWORD_SET", aliases=("GIVE EXAMPLES", "GIVE TWO EXAMPLES"),
      brief="Ask for N examples of one or more categories. The answer rule is 'any valid member of the category', with sample answers.",
      example="Give two examples each of: (i) Herbivores (ii) Carnivores",
      answer="(i) cow, deer (ii) lion, tiger — any valid examples"),
]
