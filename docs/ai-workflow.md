# AI-assisted development workflow

**Project:** HealthProfile
**Evidence focus:** Week 2 mentor-review follow-up fixes (Issues 1, 2 and 3), plus the retained earlier project history
**Last updated:** 2026-10-27

## 1. Scope and evidence

This note records AI-assisted work on the HealthProfile project that is supported by the repository and retained session context. It is a summary, not a reconstruction of exact chat history.

- The complete verbatim prompts from earlier project phases were not retained in the available context and are not quoted here.
- The two Week 2 coding prompts (Issue 1 and Issue 2) are recorded in full in Section 3.
- The original formal assignment file and any rubric were not found in the repository or retained context. Rubric-specific requirements must be confirmed against the original assignment source.
- Test results are reported from the implementation turns that produced them. The documentation author did **not** run any tests or checks while preparing this documentation. Historical results are not presented as rerun, with one exception: on 2026-10-27 the developer ran the focused admin API tests, the full backend suite, and the Django system check (Section 5.3). Frontend lint/build and `git diff --check` results have not been rerun.
- Automated checks, manual verification, and pending work are kept distinct throughout. Nothing pending is marked complete.
- The developer reported manual checks of the Week 2 fixes on 2026-10-27 (Sections 3.1, 3.2 and 3.4): the Issue 1 `is_active` database transitions and the Issue 2 pagination scenario. The developer has not separately confirmed a manual check that repeated-status requests create no extra audit event; that behavior is covered only by the automated tests. Exact steps, environment, and screenshots were not retained. Manual checks are separate from the automated test results (Section 5.3 for the 2026-10-27 backend run).
- The developer personally reviewed the source-code changes for Issues 1, 2 and 3 and confirmed on 2026-10-27 that they look correct. This is a developer-reported manual review; no findings or review notes were retained, and the documentation author did not access the repository.
- Issue 3 (Section 3.3) is documented from the developer's report of the implementation, the lint/build/`git diff --check` results, and the manual browser test. The documentation author did not have the repository available and did not inspect the Issue 3 source diff, so the implementation description is developer-reported; the developer's own source review is recorded in Section 3.3.

## 2. Substantiated work (earlier project history)

The retained project history records AI assistance across the following implementation areas:

- Project planning and separation of the Next.js frontend and Django REST Framework backend.
- PostgreSQL-backed user/profile schema, migrations, and model tests.
- Standard-user signup, JWT access, server-managed session restoration, profile endpoints, and the profile form.
- Separate Django admin session and CSRF flow, admin profile listing, and the frontend admin experience.
- Targeted investigations of admin proxy/login and logout failures, including CSRF token rotation.
- Profile status management with staff-only authorization, CSRF enforcement, and tests verifying that status changes retain both account and profile data.
- Frontend visual refinement while preserving the existing routes, state transitions, and request behavior.

These are summaries of recorded project work, not verbatim historical prompts or a claim that AI independently verified every implementation decision.

### 2.1 Member profile timestamps

- **Task summary:** expose existing `created_at` and `updated_at` values as read-only fields in the member profile API, and test GET/PATCH responses plus rejection of client-supplied timestamps.
- **Files changed:** `backend/profiles/serializers.py`, `backend/profiles/test_api.py`.
- **Reported verification:** `manage.py test profiles.test_api` — 8 tests passed; documentation link check found all local links; `git diff --check` passed.
- **Human review:** inspect serializer field/read-only configuration and confirm PATCH still rejects timestamp values; review the GET/PATCH assertions and ensure no model or migration changed.

### 2.2 Rerunnable fictional demo profiles

- **Task summary:** add a repeatable Django management command for a small set of fictional standard users and profiles, skipping existing identities without overwriting data and keeping it outside migrations/test setup.
- **Files changed:** `backend/profiles/management/__init__.py`, `backend/profiles/management/commands/__init__.py`, `backend/profiles/management/commands/create_demo_profiles.py`, `backend/profiles/test_demo_command.py`, and `README.md`.
- **Reported verification:** `manage.py test profiles.test_demo_command profiles.test_api` — 10 tests passed; `manage.py check` passed; `manage.py makemigrations --check --dry-run` reported no changes; `git diff --check` passed. The command was not run against the configured project database.
- **Human review:** inspect the fixed `.example.test` identities, unusable passwords, duplicate-skip behavior, preservation test, and README instructions. Confirm the command does not grant staff privileges, update/delete existing rows, or run automatically.

For these two earlier tasks, no specific manual code correction by a human after AI generation is evidenced in the retained records. A reviewer should independently inspect the source diff and tests rather than treating the reported command output as a substitute for review.

## 3. Week 2 mentor-review fixes — 2026-10-27

The mentor's Week 2 review raised three issues. Issues 1 and 2 were addressed first. Issue 3 is separate from Issue 2 and was addressed afterwards in `frontend/src/app/admin/page.tsx` (see 3.3). Issue 3 is documented with a shorter structure than Issues 1 and 2 because its original coding prompt was not retained.

Each issue below is organized in the same eight parts: (1) mentor-reported problem, (2) original coding prompt, (3) requirements and acceptance criteria, (4) files allowed to change, (5) implementation and refinement, (6) automated verification, (7) manual verification status, (8) human-review checklist and remaining work.

### 3.1 Issue 1 — Admin status validation and audit events

#### 1. Mentor-reported problem

The admin status endpoint accepted an empty PATCH, or a repeated status such as `is_active=true` for an already-active profile, returned HTTP 200, and created an incorrect `profile_reactivated` audit event.

#### 2. Original coding prompt

The following is the full coding prompt supplied to the agent:

> We need to fix Issue 1 from my Week 2 mentor review in the existing HealthProfile project.
>
> **Problem:** The admin status endpoint currently allows an empty PATCH or a repeated status such as `is_active=true` for a profile that is already active to return 200 and create an incorrect `profile_reactivated` audit event.
>
> **Scope — inspect and modify only these files unless another file is genuinely necessary:**
>
> - `backend/profiles/admin_views.py`
> - `backend/profiles/test_admin_api.py`
>
> **Requirements:**
>
> 1. Require `is_active` to be explicitly present in the request body.
> 2. Accept only a real JSON boolean (`true` or `false`). Reject strings such as `"true"`, `"false"`, `"yes"`, numbers, null, and other invalid values.
> 3. Reject an empty payload, a missing `is_active` field, and unexpected fields with HTTP 400. Do not silently ignore unexpected fields.
> 4. Create `profile_deactivated` only when the profile actually changes from active to inactive.
> 5. Create `profile_reactivated` only when the profile actually changes from inactive to active.
> 6. If the requested status is already the current status, handle it as a successful no-op if compatible with the existing API, but do not create an audit event.
> 7. Keep the status update and corresponding audit event atomic in a database transaction. If the operation fails, do not leave an audit event without its successful status change.
> 8. Preserve existing admin authentication, permission checks, CSRF protection, response conventions where possible, and existing functionality.
> 9. Add or update focused tests in `backend/profiles/test_admin_api.py` for:
>    - Empty payload.
>    - Missing `is_active`.
>    - Invalid non-boolean values.
>    - Unexpected fields.
>    - Repeating `is_active=true` when already active.
>    - Repeating `is_active=false` when already inactive.
>    - Active → inactive transition.
>    - Inactive → active transition.
>    - Correct audit action and event count for each case.
>    - Rejected requests do not change the status or create audit events.
>
> **Implementation instructions:**
>
> - Inspect the existing endpoint, audit model, and test conventions before changing code.
> - Use strict boolean validation; do not use Python truthiness because `"false"` is truthy.
> - Keep changes minimal and consistent with the existing codebase.
> - Do not modify unrelated files, rewrite history, or create a migration unless genuinely required.
> - Do not claim tests passed unless you actually run them.
>
> **Verification:** Run the focused admin API tests first. If they pass, run the full backend test suite and `git diff --check` if the environment permits. Report:
>
> 1. Files changed.
> 2. The behavior before and after the fix.
> 3. Tests added and their actual results.
> 4. Any checks that could not be run.
>
> Do not commit or push.

#### 3. Requirements and acceptance criteria

- `is_active` must be present and must be a real JSON boolean (no Python truthiness; `"false"` is truthy).
- Empty payloads, missing `is_active`, and unexpected fields are rejected with HTTP 400. Non-boolean values (strings, numbers, null) are rejected.
- Validation errors identify `is_active` where the tests require it (empty payload and missing field).
- Audit events are created only for actual status transitions: `profile_deactivated` for active → inactive, `profile_reactivated` for inactive → active.
- A repeated status request is a successful no-op and creates no audit event.
- The status update and its audit event are atomic.
- Existing authentication, permission checks, CSRF protection, and response conventions remain intact.
- Rejected requests leave the persisted status unchanged and create no audit event.

#### 4. Files allowed to change

- `backend/profiles/admin_views.py`
- `backend/profiles/test_admin_api.py`

The task limited changes to these files unless another file was genuinely necessary. No migration, commit, or push was part of the task.

#### 5. Implementation and refinement

- The first focused implementation validated the request and made status changes and audit events conditional on a real transition, with the update and event performed together in a transaction.
- **Refinement:** the tests were then strengthened so that the empty-payload and missing-`is_active` cases assert that the error identifies `is_active`, in addition to asserting unchanged database status and no audit event for rejected requests.

#### 6. Automated verification (as reported)

| Run | Result |
| --- | --- |
| Focused admin API tests | **16 passed** |
| Full backend suite, before the final test-only assertion change | **75 passed** |
| Focused admin API tests, rerun after the final test-only assertion change | **16 passed** |
| Focused admin API tests (`python manage.py test profiles.test_admin_api`), run by the developer on 2026-10-27 | **16 passed** |
| Full backend suite (`python manage.py test`), run by the developer on 2026-10-27 | **75 passed** |

- After the final assertion-only change, the earlier implementation run reran only the focused tests. The full suite was later run by the developer on 2026-10-27 (75 passed), which closes that gap for the code as it stood on that date (details in Section 5.3).
- The first three rows come from the implementation runs. The two 2026-10-27 rows are developer-run results; the documentation author did not run them.
- These backend tests verify Issue 1 behaviour only. They do not verify Issue 2 or Issue 3 frontend behaviour.
- The automated tests verified database status and audit-event behavior for endpoint transitions and no-ops.

#### 7. Manual verification status

**Partly completed (developer-reported, 2026-10-27).**

- **Manually verified by the developer:** in the `profiles_healthprofile` table, `is_active` becomes `false` when a profile is deactivated and `true` when it is reactivated.
- **Not manually verified (not confirmed):** that repeating the same status request creates no extra audit event. This behavior is covered by the automated tests reported above, but the developer has not separately confirmed it by a manual check. It must not be recorded as manually verified unless that check is performed and confirmed.

Limitations of this record: the exact steps, environment, and screenshots of the manual test were not retained, and no other manual checks (for example of non-boolean values or unexpected fields) were reported. Those cases are covered by the automated tests only.

#### 8. Human-review checklist and remaining work

- [x] The endpoint validates the submitted object and requires `is_active` to be an actual boolean, not a truthy string or number.
- [x] Empty, missing-field, and unexpected-field requests return 400, and errors identify `is_active` where required.
- [x] The requested state is compared with the existing state before any write.
- [x] Audit events are written only for genuine transitions, with the correct action.
- [x] The status update and matching audit event occur inside the same transaction.
- [x] Tests assert response status, persisted status, audit action, and event count.
- [x] Admin authentication, staff-only permission, and CSRF protection are unchanged.
- [x] No model, migration, or unrelated file changed.
- [x] Manual check that `is_active` becomes false when deactivated and true when reactivated in `profiles_healthprofile` (developer-reported, 2026-10-27).
- [ ] Manual check that repeated-status requests create no extra audit event (not confirmed; covered by automated tests only).
- [x] Source diff reviewed against this checklist (developer's manual source review, confirmed correct, 2026-10-27; the code-review items above are checked on that basis).

**Remaining work for Issue 1:** optionally confirm the repeated-status audit-event behavior manually. The human source diff review was completed by the developer on 2026-10-27.

### 3.2 Issue 2 — Admin directory pagination

#### 1. Mentor-reported problem

With 11 filtered active profiles and 10 items per page, page 2 contains exactly one profile. If the admin deactivates that profile, only 10 active profiles remain and page 2 no longer exists. The frontend could reload the now-invalid page 2 and show stale rows or incorrect pagination/counts.

#### 2. Original coding prompt

The following is the full coding prompt supplied to the agent:

> Fix Issue 2 from my HealthProfile Week 2 mentor review. Keep this task narrowly scoped to the admin directory pagination bug.
>
> **Problem:** When the admin filters to 11 active profiles with 10 items per page, page 2 contains one profile. If the admin deactivates that profile, only 10 active profiles remain. The frontend may reload the now-invalid page 2 and display stale rows or incorrect pagination/counts.
>
> **Instructions:**
>
> 1. Inspect only the admin directory page component and its directly related existing directory-fetching code. Likely starting point: `frontend/src/app/admin/page.tsx`. Inspect other files only if necessary.
> 2. Trace the current page state, filtered total/count, page size, fetch behavior, and deactivation-success handler before editing.
> 3. After a successful status change, ensure the directory never remains on a page beyond the last valid page for the current filtered result set.
> 4. If the current page becomes invalid, move to the last valid page and fetch the correct results. If necessary, handle an invalid/empty page response safely without showing stale rows or incorrect counts.
> 5. Preserve existing search, active-status filters, pagination behavior, authentication, and CSRF handling.
> 6. Add or update a focused regression test using the project's existing frontend testing setup if one is available. Do not introduce a new testing framework or dependencies.
> 7. Make the smallest safe change. Do not modify backend code, audit logging, unrelated UI, or documentation for this task.
> 8. Run the relevant available test/check commands and `git diff --check`. Report exact files changed, test results, and any manual browser verification still needed.
> 9. Do not commit or push.
>
> Do not implement the separate out-of-order request race-condition fix in this task; that is Issue 3. Avoid broad refactoring and do not claim browser reproduction unless you actually performed it.

#### 3. Requirements and acceptance criteria

- After a successful status change, the directory never remains beyond the last valid page for the current filtered result set.
- When the current page becomes invalid, the UI moves to the last valid page and fetches the correct results, with no stale rows and correct counts.
- Existing search, status filters, pagination behavior, authentication, and CSRF handling are preserved.
- Smallest safe change: no backend, audit-logging, unrelated UI, or documentation changes, and no new testing framework or dependencies.
- The out-of-order request race condition (Issue 3) is explicitly excluded.

#### 4. File allowed to change

- `frontend/src/app/admin/page.tsx`

The prompt limited the change to the admin directory component and directly related fetching code only if necessary. The reported implementation was confined to this file.

#### 5. Implementation and refinement

- The change updates the filtered count after a successful status change and, when the current page exceeds the last valid page, moves to that last valid page.
- It clears stale rows and uses the existing fetch effect to load the correct results.
- No broader refactor or authentication change was part of the fix. No separate refinement round is recorded for this issue.
- The retained record does not show a frontend regression test being added; the checks reported below are lint and build.

#### 6. Automated verification (as reported)

- Frontend `npm run lint` — **passed**.
- Frontend `npm run build` — **passed**.
- `git diff --check` — **passed**.

These results come from the implementation run and were not rerun while preparing this document. They do not demonstrate the browser scenario.

#### 7. Manual verification status

- **Before the fix (reproduced):** the developer manually reproduced the symptom. After deactivating the only profile on page 2, the UI stayed on page 2 instead of returning to page 1.
- **After the fix (completed, developer-reported, 2026-10-27):** the developer manually tested the pagination scenario. With 11 active profiles and 10 profiles per page, the only profile on page 2 was deactivated. The developer confirmed that the UI returned to the valid page and displayed the correct rows and count. This replaces the earlier limitation that no post-fix manual browser test had been recorded.
- **Limitations of this record:** the exact browser steps, environment, and screenshots were not retained. Only the scenario above was reported as manually tested; other filters and search combinations were not reported as manually tested.

#### 8. Human-review checklist and remaining work

- [x] Filtered total is adjusted correctly after a successful deactivation.
- [x] The last valid page is calculated correctly (including the case where results become empty).
- [x] Navigation to that page happens when the current page becomes invalid.
- [x] Stale rows are cleared or replaced and the correct results are fetched.
- [x] Search, filters, and unrelated request behavior are unchanged.
- [x] No backend, audit-log, or unrelated UI change.
- [x] Post-fix manual browser verification performed (developer-reported, 2026-10-27): the UI returned to the valid page with correct rows and count.
- [x] Source diff reviewed against this checklist (developer's manual source review, confirmed correct, 2026-10-27; the code-review items above are checked on that basis).

**Remaining work for Issue 2:** none recorded. The post-fix manual browser verification and the developer's source diff review (2026-10-27) are done.

### 3.3 Issue 3 — Out-of-order directory requests (separate from Issue 2)

#### 1. Mentor-reported problem

- Mentor's stated concern (as relayed by the developer): out-of-order admin directory responses can overwrite newer results when search or filters change quickly. The exact mentor wording is not available in the retained context.
- The Issue 2 prompt explicitly excluded the "out-of-order request race-condition fix" and named it Issue 3. The Issue 2 pagination fix was not an Issue 3 fix.

#### 2. Original coding prompt

Not retained. The retained records contain no Issue 3 coding prompt, so none is quoted here.

#### 3. Requirements and acceptance criteria

Superseded or stale directory responses must not overwrite the results for the latest search/filter query, including stale error responses. (Stated from the developer's description; no retained prompt specifies further criteria.)

#### 4. File allowed to change

- `frontend/src/app/admin/page.tsx` (the developer-reported location of the implementation).

#### 5. Implementation (developer-reported)

- The developer reported that the implementation in `frontend/src/app/admin/page.tsx` guards against stale directory responses when the search/filter query changes.
- The reported mechanism is a request sequence / current-query guard plus effect cleanup, so that superseded responses, including stale errors, do not overwrite the latest results.
- **Not independently confirmed:** the documentation author did not inspect the source diff, so this description has not been checked against the code.

#### 6. Verification by type

- **Automated backend tests:** not applicable. No backend change was reported for Issue 3, and no backend test result is claimed for it. The backend results in Section 3.1 belong to Issue 1 only.
- **Frontend static/build checks (developer-reported, not rerun while preparing this document):** `npm run lint` passed; `npm run build` passed; `git diff --check` passed.
- **Automated frontend race-condition test:** none. No frontend automated test framework was available, so no automated frontend race-condition test was added and none is claimed. Lint and build do not demonstrate the race-condition behavior.
- **Manual browser verification (developer-reported, Chrome DevTools):** the developer temporarily delayed the Ayesha response by 5 seconds, searched Ayesha, then immediately searched Fatima. After the delayed Ayesha response completed, Fatima's results remained on screen. The temporary browser test hook was not committed to the project (developer-reported). The exact steps beyond this description, environment, and screenshots were not retained.

#### 7. Manual verification status

Completed for the scenario above (developer-reported). Only this delayed-response scenario was reported; other filter combinations and stale-error behavior were not reported as manually tested. The stale-error handling is therefore described as implemented per the developer's report but is not claimed as manually verified.

#### 8. Human-review checklist and remaining work

- [x] The sequence/current-query guard ignores a response whose query is no longer current.
- [x] Effect cleanup invalidates the in-flight request when the query changes or the component unmounts.
- [x] Stale error responses cannot overwrite the latest results or error state.
- [x] Loading state is not left incorrect by a superseded request.
- [x] The Issue 2 last-valid-page behavior and existing search, filter, authentication, and CSRF handling are unchanged.
- [ ] The temporary browser test hook is not present in the committed source.
- [x] Source diff reviewed (developer's manual source review, confirmed correct, 2026-10-27). The one item left unchecked above, absence of the temporary test hook from the committed source, was not separately confirmed.

**Remaining work for Issue 3:** confirm the temporary test hook is absent from the repository (the developer's source diff review was completed on 2026-10-27), and optionally add an automated frontend race-condition test if a frontend test framework is introduced later.

### 3.4 Week 2 final checklist

| Check | Status | Notes |
| --- | --- | --- |
| Issue 1 focused admin API tests | Reported passed | 16 tests |
| Issue 1 full backend suite | Reported passed before the final test-only assertion change | 75 tests; superseded by the 2026-10-27 full-suite run below |
| Issue 1 focused tests after final assertion change | Reported passed | 16 tests |
| Focused admin API tests (`profiles.test_admin_api`), 2026-10-27 | **Passed** (developer-run) | 16 tests; focused run only; backend only |
| Full backend suite (`python manage.py test`), 2026-10-27 | **Passed** (developer-run) | 75 tests; backend only; does not verify frontend behaviour |
| Django system check, 2026-10-27 | **Passed** (developer-run) | No issues identified; exact command not recorded |
| Issue 2 `npm run lint` | Reported passed | Frontend |
| Issue 2 `npm run build` | Reported passed | Frontend, including TypeScript |
| `git diff --check` | Reported passed | Reported by the implementation runs |
| Issue 2 pagination symptom reproduced before fix | Done (developer-reported) | UI stayed on page 2 |
| Issue 2 post-fix manual browser test | **Completed** (developer-reported, 2026-10-27) | 11 active profiles, 10 per page; after deactivating the only profile on page 2, the UI returned to the valid page with correct rows and count |
| Issue 1 manual check of `is_active` in `profiles_healthprofile` | **Completed** (developer-reported, 2026-10-27) | `is_active` becomes false when deactivated and true when reactivated |
| Issue 1 manual check that repeated-status requests create no extra audit event | **Not confirmed** | Covered by automated tests only; not separately verified manually |
| Source diff review against the checklists above (Issues 1, 2 and 3) | **Completed** (developer-reported, 2026-10-27) | Developer personally reviewed the source changes and confirmed they look correct; no findings or notes retained |
| Issue 3 `npm run lint` | Reported passed (developer-reported) | Frontend; not rerun while preparing this document |
| Issue 3 `npm run build` | Reported passed (developer-reported) | Frontend; not rerun while preparing this document |
| Issue 3 `git diff --check` | Reported passed (developer-reported) | Not rerun while preparing this document |
| Issue 3 manual browser test (Chrome DevTools, delayed Ayesha response then Fatima search) | **Completed** (developer-reported) | Fatima's results stayed on screen after the delayed Ayesha response completed; temporary test hook not committed |
| Issue 3 automated frontend race-condition test | **None added** | No frontend automated test framework available; not claimed |
| Issue 3 out-of-order admin directory responses | Implemented per developer report in `frontend/src/app/admin/page.tsx`; developer's source diff review completed 2026-10-27 | Separate from Issue 2; mentor concern: out-of-order responses can overwrite newer results when search or filters change quickly |

## 4. Human review and security boundaries

The project requirements and follow-up decisions were supplied by the developer. The retained instructions repeatedly required:

- Human approval before broad setup changes.
- No guessed database credentials and no real secrets in source control.
- PostgreSQL-only configuration.
- Separate standard-user JWT and administrator session authentication.
- CSRF protection and staff-only admin endpoints.
- Preservation of profile ownership boundaries.
- Review of generated migration plans, and no database resets, automatic commits, credential exposure, or unrelated changes without approval.

This document does not assert that a formal security audit or penetration test was performed. The documentation task itself involved no application-code changes, migrations, database resets, commits, or pushes.

## 5. Verification evidence (dated history)

Sections 5.1 and 5.2 are historical results. They were not rerun for the Week 2 fixes or for this documentation update. The only 2026-10-27 reruns are the developer's backend runs recorded in Section 5.3.

### 5.1 Documentation audit — 2026-10-19

Reported as run during the documentation audit:

- `backend\.venv\Scripts\python.exe manage.py test` — 55 tests passed; Django created and destroyed its separate test database.
- `backend\.venv\Scripts\python.exe manage.py check` — no issues identified.
- `backend\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` — no model changes detected.
- `backend\.venv\Scripts\python.exe -m pip check` — no broken requirements.
- `frontend` `npm run lint` — passed.
- `frontend` `npm run build` — passed, including TypeScript checking and static generation.
- Read-only PostgreSQL inspection confirmed PostgreSQL 18.4, the configured target connection, the expected user/profile tables, migration application, and documented uniqueness/index objects.

These results are command output from that audit and do not substitute for manual interaction testing in a browser.

### 5.2 Final integration verification — 2026-10-22

Results reported by the final integration run:

- Full Django test suite — 70 tests passed.
- Django `manage.py check` — passed with no issues.
- Django `manage.py makemigrations --check --dry-run` and `manage.py migrate --check` — passed.
- Frontend `npm run lint` — passed.
- Frontend `npm run build` — passed, including TypeScript checking and production build.
- `git diff --check` — passed.

These results should not be conflated with the later 75-test backend run for the Week 2 Issue 1 fix, or with the 2026-10-27 run in Section 5.3.

### 5.3 Backend verification — 2026-10-27

The developer reported running the following successfully from the `backend` directory with the project's `.venv` activated. The documentation author did not run them.

| Command | Result | Scope |
| --- | --- | --- |
| `python manage.py test profiles.test_admin_api` | 16 tests passed | Focused run: admin API tests only |
| `python manage.py test` | 75 tests passed | Full backend suite |
| Django system check | No issues identified | Exact command not recorded |

Scope and limits:

- These are backend results only. They support the Issue 1 backend behaviour (strict boolean validation, no-op without audit events, atomic status and audit update). They do **not** verify the Issue 2 pagination or Issue 3 out-of-order request behaviour, which are frontend changes covered only by the frontend checks and manual browser tests in Sections 3.2 and 3.3.
- Frontend `npm run lint`, `npm run build`, and `git diff --check` were **not** rerun for this update; their results remain the earlier developer-reported ones.
- `manage.py makemigrations --check --dry-run` and `manage.py migrate --check` were not part of this run, so no new result is claimed for them.
- This run does not mean the whole project is fully verified, production-ready, or security-audited.

### 5.4 Developer-reported manual checks

The project task history reports that standard-user and admin workflows were manually tested. The exact browser steps, environment, and screenshots were not retained, so this report does not treat them as independently reproduced.

On 2026-10-27 the developer additionally reported manual checks of the Week 2 fixes: the Issue 1 `is_active` transitions in `profiles_healthprofile`, and the Issue 2 pagination scenario (11 active profiles, 10 per page, deactivating the only profile on page 2). The repeated-status/no-extra-audit-event behavior was not separately confirmed manually. Details are in Sections 3.1, 3.2 and 3.4. The developer also reported a manual Chrome DevTools test for Issue 3 (delayed Ayesha response, then a Fatima search; Fatima's results remained on screen), described in Section 3.3. The developer also reported completing a manual review of the source changes for all three issues on 2026-10-27 (Section 3.4).

## 6. Lessons and limitations

- Trace each frontend request through its same-origin Next.js route, proxy mapping, and Django URL configuration; similarly named frontend and backend routes can have different behavior.
- Django login can rotate the CSRF secret. The client must use the fresh token returned by login for subsequent session-authenticated mutations.
- Keep database identity verification separate from migration execution, and never infer project credentials from placeholders.
- Use synthetic accounts and fictional profile details for demonstrations. Do not put real health data, tokens, or credentials in screenshots or recordings.
- Validate JSON booleans strictly; Python truthiness would accept `"false"` as true.
- Reported test output is evidence of what was run, not a substitute for reviewing the diff or performing manual checks.
- Backend tests do not verify frontend behaviour. Issue 2 and Issue 3 rely on frontend lint/build and on one manual browser scenario each; no automated frontend test exists for either.
- Developer's manual source-code review of all three issues was completed on 2026-10-27 (developer-reported; no findings retained).
- Outstanding: optional manual check of repeated-status requests creating no extra audit event; confirmation that the temporary DevTools test hook is absent from the committed source.
- The complete historical prompt transcript for earlier phases and the original formal assignment file were not found in the retained project context. Confirm any rubric-specific requirements against the original assignment source.