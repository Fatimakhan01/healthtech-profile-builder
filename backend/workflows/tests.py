import csv
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from . import services
from .models import WorkflowJob


User = get_user_model()


class WorkflowQueueTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="workflow-admin@example.com",
            password="A-strong-but-not-real-password-834!",
        )

    def create_job(self, job_type=WorkflowJob.JobType.DOCUMENT_INDEXING):
        return WorkflowJob.objects.create(
            job_type=job_type,
            idempotency_hash=("a" * 63) + str(WorkflowJob.objects.count()),
            requested_by=self.admin,
        )

    def test_enqueue_is_idempotent_for_same_admin_key_and_job_type(self):
        first, created = services.enqueue_job(
            WorkflowJob.JobType.DOCUMENT_INDEXING,
            "index-key-0001",
            actor=self.admin,
        )
        repeated, repeated_created = services.enqueue_job(
            WorkflowJob.JobType.DOCUMENT_INDEXING,
            "index-key-0001",
            actor=self.admin,
        )

        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(WorkflowJob.objects.count(), 1)

    def test_idempotency_key_cannot_be_reused_for_another_job_type(self):
        services.enqueue_job(
            WorkflowJob.JobType.DOCUMENT_INDEXING,
            "same-key-0001",
            actor=self.admin,
        )
        with self.assertRaises(services.IdempotencyConflict):
            services.enqueue_job(
                WorkflowJob.JobType.BATCH_PREDICTION,
                "same-key-0001",
                actor=self.admin,
            )

    def test_enqueue_rejects_bad_key_and_non_admin_actor(self):
        with self.assertRaises(ValueError):
            services.enqueue_job(
                WorkflowJob.JobType.DOCUMENT_INDEXING,
                "short",
                actor=self.admin,
            )
        standard = User.objects.create_user(
            email="workflow-user@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        with self.assertRaises(PermissionError):
            services.enqueue_job(
                WorkflowJob.JobType.DOCUMENT_INDEXING,
                "valid-key-0001",
                actor=standard,
            )

    @patch(
        "workflows.services._run_job",
        return_value={"documents_processed": 3, "chunks_embedded": 7},
    )
    def test_worker_claims_and_completes_job_with_duration(self, run_job):
        job = self.create_job()

        completed = services.process_next_job()

        run_job.assert_called_once()
        self.assertEqual(completed.pk, job.pk)
        self.assertEqual(completed.status, WorkflowJob.Status.SUCCEEDED)
        self.assertEqual(completed.attempt_count, 1)
        self.assertIsNotNone(completed.started_at)
        self.assertIsNotNone(completed.finished_at)
        self.assertEqual(
            completed.result,
            {"documents_processed": 3, "chunks_embedded": 7},
        )

    def test_worker_marks_job_running_before_execution(self):
        job = self.create_job()

        def verify_running(current_job):
            stored = WorkflowJob.objects.get(pk=current_job.pk)
            self.assertEqual(stored.status, WorkflowJob.Status.RUNNING)
            return {"documents_processed": 1}

        with patch("workflows.services._run_job", side_effect=verify_running):
            completed = services.process_next_job()

        self.assertEqual(completed.status, WorkflowJob.Status.SUCCEEDED)
        self.assertEqual(completed.pk, job.pk)

    @patch("workflows.services._run_job", side_effect=ConnectionError("private detail"))
    def test_transient_failure_requeues_then_succeeds_idempotently(self, run_job):
        job = self.create_job()

        retry = services.process_next_job()
        self.assertEqual(retry.status, WorkflowJob.Status.QUEUED)
        self.assertEqual(retry.attempt_count, 1)
        self.assertEqual(retry.failure_code, "transient_error")
        self.assertNotIn("private detail", retry.failure_code)

        run_job.side_effect = None
        run_job.return_value = {"safe": "aggregate"}
        completed = services.process_next_job()
        self.assertEqual(completed.status, WorkflowJob.Status.SUCCEEDED)
        self.assertEqual(completed.attempt_count, 2)

    @patch("workflows.services._run_job", side_effect=TimeoutError("secret"))
    def test_transient_failures_stop_after_maximum_attempts(self, _run_job):
        job = self.create_job()

        for _ in range(services.MAX_ATTEMPTS):
            failed = services.process_next_job()

        self.assertEqual(failed.pk, job.pk)
        self.assertEqual(failed.status, WorkflowJob.Status.FAILED)
        self.assertEqual(failed.attempt_count, services.MAX_ATTEMPTS)
        self.assertEqual(failed.failure_code, "retries_exhausted")
        self.assertNotIn("secret", failed.failure_code)

    @patch(
        "workflows.services._run_job",
        side_effect=services.PermanentWorkflowError("synthetic_dataset_schema_invalid"),
    )
    def test_permanent_failure_is_terminal_and_sanitized(self, _run_job):
        self.create_job()
        failed = services.process_next_job()

        self.assertEqual(failed.status, WorkflowJob.Status.FAILED)
        self.assertEqual(failed.attempt_count, 1)
        self.assertEqual(failed.failure_code, "synthetic_dataset_schema_invalid")

    def test_worker_returns_none_for_an_empty_queue(self):
        self.assertIsNone(services.process_next_job())

    @patch("workflows.services.ingest_approved_documents")
    @patch("workflows.services.embed_approved_chunks")
    @patch("workflows.services.load_embedding_config", return_value="local-model")
    def test_document_indexing_reuses_existing_ingestion_and_embedding(
        self,
        _load_model,
        embed,
        ingest,
    ):
        ingest.return_value = SimpleNamespace(
            processed=4,
            created=1,
            updated=1,
            unchanged=2,
            deactivated=0,
            chunks_created=3,
        )
        embed.return_value = SimpleNamespace(
            embedded_chunks=3,
            skipped_chunks=1,
        )

        result = services._run_document_indexing()

        ingest.assert_called_once_with()
        embed.assert_called_once_with()
        self.assertEqual(result["documents_processed"], 4)
        self.assertEqual(result["chunks_embedded"], 3)
        self.assertNotIn("source_filename", result)

    def test_batch_prediction_uses_aggregate_results_only_and_flags_drift(self):
        rows = [
            {
                "days_ahead": 10,
                "previous_no_shows": 0,
                "sms_reminder": "yes",
                "weekday": "Monday",
                "no_show": 0,
            },
            {
                "days_ahead": 20,
                "previous_no_shows": 1,
                "sms_reminder": "no",
                "weekday": "Friday",
                "no_show": 1,
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "synthetic.csv"
            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=[*services.PREDICTION_FEATURES, "no_show"],
                )
                writer.writeheader()
                writer.writerows(rows)
            with patch("workflows.services.BATCH_DATASET_PATH", path):
                with patch(
                    "workflows.services.NoShowPredictionView.post",
                    side_effect=[
                        SimpleNamespace(
                            status_code=200,
                            data={
                                "predicted_class": 1,
                                "probability_no_show": 0.8,
                                "model_version": "synthetic-model-v1",
                                "display_version": "No-Show Model v1",
                            },
                        ),
                        SimpleNamespace(
                            status_code=200,
                            data={
                                "predicted_class": 1,
                                "probability_no_show": 0.6,
                                "model_version": "synthetic-model-v1",
                                "display_version": "No-Show Model v1",
                            },
                        ),
                    ],
                ) as predict:
                    result = services._run_batch_prediction()

        self.assertEqual(predict.call_count, 2)
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["actual_label_distribution"]["no_show"], 1)
        self.assertEqual(result["prediction_distribution"]["no_show"], 2)
        self.assertEqual(result["absolute_rate_delta"], 0.5)
        self.assertEqual(result["drift_indicator"], "alert")
        self.assertEqual(result["mean_probability_no_show"], 0.7)
        self.assertNotIn("days_ahead", result)
        self.assertNotIn("patient", str(result).lower())

    def test_batch_prediction_rejects_unexpected_dataset_columns(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.csv"
            path.write_text("patient,days_ahead\nsynthetic,10\n", encoding="utf-8")
            with patch("workflows.services.BATCH_DATASET_PATH", path):
                with self.assertRaises(services.PermanentWorkflowError):
                    list(services._read_synthetic_rows())

    @patch("workflows.services.process_next_job", return_value=None)
    def test_worker_command_supports_single_pass(self, process):
        call_command("run_workflow_jobs", once=True, poll_seconds=1)
        process.assert_called_once_with()


class WorkflowAdminApiTests(TestCase):
    jobs_url = "/api/admin/workflows/jobs/"
    enqueue_url = "/api/admin/workflows/enqueue/"

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="workflow-admin-api@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.client = APIClient()
        self.client.force_login(self.admin)

    def test_admin_can_enqueue_job_and_repeat_request_is_idempotent(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "predict-batch-0001"}
        payload = {"job_type": WorkflowJob.JobType.BATCH_PREDICTION}

        first = self.client.post(self.enqueue_url, payload, format="json", **headers)
        second = self.client.post(self.enqueue_url, payload, format="json", **headers)

        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(first.data["created"])
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(second.data["created"])
        self.assertEqual(first.data["job"]["id"], second.data["job"]["id"])
        self.assertEqual(WorkflowJob.objects.count(), 1)

    def test_enqueue_requires_valid_idempotency_key_and_strict_body(self):
        missing_key = self.client.post(
            self.enqueue_url,
            {"job_type": WorkflowJob.JobType.DOCUMENT_INDEXING},
            format="json",
        )
        unexpected = self.client.post(
            self.enqueue_url,
            {"job_type": WorkflowJob.JobType.DOCUMENT_INDEXING, "payload": {}},
            format="json",
            HTTP_IDEMPOTENCY_KEY="document-job-0001",
        )
        self.assertEqual(missing_key.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unexpected.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enqueue_requires_csrf_for_admin_session_authentication(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        csrf_response = client.get("/api/admin/csrf/")
        csrf_token = csrf_response.data["csrf_token"]
        payload = {"job_type": WorkflowJob.JobType.DOCUMENT_INDEXING}
        idempotency_header = {"HTTP_IDEMPOTENCY_KEY": "csrf-index-job-0001"}

        rejected = client.post(
            self.enqueue_url,
            payload,
            format="json",
            **idempotency_header,
        )
        accepted = client.post(
            self.enqueue_url,
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
            **idempotency_header,
        )

        self.assertEqual(rejected.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(accepted.status_code, status.HTTP_202_ACCEPTED)

    def test_idempotency_conflict_returns_conflict_without_creating_job(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "conflict-key-0001"}
        self.client.post(
            self.enqueue_url,
            {"job_type": WorkflowJob.JobType.DOCUMENT_INDEXING},
            format="json",
            **headers,
        )

        response = self.client.post(
            self.enqueue_url,
            {"job_type": WorkflowJob.JobType.BATCH_PREDICTION},
            format="json",
            **headers,
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(WorkflowJob.objects.count(), 1)

    def test_audit_list_is_read_only_and_exposes_only_safe_job_fields(self):
        job = WorkflowJob.objects.create(
            job_type=WorkflowJob.JobType.BATCH_PREDICTION,
            idempotency_hash="b" * 64,
            requested_by=self.admin,
            status=WorkflowJob.Status.SUCCEEDED,
            result={
                "record_count": 2000,
                "prediction_distribution": {"no_show": 700},
            },
        )

        response = self.client.get(self.jobs_url)
        post_response = self.client.post(self.jobs_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(job.pk))
        self.assertIn("monitoring", response.data)
        self.assertNotIn("requested_by", response.data["results"][0])
        self.assertNotIn("idempotency_hash", response.data["results"][0])
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_standard_user_cannot_read_or_enqueue_workflow_jobs(self):
        standard_user = User.objects.create_user(
            email="workflow-standard@example.com",
            password="A-strong-but-not-real-password-834!",
        )
        self.client.force_login(standard_user)

        listing = self.client.get(self.jobs_url)
        enqueue = self.client.post(
            self.enqueue_url,
            {"job_type": WorkflowJob.JobType.DOCUMENT_INDEXING},
            format="json",
            HTTP_IDEMPOTENCY_KEY="document-job-0002",
        )

        self.assertEqual(listing.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(enqueue.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(WorkflowJob.objects.count(), 0)

    def test_anonymous_user_cannot_read_workflow_jobs(self):
        self.client.logout()

        response = self.client.get(self.jobs_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_monitoring_reports_counts_latency_failures_and_latest_distribution(self):
        WorkflowJob.objects.create(
            job_type=WorkflowJob.JobType.BATCH_PREDICTION,
            idempotency_hash="c" * 64,
            status=WorkflowJob.Status.SUCCEEDED,
            duration_ms=120,
            result={
                "record_count": 50,
                "absolute_rate_delta": 0.12,
                "drift_indicator": "alert",
            },
        )
        WorkflowJob.objects.create(
            job_type=WorkflowJob.JobType.DOCUMENT_INDEXING,
            idempotency_hash="d" * 64,
            status=WorkflowJob.Status.FAILED,
            duration_ms=80,
            failure_code="processing_error",
        )

        response = self.client.get(self.jobs_url)
        monitoring = response.data["monitoring"]

        self.assertEqual(monitoring["job_counts"]["succeeded"], 1)
        self.assertEqual(monitoring["job_counts"]["failed"], 1)
        self.assertEqual(monitoring["failure_rate"], 0.5)
        self.assertEqual(monitoring["execution_latency_ms"]["average"], 100)
        self.assertEqual(
            monitoring["latest_batch_prediction"]["drift_indicator"],
            "alert",
        )
