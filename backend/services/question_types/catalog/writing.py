"""Family F (iii) — language: writing.

All writing is original generation — never retrieved from a textbook and
never reused from the bank, because a reused writing prompt is a leak. Formats
the independent writing generator already writes (`WRITING_FORMAT_GLOSS` in
`services/assets/writing.py`) carry a `route` to it.
"""

from __future__ import annotations

from services.question_types.catalog._build import family_builder
from services.question_types.spec import Route

_ = family_builder("LANGUAGE")

_LANGUAGES = ("english", "hindi", "telugu", "sanskrit")


def _writing(asset_type: str, *also: str) -> Route:
    return Route("writing_asset_pool", asset_type, also=also)


_RUBRIC = "The answer is a rubric: format, content, expression."

ENTRIES = [
    _("LETTER_WRITING", "Letter Writing", "F19", "LIVE", "LETTER",
      "Format, tone and content.", 5, (4, 10), "LONG_TEXT", "CREATE",
      marks_range=(5, 6), marking="RUBRIC", lane="original",
      route=_writing(
          "formal_letter_to_authority", "letter_to_editor", "letter_of_complaint",
          "letter_of_enquiry", "letter_placing_order",
      ),
      subjects=_LANGUAGES,
      aliases=("LETTER", "FORMAL LETTER", "INFORMAL LETTER", "पत्र लेखन"),
      brief=f"A situation naming the writer, class and school and the recipient, and a word limit (100–120 words). {_RUBRIC}",
      example="You are Rahul of Class X, Sunrise Public School. Write a letter to the Principal requesting permission to organise a book donation drive in your school. (100–120 words)",
      answer="Format 1 · content 2 · expression 2"),
    _("EMAIL_WRITING", "Email Writing", "F20", "DB", "LETTER",
      "Functional email format and content.", 5, (6, 10), "LONG_TEXT", "CREATE",
      marks_range=(4, 5), marking="RUBRIC", lane="original", route=_writing("email"),
      subjects=_LANGUAGES, aliases=("EMAIL", "E-MAIL"),
      brief=f"A situation calling for an email, with the sender, recipient, purpose and a word limit. {_RUBRIC}",
      example="You are Meera, the class monitor. Write an email to your class teacher asking to reschedule the science quiz. (80–100 words)"),
    _("NOTICE_WRITING", "Notice Writing", "F21", "NEW", "COMPOSITION",
      "Notice format: box, heading, date, signature.", 4, (6, 10), "LONG_TEXT", "CREATE",
      marks_range=(4, 5), marking="RUBRIC", lane="original", route=_writing("notice"),
      subjects=_LANGUAGES, aliases=("NOTICE",),
      brief=f"A situation naming the issuer (Head Boy, Secretary) and the event, and a word limit (about 50 words). The format is heavily marked. {_RUBRIC}",
      example="You are the Head Boy of your school. Write a notice informing students about an inter-house quiz competition. (50 words)"),
    _("MESSAGE_WRITING", "Message Writing", "F22", "NEW", "COMPOSITION",
      "Taking and conveying a message.", 3, (5, 9), "LONG_TEXT", "CREATE",
      marks_range=(3, 4), marking="RUBRIC", lane="original", subjects=_LANGUAGES, aliases=("MESSAGE",),
      brief=f"A phone call or situation to be written up as a short message with date, time, to, from and body (about 50 words). {_RUBRIC}",
      example="Your mother's friend called while she was out, to say the meeting has moved to 5 p.m. tomorrow. Write a message for your mother. (50 words)"),
    _("ESSAY_WRITING", "Essay / Composition", "F23", "LIVE", "COMPOSITION",
      "Organised extended writing on a topic.", 8, (4, 10), "LONG_TEXT", "CREATE",
      marks_range=(5, 10), marking="RUBRIC", lane="original", subjects=_LANGUAGES,
      aliases=("ESSAY", "COMPOSITION", "निबंध"),
      brief=f"A topic and a word limit (150–200 words for Classes 8–10, less for younger classes). {_RUBRIC}",
      example="Write an essay on 'The Importance of Trees in Our Life'. (150–200 words)"),
    _("STORY_WRITING", "Story Writing", "F24", "NEW", "COMPOSITION",
      "Narrative writing from cues.", 5, (3, 10), "LONG_TEXT", "CREATE",
      marks_range=(5, 8), marking="RUBRIC", lane="original", route=_writing("story"),
      subjects=_LANGUAGES, aliases=("STORY", "COMPLETE THE STORY"),
      brief=f"An outline, an opening line or a set of given words, and a word limit. Say which of the three the student is working from. {_RUBRIC}",
      example="Complete the story in about 120 words.\nIt was almost midnight when Meera heard a faint knock at the door…"),
    _("PARAGRAPH_WRITING", "Paragraph Writing", "F25", "NEW", "COMPOSITION",
      "A single organised paragraph.", 4, (3, 10), "LONG_TEXT", "CREATE",
      marks_range=(4, 5), marking="RUBRIC", lane="original", subjects=_LANGUAGES, aliases=("PARAGRAPH",),
      brief=f"A topic or a few cue words, and a word limit (60–100 words). {_RUBRIC}",
      example="Write a paragraph on 'My Favourite Festival' in about 80 words."),
    _("ANALYTICAL_PARAGRAPH", "Analytical Paragraph", "F26", "LIVE", "ANALYTICAL_PARAGRAPH",
      "Describing data in prose.", 5, (9, 10), "LONG_TEXT", "INTERPRET",
      stimulus="TABLE", marking="RUBRIC", lane="original", route=_writing("analytical_paragraph"),
      subjects=_LANGUAGES, aliases=("ANALYTICAL PARAGRAPH",),
      brief=f"Data (a table or described chart) and a word limit (100–120 words); the student describes trends and comparisons. {_RUBRIC}",
      example="The table shows the mode of transport used by students of a school. Write an analytical paragraph in 100–120 words."),
    _("DIALOGUE_WRITING", "Dialogue Writing", "F27", "DB", "COMPOSITION",
      "Writing a conversation.", 4, (4, 9), "LONG_TEXT", "CREATE",
      marks_range=(4, 5), marking="RUBRIC", lane="original", subjects=_LANGUAGES, aliases=("DIALOGUE",),
      brief=f"A situation and the two speakers; the student writes a dialogue of 8–10 exchanges. {_RUBRIC}",
      example="Write a dialogue between a shopkeeper and a customer who wants to return a faulty torch."),
    _("DIARY_ENTRY", "Diary Entry", "F28", "NEW", "COMPOSITION",
      "Personal reflective writing.", 4, (5, 9), "LONG_TEXT", "CREATE",
      marks_range=(4, 5), marking="RUBRIC", lane="original", subjects=_LANGUAGES, aliases=("DIARY",),
      brief=f"An event to reflect on, with a word limit (about 100 words). {_RUBRIC}",
      example="You visited an old-age home with your class today. Write a diary entry about the experience in about 100 words."),
    _("SPEECH_DEBATE", "Speech / Debate", "F29", "NEW", "COMPOSITION",
      "Persuasive spoken-style writing.", 5, (7, 10), "LONG_TEXT", "CREATE",
      marks_range=(5, 8), marking="RUBRIC", lane="original", route=_writing("speech", "debate"),
      subjects=_LANGUAGES, aliases=("SPEECH", "DEBATE", "SPEECH_DEBATE_WRITING"),
      brief=f"A motion or topic, the occasion and a word limit; for a debate, state for or against. {_RUBRIC}",
      example="Write a speech to be delivered in the school assembly on 'Say No to Single-Use Plastic'. (120 words)"),
    _("PICTURE_COMPOSITION", "Picture Composition", "F30", "NEW", "COMPOSITION",
      "Writing about a picture.", 5, (1, 6), "LONG_TEXT", "CREATE",
      marks_range=(3, 5), stimulus="IMAGE", marking="RUBRIC", lane="original",
      subjects=_LANGUAGES, aliases=("DESCRIBE THE PICTURE",),
      notes="The main writing format for Classes 1–4."),
    _("TRANSLATION", "Translation", "F31", "DB", "SHORT_ANSWER",
      "Rendering meaning in another language.", 2, (3, 10), "SHORT_TEXT", "CREATE",
      marks_range=(1, 5), marking="SCHEME", lane="original", subjects=_LANGUAGES,
      aliases=("TRANSLATE",),
      brief="One to five short sentences to translate into the named language.",
      example="Translate into Hindi: The farmer works hard in his field."),
    # Seeded by migration 0012 but not in Draft 1 of the catalogue.
    _("ARTICLE_WRITING", "Article Writing", "F+1", "DB", "COMPOSITION",
      "Article format and argument.", 5, (8, 10), "LONG_TEXT", "CREATE",
      marks_range=(5, 6), marking="RUBRIC", lane="original", route=_writing("article"),
      subjects=_LANGUAGES, aliases=("ARTICLE",),
      brief=f"A topic, a title requirement and a word limit (120–150 words). {_RUBRIC}",
      example="Write an article for your school magazine on 'Why every child should learn to swim'. (120–150 words)",
      notes="Not in Draft 1 of the catalogue; kept because the writing generator writes it."),
    _("REPORT_WRITING", "Report Writing", "F+2", "DB", "COMPOSITION",
      "Report format: heading, byline, account.", 5, (8, 10), "LONG_TEXT", "CREATE",
      marks_range=(5, 6), marking="RUBRIC", lane="original", route=_writing("report"),
      subjects=_LANGUAGES, aliases=("REPORT",),
      brief=f"An event to report, the reporter's role and a word limit (120–150 words). {_RUBRIC}",
      example="As the cultural secretary, write a report on the Annual Day celebrations of your school. (120–150 words)",
      notes="Not in Draft 1 of the catalogue; kept because the writing generator writes it."),
    _("ADVERTISEMENT_WRITING", "Advertisement Writing", "F+3", "DB", "COMPOSITION",
      "Advertisement format.", 4, (9, 10), "LONG_TEXT", "CREATE",
      marking="RUBRIC", lane="original", availability="internal", subjects=_LANGUAGES,
      reason="Not in Draft 1 of the catalogue.", notes="Seeded by migration 0012."),
    _("NOTE_MAKING_SUMMARY", "Note Making & Summary", "F+4", "DB", "COMPOSITION",
      "Note making and summarising.", 5, (9, 10), "LONG_TEXT", "INTERPRET",
      stimulus="PASSAGE", marking="RUBRIC", lane="original", availability="internal",
      subjects=_LANGUAGES, reason="Not in Draft 1 of the catalogue.", notes="Seeded by migration 0012."),
    _("ORAL_TASK", "Oral Task", "F+5", "DB", "SHORT_ANSWER",
      "Speaking and listening.", 2, (1, 10), "SHORT_TEXT", "CREATE",
      marks_range=(1, 10), marking="RUBRIC", availability="internal", subjects=_LANGUAGES,
      reason="Internal assessment, not a printed paper item.", notes="Seeded by migration 0012."),
]
