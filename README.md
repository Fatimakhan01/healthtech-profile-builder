# HealthProfile

HealthProfile is a full-stack assignment foundation with a TypeScript/Next.js frontend and a Django REST Framework backend. The frontend and backend keep their dependencies separate.

## Project layout

- `frontend/` — Next.js App Router application, TypeScript, and Tailwind CSS.
- `backend/accounts/` — custom email-based user model and standard/admin role definitions.
- `backend/profiles/` — one-to-one health profile schema.
- `backend/` — Django project and pinned Python dependencies.
- `backend/.venv/` — local Python virtual environment (not tracked by Git).
- `docs/` — API/authentication reference, schema/constraint diagram, AI-workflow evidence, and submission checklist.
- `.env.example` — names of local settings to configure; it contains placeholders, not credentials.

## Implemented features

**Standard users** can sign up, log in, restore their session, retrieve and edit their own health profile, and log out. Profile fields are limited to wellness goals and preferences, optional allergy information, and optional emergency-contact/lifestyle details; clinical diagnoses and precise dates of birth are not collected.

**Administrators** use a separate Django session and CSRF-protected login. Staff can search, filter, and paginate the profile directory, open a profile detail view, and deactivate or reactivate a profile. The latter changes only `HealthProfile.is_active`; it does not disable the Django user or delete profile data.

## Prerequisites

- Node.js 20.9 or later and npm, compatible with Next.js 16. The audited local environment used Node.js 24.18.0 and npm 11.17.0.
- Python 3.14 and pip. The audited local environment used Python 3.14.6 and pip 26.2.1.
- PostgreSQL 18 or a compatible PostgreSQL server, with a project database and login role provisioned separately. The configured database was verified as PostgreSQL 18.4 during the documentation audit.

PostgreSQL is the configured backend database. The application does not fall back to SQLite. Database provisioning and migrations require working project credentials.

## Local configuration

Copy `.env.example` to `.env` only if a root `.env` does not already exist, then replace every placeholder locally. Django loads the root `.env` using the pinned `python-dotenv` dependency. `.env.example` is a template, not a configuration file and not a source of usable credentials. Do not commit `.env` or put real credentials in source control. Alternatively, set the listed variables in the shell that runs Django. For PowerShell, for example:

```powershell
$env:DJANGO_SECRET_KEY = '<your-local-secret-key>'
$env:DJANGO_DEBUG = 'true'
$env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'
$env:POSTGRES_DB = '<provisioned-database-name>'
$env:POSTGRES_USER = '<provisioned-database-user>'
$env:POSTGRES_PASSWORD = '<user-provided-password>'
$env:POSTGRES_HOST = 'localhost'
$env:POSTGRES_PORT = '5432'
```

Do not use the example values as credentials. Obtain the database name, role, and password from the database administrator or provision them with the necessary local PostgreSQL access.

## PostgreSQL provisioning

Provision a database and least-privilege application login using an authorized PostgreSQL administrator account. Do not put a password in SQL history or a command argument. For example, open an interactive administrator connection with `psql -h <host> -U <administrator-role> -d postgres`, then enter:

```sql
CREATE ROLE healthprofile_app LOGIN;
```

Use the interactive `\password healthprofile_app` prompt to set its password, then create the database:

```sql
CREATE DATABASE healthprofile OWNER healthprofile_app;
```

Set the matching database, role, password, host, and port in the local `.env`; never copy the placeholders as credentials. The database must exist before running migrations.

## Local setup

From the repository root in PowerShell, create a virtual environment if one does not already exist, install the pinned backend dependencies, and create/edit `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path backend\.venv)) { py -3.14 -m venv backend\.venv }
& backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

After configuring `.env` and provisioning the PostgreSQL target, run the backend checks and migrations from the repository root:

```powershell
Push-Location backend
& .\.venv\Scripts\python.exe manage.py check
& .\.venv\Scripts\python.exe manage.py migrate
& .\.venv\Scripts\python.exe manage.py runserver
Pop-Location
```

The database must already exist and the PostgreSQL environment variables above must refer to a working login before running migrations. Create an administrator interactively after migrations with `Push-Location backend; & .\.venv\Scripts\python.exe manage.py createsuperuser; Pop-Location`; enter its email and password only at Django's prompts.

In a separate PowerShell terminal, install frontend dependencies and run Next.js:

```powershell
Push-Location frontend
npm ci
npm run dev
Pop-Location
```

The frontend is normally served at `http://localhost:3000`; Django's development server is normally served at `http://127.0.0.1:8000`. The Next.js proxy defaults to `http://127.0.0.1:8000/api`; set `BACKEND_API_URL` in the Next.js server environment to override it.

## Technology and architecture

| Area | Implementation |
|---|---|
| Frontend | Next.js 16.4.1 App Router, React 19.3.0, TypeScript, Tailwind CSS 4 |
| Backend | Python 3.14, Django 5.2.13, Django REST Framework 3.18.3 |
| Standard-user API authentication | Simple JWT 5.5.1 access JWTs, five-minute lifetime |
| Admin authentication | Django server-side sessions, CSRF validation, staff permission checks |
| Database | PostgreSQL only; psycopg 3.3.6 |
| Environment loading | python-dotenv 1.2.4 loads the repository-root `.env` |

The browser calls same-origin Next.js route handlers. Those handlers proxy to Django and narrowly forward the authentication cookies and headers needed by each route. Frontend and backend dependencies are managed separately in `frontend/package-lock.json` and `backend/requirements.txt`.

## Standard-user authentication

The Django API provides:

- `POST /api/auth/signup/` — accepts `full_name`, `email`, and `password`. Successful signup creates a standard user and its health profile, returning `201` with only the user ID, normalized email, full name, and role.
- `POST /api/auth/login/` — the Django API accepts `email` and `password` and returns a Bearer access token and `expires_in: 300`. The API issues no refresh token. The browser uses the same-origin Next.js route described below, which establishes a server-side session as the refresh credential.
- `GET /api/auth/me/` — requires `Authorization: Bearer <access-token>` and returns the authenticated standard user's safe profile summary.

Example signup body:

```json
{
  "full_name": "Example Person",
  "email": "person@example.com",
  "password": "<a strong password>"
}
```

Example login response (token value abbreviated):

```json
{
  "access_token": "<short-lived token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "user": {
    "id": 1,
    "email": "person@example.com",
    "full_name": "Example Person",
    "role": "standard"
  }
}
```

The raw Django `POST /api/auth/login/` endpoint issues a stateless access JWT. In contrast, the browser calls the same-origin Next.js `POST /api/auth/login/` route; that proxy maps to Django `POST /api/auth/session/login/` to establish the standard-user session used for restoration. All browser-facing API calls use same-origin Next.js handlers that proxy to Django. The proxy defaults to `http://127.0.0.1:8000/api`; set `BACKEND_API_URL` in the Next.js server environment to override it. Standard-user access JWTs remain in browser JavaScript memory only, expire after five minutes, and are never stored in browser storage or cookies. The session identifier is carried only in an HttpOnly, SameSite=Lax cookie (Secure when `DEBUG` is false), with a maximum age of 14 days. The cookie is forwarded by the Next.js proxy only to the standard-session routes; it is not an access JWT or refresh JWT. Session refresh is a CSRF-protected POST and returns a fresh five-minute access JWT to memory. No refresh token is exposed to browser JavaScript. Explicit logout invalidates the Django session. A JWT issued before logout remains valid until its own five-minute expiry; logout does not revoke that already-issued stateless access JWT. Use HTTPS in deployment; XSS could still read a live access token while the page is open.

JWT-protected API access is restricted to standard-role users. The standard-user session is only a server-held credential for issuing new short-lived access JWTs; it does not grant access to admin-only routes. Administrator sessions and their CSRF flow are separate and documented below.

The browser-facing auth routes are `GET /api/auth/csrf/`, `POST /api/auth/signup/`, `POST /api/auth/login/`, `POST /api/auth/session/refresh/`, and `POST /api/auth/session/logout/`. The login proxy targets Django `/api/auth/session/login/`; signup targets Django `/api/auth/signup/`. Fetch a CSRF token before session-changing requests and send it in `X-CSRFToken`. On reload, the frontend obtains a fresh CSRF token and uses the existing HttpOnly session cookie to restore a short-lived access token. Session refresh requires an active standard-user session. Django's configured session cookie maximum age is 14 days.

## Health profile API

The same-origin browser routes `GET/PATCH /api/profile/me/` proxy to Django `GET/PATCH /api/profiles/me/`. Both require a standard-user access token:

- `GET /api/profiles/me/` — retrieve the authenticated user's own health profile.
- `PATCH /api/profiles/me/` — update permitted profile fields. The API resolves the profile from the authenticated user; clients cannot select another profile.

Example request:

```http
PATCH /api/profiles/me/
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "full_name": "Example Person",
  "age_range": "25_34",
  "contact_preference": "email",
  "wellness_goals": "Improve daily activity",
  "allergies": "",
  "emergency_contact_name": "",
  "emergency_contact_relationship": "",
  "emergency_contact_phone": "",
  "lifestyle_notes": ""
}
```

The response contains only those health-profile fields. User ownership, active status, and timestamps are not writable or returned by this API. Unknown/protected fields, invalid choices, invalid phone numbers, and incomplete emergency-contact details return `400`; missing/invalid authentication returns `401`.

## Administrator session API

Administrator endpoints use Django server-side sessions, not standard-user JWTs:

1. `GET /api/admin/csrf/` to obtain a CSRF token in the JSON response and establish the CSRF cookie.
2. `POST /api/admin/login/` with JSON `{"email":"admin@example.com","password":"<local password>"}`, the CSRF cookie, and the returned token in the `X-CSRFToken` header. Successful login establishes an HttpOnly server-side session cookie and returns a safe user summary plus a newly rotated CSRF token.
3. `GET /api/admin/session/` to check the current admin session.
4. `POST /api/admin/session/` with the CSRF cookie and `X-CSRFToken` header to log out and invalidate the server-side session. Login rotates Django's CSRF secret, so use the `csrf_token` returned by the successful login response for later state-changing requests.

The CSRF endpoint returns `{"csrf_token":"<token>"}`. Admin login returns `{"user":{"id":1,"email":"admin@example.com","role":"admin"},"csrf_token":"<rotated-token>"}`; the session endpoint has the same user shape. Invalid credentials return `401`; an anonymous or ordinary account is denied admin-only routes. Session-changing requests require CSRF validation. In production, secure session and CSRF cookies are enabled when `DEBUG` is false; both cookies use `SameSite=Lax`.

Create an administrator locally using Django's supported interactive command from the backend directory, after setting the database and Django environment:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Enter the administrator email and password only at the interactive prompts. Do not create default credentials or send secrets through commands, source control, or chat.

The admin UI is available at `/admin`. Its session-protected profile table calls `GET /api/admin/profiles/`, which is restricted to Django staff users and supports `search` (profile full name or account email), `active=true|false`, and page-number pagination with a default of 10 rows (maximum `page_size` 50). Example: `/api/admin/profiles/?search=alex&active=true&page=1&page_size=10`. The response follows DRF pagination (`count`, `next`, `previous`, and `results`). Staff users can change only a profile's active flag through `PATCH /api/admin/profiles/<profile_id>/status/` with `{"is_active":false}` or `{"is_active":true}`; this retains the account and profile data and requires the existing Django session and CSRF token. The admin UI asks for confirmation before deactivation. The admin UI bootstraps CSRF and checks the existing session before requesting profiles; login and logout use the existing CSRF-protected session endpoints.

## Database schema

`accounts.User` is the authentication identity and uses a normalized email address. A regular unique constraint supports Django's `USERNAME_FIELD` checks and exact normalized-email lookups; an additional database unique constraint on `LOWER(email)` prevents case-only duplicates even for writes that bypass application normalization. The user manager creates standard users by default and reserves administrator creation for Django's superuser manager path.

Each user may have one `profiles.HealthProfile`; deleting a user cascades to that profile. The profile stores a full name, optional age band (not date of birth), contact preference, wellness goals, optional allergies, optional emergency-contact details, optional lifestyle notes, active status, and timestamps. It deliberately does not model clinical diagnoses. An index on `(is_active, created_at DESC)` supports administrative profile listing by status and recency; the one-to-one relation and normalized-email constraint are indexed by their database constraints.

Initial migrations are in `backend/accounts/migrations/` and `backend/profiles/migrations/`. They define schema only; run them only after verifying the configured PostgreSQL database and credentials. On 2026-10-19, read-only inspection connected to the configured PostgreSQL 18.4 database, found the user/profile tables and documented constraints/indexes, and showed all migrations applied. A fresh setup must provision its own database and apply migrations.

See [docs/api-authentication.md](./docs/api-authentication.md) for full Django and browser-proxy API contracts, [docs/database-er-diagram.md](./docs/database-er-diagram.md) for the ER diagram and verified schema/index details, [docs/ai-workflow.md](./docs/ai-workflow.md) for evidence-based AI workflow notes, and [docs/submission-checklist.md](./docs/submission-checklist.md) for submission status and remaining tasks. The formal original assignment brief was not located in the repository, so the checklist does not claim a verified rubric mapping.

## Verify

```powershell
Push-Location backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
Pop-Location

Push-Location frontend
npm run lint
npm run build
Pop-Location
```
