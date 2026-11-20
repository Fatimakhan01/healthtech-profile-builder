from django.core.management.base import BaseCommand, CommandError

from clinic_faq.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingModelError,
    EmbeddingResponseError,
)
from clinic_faq.ingestion import PolicyIngestionError
from clinic_faq.retrieval_evaluation import (
    CHUNK_REPORT_PATH,
    DATASET_PATH,
    REPORT_JSON_PATH,
    REPORT_MARKDOWN_PATH,
    run_evaluation,
)


class Command(BaseCommand):
    help = "Evaluate local semantic and hybrid retrieval without answer generation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--questions",
            default=DATASET_PATH,
            help="Question dataset JSON path (defaults to the checked-in dataset).",
        )
        parser.add_argument(
            "--output-json",
            default=REPORT_JSON_PATH,
            help="Retrieval report JSON destination.",
        )
        parser.add_argument(
            "--output-markdown",
            default=REPORT_MARKDOWN_PATH,
            help="Retrieval report Markdown destination.",
        )
        parser.add_argument(
            "--chunk-output",
            default=CHUNK_REPORT_PATH,
            help="In-memory chunk-size comparison JSON destination.",
        )

    def handle(self, *args, **options):
        try:
            report = run_evaluation(
                dataset_path=options["questions"],
                report_json_path=options["output_json"],
                report_markdown_path=options["output_markdown"],
                chunk_report_path=options["chunk_output"],
            )
        except (
            EmbeddingConfigurationError,
            EmbeddingModelError,
            EmbeddingResponseError,
            PolicyIngestionError,
            OSError,
            ValueError,
        ) as error:
            raise CommandError(
                f"Clinic FAQ retrieval evaluation failed ({type(error).__name__})."
            ) from error

        semantic = report["methods"]["semantic"]["aggregate"]
        hybrid = report["methods"]["hybrid"]["aggregate"]
        self.stdout.write(
            self.style.SUCCESS(
                "Clinic FAQ retrieval evaluation complete: "
                f"questions={report['dataset']['question_count']}, "
                f"semantic_mrr={semantic['reciprocal_rank']:.3f}, "
                f"hybrid_mrr={hybrid['reciprocal_rank']:.3f}, "
                f"report={options['output_json']}, "
                f"chunk_report={options['chunk_output']}."
            )
        )
