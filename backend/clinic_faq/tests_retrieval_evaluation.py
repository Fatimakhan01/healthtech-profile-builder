import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import TestCase

from . import embeddings, ingestion
from .models import PolicyChunk, PolicyDocument
from .retrieval import RetrievedPolicyChunk
from .retrieval_evaluation import (
    CHUNK_CONFIGURATIONS,
    DATASET_PATH,
    calculate_retrieval_metrics,
    evaluate_chunk_size_configurations,
    evaluate_retrieval_methods,
    load_and_validate_questions,
    load_approved_sources,
)


class RetrievalEvaluationTests(TestCase):
    def setUp(self):
        self.sources = load_approved_sources()
        self.questions = load_and_validate_questions(
            DATASET_PATH,
            sources=self.sources,
        )

    @staticmethod
    def passage(chunk_id, filename):
        return RetrievedPolicyChunk(
            chunk_id=chunk_id,
            source_title=filename,
            source_filename=filename,
            text=f"Evidence from {filename}",
            similarity=0.8,
        )

    def test_dataset_schema_evidence_and_expected_sources_are_valid(self):
        self.assertEqual(len(self.questions), 20)
        self.assertEqual(len({question["id"] for question in self.questions}), 20)
        distribution = Counter(
            filename
            for question in self.questions
            for filename in question["expected_sources"]
        )
        self.assertEqual(
            distribution,
            Counter(
                {
                    "appointment-scheduling.md": 5,
                    "cancellations.md": 5,
                    "late-arrivals.md": 5,
                    "reminders.md": 5,
                }
            ),
        )
        self.assertTrue(
            all(
                re.sub(r"\s+", " ", evidence.casefold())
                in re.sub(
                    r"\s+",
                    " ",
                    self.sources[filename].text.casefold(),
                )
                for question in self.questions
                for filename, evidence in question["evidence"].items()
            )
        )

    def test_dataset_rejects_evidence_not_found_in_expected_source(self):
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        payload["questions"][0]["evidence"]["appointment-scheduling.md"] = (
            "The policy promises same-day appointments."
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "questions.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence not found"):
                load_and_validate_questions(path, sources=self.sources)

    def test_recall_hit_rate_mrr_and_source_metrics_deduplicate_filenames(self):
        questions = [
            {
                "id": "q1",
                "question": "Question one",
                "expected_sources": ["a.md", "b.md"],
            },
            {
                "id": "q2",
                "question": "Question two",
                "expected_sources": ["c.md"],
            },
        ]
        results = {
            "q1": [
                self.passage(1, "a.md"),
                self.passage(2, "a.md"),
                self.passage(3, "other.md"),
            ],
            "q2": [],
        }

        measured = calculate_retrieval_metrics(questions, results)
        aggregate = measured["aggregate"]

        self.assertEqual(measured["questions"][0]["retrieved_source_filenames"], [
            "a.md",
            "other.md",
        ])
        self.assertEqual(aggregate["recall_at_1"], 0.25)
        self.assertEqual(aggregate["hitrate_at_1"], 0.5)
        self.assertEqual(aggregate["source_precision_at_3"], 0.25)
        self.assertEqual(aggregate["source_recall_at_3"], 0.25)
        self.assertEqual(aggregate["reciprocal_rank"], 0.5)

    def test_empty_results_and_empty_dataset_have_zero_metrics(self):
        question = {
            "id": "q1",
            "question": "Question one",
            "expected_sources": ["a.md"],
        }
        measured = calculate_retrieval_metrics([question], {"q1": []})
        self.assertEqual(measured["aggregate"]["recall_at_5"], 0.0)
        self.assertEqual(measured["aggregate"]["hitrate_at_5"], 0.0)
        self.assertEqual(measured["aggregate"]["source_precision_at_5"], 0.0)
        self.assertEqual(measured["aggregate"]["source_recall_at_5"], 0.0)
        self.assertEqual(measured["aggregate"]["reciprocal_rank"], 0.0)
        self.assertEqual(calculate_retrieval_metrics([], {})["question_count"], 0)

    def test_semantic_and_hybrid_evaluations_use_same_questions_and_parameters(self):
        question = self.questions[0]
        returned = self.passage(1, question["expected_sources"][0])
        retrieve = Mock(return_value=[returned])
        timestamp = datetime(2026, 11, 15, tzinfo=timezone.utc)

        report = evaluate_retrieval_methods(
            [question],
            model_name=embeddings.DEFAULT_EMBEDDING_MODEL,
            corpus_context={"source_count": 4},
            retrieve=retrieve,
            evaluation_time=timestamp,
        )

        self.assertEqual(report["evaluation_type"], "retrieval_only")
        self.assertFalse(report["generation_model_used"])
        self.assertEqual(report["generated_at"], timestamp.isoformat())
        self.assertEqual(report["methods"]["semantic"]["top_k"], 5)
        self.assertEqual(report["methods"]["hybrid"]["top_k"], 5)
        self.assertEqual(
            report["methods"]["semantic"]["aggregate"],
            report["methods"]["hybrid"]["aggregate"],
        )
        self.assertEqual(retrieve.call_count, 2)
        self.assertEqual(
            {call.kwargs["search_mode"] for call in retrieve.call_args_list},
            {"semantic", "hybrid"},
        )
        self.assertEqual(
            {call.kwargs["model_name"] for call in retrieve.call_args_list},
            {embeddings.DEFAULT_EMBEDDING_MODEL},
        )

    def test_metric_aggregation_is_deterministic(self):
        question = self.questions[0]
        results = {
            question["id"]: [
                self.passage(3, question["expected_sources"][0]),
                self.passage(4, "other.md"),
            ]
        }
        first = calculate_retrieval_metrics([question], results)
        second = calculate_retrieval_metrics([question], results)
        self.assertEqual(first, second)

    def test_chunk_size_comparison_is_in_memory_and_preserves_database_records(self):
        source = ingestion.ExtractedDocument(
            source_filename="appointment-scheduling.md",
            title="Synthetic Scheduling",
            text="Appointment scheduling details are available. " * 100,
            content_sha256="a" * 64,
        )
        question = {
            "id": "isolated-test",
            "question": "How can I request an appointment?",
            "expected_sources": ["appointment-scheduling.md"],
        }
        calls = []

        def fake_embed_texts(texts, *, model_name):
            calls.append((list(texts), model_name))
            return [[1.0, 0.0] for _ in texts]

        before_documents = list(
            PolicyDocument.objects.values_list(
                "pk",
                "content_sha256",
                "chunk_size",
                "chunk_overlap",
                "version",
            )
        )
        before_chunks = list(
            PolicyChunk.objects.values_list(
                "pk",
                "document_id",
                "text",
                "embedding",
            )
        )

        report = evaluate_chunk_size_configurations(
            [question],
            {source.source_filename: source},
            model_name="local-test-model",
            embed_texts=fake_embed_texts,
        )

        after_documents = list(
            PolicyDocument.objects.values_list(
                "pk",
                "content_sha256",
                "chunk_size",
                "chunk_overlap",
                "version",
            )
        )
        after_chunks = list(
            PolicyChunk.objects.values_list(
                "pk",
                "document_id",
                "text",
                "embedding",
            )
        )
        self.assertEqual(before_documents, after_documents)
        self.assertEqual(before_chunks, after_chunks)
        self.assertEqual(
            [entry["configuration"] for entry in report["configurations"]],
            [{**config, "unit": "characters"} for config in CHUNK_CONFIGURATIONS],
        )
        self.assertEqual(
            report["differences_vs_current_default"]["smaller"][
                "chunk_count_delta_vs_current_default"
            ],
            report["configurations"][0]["chunk_count"]
            - report["configurations"][1]["chunk_count"],
        )
        counts = [entry["chunk_count"] for entry in report["configurations"]]
        self.assertGreater(counts[0], counts[1])
        self.assertGreater(counts[1], counts[2])
        self.assertTrue(all(entry["methods"]["hybrid"]["question_count"] == 1 for entry in report["configurations"]))
        self.assertEqual(
            {model_name for _, model_name in calls},
            {"local-test-model"},
        )
        self.assertIn("in-memory only", report["corpus"]["storage"])

