import logging
import re
from typing import Dict, List, Optional, Set

from apps.accounts.models import User
from apps.documents.models import DocumentChunk
from pgvector.django import L2Distance

from services.embedding_service import generate_single_embedding

logger = logging.getLogger("[QG_RETRIEVAL]")


def _chunk_to_payload(chunk, similarity: float) -> dict:
    metadata = chunk.metadata or {}
    payload = {
        "id": chunk.id,
        "content": chunk.content,
        "page": chunk.page,
        "similarity": similarity,
        "metadata": metadata,
    }
    if metadata.get("image_url"):
        payload["image_url"] = metadata.get("image_url")
    return payload


def _lexical_score(query: str, content: str) -> int:
    terms = {
        term
        for term in re.findall(r"[a-z0-9]{3,}", query.lower())
        if term not in {"class", "mark", "marks", "easy", "medium", "hard", "question"}
    }
    if not terms:
        return 0
    content_norm = content.lower()
    return sum(1 for term in terms if term in content_norm)


def retrieve_fallback_chunks(
    query: str,
    pdf_source_ids: List[str],
    limit: int = 4,
    require_image: bool = False,
    exclude_chunk_ids: Optional[Set[str]] = None,
) -> List[dict]:
    if not pdf_source_ids:
        return []

    queryset = DocumentChunk.objects.filter(pdf_source_id__in=pdf_source_ids)
    if exclude_chunk_ids:
        queryset = queryset.exclude(id__in=exclude_chunk_ids)
    if require_image:
        queryset = queryset.filter(metadata__has_key="image_url")

    chunks = list(
        queryset.order_by("pdf_source_id", "page", "chunk_index")
    )
    ranked = sorted(
        chunks,
        key=lambda chunk: (_lexical_score(query, chunk.content), -(chunk.page or 0)),
        reverse=True,
    )
    return [_chunk_to_payload(chunk, 0.0) for chunk in ranked[:limit]]


def retrieve_relevant_chunks(
    query: str,
    pdf_source_ids: List[str],
    limit: int = 4,
    user: Optional[User] = None,
    require_image: bool = False,
    exclude_chunk_ids: Optional[Set[str]] = None,
) -> List[dict]:
    if not pdf_source_ids:
        return []

    try:
        query_embedding = generate_single_embedding(query, user=user)
    except Exception as exc:
        logger.warning("[RAG] Embedding retrieval failed, using lexical fallback: %s", exc)
        fallback = retrieve_fallback_chunks(
            query,
            pdf_source_ids,
            limit=limit,
            require_image=require_image,
            exclude_chunk_ids=exclude_chunk_ids,
        )
        if fallback or not require_image:
            return fallback
        return retrieve_fallback_chunks(
            query,
            pdf_source_ids,
            limit=limit,
            exclude_chunk_ids=exclude_chunk_ids,
        )

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
        similarity = 1 - float(chunk.distance) if chunk.distance is not None else 0
        results.append(_chunk_to_payload(chunk, similarity))

    if not results:
        fallback = retrieve_fallback_chunks(
            query,
            pdf_source_ids,
            limit=limit,
            require_image=require_image,
            exclude_chunk_ids=exclude_chunk_ids,
        )
        if fallback or not require_image:
            return fallback
        return retrieve_fallback_chunks(
            query,
            pdf_source_ids,
            limit=limit,
            exclude_chunk_ids=exclude_chunk_ids,
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
