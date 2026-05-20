from io import BytesIO

from apps.documents.models import DocumentChunk, PdfSource
from django.db import transaction
from docx import Document as DocxDocument

from services.chunking_service import chunk_pages, chunk_text
from services.embedding_service import generate_embeddings
from services.pdf_service import extract_text_from_pdf


def _extract_text_from_docx(buffer: bytes) -> str:
    doc = DocxDocument(BytesIO(buffer))
    return "\n".join(p.text for p in doc.paragraphs)


def process_pdf_upload(file, user) -> PdfSource:
    """
    Upload and process a PDF/DOCX/TXT file into a PdfSource.

    This creates a PdfSource with its DocumentChunks and embeddings so that
    questions can later be generated from it via semantic retrieval.

    PdfSource is a temporary generation context — it is NOT automatically
    linked to the Question Bank or any Paper. Questions become persistent only
    when the user explicitly saves them.
    """
    file_type = file.content_type or "text/plain"
    file_name = file.name
    buffer = file.read()

    extracted_text = ""
    pages = []

    if file_type == "application/pdf":
        pdf_data = extract_text_from_pdf(buffer)
        extracted_text = pdf_data.get("text", "")
        pages = pdf_data.get("pages", [])
    elif (
        file_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        extracted_text = _extract_text_from_docx(buffer)
    else:
        extracted_text = buffer.decode("utf-8", errors="ignore")

    if not extracted_text.strip():
        raise ValueError("Failed to extract text from document")

    with transaction.atomic():
        pdf_source = PdfSource.objects.create(
            name=file_name,
            size=len(buffer),
            status="processing",
            user=user,
        )

        try:
            chunks = chunk_pages(pages) if pages else chunk_text(extracted_text)

            batch_size = 50
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                embeddings = generate_embeddings(
                    [chunk.content for chunk in batch], user=user
                )

                DocumentChunk.objects.bulk_create(
                    [
                        DocumentChunk(
                            content=chunk.content,
                            page=chunk.page,
                            chunk_index=chunk.chunk_index,
                            embedding=embedding,
                            pdf_source=pdf_source,
                        )
                        for chunk, embedding in zip(batch, embeddings)
                    ]
                )

            pdf_source.status = "ready"
            pdf_source.save(update_fields=["status", "updated_at"])

        except Exception as exc:
            pdf_source.status = "error"
            pdf_source.error = str(exc)
            pdf_source.save(update_fields=["status", "error", "updated_at"])
            raise

    return pdf_source
