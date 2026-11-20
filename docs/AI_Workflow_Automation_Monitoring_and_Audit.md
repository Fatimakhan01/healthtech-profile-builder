# AI Workflow Automation, Monitoring and Audit

## Architecture

Workflow jobs are persisted in PostgreSQL by the `workflows` Django app. Admins
enqueue one of two fixed job types through a session-authenticated API. A
separate Django management-command worker claims jobs with a database row lock,
so multiple worker processes do not claim the same queued row concurrently.
There is no new task framework or external service.

- `document_indexing` reuses Clinic FAQ's approved-document ingestion and local
  embedding services. The existing per-document transactions, content hashes,
  versions, and unchanged-document handling remain authoritative.
- `batch_prediction` reads only the repository's synthetic appointment CSV and
  calls the existing validated no-show API view logic in-process without HTTP.
  It does not write predictions to that dataset or store individual inputs or
  outputs.
- Job history and monitoring are available to staff administrators through a
  read-only audit API and the admin dashboard.

## Job lifecycle

Jobs move through `queued`, `running`, and either `succeeded` or `failed`.
Execution attempts are bounded to three. A job's timestamps, accumulated
execution duration, sanitized failure code, and safe aggregate result are
stored with the job. A worker interruption can leave a job in `running`; an
operator must confirm the worker is no longer executing before recovery. The
worker has no lease, heartbeat, automatic stale-job reaper, or status-reset API.

The enqueue endpoint requires an `Idempotency-Key` header. The key is hashed
with the requesting administrator's identifier and is never returned. Reusing
the same key and job type returns the original job instead of creating another.
Reusing it for a different type is rejected. Document ingestion, embedding, and
batch inference are themselves safe to repeat: ingestion uses document hashes
and versions, embeddings are updated only for eligible current chunks, and
batch prediction is read-only.

Transient database, timeout, connection, and local embedding-model errors
raised while running a job are retried automatically, up to the configured
attempt limit. Invalid input, unavailable model configuration, and other
permanent processing errors fail without retry. A transient database error
while claiming or finalizing a job is outside that retry handler; it may stop
the worker and leave the row queued or running. Public status and failure codes
do not include exception text, paths, inputs, or credentials.

### Failed or interrupted jobs

- A job retried after a caught transient processing error returns to `queued`.
  Run the one-pass worker again to attempt it; after three attempts it is
  terminal `failed` with `retries_exhausted`.
- A permanent processing error becomes `failed` immediately. Repeating the same
  idempotency key returns that same terminal row; it does not restart the job.
- If a worker is interrupted, its job remains `running`. First verify that no
  worker process is still executing it. Then enqueue the same job type with a
  **new** idempotency key and run the worker again. The same key only returns
  the old running row. Indexing is safe to repeat and batch prediction is
  read-only, but the abandoned audit row remains `running` and continues to
  appear in state counts. Do not edit job rows or mark them failed while a
  worker might still be processing them.
- An operator can inspect recent rows with the admin UI or
  `GET /api/admin/workflows/jobs/`. History is paginated, so use its `page`
  query parameter to find older jobs.

## Monitoring

The audit response reports job counts for every lifecycle state, the terminal
job failure rate (failed jobs divided by succeeded plus failed jobs), and
average/minimum/maximum terminal-job execution latency. Successful
batch-prediction jobs also retain aggregate observed and predicted class counts,
rates, mean no-show probability, model version, and an absolute predicted-vs-
observed rate delta.

The drift indicator is a simple educational threshold comparison
(`absolute_rate_delta > 0.1`), not a statistical drift test or proof of model
quality. It is calculated over the synthetic fixture and must not be interpreted
as a clinical signal. Document indexing results contain aggregate processed,
updated, unchanged, deactivated, and embedded counts only.

## Admin permissions and endpoints

Both endpoints use Django `SessionAuthentication` and `IsAdminUser`; ordinary
standard-user and anonymous sessions are denied.

- `GET /api/admin/workflows/jobs/` — read-only, paginated job history and
  monitoring summary. Page size defaults to 20 and is capped at 50. Responses
  are not cached.
- `POST /api/admin/workflows/enqueue/` — accepts only
  `{"job_type":"document_indexing"}` or
  `{"job_type":"batch_prediction"}` plus an `Idempotency-Key` header. A newly
  created job returns HTTP 202 with `created: true`; an idempotent replay using
  the same key and type returns HTTP 200 with `created: false` and the same job
  ID. Reusing the key for the other job type returns HTTP 409. Invalid keys or
  extra JSON fields return HTTP 400. POST requires the admin session cookie and
  matching `X-CSRFToken` header.
- `python manage.py run_workflow_jobs --once` — process at most one job and
  exit. Without `--once`, the worker polls continuously; run it under an
  existing process supervisor for persistent operation.

The admin page's **Workflow audit** section is read-only and displays statuses,
attempt counts, durations, failure codes, and aggregate monitoring indicators.
It does not show job requesters, dataset rows, prediction inputs, or patient
profiles.

## Manual API and UI verification

From PowerShell, start the backend and frontend using the project's existing
development setup. For example, start Django from `backend` and Next.js from
`frontend` in separate terminals. Sign in at `/admin` using an administrator
account. The page should show the Workflow audit section with an empty state
until jobs have been queued.

The following direct API sequence obtains a CSRF cookie, authenticates an
administrator session, enqueues one synthetic batch, runs it, and reads the
audit record. Use only a local administrator account and run from the
repository root:

```powershell
$base = "http://127.0.0.1:8000/api/admin"
$csrf = Invoke-WebRequest "$base/csrf/" -SessionVariable adminSession
$token = ($csrf.Content | ConvertFrom-Json).csrf_token
$loginBody = @{ email = "admin@example.test"; password = "<local-admin-password>" } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$base/login/" -WebSession $adminSession `
  -Headers @{ "X-CSRFToken" = $token } -ContentType "application/json" -Body $loginBody
$token = $login.csrf_token
$jobBody = @{ job_type = "batch_prediction" } | ConvertTo-Json
$enqueue = Invoke-WebRequest -Method Post -Uri "$base/workflows/enqueue/" -WebSession $adminSession `
  -Headers @{ "X-CSRFToken" = $token; "Idempotency-Key" = "batch-check-2026-11-20" } `
  -ContentType "application/json" -Body $jobBody
$enqueue.StatusCode
$enqueue.Content | ConvertFrom-Json
$duplicate = Invoke-WebRequest -Method Post -Uri "$base/workflows/enqueue/" -WebSession $adminSession `
  -Headers @{ "X-CSRFToken" = $token; "Idempotency-Key" = "batch-check-2026-11-20" } `
  -ContentType "application/json" -Body $jobBody
$duplicate.StatusCode
$duplicate.Content | ConvertFrom-Json
Set-Location backend
$workerPython = "..\.venv-integration\Scripts\python.exe"
& $workerPython manage.py run_workflow_jobs --once
Set-Location ..
$audit = Invoke-RestMethod -Method Get -Uri "$base/workflows/jobs/?page_size=20&page=1" -WebSession $adminSession
$audit.results
$audit.monitoring
```

Expected: the first enqueue returns HTTP 202, `status: queued`, and
`created: true`; the duplicate returns HTTP 200, `created: false`, and the same
job ID. The worker prints the ID, type, final status, attempts, and
`Processed jobs: 1.` The audit GET returns pagination, monitoring metrics, and
the job result. Success results depend on the indexing/prediction data; a
model/configuration problem can yield a sanitized `failed` job. The admin
page's Refresh button shows statuses and aggregate rates. `document_indexing`
can be submitted by changing the body to
`@{ job_type = "document_indexing" } | ConvertTo-Json` and using a distinct
key.

To check standard-user denial, authenticate a standard account through
`/api/auth/csrf/` and `/api/auth/session/login/`, retain its session cookies,
then GET `/api/admin/workflows/jobs/`; expect HTTP 403. A POST without the
admin session or without a matching CSRF token is also rejected.

### Completion criteria

- Both job types can be enqueued by an administrator; duplicate requests with
  the same key do not create extra rows.
- The worker reaches `succeeded` or a sanitized `failed` state, with attempts
  and duration visible in the admin audit.
- Standard/anonymous users cannot read or enqueue; admin POSTs require CSRF.
- Audit pages show aggregate monitoring only, with no row-level prediction or
  patient data.

## Tests and checks

From `backend`:

```powershell
& ..\.venv-integration\Scripts\python.exe manage.py test workflows predictions clinic_faq agent_tools profiles.test_admin_api
& ..\.venv-integration\Scripts\python.exe manage.py check
& ..\.venv-integration\Scripts\python.exe manage.py makemigrations --check --dry-run
```

From `frontend`:

```powershell
npm run lint
npx tsc --noEmit
```

Workflow tests use deterministic fixture CSV data and mocked model inference;
they do not require Ollama or load/download the embedding model.

## Limitations

The worker is an explicit management command, not an always-running service;
deployment must supervise it. Jobs left `running` after abrupt worker termination
require operator review and safe re-enqueue with a new key. The monitoring
summary is operational telemetry, not a clinical metric, and the baseline
comparison is intentionally lightweight. Audit history has no automatic
retention or archival policy yet. The Week 3 model artifact requires a runtime
compatible with its recorded dependency metadata. In this workspace the
`backend/.venv` uses scikit-learn 1.9.1 and cannot load the artifact created with
1.5.2; the existing root `.venv-integration` uses the compatible version and
passes the real-artifact inference test. Run the batch worker under a compatible
environment or the existing prediction API will report the model as unavailable
and the job will exhaust its bounded retries.
