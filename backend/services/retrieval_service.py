from typing import List, Optional, Set

from apps.accounts.models import User
from apps.documents.models import DocumentChunk
from django.db.models import Q
from pgvector.django import L2Distance

from services.embedding_service import generate_single_embedding


def retrieve_relevant_chunks(
    query: str,
    pdf_source_ids: List[str],
    limit: int = 5,
    user: Optional[User] = None,
    require_image: bool = False,
    exclude_chunk_ids: Optional[Set[str]] = None,
    query_embedding: Optional[List[float]] = None,
    hsat_source_ids: Optional[List[str]] = None,
) -> List[dict]:
    """
    Retrieve the most semantically relevant chunks from the given PdfSources
    (user uploads) and/or HsatSources (shared textbooks) for use as
    generation context. Both source kinds share the DocumentChunk table so
    the resulting ranking treats them as a single pool — exactly what a
    "shared HSAT plus my notes" retrieval should do.

    If query_embedding is provided, it is used directly to avoid an extra
    embeddings API call per query.
    """
    pdf_ids = [pid for pid in (pdf_source_ids or []) if pid]
    hsat_ids = [hid for hid in (hsat_source_ids or []) if hid]
    if not pdf_ids and not hsat_ids:
        return []

    if query_embedding is None:
        query_embedding = generate_single_embedding(query, user=user)

    source_filter = Q()
    if pdf_ids:
        source_filter |= Q(pdf_source_id__in=pdf_ids)
    if hsat_ids:
        source_filter |= Q(hsat_source_id__in=hsat_ids)

    queryset = DocumentChunk.objects.filter(
        source_filter,
        embedding__isnull=False,
    )
    if require_image:
        queryset = queryset.filter(metadata__has_key="image_url")

    queryset = queryset.annotate(distance=L2Distance("embedding", query_embedding)).order_by("distance")

    results = []
    
    # We fetch a larger pool and filter in memory if exclude_chunk_ids is provided.
    # This allows upper layers to cache the query safely.
    max_fetch = 50 if exclude_chunk_ids else limit
    
    for chunk in queryset[:max_fetch]:
        if exclude_chunk_ids and str(chunk.id) in exclude_chunk_ids:
            continue
            
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
        
        if len(results) >= limit:
            break

    return results

def get_all_chunks(
    pdf_source_ids: List[str],
    hsat_source_ids: Optional[List[str]] = None,
) -> List[dict]:
    """
    Retrieves chunks from the specified PDFs and/or HSAT books. If the
    document is too large, it dynamically samples chunks evenly across the
    document to stay safely below OpenAI's 30,000 TPM rate limit while
    still representing the ENTIRE document.
    """
    pdf_ids = [pid for pid in (pdf_source_ids or []) if pid]
    hsat_ids = [hid for hid in (hsat_source_ids or []) if hid]
    if not pdf_ids and not hsat_ids:
        return []

    source_filter = Q()
    if pdf_ids:
        source_filter |= Q(pdf_source_id__in=pdf_ids)
    if hsat_ids:
        source_filter |= Q(hsat_source_id__in=hsat_ids)

    queryset = (
        DocumentChunk.objects.filter(source_filter)
        .order_by("pdf_source_id", "hsat_source_id", "page")
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
