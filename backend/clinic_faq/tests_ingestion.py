from io import StringIO
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from . import ingestion
from .models import PolicyChunk, PolicyDocument


class DocumentExtractionTests(TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.approved_directory = Path(self.temporary_directory.name)
        self.directory_patch = patch.object(
            ingestion,
            "APPROVED_POLICY_DIR",
            self.approved_directory,
        )
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)

    def write(self, filename, content):
        path = self.approved_directory / filename
        path.write_text(content, encoding="utf-8")
        return path

    def test_extracts_markdown_title_and_readable_text(self):
        path = self.write(
            "example.md",
            "# Fictional Scheduling Policy\n\n"
            "**Synthetic only.** Use the [booking page](https://example.test).",
        )

        extracted = ingestion.extract_document(path)

        self.assertEqual(extracted.source_filename, "example.md")
        self.assertEqual(extracted.title, "Fictional Scheduling Policy")
        self.assertEqual(
            extracted.text,
            "Synthetic only. Use the booking page.",
        )
        self.assertEqual(len(extracted.content_sha256), 64)

    def test_text_title_uses_filename_and_content_is_preserved(self):
        path = self.write("late_arrivals.txt", "Contact the fictional desk.\n")

        extracted = ingestion.extract_document(path)

        self.assertEqual(extracted.title, "late arrivals")
        self.assertEqual(extracted.text, "Contact the fictional desk.")

    def test_empty_document_is_rejected(self):
        path = self.write("empty.md", "# Empty\n\n  \n")

        with self.assertRaisesRegex(
            ingestion.PolicyIngestionError,
            "empty after text extraction",
        ):
            ingestion.extract_document(path)

    def test_unsupported_file_type_and_external_path_are_rejected(self):
        unsupported = self.write("policy.pdf", "not a PDF")
        outside = Path(self.temporary_directory.name).parent / "outside.txt"

        with self.assertRaisesRegex(ingestion.PolicyIngestionError, "Only .md and .txt"):
            ingestion.extract_document(unsupported)
        with self.assertRaisesRegex(
            ingestion.PolicyIngestionError,
            "direct files in the approved",
        ):
            ingestion.extract_document(outside)

    def test_chunk_boundaries_prefer_paragraphs_and_obey_maximum(self):
        text = (
            "First paragraph has several words.\n\n"
            "Second paragraph also has several words.\n\n"
            "Third paragraph concludes the document."
        )

        chunks = ingestion.chunk_text(text, chunk_size=55, overlap=0)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.strip() for chunk in chunks))
        self.assertTrue(all(len(chunk) <= 55 for chunk in chunks))
        self.assertIn("First paragraph", chunks[0])
        self.assertIn("Third paragraph", chunks[-1])

    def test_chunks_have_configured_word_boundary_overlap(self):
        text = " ".join(
            f"paragraph{index}" for index in range(50)
        )

        chunks = ingestion.chunk_text(text, chunk_size=70, overlap=18)

        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 70 for chunk in chunks))
        self.assertTrue(
            any(
                previous.split()[-1] in following
                for previous, following in zip(chunks, chunks[1:])
            )
        )

    def test_chunk_parameters_are_validated(self):
        with self.assertRaises(ValueError):
            ingestion.chunk_text("text", chunk_size=0)
        with self.assertRaises(ValueError):
            ingestion.chunk_text("text", chunk_size=10, overlap=10)
        self.assertEqual(ingestion.chunk_text("\n\n  "), [])


class PolicyIngestionPersistenceTests(TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.approved_directory = Path(self.temporary_directory.name)
        patcher = patch.object(
            ingestion,
            "APPROVED_POLICY_DIR",
            self.approved_directory,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_policy(self, body):
        path = self.approved_directory / "test-policy.md"
        path.write_text(
            f"# Test Policy\n\n**Synthetic only.**\n\n{body}\n",
            encoding="utf-8",
        )
        return path

    def test_ingestion_is_idempotent_and_retains_source_metadata(self):
        path = self.write_policy("First paragraph.\n\nSecond paragraph.")

        created_state, created_count = ingestion.ingest_document(
            path,
            chunk_size=50,
            overlap=5,
        )
        unchanged_state, unchanged_count = ingestion.ingest_document(
            path,
            chunk_size=50,
            overlap=5,
        )

        document = PolicyDocument.objects.get()
        chunks = list(document.chunks.all())
        self.assertEqual(created_state, "created")
        self.assertEqual(unchanged_state, "unchanged")
        self.assertEqual(created_count, unchanged_count)
        self.assertEqual(document.source_filename, "test-policy.md")
        self.assertEqual(document.title, "Test Policy")
        self.assertEqual(len(chunks), created_count)
        self.assertEqual(
            [chunk.chunk_index for chunk in chunks],
            list(range(created_count)),
        )
        self.assertTrue(all(chunk.document_id == document.id for chunk in chunks))

    def test_changed_document_replaces_chunks_without_duplicates(self):
        path = self.write_policy("Original text " * 20)
        state, _ = ingestion.ingest_document(path, chunk_size=60, overlap=10)
        document = PolicyDocument.objects.get()
        original_digest = document.content_sha256
        original_count = document.chunks.count()

        path.write_text(
            "# Updated Policy\n\n**Synthetic only.**\n\nNew replacement text.",
            encoding="utf-8",
        )
        updated_state, updated_count = ingestion.ingest_document(
            path,
            chunk_size=60,
            overlap=10,
        )

        document.refresh_from_db()
        self.assertEqual(state, "created")
        self.assertEqual(updated_state, "updated")
        self.assertNotEqual(document.content_sha256, original_digest)
        self.assertGreater(original_count, 1)
        self.assertEqual(PolicyDocument.objects.count(), 1)
        self.assertEqual(document.chunks.count(), updated_count)
        self.assertEqual(document.title, "Updated Policy")
        self.assertIn(
            "New replacement text.",
            " ".join(document.chunks.values_list("text", flat=True)),
        )
        self.assertNotIn(
            "Original text",
            " ".join(document.chunks.values_list("text", flat=True)),
        )

    def test_changed_chunk_configuration_rebuilds_chunks(self):
        path = self.write_policy("A repeated source phrase. " * 20)
        ingestion.ingest_document(path, chunk_size=80, overlap=10)
        document = PolicyDocument.objects.get()
        original_count = document.chunks.count()

        updated_state, _ = ingestion.ingest_document(
            path,
            chunk_size=40,
            overlap=5,
        )

        document.refresh_from_db()
        self.assertEqual(updated_state, "updated")
        self.assertEqual(document.chunk_size, 40)
        self.assertEqual(document.chunk_overlap, 5)
        self.assertGreater(document.chunks.count(), original_count)
        self.assertEqual(
            document.chunks.count(),
            document.chunks.values("chunk_index").distinct().count(),
        )

    def test_command_reports_processed_unchanged_and_updated_counts(self):
        self.write_policy("First version.")
        output = StringIO()

        call_command("ingest_clinic_policies", stdout=output)
        output.seek(0)
        first_run = output.read()
        output.seek(0)
        output.truncate()
        call_command("ingest_clinic_policies", stdout=output)
        output.seek(0)
        second_run = output.read()

        self.assertIn("processed=1, created=1", first_run)
        self.assertIn("unchanged=1, updated=0", second_run)

    def test_command_fails_on_unsupported_file(self):
        (self.approved_directory / "unexpected.pdf").write_text(
            "not approved",
            encoding="utf-8",
        )

        with patch(
            "clinic_faq.ingestion.APPROVED_POLICY_DIR",
            self.approved_directory,
        ):
            with self.assertRaises(CommandError):
                call_command("ingest_clinic_policies")
