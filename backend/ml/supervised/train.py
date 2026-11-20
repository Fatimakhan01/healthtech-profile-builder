"""Train, compare, and evaluate the separate Week 4 supervised ML models."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    GridSearchCV,
    StratifiedKFold,
    cross_validate,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

if __package__:
    from .evaluate import classification_metrics
else:
    from evaluate import classification_metrics


SEED = 42
ML_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ML_DIR / "data" / "appointment_attendance.csv"
OUTPUT_DIR = ML_DIR / "reports"
ARTIFACT_DIR = ML_DIR / "artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / "supervised_pipeline.joblib"
METADATA_PATH = ARTIFACT_DIR / "supervised_pipeline.metadata.json"
METRICS_PATH = OUTPUT_DIR / "model_comparison.json"
CONFUSION_MATRICES_PATH = OUTPUT_DIR / "confusion_matrices.json"
CV_RESULTS_PATH = OUTPUT_DIR / "cross_validation.json"
GRID_RESULTS_PATH = OUTPUT_DIR / "hyperparameter_search.json"

TARGET = "no_show"
NUMERIC_FEATURES = [
    "days_ahead",
    "previous_appointments",
    "previous_no_shows",
    "appointment_hour",
    "distance_km",
    "portal_activity",
    "engagement_score",
]
BINARY_FEATURES = ["sms_reminder"]
CATEGORICAL_FEATURES = ["weekday", "appointment_type"]
FEATURE_NAMES = NUMERIC_FEATURES + BINARY_FEATURES + CATEGORICAL_FEATURES
FEATURE_SCHEMA = {
    "days_ahead": {
        "type": "numeric",
        "meaning": "Whole days between booking and appointment, from 0 to 60.",
    },
    "previous_appointments": {
        "type": "numeric",
        "meaning": "Fictional count of prior appointments, from 0 to 15.",
    },
    "previous_no_shows": {
        "type": "numeric",
        "meaning": "Fictional count of prior missed appointments; never exceeds prior appointments.",
    },
    "sms_reminder": {
        "type": "binary",
        "meaning": "Whether a reminder was scheduled at booking time (1=yes, 0=no).",
    },
    "weekday": {
        "type": "categorical",
        "meaning": "Scheduled day of week.",
    },
    "appointment_hour": {
        "type": "numeric",
        "meaning": "Scheduled local hour, from 8 through 18.",
    },
    "distance_km": {
        "type": "numeric",
        "meaning": "Fictional distance to appointment location in kilometers.",
    },
    "appointment_type": {
        "type": "categorical",
        "meaning": "Fictional booking category: routine, follow_up, consultation, or procedure.",
    },
    "portal_activity": {
        "type": "numeric",
        "meaning": "Fictional count of portal actions before the appointment.",
    },
    "engagement_score": {
        "type": "numeric",
        "meaning": "Fictional 0-100 engagement score available before the appointment.",
    },
}
CV_SCORING = {
    "accuracy": "accuracy",
    "precision": "precision",
    "recall": "recall",
    "f1": "f1",
    "roc_auc": "roc_auc",
    "average_precision": "average_precision",
}
GRID_PARAM_GRID = {
    "model__n_estimators": [100, 200],
    "model__max_depth": [None, 10],
    "model__min_samples_leaf": [1, 3],
}


def make_preprocessor() -> ColumnTransformer:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    binary = SimpleImputer(strategy="most_frequent")
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("one_hot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric, NUMERIC_FEATURES),
            ("binary", binary, BINARY_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ]
    )


def make_pipeline(classifier: Any) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocessor", make_preprocessor()),
            ("model", classifier),
        ]
    )


def make_models() -> dict[str, Pipeline]:
    return {
        "LogisticRegression": make_pipeline(
            LogisticRegression(
                class_weight="balanced",
                max_iter=1_000,
                random_state=SEED,
            )
        ),
        "RandomForestClassifier": make_pipeline(
            RandomForestClassifier(
                class_weight="balanced_subsample",
                n_estimators=100,
                random_state=SEED,
                n_jobs=1,
            )
        ),
        "GradientBoostingClassifier": make_pipeline(
            GradientBoostingClassifier(random_state=SEED)
        ),
    }


def load_features_and_target(data_path: Path = DATA_PATH) -> tuple[pd.DataFrame, pd.Series]:
    data = pd.read_csv(data_path)
    if TARGET not in data.columns:
        raise ValueError(f"Dataset is missing target column {TARGET!r}.")
    if set(FEATURE_NAMES) - set(data.columns):
        raise ValueError("Dataset is missing one or more documented features.")
    if TARGET in FEATURE_NAMES:
        raise ValueError("Target leakage: target column is included in features.")
    features = data.loc[:, FEATURE_NAMES]
    target = data[TARGET]
    if not target.isin([0, 1]).all():
        raise ValueError("Target must contain only binary values 0 and 1.")
    return features, target


def split_dataset(
    features: pd.DataFrame,
    target: pd.Series,
) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
    train_x, holdout_x, train_y, holdout_y = train_test_split(
        features,
        target,
        test_size=0.30,
        random_state=SEED,
        stratify=target,
    )
    validation_x, test_x, validation_y, test_y = train_test_split(
        holdout_x,
        holdout_y,
        test_size=0.50,
        random_state=SEED,
        stratify=holdout_y,
    )
    return {
        "train": (train_x, train_y),
        "validation": (validation_x, validation_y),
        "test": (test_x, test_y),
    }


def summarize_cross_validation(
    features: pd.DataFrame,
    target: pd.Series,
) -> dict[str, Any]:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    results = {}
    for name, model in make_models().items():
        scores = cross_validate(
            model,
            features,
            target,
            cv=cv,
            scoring=CV_SCORING,
            return_train_score=False,
            n_jobs=1,
        )
        results[name] = {
            metric: {
                "mean": float(pd.Series(scores[f"test_{metric}"]).mean()),
                "std": float(pd.Series(scores[f"test_{metric}"]).std(ddof=1)),
                "fold_scores": [float(value) for value in scores[f"test_{metric}"]],
            }
            for metric in CV_SCORING
        }
    return results


def tune_random_forest(
    train_features: pd.DataFrame,
    train_target: pd.Series,
) -> GridSearchCV:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    search = GridSearchCV(
        estimator=make_pipeline(
            RandomForestClassifier(
                class_weight="balanced_subsample",
                random_state=SEED,
                n_jobs=1,
            )
        ),
        param_grid=GRID_PARAM_GRID,
        scoring="f1",
        cv=cv,
        refit=True,
        n_jobs=1,
        return_train_score=False,
    )
    search.fit(train_features, train_target)
    return search


def class_distribution(target: pd.Series) -> dict[str, Any]:
    counts = target.value_counts().reindex([0, 1], fill_value=0)
    return {
        str(label): {
            "count": int(counts.loc[label]),
            "proportion": float(counts.loc[label] / len(target)),
        }
        for label in (0, 1)
    }


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run_training(
    data_path: Path = DATA_PATH,
    output_dir: Path = OUTPUT_DIR,
    artifact_dir: Path = ARTIFACT_DIR,
) -> dict[str, Any]:
    features, target = load_features_and_target(data_path)
    splits = split_dataset(features, target)
    train_x, train_y = splits["train"]
    validation_x, validation_y = splits["validation"]
    test_x, test_y = splits["test"]

    # Cross-validation and tuning receive training rows only; test remains untouched.
    cv_results = summarize_cross_validation(train_x, train_y)
    search = tune_random_forest(train_x, train_y)
    models = make_models()
    models["TunedRandomForestClassifier"] = search.best_estimator_
    candidate_metrics: dict[str, dict[str, Any]] = {}
    matrices: dict[str, dict[str, Any]] = {}

    for name, model in models.items():
        if name != "TunedRandomForestClassifier":
            model.fit(train_x, train_y)
        candidate_metrics[name] = {
            "parameters": model.named_steps["model"].get_params(deep=False),
            "training": classification_metrics(model, train_x, train_y),
            "validation": classification_metrics(model, validation_x, validation_y),
        }
        matrices[name] = {
            split_name: candidate_metrics[name][split_name]["confusion_matrix"]
            for split_name in ("training", "validation")
        }
        matrices[name]["matrix_order"] = {
            "rows": ["actual_0_attended", "actual_1_no_show"],
            "columns": ["predicted_0_attended", "predicted_1_no_show"],
        }

    selected_name = max(
        candidate_metrics,
        key=lambda name: (
            candidate_metrics[name]["validation"]["f1_score"],
            search.best_score_ if name == "TunedRandomForestClassifier" else
            cv_results.get(name, {}).get("f1", {}).get("mean", 0.0),
        ),
    )
    selected_model = models[selected_name]
    final_test_metrics = classification_metrics(selected_model, test_x, test_y)
    matrices["selected_final_model"] = {
        "name": selected_name,
        "test": final_test_metrics["confusion_matrix"],
        "matrix_order": {
            "rows": ["actual_0_attended", "actual_1_no_show"],
            "columns": ["predicted_0_attended", "predicted_1_no_show"],
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / ARTIFACT_PATH.name
    metadata_path = artifact_dir / METADATA_PATH.name
    joblib.dump(selected_model, artifact_path)
    artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

    split_sizes = {name: len(split[0]) for name, split in splits.items()}
    distributions = {
        "overall": class_distribution(target),
        **{name: class_distribution(split[1]) for name, split in splits.items()},
    }
    try:
        sklearn_version = importlib.metadata.version("scikit-learn")
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError("scikit-learn version is required for metadata.") from error

    metrics = {
        "dataset": str(data_path),
        "dataset_description": "2,000 fictional synthetic appointment records; no real patient data.",
        "random_seed": SEED,
        "split_strategy": "Stratified 70% train, 15% validation, 15% test",
        "split_sizes": split_sizes,
        "class_distribution": distributions,
        "feature_names": FEATURE_NAMES,
        "target_name": TARGET,
        "training_metrics": candidate_metrics,
        "selected_model": selected_name,
        "selection_rule": (
            "Highest validation binary F1; ties use training-only cross-validation "
            "mean F1 (GridSearchCV best mean F1 for the tuned forest)."
        ),
        "test_metrics": final_test_metrics,
    }
    grid_results = {
        "training_rows_only": True,
        "training_row_count": len(train_x),
        "scoring": "f1",
        "folds": 5,
        "best_params": search.best_params_,
        "best_cv_f1_mean": float(search.best_score_),
        "results": [
            {
                "params": search.cv_results_["params"][index],
                "mean_test_f1": float(search.cv_results_["mean_test_score"][index]),
                "std_test_f1": float(search.cv_results_["std_test_score"][index]),
                "rank_test_f1": int(search.cv_results_["rank_test_score"][index]),
            }
            for index in range(len(search.cv_results_["params"]))
        ],
    }
    metadata = {
        "metadata_schema_version": 1,
        "model_name": selected_name,
        "model_version": f"week4-supervised-{artifact_sha256}",
        "artifact_sha256": artifact_sha256,
        "dataset_description": metrics["dataset_description"],
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "feature_schema": FEATURE_SCHEMA,
        "feature_names": FEATURE_NAMES,
        "target_name": TARGET,
        "random_seed": SEED,
        "split_strategy": metrics["split_strategy"],
        "split_sizes": split_sizes,
        "training_configuration": {
            "candidate_models": list(models),
            "model_parameters": {
                name: model.named_steps["model"].get_params(deep=False)
                for name, model in models.items()
            },
            "cross_validation": {
                "type": "StratifiedKFold",
                "n_splits": 5,
                "shuffle": True,
                "random_state": SEED,
                "training_data_only": True,
            },
            "grid_search": {
                "model": "RandomForestClassifier",
                "scoring": "f1",
                "best_params": search.best_params_,
                "best_cv_f1_mean": float(search.best_score_),
            },
            "selected_model": selected_name,
        },
        "python_version": platform.python_version(),
        "scikit_learn_version": sklearn_version,
        "positive_class": 1,
    }

    save_json(output_dir / METRICS_PATH.name, metrics)
    save_json(output_dir / CONFUSION_MATRICES_PATH.name, matrices)
    save_json(output_dir / CV_RESULTS_PATH.name, cv_results)
    save_json(output_dir / GRID_RESULTS_PATH.name, grid_results)
    save_json(metadata_path, metadata)

    print(f"Split sizes: {split_sizes}")
    print(f"Overall class distribution: {distributions['overall']}")
    print(f"Selected model by validation F1: {selected_name}")
    print(json.dumps(candidate_metrics, indent=2))
    print(f"Final test metrics: {json.dumps(final_test_metrics)}")
    print(f"5-fold RF GridSearchCV best parameters: {search.best_params_}")
    print(f"5-fold RF GridSearchCV best mean F1: {search.best_score_:.4f}")
    print(f"Saved Week 4 pipeline: {artifact_path}")
    print(f"Saved Week 4 metadata: {metadata_path}")
    return metrics


def main() -> None:
    run_training()


if __name__ == "__main__":
    main()
