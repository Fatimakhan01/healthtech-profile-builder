"""Compare a majority baseline and focused Logistic Regression variants."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

if __package__:
    from . import train
else:
    import train


OUTPUT_PATH = train.OUTPUT_DIR / "model_improvement_experiments.json"
OOF_FOLDS = 5
OOF_SEED = 42
CLASS_WEIGHT_VARIANTS = {
    "unweighted": None,
    "moderate_positive_weight": {0: 1.0, 1: 1.5},
    "balanced": "balanced",
}


def metrics_at_threshold(
    target: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    predictions = (probabilities >= threshold).astype(int)
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


def select_f1_threshold(
    target: pd.Series,
    probabilities: np.ndarray,
) -> tuple[float, dict[str, float]]:
    """Choose an F1 threshold using out-of-fold training probabilities only."""
    thresholds = np.unique(probabilities)
    scored = []
    for threshold in thresholds:
        predictions = probabilities >= threshold
        scored.append(
            (
                float(f1_score(target, predictions, zero_division=0)),
                float(precision_score(target, predictions, zero_division=0)),
                float(threshold),
                float(recall_score(target, predictions, zero_division=0)),
            )
        )
    f1, precision, threshold, recall = max(scored)
    return threshold, {
        "f1_score": f1,
        "precision": precision,
        "recall": recall,
    }


def positive_class_probabilities(
    model: Pipeline,
    features: pd.DataFrame,
) -> np.ndarray:
    classes = list(model.classes_)
    if 1 not in classes:
        raise ValueError("The fitted classifier must include positive class 1.")
    return model.predict_proba(features)[:, classes.index(1)]


def existing_validation_comparisons(
    original_metrics: dict[str, Any],
) -> dict[str, Any]:
    candidates = {}
    for name in (
        "LogisticRegression",
        "RandomForestClassifier",
        "GradientBoostingClassifier",
        "TunedRandomForestClassifier",
    ):
        candidates[name] = {
            "source": "Existing original model_comparison.json",
            "threshold": 0.5,
            "validation": original_metrics["training_metrics"][name]["validation"],
        }
    return candidates


def run_experiment(
    output_path: Path = OUTPUT_PATH,
    data_path: Path = train.DATA_PATH,
    original_metrics_path: Path = train.METRICS_PATH,
) -> dict[str, Any]:
    features, target = train.load_features_and_target(data_path)
    splits = train.split_dataset(features, target)
    train_x, train_y = splits["train"]
    validation_x, validation_y = splits["validation"]

    original_metrics = json.loads(original_metrics_path.read_text(encoding="utf-8"))
    candidates = existing_validation_comparisons(original_metrics)

    dummy = train.make_pipeline(DummyClassifier(strategy="most_frequent"))
    dummy.fit(train_x, train_y)
    dummy_probabilities = positive_class_probabilities(dummy, validation_x)
    candidates["DummyClassifier"] = {
        "source": "Fitted on the experiment training split",
        "parameters": {"strategy": "most_frequent"},
        "threshold": 0.5,
        "validation": metrics_at_threshold(
            validation_y, dummy_probabilities, 0.5
        ),
    }

    cv = StratifiedKFold(n_splits=OOF_FOLDS, shuffle=True, random_state=OOF_SEED)
    for variant, class_weight in CLASS_WEIGHT_VARIANTS.items():
        pipeline = train.make_pipeline(
            LogisticRegression(
                class_weight=class_weight,
                max_iter=1_000,
                random_state=train.SEED,
            )
        )
        oof_probabilities = cross_val_predict(
            pipeline,
            train_x,
            train_y,
            cv=cv,
            method="predict_proba",
            n_jobs=1,
        )[:, 1]
        selected_threshold, oof_metrics = select_f1_threshold(
            train_y, oof_probabilities
        )
        pipeline.fit(train_x, train_y)
        validation_probabilities = positive_class_probabilities(
            pipeline, validation_x
        )

        for threshold_name, threshold in (
            ("default_0_5", 0.5),
            ("training_oof_f1", selected_threshold),
        ):
            name = f"LogisticRegression_{variant}_{threshold_name}"
            candidates[name] = {
                "source": "Fitted on experiment training split",
                "parameters": {
                    "class_weight": (
                        {str(label): weight for label, weight in class_weight.items()}
                        if isinstance(class_weight, dict)
                        else class_weight
                    ),
                    "max_iter": 1_000,
                    "random_state": train.SEED,
                },
                "threshold": threshold,
                "threshold_selection": (
                    "Default predict_proba threshold"
                    if threshold_name == "default_0_5"
                    else "Max F1 on 5-fold out-of-fold training probabilities"
                ),
                "training_oof_f1_at_selected_threshold": (
                    oof_metrics if threshold_name == "training_oof_f1" else None
                ),
                "validation": metrics_at_threshold(
                    validation_y, validation_probabilities, threshold
                ),
            }

    selected_name = max(
        candidates,
        key=lambda name: candidates[name]["validation"]["f1_score"],
    )
    selected_f1 = candidates[selected_name]["validation"]["f1_score"]
    original_f1 = candidates["LogisticRegression"]["validation"]["f1_score"]
    result = {
        "experiment": "Dummy baseline and Logistic Regression class-weight/threshold variants",
        "random_seed": train.SEED,
        "split_strategy": "Stratified 70% train, 15% validation, 15% test; test not accessed",
        "split_sizes": {
            "train": len(train_x),
            "validation": len(validation_x),
        },
        "training_oof_threshold_selection": {
            "method": "StratifiedKFold",
            "n_splits": OOF_FOLDS,
            "shuffle": True,
            "random_state": OOF_SEED,
            "training_partition_only": True,
            "selection_metric": "F1",
        },
        "forest_search_assessment": (
            "The existing eight-combination Random Forest search is retained; "
            "no additional forest search was run."
        ),
        "candidates": candidates,
        "selection_metric": "validation F1",
        "selected_candidate": selected_name,
        "selected_f1_delta_vs_original_logistic_regression": (
            selected_f1 - original_f1
        ),
        "interpretation": (
            "The top validation candidate is selected for comparison only. "
            "A small single-split F1 difference is not evidence of a robust "
            "improvement; retain the original Logistic Regression pipeline."
        ),
        "original_pipeline_action": "Preserved; no artifact was replaced.",
        "test_metrics": None,
        "test_usage": "The test partition was not used for fitting, threshold selection, comparison, or reporting.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Selected validation candidate: {selected_name}")
    print(f"Saved experiment report: {output_path}")
    return result


def main() -> None:
    run_experiment()


if __name__ == "__main__":
    main()
