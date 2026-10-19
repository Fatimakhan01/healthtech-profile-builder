# HealthProfile

HealthProfile is a full-stack assignment foundation with a TypeScript/Next.js frontend and a Django REST Framework backend. The frontend and backend keep their dependencies separate.

## Project layout

- `frontend/` — Next.js App Router application, TypeScript, and Tailwind CSS.
- `backend/accounts/` — custom email-based user model and standard/admin role definitions.
- `backend/profiles/` — one-to-one health profile schema.
- `backend/` — Django project and pinned Python dependencies.
- `backend/.venv/` — local Python virtual environment (not tracked by Git).
- `.env.example` — names of local settings to configure; it contains placeholders, not credentials.

## Prerequisites

- Node.js and npm compatible with the generated Next.js version.
- Python 3.14 for the pinned backend dependencies.
- PostgreSQL 18, or a compatible PostgreSQL server, with a project database and login role provisioned separately.

PostgreSQL is the configured backend database. The application does not fall back to SQLite. Database provisioning and migrations require working project credentials.

## Local configuration

Copy `.env.example` to `.env` and replace every placeholder locally. The Django settings load the root `.env` file using the pinned `python-dotenv` dependency. Do not commit `.env` or put real credentials in source control. Alternatively, set the listed variables in the shell that runs Django. For PowerShell, for example:

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

## Run the frontend

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open the local URL printed by Next.js.

## Run the backend

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

The database must already exist and the PostgreSQL environment variables above must refer to a working login before running migrations. The backend exposes standard-user signup and JWT login, JWT-protected self-service profile endpoints, and separate session-authenticated administrator endpoints.

## Standard-user authentication

The API provides:

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

The browser calls same-origin Next.js route handlers, which proxy requests to Django. The proxy defaults to `http://127.0.0.1:8000/api`; set `BACKEND_API_URL` in the Next.js server environment to override it. Standard-user access JWTs remain in browser JavaScript memory only, expire after five minutes, and are never stored in browser storage or cookies. To restore authentication after a reload, the frontend login route also establishes a Django server-side session. Its session identifier is carried only in an HttpOnly, SameSite=Lax cookie (Secure when `DEBUG` is false), with a 14-day maximum lifetime from login. The cookie is forwarded by the Next.js proxy only to the standard-session routes; it is not an access JWT or refresh JWT. Session refresh is a CSRF-protected POST and returns a fresh five-minute access JWT to memory. No refresh token is exposed to browser JavaScript. Explicit logout invalidates the Django session and clears the session cookie. A JWT issued before logout remains valid until its own five-minute expiry; logout does not revoke that already-issued stateless access JWT. Use HTTPS in deployment; XSS could still read a live access token while the page is open.

JWT-protected API access is restricted to standard-role users. The standard-user session is only a server-held credential for issuing new short-lived access JWTs; it does not grant access to admin-only routes. Administrator sessions and their CSRF flow are separate and documented below.

The browser-facing auth proxy routes are `GET /api/auth/csrf/`, `POST /api/auth/login/`, `POST /api/auth/session/refresh/`, and `POST /api/auth/session/logout/`. Fetch a CSRF token before login or other session-changing requests; send it in `X-CSRFToken`. On reload, the frontend obtains a fresh CSRF token and uses the existing HttpOnly session cookie to restore a short-lived access token. Session refresh requires an active standard-user session. The Django session expires after at most 14 days.

## Health profile API

Both profile routes require a standard-user access token:

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
2. `POST /api/admin/login/` with JSON `{"email":"admin@example.com","password":"<local password>"}`, the CSRF cookie, and the returned token in the `X-CSRFToken` header. Successful login establishes an HttpOnly server-side session cookie; the response contains only user ID, email, and role.
3. `GET /api/admin/session/` to check the current admin session.
4. `POST /api/admin/session/` with the CSRF cookie and `X-CSRFToken` header to log out and invalidate the server-side session.

The CSRF endpoint returns `{"csrf_token":"<token>"}`. Admin login returns `{"user":{"id":1,"email":"admin@example.com","role":"admin"}}`; the session endpoint has the same user shape. Invalid credentials return `401`; an anonymous or ordinary account is denied admin-only routes. Session-changing requests require CSRF validation. In production, secure session and CSRF cookies are enabled when `DEBUG` is false; both cookies use `SameSite=Lax`.

Create an administrator locally using Django's supported interactive command from the backend directory, after setting the database and Django environment:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Enter the administrator email and password only at the interactive prompts. Do not create default credentials or send secrets through commands, source control, or chat.

The admin UI is available at `/admin`. Its session-protected profile table calls `GET /api/admin/profiles/`, which is restricted to Django staff users and supports `search` (profile full name or account email), `active=true|false`, and page-number pagination with a default of 10 rows (maximum `page_size` 50). Example: `/api/admin/profiles/?search=alex&active=true&page=1&page_size=10`. The response follows DRF pagination (`count`, `next`, `previous`, and `results`). The admin UI bootstraps CSRF and checks the existing session before requesting profiles; login and logout use the existing CSRF-protected session endpoints.

## Database schema

`accounts.User` is the authentication identity and uses a normalized email address. A regular unique constraint supports Django's `USERNAME_FIELD` checks and exact normalized-email lookups; an additional database unique constraint on `LOWER(email)` prevents case-only duplicates even for writes that bypass application normalization. The user manager creates standard users by default and reserves administrator creation for Django's superuser manager path.

Each user may have one `profiles.HealthProfile`; deleting a user cascades to that profile. The profile stores a full name, optional age band (not date of birth), contact preference, wellness goals, optional allergies, optional emergency-contact details, optional lifestyle notes, active status, and timestamps. It deliberately does not model clinical diagnoses. An index on `(is_active, created_at DESC)` supports administrative profile listing by status and recency; the one-to-one relation and normalized-email constraint are indexed by their database constraints.

Initial migrations are generated in `accounts/migrations/` and `profiles/migrations/`. They define schema only; run them only after verifying the configured PostgreSQL database and credentials.

## Verify

```powershell
Push-Location backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
Pop-Location

Push-Location frontend
npm run lint
npm run build
Pop-Location
```

The Day 1 model tests do not require a database. The Day 2 authentication tests create users and profiles and therefore require the configured PostgreSQL database plus permission to create a test database. The full suite creates and removes a separate temporary test database.
