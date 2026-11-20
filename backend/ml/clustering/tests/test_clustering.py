"""Focused tests for Week 4 unsupervised engagement clustering."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.ml.clustering import cluster, generate_dataset


class ClusteringDatasetTests(unittest.TestCase):
    def test_dataset_is_reproducible_and_excludes_target(self):
        first = generate_dataset.generate_dataset()
        second = generate_dataset.generate_dataset()
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(len(first), generate_dataset.ROW_COUNT)
        self.assertEqual(list(first.columns), cluster.FEATURE_NAMES)
        self.assertNotIn("no_show", first.columns)
        self.assertGreater(int(first.isna().sum().sum()), 0)
        valid_history = first.dropna(
            subset=["previous_appointments", "previous_no_shows"]
        )
        self.assertTrue(
            (
                valid_history["previous_no_shows"]
                <= valid_history["previous_appointments"]
            ).all()
        )

    def test_loader_rejects_target_even_when_engagement_features_exist(self):
        data = generate_dataset.generate_dataset(row_count=20)
        data["no_show"] = 0
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "leaky.csv"
            data.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "Target leakage"):
                cluster.load_features(path)


class ClusteringMethodTests(unittest.TestCase):
    def test_preprocessing_imputes_and_scales_features(self):
        features = generate_dataset.generate_dataset(row_count=300)
        preprocessor = cluster.make_preprocessor()
        transformed = preprocessor.fit_transform(features)
        self.assertEqual(transformed.shape, (300, len(cluster.FEATURE_NAMES)))
        self.assertTrue(np.isfinite(transformed).all())
        self.assertTrue(
            isinstance(preprocessor.named_transformers_["numeric"], Pipeline)
        )
        self.assertIsInstance(
            preprocessor.named_transformers_["numeric"].named_steps["scaler"],
            StandardScaler,
        )
        self.assertIsInstance(
            preprocessor.named_transformers_["binary"].named_steps["scaler"],
            StandardScaler,
        )
        np.testing.assert_allclose(transformed.mean(axis=0), 0, atol=1e-12)
        np.testing.assert_allclose(transformed.std(axis=0), 1, atol=1e-12)

    def test_repeated_kmeans_results_are_reproducible(self):
        features = generate_dataset.generate_dataset(row_count=240)
        first = cluster.make_kmeans_pipeline(3)
        second = cluster.make_kmeans_pipeline(3)
        first_labels = first.fit_predict(features)
        second_labels = second.fit_predict(features)
        np.testing.assert_array_equal(first_labels, second_labels)
        self.assertAlmostEqual(
            first.named_steps["clusterer"].inertia_,
            second.named_steps["clusterer"].inertia_,
        )

    def test_label_counts_and_noise_are_preserved(self):
        labels = np.array([-1, -1, 0, 0, 1, 1, 1])
        self.assertEqual(
            cluster.cluster_counts(labels),
            {"-1": 2, "0": 2, "1": 3},
        )
        features = pd.DataFrame(
            {
                name: [1, 2, 3, 4, 5, 6, 7]
                for name in cluster.FEATURE_NAMES
            }
        )
        summaries = cluster.summarize_clusters(features, labels)
        self.assertEqual([row["cluster_label"] for row in summaries], [-1, 0, 1])
        self.assertEqual(summaries[0]["record_count"], 2)
        self.assertNotIn("diagnosis", json.dumps(summaries).lower())
        self.assertNotIn("risk", json.dumps(summaries).lower())

    def test_silhouette_edge_cases_and_dbscan_noise_exclusion(self):
        features = np.array([[0.0], [0.1], [3.0], [3.1], [6.0]])
        one_cluster, one_status = cluster.safe_silhouette(
            features, np.array([0, 0, 0, 0, 0])
        )
        all_unique, unique_status = cluster.safe_silhouette(
            features, np.arange(5)
        )
        all_noise, noise_status = cluster.safe_silhouette(
            features, np.full(5, -1), ignore_noise=True
        )
        with_noise, with_noise_status = cluster.safe_silhouette(
            features, np.array([-1, 0, 0, 1, 1]), ignore_noise=True
        )

        self.assertIsNone(one_cluster)
        self.assertEqual(one_status, "requires_at_least_two_non-noise_clusters")
        self.assertIsNone(all_unique)
        self.assertEqual(unique_status, "requires_fewer_clusters_than_samples")
        self.assertIsNone(all_noise)
        self.assertEqual(noise_status, "all_points_are_noise")
        self.assertIsNotNone(with_noise)
        self.assertEqual(with_noise_status, "computed")

    def test_full_report_has_two_dimensional_pca_and_neutral_summaries(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_path = root / "engagement.csv"
            report_path = root / "reports" / "results.json"
            repeat_path = root / "reports" / "repeat.json"
            generate_dataset.generate_dataset(row_count=240).to_csv(
                data_path, index=False
            )
            report = cluster.run_clustering(data_path, report_path)
            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            repeated = cluster.run_clustering(data_path, repeat_path)

        self.assertEqual(persisted, report)
        self.assertEqual(repeated, report)
        self.assertFalse(report["dataset"]["target_used"])
        self.assertEqual(len(report["kmeans"]["elbow_and_silhouette"]), 7)
        self.assertEqual(len(report["visualization"]["coordinates"]), 240)
        self.assertEqual(
            set(report["visualization"]["coordinates"][0]),
            {"row_index", "pca_1", "pca_2", "kmeans_cluster", "dbscan_cluster"},
        )
        self.assertEqual(
            len(report["visualization"]["explained_variance_ratio"]), 2
        )
        self.assertEqual(
            len(report["kmeans"]["cluster_summaries"]),
            len(report["kmeans"]["selected_cluster_counts"]),
        )
        self.assertIn("silhouette_status", report["dbscan"])
        self.assertNotIn("no_show", report["dataset"]["feature_schema"])
        self.assertTrue(report["dataset"]["target_used"] is False)
        self.assertNotIn("diagnosis", json.dumps(report).lower())
        self.assertNotIn("risk category", json.dumps(report).lower())


if __name__ == "__main__":
    unittest.main()
