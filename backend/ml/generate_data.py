"""Generate a reproducible, entirely synthetic appointment dataset."""

import csv
import math
import random
from pathlib import Path


SEED = 42
RECORD_COUNT = 2_000
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def no_show_probability(
    days_ahead: int,
    previous_no_shows: int,
    sms_reminder: str,
    weekday: str,
) -> float:
    """Return an artificial probability based on the documented toy rule."""
    log_odds = -1.5
    log_odds += 0.035 * days_ahead
    log_odds += 0.65 * previous_no_shows
    log_odds -= 0.55 if sms_reminder == "yes" else 0
    log_odds += 0.15 if weekday in ("Monday", "Saturday") else 0
    return 1 / (1 + math.exp(-log_odds))


def generate_dataset() -> list[dict[str, int | str]]:
    rng = random.Random(SEED)
    records = []

    for _ in range(RECORD_COUNT):
        days_ahead = rng.randint(0, 60)
        previous_no_shows = rng.choices(
            population=range(6),
            weights=(55, 22, 12, 6, 3, 2),
            k=1,
        )[0]
        sms_reminder = rng.choice(("yes", "no"))
        weekday = rng.choice(WEEKDAYS)
        probability = no_show_probability(
            days_ahead,
            previous_no_shows,
            sms_reminder,
            weekday,
        )

        records.append(
            {
                "days_ahead": days_ahead,
                "previous_no_shows": previous_no_shows,
                "sms_reminder": sms_reminder,
                "weekday": weekday,
                "no_show": int(rng.random() < probability),
            }
        )

    return records


def main() -> None:
    output_path = Path(__file__).parent / "data" / "synthetic_appointments.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = generate_dataset()

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    no_show_count = sum(record["no_show"] for record in records)
    attended_count = len(records) - no_show_count
    print(f"Generated {len(records)} synthetic records: {output_path}")
    print(f"Attended (0): {attended_count}; no-show (1): {no_show_count}")
    print("All records are fictional; the generation rule is artificial.")


if __name__ == "__main__":
    main()
