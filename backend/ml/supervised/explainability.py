"""Read-only explainability and error analysis for the saved pipeline."""

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import f1_score

if __package__:
    from . import train
else:
    import train


FEATURE_IMPORTANCE_PATH = train.OUTPUT_DIR / "feature_importance.json"
ERROR_ANALYSIS_PATH = train.OUTPUT_DIR / "error_analysis.json"
PERMUTATION_REPEATS = 30


def calculate_feature_importance(
    model: Any,
    validation_features: pd.DataFrame,
    validation_target: pd.Series,
    n_repeats: int = PERMUTATION_REPEATS,
) -> dict[str, Any]:
    result = permutation_importance(
        model,
        validation_features,
        validation_target,
        scoring="f1",
        n_repeats=n_repeats,
        random_state=train.SEED,
        n_jobs=1,
    )
    ranked = sorted(
        zip(
            train.FEATURE_NAMES,
            result.importances_mean,
            result.importances_std,
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "model": "saved LogisticRegression pipeline",
        "split": "validation",
        "split_size": len(validation_features),
        "scoring": "f1",
        "baseline_f1": float(
            f1_score(
                validation_target,
                model.predict(validation_features),
                zero_division=0,
            )
        ),
        "n_repeats": n_repeats,
        "random_state": train.SEED,
        "importance_definition": (
            "Mean decrease in validation F1 when one original input feature "
            "is permuted; larger positive values indicate greater reliance "
            "for this fitted model on this validation split."
        ),
        "features": [
            {
                "feature": feature,
                "importance_mean": float(mean),
                "importance_std": float(std),
            }
            for feature, mean, std in ranked
        ],
        "interpretation_note": (
            "Permutation importance is split- and model-specific, not causal. "
            "Correlated inputs may share or mask importance."
        ),
    }


def summarize_feature_patterns(features: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {"record_count": len(features), "features": {}}
    for column in train.FEATURE_NAMES:
        values = features[column]
        non_missing = values.dropna()
        if column in train.NUMERIC_FEATURES or column in train.BINARY_FEATURES:
            summary["features"][column] = {
                "type": "numeric_or_binary",
                "non_missing_count": int(non_missing.size),
                "missing_count": int(values.isna().sum()),
                "mean": (
                    float(non_missing.mean()) if not non_missing.empty else None
                ),
                "median": (
                    float(non_missing.median()) if not non_missing.empty else None
                ),
            }
        else:
            counts = non_missing.value_counts().sort_index()
            denominator = int(non_missing.size)
            summary["features"][column] = {
                "type": "categorical",
                "non_missing_count": denominator,
                "missing_count": int(values.isna().sum()),
                "category_proportions": {
                    str(category): float(count / denominator)
                    for category, count in counts.items()
                }
                if denominator
                else {},
            }
    return summary


def analyze_errors(
    features: pd.DataFrame,
    target: pd.Series,
    predictions: np.ndarray,
) -> dict[str, Any]:
    if len(features) != len(target) or len(target) != len(predictions):
        raise ValueError("Features, target, and predictions must have equal lengths.")

    actual = target.to_numpy()
    predicted = np.asarray(predictions)
    if not np.isin(actual, [0, 1]).all() or not np.isin(predicted, [0, 1]).all():
        raise ValueError("Actual and predicted labels must contain only 0 and 1.")

    false_positive_mask = (predicted == 1) & (actual == 0)
    false_negative_mask = (predicted == 0) & (actual == 1)
    correct_mask = predicted == actual
    actual_attended = int((actual == 0).sum())
    actual_no_show = int((actual == 1).sum())
    total = len(actual)

    def error_group(mask: np.ndarray, denominator: int) -> dict[str, Any]:
        count = int(mask.sum())
        group_features = features.loc[mask]
        return {
            "count": count,
            "percent_of_test_set": float(100 * count / total) if total else 0.0,
            "percent_of_actual_class": (
                float(100 * count / denominator) if denominator else 0.0
            ),
            "feature_patterns": summarize_feature_patterns(group_features),
        }

    confusion = [
        [
            int(((actual == 0) & (predicted == 0)).sum()),
            int(((actual == 0) & (predicted == 1)).sum()),
        ],
        [
            int(((actual == 1) & (predicted == 0)).sum()),
            int(((actual == 1) & (predicted == 1)).sum()),
        ],
    ]
    return {
        "model": "saved LogisticRegression pipeline",
        "split": "test",
        "split_size": total,
        "prediction_rule": "Saved pipeline predict() at its default decision threshold.",
        "positive_class": "no_show=1",
        "confusion_matrix": {
            "labels": [0, 1],
            "rows": ["actual_attended_0", "actual_no_show_1"],
            "columns": ["predicted_attended_0", "predicted_no_show_1"],
            "counts": confusion,
        },
        "false_positives": error_group(false_positive_mask, actual_attended),
        "false_negatives": error_group(false_negative_mask, actual_no_show),
        "correct_predictions": {
            "count": int(correct_mask.sum()),
            "feature_patterns": summarize_feature_patterns(
                features.loc[correct_mask]
            ),
        },
        "interpretation_note": (
            "Feature patterns are aggregate descriptive summaries only. "
            "They do not explain causation, diagnose individuals, or justify "
            "test-set model, feature, or threshold changes."
        ),
    }


def save_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_analysis(
    artifact_path: Path = train.ARTIFACT_PATH,
    data_path: Path = train.DATA_PATH,
    feature_importance_path: Path = FEATURE_IMPORTANCE_PATH,
    error_analysis_path: Path = ERROR_ANALYSIS_PATH,
    n_repeats: int = PERMUTATION_REPEATS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    features, target = train.load_features_and_target(data_path)
    splits = train.split_dataset(features, target)
    validation_features, validation_target = splits["validation"]
    test_features, test_target = splits["test"]

    model = joblib.load(artifact_path)
    if not isinstance(model, train.Pipeline):
        raise TypeError("Saved artifact is not a scikit-learn Pipeline.")
    if tuple(getattr(model, "feature_names_in_", ())) != tuple(train.FEATURE_NAMES):
        raise ValueError("Saved pipeline feature schema does not match Week 4.")
    classifier = model.named_steps.get("model")
    if classifier is None or classifier.__class__.__name__ != "LogisticRegression":
        raise ValueError("Saved Week 4 pipeline is not the selected Logistic Regression.")

    importance = calculate_feature_importance(
        model,
        validation_features,
        validation_target,
        n_repeats=n_repeats,
    )
    test_predictions = model.predict(test_features)
    errors = analyze_errors(test_features, test_target, test_predictions)

    save_report(feature_importance_path, importance)
    save_report(error_analysis_path, errors)
    return importance, errors


def main() -> None:
    importance, errors = run_analysis()
    print(f"Saved permutation importance: {FEATURE_IMPORTANCE_PATH}")
    print(f"Saved test error analysis: {ERROR_ANALYSIS_PATH}")
    print("Top permutation-importance features:")
    print(json.dumps(importance["features"][:5], indent=2))
    print(
        "False positives: "
        f"{errors['false_positives']['count']}; false negatives: "
        f"{errors['false_negatives']['count']}"
    )


if __name__ == "__main__":
    main()
