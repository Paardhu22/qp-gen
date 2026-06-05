"""Side-by-side extraction quality: PyMuPDF (incumbent) vs markitdown.

Decision rule from the brief:
* If extraction dumps look CLEAN with PyMuPDF, markitdown adds nothing.
* If math/special chars are mangled, run markitdown and compare.

Cluster B's dump showed PyMuPDF DROPS most math symbols (no √ / π / ²)
and smashes formulae across newlines, so we run the comparison here.

Run from backend/:
    source .venv/bin/activate
    python scratch/eval_markitdown.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from services.pdf_service import extract_text_from_pdf  # noqa: E402

PDFS = [
    "/home/paardhu/Downloads/trignometry.pdf",
    "/home/paardhu/Downloads/MathsStandard-SQP.pdf",
    "/home/paardhu/Downloads/surfaceareavol.pdf",
]


def readability_signals(text: str) -> dict:
    return {
        "chars": len(text),
        "sqrt_chars": text.count("√"),
        "pi_chars": text.count("π"),
        "sup_2": text.count("²"),
        "subscript_digits": sum(1 for c in text if c in "₀₁₂₃₄₅₆₇₈₉"),
        "mcq_a_paren": text.count("(A)") + text.count("(a)"),
        "mcq_d_paren": text.count("(D)") + text.count("(d)"),
        "left_paren_A": text.count("(A)"),
        "left_paren_B": text.count("(B)"),
        "n_dot_pattern": sum(1 for l in text.splitlines() if l.lstrip()[:3] in {"1. ", "2. ", "3. ", "33.", "32.", "35."}),
        "tag_markdown_header": text.count("# "),
        "tag_table": text.count("|"),
    }


def main() -> int:
    from markitdown import MarkItDown

    md = MarkItDown()

    for pdf in PDFS:
        path = Path(pdf)
        print("\n" + "=" * 80)
        print(f"FILE: {path.name} ({path.stat().st_size / 1024:.0f} KB)")
        print("=" * 80)

        buffer = path.read_bytes()

        t = time.perf_counter()
        pymupdf_text = (extract_text_from_pdf(buffer).get("text") or "")
        pymupdf_ms = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        try:
            mk_result = md.convert(str(path))
            mk_text = mk_result.text_content or ""
        except Exception as exc:
            print(f"markitdown FAILED: {exc}")
            mk_text = ""
        mk_ms = (time.perf_counter() - t) * 1000

        py_sig = readability_signals(pymupdf_text)
        mk_sig = readability_signals(mk_text)

        print(f"PyMuPDF:    {pymupdf_ms:>6.0f} ms  {py_sig}")
        print(f"markitdown: {mk_ms:>6.0f} ms  {mk_sig}")

        # First chunk of each, side-by-side, to eyeball formula handling
        print("\n--- PyMuPDF first 500 chars ---")
        print(pymupdf_text[:500].replace("\n", "⏎ ").strip()[:500])
        print("\n--- markitdown first 500 chars ---")
        print(mk_text[:500].replace("\n", "⏎ ").strip()[:500])

        # Find specific landmarks and show how each renders the surrounding 200 chars
        landmarks = ["63 km", "Aryan", "BPT", "India Gate", "frustum", "π"]
        for needle in landmarks:
            in_py = needle.lower() in pymupdf_text.lower()
            in_mk = needle.lower() in mk_text.lower()
            print(f"\nLandmark {needle!r}: pymupdf={'✓' if in_py else '·'}  markitdown={'✓' if in_mk else '·'}")
            if in_mk:
                idx = mk_text.lower().find(needle.lower())
                snippet = mk_text[max(0, idx - 60) : idx + 140].replace("\n", "⏎ ")
                print(f"  markitdown context: ...{snippet}...")
            if in_py:
                idx = pymupdf_text.lower().find(needle.lower())
                snippet = pymupdf_text[max(0, idx - 60) : idx + 140].replace("\n", "⏎ ")
                print(f"  pymupdf context:    ...{snippet}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
