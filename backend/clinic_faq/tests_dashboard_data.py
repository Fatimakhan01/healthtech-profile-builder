import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APIClient

from ml_dashboard import views


class MLDashboardDataViewTests(SimpleTestCase):
    url = "/api/v1/ml-dashboard/"

    def setUp(self):
        self.client = APIClient()

    def authenticate_standard_user(self):
        user = SimpleNamespace(
            pk=id(self),
            is_authenticated=True,
            is_active=True,
            role="standard",
        )
        self.client.force_authenticate(user=user)

    def test_requires_authentication_and_standard_user_permission(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(
            user=SimpleNamespace(
                pk=id(self),
                is_authenticated=True,
                is_active=True,
                role="admin",
            )
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_returns_existing_reports_without_absolute_local_paths(self):
        self.authenticate_standard_user()
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = {}
            for name in views.REPORT_PATHS:
                report_path = Path(temporary_directory) / f"{name}.json"
                report = {
                    "dataset": {"path": "C:\\private\\local\\dataset.csv"}
                }
                report_path.write_text(json.dumps(report), encoding="utf-8")
                paths[name] = report_path

            with patch.object(views, "REPORT_PATHS", paths):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data),
            {"supervised", "supervised_metadata", "clustering"},
        )
        self.assertEqual(
            response.data["clustering"]["dataset"]["path"],
            "backend/ml/clustering/data/engagement_clustering.csv",
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_missing_or_malformed_report_returns_safe_service_error(self):
        self.authenticate_standard_user()
        with patch.object(
            views,
            "REPORT_PATHS",
            {"supervised": Path("missing-report.json")},
        ):
            response = self.client.get(self.url)
        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data["detail"],
            "The ML dashboard reports are unavailable.",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            malformed_path = Path(temporary_directory) / "malformed.json"
            malformed_path.write_text("{", encoding="utf-8")
            with patch.object(
                views,
                "REPORT_PATHS",
                {"supervised": malformed_path},
            ):
                response = self.client.get(self.url)
        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
