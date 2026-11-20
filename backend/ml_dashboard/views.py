"""Authenticated, read-only access to the existing synthetic ML reports."""

import json
from pathlib import Path

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsStandardUser


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPORT_PATHS = {
    "supervised": BACKEND_DIR / "ml" / "reports" / "model_comparison.json",
    "supervised_metadata": (
        BACKEND_DIR / "ml" / "artifacts" / "supervised_pipeline.metadata.json"
    ),
    "clustering": (
        BACKEND_DIR
        / "ml"
        / "clustering"
        / "reports"
        / "clustering_results.json"
    ),
}


class MLDashboardDataView(APIView):
    permission_classes = [IsAuthenticated, IsStandardUser]

    def get(self, request):
        try:
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in REPORT_PATHS.items()
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return Response(
                {"detail": "The ML dashboard reports are unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Cache-Control": "no-store"},
            )

        if not all(isinstance(report, dict) for report in reports.values()):
            return Response(
                {"detail": "The ML dashboard reports are invalid."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Cache-Control": "no-store"},
            )

        clustering_dataset = reports["clustering"].get("dataset")
        if isinstance(clustering_dataset, dict):
            clustering_dataset["path"] = (
                "backend/ml/clustering/data/engagement_clustering.csv"
            )

        return Response(
            reports,
            headers={"Cache-Control": "no-store"},
        )
