# Week 4 submission checklist

This page records submission evidence and known gaps; it does not replace the
methodology and run instructions in the [ML README](../backend/ml/README.md),
[Clinic FAQ README](../backend/clinic_faq/README.md), or
[API reference](./api-authentication.md).

## Evidence locations

No Week 4 screenshots or Loom recording were found in the repository during
this audit. When captured, place screenshots in `docs/screenshots/week4/` and
link them from this section. Suggested filenames:

- `01-overview.png` — HealthProfile Intelligence overview.
- `02-predictive-analytics.png` — validation metrics and confusion matrices.
- `03-engagement-segmentation.png` — K-Means and DBSCAN summaries and PCA view.
- `04-clinic-assistant.png` — a general policy answer and its citations.
- `05-model-governance.png` — model version, synthetic-data notice, and limits.

The repository does contain PNG plots under `backend/ml/outputs/` for the
separate original ML analysis; those are not Week 4 dashboard screenshots.

Only add screenshots after a real manual run. Use fictional/demo accounts and
synthetic content; redact email addresses, tokens, environment settings, and
other private information. Reference captured files here with relative links,
for example `[Overview](./screenshots/week4/01-overview.png)`.

## Loom demonstration outline

A concise 3–5 minute recording can:

1. Introduce HealthProfile Intelligence and state that model data and policy
   documents are synthetic examples.
2. Show Overview, then Predictive Analytics and the validation metrics and
   confusion matrices.
3. Switch between K-Means and DBSCAN; explain that PCA is a visualization and
   the segments are descriptive, not clinical categories.
4. Ask a general question answered by an approved policy, point out its
   citation, then ask an unsupported question and show the abstention.
5. Show Model Governance, model version, data limitations, and the synthetic-
   data notice.

Do not show `.env`, API tokens, real profile information, or patient data.
Record only after manually confirming the local backend, frontend, PostgreSQL,
policy ingestion/embeddings, and Ollama are working.

## Readiness findings

- The reports, model metadata, FAQ evaluation, and five dashboard sections are
  documented in their linked source references.
- The saved FAQ evaluation report records 0/12 checks passed for configuration
  A and 4/12 for configuration B. These checks are partly lexical heuristics;
  inspect failed cases and do not present this as a successful quality
  validation.
- `feature_importance.json` and `error_analysis.json` exist as supervised
  reports, but the authenticated dashboard API does not return them and the
  dashboard does not display their values. If the submission rubric requires
  these within the dashboard, this remains an implementation gap; this
  documentation-only audit did not change application code.
- The repository does not yet contain the screenshot files or a recorded Loom
  link. Capture and add them only after the manual checks below.
- Verify the formal assignment rubric independently; the project README notes
  that the original brief was not located in the repository.

## Manual testing checklist

Run the automated checks from the repository root in PowerShell:

```powershell
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\supervised\tests
.\.venv-integration\Scripts\python.exe -m unittest discover -s backend\ml\clustering\tests
Push-Location backend
..\.venv-integration\Scripts\python.exe manage.py test clinic_faq
..\.venv-integration\Scripts\python.exe manage.py check
..\.venv-integration\Scripts\python.exe manage.py makemigrations --check --dry-run
Pop-Location
Push-Location frontend
npm run lint
npx tsc --noEmit
npm run build
Pop-Location
```

For manual verification, start the configured Django/PostgreSQL backend and
Next.js frontend as described in the root README, then:

- Sign in as a standard user and visit Overview, Predictive Analytics,
  Engagement Segmentation, Clinic Assistant, and Model Governance.
- Confirm metric values come from the displayed report data, the confusion
  matrices identify actual/predicted classes, and PCA can be viewed with both
  clustering methods.
- Submit a general policy question and check for policy citations. Ask about a
  detail absent from the approved examples and confirm the assistant reports
  insufficient information.
- Confirm a request without authentication is denied. The documented Django
  endpoints are `GET /api/v1/ml-dashboard/` and
  `POST /api/v1/clinic-faq/ask/`; their same-origin browser proxies and error
  statuses are in the [API reference](./api-authentication.md).
- Capture the five screenshots above only after these checks; use only
  fictional data and do not capture credentials or private profile content.
