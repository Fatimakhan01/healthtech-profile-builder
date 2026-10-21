# API and authentication reference

This document describes the Django API and the same-origin Next.js routes exposed by this repository. Browser requests use Next.js `/api/...` handlers, which proxy to Django at `BACKEND_API_URL` (default `http://127.0.0.1:8000/api`). The Django route and browser route may differ even when their paths look the same.

All examples use fictional values. Never put actual passwords, access tokens, or secret configuration in source control.

## Standard-user account and token API

| Method and Django route | Purpose | Authentication and CSRF |
|---|---|---|
| `POST /api/auth/signup/` | Create a standard user and initial health profile. | Public; no CSRF enforcement in this view. |
| `POST /api/auth/login/` | Issue a stateless access JWT. | Public; this direct Django endpoint does not create a session. |
| `GET /api/auth/me/` | Return the current standard user's safe identity. | `Authorization: Bearer <access-token>`; standard-user role. |

Signup accepts:

```json
{
  "full_name": "Example Person",
  "email": "person@example.test",
  "password": "<strong local password>"
}
```

Email is trimmed and lowercased; invalid or case-insensitive duplicate email, weak password, missing fields, or unexpected/privileged fields are rejected with `400`. Successful signup returns `201`:

```json
{
  "user": {
    "id": 1,
    "email": "person@example.test",
    "full_name": "Example Person",
    "role": "standard"
  }
}
```

Direct Django login accepts `email` and `password`; a successful response contains `access_token`, `token_type: "Bearer"`, `expires_in: 300`, and `user`. Invalid credentials return `401`. The access token is valid for five minutes. This API issues no refresh JWT.

`GET /api/auth/me/` returns `{"user":{"id":1,"email":"person@example.test","full_name":"Example Person","role":"standard"}}`. Missing, malformed, or expired access tokens return `401`; a non-standard user is denied.

## Standard-user browser session and JWT restoration

The frontend uses these same-origin Next.js routes:

| Browser route | Proxied Django route | Purpose and protections |
|---|---|---|
| `GET /api/auth/csrf/` | `GET /api/auth/csrf/` | Returns a CSRF token and sets the CSRF cookie. |
| `POST /api/auth/signup/` | `POST /api/auth/signup/` | Public signup described above. |
| `POST /api/auth/login/` | `POST /api/auth/session/login/` | CSRF-protected login; establishes the standard-user server-side session and returns a fresh five-minute access JWT. |
| `POST /api/auth/session/refresh/` | Same path | CSRF-protected; requires an active standard-user session and returns a new short-lived access JWT. |
| `POST /api/auth/session/logout/` | Same path | CSRF-protected; invalidates the standard-user session. |

The route distinction is important: the browser's `/api/auth/login/` is handled by Next.js and maps to Django's session login route. A direct request to Django `/api/auth/login/` uses the stateless JWT login view above instead.

The frontend holds standard-user access JWTs in JavaScript memory; it does not put them in local or session storage or cookies. The browser's server-side session identifier is stored in an HttpOnly cookie. The session cookie has a configured maximum age of 14 days; it is `SameSite=Lax` and is `Secure` when Django `DEBUG` is false. The Django CSRF cookie is HttpOnly and `SameSite=Lax`, and is also Secure when `DEBUG` is false. Next.js forwards only the session and CSRF cookies to the relevant session routes. State-changing session requests use `X-CSRFToken`.

Refresh obtains a new short-lived JWT from the Django session; it is not a JWT refresh-token grant. Logout invalidates the server session, but an already-issued stateless access JWT remains usable until its own five-minute expiry. The API returns safe validation/authentication error bodies; commonly applicable status codes include `400` for invalid input, `401` for invalid credentials or access tokens, `403` for denied permissions/CSRF, and `204` for successful logout.

## Standard-user health profile API

Both browser routes are same-origin Next.js proxies to Django `/api/profiles/me/`.

| Method and route | Purpose | Authentication |
|---|---|---|
| `GET /api/profile/me/` (browser) → `GET /api/profiles/me/` (Django) | Retrieve the authenticated user's own profile. | Standard-user JWT. |
| `PATCH /api/profile/me/` (browser) → `PATCH /api/profiles/me/` (Django) | Update permitted fields on that user's profile. | Standard-user JWT. |

The patch body may contain any subset of `full_name`, `age_range`, `contact_preference`, `wellness_goals`, `allergies`, `emergency_contact_name`, `emergency_contact_relationship`, `emergency_contact_phone`, and `lifestyle_notes`. Example:

```http
PATCH /api/profile/me/
Authorization: Bearer <short-lived-access-token>
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

The response contains the permitted profile fields only. Profile ownership is derived from the authenticated user; `user`, `is_active`, timestamps, and unknown fields cannot be written through this API. Full name must not be blank, choice values must be valid, the phone must match the model validator, and emergency-contact name, relationship, and phone must be supplied together. Invalid input returns `400`; missing/invalid authentication returns `401`. Standard users cannot retrieve or edit another user's profile.

## Administrator session and CSRF API

Admin authentication is separate from standard-user JWT authentication. Admin accounts are provisioned through Django, not public signup. Browser routes below are Next.js same-origin proxies to the corresponding Django `/api/admin/...` paths.

| Method and route | Purpose | Authentication and CSRF |
|---|---|---|
| `GET /api/admin/csrf/` | Bootstrap CSRF cookie and obtain JSON token. | Public bootstrap. |
| `POST /api/admin/login/` | Authenticate an active staff account and establish a Django server-side session. | CSRF cookie and matching `X-CSRFToken`; no JWT. |
| `GET /api/admin/session/` | Return the authenticated staff user's ID, email, and role. | Django session and staff permission. |
| `POST /api/admin/session/` | Invalidate the current admin session. | Django session, staff permission, and CSRF. |

Get a CSRF token before login:

```http
GET /api/admin/csrf/
```

The JSON response is `{"csrf_token":"<csrf-token>"}`. Submit credentials and the CSRF token:

```http
POST /api/admin/login/
Content-Type: application/json
X-CSRFToken: <csrf-token>
```

```json
{
  "email": "admin@example.test",
  "password": "<local administrator password>"
}
```

A successful login returns a safe `user` object and a newly rotated `csrf_token`; use the returned token for later state-changing admin requests. Django sets the HttpOnly server-side session cookie. Invalid credentials return `401`; missing/invalid CSRF is rejected with `403`. Session checks return `{"user":{"id":1,"email":"admin@example.test","role":"admin"}}`. An anonymous or non-staff account cannot use protected admin routes. Successful logout returns `204` and invalidates the server-side session.

Admin sessions expire after 8 hours, set explicitly at successful admin login. This shorter staff-session lifetime limits exposure from an unattended privileged browser session; regular standard-user sessions retain the 14-day Django default. Both use server-side Django sessions, and `SESSION_EXPIRE_AT_BROWSER_CLOSE` remains false. The expiration is enforced by the server-side session store, not merely by the browser cookie.

Create an administrator interactively from `backend/`:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Enter credentials only at Django's prompts. Do not create a default administrator or send passwords in command arguments.

## Admin profile directory, detail, and status

| Method and route | Purpose | Authentication and CSRF |
|---|---|---|
| `GET /api/admin/profiles/` | Search, filter, and paginate profile summaries. | Django session and staff permission. |
| `PATCH /api/admin/profiles/<profile_id>/status/` | Change only the profile's `is_active` value. | Django session, staff permission, and CSRF. |

The listing accepts:

- `search`: case-insensitive substring match on profile full name or account email.
- `active`: `true` or `false`; other values return `400`.
- `page`: page number.
- `page_size`: requested page size, default `10`, maximum `50`.

The DRF paginated response contains `count`, `next`, `previous`, and `results`. Each result is serialized using `AdminHealthProfileSerializer`: profile `id`, `user_id`, `email`, `full_name`, `age_range`, `contact_preference`, `wellness_goals`, `allergies`, emergency-contact name/relationship/phone, `lifestyle_notes`, `is_active`, `created_at`, and `updated_at`. Credential fields are not included. The frontend opens a detail modal using this already-authorized listing data; there is no separate profile-detail GET endpoint.

Change status with a JSON boolean:

```http
PATCH /api/admin/profiles/1/status/
Content-Type: application/json
X-CSRFToken: <current-admin-csrf-token>
```

```json
{"is_active": false}
```

The response is the updated admin profile serialization. Invalid data returns `400`; an unknown profile returns `404`; unauthenticated/non-staff access and failed CSRF checks are denied. Deactivation changes `HealthProfile.is_active` only. It does not change the associated Django user's `is_active`, delete the profile, or remove profile data. The UI confirms before deactivating; reactivation is available without confirmation.
