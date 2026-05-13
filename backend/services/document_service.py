from typing import Optional

from django.db import transaction
from io import BytesIO

from docx import Document as DocxDocument

from apps.documents.models import Document, DocumentChunk
from services.chunking_service import chunk_pages, chunk_text
from services.embedding_service import generate_embeddings
from services.pdf_service import extract_text_from_pdf


def _extract_text_from_docx(buffer: bytes) -> str:
    doc = DocxDocument(BytesIO(buffer))
    return "\n".join(p.text for p in doc.paragraphs)


def process_document_upload(file, user, project_id: Optional[str] = None) -> Document:
    file_type = file.content_type or "text/plain"
    file_name = file.name
    buffer = file.read()

    extracted_text = ""
    pages = []

    if file_type == "application/pdf":
        pdf_data = extract_text_from_pdf(buffer)
        extracted_text = pdf_data.get("text", "")
        pages = pdf_data.get("pages", [])
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        extracted_text = _extract_text_from_docx(buffer)
    else:
        extracted_text = buffer.decode("utf-8", errors="ignore")

    if not extracted_text:
        raise ValueError("Failed to extract text from document")

    with transaction.atomic():
        document = Document.objects.create(
            title=file_name,
            doc_type=file_type,
            user=user,
            project_id=project_id,
        )

        if pages:
            chunks = chunk_pages(pages)
        else:
            chunks = chunk_text(extracted_text)

        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embeddings = generate_embeddings([chunk.content for chunk in batch])

            chunk_objects = []
            for chunk, embedding in zip(batch, embeddings):
                chunk_objects.append(
                    DocumentChunk(
                        content=chunk.content,
                        page=chunk.page,
                        chunk_index=chunk.chunk_index,
                        embedding=embedding,
                        document=document,
                    )
                )

            DocumentChunk.objects.bulk_create(chunk_objects)

    return document
