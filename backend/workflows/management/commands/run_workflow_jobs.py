import time

from django.core.management.base import BaseCommand, CommandError

from workflows.services import process_next_job


class Command(BaseCommand):
    help = "Process queued safe document-indexing and synthetic batch-prediction jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one queued job, then exit.",
        )
        parser.add_argument(
            "--poll-seconds",
            type=int,
            default=5,
            help="Seconds to wait when the queue is empty (1-300; default: 5).",
        )

    def handle(self, *args, **options):
        poll_seconds = options["poll_seconds"]
        if type(poll_seconds) is not int or not 1 <= poll_seconds <= 300:
            raise CommandError("--poll-seconds must be between 1 and 300.")

        processed = 0
        while True:
            job = process_next_job()
            if job is not None:
                processed += 1
                self.stdout.write(
                    f"job={job.pk} type={job.job_type} status={job.status} "
                    f"attempts={job.attempt_count}"
                )
            elif options["once"]:
                self.stdout.write("No queued workflow jobs.")
                break

            if options["once"]:
                break
            if job is None:
                time.sleep(poll_seconds)

        if options["once"]:
            self.stdout.write(f"Processed jobs: {processed}.")
