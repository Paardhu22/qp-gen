import logging
import re
from typing import Dict, List, Optional, Set

from apps.accounts.models import User
from apps.documents.models import DocumentChunk
from django.db.models import Q
from pgvector.django import L2Distance

from services.embedding_service import generate_single_embedding
from services.media_urls import normalise_chunk_payload


def _source_filter(
    pdf_source_ids: Optional[List[str]],
    hsat_source_ids: Optional[List[str]],
) -> Optional[Q]:
    """Build a Q() that unions PdfSource and HsatSource keys, or None if both empty."""
    pdf_ids = [pid for pid in (pdf_source_ids or []) if pid]
    hsat_ids = [hid for hid in (hsat_source_ids or []) if hid]
    if not pdf_ids and not hsat_ids:
        return None
    q = Q()
    if pdf_ids:
        q |= Q(pdf_source_id__in=pdf_ids)
    if hsat_ids:
        q |= Q(hsat_source_id__in=hsat_ids)
    return q

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
    # Legacy chunks persisted presigned URLs in metadata.image_url; rebuild
    # the stable /media/ URL from the permanent storage path so nothing
    # downstream (prompts, validation, the saved question) can go stale.
    return normalise_chunk_payload(payload)


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
    hsat_source_ids: Optional[List[str]] = None,
) -> List[dict]:
    source_q = _source_filter(pdf_source_ids, hsat_source_ids)
    if source_q is None:
        return []

    queryset = DocumentChunk.objects.filter(source_q)
    if exclude_chunk_ids:
        queryset = queryset.exclude(id__in=exclude_chunk_ids)
    if require_image:
        queryset = queryset.filter(metadata__has_key="image_url")

    chunks = list(
        queryset.order_by("pdf_source_id", "hsat_source_id", "page", "chunk_index")
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
    hsat_source_ids: Optional[List[str]] = None,
) -> List[dict]:
    source_q = _source_filter(pdf_source_ids, hsat_source_ids)
    if source_q is None:
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
            hsat_source_ids=hsat_source_ids,
        )
        if fallback or not require_image:
            return fallback
        return retrieve_fallback_chunks(
            query,
            pdf_source_ids,
            limit=limit,
            exclude_chunk_ids=exclude_chunk_ids,
            hsat_source_ids=hsat_source_ids,
        )

    queryset = DocumentChunk.objects.filter(source_q, embedding__isnull=False)
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
            hsat_source_ids=hsat_source_ids,
        )
        if fallback or not require_image:
            return fallback
        return retrieve_fallback_chunks(
            query,
            pdf_source_ids,
            limit=limit,
            exclude_chunk_ids=exclude_chunk_ids,
            hsat_source_ids=hsat_source_ids,
        )

    return results


def get_all_chunks(
    pdf_source_ids: List[str],
    hsat_source_ids: Optional[List[str]] = None,
) -> List[dict]:
    source_q = _source_filter(pdf_source_ids, hsat_source_ids)
    if source_q is None:
        return []

    queryset = (
        DocumentChunk.objects.filter(source_q)
        .order_by("pdf_source_id", "hsat_source_id", "page")
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
            normalise_chunk_payload(
                {
                    "content": chunk.content,
                    "page": chunk.page,
                    "similarity": 1.0,
                    "metadata": chunk.metadata,
                }
            )
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
