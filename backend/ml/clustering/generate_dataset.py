"""Generate a reproducible, fictional engagement dataset for clustering."""

from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42
ROW_COUNT = 1_200
ML_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ML_DIR / "clustering" / "data" / "engagement_clustering.csv"

FEATURE_SCHEMA = {
    "previous_appointments": {
        "type": "numeric",
        "meaning": "Synthetic count of prior appointments; capped at 15.",
    },
    "previous_no_shows": {
        "type": "numeric",
        "meaning": "Synthetic prior missed-appointment count, bounded by prior appointments.",
    },
    "portal_activity": {
        "type": "numeric",
        "meaning": "Synthetic count of portal actions before a hypothetical appointment.",
    },
    "engagement_score": {
        "type": "numeric",
        "meaning": "Synthetic engagement value from 0 to 100.",
    },
    "sms_reminder": {
        "type": "binary",
        "meaning": "Whether a reminder is scheduled (1=yes, 0=no).",
    },
}


def generate_dataset(row_count: int = ROW_COUNT, seed: int = SEED) -> pd.DataFrame:
    """Create engagement features only; no outcome or latent group is exported."""
    if row_count < 1:
        raise ValueError("row_count must be positive.")

    rng = np.random.default_rng(seed)
    latent_group = rng.choice(3, size=row_count, p=[0.34, 0.36, 0.30])
    appointment_means = np.array([2.0, 7.0, 12.0])
    no_show_rates = np.array([0.06, 0.12, 0.20])
    portal_means = np.array([1.5, 4.0, 8.0])
    score_means = np.array([35.0, 62.0, 82.0])
    score_std = np.array([12.0, 14.0, 10.0])
    reminder_rates = np.array([0.35, 0.62, 0.85])

    previous_appointments = np.minimum(
        rng.poisson(appointment_means[latent_group]), 15
    )
    previous_no_shows = rng.binomial(
        previous_appointments, no_show_rates[latent_group]
    )
    portal_activity = np.minimum(rng.poisson(portal_means[latent_group]), 15)
    engagement_score = np.clip(
        rng.normal(score_means[latent_group], score_std[latent_group]), 0, 100
    )
    sms_reminder = rng.binomial(1, reminder_rates[latent_group])

    data = pd.DataFrame(
        {
            "previous_appointments": previous_appointments,
            "previous_no_shows": previous_no_shows,
            "portal_activity": portal_activity,
            "engagement_score": np.round(engagement_score, 2),
            "sms_reminder": sms_reminder,
        }
    )

    missing_rates = {
        "previous_appointments": 0.04,
        "previous_no_shows": 0.04,
        "portal_activity": 0.05,
        "engagement_score": 0.05,
        "sms_reminder": 0.03,
    }
    for column, rate in missing_rates.items():
        missing_mask = rng.random(row_count) < rate
        data.loc[missing_mask, column] = np.nan

    return data


def main() -> None:
    data = generate_dataset()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(DATA_PATH, index=False)
    print(f"Saved {len(data)} synthetic engagement records to {DATA_PATH}")
    print(f"Feature columns: {', '.join(data.columns)}")
    print(f"Missing values: {int(data.isna().sum().sum())}")


if __name__ == "__main__":
    main()
