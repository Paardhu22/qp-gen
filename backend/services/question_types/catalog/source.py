"""Family D — source and stimulus based. Read something, then answer.

Every type here is a container: the stimulus is printed once and the
sub-questions (i), (ii), (iii) carry their own marks, which must sum to the
question's marks and be answerable from the stimulus alone.
"""

from __future__ import annotations

from services.question_types.catalog._build import family_builder
from services.question_types.spec import Route

_ = family_builder("SOURCE_BASED")

_LANGUAGES = ("english", "hindi", "telugu", "sanskrit")

ENTRIES = [
    _("CASE_STUDY", "Case Study", "D1", "LIVE", "CASE_STUDY",
      "Applying concepts to a described situation.", 4, (6, 10), "SHORT_TEXT", "APPLY",
      marks_range=(3, 5), stimulus="SCENARIO", container="SUB_PARTS", marking="SCHEME",
      aliases=("CASE BASED", "CASE STUDY", "CBQ", "CASE_BASED"),
      brief=("A scenario paragraph of 80–150 words, then exactly three sub-questions (i), (ii), "
             "(iii) worth 1 + 1 + 2 marks, each answerable from the scenario plus the chapter. "
             "No OR inside a case study."),
      example=("A farmer noticed that the yield from his field had been falling every year despite using the "
               "same fertiliser. A soil test showed the nitrogen content had dropped sharply. An officer advised "
               "him to grow groundnut in alternate seasons instead of rice.\n(i) Why did the nitrogen content fall? (1)\n"
               "(ii) How does growing groundnut help restore soil nitrogen? (1)\n"
               "(iii) Name this farming practice and state two other benefits of it. (2)"),
      answer="(i) Continuous cropping depletes one nutrient. (ii) Rhizobium in root nodules fixes nitrogen. (iii) Crop rotation — controls pests, improves soil structure."),
    _("SOURCE_BASED", "Source Based", "D2", "DB", "CASE_STUDY",
      "Extracting meaning from a historical or documentary source.", 4, (8, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(4, 5), stimulus="PASSAGE", container="SUB_PARTS", marking="SCHEME",
      subjects=("social science",), aliases=("SOURCE BASED", "SOURCE BASED QUESTION"),
      brief=("A quoted historical or documentary source of 60–120 words (a speech, letter or "
             "record), then three sub-questions worth 1 + 1 + 2 marks about who, what and why."),
      example=("\"We shall not surrender. We shall fight with the weapon of truth and non-violence. Freedom is our "
               "birthright and we shall have it.\"\n(i) Who is the likely speaker of these lines? (1)\n"
               "(ii) Which two principles are mentioned in the source? (1)\n"
               "(iii) Explain how these principles shaped the freedom movement. (2)"),
      answer="(i) Mahatma Gandhi (ii) Truth and non-violence (iii) Mass non-violent movements such as Non-Cooperation and Civil Disobedience"),
    _("PASSAGE_UNSEEN", "Unseen Passage / Reading Comprehension", "D3", "LIVE", "READING_COMP",
      "Comprehension of never-before-seen text.", 10, (3, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(4, 12), stimulus="PASSAGE", container="SUB_PARTS", marking="SCHEME",
      lane="original", route=Route("reading_asset_pool", "discursive_passage"),
      subjects=_LANGUAGES,
      aliases=("READING COMPREHENSION", "UNSEEN PASSAGE", "COMPREHENSION PASSAGE", "READING_COMP"),
      brief=("An ORIGINAL passage (250–450 words for Classes 8–10, 120–250 for Classes 3–7) that "
             "the student has never seen, then sub-questions of mixed kinds whose marks sum to the "
             "question's marks. Never drawn from a textbook and never reused."),
      example="Read the passage carefully and answer the questions that follow.\n[PASSAGE — 350 words]\n(i) When was the first post office opened in India? (1)\n(ii) Find a word from the passage that means 'to send'. (1)",
      notes="Generated fresh every time — a reused passage leaks."),
    _("EXTRACT_SEEN", "Seen Extract — Prose", "D4", "LIVE", "EXTRACT_PROSE",
      "Recall and interpretation of a studied chapter.", 3, (5, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(3, 5), stimulus="PASSAGE", container="SUB_PARTS", marking="SCHEME",
      subjects=_LANGUAGES, aliases=("PROSE EXTRACT", "EXTRACT BASED", "EXTRACT_PROSE"),
      brief="Quote a 3–6 line extract from the studied chapter, then three sub-questions (who/what/why and interpretation) worth 1 mark each.",
      example="\"I looked at the stranger again. There was something in his eyes that told me he had walked a very long way.\"\n(i) Who is the 'I' in the extract? (1)\n(ii) Who was the stranger? (1)\n(iii) What did the narrator conclude, and on what basis? (1)"),
    _("POETRY_APPRECIATION", "Seen Extract — Poetry", "D5", "LIVE", "EXTRACT_POETRY",
      "Poetic device, tone and meaning.", 3, (5, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(3, 5), stimulus="PASSAGE", container="SUB_PARTS", marking="SCHEME",
      subjects=_LANGUAGES, aliases=("POETRY EXTRACT", "STANZA BASED", "EXTRACT_POETRY"),
      brief="Quote a 4–6 line stanza from the studied poem, then sub-questions on the poem and poet, a figure of speech, and mood or meaning.",
      example="[STANZA — 4 lines from the prescribed poem]\n(i) Name the poem and the poet. (1)\n(ii) Identify the figure of speech in line 2. (1)\n(iii) What mood does the stanza create? (1)"),
    _("DATA_INTERPRETATION", "Data Interpretation", "D6", "DB", "CASE_STUDY",
      "Reading and reasoning from numbers.", 4, (5, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(3, 4), stimulus="GRAPH", container="SUB_PARTS", marking="EXACT",
      aliases=("DATA INTERPRETATION", "GRAPH BASED", "CHART BASED"),
      brief=("A bar graph, pie chart or line graph supplied as data in `figure` (the paper prints "
             "the chart), then sub-questions answerable only by reading it: a direct read, a "
             "comparison, and one calculation."),
      example="Study the bar graph showing the number of trees planted by four schools.\n[BAR GRAPH: School A 45, School B 70, School C 30, School D 55]\n(i) Which school planted the most trees? (1)\n(ii) How many more trees did School B plant than School C? (1)\n(iii) What is the average number of trees planted per school? (2)",
      answer="(i) School B (ii) 40 (iii) 50"),
    _("CARTOON_BASED", "Cartoon Based", "D7", "DB", "CASE_STUDY",
      "Interpreting political satire and symbolism.", 2, (9, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(1, 4), stimulus="CARTOON", container="SUB_PARTS",
      subjects=("social science",), aliases=("CARTOON BASED",),
      notes="Civics, Classes 9–10. Must carry a visually impaired alternative."),
    _("PICTURE_BASED", "Picture Based", "D8", "DB", "CASE_STUDY",
      "Observation and inference from an image.", 3, (1, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(2, 5), stimulus="IMAGE", container="SUB_PARTS", aliases=("PICTURE BASED",)),
    _("INFOGRAPHIC_BASED", "Infographic / Poster Based", "D9", "DB", "CASE_STUDY",
      "Reading mixed text-and-graphic information.", 3, (6, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(3, 4), stimulus="IMAGE", container="SUB_PARTS", aliases=("POSTER BASED", "INFOGRAPHIC")),
    _("AUDIO_VISUAL_STIM", "Audio / Visual Stimulus", "D10", "DB", "CASE_STUDY",
      "Listening or viewing comprehension.", 2, (1, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(1, 10), stimulus="AUDIO", container="SUB_PARTS",
      reason="Needs audio or video — out of scope for printed papers."),
    _("DIALOGUE_BASED", "Dialogue / Conversation Based", "D11", "NEW", "CASE_STUDY",
      "Comprehension of a spoken exchange; inferring relationship and intent.", 2, (3, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(2, 4), stimulus="DIALOGUE", container="SUB_PARTS", lane="original",
      aliases=("DIALOGUE BASED", "CONVERSATION BASED"),
      brief="An ORIGINAL short conversation of 4–8 lines between named speakers, then sub-questions on why, what and who, 1 mark each.",
      example="Anu: Amma, why can't I go out to play now?\nMother: Look at the sky, Anu. The clouds are very dark.\nAnu: But it isn't raining yet!\nMother: It will, in a few minutes.\n(i) Why did the mother stop Anu from going out? (1)\n(ii) What made the mother think it would rain? (1)"),
    _("NEWS_BASED", "News Report / Notice Based", "D12", "NEW", "CASE_STUDY",
      "Extracting facts from a functional text.", 2, (5, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(2, 4), stimulus="NOTICE", container="SUB_PARTS", lane="original",
      aliases=("NOTICE BASED", "NEWS BASED", "NEWS REPORT BASED"),
      brief="An ORIGINAL short notice or news report (school name, heading, date, time, venue, issuer), then factual sub-questions of 1 mark each.",
      example="SUNRISE PUBLIC SCHOOL — ANNUAL SPORTS DAY\nDate: 14 December · Time: 9:00 a.m. · Venue: School Ground\nStudents must report by 8:30 a.m. in uniform. — Sports Secretary\n(i) By what time must students report? (1)\n(ii) Who issued this notice? (1)"),
    _("EXPERIMENT_OBSERVATION", "Experiment / Observation Based", "D13", "NEW", "CASE_STUDY",
      "Interpreting experimental observations.", 3, (6, 10), "SHORT_TEXT", "INTERPRET",
      marks_range=(3, 5), stimulus="TABLE", container="SUB_PARTS", marking="SCHEME",
      subjects=("science",), aliases=("OBSERVATION BASED", "OBSERVATION TABLE"),
      brief="A short observation table from an experiment (substance/condition | observation), then sub-questions that interpret it, with marks per part.",
      example="A student heated four substances.\n| Substance | Observation on heating |\n| A | Melted, then solidified on cooling |\n| B | Burned with a bright flame, left white ash |\n| C | No change |\n| D | Gave off a gas that turned lime water milky |\n(i) Which substances underwent a chemical change? Give a reason. (2)\n(ii) Identify the gas released by substance D. (1)",
      answer="(i) B and D — new substances formed. (ii) Carbon dioxide"),
]
