"""
AOS Hindi Course B — Bloom's Taxonomy Engine
==============================================
Cognitive demands and action verbs for CBSE Class 10 Hindi Course B.
Hindi Bloom's labels in parentheses for teacher reference.
"""

from typing import Dict, Set

from q_instructions.core.enums import BloomsLevel, StreamType
from q_instructions.core.datatypes import BloomsVerb, BloomsTaxonomyProfile

_ALL = {StreamType.INTEGRATED}


class HindiBloomsTaxonomyEngine:
    """Bloom's taxonomy profiles with Hindi-specific verb bindings."""

    def __init__(self) -> None:
        self._profiles: Dict[BloomsLevel, BloomsTaxonomyProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._profiles[BloomsLevel.REMEMBER] = BloomsTaxonomyProfile(
            level=BloomsLevel.REMEMBER,
            cognitive_weight_index=1.0,
            action_verbs=[
                BloomsVerb("पहचानना", _ALL, "दिए गए वाक्य में समास का भेद पहचानिए।"),
                BloomsVerb("याद करना", _ALL, "मुहावरे का अर्थ लिखिए।"),
                BloomsVerb("सूचीबद्ध करना", _ALL, "पाठ में उल्लिखित पात्रों के नाम लिखिए।"),
            ],
            difficulty_coefficient_range=(0.1, 0.35),
            description="स्मृति परीक्षण — पाठ के तथ्य, व्याकरण-नियम, एवं शब्द-अर्थ।",
        )

        self._profiles[BloomsLevel.UNDERSTAND] = BloomsTaxonomyProfile(
            level=BloomsLevel.UNDERSTAND,
            cognitive_weight_index=2.0,
            action_verbs=[
                BloomsVerb("समझाना", _ALL, "गद्यांश का केंद्रीय भाव समझाइए।"),
                BloomsVerb("व्याख्या करना", _ALL, "कविता की पंक्तियों की सप्रसंग व्याख्या कीजिए।"),
                BloomsVerb("स्पष्ट करना", _ALL, "लेखक के कहने का आशय स्पष्ट कीजिए।"),
            ],
            difficulty_coefficient_range=(0.3, 0.55),
            description="बोध परीक्षण — अर्थ, भाव, और संदेश की समझ।",
        )

        self._profiles[BloomsLevel.APPLY] = BloomsTaxonomyProfile(
            level=BloomsLevel.APPLY,
            cognitive_weight_index=3.5,
            action_verbs=[
                BloomsVerb("लिखना", _ALL, "प्रधानाचार्य को प्रार्थना-पत्र लिखिए।"),
                BloomsVerb("रूपांतरित करना", _ALL, "सरल वाक्य को मिश्र वाक्य में रूपांतरित कीजिए।"),
                BloomsVerb("प्रयोग करना", _ALL, "दिए गए मुहावरे का वाक्य में प्रयोग कीजिए।"),
            ],
            difficulty_coefficient_range=(0.5, 0.72),
            description="अनुप्रयोग परीक्षण — व्याकरण-नियम और लेखन-कौशल का उपयोग।",
        )

        self._profiles[BloomsLevel.ANALYZE] = BloomsTaxonomyProfile(
            level=BloomsLevel.ANALYZE,
            cognitive_weight_index=4.8,
            action_verbs=[
                BloomsVerb("विश्लेषण करना", _ALL, "लेखक की भाषा-शैली का विश्लेषण कीजिए।"),
                BloomsVerb("तुलना करना", _ALL, "दो पात्रों के स्वभाव की तुलना कीजिए।"),
                BloomsVerb("परखना", _ALL, "कविता में प्रयुक्त बिम्ब-विधान को परखिए।"),
            ],
            difficulty_coefficient_range=(0.6, 0.83),
            description="विश्लेषण परीक्षण — पाठ के तत्वों को अलग कर उनका अध्ययन।",
        )

        self._profiles[BloomsLevel.EVALUATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.EVALUATE,
            cognitive_weight_index=5.5,
            action_verbs=[
                BloomsVerb("मूल्यांकन करना", _ALL, "कहानी के अंत की सार्थकता पर अपना मत व्यक्त कीजिए।"),
                BloomsVerb("समालोचना करना", _ALL, "कविता के सामाजिक संदेश का मूल्यांकन कीजिए।"),
                BloomsVerb("न्याय करना", _ALL, "पात्र के निर्णय की उचितता पर विचार कीजिए।"),
            ],
            difficulty_coefficient_range=(0.7, 0.92),
            description="मूल्यांकन परीक्षण — साहित्यिक निर्णयों और सामाजिक संदेशों का आकलन।",
        )

        self._profiles[BloomsLevel.CREATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.CREATE,
            cognitive_weight_index=6.0,
            action_verbs=[
                BloomsVerb("रचना करना", _ALL, "दिए गए विषय पर एक सारगर्भित अनुच्छेद लिखिए।"),
                BloomsVerb("निर्माण करना", _ALL, "दिए गए संकेत-बिन्दुओं के आधार पर विज्ञापन बनाइए।"),
                BloomsVerb("सृजन करना", _ALL, "दिए गए पहले वाक्य से आगे लघुकथा लिखिए।"),
            ],
            difficulty_coefficient_range=(0.8, 1.0),
            description="सृजन परीक्षण — मौलिक लेखन: अनुच्छेद, पत्र, विज्ञापन, लघुकथा।",
        )

    def get_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        if level not in self._profiles:
            raise KeyError(f"Bloom's level {level.name} not registered for Hindi.")
        return self._profiles[level]
