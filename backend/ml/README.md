# Synthetic appointment no-show ML prototype

This is a small educational machine-learning exercise, not a diagnostic,
clinical, or production-ready system. All records are fictional. The feature
relationships and labels are artificial and cannot establish real-world
healthcare validity.

## Data provenance and license

`data/synthetic_appointments.csv` is synthetic and generated locally by
`generate_data.py` from an original, fixed-seed rule. It contains no real
patient data, identifying information, diagnoses, or sensitive attributes.
There is no external dataset source, and no separate dataset license is
currently assigned to the generated CSV. Reuse and redistribution permissions
have not been explicitly granted; no repository license was found that
establishes otherwise. The third-party Python packages have their own
licenses; consult each package's license for use and redistribution terms.

## Dataset schema

The generator creates 2,000 rows. It uses seed `42`; running it again with the
same Python random implementation and seed reproduces the CSV.

| Column | Meaning | Valid range / values |
|---|---|---|
| `days_ahead` | Days between booking and appointment | Integer, 0-60 inclusive |
| `previous_no_shows` | Fictional count of previous missed appointments | Integer, 0-5 inclusive |
| `sms_reminder` | Whether a reminder was sent | `yes` or `no` |
| `weekday` | Appointment weekday | Monday through Sunday |
| `no_show` | Target: whether the fictional appointment was missed | `1` = no-show, `0` = attended |

The target is sampled probabilistically. The generator starts with log-odds
`-1.5`, adds `0.035 * days_ahead`, adds `0.65 * previous_no_shows`, subtracts
`0.55` when an SMS reminder was sent, and adds `0.15` for Monday or Saturday.
It converts these log-odds to a probability with the logistic function and
draws a random binary label. These invented coefficients are only for a
learnable demonstration; they do not represent established effects or
healthcare evidence. Feature distributions and target balance are also
synthetic.

## Requirements and commands

The ML environment and prediction API tests use Python 3.13.17 in
`.venv-integration`; other Python versions have not been verified for this
environment. From the repository root in PowerShell, install the backend and
ML packages:

```powershell
.\.venv-integration\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv-integration\Scripts\python.exe -m pip install -r backend\ml\requirements-ml.txt
```

Run these commands from the repository root in PowerShell:

```powershell
.\.venv-integration\Scripts\python.exe backend\ml\generate_data.py
.\.venv-integration\Scripts\python.exe backend\ml\eda.py
.\.venv-integration\Scripts\python.exe backend\ml\train.py
.\.venv-integration\Scripts\python.exe backend\ml\evaluate.py
.\.venv-integration\Scripts\python.exe backend\ml\diagnostics.py
.\.venv-integration\Scripts\python.exe backend\ml\regularization_experiment.py
```

The EDA script writes `outputs/target_distribution.png` and
`outputs/days_ahead_distribution.png`. The training script writes validation
and test metrics to `outputs/metrics.json` and the complete fitted
preprocessing-plus-classifier pipeline to
`artifacts/no_show_pipeline.joblib`. `evaluate.py` prints its diagnostics
without writing files; `diagnostics.py` writes
`outputs/learning_curve.png`; and `regularization_experiment.py` writes
`outputs/regularization_experiment.json`. `generate_data.py` replaces the CSV
and `train.py` replaces the model and metrics, so omit those commands when
preserving the existing artifacts.

## Modeling and reproducibility

Seed `42` is used for data generation and the stratified train/validation/test
split. The split is 70% training, then the remaining 30% is split evenly into
15% validation and 15% test. The preprocessing pipeline (median imputation and
scaling for numeric features; most-frequent imputation and one-hot encoding
for categorical features) is fitted only on the training data.

The training script compares a most-frequent `DummyClassifier` baseline with
logistic regression on validation F1-score. It selects the higher-F1 pipeline
(ties favor the baseline), evaluates that selected model once on the held-out
test set, and reports accuracy, precision, recall, F1-score, confusion matrix,
and ROC-AUC when both test classes are present. It also reports false-positive
and false-negative counts. Accuracy alone can be misleading if class
frequencies differ: a model can appear accurate by favoring the more common
class while missing many cases in the other class. The training script records
the observed class distributions and model metrics in `outputs/metrics.json`
when run. The generated dataset currently contains 1,024 attended records
(51.2%) and 976 no-show records (48.8%); this count was checked from the
generated CSV and is not a model result. Validation and test metrics are
recorded in `outputs/metrics.json`.

`evaluate.py` reconstructs the same seeded, stratified 70/15/15 split and loads
the saved pipeline without fitting or saving a model. It reports metrics at
fixed classification thresholds on validation data only, then reports ROC-AUC,
Brier scores, and calibration-bin counts on the test data as final evaluation.
The test results must not be used to select a threshold. A lower threshold
typically flags more records, increasing recall while also increasing false
positives; a higher threshold typically reduces flags and false positives but
misses more positive cases. These diagnostics describe only the synthetic
dataset and do not establish real-world validity or proven calibration.

`diagnostics.py` uses a fixed-seed, 5-fold stratified cross-validation and
learning curve on the training partition only. Preprocessing remains inside
each fold's pipeline. It reports mean and standard deviation for the
cross-validation metrics and writes `outputs/learning_curve.png`, a plot of
training and cross-validation binary F1 by training size. A persistent gap or
convergence pattern can help investigate fit, but these diagnostics are
uncertain on this small synthetic dataset and do not establish real-world
performance. Validation and test partitions are not used in these diagnostics.

`regularization_experiment.py` compares `DummyClassifier` and Logistic
Regression with `C` values 0.1, 1.0 (the existing configuration), and 10.0
using identical 5-fold stratified cross-validation on the 70% training
partition only. It selects by mean binary F1 for reporting and writes the
results to `outputs/regularization_experiment.json`; it does not change the
saved model or training metrics. `C` is inverse regularization strength, so
smaller values apply stronger regularization. Cross-validation results are
diagnostic comparisons on synthetic data and do not establish that a small
score difference is a general improvement.

The fitted pipeline artifact is generated by `train.py`; it is not a
hand-authored model and can be recreated by running the documented commands in
the documented compatible environment.

## Prediction API

The versioned Django endpoint is `POST /api/v1/predictions/no-show/`. The
signed-in dashboard calls it through a same-origin Next.js proxy. The
authoritative route mapping, authentication, request/response example, and
error behavior are documented in
[the API and authentication reference](../../docs/api-authentication.md#synthetic-no-show-prediction-api).
The focused API test command is documented in the root README. Predictions
come from synthetic data only and are not real appointment estimates.

## Recorded results

The existing dataset has 2,000 rows: 1,024 attended (51.2%) and 976 no-show
(48.8%). EDA found no missing values and 395 exact duplicate rows; repeated
feature combinations are expected because the generator samples discrete
features with replacement and samples each label probabilistically.

The split is stratified with seed `42`: 1,400 training, 300 validation, and 300
test rows. Preprocessing is contained in the pipeline and fitted on training
data only. F1 below is binary F1 for the positive class `no_show=1`;
confusion-matrix rows are actual labels `[0, 1]` and columns predicted labels
`[0, 1]`.

| Model/split | Accuracy | Precision | Recall | Binary F1 | ROC-AUC | Confusion matrix |
|---|---:|---:|---:|---:|---:|---|
| Dummy baseline, validation | 0.510 | 0.000 | 0.000 | 0.000 | 0.500 | `[[153, 0], [147, 0]]` |
| Logistic Regression, validation | 0.700 | 0.728 | 0.619 | 0.669 | 0.753 | `[[119, 34], [56, 91]]` |
| Selected Logistic Regression, test | 0.680 | 0.705 | 0.589 | 0.642 | 0.756 | `[[118, 36], [60, 86]]` |

Validation F1 selected Logistic Regression over the majority-class baseline;
the test set was used only for the final recorded evaluation. On test data,
ROC-AUC was 0.756, Brier score was 0.201, and test-prevalence constant baseline
Brier score was 0.250. This comparison is a diagnostic on this synthetic split,
not proof of calibration or performance on real data.

`diagnostics.py` uses five-fold stratified cross-validation on the training
partition only (seed `42`), with preprocessing inside each pipeline fold.
`regularization_experiment.py` compares the majority-class baseline and
Logistic Regression with `C` values 0.1, 1.0, and 10.0 on identical folds.
Values below are cross-validation mean ± sample standard deviation; F1 is
binary for `no_show=1`.

| Candidate | Accuracy | Precision | Recall | Binary F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Dummy baseline | 0.512 ± 0.002 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.500 ± 0.000 |
| Logistic Regression, C=0.1 | 0.666 ± 0.029 | 0.669 ± 0.030 | 0.625 ± 0.038 | 0.646 ± 0.032 | 0.738 ± 0.035 |
| Logistic Regression, C=1.0 (current) | 0.672 ± 0.025 | 0.677 ± 0.028 | 0.630 ± 0.033 | 0.652 ± 0.026 | 0.738 ± 0.035 |
| Logistic Regression, C=10.0 | 0.672 ± 0.025 | 0.677 ± 0.028 | 0.628 ± 0.035 | 0.651 ± 0.027 | 0.738 ± 0.035 |

The experiment reports C=1.0 by mean cross-validation binary F1. The small
differences do not establish a general improvement, and no replacement
production model was saved. With scikit-learn 1.5.2 and SciPy 1.18.1, Logistic
Regression may emit an `OptimizeWarning` about an unknown `iprint` solver
option; this originates in the library's `lbfgs` integration and is not
silenced by the scripts.

The learning curve is written to `outputs/learning_curve.png`. Across training
sizes 224, 448, 672, 896, and 1,120, training and cross-validation binary F1
means were approximately 0.662/0.650, 0.663/0.645, 0.662/0.649, 0.666/0.659,
and 0.658/0.652. These five-fold diagnostics are limited by the small
synthetic dataset and do not establish real-world model behavior.

## Limitations

This dataset is synthetic and small, with outcomes created from a simplified
rule. Its distributions, coefficients, and assumed effects may introduce
artificial bias and do not reflect validated clinical or operational
relationships. Performance on these records does not predict performance on
real appointments. No clinical validity, fairness, safety, or deployment
readiness is claimed. Probabilities are not validated risk estimates and must
not be used for clinical or appointment decisions.
