"""Hybrid search over current, approved clinic policy chunks."""

import math
import numbers
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection

from . import embeddings
from .models import PolicyChunk, PolicyDocument


DEFAULT_TOP_K = 5
MAX_TOP_K = 50
DEFAULT_MIN_SIMILARITY = 0.2
DEFAULT_CANDIDATE_LIMIT = 500
MAX_CANDIDATE_LIMIT = 2_000
RRF_K = 60
TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
ALLOWED_FILTERS = {"source_filenames", "document_ids"}


@dataclass(frozen=True)
class RetrievedPolicyChunk:
    chunk_id: int
    source_title: str
    source_filename: str
    text: str
    similarity: float
    fusion_score: float = 0.0
    retrieval_method: str = "semantic"


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


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def _validated_filters(filters: Mapping[str, Any] | None) -> dict[str, set]:
    if filters is None:
        return {}
    if not isinstance(filters, Mapping):
        raise ValueError("filters must be a mapping of supported document fields.")
    unknown = set(filters) - ALLOWED_FILTERS
    if unknown:
        raise ValueError(f"Unsupported retrieval filter: {sorted(unknown)[0]}.")

    validated = {}
    for name, value in filters.items():
        if not isinstance(value, (list, tuple, set, frozenset)) or not value:
            raise ValueError(f"filters[{name!r}] must be a non-empty collection.")
        values = list(value)
        if name == "source_filenames":
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError("source_filenames must contain non-empty strings.")
            validated[name] = {item.strip() for item in values}
        else:
            if any(type(item) is not int or item < 1 for item in values):
                raise ValueError("document_ids must contain positive integers.")
            validated[name] = set(values)
    return validated


def _bm25_keyword_scores(
    query: str,
    chunks: list[PolicyChunk],
) -> list[tuple[PolicyChunk, float]]:
    query_terms = set(_tokens(query))
    if not query_terms or not chunks:
        return []

    tokenized = [_tokens(chunk.text) for chunk in chunks]
    document_frequencies = Counter(
        term
        for terms in tokenized
        for term in query_terms.intersection(terms)
    )
    average_length = sum(map(len, tokenized)) / len(tokenized) or 1.0
    document_count = len(chunks)
    scores = []
    for chunk, terms in zip(chunks, tokenized):
        frequencies = Counter(terms)
        score = 0.0
        for term in query_terms:
            frequency = frequencies[term]
            if not frequency:
                continue
            doc_frequency = document_frequencies[term]
            inverse_frequency = math.log(
                1
                + (document_count - doc_frequency + 0.5)
                / (doc_frequency + 0.5)
            )
            length_norm = 1.5 * (
                1 - 0.75 + 0.75 * len(terms) / average_length
            )
            score += (
                inverse_frequency
                * frequency
                * (1.5 + 1)
                / (frequency + length_norm)
            )
        if score > 0:
            scores.append((chunk, score))
    return sorted(scores, key=lambda item: (-item[1], item[0].pk))


def _keyword_ranked(
    query: str,
    chunks: list[PolicyChunk],
    limit: int,
) -> list[tuple[PolicyChunk, float]]:
    if not _tokens(query) or not chunks:
        return []
    if connection.vendor != "postgresql":
        return _bm25_keyword_scores(query, chunks)[:limit]

    chunks_by_id = {chunk.pk: chunk for chunk in chunks}
    vector = SearchVector("text", config="english")
    search_query = SearchQuery(query, search_type="plain", config="english")
    ranked_ids = (
        PolicyChunk.objects.filter(pk__in=chunks_by_id)
        .annotate(search_document=vector)
        .filter(search_document=search_query)
        .annotate(keyword_rank=SearchRank(vector, search_query))
        .order_by("-keyword_rank", "pk")
        .values_list("pk", "keyword_rank")[:limit]
    )
    return [
        (chunks_by_id[chunk_id], float(score))
        for chunk_id, score in ranked_ids
    ]


def _semantic_ranked(
    chunks: list[PolicyChunk],
    query_vector: np.ndarray | None,
    *,
    min_similarity: float,
    limit: int,
) -> list[tuple[PolicyChunk, float]]:
    if query_vector is None or not chunks:
        return []
    compatible = []
    for chunk in chunks:
        vector = _vector(chunk.embedding)
        if vector is not None and vector.shape == query_vector.shape:
            compatible.append((chunk, vector))
    if not compatible:
        return []

    matrix = np.stack([vector for _, vector in compatible])
    normalized_matrix = matrix / np.linalg.norm(matrix, axis=1)[:, np.newaxis]
    normalized_query = query_vector / np.linalg.norm(query_vector)
    similarities = normalized_matrix @ normalized_query
    ranked = sorted(
        (
            (chunk, float(score))
            for (chunk, _), score in zip(compatible, similarities)
            if score >= min_similarity
        ),
        key=lambda item: (-item[1], item[0].pk),
    )
    return ranked[:limit]


def _fuse_and_rerank(
    query: str,
    semantic: list[tuple[PolicyChunk, float]],
    keyword: list[tuple[PolicyChunk, float]],
) -> list[RetrievedPolicyChunk]:
    chunks_by_id = {}
    semantic_scores = {}
    reciprocal_scores = {}
    branch_membership = {}
    for method, ranked in (("semantic", semantic), ("keyword", keyword)):
        for rank, (chunk, score) in enumerate(ranked, start=1):
            chunks_by_id[chunk.pk] = chunk
            if method == "semantic":
                semantic_scores[chunk.pk] = score
            reciprocal_scores[chunk.pk] = reciprocal_scores.get(chunk.pk, 0.0) + (
                1.0 / (RRF_K + rank)
            )
            branch_membership.setdefault(chunk.pk, set()).add(method)

    query_terms = set(_tokens(query))
    normalized_query = " ".join(_tokens(query))

    def rerank_key(chunk_id: int):
        chunk = chunks_by_id[chunk_id]
        text_tokens = set(_tokens(chunk.text))
        coverage = len(query_terms.intersection(text_tokens)) / len(query_terms) if query_terms else 0
        exact_phrase = bool(
            normalized_query
            and normalized_query in " ".join(_tokens(chunk.text))
        )
        return (
            -reciprocal_scores[chunk_id],
            -int(exact_phrase),
            -coverage,
            -semantic_scores.get(chunk_id, 0.0),
            chunk_id,
        )

    results = []
    for chunk_id in sorted(chunks_by_id, key=rerank_key):
        chunk = chunks_by_id[chunk_id]
        methods = branch_membership[chunk_id]
        method = (
            "hybrid"
            if len(methods) == 2
            else next(iter(methods))
        )
        results.append(
            RetrievedPolicyChunk(
                chunk_id=chunk_id,
                source_title=chunk.document.title,
                source_filename=chunk.document.source_filename,
                text=chunk.text,
                similarity=semantic_scores.get(chunk_id, 0.0),
                fusion_score=reciprocal_scores[chunk_id],
                retrieval_method=method,
            )
        )
    return results


def retrieve_policy_chunks(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    model_name: str | None = None,
    search_mode: str = "hybrid",
    filters: Mapping[str, Any] | None = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[RetrievedPolicyChunk]:
    """Return bounded hybrid results from approved current policy chunks.

    Keyword and semantic rankings are combined with reciprocal rank fusion.
    Metadata filters only narrow eligible documents; they cannot disable the
    mandatory approval, activity, indexing, current-version, or embedding checks.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    if type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}.")
    if (
        isinstance(min_similarity, bool)
        or not isinstance(min_similarity, numbers.Real)
        or not math.isfinite(float(min_similarity))
        or not -1 <= min_similarity <= 1
    ):
        raise ValueError("min_similarity must be a finite number from -1 to 1.")
    if not isinstance(search_mode, str) or search_mode not in {
        "hybrid",
        "semantic",
        "keyword",
    }:
        raise ValueError("search_mode must be 'hybrid', 'semantic', or 'keyword'.")
    if (
        type(candidate_limit) is not int
        or not 1 <= candidate_limit <= MAX_CANDIDATE_LIMIT
        or top_k > candidate_limit
    ):
        raise ValueError(
            f"candidate_limit must be between top_k and {MAX_CANDIDATE_LIMIT}."
        )

    validated_filters = _validated_filters(filters)
    configured_model = model_name or embeddings.load_embedding_config()
    chunks, _, _ = embeddings._approved_stored_chunks(
        source_filenames=validated_filters.get("source_filenames"),
        document_ids=validated_filters.get("document_ids"),
    )
    candidates = [
        chunk
        for chunk in chunks
        if chunk.document_version == chunk.document.version
        and chunk.document.is_approved
        and chunk.document.is_active
        and chunk.document.indexing_status
        == PolicyDocument.IndexingStatus.INDEXED
        and chunk.embedding_model == configured_model
        and chunk.embedding_text_sha256 == embeddings._text_digest(chunk.text)
        and embeddings._valid_saved_embedding(
            chunk.embedding,
            embeddings.MODEL_DIMENSIONS.get(configured_model),
        )
    ][:candidate_limit]
    if not candidates:
        return []

    semantic = []
    if search_mode in {"hybrid", "semantic"}:
        query_vector = _vector(
            embeddings.embed_query(query, model_name=configured_model)
        )
        semantic = _semantic_ranked(
            candidates,
            query_vector,
            min_similarity=min_similarity,
            limit=candidate_limit,
        )
    keyword = []
    if search_mode in {"hybrid", "keyword"}:
        keyword = _keyword_ranked(query, candidates, candidate_limit)

    ranked = _fuse_and_rerank(query, semantic, keyword)
    return ranked[:top_k]
