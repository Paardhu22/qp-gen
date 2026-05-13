from typing import List

from django.conf import settings

from services.openai_service import get_openai_client


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    client = get_openai_client()
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
    )

    return [item.embedding for item in response.data]


def generate_single_embedding(text: str) -> List[float]:
    embeddings = generate_embeddings([text])
    return embeddings[0]
