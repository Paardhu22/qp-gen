"""Embed the three PDFs in-memory and run landmark retrieval queries to
quantify scores and confirm the dedup-exhaustion hypothesis.

No DB writes. Heavy operations are batched embedding calls only.

Run from backend/:
    source .venv/bin/activate
    python scratch/probe_retrieval.py
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

import math  # noqa: E402

from services.pdf_service import extract_text_from_pdf  # noqa: E402
from services.semantic_pipeline import process_semantic_pipeline  # noqa: E402
from services.embedding_service import generate_embeddings  # noqa: E402


PDFS = {
    "trignometry.pdf": "/home/paardhu/Downloads/trignometry.pdf",
    "MathsStandard-SQP.pdf": "/home/paardhu/Downloads/MathsStandard-SQP.pdf",
    "surfaceareavol.pdf": "/home/paardhu/Downloads/surfaceareavol.pdf",
}

# Landmark queries the user cited as "match the SQP source verbatim"
QUERIES = [
    ("Q32_train", "train traveling 63 km constant speed Maths class 10 LONG_ANSWER 5 mark"),
    ("Q33_BPT", "Basic Proportionality Theorem prove parallel line triangle Maths class 10 LONG_ANSWER"),
    ("Q35_grouped_freq", "mode median grouped frequency distribution class interval Maths class 10 LONG_ANSWER"),
    ("Q38_India_Gate", "India Gate height angle elevation depression trigonometry Maths class 10 5 mark"),
    ("Q31_monthly_income", "monthly income ratio savings expenditure linear equations Maths class 10 LONG_ANSWER"),
    ("Q22_prob_dice", "probability die rolled sum favourable outcomes Maths class 10 SHORT"),
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def l2(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def main() -> int:
    all_chunks = []
    chunk_meta = []  # (source_name, chunk_index, content)
    for name, path in PDFS.items():
        buffer = Path(path).read_bytes()
        data = extract_text_from_pdf(buffer)
        pages = data.get("pages") or []
        chunks = process_semantic_pipeline(pages) if pages else []
        for c in chunks:
            all_chunks.append(c.content)
            chunk_meta.append((name, c.chunk_index, c.content))
    print(f"Total chunks across 3 PDFs: {len(all_chunks)}")

    print("\nEmbedding all chunks (batched)...")
    chunk_embeddings = []
    for i in range(0, len(all_chunks), 50):
        chunk_embeddings.extend(generate_embeddings(all_chunks[i : i + 50]))
    print(f"  {len(chunk_embeddings)} embeddings")

    print("\nEmbedding queries...")
    query_embeddings = generate_embeddings([q for _, q in QUERIES])

    print("\nTop-3 retrieval per landmark query:")
    for (label, query), q_emb in zip(QUERIES, query_embeddings):
        scored = []
        for i, c_emb in enumerate(chunk_embeddings):
            scored.append((l2(q_emb, c_emb), 1 - l2(q_emb, c_emb), i))
        scored.sort(key=lambda r: r[0])
        print(f"\n[{label}] query={query[:80]!r}")
        for rank, (l2_dist, similarity, idx) in enumerate(scored[:3]):
            src, ck_idx, content = chunk_meta[idx]
            head = content[:120].replace("\n", " ")
            print(
                f"  rank={rank + 1}  src={src}  chunk={ck_idx}  "
                f"L2={l2_dist:.4f}  sim={similarity:.4f}"
            )
            print(f"    head: {head}…")

    # The dedup-exhaustion claim: simulate ~38 slot retrievals (one per
    # question in a CBSE Standard paper) with strict per-chunk dedup.
    print("\n--- DEDUP SIMULATION ---")
    print(
        "Cycling through ~38 distinct slot queries with strict dedup; "
        "report at which slot the chunk pool starves."
    )

    slot_topics = [
        "linear pair of equations word problem age",
        "real numbers prime factorisation HCF LCM",
        "polynomial zeros relationship coefficients",
        "quadratic equation discriminant roots",
        "arithmetic progression common difference sum",
        "triangle similarity proportion",
        "Basic Proportionality Theorem",
        "Pythagoras theorem proof",
        "coordinate geometry distance formula",
        "section formula midpoint",
        "trigonometric ratios sine cosine angle",
        "height distance trigonometry application",
        "circle tangent length chord",
        "area sector circle major minor",
        "surface area combined solid",
        "volume frustum cone",
        "statistics mean median mode",
        "frequency distribution class interval",
        "probability die rolled favourable",
        "probability card drawn deck",
        "MCQ HCF of two numbers",
        "MCQ AP nth term",
        "MCQ trigonometric identity",
        "MCQ quadratic discriminant",
        "MCQ probability bag balls",
        "Assertion Reason similar triangles",
        "very short answer 2 marks volume sphere",
        "very short answer 2 marks AP sum",
        "long answer 5 marks word problem train",
        "long answer 5 marks angle elevation depression",
        "long answer 5 marks Indian flag",
        "case study water tank",
        "case study coordinate geometry",
        "case study probability spinner",
        "monthly income ratio Aryan Babban",
        "prove BPT triangle parallel line",
        "mode grouped distribution class interval",
        "India Gate angle elevation",
    ]
    slot_embeddings = generate_embeddings(slot_topics)
    used = set()
    chunk_use_count = {}
    fallback_indices = []
    for i, q_emb in enumerate(slot_embeddings):
        scored = sorted(
            [(l2(q_emb, e), idx) for idx, e in enumerate(chunk_embeddings)]
        )
        # strict per-chunk dedup
        fresh = [idx for _, idx in scored if idx not in used][:4]
        if not fresh:
            fallback_indices.append(i)
        else:
            for idx in fresh:
                used.add(idx)
                chunk_use_count[idx] = chunk_use_count.get(idx, 0) + 1
    print(
        f"Total slots simulated: {len(slot_topics)}  "
        f"Curriculum_fallback slots: {len(fallback_indices)}  "
        f"({len(fallback_indices) * 100 / len(slot_topics):.0f}%)"
    )
    print(f"First fallback at slot index: {fallback_indices[0] if fallback_indices else 'n/a'}")

    # Loose-dedup simulation: allow each chunk to ground up to 3 slots
    used2 = {}
    fallback_indices2 = []
    for i, q_emb in enumerate(slot_embeddings):
        scored = sorted(
            [(l2(q_emb, e), idx) for idx, e in enumerate(chunk_embeddings)]
        )
        fresh = [idx for _, idx in scored if used2.get(idx, 0) < 3][:4]
        if not fresh:
            fallback_indices2.append(i)
        else:
            for idx in fresh:
                used2[idx] = used2.get(idx, 0) + 1
    print(
        f"With MAX_REUSES=3:  Curriculum_fallback slots: "
        f"{len(fallback_indices2)} ({len(fallback_indices2) * 100 / len(slot_topics):.0f}%)"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
