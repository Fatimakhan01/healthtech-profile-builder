# AI-assisted development workflow

## Scope and evidence

This note records AI-assisted work that is supported by the repository and retained session context. It is a summary, not a reconstruction of exact chat history. The complete verbatim prompts from earlier project phases were not retained in the available context and are not quoted here.

## Substantiated work

The retained project history records AI assistance across the following implementation areas:

- Project planning and separation of the Next.js frontend and Django REST Framework backend.
- PostgreSQL-backed user/profile schema, migrations, and model tests.
- Standard-user signup, JWT access, server-managed session restoration, profile endpoints, and the profile form.
- Separate Django admin session and CSRF flow, admin profile listing, and the frontend admin experience.
- Targeted investigations of admin proxy/login and logout failures, including CSRF token rotation.
- Profile status management with staff-only authorization, CSRF enforcement, and tests verifying that status changes retain both account and profile data.
- Frontend visual refinement while preserving the existing routes, state transitions, and request behavior.

These are summaries of recorded project work, not verbatim historical prompts or a claim that AI independently verified every implementation decision.

## Recent task evidence

The two entries below summarize task objectives from the retained conversation; neither is a verbatim prompt. The verification results are reported from their implementation turns and were not rerun specifically to prepare this evidence.

### Member profile timestamps

- **Task summary:** expose existing `created_at` and `updated_at` values as read-only fields in the member profile API, and test GET/PATCH responses plus rejection of client-supplied timestamps.
- **Files changed:** `backend/profiles/serializers.py`, `backend/profiles/test_api.py`.
- **Reported verification:** `manage.py test profiles.test_api` — 8 tests passed; documentation link check found all local links; `git diff --check` passed.
- **Human review:** inspect serializer field/read-only configuration and confirm PATCH still rejects timestamp values; review the GET/PATCH assertions and ensure no model or migration changed.

### Rerunnable fictional demo profiles

- **Task summary:** add a repeatable Django management command for a small set of fictional standard users and profiles, skipping existing identities without overwriting data and keeping it outside migrations/test setup.
- **Files changed:** `backend/profiles/management/__init__.py`, `backend/profiles/management/commands/__init__.py`, `backend/profiles/management/commands/create_demo_profiles.py`, `backend/profiles/test_demo_command.py`, and `README.md`.
- **Reported verification:** `manage.py test profiles.test_demo_command profiles.test_api` — 10 tests passed; `manage.py check` passed; `manage.py makemigrations --check --dry-run` reported no changes; `git diff --check` passed. The command was not run against the configured project database.
- **Human review:** inspect the fixed `.example.test` identities, unusable passwords, duplicate-skip behavior, preservation test, and README instructions. Confirm the command does not grant staff privileges, update/delete existing rows, or run automatically.

No specific manual code correction by a human after AI generation is evidenced for these two tasks in the retained records. A reviewer should independently inspect the source diff and tests above rather than treating the reported command output as a substitute for review.

## Human review and security boundaries

The project requirements and follow-up decisions were supplied by the developer. The retained instructions repeatedly required human approval before broad setup changes, no guessed database credentials, PostgreSQL-only configuration, no real secrets in source control, separate standard-user JWT and administrator session authentication, CSRF protection, staff-only admin endpoints, and preservation of profile ownership boundaries.

The human-facing task records required review of generated migration plans and prohibited resets, automatic commits, credential exposure, and unrelated changes. This document does not assert that a formal security audit or penetration test was performed.

## Verification evidence

### Automated checks run during this documentation audit

On 2026-10-19:

- `backend\.venv\Scripts\python.exe manage.py test` — 55 tests passed; Django created and destroyed its separate test database.
- `backend\.venv\Scripts\python.exe manage.py check` — no issues identified.
- `backend\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` — no model changes detected.
- `backend\.venv\Scripts\python.exe -m pip check` — no broken requirements.
- `frontend` `npm run lint` — passed.
- `frontend` `npm run build` — passed, including TypeScript and static generation.
- Read-only PostgreSQL inspection confirmed PostgreSQL 18.4, the configured target connection, the expected user/profile tables, migration application, and documented uniqueness/index objects.

These results are command output from this audit. They do not substitute for manual interaction testing in a browser.

### Final integration verification — 2026-10-22

The following are the results reported by the final integration run on 2026-10-22. They are retained verification evidence and were **not rerun during this documentation-only update**:

- Full Django test suite — 70 tests passed.
- Django `manage.py check` — passed with no issues.
- Django `manage.py makemigrations --check --dry-run` and `manage.py migrate --check` — passed.
- Frontend `npm run lint` — passed.
- Frontend `npm run build` — passed, including TypeScript checking and production build.
- `git diff --check` — passed.

### Developer-reported manual checks

The project task history reports that standard-user and admin workflows were manually tested. The exact browser steps, environment, and screenshots for those tests were not retained, so this report does not treat them as independently reproduced during the documentation audit.

## Lessons and limitations

- Trace each frontend request through its same-origin Next.js route, proxy mapping, and Django URL configuration; similarly named frontend and backend routes can have different behavior.
- Django login can rotate the CSRF secret. The client must use the fresh token returned by login for subsequent session-authenticated mutations.
- Keep database identity verification separate from migration execution, and never infer project credentials from placeholders.
- Use synthetic accounts and fictional profile details for demonstrations. Do not put real health data, tokens, or credentials in screenshots or recordings.
- The original formal assignment file and complete historical prompt transcript were not found in the repository/available retained context. Confirm final rubric-specific requirements with the original assignment source.
