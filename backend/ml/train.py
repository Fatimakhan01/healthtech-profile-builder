"""Train, compare, and evaluate baseline and logistic-regression pipelines."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


SEED = 42
DATA_PATH = Path(__file__).parent / "data" / "synthetic_appointments.csv"
OUTPUT_DIR = Path(__file__).parent / "outputs"
ARTIFACT_DIR = Path(__file__).parent / "artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / "no_show_pipeline.joblib"
ARTIFACT_METADATA_PATH = ARTIFACT_DIR / "no_show_pipeline.metadata.json"
ML_DEPENDENCIES = ("joblib", "numpy", "pandas", "scikit-learn", "scipy")
NUMERIC_FEATURES = ["days_ahead", "previous_no_shows"]
CATEGORICAL_FEATURES = ["sms_reminder", "weekday"]
FEATURE_NAMES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "no_show"


def make_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("one_hot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ]
    )


def make_pipeline(classifier: object) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", make_preprocessor()),
            ("model", classifier),
        ]
    )


def calculate_metrics(
    model: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
) -> dict[str, float | list[list[int]] | None]:
    predictions = model.predict(features)
    metrics: dict[str, float | list[list[int]] | None] = {
        "accuracy": float(accuracy_score(target, predictions)),
        "precision": float(precision_score(target, predictions, zero_division=0)),
        "recall": float(recall_score(target, predictions, zero_division=0)),
        "f1_score": float(f1_score(target, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(
            target, predictions, labels=[0, 1]
        ).tolist(),
    }

    if target.nunique() == 2:
        probabilities = model.predict_proba(features)[:, 1]
        metrics["roc_auc"] = float(roc_auc_score(target, probabilities))
    else:
        metrics["roc_auc"] = None

    return metrics


def class_distribution(
    target: pd.Series,
) -> dict[str, dict[str, float | int]]:
    counts = target.value_counts().reindex([0, 1], fill_value=0)
    proportions = target.value_counts(normalize=True).reindex([0, 1], fill_value=0)
    return {
        "attended_0": {
            "count": int(counts.loc[0]),
            "proportion": float(proportions.loc[0]),
        },
        "no_show_1": {
            "count": int(counts.loc[1]),
            "proportion": float(proportions.loc[1]),
        },
    }


def main() -> None:
    data = pd.read_csv(DATA_PATH)
    features = data[FEATURE_NAMES]
    target = data[TARGET]

    train_features, holdout_features, train_target, holdout_target = train_test_split(
        features,
        target,
        test_size=0.30,
        random_state=SEED,
        stratify=target,
    )
    validation_features, test_features, validation_target, test_target = (
        train_test_split(
            holdout_features,
            holdout_target,
            test_size=0.50,
            random_state=SEED,
            stratify=holdout_target,
        )
    )

    baseline = make_pipeline(DummyClassifier(strategy="most_frequent"))
    logistic = make_pipeline(
        LogisticRegression(
            random_state=SEED,
            max_iter=1_000,
            solver="lbfgs",
        )
    )
    baseline.fit(train_features, train_target)
    logistic.fit(train_features, train_target)

    validation_metrics = {
        "DummyClassifier": calculate_metrics(
            baseline, validation_features, validation_target
        ),
        "LogisticRegression": calculate_metrics(
            logistic, validation_features, validation_target
        ),
    }
    selected_name = max(
        validation_metrics,
        key=lambda name: validation_metrics[name]["f1_score"],
    )
    selected_model = baseline if selected_name == "DummyClassifier" else logistic
    test_metrics = calculate_metrics(selected_model, test_features, test_target)
    confusion = test_metrics["confusion_matrix"]
    false_positives = confusion[0][1]
    false_negatives = confusion[1][0]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(selected_model, ARTIFACT_PATH)
    artifact_sha256 = hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()
    model_version = f"no-show-{artifact_sha256}"
    artifact_metadata = {
        "metadata_schema_version": 1,
        "model_version": model_version,
        "artifact_sha256": artifact_sha256,
        "feature_names": FEATURE_NAMES,
        "positive_class": 1,
        "python_version": platform.python_version(),
        "dependencies": {
            dependency: importlib.metadata.version(dependency)
            for dependency in ML_DEPENDENCIES
        },
    }
    ARTIFACT_METADATA_PATH.write_text(
        json.dumps(artifact_metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata_sha256 = hashlib.sha256(
        ARTIFACT_METADATA_PATH.read_bytes()
    ).hexdigest()

    split_sizes = {
        "train": len(train_features),
        "validation": len(validation_features),
        "test": len(test_features),
    }
    distributions = {
        "overall": class_distribution(target),
        "train": class_distribution(train_target),
        "validation": class_distribution(validation_target),
        "test": class_distribution(test_target),
    }
    metadata = {
        "model_version": model_version,
        "random_seed": SEED,
        "split_strategy": "Stratified 70% train, 15% validation, 15% test",
        "split_sizes": split_sizes,
        "feature_names": FEATURE_NAMES,
        "target_name": TARGET,
        "class_distribution": distributions,
        "validation_metrics": validation_metrics,
        "selected_model": selected_name,
        "test_metrics": test_metrics,
        "error_analysis": {
            "false_positives": false_positives,
            "false_positive_meaning": (
                "Predicted no-show, but the synthetic label was attended."
            ),
            "false_negatives": false_negatives,
            "false_negative_meaning": (
                "Predicted attended, but the synthetic label was no-show."
            ),
        },
        "accuracy_note": (
            "Accuracy alone can hide poor detection of the less common class; "
            "consider precision, recall, F1, ROC-AUC, and the confusion matrix."
        ),
    }

    metrics_path = OUTPUT_DIR / "metrics.json"
    metrics_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Split sizes: {split_sizes}")
    print(f"Class distribution: {distributions['overall']}")
    print("Validation metrics:")
    print(json.dumps(validation_metrics, indent=2))
    print(f"Selected model (validation F1-score): {selected_name}")
    print("Test metrics:")
    print(json.dumps(test_metrics, indent=2))
    print(
        f"Test error analysis: {false_positives} false positives; "
        f"{false_negatives} false negatives."
    )
    print(metadata["accuracy_note"])
    print(f"Saved fitted pipeline: {ARTIFACT_PATH}")
    print(f"Saved artifact metadata: {ARTIFACT_METADATA_PATH}")
    print(f"Trusted artifact SHA-256: {artifact_sha256}")
    print(f"Trusted metadata SHA-256: {metadata_sha256}")
    print(f"Saved metrics and metadata: {metrics_path}")


if __name__ == "__main__":
    main()
