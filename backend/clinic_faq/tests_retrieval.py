import math
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from . import embeddings, ingestion
from .models import PolicyChunk, PolicyDocument
from .retrieval import retrieve_policy_chunks


class PolicyRetrievalTests(TestCase):
    model_name = embeddings.DEFAULT_EMBEDDING_MODEL
    environment = {"CLINIC_FAQ_EMBEDDING_MODEL": model_name}

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.approved_directory = Path(self.temporary_directory.name)
        directory_patch = patch.object(
            ingestion,
            "APPROVED_POLICY_DIR",
            self.approved_directory,
        )
        directory_patch.start()
        self.addCleanup(directory_patch.stop)

        self.source = self.approved_directory / "synthetic-policy.md"
        self.write_source("Fictional policy text. " * 20)
        ingestion.ingest_document(self.source, chunk_size=80, overlap=10)
        self.chunks = list(PolicyChunk.objects.order_by("chunk_index"))

    def write_source(self, text):
        self.source.write_text(
            f"# Synthetic scheduling policy\n\n{text}\n",
            encoding="utf-8",
        )

    def set_embedding(self, chunk, vector, *, model_name=None, digest=None):
        chunk.embedding = vector
        chunk.embedding_model = model_name or self.model_name
        chunk.embedding_text_sha256 = (
            digest if digest is not None else embeddings._text_digest(chunk.text)
        )
        chunk.save(
            update_fields=[
                "embedding",
                "embedding_model",
                "embedding_text_sha256",
            ]
        )

    @staticmethod
    def basis_vector(similarity, dimension=embeddings.DEFAULT_EMBEDDING_DIMENSION):
        remainder = math.sqrt(max(0.0, 1 - similarity**2))
        return [similarity, remainder] + [0.0] * (dimension - 2)

    def retrieve(self, *args, **kwargs):
        with patch.dict(os.environ, self.environment, clear=True):
            return retrieve_policy_chunks(*args, **kwargs)

    def test_ranks_by_cosine_similarity_and_returns_source_metadata(self):
        for chunk, score in zip(self.chunks[:3], (0.25, 0.95, 0.7)):
            self.set_embedding(chunk, self.basis_vector(score))

        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch(
                "clinic_faq.embeddings.embed_query",
                return_value=self.basis_vector(1.0),
            ) as embed_query,
        ):
            results = retrieve_policy_chunks("When should I schedule?")

        self.assertEqual([result.chunk_id for result in results], [
            self.chunks[1].pk,
            self.chunks[2].pk,
            self.chunks[0].pk,
        ])
        self.assertEqual(results[0].source_title, "Synthetic scheduling policy")
        self.assertEqual(results[0].source_filename, self.source.name)
        self.assertEqual(results[0].text, self.chunks[1].text)
        self.assertAlmostEqual(results[0].similarity, 0.95)
        embed_query.assert_called_once_with(
            "When should I schedule?",
            model_name=self.model_name,
        )

    def test_top_k_and_minimum_similarity_are_applied(self):
        for chunk, score in zip(self.chunks[:3], (0.35, 0.85, 0.6)):
            self.set_embedding(chunk, self.basis_vector(score))
        with patch(
            "clinic_faq.embeddings.embed_query",
            return_value=self.basis_vector(1.0),
        ):
            results = self.retrieve(
                "Policy question",
                top_k=1,
                min_similarity=0.5,
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk_id, self.chunks[1].pk)

    def test_empty_knowledge_base_returns_without_embedding_query(self):
        PolicyDocument.objects.all().delete()
        with patch("clinic_faq.embeddings.embed_query") as embed_query:
            self.assertEqual(self.retrieve("Policy question"), [])
        embed_query.assert_not_called()

    def test_missing_stale_and_wrong_model_embeddings_are_ignored(self):
        self.set_embedding(
            self.chunks[0],
            self.basis_vector(1.0),
            model_name="another-local-model",
        )
        self.set_embedding(
            self.chunks[1],
            self.basis_vector(1.0),
            digest="0" * 64,
        )
        self.chunks[2].embedding = None
        self.chunks[2].save(update_fields=["embedding"])

        with patch("clinic_faq.embeddings.embed_query") as embed_query:
            self.assertEqual(self.retrieve("Policy question"), [])
        embed_query.assert_not_called()

    def test_invalid_and_wrong_dimension_embeddings_are_ignored(self):
        self.set_embedding(self.chunks[0], ["invalid", 0.0])
        self.set_embedding(self.chunks[1], [1.0, 0.0])
        with patch("clinic_faq.embeddings.embed_query") as embed_query:
            self.assertEqual(self.retrieve("Policy question"), [])
        embed_query.assert_not_called()

    def test_query_dimension_mismatch_is_ignored(self):
        self.set_embedding(self.chunks[0], self.basis_vector(1.0))
        with patch("clinic_faq.embeddings.embed_query", return_value=[1.0, 0.0]):
            self.assertEqual(self.retrieve("Policy question"), [])

    def test_only_chunks_verified_against_approved_sources_are_retrieved(self):
        approved_chunk = self.chunks[0]
        self.set_embedding(approved_chunk, self.basis_vector(1.0))
        outside_document = PolicyDocument.objects.create(
            source_filename="external.md",
            title="Unapproved document",
            content_sha256="a" * 64,
            chunk_size=100,
            chunk_overlap=10,
        )
        outside_chunk = PolicyChunk.objects.create(
            document=outside_document,
            chunk_index=0,
            text="This content is not in the approved directory.",
            embedding=self.basis_vector(1.0),
            embedding_model=self.model_name,
            embedding_text_sha256=embeddings._text_digest(
                "This content is not in the approved directory."
            ),
        )

        with patch(
            "clinic_faq.embeddings.embed_query",
            return_value=self.basis_vector(1.0),
        ):
            results = self.retrieve("Policy question")

        result_ids = {result.chunk_id for result in results}
        self.assertIn(approved_chunk.pk, result_ids)
        self.assertNotIn(outside_chunk.pk, result_ids)

    def test_local_query_embedding_failure_is_safely_propagated(self):
        self.set_embedding(self.chunks[0], self.basis_vector(1.0))
        error = embeddings.EmbeddingModelError("generation", "RuntimeError")
        with patch("clinic_faq.embeddings.embed_query", side_effect=error):
            with self.assertRaises(embeddings.EmbeddingModelError):
                self.retrieve("Policy question")

    def test_invalid_query_and_retrieval_options_are_rejected(self):
        for query, options in (
            ("", {}),
            ("Policy question", {"top_k": 0}),
            ("Policy question", {"top_k": True}),
            ("Policy question", {"min_similarity": 1.1}),
            ("Policy question", {"min_similarity": float("nan")}),
        ):
            with self.subTest(query=query, options=options):
                with self.assertRaises(ValueError):
                    self.retrieve(query, **options)

    def test_empty_model_configuration_is_rejected(self):
        with patch.dict(
            os.environ,
            {"CLINIC_FAQ_EMBEDDING_MODEL": ""},
            clear=True,
        ):
            with self.assertRaises(embeddings.EmbeddingConfigurationError):
                retrieve_policy_chunks("Policy question")
