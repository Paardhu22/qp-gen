"""End-to-end ingestion profiler.

Phase-by-phase timings on a real PDF so we can identify the bottleneck
from numbers, not hypotheses.

Run from backend/:
    source .venv/bin/activate
    python scratch/profile_ingestion.py /home/paardhu/Downloads/trignometry.pdf

Cost guard: image captioning is ~$0.001 / call on gpt-5-mini and we
exercise ONE real call only. Embeddings cost ~$0.0001 per batch of 50.
The full pipeline budget is well under $0.01 per invocation.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Bootstrap Django so the services modules import cleanly.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from services.pdf_service import extract_text_from_pdf  # noqa: E402
from services.semantic_pipeline import process_semantic_pipeline  # noqa: E402
from services.chunking_service import chunk_text  # noqa: E402
from services.embedding_service import generate_embeddings  # noqa: E402
from services.openai_service import caption_image_for_embedding  # noqa: E402
from services.document_service import _is_usable_image, _image_data_url  # noqa: E402
from django.conf import settings  # noqa: E402


class Phase:
    def __init__(self, label):
        self.label = label
        self.start = 0.0
        self.end = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_args):
        self.end = time.perf_counter()
        print(f"  {self.label:<40} {self.ms:>10.1f} ms")

    @property
    def ms(self) -> float:
        return (self.end - self.start) * 1000.0


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument(
        "--sample-captions",
        type=int,
        default=1,
        help="How many real vision-API caption calls to make (0 = none, "
        "1 = one for per-call latency, > 1 = stress test).",
    )
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found")
        return 1

    print(f"\nProfiling {pdf_path.name} ({pdf_path.stat().st_size / 1024:.0f} KB)")
    print(f"OPENAI_MODEL={settings.OPENAI_MODEL}")
    print(f"OPENAI_EMBEDDING_MODEL={settings.OPENAI_EMBEDDING_MODEL}")
    print(f"PDF_IMAGE_MAX_CAPTIONS={getattr(settings, 'PDF_IMAGE_MAX_CAPTIONS', 40)}")
    print()

    # ── 1. File read ────────────────────────────────────────────────────
    with Phase("File read") as p_read:
        buffer = pdf_path.read_bytes()
    print(f"      buffer={len(buffer)} bytes")

    # ── 2. PyMuPDF extraction ───────────────────────────────────────────
    with Phase("PyMuPDF extract_text_from_pdf") as p_extract:
        pdf_data = extract_text_from_pdf(buffer)
    pages = pdf_data.get("pages") or []
    images = pdf_data.get("images") or []
    text = pdf_data.get("text") or ""
    print(
        f"      pages={len(pages)} images={len(images)} "
        f"text_chars={len(text)}"
    )

    # ── 3. Semantic chunking ────────────────────────────────────────────
    with Phase("Semantic chunking pipeline") as p_chunk:
        if pages:
            chunks = process_semantic_pipeline(pages)
        else:
            chunks = chunk_text(text)
    print(f"      chunks={len(chunks)}")

    # ── 4. Image captioning ── potentially the bottleneck ──────────────
    caption_limit = getattr(settings, "PDF_IMAGE_MAX_CAPTIONS", 40)
    usable_images = [img for img in images if _is_usable_image(img)][:caption_limit]
    print(f"\n  Images: total={len(images)} usable_after_cap={len(usable_images)}")

    per_image_ms = 0.0
    if args.sample_captions > 0 and usable_images:
        sample = usable_images[: args.sample_captions]
        with Phase(
            f"Captioning {len(sample)} image(s) SERIAL"
        ) as p_caption_sample:
            for image in sample:
                page_text = next(
                    (
                        str(p.get("content") or "")
                        for p in pages
                        if p.get("pageNumber") == image.get("pageNumber")
                    ),
                    "",
                )
                try:
                    caption_image_for_embedding(
                        _image_data_url(image),
                        page_context=page_text,
                        user=None,
                    )
                except Exception as exc:
                    print(f"      caption FAILED: {exc}")
                    break
        if len(sample):
            per_image_ms = p_caption_sample.ms / len(sample)
            projected_total = per_image_ms * len(usable_images)
            print(
                f"      per_image={per_image_ms:.0f} ms — "
                f"projected SERIAL total for {len(usable_images)} images = "
                f"{projected_total / 1000:.1f} s"
            )

    # ── 5. Embedding (just one batch to measure latency) ────────────────
    if chunks:
        first_batch = chunks[: min(50, len(chunks))]
        with Phase(
            f"Embedding 1 batch of {len(first_batch)} chunks"
        ) as p_embed:
            try:
                generate_embeddings(
                    [chunk.content for chunk in first_batch], user=None
                )
            except Exception as exc:
                print(f"      embedding FAILED: {exc}")
        batches = (len(chunks) + 49) // 50
        projected_embed_ms = p_embed.ms * batches
        print(
            f"      batches_needed={batches} — projected total = "
            f"{projected_embed_ms / 1000:.2f} s"
        )

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    print(
        f"  TOTAL extract+chunk = "
        f"{(p_read.ms + p_extract.ms + p_chunk.ms) / 1000:.2f} s"
    )
    if per_image_ms > 0:
        print(
            "  PROJECTED full ingestion with current SERIAL captioning ≈ "
            f"{(p_extract.ms + p_chunk.ms + per_image_ms * len(usable_images) + p_embed.ms * batches) / 1000:.1f} s"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
