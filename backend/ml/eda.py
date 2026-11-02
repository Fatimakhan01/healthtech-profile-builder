"""Explore the generated synthetic appointment dataset."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


DATA_PATH = Path(__file__).parent / "data" / "synthetic_appointments.csv"
OUTPUT_DIR = Path(__file__).parent / "outputs"


def main() -> None:
    data = pd.read_csv(DATA_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Sample rows:")
    print(data.head())
    print(f"\nDataset dimensions: {data.shape[0]} rows x {data.shape[1]} columns")
    print("\nColumn data types:")
    print(data.dtypes)
    print("\nDescriptive statistics:")
    print(data.describe(include="all").T)

    missing_by_column = data.isna().sum()
    missing_count = int(missing_by_column.sum())
    duplicate_count = int(data.duplicated().sum())
    print("\nMissing values by column:")
    print(missing_by_column)
    print(f"Total missing values: {missing_count}")
    print(f"Duplicate rows: {duplicate_count}")

    target_counts = data["no_show"].value_counts().reindex([0, 1], fill_value=0)
    target_proportions = data["no_show"].value_counts(
        normalize=True
    ).reindex([0, 1], fill_value=0)
    print("\nTarget class counts (0=attended, 1=no-show):")
    print(target_counts)
    print("Target class proportions:")
    print(target_proportions)

    figure, axis = plt.subplots()
    target_counts.plot(kind="bar", ax=axis, color=["steelblue", "darkorange"])
    axis.set(title="Synthetic appointment outcomes", xlabel="no_show", ylabel="Records")
    axis.set_xticklabels(["Attended (0)", "No-show (1)"], rotation=0)
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "target_distribution.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots()
    data["days_ahead"].plot(kind="hist", bins=20, ax=axis, color="slateblue")
    axis.set(
        title="Days between booking and appointment",
        xlabel="Days ahead (0-60)",
        ylabel="Records",
    )
    figure.tight_layout()
    figure.savefig(OUTPUT_DIR / "days_ahead_distribution.png", dpi=150)
    plt.close(figure)

    largest_class_share = float(target_proportions.max())
    print("\nEDA summary:")
    print(
        f"- {len(data)} records; {missing_count} missing values; "
        f"{duplicate_count} duplicate rows."
    )
    print(
        f"- Target counts: attended={target_counts.loc[0]}, "
        f"no-show={target_counts.loc[1]}; largest class is "
        f"{largest_class_share:.1%} of records."
    )
    print(f"- Plots saved under {OUTPUT_DIR}.")
    print(
        "- These are artificial relationships in synthetic data, not evidence "
        "of real-world healthcare validity."
    )


if __name__ == "__main__":
    main()
