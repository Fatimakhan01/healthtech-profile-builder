import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from . import evaluation, provider
from .retrieval import RetrievedPolicyChunk


class ClinicFAQEvaluationTests(SimpleTestCase):
    config = {
        "LLM_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        "OLLAMA_CHAT_MODEL": "test-local-model",
        "OLLAMA_TIMEOUT_SECONDS": "120",
        "OLLAMA_NUM_CTX": "2048",
        "OLLAMA_TEMPERATURE": "0.1",
        "OLLAMA_MAX_OUTPUT_TOKENS": "256",
    }

    def build_passages(self, question):
        if question["expected_sources"]:
            filename = question["expected_sources"][0]
            source_title = {
                "appointment-scheduling.md": "Synthetic Example — Appointment Scheduling",
                "cancellations.md": "Synthetic Example — Cancellations and Rescheduling",
                "late-arrivals.md": "Synthetic Example — Late Arrivals",
                "reminders.md": "Synthetic Example — Appointment Reminders",
            }[filename]
        else:
            filename = "unapproved.md"
            source_title = "Unapproved"
        text = " ".join(question["expected_facts"]) or "No requested policy fact."
        return [
            RetrievedPolicyChunk(
                chunk_id=1,
                source_title=source_title,
                source_filename=filename,
                text=text,
                similarity=0.9,
            )
        ]

    @staticmethod
    def generate_answer(question, passages, *, system_prompt):
        if question in {
            entry["question"]
            for entry in evaluation.EVALUATION_QUESTIONS
            if entry["expected_insufficient_information"]
        } or not passages:
            return {
                "answer": "The approved examples do not specify that.",
                "insufficient_information": True,
                "citations": [],
            }
        source = passages[0]
        return {
            "answer": " ".join(
                " ".join(entry["expected_facts"])
                for entry in evaluation.EVALUATION_QUESTIONS
                if entry["question"] == question
            ),
            "insufficient_information": False,
            "citations": [
                {"title": source.source_title, "filename": source.source_filename}
            ],
        }

    def test_curated_set_has_twelve_questions_based_on_approved_files(self):
        self.assertEqual(len(evaluation.EVALUATION_QUESTIONS), 12)
        self.assertEqual(
            {filename for question in evaluation.EVALUATION_QUESTIONS for filename in question["expected_sources"]},
            evaluation.APPROVED_SOURCE_FILENAMES,
        )
        self.assertTrue(
            any(question["expected_insufficient_information"] for question in evaluation.EVALUATION_QUESTIONS)
        )
        self.assertTrue(
            any(not question["expected_insufficient_information"] for question in evaluation.EVALUATION_QUESTIONS)
        )

    def test_runs_both_profiles_and_writes_complete_json_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "nested" / "report.json"
            questions_by_text = {
                question["question"]: question
                for question in evaluation.EVALUATION_QUESTIONS
            }
            retrieve = Mock(
                side_effect=lambda text, **kwargs: self.build_passages(
                    questions_by_text[text]
                )
            )
            generate = Mock(side_effect=self.generate_answer)
            with patch.dict(os.environ, self.config, clear=True):
                report = evaluation.run_evaluation(
                    output_path=report_path,
                    retrieve=retrieve,
                    generate_answer=generate,
                )

            stored_report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(stored_report, report)
        self.assertEqual(report["provider"], "ollama")
        self.assertEqual(report["model"], "test-local-model")
        self.assertEqual(len(report["configurations"]), 2)
        self.assertEqual([entry["summary"]["question_count"] for entry in report["configurations"]], [12, 12])
        self.assertEqual(retrieve.call_count, 24)
        self.assertEqual(generate.call_count, 24)
        baseline, improved = report["configurations"]
        self.assertEqual(baseline["configuration"]["top_k"], 5)
        self.assertEqual(baseline["configuration"]["min_similarity"], 0.2)
        self.assertEqual(improved["configuration"]["top_k"], 3)
        self.assertEqual(improved["configuration"]["min_similarity"], 0.35)
        self.assertNotEqual(
            baseline["configuration"]["system_prompt"],
            improved["configuration"]["system_prompt"],
        )
        sample = baseline["results"][0]
        self.assertIn("generated_answer", sample)
        self.assertIn("insufficient_information", sample)
        self.assertIn("citations", sample)
        self.assertIn("retrieval_results", sample)
        self.assertIn("evaluation_outcome", sample)
        self.assertTrue(
            all(result["evaluation_outcome"]["passed"] for result in baseline["results"])
        )

    def test_evaluation_filters_non_approved_retrieval_sources(self):
        question = evaluation.EVALUATION_QUESTIONS[0]
        unapproved = RetrievedPolicyChunk(
            chunk_id=99,
            source_title="External",
            source_filename="external.md",
            text="A fabricated policy passage.",
            similarity=1.0,
        )
        retrieve = Mock(return_value=[unapproved])
        generate = Mock(
            return_value={
                "answer": "Unsupported answer.",
                "insufficient_information": False,
                "citations": [{"title": "External", "filename": "external.md"}],
            }
        )

        result = evaluation._evaluate_question(
            question,
            evaluation.CONFIGURATIONS[0],
            retrieve,
            generate,
        )

        self.assertEqual(result["retrieval_results"], [])
        self.assertTrue(result["insufficient_information"])
        generate.assert_not_called()

    def test_checks_citations_relevance_unsupported_claims_and_abstention(self):
        question = evaluation.EVALUATION_QUESTIONS[0]
        passage = self.build_passages(question)[0]
        supported = {
            "answer": "Use the scheduling desk or online booking page.",
            "insufficient_information": False,
            "citations": [
                {
                    "title": passage.source_title,
                    "filename": passage.source_filename,
                }
            ],
        }
        outcome = evaluation._check_result(question, supported, [passage], None)
        self.assertTrue(outcome["citation_correctness"])
        self.assertTrue(outcome["relevance_to_retrieved_passages"])
        self.assertTrue(outcome["unsupported_claims"]["passed"])
        self.assertTrue(outcome["correct_abstention"])
        self.assertTrue(outcome["passed"])

        unsupported = {
            **supported,
            "answer": "Walk in is offered.",
            "citations": [{"title": "Wrong title", "filename": passage.source_filename}],
        }
        outcome = evaluation._check_result(question, unsupported, [passage], None)
        self.assertFalse(outcome["citation_correctness"])
        self.assertFalse(outcome["relevance_to_retrieved_passages"])
        self.assertFalse(outcome["unsupported_claims"]["passed"])
        self.assertFalse(outcome["passed"])

        abstention_case = next(
            item
            for item in evaluation.EVALUATION_QUESTIONS
            if item["expected_insufficient_information"]
        )
        abstention = {
            "answer": "The example does not specify a cancellation deadline.",
            "insufficient_information": True,
            "citations": [],
        }
        outcome = evaluation._check_result(abstention_case, abstention, [], None)
        self.assertTrue(outcome["citation_correctness"])
        self.assertTrue(outcome["correct_abstention"])
        self.assertTrue(outcome["passed"])

    def test_provider_errors_are_recorded_without_exposing_error_text(self):
        question = evaluation.EVALUATION_QUESTIONS[0]
        passages = self.build_passages(question)
        result = evaluation._evaluate_question(
            question,
            evaluation.CONFIGURATIONS[0],
            lambda *args, **kwargs: passages,
            Mock(side_effect=provider.FAQProviderTimeout("private detail")),
        )

        self.assertIsNone(result["generated_answer"])
        self.assertEqual(
            result["evaluation_outcome"]["error"],
            "FAQProviderTimeout",
        )
        self.assertNotIn(
            "private detail",
            json.dumps(result),
        )
