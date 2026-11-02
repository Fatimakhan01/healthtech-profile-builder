"""Evaluate the saved synthetic no-show pipeline without fitting or saving models."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split


SEED = 42
DATA_PATH = Path(__file__).parent / "data" / "synthetic_appointments.csv"
MODEL_PATH = Path(__file__).parent / "artifacts" / "no_show_pipeline.joblib"
FEATURE_NAMES = [
    "days_ahead",
    "previous_no_shows",
    "sms_reminder",
    "weekday",
]
TARGET = "no_show"
THRESHOLDS = (0.30, 0.40, 0.50, 0.60, 0.70)
CALIBRATION_BIN_COUNT = 5


def positive_class_probabilities(model, features: pd.DataFrame) -> np.ndarray:
    class_indices = np.flatnonzero(model.classes_ == 1)
    if len(class_indices) != 1:
        raise ValueError("The saved pipeline must contain the no-show class (1).")
    return model.predict_proba(features)[:, class_indices[0]]


def classification_metrics(
    model,
    features: pd.DataFrame,
    target: pd.Series,
) -> dict[str, float | list[list[int]]]:
    predictions = model.predict(features)
    probabilities = positive_class_probabilities(model, features)
    return {
        "accuracy": float((predictions == target).mean()),
        "precision": float(
            precision_score(target, predictions, pos_label=1, zero_division=0)
        ),
        "recall": float(recall_score(target, predictions, pos_label=1)),
        "binary_f1": float(f1_score(target, predictions, pos_label=1)),
        "roc_auc": float(roc_auc_score(target, probabilities)),
        "confusion_matrix": confusion_matrix(
            target, predictions, labels=[0, 1]
        ).tolist(),
    }


def validation_threshold_metrics(
    target: pd.Series,
    probabilities: np.ndarray,
) -> list[dict[str, float | list[list[int]]]]:
    results = []
    for threshold in THRESHOLDS:
        predictions = (probabilities >= threshold).astype(int)
        results.append(
            {
                "threshold": threshold,
                "precision": float(
                    precision_score(target, predictions, zero_division=0)
                ),
                "recall": float(recall_score(target, predictions, zero_division=0)),
                "f1_score": float(f1_score(target, predictions, zero_division=0)),
                "confusion_matrix": confusion_matrix(
                    target, predictions, labels=[0, 1]
                ).tolist(),
                "predicted_positive_rate": float(predictions.mean()),
            }
        )
    return results


def calibration_bins(
    target: pd.Series,
    probabilities: np.ndarray,
) -> list[dict[str, float | int]]:
    bin_edges = np.linspace(0.0, 1.0, CALIBRATION_BIN_COUNT + 1)
    bin_indices = np.minimum(
        np.digitize(probabilities, bin_edges[1:-1]),
        CALIBRATION_BIN_COUNT - 1,
    )
    results = []
    for bin_index in range(CALIBRATION_BIN_COUNT):
        in_bin = bin_indices == bin_index
        count = int(in_bin.sum())
        if count:
            results.append(
                {
                    "lower_bound": float(bin_edges[bin_index]),
                    "upper_bound": float(bin_edges[bin_index + 1]),
                    "count": count,
                    "mean_predicted_probability": float(
                        probabilities[in_bin].mean()
                    ),
                    "observed_no_show_rate": float(target.iloc[in_bin].mean()),
                }
            )
        else:
            results.append(
                {
                    "lower_bound": float(bin_edges[bin_index]),
                    "upper_bound": float(bin_edges[bin_index + 1]),
                    "count": 0,
                    "mean_predicted_probability": None,
                    "observed_no_show_rate": None,
                }
            )
    return results


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
    model = joblib.load(MODEL_PATH)
    train_validation_metrics = {
        "positive_class": "no_show=1",
        "confusion_matrix_order": {
            "rows": ["actual_attended=0", "actual_no_show=1"],
            "columns": ["predicted_attended=0", "predicted_no_show=1"],
        },
        "train": classification_metrics(model, train_features, train_target),
        "validation": classification_metrics(
            model, validation_features, validation_target
        ),
    }
    validation_probabilities = positive_class_probabilities(
        model, validation_features
    )
    test_probabilities = positive_class_probabilities(model, test_features)

    test_prevalence = float(test_target.mean())
    results = {
        "scope": (
            "Synthetic data only; evaluates the saved pipeline without fitting "
            "or modifying artifacts."
        ),
        "split_sizes": {
            "train": len(train_features),
            "validation": len(validation_features),
            "test": len(test_features),
        },
        "saved_model_train_validation_metrics": train_validation_metrics,
        "validation_threshold_metrics": validation_threshold_metrics(
            validation_target, validation_probabilities
        ),
        "test_final_evaluation": {
            "roc_auc": float(roc_auc_score(test_target, test_probabilities)),
            "brier_score": float(
                brier_score_loss(test_target, test_probabilities)
            ),
            "prevalence_baseline_brier_score": float(
                brier_score_loss(
                    test_target,
                    np.full(len(test_target), test_prevalence),
                )
            ),
            "observed_no_show_rate": test_prevalence,
            "mean_predicted_probability": float(test_probabilities.mean()),
            "calibration_bins": calibration_bins(test_target, test_probabilities),
        },
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
