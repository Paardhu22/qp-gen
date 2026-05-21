from typing import List, Optional

from apps.accounts.models import User
from apps.documents.models import DocumentChunk
from pgvector.django import L2Distance

from services.embedding_service import generate_single_embedding


def retrieve_relevant_chunks(
    query: str,
    pdf_source_ids: List[str],
    limit: int = 5,
    user: Optional[User] = None,
) -> List[dict]:
    """
    Retrieve the most semantically relevant chunks from the given PdfSources
    for use as generation context. This never touches Question Bank or Paper
    data — it only reads from DocumentChunk via the PdfSource FK.
    """
    if not pdf_source_ids:
        return []

    query_embedding = generate_single_embedding(query, user=user)

    queryset = (
        DocumentChunk.objects.filter(
            pdf_source_id__in=pdf_source_ids,
            embedding__isnull=False,
        )
        .annotate(distance=L2Distance("embedding", query_embedding))
        .order_by("distance")
    )

    results = []
    for chunk in queryset[:limit]:
        similarity = 1 - float(chunk.distance) if chunk.distance is not None else 0
        results.append(
            {
                "content": chunk.content,
                "page": chunk.page,
                "similarity": similarity,
                "metadata": chunk.metadata,
            }
        )

    return results
