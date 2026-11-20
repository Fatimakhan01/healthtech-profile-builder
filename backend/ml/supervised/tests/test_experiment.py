"""Tests for the isolated model-improvement experiment."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from backend.ml.supervised import experiment, train


class ThresholdSelectionTests(unittest.TestCase):
    def test_selects_f1_threshold_from_supplied_oof_probabilities(self):
        target = pd.Series([0, 0, 0, 1, 1, 1])
        probabilities = np.array([0.1, 0.4, 0.6, 0.35, 0.55, 0.8])

        threshold, metrics = experiment.select_f1_threshold(target, probabilities)

        predictions = probabilities >= threshold
        self.assertEqual(
            metrics["f1_score"],
            float(f1_score(target, predictions)),
        )
        self.assertIn(threshold, probabilities)
        self.assertGreater(metrics["f1_score"], 0)

    def test_threshold_metrics_include_required_metrics_and_matrix(self):
        target = pd.Series([0, 0, 1, 1])
        probabilities = np.array([0.2, 0.7, 0.4, 0.8])

        metrics = experiment.metrics_at_threshold(target, probabilities, 0.5)

        self.assertEqual(
            set(metrics),
            {
                "accuracy",
                "precision",
                "recall",
                "f1_score",
                "roc_auc",
                "average_precision",
                "confusion_matrix",
            },
        )
        self.assertEqual(metrics["confusion_matrix"], [[1, 1], [1, 1]])


class ExperimentReportTests(unittest.TestCase):
    def test_report_compares_baselines_without_touching_original_artifacts(self):
        ml_dir = Path(__file__).resolve().parents[2]
        preserved_paths = (
            ml_dir / "data" / "appointment_attendance.csv",
            ml_dir / "artifacts" / "supervised_pipeline.joblib",
            ml_dir / "artifacts" / "supervised_pipeline.metadata.json",
            ml_dir / "reports" / "model_comparison.json",
            ml_dir / "reports" / "confusion_matrices.json",
            ml_dir / "reports" / "cross_validation.json",
            ml_dir / "reports" / "hyperparameter_search.json",
            ml_dir / "data" / "synthetic_appointments.csv",
            ml_dir / "artifacts" / "no_show_pipeline.joblib",
            ml_dir / "artifacts" / "no_show_pipeline.metadata.json",
        )
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in preserved_paths
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "model_improvement_experiments.json"
            result = experiment.run_experiment(output_path=report_path)
            saved = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result, saved)
        self.assertEqual(result["split_sizes"], {"train": 1_400, "validation": 300})
        self.assertIsNone(result["test_metrics"])
        self.assertIn("not used", result["test_usage"])
        self.assertEqual(
            result["candidates"]["DummyClassifier"]["validation"]["accuracy"],
            215 / 300,
        )
        for name in (
            "LogisticRegression",
            "RandomForestClassifier",
            "GradientBoostingClassifier",
            "TunedRandomForestClassifier",
        ):
            self.assertIn(name, result["candidates"])
            self.assertIn("validation", result["candidates"][name])
        self.assertIn(result["selected_candidate"], result["candidates"])
        self.assertEqual(
            result["selected_candidate"],
            max(
                result["candidates"],
                key=lambda name: result["candidates"][name]["validation"]["f1_score"],
            ),
        )
        self.assertEqual(
            result["original_pipeline_action"],
            "Preserved; no artifact was replaced.",
        )
        for name, candidate in result["candidates"].items():
            metrics = candidate["validation"]
            self.assertEqual(
                set(metrics),
                {
                    "accuracy",
                    "precision",
                    "recall",
                    "f1_score",
                    "roc_auc",
                    "average_precision",
                    "confusion_matrix",
                },
                name,
            )
        for variant in experiment.CLASS_WEIGHT_VARIANTS:
            self.assertIn(
                f"LogisticRegression_{variant}_default_0_5",
                result["candidates"],
            )
            oof_candidate = result["candidates"][
                f"LogisticRegression_{variant}_training_oof_f1"
            ]
            self.assertIn(
                "training_oof_f1_at_selected_threshold",
                oof_candidate,
            )
            self.assertEqual(
                oof_candidate["threshold_selection"],
                "Max F1 on 5-fold out-of-fold training probabilities",
            )

        self.assertEqual(
            before,
            {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in preserved_paths
            },
        )


if __name__ == "__main__":
    unittest.main()
