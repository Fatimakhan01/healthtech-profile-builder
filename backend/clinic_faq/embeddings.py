"""Generate embeddings only for chunks verified against approved policy files."""

import hashlib
import logging
import math
import numbers
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.db import transaction

from . import ingestion
from .models import PolicyChunk, PolicyDocument


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIMENSION = 384
MODEL_DIMENSIONS = {
    DEFAULT_EMBEDDING_MODEL: DEFAULT_EMBEDDING_DIMENSION,
}
DEFAULT_BATCH_SIZE = 32
MAX_BATCH_SIZE = 64
logger = logging.getLogger(__name__)


class EmbeddingConfigurationError(Exception):
    """Local embedding model configuration is invalid."""


class EmbeddingModelError(Exception):
    """The local embedding model could not be loaded or used."""

    def __init__(self, operation: str, error_type: str):
        self.operation = operation
        self.error_type = error_type
        super().__init__(
            f"Local embedding {operation} failed ({error_type})."
        )


class EmbeddingResponseError(Exception):
    """Local embedding model returned invalid vectors."""


@dataclass(frozen=True)
class EmbeddingSummary:
    processed_documents: int = 0
    skipped_documents: int = 0
    processed_chunks: int = 0
    skipped_chunks: int = 0
    embedded_chunks: int = 0
    failed_chunks: int = 0
    batch_count: int = 0


def load_embedding_config(
    environ: dict[str, str] | None = None,
) -> str:
    values = os.environ if environ is None else environ
    model = values.get(
        "CLINIC_FAQ_EMBEDDING_MODEL",
        DEFAULT_EMBEDDING_MODEL,
    ).strip()
    if not model or model.startswith("replace-with-"):
        raise EmbeddingConfigurationError(
            "CLINIC_FAQ_EMBEDDING_MODEL must name a local Sentence Transformers model."
        )
    return model


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise EmbeddingConfigurationError(
            "sentence-transformers is not installed."
        ) from error
    try:
        return SentenceTransformer(model_name, device="cpu")
    except Exception as error:
        error_type = type(error).__name__
        logger.error(
            "Could not load local embedding model: model=%s error_type=%s",
            model_name,
            error_type,
        )
        raise EmbeddingModelError("model loading", error_type) from error


def _text_to_vectors(
    model: Any,
    model_name: str,
    texts: list[str],
    expected_dimension: int | None = None,
) -> list[list[float]]:
    try:
        encoded = model.encode(
            texts,
            batch_size=min(len(texts), MAX_BATCH_SIZE),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception as error:
        error_type = type(error).__name__
        logger.error(
            "Local embedding generation failed: model=%s error_type=%s",
            model_name,
            error_type,
        )
        raise EmbeddingModelError("generation", error_type) from error
    return _validate_vectors(
        encoded,
        len(texts),
        expected_dimension=(
            expected_dimension
            if expected_dimension is not None
            else MODEL_DIMENSIONS.get(model_name)
        ),
    )


def embed_texts(
    texts: list[str],
    model_name: str | None = None,
) -> list[list[float]]:
    """Encode local text with the configured Sentence Transformers model."""
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("texts must contain non-empty strings.")
    configured_model = model_name or load_embedding_config()
    return _text_to_vectors(_load_model(configured_model), configured_model, texts)


def embed_query(query: str, model_name: str | None = None) -> list[float]:
    """Create one local query vector using the same model as document vectors."""
    return embed_texts([query], model_name=model_name)[0]


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _approved_stored_chunks() -> tuple[list[PolicyChunk], int, int]:
    approved_directory = ingestion.APPROVED_POLICY_DIR
    if approved_directory.is_symlink() or not approved_directory.is_dir():
        raise ingestion.PolicyIngestionError(
            "The approved policy directory is unavailable."
        )

    approved_files = {
        path.name: path
        for path in approved_directory.iterdir()
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.lower() in ingestion.SUPPORTED_SUFFIXES
    }

    valid_chunks: list[PolicyChunk] = []
    skipped_documents = 0
    skipped_chunks = 0
    documents = PolicyDocument.objects.prefetch_related("chunks").all()
    for document in documents:
        source_path = approved_files.get(document.source_filename)
        if source_path is None:
            skipped_documents += 1
            skipped_chunks += document.chunks.count()
            continue

        try:
            extracted = ingestion.extract_document(source_path)
            expected_chunks = ingestion.chunk_text(
                extracted.text,
                chunk_size=document.chunk_size,
                overlap=document.chunk_overlap,
            )
        except (ingestion.PolicyIngestionError, ValueError):
            skipped_documents += 1
            skipped_chunks += document.chunks.count()
            continue

        if extracted.content_sha256 != document.content_sha256:
            skipped_documents += 1
            skipped_chunks += document.chunks.count()
            continue

        stored_chunks = list(document.chunks.all())
        expected_by_index = dict(enumerate(expected_chunks))
        for chunk in stored_chunks:
            if expected_by_index.get(chunk.chunk_index) != chunk.text:
                skipped_chunks += 1
                continue
            valid_chunks.append(chunk)

    return valid_chunks, skipped_documents, skipped_chunks


def _validate_vectors(
    response_data: Any,
    expected_count: int,
    expected_dimension: int | None = None,
) -> list[list[float]]:
    try:
        if hasattr(response_data, "tolist"):
            response_data = response_data.tolist()
        if (
            not isinstance(response_data, (list, tuple))
            or len(response_data) != expected_count
        ):
            raise EmbeddingResponseError("Embedding output count is invalid.")

        vectors = []
        for vector in response_data:
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            if not isinstance(vector, (list, tuple)) or not vector:
                raise EmbeddingResponseError("Embedding vector is empty or invalid.")
            validated = []
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, numbers.Real):
                    raise EmbeddingResponseError(
                        "Embedding vector contains a non-numeric value."
                    )
                numeric = float(value)
                if not math.isfinite(numeric):
                    raise EmbeddingResponseError(
                        "Embedding vector contains a non-finite value."
                    )
                validated.append(numeric)
            vectors.append(validated)
    except EmbeddingResponseError:
        raise
    except (AttributeError, TypeError, ValueError) as error:
        raise EmbeddingResponseError("Embedding output is malformed.") from error

    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise EmbeddingResponseError("Embedding vector dimensions are inconsistent.")
    if expected_dimension is not None and dimensions != {expected_dimension}:
        raise EmbeddingResponseError(
            f"Expected {expected_dimension}-dimensional embedding vectors."
        )
    return vectors


def _valid_saved_embedding(
    vector: Any,
    expected_dimension: int | None,
) -> bool:
    if not isinstance(vector, list) or not vector:
        return False
    return all(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        for value in vector
    ) and (
        expected_dimension is None or len(vector) == expected_dimension
    )


def embed_approved_chunks(
    batch_size: int = DEFAULT_BATCH_SIZE,
    environ: dict[str, str] | None = None,
) -> EmbeddingSummary:
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}.")

    values = os.environ if environ is None else environ
    model = load_embedding_config(values)
    chunks, skipped_documents, invalid_chunks = _approved_stored_chunks()
    eligible_chunks = len(chunks)
    matching_chunks = [
        chunk
        for chunk in chunks
        if not (
            chunk.embedding is not None
            and chunk.embedding_model == model
            and chunk.embedding_text_sha256 == _text_digest(chunk.text)
            and _valid_saved_embedding(
                chunk.embedding,
                MODEL_DIMENSIONS.get(model),
            )
        )
    ]
    current_embeddings = [
        chunk.embedding
        for chunk in chunks
        if (
            chunk.embedding is not None
            and chunk.embedding_model == model
            and chunk.embedding_text_sha256 == _text_digest(chunk.text)
            and _valid_saved_embedding(
                chunk.embedding,
                MODEL_DIMENSIONS.get(model),
            )
        )
    ]
    current_dimensions = {len(vector) for vector in current_embeddings}
    if len(current_dimensions) > 1:
        matching_chunks = list(chunks)
        current_dimensions.clear()
    skipped_chunks = invalid_chunks + eligible_chunks - len(matching_chunks)
    pending_chunks = matching_chunks
    if not pending_chunks:
        return EmbeddingSummary(
            skipped_documents=skipped_documents,
            skipped_chunks=skipped_chunks,
        )

    local_model = _load_model(model)
    embedded = 0
    batches = 0
    expected_dimension = next(iter(current_dimensions), None)
    if expected_dimension is None:
        expected_dimension = MODEL_DIMENSIONS.get(model)

    for offset in range(0, len(pending_chunks), batch_size):
        batch = pending_chunks[offset : offset + batch_size]
        vectors = _text_to_vectors(
            local_model,
            model,
            [chunk.text for chunk in batch],
            expected_dimension=expected_dimension,
        )
        if expected_dimension is not None and len(vectors[0]) != expected_dimension:
            raise EmbeddingResponseError(
                f"Expected {expected_dimension}-dimensional embedding vectors."
            )
        if vectors:
            expected_dimension = len(vectors[0])
        batches += 1
        for chunk, vector in zip(batch, vectors):
            with transaction.atomic():
                current = (
                    PolicyChunk.objects.select_for_update()
                    .select_related("document")
                    .get(pk=chunk.pk)
                )
                if (
                    current.text != chunk.text
                    or current.document.content_sha256
                    != chunk.document.content_sha256
                ):
                    continue
                current.embedding = vector
                current.embedding_model = model
                current.embedding_text_sha256 = _text_digest(current.text)
                current.save(
                    update_fields=[
                        "embedding",
                        "embedding_model",
                        "embedding_text_sha256",
                    ]
                )
                embedded += 1

    return EmbeddingSummary(
        processed_documents=len({chunk.document_id for chunk in pending_chunks}),
        skipped_documents=skipped_documents,
        processed_chunks=len(pending_chunks),
        skipped_chunks=skipped_chunks,
        embedded_chunks=embedded,
        failed_chunks=0,
        batch_count=batches,
    )
