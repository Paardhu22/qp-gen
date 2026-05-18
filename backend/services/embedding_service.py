from typing import List, Optional

from django.conf import settings

from apps.accounts.models import User
from services.openai_service import get_openai_client


def generate_embeddings(texts: List[str], user: Optional[User] = None) -> List[List[float]]:
    if not texts:
        return []

    client = get_openai_client()
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
    )

    if user:
        from services.openai_service import _record_usage
        _record_usage(user, "embeddings", settings.OPENAI_EMBEDDING_MODEL, response.usage)

    return [item.embedding for item in response.data]


def generate_single_embedding(text: str, user: Optional[User] = None) -> List[float]:
    embeddings = generate_embeddings([text], user=user)
    return embeddings[0]
