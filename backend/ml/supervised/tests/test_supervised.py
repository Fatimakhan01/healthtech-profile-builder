"""Focused tests for the independent Week 4 supervised ML workflow."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

from backend.ml.supervised import generate_dataset, train


class Week4DatasetTests(unittest.TestCase):
    def test_dataset_generation_is_reproducible_and_has_documented_schema(self):
        first = generate_dataset.generate_dataset()
        second = generate_dataset.generate_dataset()

        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(len(first), 2_000)
        self.assertEqual(
            list(first.columns),
            train.FEATURE_NAMES + [train.TARGET],
        )
        self.assertEqual(set(first[train.TARGET].unique()), {0, 1})
        self.assertTrue(
            (first["previous_no_shows"] <= first["previous_appointments"]).all()
        )
        self.assertGreater(int(first.isna().sum().sum()), 0)
        self.assertFalse(first[train.TARGET].isna().any())

    def test_target_is_separate_and_never_used_as_a_feature(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_path = Path(temporary_directory) / "dataset.csv"
            generate_dataset.generate_dataset().to_csv(data_path, index=False)
            features, target = train.load_features_and_target(data_path)

        self.assertNotIn(train.TARGET, features.columns)
        self.assertEqual(list(features.columns), train.FEATURE_NAMES)
        self.assertEqual(len(features), len(target))
        self.assertEqual(set(target.unique()), {0, 1})

    def test_split_sizes_and_stratification(self):
        data = generate_dataset.generate_dataset()
        splits = train.split_dataset(
            data[train.FEATURE_NAMES],
            data[train.TARGET],
        )

        self.assertEqual(
            {name: len(split[0]) for name, split in splits.items()},
            {"train": 1_400, "validation": 300, "test": 300},
        )
        overall_rate = data[train.TARGET].mean()
        for _, target in splits.values():
            self.assertLess(abs(float(target.mean()) - overall_rate), 0.01)


class Week4TrainingTests(unittest.TestCase):
    def test_preprocessing_handles_missing_and_unseen_categories(self):
        data = generate_dataset.generate_dataset()
        features, target = data[train.FEATURE_NAMES], data[train.TARGET]
        splits = train.split_dataset(features, target)
        train_x, train_y = splits["train"]
        model = train.make_models()["LogisticRegression"]
        model.fit(train_x, train_y)

        unseen = train_x.iloc[[0]].copy()
        unseen.loc[:, "weekday"] = "FictionalDay"
        unseen.loc[:, "appointment_type"] = "new_category"
        unseen.loc[:, "distance_km"] = np.nan
        probabilities = model.predict_proba(unseen)

        self.assertEqual(probabilities.shape, (1, 2))
        self.assertTrue(np.isfinite(probabilities).all())

    def test_all_classifiers_and_metrics_are_valid(self):
        data = generate_dataset.generate_dataset()
        features, target = data[train.FEATURE_NAMES], data[train.TARGET]
        splits = train.split_dataset(features, target)
        train_x, train_y = splits["train"]
        validation_x, validation_y = splits["validation"]

        for name, model in train.make_models().items():
            with self.subTest(model=name):
                model.fit(train_x, train_y)
                metrics = train.classification_metrics(
                    model, validation_x, validation_y
                )
                for metric in (
                    "precision",
                    "recall",
                    "f1_score",
                    "roc_auc",
                    "average_precision",
                ):
                    self.assertTrue(0 <= metrics[metric] <= 1)
                self.assertEqual(
                    np.asarray(metrics["confusion_matrix"]).shape, (2, 2)
                )

    def test_grid_search_receives_training_partition_only(self):
        data = generate_dataset.generate_dataset()
        splits = train.split_dataset(
            data[train.FEATURE_NAMES],
            data[train.TARGET],
        )
        train_x, train_y = splits["train"]

        with patch.object(train.GridSearchCV, "fit", autospec=True) as fit:
            search = train.tune_random_forest(train_x, train_y)

        self.assertEqual(len(fit.call_args.args[1]), len(train_x))
        pd.testing.assert_frame_equal(fit.call_args.args[1], train_x)
        pd.testing.assert_series_equal(fit.call_args.args[2], train_y)
        self.assertEqual(search.scoring, "f1")
        self.assertEqual(search.cv.n_splits, 5)
        self.assertTrue(search.cv.shuffle)
        self.assertEqual(search.cv.random_state, train.SEED)

    def test_full_training_saves_reloadable_pipeline_and_preserves_week3(self):
        repository_root = Path(__file__).resolve().parents[4]
        week3_paths = (
            repository_root / "backend/ml/data/synthetic_appointments.csv",
            repository_root / "backend/ml/artifacts/no_show_pipeline.joblib",
            repository_root / "backend/ml/artifacts/no_show_pipeline.metadata.json",
        )
        week3_digests_before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in week3_paths
        }
        data = generate_dataset.generate_dataset()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_path = root / "week4.csv"
            output_dir = root / "reports"
            artifact_dir = root / "artifacts"
            data.to_csv(data_path, index=False)

            metrics = train.run_training(
                data_path=data_path,
                output_dir=output_dir,
                artifact_dir=artifact_dir,
            )
            pipeline_path = artifact_dir / "supervised_pipeline.joblib"
            loaded = joblib.load(pipeline_path)
            predictions = loaded.predict(data[train.FEATURE_NAMES].iloc[:7])
            probabilities = loaded.predict_proba(
                data[train.FEATURE_NAMES].iloc[:7]
            )
            metadata = json.loads(
                (artifact_dir / "supervised_pipeline.metadata.json").read_text(
                    encoding="utf-8"
                )
            )
            grid = json.loads(
                (output_dir / "hyperparameter_search.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertTrue(pipeline_path.is_file())
            self.assertEqual(len(predictions), 7)
            self.assertTrue(set(predictions).issubset({0, 1}))
            self.assertEqual(probabilities.shape, (7, 2))
            self.assertEqual(metadata["feature_names"], train.FEATURE_NAMES)
            self.assertEqual(metadata["artifact_sha256"], hashlib.sha256(
                pipeline_path.read_bytes()
            ).hexdigest())
            self.assertTrue(grid["training_rows_only"])
            self.assertEqual(grid["training_row_count"], 1_400)
            self.assertEqual(len(grid["results"]), 8)
            self.assertEqual(metrics["split_sizes"], {
                "train": 1_400,
                "validation": 300,
                "test": 300,
            })
            self.assertEqual(set(metrics["training_metrics"]), {
                "LogisticRegression",
                "RandomForestClassifier",
                "GradientBoostingClassifier",
                "TunedRandomForestClassifier",
            })
            self.assertTrue(
                all(
                    "parameters" in result
                    for result in metrics["training_metrics"].values()
                )
            )

        self.assertEqual(
            week3_digests_before,
            {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in week3_paths
            },
        )


if __name__ == "__main__":
    unittest.main()
