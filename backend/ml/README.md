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

The 2,000 locally generated records contain 976 no-shows (48.8%), so this
dataset is nearly balanced. That prevalence is a property of the generator,
not an estimate of clinic prevalence. Real clinics may have substantially
different no-show rates, and these metrics do not establish how a model would
perform at those rates. The assumed logistic-style relationships among
`days_ahead`, `previous_no_shows`, `sms_reminder`, `weekday`, and the target
are educational assumptions, not findings from real patient data. Results
must not be interpreted as clinical evidence or proof of real-world
predictive performance.

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

Training also writes `artifacts/no_show_pipeline.metadata.json`, recording
the artifact-derived model version, SHA-256, feature order, positive class,
Python version, and ML dependency versions. Django loads the root `.env` with
the existing `python-dotenv` dependency. The prediction API requires
`NO_SHOW_MODEL_SHA256` and `NO_SHOW_MODEL_METADATA_SHA256`; both expected
values are checked before model deserialization.

```powershell
Push-Location backend
..\.venv-integration\Scripts\python.exe manage.py refresh_no_show_hashes
Pop-Location
```

The refresh command must be run deliberately after authorized retraining or
artifact replacement. It calculates hashes from the current files and updates
only these keys in the ignored root `.env`; startup never recalculates or trusts
new hashes automatically. If a replacement leaves the old hashes in place,
prediction loading fails safely until the refresh command is run. For
production, supply expected values through a trusted deployment configuration.
The loader verifies both digests before deserializing the pipeline and rejects
metadata with an incompatible feature schema, Python version, or dependency
versions. Restart Django after updating the artifact or digest configuration
so the in-process model cache is cleared.

### Explainability and error analysis

The read-only `supervised/explainability.py` workflow loads the existing
`artifacts/supervised_pipeline.joblib`; it does not fit, retrain, or replace a
model. It reconstructs the same seeded, stratified 70/15/15 split through
`supervised/train.py`. Permutation importance is computed on validation rows
with F1 scoring because the selected model was chosen by positive-class F1 and
the classes are imbalanced; each original input column is permuted as a unit,
so report names remain interpretable rather than exposing one-hot encoded
columns. Importance is model- and validation-split-specific, not causal.

False-positive and false-negative counts and aggregate feature summaries use
the held-out test partition for descriptive analysis only. The default saved
pipeline predictions are used without changing thresholds or selecting a
model. Reports contain aggregate summaries, not individual records, and are
not used for tuning.

```powershell
.\.venv-integration\Scripts\python.exe backend\ml\supervised\explainability.py
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\supervised\tests -p test_explainability.py
```

The workflow writes only `reports/feature_importance.json` and
`reports/error_analysis.json`.

## Modeling and reproducibility

Seed `42` is used for data generation and the stratified train/validation/test
split. The split is 70% training, then the remaining 30% is split evenly into
15% validation and 15% test. The preprocessing pipeline (median imputation and
scaling for numeric features; most-frequent imputation and one-hot encoding
for categorical features) is fitted only on the training data.

The training script compares a most-frequent `DummyClassifier` baseline with
logistic regression on validation binary F1. The Logistic Regression uses
scikit-learn's default `predict()` decision threshold of 0.5. Model selection
uses validation F1 at that default behavior; training does not tune or select
another threshold. It evaluates the selected model once on the held-out test
set and records accuracy, precision, recall, F1-score, confusion matrix,
ROC-AUC, and aggregate false-positive and false-negative counts in
`outputs/metrics.json`. Accuracy alone can be misleading: a model may favor a
more common class while missing cases in the other class.

`evaluate.py` reconstructs the same seeded, stratified split (1,400 train,
300 validation, 300 test) and loads the saved pipeline without fitting or
saving models or outputs. Its train and validation classification metrics use
the saved model's `predict()` behavior. The fixed-threshold comparison uses
validation probabilities only; it reports thresholds 0.30-0.70 and does not
automatically choose one. Lower thresholds generally flag more records,
increasing recall and false positives; higher thresholds generally reduce
flags and false positives while missing more positive cases. The current
Logistic Regression's default decision threshold remains 0.5.

The test split is reserved for final evaluation. `evaluate.py` reports test
ROC-AUC, Brier score, prevalence-baseline Brier score, calibration-bin counts,
and subgroup error counts using the saved pipeline's existing predictions
(Logistic Regression's default threshold of 0.5). Subgroups are lead-time
bands `0-14`, `15-29`, `30-44`, and `45-60` days, plus `sms_reminder=yes` and
`sms_reminder=no`. Each group reports total records, actual no-shows, predicted
no-shows, false positives, and false negatives. These counts describe the
held-out synthetic test split only; they are not used to select a model or
threshold.

A false positive is an attended synthetic record predicted as a no-show; a
false negative is a synthetic no-show predicted as attended. Both matter:
false alarms can cause unnecessary follow-up, while misses fail to flag
positive examples. The dataset does not measure consequences for actual
patients. Subgroup counts can be small and unstable, so differences are
descriptive only; they do not establish bias, causation, fairness, or
real-world performance. No threshold, model, or clinical decision should be
selected from the test subgroup results.

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
the documented compatible environment. Each training run writes a human-readable
display version to the verified metadata sidecar. A fresh artifact starts at
`No-Show Model v1`; retraining increments the prior metadata version, while a
legacy sidecar without a display version is treated as v1 so its next training
run becomes v2. After training, explicitly refresh the trusted SHA-256 configuration values as
described above; ordinary API requests and application restarts do not
increment the display version.

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

## Week 4 Day 1: supervised learning

Week 4 is an independent educational workflow. It does not replace or retrain
the Week 3 dataset, model, metadata, or prediction API. All Week 4 records are
fictional; no sensitive or identifying patient attributes are generated.

`supervised/generate_dataset.py` creates 2,000 records with NumPy seed `42` at
`data/appointment_attendance.csv`. Re-running it in the documented
environment reproduces the dataset. The synthetic appointment distribution
uses 0-60 days' notice, Poisson prior-appointment counts capped at 15,
Bernoulli prior missed appointments with a 22% per-appointment probability,
68% reminder assignment, sampled weekdays and appointment categories,
weekday daytime hours, gamma-distributed distances capped at 60 km, and
Poisson portal activity. Engagement score is a noisy, clipped, fictional
0-100 quantity related to portal activity and reminders. Outcomes are sampled
from an invented logistic rule using only those booking-time characteristics;
the coefficients are illustrative and are not evidence of real-world
relationships. Prior no-shows are generated as a subset of prior appointments.
Missing values are introduced into eight predictor columns at predefined rates;
the target and prior-appointment counts are complete. No final appointment
outcome or post-appointment information is used as an input. `no_show` is
explicitly excluded from `X`.

| Feature | Type | Intended meaning |
|---|---|---|
| `days_ahead` | Numeric | Generated integer 0-60; days between booking and appointment |
| `previous_appointments` | Numeric | Generated integer count 0-15 |
| `previous_no_shows` | Numeric | Generated integer count from 0 through `previous_appointments` |
| `sms_reminder` | Binary | Generated value 0 or 1; reminder scheduled at booking time |
| `weekday` | Categorical | `Monday`, `Tuesday`, `Wednesday`, `Thursday`, `Friday`, `Saturday`, or `Sunday` |
| `appointment_hour` | Numeric | Generated integer hour 8-18 |
| `distance_km` | Numeric | Generated fictional distance, clipped to 0.2-60.0 km |
| `appointment_type` | Categorical | `routine`, `follow_up`, `consultation`, or `procedure` |
| `portal_activity` | Numeric | Generated nonnegative integer count; no fixed upper cap |
| `engagement_score` | Numeric | Generated fictional score clipped to 0-100 |
| `no_show` | Binary target | `0` attended; `1` did not attend; excluded from model inputs |

These are generator-produced domains, not per-field API validation rules.
Missing predictor values are generated for eight inputs and imputed inside the
training pipeline; previous appointment counts and the target are complete.
`load_features_and_target` checks for the documented columns and binary target
but does not enforce each numeric range. The fitted pipeline's
`OneHotEncoder(handle_unknown="ignore")` tolerates unseen categorical values.
There is no Week 4 prediction endpoint or dedicated request serializer. The
separate Week 3 endpoint accepts only four differently validated fields; see
the [API reference](../../docs/api-authentication.md#synthetic-no-show-prediction-api).

### Training and evaluation

Run the Week 4 workflow from the repository root in PowerShell:

```powershell
.\.venv-integration\Scripts\python.exe backend\ml\supervised\generate_dataset.py
.\.venv-integration\Scripts\python.exe backend\ml\supervised\train.py
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\supervised\tests -p test_supervised.py
.\.venv-integration\Scripts\python.exe backend\manage.py test predictions
```

The split is stratified 70/15/15 with seed `42` (1,400/300/300 rows).
Numeric inputs use median imputation and standard scaling; the binary input
uses most-frequent imputation; categorical inputs use most-frequent imputation
and one-hot encoding with unknown categories ignored. All transformations are
inside each model pipeline and are fitted only on its training fold or the full
training partition. Logistic Regression and Random Forest use class weighting;
the observed 28.6% positive class does not require resampling. Validation F1
selects among the three base classifiers and tuned Random Forest; ties use
training-only CV F1. The test partition is evaluated once after selection.

The observed generated distribution is 1,429 attended (71.45%) and 571
no-shows (28.55%). Split counts are:

| Split | Attended (0) | No-show (1) | Total |
|---|---:|---:|---:|
| Training | 1,000 | 400 | 1,400 |
| Validation | 215 | 85 | 300 |
| Test | 214 | 86 | 300 |

The following are actual validation metrics from the generated Week 4 data;
the JSON results also contain full training metrics, classifier parameters,
and per-split confusion matrices.

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | Average precision |
|---|---:|---:|---:|---:|---:|---:|
| Logistic Regression | 0.643 | 0.413 | 0.612 | 0.493 | 0.667 | 0.507 |
| Random Forest | 0.730 | 0.591 | 0.153 | 0.243 | 0.584 | 0.383 |
| Gradient Boosting | 0.723 | 0.545 | 0.141 | 0.224 | 0.615 | 0.450 |
| Tuned Random Forest | 0.707 | 0.476 | 0.353 | 0.405 | 0.627 | 0.438 |

Five-fold stratified cross-validation runs on training rows only. Base-model
F1 means ± sample standard deviations were 0.489 ± 0.032 for Logistic
Regression, 0.123 ± 0.029 for Random Forest, and 0.276 ± 0.061 for Gradient
Boosting. The Random Forest grid search uses F1 and 8 combinations across
`n_estimators`, `max_depth`, and `min_samples_leaf`; its best parameters were
`max_depth=10`, `min_samples_leaf=3`, and `n_estimators=200`, with mean CV F1
0.408 ± 0.043. Logistic Regression had the highest validation F1 and the
highest base-model CV F1, so it was selected. On the untouched test set its
accuracy was 0.627, precision 0.386, recall 0.512, F1 0.440, ROC-AUC 0.650,
and average precision 0.390; the confusion matrix was
`[[144, 70], [42, 44]]` (rows actual 0/1, columns predicted 0/1). These results
describe only the fictional sampled data and do not establish clinical or
operational validity.

Training writes separate Week 4 outputs to `reports/`:

- `reports/model_comparison.json` — train and validation metrics for every
  candidate, selection evidence, class distributions, and final test metrics.
- `reports/confusion_matrices.json` — candidate train/validation and
  selected-model test confusion matrices.
- `reports/cross_validation.json` — five-fold results for all
  three classifiers.
- `reports/hyperparameter_search.json` — training-only GridSearchCV
  parameters, fold count, and candidate scores.
- `artifacts/supervised_pipeline.joblib` — independently loadable
  preprocessing-plus-model pipeline.
- `artifacts/supervised_pipeline.metadata.json` — feature schema,
  configuration, versions, split information, and artifact/dataset SHA-256.

The supervised `model_version` is generated as
`week4-supervised-<artifact_sha256>` from the SHA-256 digest of the saved
`.joblib` bytes. The sidecar also stores that digest in `artifact_sha256`.
For a read-only consistency check from the repository root in PowerShell:

```powershell
$artifact = "backend\ml\artifacts\supervised_pipeline.joblib"
$metadata = Get-Content "backend\ml\artifacts\supervised_pipeline.metadata.json" -Raw | ConvertFrom-Json
$digest = (Get-FileHash $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
if ($metadata.artifact_sha256 -ne $digest -or $metadata.model_version -ne "week4-supervised-$digest") {
  throw "The Week 4 metadata does not match the saved pipeline."
}
```

This is a metadata/artifact consistency check, not a runtime prediction-endpoint
verification mechanism. Week 4 has no prediction API; the separately
digest-verified Week 3 endpoint is unchanged.

For standalone inference, load the Week 4 pipeline with `joblib.load` and pass
a pandas DataFrame containing the ten documented input columns in any order;
do not include `no_show`. Week 4 does not add a prediction API or alter the
Week 3 API or SHA-256 verification.

### Focused model-improvement experiment

The original dataset, pipeline, metadata, and reports are preserved as the
Week 4 baseline. Run the separate experiment with:

```powershell
.\.venv-integration\Scripts\python.exe backend\ml\supervised\experiment.py
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\supervised\tests -p test_experiment.py
```

It compares an in-training majority-class DummyClassifier and the original
validation results with three Logistic Regression class-weight settings
(unweighted, moderate positive-class weight, and balanced). Each new Logistic
Regression setting is evaluated at threshold 0.5 and at the threshold selected
by maximizing F1 on five-fold out-of-fold predictions from the training split
only. Candidate selection uses validation F1. The test partition is not used
for fitting, threshold selection, comparison, or reporting. The already
completed eight-combination Random Forest search is reused as evidence; this
experiment does not repeat it.

The new report is written only to
`reports/model_improvement_experiments.json`; it contains validation metrics
and confusion matrices, threshold provenance, and the selected candidate.
It does not replace the original report, test metrics, saved pipeline, or
metadata.

### Week 4 Day 2: unsupervised engagement clustering

The independent `clustering/` workflow creates a new 1,200-row fictional
engagement dataset with five input features: previous appointment and
no-show counts, portal activity, engagement score, and reminder indicator.
Its generator uses a fixed NumPy seed and includes missing observations.
Synthetic feature relationships are generated from a mixture of distributions
solely to make a clustering exercise; latent generator groups are not saved.
The dataset has no `no_show` target, and the loader rejects extra columns to
prevent accidental target inclusion.

From the repository root in PowerShell, generate the dataset, run clustering,
and execute its focused tests:

```powershell
.\.venv-integration\Scripts\python.exe backend\ml\clustering\generate_dataset.py
.\.venv-integration\Scripts\python.exe backend\ml\clustering\cluster.py
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\clustering\tests
```

Median imputation and standard scaling are part of the clustering pipelines.
K-Means evaluates k=2 through 8 with seed 42 and 20 initializations, reporting
inertia (elbow evidence) and silhouette; the descriptive solution uses the
tested k with the highest silhouette. This is a heuristic, not evidence that
the selected number of segments is objectively correct. DBSCAN uses Euclidean
distance in the same standardized five-feature space with `eps=1.15` and
`min_samples=10`. Its silhouette is left null when invalid and otherwise
excludes noise points. PCA produces two coordinates from the standardized
five-feature space for visualization only; it does not replace the clustering
space.

The single output `clustering/reports/clustering_results.json` contains the
feature schema, algorithm parameters, random seed, K-Means inertia and
silhouette values, DBSCAN cluster/noise counts and valid silhouette status,
neutral aggregate feature summaries, and per-row PCA coordinates with both
sets of cluster labels for visualization. Cluster identifiers are arbitrary;
summaries do not assign diagnoses, risk categories, or clinical meaning.
These synthetic distributions, internal metrics, and resulting segments are
not clinically validated and should not be used for operational decisions.

### HealthProfile Intelligence dashboard

The authenticated dashboard is available to standard users from the signed-in
profile screen. Its five sections map to existing report/API functionality:

- **Overview** summarizes report-backed model and dataset information.
- **Predictive Analytics** compares Logistic Regression, Random Forest, and
  Gradient Boosting validation metrics and confusion matrices.
- **Engagement Segmentation** presents K-Means/DBSCAN summaries and PCA
  coordinates from the clustering report. PCA is visualization-only.
- **Clinic Assistant** submits general questions to the existing authenticated
  FAQ endpoint and displays its answer, abstention status, and policy citations.
- **Model Governance** presents model metadata, validation metrics, synthetic
  data notices, and limitations.

The same-origin browser route `GET /api/ml-dashboard/` proxies to
`GET /api/v1/ml-dashboard/`. It returns `model_comparison.json`,
`supervised_pipeline.metadata.json`, and `clustering_results.json`; it does not
retrain models or calculate metrics. The feature-importance and error-analysis
reports are produced separately by `supervised/explainability.py` and are not
included in this dashboard response. Accordingly, the dashboard does not show
their values; its Predictive Analytics section identifies this as unavailable.
See the [API/authentication reference](../../docs/api-authentication.md) for
route, response, and authorization details, and the
[Week 4 submission checklist](../../docs/week4-submission.md) for manual
verification and evidence guidance.

Run the relevant checks from the repository root in PowerShell:

```powershell
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\supervised\tests
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\clustering\tests
Push-Location backend
..\.venv-integration\Scripts\python.exe manage.py test clinic_faq
..\.venv-integration\Scripts\python.exe manage.py check
Pop-Location
Push-Location frontend
npm run lint
npx tsc --noEmit
npm run build
Pop-Location
```

The evaluation report records outcomes for both FAQ configurations and should
be reviewed before submission; the lexical checks are not a substitute for
human assessment. Do not present synthetic model results or FAQ responses as
clinical evidence or real clinic policy.
