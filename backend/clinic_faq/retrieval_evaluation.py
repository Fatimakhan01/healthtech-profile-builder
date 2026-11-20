"""Retrieval-only evaluation for the approved Clinic FAQ policy corpus."""

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import embeddings, ingestion, retrieval
from .models import PolicyChunk, PolicyDocument


PACKAGE_DIR = Path(__file__).resolve().parent
DATASET_PATH = PACKAGE_DIR / "evaluation" / "retrieval_questions.json"
REPORT_DIR = PACKAGE_DIR / "reports"
REPORT_JSON_PATH = REPORT_DIR / "retrieval_evaluation.json"
REPORT_MARKDOWN_PATH = REPORT_DIR / "retrieval_evaluation.md"
CHUNK_REPORT_PATH = PACKAGE_DIR / "reports" / "chunk_size_comparison.json"
APPROVED_SOURCE_FILENAMES = frozenset(
    {
        "appointment-scheduling.md",
        "cancellations.md",
        "late-arrivals.md",
        "reminders.md",
    }
)
RETRIEVAL_METHODS = ("semantic", "hybrid")
TOP_K = 5
METRIC_CUTOFFS = (1, 3, 5)
CHUNK_CONFIGURATIONS = (
    {
        "name": "smaller",
        "chunk_size": round(ingestion.DEFAULT_CHUNK_SIZE * 0.75),
        "chunk_overlap": round(ingestion.DEFAULT_CHUNK_OVERLAP * 0.75),
    },
    {
        "name": "current_default",
        "chunk_size": ingestion.DEFAULT_CHUNK_SIZE,
        "chunk_overlap": ingestion.DEFAULT_CHUNK_OVERLAP,
    },
    {
        "name": "larger",
        "chunk_size": round(ingestion.DEFAULT_CHUNK_SIZE * 1.5),
        "chunk_overlap": round(ingestion.DEFAULT_CHUNK_OVERLAP * 1.5),
    },
)
WHITESPACE = re.compile(r"\s+")


def _normalized(text: str) -> str:
    return WHITESPACE.sub(" ", text.casefold()).strip()


def load_approved_sources() -> dict[str, ingestion.ExtractedDocument]:
    directory = ingestion.APPROVED_POLICY_DIR
    if directory.is_symlink() or not directory.is_dir():
        raise ingestion.PolicyIngestionError(
            "The approved policy directory is unavailable."
        )
    extracted = {}
    for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_dir() and not path.is_symlink():
            continue
        if path.suffix.lower() not in ingestion.SUPPORTED_SUFFIXES:
            continue
        document = ingestion.extract_document(path)
        extracted[document.source_filename] = document
    if set(extracted) != APPROVED_SOURCE_FILENAMES:
        raise ValueError(
            "Retrieval evaluation requires exactly the four approved policy sources."
        )
    return extracted


def load_and_validate_questions(
    path: Path | str = DATASET_PATH,
    *,
    sources: Mapping[str, ingestion.ExtractedDocument] | None = None,
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Retrieval question dataset is unreadable or invalid JSON.") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"dataset_version", "description", "questions"}
        or payload["dataset_version"] != 1
        or not isinstance(payload["description"], str)
        or not isinstance(payload["questions"], list)
    ):
        raise ValueError("Retrieval question dataset has an invalid schema.")

    source_documents = (
        sources if sources is not None else load_approved_sources()
    )
    if len(payload["questions"]) < 20:
        raise ValueError("Retrieval evaluation requires at least 20 labeled questions.")
    question_ids = set()
    validated = []
    for question in payload["questions"]:
        if (
            not isinstance(question, dict)
            or set(question) != {"id", "question", "expected_sources", "evidence"}
            or not isinstance(question["id"], str)
            or not question["id"].strip()
            or question["id"] in question_ids
            or not isinstance(question["question"], str)
            or not question["question"].strip()
            or not isinstance(question["expected_sources"], list)
            or not question["expected_sources"]
            or any(
                not isinstance(source, str) or not source.strip()
                for source in question["expected_sources"]
            )
            or len(set(question["expected_sources"])) != len(question["expected_sources"])
            or not isinstance(question["evidence"], dict)
            or set(question["evidence"]) != set(question["expected_sources"])
        ):
            raise ValueError("A retrieval question has invalid fields or duplicate IDs.")
        expected_sources = question["expected_sources"]
        if any(source not in source_documents for source in expected_sources):
            raise ValueError(
                f"Question {question['id']!r} labels a source outside the approved corpus."
            )
        for filename, evidence in question["evidence"].items():
            if (
                not isinstance(evidence, str)
                or not evidence.strip()
                or _normalized(evidence)
                not in _normalized(source_documents[filename].text)
            ):
                raise ValueError(
                    f"Question {question['id']!r} has evidence not found in {filename!r}."
                )
        question_ids.add(question["id"])
        validated.append(question)
    return validated


def _live_corpus_context(
    sources: Mapping[str, ingestion.ExtractedDocument],
) -> dict[str, Any]:
    documents = {
        document.source_filename: document
        for document in PolicyDocument.objects.filter(
            source_filename__in=sources
        ).prefetch_related("chunks")
    }
    if set(documents) != set(sources):
        raise ValueError(
            "All approved sources must be ingested before retrieval evaluation."
        )
    records = []
    for filename in sorted(sources):
        document = documents[filename]
        source = sources[filename]
        chunks = list(document.chunks.all())
        if (
            not document.is_approved
            or not document.is_active
            or document.indexing_status != PolicyDocument.IndexingStatus.INDEXED
            or document.content_sha256 != source.content_sha256
            or not chunks
            or any(chunk.document_version != document.version for chunk in chunks)
        ):
            raise ValueError(
                f"Approved source {filename!r} must be current and fully indexed."
            )
        records.append(
            {
                "source_filename": filename,
                "content_sha256": source.content_sha256,
                "document_version": document.version,
                "chunk_size": document.chunk_size,
                "chunk_overlap": document.chunk_overlap,
                "chunk_count": len(chunks),
                "indexing_status": document.indexing_status,
            }
        )
    return {
        "source_count": len(records),
        "documents": records,
        "source_hashes": {
            entry["source_filename"]: entry["content_sha256"] for entry in records
        },
    }


def _source_filename(result: Any) -> str:
    if isinstance(result, Mapping):
        return result["source_filename"]
    return result.source_filename


def _serialize_result(result: Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        return {
            "chunk_id": result["chunk_id"],
            "source_title": result["source_title"],
            "source_filename": result["source_filename"],
            "text": result["text"],
            "similarity": result.get("similarity", 0.0),
        }
    return {
        "chunk_id": result.chunk_id,
        "source_title": result.source_title,
        "source_filename": result.source_filename,
        "text": result.text,
        "similarity": result.similarity,
    }


def calculate_retrieval_metrics(
    questions: Sequence[Mapping[str, Any]],
    retrieved_by_question: Mapping[str, Sequence[Any]],
) -> dict[str, Any]:
    """Calculate macro-averaged, source-labeled metrics for one method."""
    per_question = []
    for question in questions:
        question_id = question["id"]
        retrieved = list(retrieved_by_question.get(question_id, ()))
        expected = set(question["expected_sources"])
        retrieved_sources = []
        seen_sources = set()
        for result in retrieved:
            filename = _source_filename(result)
            if filename not in seen_sources:
                seen_sources.add(filename)
                retrieved_sources.append(filename)

        row = {
            "question_id": question_id,
            "question": question["question"],
            "expected_sources": list(question["expected_sources"]),
            "retrieved_source_filenames": retrieved_sources,
            "retrieval_results": [_serialize_result(result) for result in retrieved],
            "metrics": {},
        }
        first_relevant_rank = next(
            (
                rank
                for rank, filename in enumerate(retrieved_sources, start=1)
                if filename in expected
            ),
            None,
        )
        row["metrics"]["reciprocal_rank"] = (
            1.0 / first_relevant_rank if first_relevant_rank else 0.0
        )
        for cutoff in METRIC_CUTOFFS:
            top_sources = {
                _source_filename(result)
                for result in retrieved[:cutoff]
            }
            relevant_retrieved = len(expected.intersection(top_sources))
            recall = relevant_retrieved / len(expected)
            precision = (
                relevant_retrieved / len(top_sources) if top_sources else 0.0
            )
            hit = float(relevant_retrieved > 0)
            row["metrics"][f"recall_at_{cutoff}"] = recall
            row["metrics"][f"hitrate_at_{cutoff}"] = hit
            row["metrics"][f"source_precision_at_{cutoff}"] = precision
            row["metrics"][f"source_recall_at_{cutoff}"] = recall
        per_question.append(row)

    metric_names = [
        "reciprocal_rank",
        *(
            metric
            for cutoff in METRIC_CUTOFFS
            for metric in (
                f"recall_at_{cutoff}",
                f"hitrate_at_{cutoff}",
                f"source_precision_at_{cutoff}",
                f"source_recall_at_{cutoff}",
            )
        ),
    ]
    aggregate = {
        metric: (
            sum(question["metrics"][metric] for question in per_question)
            / len(per_question)
            if per_question
            else 0.0
        )
        for metric in metric_names
    }
    return {"question_count": len(per_question), "aggregate": aggregate, "questions": per_question}


def _method_evaluation(
    questions: Sequence[Mapping[str, Any]],
    retrieve: Callable[..., Sequence[Any]],
    *,
    method: str,
    model_name: str,
) -> dict[str, Any]:
    retrieved = {}
    for question in questions:
        retrieved[question["id"]] = list(
            retrieve(
                question["question"],
                top_k=TOP_K,
                min_similarity=retrieval.DEFAULT_MIN_SIMILARITY,
                model_name=model_name,
                search_mode=method,
            )
        )
    metrics = calculate_retrieval_metrics(questions, retrieved)
    return {
        "retrieval_method": method,
        "top_k": TOP_K,
        "min_similarity": retrieval.DEFAULT_MIN_SIMILARITY,
        **metrics,
    }


def _metric_differences(
    semantic: Mapping[str, Any],
    hybrid: Mapping[str, Any],
) -> dict[str, Any]:
    differences = {}
    for metric, hybrid_value in hybrid["aggregate"].items():
        semantic_value = semantic["aggregate"][metric]
        differences[metric] = {
            "semantic": semantic_value,
            "hybrid": hybrid_value,
            "hybrid_minus_semantic": hybrid_value - semantic_value,
        }
    question_differences = {}
    for name in semantic["aggregate"]:
        deltas = [
            hybrid_question["metrics"][name] - semantic_question["metrics"][name]
            for semantic_question, hybrid_question in zip(
                semantic["questions"],
                hybrid["questions"],
            )
        ]
        question_differences[name] = {
            "improved": sum(delta > 0 for delta in deltas),
            "regressed": sum(delta < 0 for delta in deltas),
            "unchanged": sum(delta == 0 for delta in deltas),
        }
    return {
        "metrics": differences,
        "per_question_metric_outcomes": question_differences,
        "per_question_recall_outcomes": {
            metric: outcomes
            for metric, outcomes in question_differences.items()
            if metric.startswith("recall_at_")
        },
    }


def evaluate_retrieval_methods(
    questions: Sequence[Mapping[str, Any]],
    *,
    model_name: str,
    corpus_context: Mapping[str, Any],
    dataset_path: Path | str = DATASET_PATH,
    retrieve: Callable[..., Sequence[Any]] = retrieval.retrieve_policy_chunks,
    evaluation_time: datetime | None = None,
) -> dict[str, Any]:
    methods = {
        method: _method_evaluation(
            questions,
            retrieve,
            method=method,
            model_name=model_name,
        )
        for method in RETRIEVAL_METHODS
    }
    return {
        "report_version": 1,
        "evaluation_type": "retrieval_only",
        "generated_at": (evaluation_time or datetime.now(timezone.utc)).isoformat(),
        "dataset": {
            "path": Path(dataset_path).as_posix(),
            "question_count": len(questions),
            "question_ids": [question["id"] for question in questions],
        },
        "corpus": dict(corpus_context),
        "embedding_model": model_name,
        "top_k": TOP_K,
        "metric_cutoffs": list(METRIC_CUTOFFS),
        "methods": methods,
        "comparison": _metric_differences(
            methods["semantic"],
            methods["hybrid"],
        ),
        "generation_model_used": False,
    }


def _in_memory_chunks(
    sources: Mapping[str, ingestion.ExtractedDocument],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[list[PolicyChunk], dict[str, int]]:
    chunks = []
    counts = {}
    for filename in sorted(sources):
        source = sources[filename]
        title = source.title
        document = SimpleNamespace(
            source_filename=filename,
            title=title,
            version=1,
            content_sha256=source.content_sha256,
            is_approved=True,
            is_active=True,
            indexing_status=PolicyDocument.IndexingStatus.INDEXED,
        )
        texts = ingestion.chunk_text(
            source.text,
            chunk_size=chunk_size,
            overlap=chunk_overlap,
        )
        counts[filename] = len(texts)
        for chunk_index, text in enumerate(texts):
            chunk = SimpleNamespace(
                pk=len(chunks) + 1,
                document=document,
                document_id=len(chunks) + 1,
                document_version=1,
                chunk_index=chunk_index,
                text=text,
                embedding=None,
                embedding_model="",
                embedding_text_sha256="",
            )
            chunks.append(chunk)
    return chunks, counts


def _evaluate_in_memory_configuration(
    questions: Sequence[Mapping[str, Any]],
    chunks: list[PolicyChunk],
    query_vectors: Mapping[str, Any],
    *,
    model_name: str,
) -> dict[str, Any]:
    results_by_method = {}
    for method in RETRIEVAL_METHODS:
        results_by_question = {}
        for question in questions:
            query_vector = retrieval._vector(query_vectors[question["id"]])
            semantic_ranked = retrieval._semantic_ranked(
                chunks,
                query_vector,
                min_similarity=retrieval.DEFAULT_MIN_SIMILARITY,
                limit=retrieval.DEFAULT_CANDIDATE_LIMIT,
            )
            keyword_ranked = (
                retrieval._bm25_keyword_scores(
                    question["question"],
                    chunks,
                )[: retrieval.DEFAULT_CANDIDATE_LIMIT]
                if method == "hybrid"
                else []
            )
            ranked = retrieval._fuse_and_rerank(
                question["question"],
                semantic_ranked,
                keyword_ranked,
            )
            results_by_question[question["id"]] = ranked[:TOP_K]
        results_by_method[method] = {
            "retrieval_method": method,
            "top_k": TOP_K,
            "min_similarity": retrieval.DEFAULT_MIN_SIMILARITY,
            **calculate_retrieval_metrics(questions, results_by_question),
        }
    return {
        "embedding_model": model_name,
        "methods": results_by_method,
        "comparison": _metric_differences(
            results_by_method["semantic"],
            results_by_method["hybrid"],
        ),
    }


def evaluate_chunk_size_configurations(
    questions: Sequence[Mapping[str, Any]],
    sources: Mapping[str, ingestion.ExtractedDocument],
    *,
    model_name: str,
    dataset_path: Path | str = DATASET_PATH,
    embed_texts: Callable[..., Sequence[Sequence[float]]],
) -> dict[str, Any]:
    """Evaluate alternative chunking entirely in memory; no ORM writes occur."""
    query_texts = [question["question"] for question in questions]
    query_vectors_list = list(embed_texts(query_texts, model_name=model_name))
    if len(query_vectors_list) != len(questions):
        raise ValueError("Embedding model returned an invalid query count.")
    query_vectors = {
        question["id"]: vector
        for question, vector in zip(questions, query_vectors_list)
    }

    configurations = []
    for config in CHUNK_CONFIGURATIONS:
        chunks, counts = _in_memory_chunks(
            sources,
            chunk_size=config["chunk_size"],
            chunk_overlap=config["chunk_overlap"],
        )
        chunk_vectors = []
        texts = [chunk.text for chunk in chunks]
        for offset in range(0, len(texts), embeddings.DEFAULT_BATCH_SIZE):
            chunk_vectors.extend(
                embed_texts(
                    texts[offset : offset + embeddings.DEFAULT_BATCH_SIZE],
                    model_name=model_name,
                )
            )
        if len(chunk_vectors) != len(chunks):
            raise ValueError("Embedding model returned an invalid chunk count.")
        for chunk, vector in zip(chunks, chunk_vectors):
            chunk.embedding = list(vector)
            chunk.embedding_model = model_name
            chunk.embedding_text_sha256 = embeddings._text_digest(chunk.text)

        results = _evaluate_in_memory_configuration(
            questions,
            chunks,
            query_vectors,
            model_name=model_name,
        )
        configurations.append(
            {
                "configuration": {
                    **config,
                    "unit": "characters",
                },
                "chunk_count": len(chunks),
                "chunk_counts_by_source": counts,
                "methods": results["methods"],
                "comparison": results["comparison"],
            }
        )
    default_configuration = next(
        entry
        for entry in configurations
        if entry["configuration"]["name"] == "current_default"
    )
    differences = {}
    for configuration in configurations:
        name = configuration["configuration"]["name"]
        if name == "current_default":
            continue
        differences[name] = {
            "chunk_count_delta_vs_current_default": (
                configuration["chunk_count"]
                - default_configuration["chunk_count"]
            ),
            "methods": {
                method: {
                    metric: (
                        configuration["methods"][method]["aggregate"][metric]
                        - default_configuration["methods"][method]["aggregate"][metric]
                    )
                    for metric in configuration["methods"][method]["aggregate"]
                }
                for method in RETRIEVAL_METHODS
            },
        }
    return {
        "report_version": 1,
        "evaluation_type": "in_memory_chunk_size_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": Path(dataset_path).as_posix(),
            "question_count": len(questions),
            "question_ids": [question["id"] for question in questions],
        },
        "corpus": {
            "source_count": len(sources),
            "source_hashes": {
                filename: source.content_sha256
                for filename, source in sorted(sources.items())
            },
            "storage": "in-memory only; PolicyDocument and PolicyChunk records are not modified",
        },
        "embedding_model": model_name,
        "top_k": TOP_K,
        "metric_cutoffs": list(METRIC_CUTOFFS),
        "keyword_ranker": "in-process BM25 on alternate in-memory chunks",
        "configurations": configurations,
        "differences_vs_current_default": differences,
    }


def render_markdown_report(report: Mapping[str, Any]) -> str:
    methods = report["methods"]
    lines = [
        "# Clinic FAQ retrieval evaluation",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Questions: {report['dataset']['question_count']}",
        f"- Embedding model: `{report['embedding_model']}`",
        f"- Top-K: {report['top_k']}",
        f"- Indexed sources: {report['corpus']['source_count']}",
        "",
        "## Semantic-only versus hybrid",
        "",
        "| Method | Recall@1 | Recall@3 | Recall@5 | HitRate@1 | HitRate@3 | HitRate@5 | MRR | Source precision@5 | Source recall@5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in RETRIEVAL_METHODS:
        values = methods[method]["aggregate"]
        lines.append(
            "| "
            + " | ".join(
                [
                    method,
                    *(
                        f"{values[f'recall_at_{cutoff}']:.3f}"
                        for cutoff in METRIC_CUTOFFS
                    ),
                    *(
                        f"{values[f'hitrate_at_{cutoff}']:.3f}"
                        for cutoff in METRIC_CUTOFFS
                    ),
                    f"{values['reciprocal_rank']:.3f}",
                    f"{values['source_precision_at_5']:.3f}",
                    f"{values['source_recall_at_5']:.3f}",
                ]
            )
            + " |"
        )
    lines.extend(["", "Hybrid minus semantic; positive values favor hybrid:", ""])
    lines.append("| Metric | Semantic | Hybrid | Difference |")
    lines.append("|---|---:|---:|---:|")
    for metric, difference in report["comparison"]["metrics"].items():
        lines.append(
            f"| {metric} | {difference['semantic']:.3f} | "
            f"{difference['hybrid']:.3f} | "
            f"{difference['hybrid_minus_semantic']:+.3f} |"
        )
    lines.extend(
        [
            "",
            "Per-question metric outcomes (hybrid improved / regressed / unchanged):",
            "",
        ]
    )
    for metric, outcomes in report["comparison"]["per_question_metric_outcomes"].items():
        lines.append(
            f"- {metric}: {outcomes['improved']} / {outcomes['regressed']} / "
            f"{outcomes['unchanged']}"
        )
    lines.extend(
        [
            "",
            "## Per-question retrieval results",
            "",
            "| ID | Expected sources | Semantic sources@5 | Hybrid sources@5 |",
            "|---|---|---|---|",
        ]
    )
    semantic_rows = {
        row["question_id"]: row for row in methods["semantic"]["questions"]
    }
    hybrid_rows = {row["question_id"]: row for row in methods["hybrid"]["questions"]}
    for question_id in report["dataset"]["question_ids"]:
        expected = semantic_rows[question_id]["expected_sources"]
        semantic_sources = semantic_rows[question_id]["retrieved_source_filenames"]
        hybrid_sources = hybrid_rows[question_id]["retrieved_source_filenames"]
        lines.append(
            f"| {question_id} | {', '.join(expected)} | "
            f"{', '.join(semantic_sources)} | {', '.join(hybrid_sources)} |"
        )

    if "chunk_size_configurations" in report:
        lines.extend(
            [
                "",
                "## Chunk-size comparison",
                "",
                "Alternate chunks were embedded and ranked in memory; no document or chunk rows were changed.",
                "",
                "| Configuration | Size / overlap (characters) | Chunks | Mode | Recall@1 | Recall@3 | Recall@5 | MRR | Precision@5 | Recall@5 |",
                "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for config in report["chunk_size_configurations"]:
            for method in RETRIEVAL_METHODS:
                values = config["methods"][method]["aggregate"]
                settings = config["configuration"]
                lines.append(
                    f"| {settings['name']} | {settings['chunk_size']} / "
                    f"{settings['chunk_overlap']} | {config['chunk_count']} | "
                    f"{method} | "
                    + " | ".join(
                        f"{values[f'recall_at_{cutoff}']:.3f}"
                        for cutoff in METRIC_CUTOFFS
                    )
                    + f" | {values['reciprocal_rank']:.3f} | "
                    f"{values['source_precision_at_5']:.3f} | "
                    f"{values['source_recall_at_5']:.3f} |"
                )
        current = next(
            config
            for config in report["chunk_size_configurations"]
            if config["configuration"]["name"] == "current_default"
        )
        same_chunk_distribution = all(
            config["chunk_counts_by_source"] == current["chunk_counts_by_source"]
            for config in report["chunk_size_configurations"]
        )
        if same_chunk_distribution:
            lines.extend(
                [
                    "",
                    "Observed chunk-size effect: all three settings produced the "
                    f"same {current['chunk_count']} chunks "
                    f"({len(current['chunk_counts_by_source'])} source chunks); "
                    "there was no measured chunk-count or ranking change between "
                    "sizes for this short corpus.",
                ]
            )
        semantic = current["methods"]["semantic"]["aggregate"]
        hybrid = current["methods"]["hybrid"]["aggregate"]
        lines.extend(
            [
                "",
                "Observed in-memory keyword/hybrid trade-off at the current "
                f"chunk size: Recall@1 {hybrid['recall_at_1']:.3f} versus "
                f"semantic {semantic['recall_at_1']:.3f}; MRR "
                f"{hybrid['reciprocal_rank']:.3f} versus "
                f"{semantic['reciprocal_rank']:.3f}. These alternate-chunk "
                "keyword trials use in-process BM25, not PostgreSQL SearchRank.",
            ]
        )
    return "\n".join(lines) + "\n"


def run_evaluation(
    *,
    dataset_path: Path | str = DATASET_PATH,
    report_json_path: Path | str = REPORT_JSON_PATH,
    report_markdown_path: Path | str = REPORT_MARKDOWN_PATH,
    chunk_report_path: Path | str = CHUNK_REPORT_PATH,
    retrieve: Callable[..., Sequence[Any]] = retrieval.retrieve_policy_chunks,
    embed_texts: Callable[..., Sequence[Sequence[float]]] = embeddings.embed_texts,
) -> dict[str, Any]:
    """Run semantic/hybrid and in-memory chunk-size retrieval evaluations."""
    sources = load_approved_sources()
    questions = load_and_validate_questions(dataset_path, sources=sources)
    corpus = _live_corpus_context(sources)
    model_name = embeddings.load_embedding_config()

    # Prevent an evaluation run from initiating a model download.
    original_hub_offline = os.environ.get("HF_HUB_OFFLINE")
    original_transformers_offline = os.environ.get("TRANSFORMERS_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        report = evaluate_retrieval_methods(
            questions,
            model_name=model_name,
            corpus_context=corpus,
            dataset_path=dataset_path,
            retrieve=retrieve,
        )
        chunk_report = evaluate_chunk_size_configurations(
            questions,
            sources,
            model_name=model_name,
            dataset_path=dataset_path,
            embed_texts=embed_texts,
        )
    finally:
        if original_hub_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = original_hub_offline
        if original_transformers_offline is None:
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
        else:
            os.environ["TRANSFORMERS_OFFLINE"] = original_transformers_offline

    report["chunk_size_configurations"] = chunk_report["configurations"]
    report["chunk_size_differences_vs_current_default"] = (
        chunk_report["differences_vs_current_default"]
    )
    for destination, content in (
        (
            Path(report_json_path),
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        ),
        (Path(report_markdown_path), render_markdown_report(report)),
        (
            Path(chunk_report_path),
            json.dumps(chunk_report, indent=2, ensure_ascii=False) + "\n",
        ),
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return report
