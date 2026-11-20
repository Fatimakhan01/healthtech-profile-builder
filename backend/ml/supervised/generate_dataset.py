"""Generate the reproducible, fictional Week 4 appointment dataset."""

from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42
RECORD_COUNT = 2_000
ML_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = ML_DIR / "data" / "appointment_attendance.csv"
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
APPOINTMENT_TYPES = ("routine", "follow_up", "consultation", "procedure")


def generate_dataset(
    seed: int = SEED,
    record_count: int = RECORD_COUNT,
) -> pd.DataFrame:
    """Create fictional booking-time features and an artificial outcome."""
    if record_count < 1:
        raise ValueError("record_count must be positive.")

    rng = np.random.default_rng(seed)
    days_ahead = rng.integers(0, 61, size=record_count)
    previous_appointments = np.minimum(rng.poisson(3.0, record_count), 15)
    previous_no_shows = rng.binomial(previous_appointments, 0.22)
    sms_reminder = rng.binomial(1, 0.68, record_count)
    weekday = rng.choice(WEEKDAYS, size=record_count)
    appointment_hour = np.clip(
        np.rint(rng.normal(13.0, 2.7, record_count)), 8, 18
    ).astype(int)
    distance_km = np.clip(rng.gamma(2.0, 6.0, record_count), 0.2, 60.0)
    appointment_type = rng.choice(
        APPOINTMENT_TYPES,
        size=record_count,
        p=(0.45, 0.25, 0.20, 0.10),
    )
    portal_activity = rng.poisson(2.0, record_count)
    engagement_score = np.clip(
        rng.normal(50 + 7 * portal_activity + 8 * sms_reminder, 18, record_count),
        0,
        100,
    )

    log_odds = (
        -1.05
        + 0.027 * days_ahead
        + 0.34 * previous_no_shows
        - 0.48 * sms_reminder
        + 0.018 * distance_km
        - 0.055 * portal_activity
        - 0.012 * engagement_score
        + np.isin(weekday, ("Monday", "Saturday")) * 0.12
        + np.isin(appointment_type, ("routine", "procedure")) * 0.12
    )
    probabilities = 1 / (1 + np.exp(-log_odds))

    data = pd.DataFrame(
        {
            "days_ahead": days_ahead,
            "previous_appointments": previous_appointments,
            "previous_no_shows": previous_no_shows,
            "sms_reminder": sms_reminder,
            "weekday": weekday,
            "appointment_hour": appointment_hour,
            "distance_km": np.round(distance_km, 2),
            "appointment_type": appointment_type,
            "portal_activity": portal_activity,
            "engagement_score": np.round(engagement_score, 2),
            "no_show": rng.binomial(1, probabilities),
        }
    )

    # Missingness is introduced only into predictor fields, never the label.
    for column, rate in (
        ("days_ahead", 0.03),
        ("sms_reminder", 0.02),
        ("weekday", 0.02),
        ("appointment_hour", 0.03),
        ("distance_km", 0.04),
        ("appointment_type", 0.02),
        ("portal_activity", 0.06),
        ("engagement_score", 0.05),
    ):
        missing = rng.random(record_count) < rate
        data.loc[missing, column] = np.nan

    return data[
        [
            "days_ahead",
            "previous_appointments",
            "previous_no_shows",
            "appointment_hour",
            "distance_km",
            "portal_activity",
            "engagement_score",
            "sms_reminder",
            "weekday",
            "appointment_type",
            "no_show",
        ]
    ]


def main() -> None:
    data = generate_dataset()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(DATA_PATH, index=False)
    counts = data["no_show"].value_counts().reindex([0, 1], fill_value=0)
    print(f"Generated {len(data)} fictional records: {DATA_PATH}")
    print(
        f"Attended (0): {counts.loc[0]} ({counts.loc[0] / len(data):.1%}); "
        f"no-show (1): {counts.loc[1]} ({counts.loc[1] / len(data):.1%})"
    )
    print(f"Missing predictor cells: {int(data.isna().sum().sum())}")


if __name__ == "__main__":
    main()
