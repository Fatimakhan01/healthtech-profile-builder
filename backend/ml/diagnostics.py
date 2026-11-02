"""Run train-only cross-validation and learning-curve diagnostics."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    StratifiedKFold,
    learning_curve,
    train_test_split,
    cross_validate,
)

from train import FEATURE_NAMES, SEED, TARGET, make_pipeline


DATA_PATH = Path(__file__).parent / "data" / "synthetic_appointments.csv"
OUTPUT_PATH = Path(__file__).parent / "outputs" / "learning_curve.png"
FOLD_COUNT = 5
TRAIN_SIZE_FRACTIONS = np.linspace(0.2, 1.0, 5)


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
    train_test_split(
        holdout_features,
        holdout_target,
        test_size=0.50,
        random_state=SEED,
        stratify=holdout_target,
    )

    estimator = make_pipeline(
        LogisticRegression(
            random_state=SEED,
            max_iter=1_000,
            solver="lbfgs",
        )
    )
    folds = StratifiedKFold(
        n_splits=FOLD_COUNT,
        shuffle=True,
        random_state=SEED,
    )
    scoring = {
        "accuracy": "accuracy",
        "precision": "precision",
        "recall": "recall",
        "binary_f1": "f1",
        "roc_auc": "roc_auc",
    }
    cross_validation = cross_validate(
        estimator,
        train_features,
        train_target,
        cv=folds,
        scoring=scoring,
        return_train_score=False,
    )
    metrics = {
        metric: {
            "mean": float(np.mean(cross_validation[f"test_{metric}"])),
            "std": float(np.std(cross_validation[f"test_{metric}"], ddof=1)),
        }
        for metric in scoring
    }

    sizes, train_scores, validation_scores = learning_curve(
        estimator,
        train_features,
        train_target,
        train_sizes=TRAIN_SIZE_FRACTIONS,
        cv=folds,
        scoring="f1",
        shuffle=True,
        random_state=SEED,
        n_jobs=1,
    )
    train_means = train_scores.mean(axis=1)
    train_stds = train_scores.std(axis=1, ddof=1)
    validation_means = validation_scores.mean(axis=1)
    validation_stds = validation_scores.std(axis=1, ddof=1)

    figure, axis = plt.subplots()
    axis.plot(sizes, train_means, marker="o", label="Training binary F1")
    axis.fill_between(
        sizes,
        train_means - train_stds,
        train_means + train_stds,
        alpha=0.2,
    )
    axis.plot(sizes, validation_means, marker="o", label="Cross-validation binary F1")
    axis.fill_between(
        sizes,
        validation_means - validation_stds,
        validation_means + validation_stds,
        alpha=0.2,
    )
    axis.set(
        title="Synthetic no-show learning curve (training partition only)",
        xlabel="Training examples per CV fold",
        ylabel="Binary F1 (positive class: no_show=1)",
        ylim=(0, 1),
    )
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT_PATH, dpi=150)
    plt.close(figure)

    results = {
        "scope": (
            "Synthetic data only; cross-validation and learning curves use only "
            "the existing training partition. Validation and test partitions "
            "are not used for these diagnostics."
        ),
        "positive_class": "no_show=1",
        "split_sizes": {
            "train": len(train_features),
            "validation": len(holdout_features) // 2,
            "test": len(holdout_features) - len(holdout_features) // 2,
        },
        "cross_validation": {
            "strategy": f"{FOLD_COUNT}-fold StratifiedKFold",
            "random_seed": SEED,
            "metrics_mean_and_sample_std": metrics,
        },
        "learning_curve": {
            "scoring": "binary F1",
            "train_sizes": sizes.tolist(),
            "training_f1_mean": train_means.tolist(),
            "training_f1_std": train_stds.tolist(),
            "cross_validation_f1_mean": validation_means.tolist(),
            "cross_validation_f1_std": validation_stds.tolist(),
            "plot": str(OUTPUT_PATH),
        },
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
