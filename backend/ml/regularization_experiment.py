"""Compare Logistic Regression regularization using training-only CV."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    make_scorer,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

from train import FEATURE_NAMES, SEED, TARGET, make_pipeline


DATA_PATH = Path(__file__).parent / "data" / "synthetic_appointments.csv"
REPORT_PATH = Path(__file__).parent / "outputs" / "regularization_experiment.json"
FOLD_COUNT = 5
C_VALUES = (0.1, 1.0, 10.0)


def main() -> None:
    data = pd.read_csv(DATA_PATH)
    features = data[FEATURE_NAMES]
    target = data[TARGET]
    train_features, _, train_target, _ = train_test_split(
        features,
        target,
        test_size=0.30,
        random_state=SEED,
        stratify=target,
    )

    folds = StratifiedKFold(
        n_splits=FOLD_COUNT,
        shuffle=True,
        random_state=SEED,
    )
    fold_indices = list(folds.split(train_features, train_target))
    scoring = {
        "accuracy": make_scorer(accuracy_score),
        "precision": make_scorer(
            precision_score,
            pos_label=1,
            zero_division=0,
        ),
        "recall": make_scorer(recall_score, pos_label=1),
        "binary_f1": make_scorer(f1_score, pos_label=1),
        "roc_auc": make_scorer(roc_auc_score, response_method="predict_proba"),
    }

    candidates = [
        ("DummyClassifier", make_pipeline(DummyClassifier(strategy="most_frequent"))),
        *[
            (
                f"LogisticRegression_C={c_value:g}",
                make_pipeline(
                    LogisticRegression(
                        C=c_value,
                        random_state=SEED,
                        max_iter=1_000,
                        solver="lbfgs",
                    )
                ),
            )
            for c_value in C_VALUES
        ],
    ]

    results = []
    for name, estimator in candidates:
        scores = cross_validate(
            estimator,
            train_features,
            train_target,
            cv=fold_indices,
            scoring=scoring,
            return_train_score=False,
        )
        metric_summary = {
            metric: {
                "mean": float(np.mean(scores[f"test_{metric}"])),
                "std": float(np.std(scores[f"test_{metric}"], ddof=1)),
            }
            for metric in scoring
        }
        results.append({"candidate": name, "metrics_mean_and_sample_std": metric_summary})

    selected = max(
        results,
        key=lambda result: result["metrics_mean_and_sample_std"]["binary_f1"][
            "mean"
        ],
    )
    report = {
        "scope": (
            "Synthetic data only. Cross-validation uses only the existing "
            "training partition; validation and test partitions are not used."
        ),
        "positive_class": "no_show=1",
        "training_partition_size": len(train_features),
        "split": {
            "training_fraction": 0.70,
            "stratified": True,
            "random_seed": SEED,
        },
        "cross_validation": {
            "strategy": f"{FOLD_COUNT}-fold StratifiedKFold",
            "shuffle": True,
            "random_seed": SEED,
            "same_folds_for_all_candidates": True,
        },
        "candidate_configurations": {
            "dummy": "DummyClassifier(strategy='most_frequent')",
            "logistic_regression": {
                "solver": "lbfgs",
                "max_iter": 1000,
                "C_values": list(C_VALUES),
                "current_configuration": "C=1.0",
            },
        },
        "scikit_learn_version": sklearn.__version__,
        "scipy_version": scipy.__version__,
        "selection_rule": (
            "Highest mean cross-validation binary F1 only; exact ties keep "
            "the first candidate in the documented order."
        ),
        "selected_candidate_by_training_cv_f1": selected["candidate"],
        "candidates": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved experiment report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
