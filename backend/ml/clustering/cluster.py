"""Run independent K-Means and DBSCAN engagement clustering analyses."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

if __package__:
    from . import generate_dataset
else:
    import generate_dataset


SEED = 42
ML_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ML_DIR / "clustering" / "data" / "engagement_clustering.csv"
REPORT_PATH = ML_DIR / "clustering" / "reports" / "clustering_results.json"
NUMERIC_FEATURES = [
    "previous_appointments",
    "previous_no_shows",
    "portal_activity",
    "engagement_score",
]
BINARY_FEATURES = ["sms_reminder"]
FEATURE_NAMES = NUMERIC_FEATURES + BINARY_FEATURES
K_VALUES = tuple(range(2, 9))
DBSCAN_EPS = 1.15
DBSCAN_MIN_SAMPLES = 10
KMEANS_N_INIT = 20


def make_preprocessor() -> ColumnTransformer:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    binary = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("scaler", StandardScaler()),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric, NUMERIC_FEATURES),
            ("binary", binary, BINARY_FEATURES),
        ],
        remainder="drop",
    )


def make_kmeans_pipeline(n_clusters: int) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", make_preprocessor()),
            (
                "clusterer",
                KMeans(
                    n_clusters=n_clusters,
                    random_state=SEED,
                    n_init=KMEANS_N_INIT,
                ),
            ),
        ]
    )


def make_dbscan_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", make_preprocessor()),
            (
                "clusterer",
                DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES),
            ),
        ]
    )


def load_features(data_path: Path = DATA_PATH) -> pd.DataFrame:
    data = pd.read_csv(data_path)
    if "no_show" in data.columns:
        raise ValueError("Target leakage: no_show must not be present in clustering data.")
    if list(data.columns) != FEATURE_NAMES:
        raise ValueError(
            "Clustering dataset columns must exactly match the documented feature schema."
        )
    return data.loc[:, FEATURE_NAMES]


def safe_silhouette(
    transformed_features: np.ndarray,
    labels: np.ndarray,
    *,
    ignore_noise: bool = False,
) -> tuple[float | None, str]:
    """Return silhouette when defined; optionally exclude DBSCAN noise rows."""
    labels = np.asarray(labels)
    features = np.asarray(transformed_features)
    if labels.ndim != 1 or len(labels) != len(features):
        raise ValueError("Labels and feature rows must have the same length.")

    included = labels != -1 if ignore_noise else np.ones(len(labels), dtype=bool)
    selected_labels = labels[included]
    selected_features = features[included]
    if ignore_noise and not np.any(included):
        return None, "all_points_are_noise"
    unique_count = np.unique(selected_labels).size
    if unique_count < 2:
        return None, "requires_at_least_two_non-noise_clusters"
    if unique_count >= len(selected_labels):
        return None, "requires_fewer_clusters_than_samples"
    return float(silhouette_score(selected_features, selected_labels)), "computed"


def cluster_counts(labels: np.ndarray) -> dict[str, int]:
    values, counts = np.unique(np.asarray(labels), return_counts=True)
    return {str(int(value)): int(count) for value, count in zip(values, counts)}


def summarize_clusters(
    original_features: pd.DataFrame,
    labels: np.ndarray,
) -> list[dict[str, Any]]:
    """Describe numeric input distributions without assigning interpretations."""
    labels = np.asarray(labels)
    summaries = []
    for label in sorted(np.unique(labels)):
        group = original_features.loc[labels == label]
        feature_summary: dict[str, Any] = {}
        for column in FEATURE_NAMES:
            values = group[column].dropna()
            feature_summary[column] = {
                "non_missing_count": int(values.size),
                "missing_count": int(group[column].isna().sum()),
                "mean": float(values.mean()) if not values.empty else None,
                "median": float(values.median()) if not values.empty else None,
            }
        summaries.append(
            {
                "cluster_label": int(label),
                "record_count": int(len(group)),
                "feature_summaries": feature_summary,
            }
        )
    return summaries


def run_clustering(
    data_path: Path = DATA_PATH,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    features = load_features(data_path)
    kmeans_results = []
    best: tuple[float, int, Pipeline, np.ndarray, np.ndarray] | None = None

    for k in K_VALUES:
        pipeline = make_kmeans_pipeline(k)
        labels = pipeline.fit_predict(features)
        transformed = pipeline.named_steps["preprocessor"].transform(features)
        score, status = safe_silhouette(transformed, labels)
        entry = {
            "n_clusters": k,
            "inertia": float(pipeline.named_steps["clusterer"].inertia_),
            "silhouette": score,
            "silhouette_status": status,
            "cluster_counts": cluster_counts(labels),
        }
        kmeans_results.append(entry)
        if score is not None and (best is None or score > best[0]):
            best = (score, k, pipeline, labels, transformed)

    if best is None:
        raise RuntimeError("No K-Means configuration produced a valid silhouette score.")

    best_silhouette, best_k, best_pipeline, best_labels, transformed = best
    dbscan_pipeline = make_dbscan_pipeline()
    dbscan_labels = dbscan_pipeline.fit_predict(features)
    dbscan_transformed = dbscan_pipeline.named_steps["preprocessor"].transform(features)
    dbscan_silhouette, dbscan_status = safe_silhouette(
        dbscan_transformed,
        dbscan_labels,
        ignore_noise=True,
    )

    pca = PCA(n_components=2, svd_solver="full")
    coordinates = pca.fit_transform(transformed)
    visualization_rows = [
        {
            "row_index": int(index),
            "pca_1": float(point[0]),
            "pca_2": float(point[1]),
            "kmeans_cluster": int(best_labels[index]),
            "dbscan_cluster": int(dbscan_labels[index]),
        }
        for index, point in enumerate(coordinates)
    ]

    report: dict[str, Any] = {
        "report_version": 1,
        "dataset": {
            "description": (
                "Fictional, locally generated engagement-only data; no personal "
                "attributes or appointment outcome labels."
            ),
            "path": str(data_path),
            "row_count": int(len(features)),
            "feature_schema": generate_dataset.FEATURE_SCHEMA,
            "target_used": False,
            "missing_value_counts": {
                column: int(count)
                for column, count in features.isna().sum().items()
            },
        },
        "preprocessing": {
            "numeric": "median imputation followed by StandardScaler",
            "binary": "most-frequent imputation followed by StandardScaler",
            "fit_scope": "entire unlabeled dataset, for unsupervised clustering",
            "clustering_space": "all five imputed and standardized input features",
        },
        "random_seed": SEED,
        "kmeans": {
            "parameters": {
                "k_values": list(K_VALUES),
                "random_state": SEED,
                "n_init": KMEANS_N_INIT,
            },
            "selection_rule": (
                "The reported descriptive solution uses the k with the highest "
                "silhouette score among the tested values; this is a heuristic."
            ),
            "elbow_and_silhouette": kmeans_results,
            "selected_k": best_k,
            "selected_silhouette": best_silhouette,
            "selected_cluster_counts": cluster_counts(best_labels),
            "cluster_summaries": summarize_clusters(features, best_labels),
        },
        "dbscan": {
            "parameters": {
                "eps": DBSCAN_EPS,
                "min_samples": DBSCAN_MIN_SAMPLES,
                "metric": "euclidean",
                "space": "imputed, standardized five-feature space",
            },
            "cluster_counts_including_noise": cluster_counts(dbscan_labels),
            "noise_count": int(np.count_nonzero(dbscan_labels == -1)),
            "silhouette_excludes_noise": True,
            "silhouette": dbscan_silhouette,
            "silhouette_status": dbscan_status,
            "cluster_summaries": summarize_clusters(features, dbscan_labels),
        },
        "visualization": {
            "method": "PCA with two components, fitted to standardized features",
            "purpose": "visualization only; clustering is performed in five dimensions",
            "explained_variance_ratio": [
                float(value) for value in pca.explained_variance_ratio_
            ],
            "coordinates": visualization_rows,
        },
        "limitations": [
            "All records and relationships are synthetic and have no clinical meaning.",
            "Cluster labels are arbitrary identifiers, not diagnoses or risk categories.",
            "Silhouette and inertia are internal heuristics and do not establish useful real-world segments.",
            "DBSCAN results depend strongly on eps, feature scaling, and local density.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = run_clustering()
    print(f"Saved clustering report: {REPORT_PATH}")
    print(
        f"K-Means selected k={report['kmeans']['selected_k']} "
        f"(silhouette={report['kmeans']['selected_silhouette']:.4f})"
    )
    print(
        f"DBSCAN clusters={len(report['dbscan']['cluster_counts_including_noise']) - int('-1' in report['dbscan']['cluster_counts_including_noise'])}, "
        f"noise={report['dbscan']['noise_count']}, "
        f"silhouette={report['dbscan']['silhouette']}"
    )


if __name__ == "__main__":
    main()
