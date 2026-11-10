"""Evaluation metrics for the supervised appointment pipeline."""

from typing import Any

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline


def classification_metrics(
    model: Pipeline,
    features: pd.DataFrame,
    target: pd.Series,
) -> dict[str, Any]:
    predictions = model.predict(features)
    probabilities = model.predict_proba(features)[:, list(model.classes_).index(1)]
    return {
        "accuracy": float(accuracy_score(target, predictions)),
        "precision": float(precision_score(target, predictions, zero_division=0)),
        "recall": float(recall_score(target, predictions, zero_division=0)),
        "f1_score": float(f1_score(target, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(target, probabilities)),
        "average_precision": float(average_precision_score(target, probabilities)),
        "confusion_matrix": confusion_matrix(
            target, predictions, labels=[0, 1]
        ).tolist(),
    }
