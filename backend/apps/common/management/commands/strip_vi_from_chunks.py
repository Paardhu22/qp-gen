"""One-time cleanup: strip embedded VI-alternate blocks from stored chunks.

Chunks ingested before the round-4 fix can still carry "Visually Impaired
Students only" blocks copied from CBSE sample papers / HSAT books; those
blocks leak into generated papers through retrieval. New ingests are clean
(document_service strips at extraction) — this command repairs the rows
that already exist.

Usage:
    python manage.py strip_vi_from_chunks            # apply
    python manage.py strip_vi_from_chunks --dry-run  # report only

Note: the chunk's embedding is left as-is. The VI note is a few tokens of
boilerplate inside an otherwise on-topic chunk, so re-embedding is not
worth an OpenAI pass; what matters is that the TEXT handed to the LLM is
clean.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.documents.models import DocumentChunk
from services.content_filters import strip_vi_blocks


class Command(BaseCommand):
    help = "Strip embedded Visually-Impaired alternate blocks from stored DocumentChunks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report affected chunks without writing changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        candidates = DocumentChunk.objects.filter(
            Q(content__icontains="visually impaired")
            | Q(content__icontains="visual-impaired")
            | Q(content__icontains="in lieu of the visual")
        )
        total = candidates.count()
        changed = 0
        for chunk in candidates.iterator(chunk_size=200):
            cleaned = strip_vi_blocks(chunk.content)
            if cleaned == chunk.content:
                continue
            changed += 1
            if dry_run:
                self.stdout.write(
                    f"would clean chunk {chunk.pk} "
                    f"(pdf={chunk.pdf_source_id} hsat={chunk.hsat_source_id}, "
                    f"{len(chunk.content)} -> {len(cleaned)} chars)"
                )
                continue
            chunk.content = cleaned
            chunk.save(update_fields=["content"])
        verb = "would clean" if dry_run else "cleaned"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {changed} of {total} candidate chunk(s) containing VI text."
            )
        )
