"""Dump the extracted text + chunked content for the three uploaded PDFs.

This proves Cluster B item 2 (extraction quality audit) and item 3 (chunking
boundary check) with primary evidence rather than guesses.

Run from backend/:
    source .venv/bin/activate
    python scratch/dump_extraction.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from services.pdf_service import extract_text_from_pdf  # noqa: E402
from services.semantic_pipeline import process_semantic_pipeline  # noqa: E402


PDFS = [
    "/home/paardhu/Downloads/trignometry.pdf",
    "/home/paardhu/Downloads/MathsStandard-SQP.pdf",
    "/home/paardhu/Downloads/surfaceareavol.pdf",
]


def summarise(text: str) -> dict:
    """Compute coarse readability signals so we can compare before/after
    of any extractor swap."""
    return {
        "chars": len(text),
        "has_sqrt": "√" in text,
        "has_pi": "π" in text,
        "has_superscript_2": "²" in text,
        "has_subscript": any(c in text for c in "₀₁₂₃₄₅₆₇₈₉ₐ"),
        "mcq_a_paren": text.count("(A)") + text.count("(a)"),
        "mcq_d_paren": text.count("(D)") + text.count("(d)"),
        "question_n_periods": sum(1 for line in text.splitlines() if line.lstrip().startswith(("1.", "2.", "3.", "Q1", "Q2"))),
        "section_a": "Section A" in text or "SECTION A" in text or "Section-A" in text,
    }


def main() -> int:
    for pdf in PDFS:
        path = Path(pdf)
        if not path.exists():
            print(f"SKIP missing: {pdf}")
            continue

        print(f"\n{'=' * 76}")
        print(f"FILE: {path.name} ({path.stat().st_size / 1024:.0f} KB)")
        print("=" * 76)
        buffer = path.read_bytes()
        data = extract_text_from_pdf(buffer)
        text = data.get("text") or ""
        pages = data.get("pages") or []
        chunks = process_semantic_pipeline(pages) if pages else []

        signals = summarise(text)
        print(
            "Readability signals:",
            ", ".join(f"{k}={v}" for k, v in signals.items()),
        )
        print(f"Pages: {len(pages)}  Chunks: {len(chunks)}")

        # Dump first 400 chars of every page (or fewer for short pages) — this
        # is what the embedding model actually sees pre-chunking.
        print("\n-- First 600 chars of page 1 --")
        if pages:
            print((pages[0].get("content") or "")[:600])

        # Find specific landmark questions the user mentioned (SQP Q32 train,
        # Q33 BPT, Q35 grouped freq, Q38 India Gate).
        landmarks = [
            ("train_keyword", "train"),
            ("bpt", "BPT"),
            ("basic_proportionality", "Basic Proportionality"),
            ("india_gate", "India Gate"),
            ("monthly_income", "monthly income"),
            ("grouped_frequency", "grouped frequency"),
            ("63 km", "63 km"),
            ("Q32", "32."),
            ("Q33", "33."),
            ("Q35", "35."),
            ("Q38", "38."),
        ]
        print("\nLandmark presence (substring match):")
        for label, needle in landmarks:
            present = needle.lower() in text.lower()
            print(f"  {label:<24} {'✓' if present else '·'}  needle={needle!r}")

        # For each landmark FOUND, show which chunk contains it — if SQP Q32
        # spans two chunks, retrieval will be split and dedup-starved later.
        for label, needle in landmarks:
            if needle.lower() not in text.lower():
                continue
            matched = [
                (idx, ck) for idx, ck in enumerate(chunks)
                if needle.lower() in ck.content.lower()
            ]
            for idx, ck in matched[:1]:
                page = ck.page
                head = ck.content[:200].replace("\n", " ")
                print(
                    f"\n  CHUNK CONTAINING {needle!r}: idx={idx} page={page}"
                )
                print(f"    head: {head}…")

    return 0


if __name__ == "__main__":
    sys.exit(main())
