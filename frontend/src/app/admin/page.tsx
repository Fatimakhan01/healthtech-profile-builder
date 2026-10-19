"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type AdminUser = {
  id: number;
  email: string;
  role: string;
};

type Profile = {
  id: number;
  user_id: number;
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
  is_active?: boolean;
  updated_at?: string;
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
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null);
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
  const [statusUpdatingId, setStatusUpdatingId] = useState<number | null>(null);
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
        setSelectedProfile(null);
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
      if (!response.ok || !payload.user || !payload.csrf_token) {
        throw new Error(responseError(payload) || "Administrator login failed.");
      }
      setCsrfToken(payload.csrf_token);
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
      setSelectedProfile(null);
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

  async function updateProfileStatus(profile: Profile) {
    const nextActiveState = !profile.is_active;
    if (
      profile.is_active &&
      !window.confirm(`Deactivate the profile for ${profile.full_name}?`)
    ) {
      return;
    }
    if (!csrfToken) {
      setError("Admin security token is missing. Refresh the page and sign in again.");
      return;
    }

    setStatusUpdatingId(profile.id);
    setError("");
    try {
      const response = await fetch(
        `/api/admin/profiles/${profile.id}/status/`,
        {
          method: "PATCH",
          headers: {
            "content-type": "application/json",
            "x-csrftoken": csrfToken,
          },
          body: JSON.stringify({ is_active: nextActiveState }),
        },
      );
      const payload = await readApiResponse(response);
      if (!response.ok) {
        throw new Error(
          responseError(payload) || "Could not update profile status.",
        );
      }
      if (typeof payload.is_active !== "boolean") {
        throw new Error("The profile status response was incomplete.");
      }

      const updatedActiveState = payload.is_active;
      setProfiles((current) =>
        current.map((item) =>
          item.id === profile.id
            ? {
                ...item,
                is_active: updatedActiveState,
                updated_at:
                  typeof payload.updated_at === "string"
                    ? payload.updated_at
                    : item.updated_at,
              }
            : item,
        ),
      );
      setSelectedProfile((current) =>
        current?.id === profile.id
          ? {
              ...current,
              is_active: updatedActiveState,
              updated_at:
                typeof payload.updated_at === "string"
                  ? payload.updated_at
                  : current.updated_at,
            }
          : current,
      );
      await loadProfiles();
    } catch (statusError) {
      setError(
        statusError instanceof Error
          ? statusError.message
          : "Could not update profile status.",
      );
    } finally {
      setStatusUpdatingId(null);
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setAppliedSearch(search);
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f4f6f8] px-6">
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <span className="size-2.5 animate-pulse rounded-full bg-indigo-600 motion-reduce:animate-none" aria-hidden="true" />
          <p className="text-sm font-medium text-slate-600" role="status">
            Checking administrator session...
          </p>
        </div>
      </main>
    );
  }

  if (!admin) {
    return (
      <main className="relative isolate flex min-h-screen items-center justify-center overflow-hidden bg-[#f4f6f8] px-4 py-10 sm:px-6">
        <div className="pointer-events-none absolute -right-32 -top-40 -z-10 size-[30rem] rounded-full bg-indigo-100/70 blur-3xl" aria-hidden="true" />
        <section className="w-full max-w-md overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_28px_80px_-38px_rgba(32,45,74,0.3)]">
          <div className="h-1.5 bg-gradient-to-r from-indigo-800 via-indigo-600 to-sky-400" aria-hidden="true" />
          <div className="p-6 sm:p-9">
          <div className="mb-8 flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-2xl bg-indigo-50 text-indigo-800 ring-1 ring-indigo-100" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" className="size-5">
                <path d="M12 3 5 6v5c0 4.6 2.9 8.2 7 10 4.1-1.8 7-5.4 7-10V6l-7-3Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <div>
              <p className="text-sm font-semibold tracking-tight text-slate-900">HealthProfile</p>
              <p className="mt-0.5 text-xs font-medium text-indigo-700">Administrator portal</p>
            </div>
          </div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-700">Secure access</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            Administrator sign in
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            This sign-in uses a separate Django server-side session.
          </p>
          {error && (
            <p className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-800" role="alert">
              {error}
            </p>
          )}
          <form className="mt-7 space-y-5" onSubmit={submitLogin}>
            <label className="block text-sm font-semibold text-slate-700">
              Email
              <input
                autoComplete="username"
                className="mt-1.5 block min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm outline-none transition hover:border-slate-400 focus-visible:border-indigo-600 focus-visible:ring-4 focus-visible:ring-indigo-600/10 motion-reduce:transition-none"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              Password
              <input
                autoComplete="current-password"
                className="mt-1.5 block min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm outline-none transition hover:border-slate-400 focus-visible:border-indigo-600 focus-visible:ring-4 focus-visible:ring-indigo-600/10 motion-reduce:transition-none"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            <button
              className="mt-2 inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-[#293b72] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#202f5c] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/20 disabled:cursor-not-allowed disabled:opacity-55 motion-reduce:transition-none"
              disabled={busy}
              type="submit"
            >
              {busy ? "Signing in..." : "Sign in"}
            </button>
          </form>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f4f6f8] px-4 py-7 sm:px-6 sm:py-10 lg:py-12">
      <div className="mx-auto max-w-6xl">
        <header className="mb-7 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200/80 bg-white px-5 py-4 shadow-sm sm:mb-8 sm:px-7">
          <div className="flex items-center gap-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-indigo-50 text-indigo-800 ring-1 ring-indigo-100" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" className="size-5">
                <path d="M12 3 5 6v5c0 4.6 2.9 8.2 7 10 4.1-1.8 7-5.4 7-10V6l-7-3Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-700">HealthProfile · Admin</p>
            <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-950 sm:text-2xl">
              Profile management
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Signed in as {admin.email}
            </p>
            </div>
          </div>
          <button
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/15 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
            disabled={busy}
            onClick={logout}
            type="button"
          >
            {busy ? "Please wait..." : "Log out"}
          </button>
        </header>

        <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_20px_60px_-40px_rgba(32,45,74,0.3)]">
          <div className="border-b border-slate-100 bg-gradient-to-r from-indigo-50/70 via-white to-white px-5 py-5 sm:px-7">
            <p className="text-xs font-semibold uppercase tracking-[0.17em] text-indigo-700">Directory</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">Health profiles</h2>
            <p className="mt-1 text-sm text-slate-600">Search and review submitted profile details.</p>
          </div>
          <div className="p-5 sm:p-7">
          <form
            className="mb-6 grid gap-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 sm:grid-cols-[1fr_12rem_auto] sm:items-end sm:p-5"
            onSubmit={applyFilters}
          >
            <label className="text-sm font-semibold text-slate-700">
              Search name or email
              <input
                className="mt-1.5 block min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus-visible:border-indigo-600 focus-visible:ring-4 focus-visible:ring-indigo-600/10 motion-reduce:transition-none"
                onChange={(event) => setSearch(event.target.value)}
                value={search}
              />
            </label>
            <label className="text-sm font-semibold text-slate-700">
              Status
              <select
                className="mt-1.5 block min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus-visible:border-indigo-600 focus-visible:ring-4 focus-visible:ring-indigo-600/10 motion-reduce:transition-none"
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
              className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[#293b72] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#202f5c] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/20 motion-reduce:transition-none"
              type="submit"
            >
              Search
            </button>
          </form>

          {error && (
            <p className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-800" role="alert">
              {error}
            </p>
          )}
          {loadingProfiles ? (
            <div className="flex items-center justify-center gap-3 py-12 text-sm font-medium text-slate-600" role="status">
              <span className="size-2.5 animate-pulse rounded-full bg-indigo-600 motion-reduce:animate-none" aria-hidden="true" />
              Loading profiles...
            </div>
          ) : profiles.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 px-5 py-12 text-center">
              <span className="mx-auto grid size-11 place-items-center rounded-2xl bg-white text-slate-500 shadow-sm ring-1 ring-slate-200" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" className="size-5">
                  <path d="M4 20a8 8 0 0 1 16 0M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                </svg>
              </span>
              <p className="mt-3 text-sm font-semibold text-slate-800">No profiles found</p>
              <p className="mt-1 text-sm text-slate-500">No profiles match these filters.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {profiles.map((profile) => (
                <article
                  className="rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm sm:p-5 motion-reduce:transition-none"
                  key={profile.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <button
                        className="text-left font-semibold text-slate-950 underline decoration-transparent underline-offset-4 transition hover:text-indigo-800 hover:decoration-indigo-300 focus-visible:rounded focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/15 motion-reduce:transition-none"
                        onClick={() => setSelectedProfile(profile)}
                        type="button"
                      >
                        {profile.full_name}
                      </button>
                      <p className="mt-1 text-sm text-slate-500">
                        {profile.email}
                      </p>
                    </div>
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${profile.is_active ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200" : "bg-slate-100 text-slate-600 ring-1 ring-slate-200"}`}>
                      <span className={`size-1.5 rounded-full ${profile.is_active ? "bg-emerald-600" : "bg-slate-400"}`} aria-hidden="true" />
                      {profile.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                    <button
                      className="inline-flex min-h-10 items-center rounded-lg px-3 text-sm font-semibold text-indigo-800 transition hover:bg-indigo-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/15 motion-reduce:transition-none"
                      onClick={() => setSelectedProfile(profile)}
                      type="button"
                    >
                      View profile
                    </button>
                    <button
                      className={`inline-flex min-h-10 items-center justify-center rounded-xl border px-3.5 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-4 disabled:cursor-wait disabled:opacity-60 motion-reduce:transition-none ${
                        profile.is_active
                          ? "border-rose-200 text-rose-800 hover:bg-rose-50 focus-visible:ring-rose-700/15"
                          : "border-emerald-200 text-emerald-800 hover:bg-emerald-50 focus-visible:ring-emerald-700/15"
                      }`}
                      disabled={statusUpdatingId === profile.id}
                      onClick={() => void updateProfileStatus(profile)}
                      type="button"
                    >
                      {statusUpdatingId === profile.id
                        ? "Updating..."
                        : profile.is_active
                          ? "Deactivate"
                          : "Reactivate"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}

          <footer className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
            <p className="text-sm font-medium text-slate-600">
              {count} profile{count === 1 ? "" : "s"} · page {page}
            </p>
            <div className="flex w-full gap-2 sm:w-auto">
              <button
                className="inline-flex min-h-11 flex-1 items-center justify-center rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/15 disabled:cursor-not-allowed disabled:opacity-40 sm:flex-none motion-reduce:transition-none"
                disabled={!previous || loadingProfiles}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                type="button"
              >
                Previous
              </button>
              <button
                className="inline-flex min-h-11 flex-1 items-center justify-center rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/15 disabled:cursor-not-allowed disabled:opacity-40 sm:flex-none motion-reduce:transition-none"
                disabled={!next || loadingProfiles}
                onClick={() => setPage((current) => current + 1)}
                type="button"
              >
                Next
              </button>
            </div>
          </footer>
          </div>
        </section>
      </div>
      {selectedProfile && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/45 p-0 backdrop-blur-sm sm:items-center sm:p-5"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setSelectedProfile(null);
            }
          }}
        >
          <section
            aria-labelledby="profile-detail-title"
            aria-modal="true"
            className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl"
            role="dialog"
          >
            <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-100 bg-white/95 px-5 py-5 backdrop-blur sm:px-7">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.17em] text-indigo-700">
                  Profile details
                </p>
                <h2
                  className="mt-1 break-words text-xl font-semibold tracking-tight text-slate-950"
                  id="profile-detail-title"
                >
                  {selectedProfile.full_name}
                </h2>
                <p className="mt-1 break-all text-sm text-slate-500">
                  {selectedProfile.email}
                </p>
              </div>
              <button
                aria-label="Close profile details"
                className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-600 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/15 motion-reduce:transition-none"
                onClick={() => setSelectedProfile(null)}
                type="button"
              >
                <svg viewBox="0 0 24 24" fill="none" className="size-5" aria-hidden="true">
                  <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </button>
            </header>
            <div className="space-y-6 px-5 py-6 sm:px-7">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ${
                    selectedProfile.is_active
                      ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200"
                      : "bg-slate-100 text-slate-600 ring-1 ring-slate-200"
                  }`}
                >
                  <span
                    className={`size-1.5 rounded-full ${
                      selectedProfile.is_active ? "bg-emerald-600" : "bg-slate-400"
                    }`}
                    aria-hidden="true"
                  />
                  {selectedProfile.is_active ? "Active" : "Inactive"}
                </span>
                <span className="text-xs text-slate-500">
                  Profile #{selectedProfile.id} · User #{selectedProfile.user_id}
                </span>
              </div>
              <dl className="grid gap-4 sm:grid-cols-2">
                {[
                  ["Age range", selectedProfile.age_range || "Not specified"],
                  ["Contact preference", selectedProfile.contact_preference],
                  ["Wellness goals", selectedProfile.wellness_goals],
                  ["Allergies", selectedProfile.allergies],
                  [
                    "Emergency contact name",
                    selectedProfile.emergency_contact_name,
                  ],
                  [
                    "Emergency contact relationship",
                    selectedProfile.emergency_contact_relationship,
                  ],
                  [
                    "Emergency contact phone",
                    selectedProfile.emergency_contact_phone,
                  ],
                  ["Lifestyle notes", selectedProfile.lifestyle_notes],
                  ["Created", selectedProfile.created_at],
                  ["Last updated", selectedProfile.updated_at],
                ].map(([label, value]) => (
                  <div
                    className="min-w-0 rounded-2xl border border-slate-100 bg-slate-50/70 p-4"
                    key={label}
                  >
                    <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {label}
                    </dt>
                    <dd className="mt-1.5 whitespace-pre-wrap break-words text-sm leading-6 text-slate-800">
                      {value || "—"}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="flex flex-wrap justify-end gap-3 border-t border-slate-100 pt-5">
                <button
                  className={`inline-flex min-h-11 items-center justify-center rounded-xl border px-4 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-4 disabled:cursor-wait disabled:opacity-60 motion-reduce:transition-none ${
                    selectedProfile.is_active
                      ? "border-rose-200 text-rose-800 hover:bg-rose-50 focus-visible:ring-rose-700/15"
                      : "border-emerald-200 text-emerald-800 hover:bg-emerald-50 focus-visible:ring-emerald-700/15"
                  }`}
                  disabled={statusUpdatingId === selectedProfile.id}
                  onClick={() => void updateProfileStatus(selectedProfile)}
                  type="button"
                >
                  {statusUpdatingId === selectedProfile.id
                    ? "Updating..."
                    : selectedProfile.is_active
                      ? "Deactivate profile"
                      : "Reactivate profile"}
                </button>
                <button
                  className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[#293b72] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#202f5c] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-700/20 motion-reduce:transition-none"
                  onClick={() => setSelectedProfile(null)}
                  type="button"
                >
                  Close
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
