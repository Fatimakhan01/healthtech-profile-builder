from django.db import models


class PolicyDocument(models.Model):
    class IndexingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        INDEXED = "indexed", "Indexed"
        INACTIVE = "inactive", "Inactive"

    source_filename = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    content_sha256 = models.CharField(max_length=64)
    chunk_size = models.PositiveIntegerField()
    chunk_overlap = models.PositiveIntegerField()
    version = models.PositiveIntegerField(default=1)
    version_history = models.JSONField(default=list, blank=True)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    indexing_status = models.CharField(
        max_length=16,
        choices=IndexingStatus.choices,
        default=IndexingStatus.PENDING,
    )
    ingested_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_filename"]

    def __str__(self):
        return self.title


class PolicyChunk(models.Model):
    document = models.ForeignKey(
        PolicyDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    document_version = models.PositiveIntegerField(default=1)
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    embedding = models.JSONField(null=True, blank=True)
    embedding_model = models.CharField(max_length=255, blank=True)
    embedding_text_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["document__source_filename", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="clinic_faq_document_chunk_unique",
            ),
        ]

    def __str__(self):
        return f"{self.document.source_filename}#{self.chunk_index}"
