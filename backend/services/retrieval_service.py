from typing import List, Optional

from pgvector.django import L2Distance

from apps.accounts.models import User
from apps.documents.models import DocumentChunk
from services.embedding_service import generate_single_embedding


def retrieve_relevant_chunks(query: str, document_ids: List[str], limit: int = 5, user: Optional[User] = None) -> List[dict]:
    if not document_ids:
        return []

    query_embedding = generate_single_embedding(query, user=user)

    queryset = (
        DocumentChunk.objects.filter(document_id__in=document_ids, embedding__isnull=False)
        .annotate(distance=L2Distance("embedding", query_embedding))
        .order_by("distance")
    )

    results = []
    for chunk in queryset[:limit]:
        similarity = 1 - float(chunk.distance) if chunk.distance is not None else 0
        results.append({
            "content": chunk.content,
            "page": chunk.page,
            "similarity": similarity,
        })

    return results
