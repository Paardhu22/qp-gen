from typing import Dict, List, Optional

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


def get_all_chunks(pdf_source_ids: List[str]) -> List[dict]:
    if not pdf_source_ids:
        return []

    queryset = (
        DocumentChunk.objects.filter(pdf_source_id__in=pdf_source_ids)
        .order_by("pdf_source_id", "page")
    )

    all_chunks = list(queryset)
    total_chunks = len(all_chunks)
    max_chunks = 55

    if total_chunks > max_chunks:
        step = total_chunks / max_chunks
        sampled_chunks = [all_chunks[int(i * step)] for i in range(max_chunks)]
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


def retrieval_quality_summary(chunks: List[dict]) -> Dict[str, float]:
    if not chunks:
        return {"avg_similarity": 0.0, "min_similarity": 0.0, "max_similarity": 0.0}

    similarities = [c.get("similarity", 0.0) for c in chunks]
    return {
        "avg_similarity": sum(similarities) / len(similarities),
        "min_similarity": min(similarities),
        "max_similarity": max(similarities),
    }
