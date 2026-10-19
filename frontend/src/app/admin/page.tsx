"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type AdminUser = {
  id: number;
  email: string;
  role: string;
};

type Profile = {
  id: number;
  email: string;
  full_name: string;
  age_range: string;
  contact_preference: string;
  wellness_goals: string;
  allergies: string;
  emergency_contact_name: string;
  emergency_contact_relationship: string;
  emergency_contact_phone: string;
  lifestyle_notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type ApiResponse = {
  detail?: string;
  csrf_token?: string;
  user?: AdminUser;
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: Profile[];
  [field: string]: unknown;
};

async function readApiResponse(response: Response): Promise<ApiResponse> {
  const contentType = response.headers.get("content-type") ?? "";
  if (
    !contentType.includes("application/json") &&
    !contentType.includes("+json")
  ) {
    return {
      detail: `The admin API returned a non-JSON response (HTTP ${response.status}). Check the Next.js proxy and Django API configuration.`,
    };
  }

  try {
    return (await response.json()) as ApiResponse;
  } catch {
    return {
      detail: `The admin API returned invalid JSON (HTTP ${response.status}).`,
    };
  }
}

function responseError(payload: ApiResponse) {
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  return Object.entries(payload)
    .flatMap(([field, value]) =>
      (Array.isArray(value) ? value : [value])
        .filter((item): item is string => typeof item === "string")
        .map((item) => `${field}: ${item}`),
    )
    .join(" ");
}

export default function AdminPage() {
  const [csrfToken, setCsrfToken] = useState("");
  const [admin, setAdmin] = useState<AdminUser | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState<string | null>(null);
  const [previous, setPrevious] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const checkSession = useCallback(async () => {
    const csrfResponse = await fetch("/api/admin/csrf/", {
      cache: "no-store",
    });
    const csrfPayload = await readApiResponse(csrfResponse);
    if (!csrfResponse.ok || !csrfPayload.csrf_token) {
      throw new Error(
        responseError(csrfPayload) || "Could not initialize admin security.",
      );
    }
    setCsrfToken(csrfPayload.csrf_token);

    const sessionResponse = await fetch("/api/admin/session/", {
      cache: "no-store",
    });
    if (sessionResponse.status === 401 || sessionResponse.status === 403) {
      return;
    }
    const sessionPayload = await readApiResponse(sessionResponse);
    if (!sessionResponse.ok || !sessionPayload.user) {
      throw new Error(
        responseError(sessionPayload) || "Could not verify admin session.",
      );
    }
    setAdmin(sessionPayload.user);
  }, []);

  useEffect(() => {
    let mounted = true;
    void Promise.resolve()
      .then(checkSession)
      .catch((sessionError: unknown) => {
        if (mounted) {
          setError(
            sessionError instanceof Error
              ? sessionError.message
              : "Could not check the admin session.",
          );
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [checkSession]);

  const loadProfiles = useCallback(async () => {
    if (!admin) {
      return;
    }
    setLoadingProfiles(true);
    setError("");
    const parameters = new URLSearchParams({ page: String(page) });
    if (appliedSearch.trim()) {
      parameters.set("search", appliedSearch.trim());
    }
    if (activeFilter) {
      parameters.set("active", activeFilter);
    }

    try {
      const response = await fetch(`/api/admin/profiles/?${parameters}`, {
        cache: "no-store",
      });
      const payload = await readApiResponse(response);
      if (response.status === 401 || response.status === 403) {
        setAdmin(null);
        setProfiles([]);
        setError("Your administrator session is no longer valid. Sign in again.");
        return;
      }
      if (!response.ok) {
        throw new Error(responseError(payload) || "Could not load profiles.");
      }
      setProfiles(payload.results ?? []);
      setCount(payload.count ?? 0);
      setNext(payload.next ?? null);
      setPrevious(payload.previous ?? null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load profiles.",
      );
    } finally {
      setLoadingProfiles(false);
    }
  }, [activeFilter, admin, appliedSearch, page]);

  useEffect(() => {
    void Promise.resolve().then(loadProfiles);
  }, [loadProfiles]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let token = csrfToken;
      if (!token) {
        const csrfResponse = await fetch("/api/admin/csrf/", {
          cache: "no-store",
        });
        const csrfPayload = await readApiResponse(csrfResponse);
        if (!csrfResponse.ok || !csrfPayload.csrf_token) {
          throw new Error(
            responseError(csrfPayload) || "Could not initialize admin security.",
          );
        }
        token = csrfPayload.csrf_token;
        setCsrfToken(token);
      }

      const response = await fetch("/api/admin/login/", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrftoken": token,
        },
        body: JSON.stringify({ email, password }),
      });
      const payload = await readApiResponse(response);
      if (!response.ok || !payload.user) {
        throw new Error(responseError(payload) || "Administrator login failed.");
      }
      setAdmin(payload.user);
      setPassword("");
      setPage(1);
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? loginError.message
          : "Could not complete administrator login.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/admin/session/", {
        method: "POST",
        headers: { "x-csrftoken": csrfToken },
      });
      if (!response.ok) {
        const payload = await readApiResponse(response);
        throw new Error(responseError(payload) || "Could not log out.");
      }
      setAdmin(null);
      setProfiles([]);
      setPassword("");
    } catch (logoutError) {
      setError(
        logoutError instanceof Error
          ? logoutError.message
          : "Could not complete administrator logout.",
      );
    } finally {
      setBusy(false);
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setAppliedSearch(search);
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <p className="text-sm text-zinc-600" role="status">
          Checking administrator session...
        </p>
      </main>
    );
  }

  if (!admin) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-md items-center px-6 py-12">
        <section className="w-full rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm">
          <p className="text-sm font-medium text-zinc-500">HealthProfile</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            Administrator sign in
          </h1>
          <p className="mt-2 text-sm text-zinc-600">
            This sign-in uses a separate Django server-side session.
          </p>
          {error && (
            <p className="mt-5 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
              {error}
            </p>
          )}
          <form className="mt-6 space-y-4" onSubmit={submitLogin}>
            <label className="block text-sm font-medium">
              Email
              <input
                autoComplete="username"
                className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </label>
            <label className="block text-sm font-medium">
              Password
              <input
                autoComplete="current-password"
                className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <button
              className="w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
              disabled={busy}
              type="submit"
            >
              {busy ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-50 px-4 py-8 sm:px-6 lg:py-12">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-zinc-500">HealthProfile</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
              Profile management
            </h1>
            <p className="mt-2 text-sm text-zinc-600">
              Signed in as {admin.email}
            </p>
          </div>
          <button
            className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium disabled:opacity-50"
            disabled={busy}
            onClick={logout}
            type="button"
          >
            {busy ? "Please wait..." : "Log out"}
          </button>
        </header>

        <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-7">
          <form
            className="mb-6 grid gap-3 sm:grid-cols-[1fr_12rem_auto]"
            onSubmit={applyFilters}
          >
            <label className="text-sm font-medium">
              Search name or email
              <input
                className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2"
                onChange={(event) => setSearch(event.target.value)}
                value={search}
              />
            </label>
            <label className="text-sm font-medium">
              Status
              <select
                className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2"
                onChange={(event) => {
                  setActiveFilter(event.target.value);
                  setPage(1);
                }}
                value={activeFilter}
              >
                <option value="">All profiles</option>
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </select>
            </label>
            <button
              className="self-end rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white"
              type="submit"
            >
              Search
            </button>
          </form>

          {error && (
            <p className="mb-5 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
              {error}
            </p>
          )}
          {loadingProfiles ? (
            <p className="py-10 text-center text-sm text-zinc-600" role="status">
              Loading profiles...
            </p>
          ) : profiles.length === 0 ? (
            <p className="py-10 text-center text-sm text-zinc-600">
              No profiles match these filters.
            </p>
          ) : (
            <div className="space-y-4">
              {profiles.map((profile) => (
                <article
                  className="rounded-xl border border-zinc-200 p-4 sm:p-5"
                  key={profile.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="font-semibold text-zinc-950">
                        {profile.full_name}
                      </h2>
                      <p className="mt-1 text-sm text-zinc-600">
                        {profile.email}
                      </p>
                    </div>
                    <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium">
                      {profile.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                    <div>
                      <dt className="text-zinc-500">Age range</dt>
                      <dd>{profile.age_range || "Not specified"}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Contact preference</dt>
                      <dd>{profile.contact_preference}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Wellness goals</dt>
                      <dd>{profile.wellness_goals || "—"}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Allergies</dt>
                      <dd>{profile.allergies || "—"}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Emergency contact</dt>
                      <dd>
                        {profile.emergency_contact_name
                          ? `${profile.emergency_contact_name} (${profile.emergency_contact_relationship}) · ${profile.emergency_contact_phone}`
                          : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Lifestyle notes</dt>
                      <dd>{profile.lifestyle_notes || "—"}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          )}

          <footer className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4">
            <p className="text-sm text-zinc-600">
              {count} profile{count === 1 ? "" : "s"} · page {page}
            </p>
            <div className="flex gap-2">
              <button
                className="rounded-lg border border-zinc-300 px-3 py-2 text-sm disabled:opacity-40"
                disabled={!previous || loadingProfiles}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                type="button"
              >
                Previous
              </button>
              <button
                className="rounded-lg border border-zinc-300 px-3 py-2 text-sm disabled:opacity-40"
                disabled={!next || loadingProfiles}
                onClick={() => setPage((current) => current + 1)}
                type="button"
              >
                Next
              </button>
            </div>
          </footer>
        </section>
      </div>
    </main>
  );
}
