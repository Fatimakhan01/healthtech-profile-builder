import hashlib
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from . import embeddings, ingestion
from .models import PolicyChunk, PolicyDocument


class PolicyEmbeddingTests(TestCase):
    environment = {
        "CLINIC_FAQ_EMBEDDING_MODEL": embeddings.DEFAULT_EMBEDDING_MODEL,
    }

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

        self.source = self.approved_directory / "test-policy.md"
        self.write_source("First approved paragraph. " * 20)
        ingestion.ingest_document(self.source, chunk_size=80, overlap=10)

    def write_source(self, body):
        self.source.write_text(
            f"# Synthetic test policy\n\n{body}\n",
            encoding="utf-8",
        )

    @staticmethod
    def response(vectors):
        return vectors

    def successful_client(self, dimension=embeddings.DEFAULT_EMBEDDING_DIMENSION):
        encode = Mock()
        encode.side_effect = lambda texts, **kwargs: self.response(
            [[float(index + 1)] * dimension for index, _ in enumerate(texts)]
        )
        return SimpleNamespace(encode=encode)

    def run_embedding(self, client, **kwargs):
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=client) as factory,
        ):
            result = embeddings.embed_approved_chunks(**kwargs)
        return result, factory

    def test_successful_embedding_storage_and_bounded_requests(self):
        client = self.successful_client()

        result, factory = self.run_embedding(client, batch_size=2)

        chunks = list(PolicyChunk.objects.order_by("chunk_index"))
        self.assertEqual(result.embedded_chunks, len(chunks))
        self.assertGreater(result.batch_count, 1)
        self.assertEqual(
            factory.call_args.args[0],
            embeddings.DEFAULT_EMBEDDING_MODEL,
        )
        self.assertTrue(
            all(
                chunk.embedding_model == embeddings.DEFAULT_EMBEDDING_MODEL
                for chunk in chunks
            )
        )
        self.assertTrue(
            all(
                len(chunk.embedding) == embeddings.DEFAULT_EMBEDDING_DIMENSION
                for chunk in chunks
            )
        )
        self.assertTrue(all(len(chunk.embedding_text_sha256) == 64 for chunk in chunks))
        self.assertTrue(
            all(
                chunk.embedding_text_sha256
                == hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
                for chunk in chunks
            )
        )
        self.assertTrue(
            all(
                call.kwargs["batch_size"] <= 2
                for call in client.encode.call_args_list
            )
        )
        self.assertTrue(
            all(
                call.kwargs["normalize_embeddings"] is True
                for call in client.encode.call_args_list
            )
        )

    def test_repeat_execution_skips_current_embeddings_without_model_calls(self):
        first_client = self.successful_client()
        self.run_embedding(first_client)

        model_loader = patch("clinic_faq.embeddings._load_model")
        with (
            patch.dict(os.environ, self.environment, clear=True),
            model_loader as factory,
        ):
            result = embeddings.embed_approved_chunks()

        self.assertEqual(result.embedded_chunks, 0)
        self.assertEqual(result.skipped_chunks, PolicyChunk.objects.count())
        factory.assert_not_called()

    def test_changed_source_text_is_reingested_then_reembedded(self):
        initial_client = self.successful_client()
        self.run_embedding(initial_client)
        old_ids = set(PolicyChunk.objects.values_list("id", flat=True))

        self.write_source("Changed approved paragraph. " * 20)
        ingestion.ingest_document(self.source, chunk_size=80, overlap=10)
        changed_ids = set(PolicyChunk.objects.values_list("id", flat=True))
        self.assertTrue(old_ids.isdisjoint(changed_ids))
        self.assertTrue(
            all(chunk.embedding is None for chunk in PolicyChunk.objects.all())
        )

        client = self.successful_client()
        result, _ = self.run_embedding(client)

        self.assertEqual(result.embedded_chunks, PolicyChunk.objects.count())
        self.assertTrue(
            all(chunk.embedding_text_sha256 for chunk in PolicyChunk.objects.all())
        )

    def test_changed_embedding_model_reembeds_existing_chunks(self):
        first_client = self.successful_client()
        self.run_embedding(first_client)
        changed_environment = {
            **self.environment,
            "CLINIC_FAQ_EMBEDDING_MODEL": "sentence-transformers/new-test-model",
        }
        client = self.successful_client()

        with (
            patch.dict(os.environ, changed_environment, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=client),
        ):
            result = embeddings.embed_approved_chunks()

        self.assertEqual(result.embedded_chunks, PolicyChunk.objects.count())
        self.assertTrue(
            all(
                chunk.embedding_model == "sentence-transformers/new-test-model"
                for chunk in PolicyChunk.objects.all()
            )
        )

    def test_default_model_needs_no_api_key(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=self.successful_client()),
        ):
            result = embeddings.embed_approved_chunks()
        self.assertEqual(result.embedded_chunks, PolicyChunk.objects.count())
        self.assertTrue(
            all(
                chunk.embedding_model == embeddings.DEFAULT_EMBEDDING_MODEL
                for chunk in PolicyChunk.objects.all()
            )
        )

    def test_empty_model_configuration_is_rejected(self):
        with self.assertRaises(embeddings.EmbeddingConfigurationError):
            embeddings.load_embedding_config(
                {"CLINIC_FAQ_EMBEDDING_MODEL": ""}
            )

    def test_local_encoding_failure_does_not_mark_chunks_embedded(self):
        client = SimpleNamespace(encode=Mock(side_effect=RuntimeError("local failure")))
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=client),
        ):
            with self.assertRaises(embeddings.EmbeddingModelError):
                embeddings.embed_approved_chunks()

        self.assertTrue(
            all(chunk.embedding is None for chunk in PolicyChunk.objects.all())
        )

    def test_local_model_load_failure_is_reported_without_api_calls(self):
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch(
                "clinic_faq.embeddings._load_model",
                side_effect=embeddings.EmbeddingModelError(
                    "model loading",
                    "OSError",
                ),
            ),
        ):
            with self.assertRaises(embeddings.EmbeddingModelError) as raised:
                embeddings.embed_approved_chunks()
        self.assertEqual(raised.exception.operation, "model loading")

        self.assertTrue(
            all(chunk.embedding is None for chunk in PolicyChunk.objects.all())
        )

    def test_malformed_vectors_are_rejected_without_writing(self):
        invalid_batches = (
            [[], [0.1, 0.2]],
            [[0.1, float("nan")], [0.3, 0.4]],
            [[0.1, 0.2], [0.3, float("inf")]],
            [[0.1, 0.2], [0.3]],
            [["not numeric"], [0.3]],
        )

        for vectors in invalid_batches:
            with self.subTest(vectors=vectors):
                client = SimpleNamespace(encode=Mock(return_value=self.response(vectors)))
                with (
                    patch.dict(os.environ, self.environment, clear=True),
                    patch(
                        "clinic_faq.embeddings._load_model",
                        return_value=client,
                    ),
                ):
                    with self.assertRaises(embeddings.EmbeddingResponseError):
                        embeddings.embed_approved_chunks(batch_size=2)
                self.assertTrue(
                    all(
                        chunk.embedding is None
                        for chunk in PolicyChunk.objects.all()
                    )
                )

    def test_dimension_change_between_batches_fails_before_saving_second_batch(self):
        client = SimpleNamespace(encode=Mock())
        client.encode.side_effect = [
            self.response([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]),
            self.response([[0.7, 0.8], [0.9, 1.0]]),
        ]
        custom_model_environment = {
            "CLINIC_FAQ_EMBEDDING_MODEL": "sentence-transformers/test-model",
        }
        with (
            patch.dict(os.environ, custom_model_environment, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=client),
        ):
            with self.assertRaises(embeddings.EmbeddingResponseError):
                embeddings.embed_approved_chunks(batch_size=2)

        chunks = list(PolicyChunk.objects.order_by("chunk_index"))
        self.assertTrue(all(chunk.embedding is not None for chunk in chunks[:2]))
        self.assertTrue(all(chunk.embedding is None for chunk in chunks[2:4]))

    def test_only_chunks_matching_approved_source_are_sent(self):
        chunk = PolicyChunk.objects.order_by("chunk_index").first()
        chunk.text = "Arbitrary database text must not be sent."
        chunk.save(update_fields=["text"])
        client = self.successful_client()

        result, _ = self.run_embedding(client)

        sent_texts = [
            text
            for call in client.encode.call_args_list
            for text in call.args[0]
        ]
        self.assertNotIn("Arbitrary database text must not be sent.", sent_texts)
        self.assertEqual(result.skipped_chunks, 1)
        self.assertEqual(result.embedded_chunks, PolicyChunk.objects.count() - 1)

    def test_stale_source_file_is_not_sent(self):
        self.write_source("Changed on disk but not ingested.")
        model_loader = patch("clinic_faq.embeddings._load_model")
        with (
            patch.dict(os.environ, self.environment, clear=True),
            model_loader as factory,
        ):
            result = embeddings.embed_approved_chunks()

        self.assertEqual(result.skipped_documents, 1)
        self.assertEqual(result.embedded_chunks, 0)
        factory.assert_not_called()

    def test_batch_size_and_malformed_vector_shapes_are_validated(self):
        for size in (0, embeddings.MAX_BATCH_SIZE + 1, True):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    embeddings.embed_approved_chunks(
                        batch_size=size,
                        environ=self.environment,
                    )

        with self.assertRaises(embeddings.EmbeddingResponseError):
            embeddings._validate_vectors([0.1, 0.2], 2)

    def test_incomplete_local_model_output_does_not_save_embeddings(self):
        client = SimpleNamespace(encode=Mock(return_value={}))
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=client),
        ):
            with self.assertRaises(embeddings.EmbeddingResponseError):
                embeddings.embed_approved_chunks()
        self.assertTrue(
            all(chunk.embedding is None for chunk in PolicyChunk.objects.all())
        )

    def test_model_failure_logs_only_safe_error_type(self):
        secret_like_text = "sensitive-document-text"
        client = SimpleNamespace(
            encode=Mock(side_effect=RuntimeError(secret_like_text))
        )
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=client),
            self.assertLogs("clinic_faq.embeddings", level="ERROR") as captured,
        ):
            with self.assertRaises(embeddings.EmbeddingModelError) as raised:
                embeddings.embed_approved_chunks()

        self.assertEqual(raised.exception.operation, "generation")
        self.assertEqual(raised.exception.error_type, "RuntimeError")
        diagnostic = "\n".join(captured.output) + str(raised.exception)
        self.assertIn("generation", diagnostic)
        self.assertIn("RuntimeError", diagnostic)
        self.assertNotIn(secret_like_text, diagnostic)
        self.assertTrue(
            all(chunk.embedding is None for chunk in PolicyChunk.objects.all())
        )

    def test_query_embedding_uses_same_configured_local_model(self):
        client = self.successful_client()
        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch("clinic_faq.embeddings._load_model", return_value=client) as loader,
        ):
            vector = embeddings.embed_query("A fictional policy question")

        self.assertEqual(len(vector), embeddings.DEFAULT_EMBEDDING_DIMENSION)
        loader.assert_called_once_with(embeddings.DEFAULT_EMBEDDING_MODEL)
        client.encode.assert_called_once()
        self.assertEqual(
            client.encode.call_args.args[0],
            ["A fictional policy question"],
        )


class EmbeddingModelTests(TestCase):
    def test_embedding_fields_default_to_unembedded_state(self):
        document = PolicyDocument.objects.create(
            source_filename="stored.md",
            title="Stored synthetic policy",
            content_sha256="a" * 64,
            chunk_size=100,
            chunk_overlap=10,
        )
        chunk = PolicyChunk.objects.create(
            document=document,
            chunk_index=0,
            text="Fictional approved content.",
        )

        self.assertIsNone(chunk.embedding)
        self.assertEqual(chunk.embedding_model, "")
        self.assertEqual(chunk.embedding_text_sha256, "")
