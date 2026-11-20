from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from clinic_faq import evaluation
from clinic_faq.embeddings import EmbeddingConfigurationError, EmbeddingModelError
from clinic_faq.ingestion import PolicyIngestionError
from clinic_faq.provider import (
    FAQConfigurationError,
    FAQMalformedResponse,
    FAQProviderError,
    FAQProviderTimeout,
)


class Command(BaseCommand):
    help = "Evaluate the local Ollama clinic FAQ against approved synthetic policies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            default=evaluation.REPORT_PATH,
            help="JSON report destination (default: clinic_faq/reports/ollama_evaluation.json).",
        )

    def handle(self, *args, **options):
        try:
            report = evaluation.run_evaluation(output_path=options["output"])
        except (
            EmbeddingConfigurationError,
            EmbeddingModelError,
            FAQConfigurationError,
            FAQMalformedResponse,
            FAQProviderError,
            FAQProviderTimeout,
            PolicyIngestionError,
            OSError,
            ValueError,
        ) as error:
            raise CommandError(
                f"Clinic FAQ evaluation failed ({type(error).__name__})."
            ) from error

        self.stdout.write(
            self.style.SUCCESS(
                "Clinic FAQ evaluation complete: "
                f"questions={report['dataset']['question_count']}, "
                f"configurations={len(report['configurations'])}, "
                f"report={options['output']}."
            )
        )
