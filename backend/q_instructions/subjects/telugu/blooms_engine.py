"""
AOS Telugu Telangana — Bloom's Taxonomy Engine
================================================
Cognitive demands and action verbs for CBSE Class 10 Telugu Telangana.
ALL labels and verbs in Telugu Unicode script.
"""

from typing import Dict, Set

from q_instructions.core.enums import BloomsLevel, StreamType
from q_instructions.core.datatypes import BloomsVerb, BloomsTaxonomyProfile

_ALL = {StreamType.INTEGRATED}


class TeluguBloomsTaxonomyEngine:
    """Bloom's taxonomy profiles with Telugu-specific verb bindings."""

    def __init__(self) -> None:
        self._profiles: Dict[BloomsLevel, BloomsTaxonomyProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        self._profiles[BloomsLevel.REMEMBER] = BloomsTaxonomyProfile(
            level=BloomsLevel.REMEMBER,
            cognitive_weight_index=1.0,
            action_verbs=[
                BloomsVerb("గుర్తించు", _ALL, "ఇచ్చిన పదానికి సంధి భేదాన్ని గుర్తించండి."),
                BloomsVerb("చెప్పు", _ALL, "ఇచ్చిన సమాసపదం యొక్క విగ్రహవాక్యం చెప్పండి."),
                BloomsVerb("జాబితా చేయు", _ALL, "పాఠంలోని ముఖ్యపాత్రల పేర్లు జాబితా చేయండి."),
            ],
            difficulty_coefficient_range=(0.1, 0.35),
            description="జ్ఞాపక పరీక్ష — పాఠ్యాంశ వాస్తవాలు, వ్యాకరణ నియమాలు, శబ్దార్థాలు.",
        )

        self._profiles[BloomsLevel.UNDERSTAND] = BloomsTaxonomyProfile(
            level=BloomsLevel.UNDERSTAND,
            cognitive_weight_index=2.0,
            action_verbs=[
                BloomsVerb("వివరించు", _ALL, "గద్యాంశంలోని కేంద్రభావాన్ని వివరించండి."),
                BloomsVerb("వ్యాఖ్యానించు", _ALL, "ఇచ్చిన పద్యపాదాన్ని అన్వయించి వ్యాఖ్యానించండి."),
                BloomsVerb("అర్థం చెప్పు", _ALL, "సామెత అర్థం చెప్పండి."),
            ],
            difficulty_coefficient_range=(0.3, 0.55),
            description="అవగాహన పరీక్ష — అర్థం, భావం, సందేశం అర్థం చేసుకోవడం.",
        )

        self._profiles[BloomsLevel.APPLY] = BloomsTaxonomyProfile(
            level=BloomsLevel.APPLY,
            cognitive_weight_index=3.5,
            action_verbs=[
                BloomsVerb("రాయి", _ALL, "ఇచ్చిన సంఘటన ఆధారంగా దినచర్య రాయండి."),
                BloomsVerb("రచించు", _ALL, "ఆధారాలు ఉపయోగించి వార్తను రచించండి."),
                BloomsVerb("ఉపయోగించు", _ALL, "ఇచ్చిన జాతీయాన్ని వాక్యంలో ఉపయోగించండి."),
            ],
            difficulty_coefficient_range=(0.5, 0.72),
            description="అనువర్తన పరీక్ష — వ్యాకరణ నియమాలు మరియు రచనా నైపుణ్యాల ఉపయోగం.",
        )

        self._profiles[BloomsLevel.ANALYZE] = BloomsTaxonomyProfile(
            level=BloomsLevel.ANALYZE,
            cognitive_weight_index=4.8,
            action_verbs=[
                BloomsVerb("విశ్లేషించు", _ALL, "పాత్ర స్వభావాన్ని విశ్లేషించండి."),
                BloomsVerb("పోల్చు", _ALL, "రెండు పాత్రల స్వభావాలను పోల్చండి."),
                BloomsVerb("పరీక్షించు", _ALL, "పద్యంలో అలంకారాన్ని పరీక్షించండి."),
            ],
            difficulty_coefficient_range=(0.6, 0.83),
            description="విశ్లేషణ పరీక్ష — పాఠ్యాంశ భాగాలను వేరుచేసి అధ్యయనం.",
        )

        self._profiles[BloomsLevel.EVALUATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.EVALUATE,
            cognitive_weight_index=5.5,
            action_verbs=[
                BloomsVerb("మూల్యాంకనం చేయు", _ALL, "పాఠంలోని సామాజిక సందేశాన్ని మూల్యాంకనం చేయండి."),
                BloomsVerb("విమర్శించు", _ALL, "రచయిత దృక్పథాన్ని విమర్శనాత్మకంగా చర్చించండి."),
                BloomsVerb("నిర్ణయించు", _ALL, "పాత్ర నిర్ణయం సరైనదా కాదా నిర్ణయించండి."),
            ],
            difficulty_coefficient_range=(0.7, 0.92),
            description="మూల్యాంకన పరీక్ష — సాహిత్య నిర్ణయాలు మరియు సామాజిక సందేశాల అంచనా.",
        )

        self._profiles[BloomsLevel.CREATE] = BloomsTaxonomyProfile(
            level=BloomsLevel.CREATE,
            cognitive_weight_index=6.0,
            action_verbs=[
                BloomsVerb("రచించు", _ALL, "ఇచ్చిన అంశంపై వ్యాసం రచించండి."),
                BloomsVerb("నిర్మించు", _ALL, "ఇచ్చిన సంఘటనపై వార్తా నివేదిక నిర్మించండి."),
                BloomsVerb("సృష్టించు", _ALL, "ఇచ్చిన వాక్యంతో కథను సృష్టించండి."),
            ],
            difficulty_coefficient_range=(0.8, 1.0),
            description="సృజన పరీక్ష — లేఖలు, వ్యాసాలు, కథలు వంటి మౌలిక రచన.",
        )

    def get_profile(self, level: BloomsLevel) -> BloomsTaxonomyProfile:
        if level not in self._profiles:
            raise KeyError(f"Bloom's level {level.name} not registered for Telugu.")
        return self._profiles[level]
