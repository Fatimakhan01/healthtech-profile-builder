import uuid

from django.conf import settings
from django.db import models


class WorkflowJob(models.Model):
    class JobType(models.TextChoices):
        DOCUMENT_INDEXING = "document_indexing", "Document indexing"
        BATCH_PREDICTION = "batch_prediction", "Batch prediction"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=32, choices=JobType.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    idempotency_hash = models.CharField(max_length=64, unique=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workflow_jobs",
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    duration_ms = models.PositiveBigIntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="workflows_status_created_idx",
            ),
            models.Index(
                fields=["job_type", "status", "-finished_at"],
                name="workflows_type_status_done_idx",
            ),
        ]

    def __str__(self):
        return f"{self.job_type}:{self.pk} ({self.status})"
