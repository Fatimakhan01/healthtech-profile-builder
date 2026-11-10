"""Read-only semantic retrieval over current, approved clinic policy chunks."""

import math
import numbers
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import embeddings


DEFAULT_TOP_K = 5
DEFAULT_MIN_SIMILARITY = 0.2


@dataclass(frozen=True)
class RetrievedPolicyChunk:
    chunk_id: int
    source_title: str
    source_filename: str
    text: str
    similarity: float


def _vector(values: Any) -> np.ndarray | None:
    if not isinstance(values, (list, tuple)) or not values:
        return None
    if any(
        isinstance(value, bool) or not isinstance(value, numbers.Real)
        for value in values
    ):
        return None
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        return None
    if vector.ndim != 1 or not np.isfinite(vector).all():
        return None
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm <= 0:
        return None
    return vector


def retrieve_policy_chunks(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    model_name: str | None = None,
) -> list[RetrievedPolicyChunk]:
    """Return the highest-scoring current approved chunks for a query.

    Similarity is cosine similarity in the configured local embedding space.
    Invalid, stale, or incompatible stored vectors are ignored.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be a positive integer.")
    if (
        isinstance(min_similarity, bool)
        or not isinstance(min_similarity, numbers.Real)
        or not math.isfinite(float(min_similarity))
        or not -1 <= min_similarity <= 1
    ):
        raise ValueError("min_similarity must be a finite number from -1 to 1.")

    configured_model = model_name or embeddings.load_embedding_config()
    chunks, _, _ = embeddings._approved_stored_chunks()
    candidates = [
        chunk
        for chunk in chunks
        if chunk.embedding_model == configured_model
        and chunk.embedding_text_sha256 == embeddings._text_digest(chunk.text)
        and embeddings._valid_saved_embedding(
            chunk.embedding,
            embeddings.MODEL_DIMENSIONS.get(configured_model),
        )
    ]
    if not candidates:
        return []

    query_vector = _vector(
        embeddings.embed_query(query, model_name=configured_model)
    )
    if query_vector is None:
        return []

    compatible = []
    for chunk in candidates:
        vector = _vector(chunk.embedding)
        if vector is not None and vector.shape == query_vector.shape:
            compatible.append((chunk, vector))
    if not compatible:
        return []

    matrix = np.stack([vector for _, vector in compatible])
    query_norm = np.linalg.norm(query_vector)
    vector_norms = np.linalg.norm(matrix, axis=1)
    normalized_matrix = matrix / vector_norms[:, np.newaxis]
    normalized_query = query_vector / query_norm
    similarities = normalized_matrix @ normalized_query

    ranked = sorted(
        (
            (float(score), chunk)
            for (chunk, _), score in zip(compatible, similarities)
            if score >= min_similarity
        ),
        key=lambda item: (-item[0], item[1].pk),
    )[:top_k]
    return [
        RetrievedPolicyChunk(
            chunk_id=chunk.pk,
            source_title=chunk.document.title,
            source_filename=chunk.document.source_filename,
            text=chunk.text,
            similarity=score,
        )
        for score, chunk in ranked
    ]
