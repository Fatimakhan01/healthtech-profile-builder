from django.core.management.base import BaseCommand, CommandError

from clinic_faq.embeddings import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    EmbeddingConfigurationError,
    EmbeddingModelError,
    EmbeddingResponseError,
    embed_approved_chunks,
)
from clinic_faq.ingestion import PolicyIngestionError


class Command(BaseCommand):
    help = "Generate embeddings for stored, verified approved clinic policy chunks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Chunks per local inference batch (1-{MAX_BATCH_SIZE}; default: %(default)s).",
        )

    def handle(self, *args, **options):
        try:
            summary = embed_approved_chunks(batch_size=options["batch_size"])
        except (
            EmbeddingConfigurationError,
            EmbeddingModelError,
            EmbeddingResponseError,
            PolicyIngestionError,
            ValueError,
        ) as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Clinic policy embedding complete: "
                f"documents={summary.processed_documents}, "
                f"skipped_documents={summary.skipped_documents}, "
                f"chunks={summary.processed_chunks}, "
                f"embedded={summary.embedded_chunks}, "
                f"skipped_chunks={summary.skipped_chunks}, "
                f"failed={summary.failed_chunks}, batches={summary.batch_count}."
            )
        )
