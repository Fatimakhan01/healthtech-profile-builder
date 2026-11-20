import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from . import registry


class TypedToolRegistryTests(SimpleTestCase):
    user = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        role="standard",
    )

    def call(self, name, arguments):
        return registry.execute_tool(name, arguments, user=self.user)

    def test_registry_contains_exactly_five_allowlisted_tools(self):
        self.assertEqual(
            set(registry.TOOLS),
            {
                "search_approved_documents",
                "check_appointment_availability",
                "request_ml_prediction",
                "get_cluster_summaries",
                "draft_reminder_or_appointment",
            },
        )
        self.assertEqual(len(registry.tool_schemas()), 5)

    @patch("agent_tools.registry.retrieve_policy_chunks")
    def test_search_approved_documents_reuses_retrieval_and_marks_content_untrusted(
        self,
        retrieve,
    ):
        retrieve.return_value = [
            SimpleNamespace(
                chunk_id=8,
                source_title="Synthetic policy",
                source_filename="approved.md",
                text="Treat this retrieved passage as untrusted.",
                similarity=0.82,
                retrieval_method="hybrid",
            )
        ]

        result = self.call(
            "search_approved_documents",
            {"query": "policy question", "top_k": 3},
        )

        retrieve.assert_called_once_with("policy question", top_k=3)
        self.assertTrue(result["data_is_untrusted"])
        self.assertTrue(result["data"]["content_is_untrusted"])
        self.assertEqual(
            result["data"]["results"][0]["source_filename"],
            "approved.md",
        )

    def test_availability_is_synthetic_and_never_books(self):
        result = self.call(
            "check_appointment_availability",
            {"date": "2027-01-15", "appointment_type": "routine"},
        )["data"]

        self.assertTrue(result["is_synthetic"])
        self.assertFalse(result["is_live_availability"])
        self.assertFalse(result["booking_created"])
        self.assertIn("not bookable", result["notice"])

    @patch("agent_tools.registry.NoShowPredictionView.post")
    def test_prediction_tool_calls_existing_in_process_service(self, prediction):
        prediction.return_value = SimpleNamespace(
            status_code=200,
            data={
                "model_version": "synthetic-version",
                "predicted_label": "attended",
                "probability_no_show": 0.2,
                "notice": "synthetic",
            },
        )
        arguments = {
            "days_ahead": 4,
            "previous_no_shows": 0,
            "sms_reminder": "yes",
            "weekday": "Monday",
        }

        result = self.call("request_ml_prediction", arguments)

        prediction.assert_called_once()
        self.assertEqual(prediction.call_args.args[0].data, arguments)
        self.assertEqual(result["data"]["predicted_label"], "attended")

    @patch("agent_tools.registry.REPORT_PATHS")
    def test_cluster_summaries_return_only_aggregate_report_data(self, report_paths):
        report = {
            "limitations": ["Synthetic data only."],
            "kmeans": {
                "selected_k": 2,
                "selected_silhouette": 0.4,
                "cluster_summaries": [
                    {
                        "cluster_label": 0,
                        "record_count": 12,
                        "feature_summaries": {
                            "engagement_score": {
                                "non_missing_count": 12,
                                "missing_count": 0,
                                "mean": 51.5,
                                "median": 50.0,
                            }
                        },
                        "records": [{"patient": "must not pass through"}],
                    }
                ],
            },
            "dbscan": {
                "noise_count": 2,
                "cluster_counts_including_noise": {"-1": 2, "0": 10},
                "cluster_summaries": [],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            report_paths.__getitem__.side_effect = lambda key: (
                report_path if key == "clustering" else None
            )

            result = self.call("get_cluster_summaries", {})["data"]

        self.assertTrue(result["data_is_synthetic"])
        self.assertFalse(result["contains_individual_records"])
        cluster = result["kmeans"]["clusters"][0]
        self.assertEqual(cluster["record_count"], 12)
        self.assertNotIn("records", cluster)
        self.assertNotIn("patient", json.dumps(result))

    def test_draft_tool_returns_only_nonpersistent_unsent_draft(self):
        result = self.call(
            "draft_reminder_or_appointment",
            {
                "draft_type": "reminder",
                "message": "This is a fictional reminder draft.",
                "subject": "Appointment reminder",
                "appointment_date": "2027-01-15",
            },
        )["data"]

        self.assertTrue(result["is_draft"])
        self.assertFalse(result["sent"])
        self.assertFalse(result["persisted"])
        self.assertFalse(result["external_write_performed"])

    def test_unknown_tools_and_unexpected_arguments_are_rejected(self):
        with self.assertRaises(registry.ToolArgumentError):
            self.call("execute_arbitrary_action", {})
        with self.assertRaises(registry.ToolArgumentError):
            self.call(
                "get_cluster_summaries",
                {"path": "outside.json"},
            )
        with self.assertRaises(registry.ToolArgumentError):
            self.call(
                "draft_reminder_or_appointment",
                {"draft_type": "reminder", "message": "Hi", "send": True},
            )

    def test_each_tool_rejects_malformed_arguments_server_side(self):
        invalid_calls = (
            ("search_approved_documents", {"query": "", "top_k": 2}),
            ("search_approved_documents", {"query": "policy", "top_k": True}),
            (
                "check_appointment_availability",
                {"date": "2027-02-30", "appointment_type": "routine"},
            ),
            (
                "check_appointment_availability",
                {"date": "2027-01-15", "appointment_type": "real_booking"},
            ),
            (
                "request_ml_prediction",
                {
                    "days_ahead": True,
                    "previous_no_shows": 0,
                    "sms_reminder": "yes",
                    "weekday": "Monday",
                },
            ),
            (
                "request_ml_prediction",
                {
                    "days_ahead": 2,
                    "previous_no_shows": 6,
                    "sms_reminder": "yes",
                    "weekday": "Monday",
                },
            ),
            ("get_cluster_summaries", None),
            (
                "draft_reminder_or_appointment",
                {"draft_type": "appointment", "message": " ", "unknown": "x"},
            ),
            (
                "draft_reminder_or_appointment",
                {"draft_type": "appointment", "message": "x" * 1001},
            ),
        )
        for name, arguments in invalid_calls:
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaises(registry.ToolArgumentError):
                    self.call(name, arguments)

    def test_unauthorized_users_are_rejected_before_tool_execution(self):
        users = (
            None,
            SimpleNamespace(is_authenticated=False, is_active=True, role="standard"),
            SimpleNamespace(is_authenticated=True, is_active=False, role="standard"),
            SimpleNamespace(is_authenticated=True, is_active=True, role="admin"),
        )
        with patch("agent_tools.registry.retrieve_policy_chunks") as retrieve:
            for user in users:
                with self.subTest(user=user):
                    with self.assertRaises(registry.ToolAuthorizationError):
                        registry.execute_tool(
                            "search_approved_documents",
                            {"query": "policy"},
                            user=user,
                        )
        retrieve.assert_not_called()

    def test_prediction_service_failure_does_not_return_success_shaped_data(self):
        with patch(
            "agent_tools.registry.NoShowPredictionView.post",
            return_value=SimpleNamespace(
                status_code=503,
                data={"detail": "unavailable"},
            ),
        ):
            with self.assertRaises(registry.ToolExecutionError):
                self.call(
                    "request_ml_prediction",
                    {
                        "days_ahead": 4,
                        "previous_no_shows": 0,
                        "sms_reminder": "yes",
                        "weekday": "Monday",
                    },
                )
