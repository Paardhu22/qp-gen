"""Turns a generation request into an ordered plan of question slots.

Read in this order:

* ``subjects``      which subject/class combinations have a CBSE blueprint
* ``slots``         ``QuestionGenerationSlot``, the planner's output unit
* ``factory``       ``_make_slot``, which fills a slot's prompt text
* ``class10``       the exact Class 10 section tables
* ``instructions``  paper-level instruction prose
* ``slot_prompts``  per-slot prompt text
* ``plan``          ``build_question_plan`` — the entry point
"""

import logging

logging.getLogger("[GEN_ROUTER]").setLevel(logging.INFO)
