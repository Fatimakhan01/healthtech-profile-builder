"""Persistent, idempotent queue and safe aggregate workflow results."""

import csv
import hashlib
import logging
import re
import socket
import time
from pathlib import Path
from types import SimpleNamespace

from django.db import OperationalError, transaction
from django.db.models import Avg, Count, Max, Min
from django.utils import timezone
from rest_framework import status as http_status

from clinic_faq.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingModelError,
    EmbeddingResponseError,
    embed_approved_chunks,
    load_embedding_config,
)
from clinic_faq.ingestion import PolicyIngestionError, ingest_approved_documents
from clinic_faq.models import PolicyDocument
from predictions.serializers import NoShowPredictionSerializer
from predictions.views import NoShowPredictionView

from .models import WorkflowJob


logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
MAX_IDEMPOTENCY_KEY_LENGTH = 128
DRIFT_RATE_DELTA_THRESHOLD = 0.1
BACKEND_DIR = Path(__file__).resolve().parents[1]
BATCH_DATASET_PATH = BACKEND_DIR / "ml" / "data" / "synthetic_appointments.csv"
IDEMPOTENCY_KEY_PATTERN = re.compile(
    rf"^[A-Za-z0-9._:-]{{8,{MAX_IDEMPOTENCY_KEY_LENGTH}}}$"
)
PREDICTION_FEATURES = (
    "days_ahead",
    "previous_no_shows",
    "sms_reminder",
    "weekday",
)


class WorkflowJobError(Exception):
    """A safe, expected failure while enqueueing or running a workflow."""


class IdempotencyConflict(WorkflowJobError):
    """An idempotency key was reused for a different job type."""


class TransientWorkflowError(WorkflowJobError):
    """A workflow failed for a condition that can safely be retried."""


class PermanentWorkflowError(WorkflowJobError):
    """A workflow failed for a non-transient condition."""


def _idempotency_hash(key: str, actor_id: int) -> str:
    if (
        not isinstance(key, str)
        or not IDEMPOTENCY_KEY_PATTERN.fullmatch(key)
    ):
        raise ValueError(
            "Idempotency-Key must be 8-128 ASCII letters, digits, dot, underscore, colon or hyphen."
        )
    return hashlib.sha256(f"{actor_id}:{key}".encode("utf-8")).hexdigest()


def enqueue_job(job_type: str, idempotency_key: str, *, actor):
    if job_type not in WorkflowJob.JobType.values:
        raise ValueError("Unsupported workflow job type.")
    if not getattr(actor, "is_authenticated", False) or not getattr(
        actor, "is_staff", False
    ):
        raise PermissionError("An authenticated administrator is required.")

    key_hash = _idempotency_hash(idempotency_key, actor.pk)
    try:
        with transaction.atomic():
            job, created = WorkflowJob.objects.get_or_create(
                idempotency_hash=key_hash,
                defaults={
                    "job_type": job_type,
                    "requested_by": actor,
                    "max_attempts": MAX_ATTEMPTS,
                },
            )
    except WorkflowJob.MultipleObjectsReturned as error:
        raise WorkflowJobError("Workflow idempotency state is invalid.") from error
    if job.job_type != job_type:
        raise IdempotencyConflict(
            "Idempotency-Key was already used for a different job type."
        )
    return job, created


def _run_document_indexing():
    ingestion = ingest_approved_documents()
    embeddings = embed_approved_chunks()
    pending = PolicyDocument.objects.filter(
        is_approved=True,
        is_active=True,
    ).exclude(indexing_status=PolicyDocument.IndexingStatus.INDEXED)
    if pending.exists():
        raise PermanentWorkflowError("indexing_incomplete")
    return {
        "documents_processed": ingestion.processed,
        "documents_created": ingestion.created,
        "documents_updated": ingestion.updated,
        "documents_unchanged": ingestion.unchanged,
        "documents_deactivated": ingestion.deactivated,
        "chunks_created": ingestion.chunks_created,
        "chunks_embedded": embeddings.embedded_chunks,
        "chunks_skipped": embeddings.skipped_chunks,
        "embedding_model": load_embedding_config(),
    }


def _read_synthetic_rows():
    try:
        source = BATCH_DATASET_PATH.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        )
    except OSError as error:
        raise PermanentWorkflowError("synthetic_dataset_unavailable") from error

    expected_columns = {*PREDICTION_FEATURES, "no_show"}
    with source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or set(reader.fieldnames) != expected_columns:
            raise PermanentWorkflowError("synthetic_dataset_schema_invalid")
        for row_number, row in enumerate(reader, start=1):
            if row_number > 100000:
                raise PermanentWorkflowError("synthetic_dataset_too_large")
            try:
                actual_label = int(row["no_show"])
                if actual_label not in (0, 1):
                    raise ValueError
                features = {
                    "days_ahead": int(row["days_ahead"]),
                    "previous_no_shows": int(row["previous_no_shows"]),
                    "sms_reminder": row["sms_reminder"],
                    "weekday": row["weekday"],
                }
            except (TypeError, ValueError, KeyError) as error:
                raise PermanentWorkflowError(
                    "synthetic_dataset_row_invalid"
                ) from error
            serializer = NoShowPredictionSerializer(data=features)
            if not serializer.is_valid():
                raise PermanentWorkflowError(
                    "synthetic_dataset_row_invalid"
                )
            yield serializer.validated_data, actual_label


def _run_batch_prediction():
    actual_counts = [0, 0]
    predicted_counts = [0, 0]
    probability_total = 0.0
    record_count = 0
    model_version = None
    display_version = None

    for features, actual_label in _read_synthetic_rows():
        response = NoShowPredictionView().post(SimpleNamespace(data=features))
        if response.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE:
            raise TransientWorkflowError("prediction_service_unavailable")
        if response.status_code != http_status.HTTP_200_OK:
            raise PermanentWorkflowError("prediction_model_unavailable")
        prediction = response.data
        predicted_class = prediction.get("predicted_class")
        probability = prediction.get("probability_no_show")
        if (
            type(predicted_class) is not int
            or predicted_class not in (0, 1)
            or type(probability) not in (float, int)
            or not 0 <= probability <= 1
        ):
            raise PermanentWorkflowError("prediction_result_invalid")
        actual_counts[actual_label] += 1
        predicted_counts[predicted_class] += 1
        probability_total += probability
        record_count += 1
        model_version = prediction.get("model_version")
        display_version = prediction.get("display_version")

    if not record_count:
        raise PermanentWorkflowError("synthetic_dataset_empty")

    baseline_rate = actual_counts[1] / record_count
    predicted_rate = predicted_counts[1] / record_count
    rate_delta = abs(predicted_rate - baseline_rate)
    return {
        "dataset": "synthetic_appointments",
        "record_count": record_count,
        "actual_label_distribution": {
            "attended": actual_counts[0],
            "no_show": actual_counts[1],
            "no_show_rate": round(baseline_rate, 6),
        },
        "prediction_distribution": {
            "attended": predicted_counts[0],
            "no_show": predicted_counts[1],
            "no_show_rate": round(predicted_rate, 6),
        },
        "mean_probability_no_show": round(probability_total / record_count, 6),
        "absolute_rate_delta": round(rate_delta, 6),
        "drift_threshold": DRIFT_RATE_DELTA_THRESHOLD,
        "drift_indicator": (
            "alert"
            if rate_delta > DRIFT_RATE_DELTA_THRESHOLD
            else "within_threshold"
        ),
        "model_version": model_version,
        "display_version": display_version,
    }


def _run_job(job: WorkflowJob):
    if job.job_type == WorkflowJob.JobType.DOCUMENT_INDEXING:
        return _run_document_indexing()
    if job.job_type == WorkflowJob.JobType.BATCH_PREDICTION:
        return _run_batch_prediction()
    raise PermanentWorkflowError("unsupported_job_type")


def _claim_job():
    with transaction.atomic():
        job = (
            WorkflowJob.objects.select_for_update(skip_locked=True)
            .filter(status=WorkflowJob.Status.QUEUED)
            .order_by("created_at")
            .first()
        )
        if job is None:
            return None
        job.status = WorkflowJob.Status.RUNNING
        job.attempt_count += 1
        if job.started_at is None:
            job.started_at = timezone.now()
        job.failure_code = ""
        job.save(
            update_fields=[
                "status",
                "attempt_count",
                "started_at",
                "failure_code",
            ]
        )
        return job


def _complete_job(job_id, status, *, result=None, failure_code="", duration_ms=0):
    with transaction.atomic():
        job = WorkflowJob.objects.select_for_update().get(pk=job_id)
        job.duration_ms += max(0, duration_ms)
        job.status = status
        job.result = result
        job.failure_code = failure_code
        if status in {WorkflowJob.Status.SUCCEEDED, WorkflowJob.Status.FAILED}:
            job.finished_at = timezone.now()
        else:
            job.finished_at = None
        job.save(
            update_fields=[
                "duration_ms",
                "status",
                "result",
                "failure_code",
                "finished_at",
            ]
        )
        return job


def process_next_job():
    """Claim and execute one queued job; repeated execution is safe."""
    job = _claim_job()
    if job is None:
        return None

    started = time.monotonic()
    try:
        result = _run_job(job)
    except (
        OperationalError,
        socket.timeout,
        TimeoutError,
        ConnectionError,
        EmbeddingModelError,
        TransientWorkflowError,
    ):
        duration_ms = round((time.monotonic() - started) * 1000)
        if job.attempt_count < job.max_attempts:
            return _complete_job(
                job.pk,
                WorkflowJob.Status.QUEUED,
                failure_code="transient_error",
                duration_ms=duration_ms,
            )
        return _complete_job(
            job.pk,
            WorkflowJob.Status.FAILED,
            failure_code="retries_exhausted",
            duration_ms=duration_ms,
        )
    except (
        PermanentWorkflowError,
        PolicyIngestionError,
        EmbeddingConfigurationError,
        EmbeddingResponseError,
        ValueError,
    ) as error:
        duration_ms = round((time.monotonic() - started) * 1000)
        failure_code = (
            str(error)
            if isinstance(error, PermanentWorkflowError)
            else "processing_error"
        )
        return _complete_job(
            job.pk,
            WorkflowJob.Status.FAILED,
            failure_code=failure_code[:64],
            duration_ms=duration_ms,
        )
    except Exception:
        logger.exception(
            "Workflow job failed unexpectedly: job_id=%s type=%s",
            job.pk,
            job.job_type,
        )
        duration_ms = round((time.monotonic() - started) * 1000)
        return _complete_job(
            job.pk,
            WorkflowJob.Status.FAILED,
            failure_code="processing_error",
            duration_ms=duration_ms,
        )

    duration_ms = round((time.monotonic() - started) * 1000)
    return _complete_job(
        job.pk,
        WorkflowJob.Status.SUCCEEDED,
        result=result,
        duration_ms=duration_ms,
    )


def monitoring_summary():
    counts = {
        entry["status"]: entry["count"]
        for entry in WorkflowJob.objects.values("status").annotate(
            count=Count("id")
        )
    }
    failed = counts.get(WorkflowJob.Status.FAILED, 0)
    terminal_count = (
        counts.get(WorkflowJob.Status.SUCCEEDED, 0) + failed
    )
    terminal = WorkflowJob.objects.filter(
        status__in=[WorkflowJob.Status.SUCCEEDED, WorkflowJob.Status.FAILED]
    )
    latency = terminal.aggregate(
        average=Avg("duration_ms"),
        minimum=Min("duration_ms"),
        maximum=Max("duration_ms"),
    )
    latest_prediction = (
        WorkflowJob.objects.filter(
            job_type=WorkflowJob.JobType.BATCH_PREDICTION,
            status=WorkflowJob.Status.SUCCEEDED,
        )
        .exclude(result__isnull=True)
        .values_list("result", flat=True)
        .first()
    )
    return {
        "job_counts": {
            status: counts.get(status, 0)
            for status, _ in WorkflowJob.Status.choices
        },
        "failure_rate": (
            round(failed / terminal_count, 6) if terminal_count else 0.0
        ),
        "execution_latency_ms": {
            "average": (
                round(latency["average"])
                if latency["average"] is not None
                else None
            ),
            "minimum": latency["minimum"],
            "maximum": latency["maximum"],
        },
        "latest_batch_prediction": latest_prediction,
    }
