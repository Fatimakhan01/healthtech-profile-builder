from django.core.management.base import BaseCommand, CommandError

from clinic_faq.ingestion import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    PolicyIngestionError,
    ingest_approved_documents,
)


class Command(BaseCommand):
    help = "Ingest only the explicitly approved fictional clinic policy documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=DEFAULT_CHUNK_SIZE,
            help="Maximum chunk length in characters (default: %(default)s).",
        )
        parser.add_argument(
            "--overlap",
            type=int,
            default=DEFAULT_CHUNK_OVERLAP,
            help="Target overlap in characters between chunks (default: %(default)s).",
        )

    def handle(self, *args, **options):
        try:
            summary = ingest_approved_documents(
                chunk_size=options["chunk_size"],
                overlap=options["overlap"],
            )
        except (PolicyIngestionError, ValueError) as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Clinic policy ingestion complete: "
                f"processed={summary.processed}, created={summary.created}, "
                f"unchanged={summary.unchanged}, updated={summary.updated}, "
                f"chunks_created={summary.chunks_created}, "
                f"chunks_updated={summary.chunks_updated}."
            )
        )
