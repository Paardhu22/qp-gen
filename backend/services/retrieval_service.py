from typing import List, Optional, Set

from apps.accounts.models import User
from apps.documents.models import DocumentChunk
from pgvector.django import L2Distance

from services.embedding_service import generate_single_embedding


def retrieve_relevant_chunks(
    query: str,
    pdf_source_ids: List[str],
    limit: int = 5,
    user: Optional[User] = None,
    require_image: bool = False,
    exclude_chunk_ids: Optional[Set[str]] = None,
) -> List[dict]:
    """
    Retrieve the most semantically relevant chunks from the given PdfSources
    for use as generation context. This never touches Question Bank or Paper
    data — it only reads from DocumentChunk via the PdfSource FK.
    """
    if not pdf_source_ids:
        return []

    query_embedding = generate_single_embedding(query, user=user)

    queryset = DocumentChunk.objects.filter(
        pdf_source_id__in=pdf_source_ids,
        embedding__isnull=False,
    )
    if exclude_chunk_ids:
        queryset = queryset.exclude(id__in=exclude_chunk_ids)
    if require_image:
        queryset = queryset.filter(metadata__has_key="image_url")

    queryset = queryset.annotate(distance=L2Distance("embedding", query_embedding)).order_by("distance")

    results = []
    for chunk in queryset[:limit]:
        metadata = chunk.metadata or {}
        similarity = 1 - float(chunk.distance) if chunk.distance is not None else 0
        payload = {
            "id": chunk.id,
            "content": chunk.content,
            "page": chunk.page,
            "similarity": similarity,
            "metadata": metadata,
        }
        if metadata.get("image_url"):
            payload["image_url"] = metadata.get("image_url")
        results.append(payload)

    return results

def get_all_chunks(
    pdf_source_ids: List[str],
) -> List[dict]:
    """
    Retrieves chunks from the specified PDFs. If the document is too large,
    it dynamically samples chunks evenly across the document to stay safely
    below OpenAI's 30,000 TPM rate limit while still representing the ENTIRE document.
    """
    if not pdf_source_ids:
        return []

    queryset = (
        DocumentChunk.objects.filter(
            pdf_source_id__in=pdf_source_ids
        )
        .order_by("pdf_source_id", "page")
    )

    all_chunks = list(queryset)
    total_chunks = len(all_chunks)
    
    # Target safe ceiling of 55 chunks to guarantee staying under the 30,000 TPM limit (leaving room for generated output)
    MAX_CHUNKS = 55
    
    if total_chunks > MAX_CHUNKS:
        # Sample evenly across the full list of chunks to cover every chapter/page
        step = total_chunks / MAX_CHUNKS
        sampled_chunks = [all_chunks[int(i * step)] for i in range(MAX_CHUNKS)]
    else:
        sampled_chunks = all_chunks

    results = []
    for chunk in sampled_chunks:
        results.append(
            {
                "content": chunk.content,
                "page": chunk.page,
                "similarity": 1.0,
                "metadata": chunk.metadata,
            }
        )

    return results
