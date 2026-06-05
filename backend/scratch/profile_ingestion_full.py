"""Full end-to-end ingestion timing — after the parallel-captioning fix.

Runs the SAME pipeline a real upload triggers, captures wall-clock per phase,
captions ALL usable images via the new ThreadPool path, embeds all chunks,
and skips the DB write so we can verify on the production-pointed DB without
inserting test rows.

Run from backend/:
    source .venv/bin/activate
    python scratch/profile_ingestion_full.py /home/paardhu/Downloads/trignometry.pdf
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from django.conf import settings  # noqa: E402

from services.pdf_service import extract_text_from_pdf  # noqa: E402
from services.semantic_pipeline import process_semantic_pipeline  # noqa: E402
from services.chunking_service import chunk_text  # noqa: E402
from services.embedding_service import generate_embeddings  # noqa: E402
from services.openai_service import caption_image_for_embedding  # noqa: E402
from services.document_service import (  # noqa: E402
    _is_usable_image,
    _image_data_url,
)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    print(f"\nProfiling {pdf_path.name} ({pdf_path.stat().st_size / 1024:.0f} KB)")
    print(f"OPENAI_VISION_MODEL={getattr(settings, 'OPENAI_VISION_MODEL', settings.OPENAI_MODEL)}")
    print(f"PDF_IMAGE_CAPTION_CONCURRENCY={settings.PDF_IMAGE_CAPTION_CONCURRENCY}")
    print()

    wall_start = time.perf_counter()
    timings = {}

    def time_phase(label, fn):
        t = time.perf_counter()
        result = fn()
        timings[label] = (time.perf_counter() - t) * 1000.0
        print(f"  {label:<40} {timings[label]:>10.1f} ms")
        return result

    # 1. File read
    buffer = time_phase("File read", lambda: pdf_path.read_bytes())
    print(f"      buffer={len(buffer)} bytes")

    # 2. Extraction
    pdf_data = time_phase("PyMuPDF extract_text_from_pdf",
                          lambda: extract_text_from_pdf(buffer))
    pages = pdf_data.get("pages") or []
    images = pdf_data.get("images") or []
    text = pdf_data.get("text") or ""
    print(f"      pages={len(pages)} images={len(images)} text_chars={len(text)}")

    # 3. Chunking
    chunks = time_phase(
        "Semantic chunking pipeline",
        lambda: process_semantic_pipeline(pages) if pages else chunk_text(text),
    )
    print(f"      chunks={len(chunks)}")

    # 4. Parallel captioning (new)
    usable = [img for img in images if _is_usable_image(img)][: settings.PDF_IMAGE_MAX_CAPTIONS]
    print(f"\n  Images: usable={len(usable)}")
    page_text_map = {p.get("pageNumber"): str(p.get("content") or "") for p in pages}

    def caption_one(image):
        try:
            return caption_image_for_embedding(
                _image_data_url(image),
                page_context=page_text_map.get(int(image.get("pageNumber") or 0), ""),
                user=None,
            )
        except Exception as exc:
            return f"<fallback> {exc}"

    if usable:
        t_caption_start = time.perf_counter()
        with ThreadPoolExecutor(
            max_workers=min(settings.PDF_IMAGE_CAPTION_CONCURRENCY, len(usable))
        ) as ex:
            captions = list(ex.map(caption_one, usable))
        caption_ms = (time.perf_counter() - t_caption_start) * 1000.0
        timings["Parallel image captioning"] = caption_ms
        print(
            f"  {'Parallel image captioning':<40} {caption_ms:>10.1f} ms "
            f"(per-image avg {caption_ms / len(usable):.0f} ms)"
        )
        fallbacks = sum(1 for c in captions if c.startswith("<fallback>"))
        if fallbacks:
            print(f"      fallbacks={fallbacks}/{len(usable)}")

    # 5. Embedding (batched 50 at a time, like real code)
    if chunks:
        t_embed_start = time.perf_counter()
        for i in range(0, len(chunks), 50):
            batch = chunks[i : i + 50]
            try:
                generate_embeddings([c.content for c in batch], user=None)
            except Exception as exc:
                print(f"      embedding FAILED: {exc}")
        embed_ms = (time.perf_counter() - t_embed_start) * 1000.0
        timings["Embedding all batches"] = embed_ms
        print(f"  {'Embedding all batches':<40} {embed_ms:>10.1f} ms")

    wall_ms = (time.perf_counter() - wall_start) * 1000.0
    print()
    print(f"  TOTAL wall time: {wall_ms / 1000:.2f} s")
    print(
        f"  Breakdown: "
        + ", ".join(f"{k}={v / 1000:.2f}s" for k, v in timings.items())
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
