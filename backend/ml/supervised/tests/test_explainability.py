"""Focused tests for saved-model explainability and error analysis."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from backend.ml.supervised import explainability, train


class ErrorAnalysisTests(unittest.TestCase):
    def test_counts_false_positives_and_false_negatives(self):
        features = pd.DataFrame(
            {
                name: (
                    ["Monday", "Tuesday", "Monday", "Friday"]
                    if name == "weekday"
                    else ["routine", "consultation", "follow_up", "procedure"]
                    if name == "appointment_type"
                    else [2, 4, 6, 8]
                )
                for name in train.FEATURE_NAMES
            }
        )
        target = pd.Series([0, 0, 1, 1])
        predictions = np.array([1, 0, 0, 1])

        report = explainability.analyze_errors(features, target, predictions)

        self.assertEqual(report["false_positives"]["count"], 1)
        self.assertEqual(
            report["false_positives"]["percent_of_test_set"], 25.0
        )
        self.assertEqual(
            report["false_positives"]["percent_of_actual_class"], 50.0
        )
        self.assertEqual(report["false_negatives"]["count"], 1)
        self.assertEqual(
            report["false_negatives"]["percent_of_test_set"], 25.0
        )
        self.assertEqual(
            report["false_negatives"]["percent_of_actual_class"], 50.0
        )
        self.assertEqual(report["confusion_matrix"]["counts"], [[1, 1], [1, 1]])


class ExplainabilityWorkflowTests(unittest.TestCase):
    def test_split_reconstruction_is_deterministic(self):
        features = pd.DataFrame(
            {
                name: (
                    ["Monday", "Tuesday"] * 100
                    if name == "weekday"
                    else ["routine", "consultation"] * 100
                    if name == "appointment_type"
                    else range(200)
                )
                for name in train.FEATURE_NAMES
            }
        )
        target = pd.Series([0] * 140 + [1] * 60)

        first = train.split_dataset(features, target)
        second = train.split_dataset(features, target)

        for split_name in ("train", "validation", "test"):
            pd.testing.assert_frame_equal(
                first[split_name][0], second[split_name][0]
            )
            pd.testing.assert_series_equal(
                first[split_name][1], second[split_name][1]
            )
        self.assertEqual(
            {name: len(split[0]) for name, split in first.items()},
            {"train": 140, "validation": 30, "test": 30},
        )

    def test_importance_structure_keeps_original_feature_names(self):
        data, target = train.load_features_and_target()
        splits = train.split_dataset(data, target)
        model = __import__("joblib").load(train.ARTIFACT_PATH)

        report = explainability.calculate_feature_importance(
            model,
            splits["validation"][0],
            splits["validation"][1],
            n_repeats=2,
        )

        self.assertEqual(report["scoring"], "f1")
        self.assertEqual(report["split"], "validation")
        self.assertEqual(report["n_repeats"], 2)
        self.assertTrue(0 <= report["baseline_f1"] <= 1)
        self.assertEqual(
            {entry["feature"] for entry in report["features"]},
            set(train.FEATURE_NAMES),
        )
        self.assertEqual(
            len(report["features"]),
            len(train.FEATURE_NAMES),
        )
        self.assertTrue(
            all(
                entry["importance_std"] >= 0
                for entry in report["features"]
            )
        )
        means = [entry["importance_mean"] for entry in report["features"]]
        self.assertEqual(means, sorted(means, reverse=True))

    def test_saved_pipeline_analysis_preserves_original_artifact_and_reports(self):
        ml_dir = Path(__file__).resolve().parents[2]
        preserved_paths = [
            ml_dir / "artifacts" / "supervised_pipeline.joblib",
            ml_dir / "artifacts" / "supervised_pipeline.metadata.json",
            ml_dir / "data" / "appointment_attendance.csv",
            *sorted((ml_dir / "reports").glob("*.json")),
        ]
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in preserved_paths
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_path = root / "feature_importance.json"
            error_path = root / "error_analysis.json"
            importance, errors = explainability.run_analysis(
                feature_importance_path=feature_path,
                error_analysis_path=error_path,
                n_repeats=2,
            )

            self.assertEqual(
                json.loads(feature_path.read_text(encoding="utf-8")),
                importance,
            )
            self.assertEqual(
                json.loads(error_path.read_text(encoding="utf-8")),
                errors,
            )

        self.assertEqual(
            before,
            {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in preserved_paths
            },
        )
        self.assertEqual(errors["split"], "test")
        self.assertEqual(errors["split_size"], 300)
        self.assertEqual(errors["false_positives"]["count"], 70)
        self.assertEqual(errors["false_negatives"]["count"], 42)


if __name__ == "__main__":
    unittest.main()
