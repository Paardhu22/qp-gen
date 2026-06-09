"""HSAT shared-textbook catalog.

Maps `(grade, subject, book) -> [S3 object keys]` for every NCERT/HSAT
textbook hosted in the shared bucket. The structure is intentionally a
plain nested dict so adding grade 9, 11, or 12 is a data-only change —
no other backend code needs to change.

Add a new grade by inserting another top-level key. Add a new book by
inserting it under the appropriate subject. The keys MUST match the
exact S3 object key (including spaces, accents, and odd punctuation),
because they are passed directly to `boto3.download_fileobj`.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

HSAT_CATALOG: Dict[str, Dict[str, Dict[str, List[str]]]] = {
    "10": {
        "English": {
            "First Flight": [
                'class 10/English/X - FIRST FLIGHT/CH1 -  A Letter to God.pdf',
                'class 10/English/X - FIRST FLIGHT/CH2 - Nelson MandelaLong Walk to Freedom.pdf',
                'class 10/English/X - FIRST FLIGHT/CH3 -  Two Stories about Flying.pdf',
                'class 10/English/X - FIRST FLIGHT/CH4 -  From the Diary of Anne Frank.pdf',
                'class 10/English/X - FIRST FLIGHT/CH5 - Glimpses of India.pdf',
                'class 10/English/X - FIRST FLIGHT/CH6 - Mijbil the Otter.pdf',
                'class 10/English/X - FIRST FLIGHT/CH7 -  Madam Rides the Bus.pdf',
                'class 10/English/X - FIRST FLIGHT/CH8 - The Sermon at Benares.pdf',
                'class 10/English/X - FIRST FLIGHT/CH9 - The Proposal.pdf',
            ],
            "Footprints Without Feet": [
                'class 10/English/X - Footprints without Feet/CH1 -   A Triumph of Surgery.pdf',
                'class 10/English/X - Footprints without Feet/CH2 - The Thief’s Stor.pdf',
                'class 10/English/X - Footprints without Feet/CH3 -  The Midnight Visitor.pdf',
                'class 10/English/X - Footprints without Feet/CH4 -  A Question of Trust.pdf',
                'class 10/English/X - Footprints without Feet/CH5 -  Footprints without Feet.pdf',
                'class 10/English/X - Footprints without Feet/CH6 - The Making of a Scientist.pdf',
                'class 10/English/X - Footprints without Feet/CH7 - The Necklace.pdf',
                'class 10/English/X - Footprints without Feet/CH8 -  Bholi.pdf',
                'class 10/English/X - Footprints without Feet/CH9 - The Book That Saved the Earth.pdf',
            ],
        },
        "Hindi": {
            "Kritika 2": [
                'class 10/Hindi/X - KRITIKA 2/CH1 - माता का आँचल.pdf',
                'class 10/Hindi/X - KRITIKA 2/CH2 - साना साना हाथ जोड़ी.pdf',
                'class 10/Hindi/X - KRITIKA 2/CH3 - मैं क्या लिखता हूं.pdf',
            ],
            "Kshitij 2": [
                'class 10/Hindi/X- KSHITIJ 2/CH1 - सूरदास.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH2 - तुलसीदास.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH3 - जय शंकर प्रसाद.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH4 - सूर्यकांत त्रिपाठी निराला.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH5 - नागार्जुन.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH6 - मंगलेश डबराल.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH7 - स्वयं प्रकाश.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH8 - रामबृक्ष बेनीपुरी.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH9 - यशपाल.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH10 - मन्नू भंडारी.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH11 - यतीन्द्र मिश्र.pdf',
                'class 10/Hindi/X- KSHITIJ 2/CH12 - भदंत आनंद कोसल्याण.pdf',
            ],
            "Sanchayan 2": [
                'class 10/Hindi/X - SANCHAYAN 2/CH1 - हरिहर काका.pdf',
                'class 10/Hindi/X - SANCHAYAN 2/CH2 - सपनों के- से दिन.pdf',
                'class 10/Hindi/X - SANCHAYAN 2/CH3 - टोपी शुक्ला.pdf',
            ],
            "Sparsh 2": [
                'class 10/Hindi/X - SPARSH 2/CH1 - कबीर.pdf',
                'class 10/Hindi/X - SPARSH 2/CH2 - मीरा.pdf',
                'class 10/Hindi/X - SPARSH 2/CH3 - मैथिलीशरण गुप्त.pdf',
                'class 10/Hindi/X - SPARSH 2/CH4 - सुमित्रानंद पंत.pdf',
                'class 10/Hindi/X - SPARSH 2/CH5 - वीरेन डंगवाल.pdf',
                'class 10/Hindi/X - SPARSH 2/CH6 - कैफ़ी आज़मी.pdf',
                'class 10/Hindi/X - SPARSH 2/CH7 - रवीन्द्रनाथ ठाकुर.pdf',
                'class 10/Hindi/X - SPARSH 2/CH8 - प्रेमचंद.pdf',
                'class 10/Hindi/X - SPARSH 2/CH9 - सीताराम सेकसरिया.pdf',
                'class 10/Hindi/X - SPARSH 2/CH10 - लीलाधर मंडलोई.pdf',
                'class 10/Hindi/X - SPARSH 2/CH11 - प्रहलादअग्रवाल.pdf',
                'class 10/Hindi/X - SPARSH 2/CH12 - निदा फाजली.pdf',
                'class 10/Hindi/X - SPARSH 2/CH13- रवीन्द्र केलेकर.pdf',
                'class 10/Hindi/X - SPARSH 2/CH14 - हबीब तनवीर.pdf',
            ],
        },
        "Mathematics": {
            "Mathematics": [
                'class 10/Maths/jemh101.pdf',
                'class 10/Maths/jemh102.pdf',
                'class 10/Maths/jemh103.pdf',
                'class 10/Maths/jemh104.pdf',
                'class 10/Maths/jemh105.pdf',
                'class 10/Maths/jemh106.pdf',
                'class 10/Maths/jemh107.pdf',
                'class 10/Maths/jemh108.pdf',
                'class 10/Maths/jemh109.pdf',
                'class 10/Maths/jemh110.pdf',
                'class 10/Maths/jemh111.pdf',
                'class 10/Maths/jemh112.pdf',
                'class 10/Maths/jemh113.pdf',
                'class 10/Maths/jemh114.pdf',
                'class 10/Maths/jemh1a1.pdf',
                'class 10/Maths/jemh1a2.pdf',
                'class 10/Maths/jemh1an.pdf',
                'class 10/Maths/jemh1ps.pdf',
            ],
        },
        "Science": {
            "Science": [
                'class 10/Science/CH1 -   Chemical Reactions and Equations.pdf',
                'class 10/Science/CH2 - Acids, Bases and Salts.pdf',
                'class 10/Science/CH3 - Metals and Non-metals.pdf',
                'class 10/Science/CH4 - Carbon and its Compounds.pdf',
                'class 10/Science/CH5 - Life Processes.pdf',
                'class 10/Science/CH6 - Control and Coordination.pdf',
                'class 10/Science/CH7 - How do Organisms Reproduce.pdf',
                'class 10/Science/CH8 - Heredity.pdf',
                'class 10/Science/CH9 - Light – Reflection and Refraction.pdf',
                'class 10/Science/CH10 - The Human Eye and the Colourful World.pdf',
                'class 10/Science/CH11 - Electricity.pdf',
                'class 10/Science/CH12 - Magnetic Effects of Electric Current.pdf',
                'class 10/Science/CH13 - Our Environment.pdf',
            ],
        },
        "Social Science": {
            "Contemporary India II": [
                'class 10/Social/X - Contemporary India -II/CH1 - Resources and Development.pdf',
                'class 10/Social/X - Contemporary India -II/CH2 - Forest and Wildlife Resources.pdf',
                'class 10/Social/X - Contemporary India -II/CH3 - Water Resources.pdf',
                'class 10/Social/X - Contemporary India -II/CH4 - Agriculture.pdf',
                'class 10/Social/X - Contemporary India -II/CH5 - Minerals and Energy Resources.pdf',
                'class 10/Social/X - Contemporary India -II/CH6 - Manufacturing Industries.pdf',
                'class 10/Social/X - Contemporary India -II/CH7 - Lifelines of National Economy.pdf',
            ],
            "Democratic Politics II": [
                'class 10/Social/X - Democratic Politics-II/CH1 - Power-sharing.pdf',
                'class 10/Social/X - Democratic Politics-II/CH2 - Federalism.pdf',
                'class 10/Social/X - Democratic Politics-II/CH3 - Gender, Religion and Caste.pdf',
                'class 10/Social/X - Democratic Politics-II/CH4 - Political Parties.pdf',
                'class 10/Social/X - Democratic Politics-II/CH5 - Outcomes of Democracy.pdf',
            ],
            "India and the Contemporary World II": [
                'class 10/Social/X - India and the Contemporary World – II/CH1 -  The Rise of Nationalism in Europe.pdf',
                'class 10/Social/X - India and the Contemporary World – II/CH2 -  Nationalism in India.pdf',
                'class 10/Social/X - India and the Contemporary World – II/CH3 -  The Making of a Global World.pdf',
                'class 10/Social/X - India and the Contemporary World – II/CH4 -  The Age of Industrialisation.pdf',
                'class 10/Social/X - India and the Contemporary World – II/CH5 -  Print Culture and the Modern World.pdf',
            ],
            "Understanding Economic Development": [
                'class 10/Social/X - Understanding Economic Development/CH1 - DEVELOPMENT.pdf',
                'class 10/Social/X - Understanding Economic Development/CH2 - SECTORS OF THE INDIAN ECONOMY.pdf',
                'class 10/Social/X - Understanding Economic Development/CH3 - MONEY AND CREDIT.pdf',
                'class 10/Social/X - Understanding Economic Development/CH4 - GLOBALISATION AND THE INDIAN ECONOMY.pdf',
                'class 10/Social/X - Understanding Economic Development/CH5 - CONSUMER RIGHTS.pdf',
            ],
        },
    },
}


def iter_books() -> Iterable[Tuple[str, str, str, List[str]]]:
    """Yield (grade, subject, book, [keys]) for every book in the catalog."""
    for grade, subjects in HSAT_CATALOG.items():
        for subject, books in subjects.items():
            for book, keys in books.items():
                yield grade, subject, book, list(keys)


def get_book_keys(grade: str, subject: str, book: str) -> List[str]:
    """Return the ordered list of S3 keys for one book, or [] if not found."""
    return list(
        HSAT_CATALOG.get(grade, {}).get(subject, {}).get(book, [])
    )


def book_exists(grade: str, subject: str, book: str) -> bool:
    return bool(get_book_keys(grade, subject, book))


def catalog_tree() -> Dict[str, Dict[str, List[str]]]:
    """Compact tree: {grade: {subject: [book, ...]}} for the UI selector."""
    return {
        grade: {subject: list(books.keys()) for subject, books in subjects.items()}
        for grade, subjects in HSAT_CATALOG.items()
    }
