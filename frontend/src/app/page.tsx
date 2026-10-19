"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import ProfileDashboard from "../components/ProfileDashboard";

type AuthUser = {
  id: number;
  email: string;
  full_name: string;
  role: string;
};

type ApiResponse = {
  detail?: string;
  access_token?: string;
  expires_in?: number;
  user?: AuthUser;
  [field: string]: unknown;
};

function getErrorMessage(payload: ApiResponse) {
  if (payload.detail) {
    return payload.detail;
  }

  for (const [field, value] of Object.entries(payload)) {
    if (Array.isArray(value) && value.length > 0) {
      return `${field}: ${value.join(" ")}`;
    }
  }

  return "The request could not be completed.";
}

export default function Home() {
  const [mode, setMode] = useState<"signup" | "login">("signup");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [csrfToken, setCsrfToken] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function restoreSession() {
      try {
        const csrfResponse = await fetch("/api/auth/csrf/", {
          cache: "no-store",
        });
        const csrfPayload = (await csrfResponse.json()) as ApiResponse & {
          csrf_token?: string;
        };
        if (!csrfResponse.ok || !csrfPayload.csrf_token) {
          throw new Error(getErrorMessage(csrfPayload));
        }
        if (active) {
          setCsrfToken(csrfPayload.csrf_token);
        }

        const response = await fetch("/api/auth/session/refresh/", {
          method: "POST",
          headers: { "x-csrftoken": csrfPayload.csrf_token },
          cache: "no-store",
        });
        const payload = (await response.json()) as ApiResponse & {
          csrf_token?: string;
        };
        if (response.status === 401) {
          return;
        }
        if (!response.ok) {
          throw new Error(getErrorMessage(payload));
        }
        if (active && payload.access_token && payload.user) {
          setAccessToken(payload.access_token);
          setUser(payload.user);
          setCsrfToken(payload.csrf_token ?? csrfPayload.csrf_token);
        }
      } catch (restoreError) {
        if (active) {
          setError(
            restoreError instanceof Error
              ? restoreError.message
              : "Could not check your sign-in session.",
          );
        }
      } finally {
        if (active) {
          setAuthLoading(false);
        }
      }
    }

    void restoreSession();
    return () => {
      active = false;
    };
  }, []);

  const refreshAccessToken = useCallback(async () => {
    if (!csrfToken) {
      return null;
    }
    try {
      const response = await fetch("/api/auth/session/refresh/", {
        method: "POST",
        headers: { "x-csrftoken": csrfToken },
        cache: "no-store",
      });
      const payload = (await response.json()) as ApiResponse & {
        csrf_token?: string;
      };
      if (!response.ok || !payload.access_token || !payload.user) {
        return null;
      }
      setAccessToken(payload.access_token);
      setUser(payload.user);
      setCsrfToken(payload.csrf_token ?? csrfToken);
      return payload.access_token;
    } catch {
      return null;
    }
  }, [csrfToken]);

  const logout = useCallback(async () => {
    if (!csrfToken) {
      return false;
    }
    try {
      const response = await fetch("/api/auth/session/logout/", {
        method: "POST",
        headers: { "x-csrftoken": csrfToken },
      });
      if (!response.ok) {
        setError("Could not end the server session. Please try again.");
        return false;
      }
      setAccessToken(null);
      setUser(null);
      setMode("login");
      setMessage("You have been signed out.");
      setError("");
      return true;
    } catch {
      setError("Could not reach the session service. Please try again.");
      return false;
    }
  }, [csrfToken]);

  const handleSessionExpired = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setMode("login");
    setMessage("Your session expired. Sign in again to continue.");
    setError("");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(`/api/auth/${mode}/`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrftoken": csrfToken,
        },
        body: JSON.stringify({
          ...(mode === "signup" ? { full_name: fullName } : {}),
          email,
          password,
        }),
      });
      const payload = (await response.json()) as ApiResponse;

      if (!response.ok) {
        setError(getErrorMessage(payload));
        return;
      }

      setPassword("");
      if (mode === "signup") {
        setMode("login");
        setMessage("Account created. Sign in to continue.");
      } else if (payload.access_token && payload.user) {
        setAccessToken(payload.access_token);
        setUser(payload.user);
        if (typeof payload.csrf_token === "string") {
          setCsrfToken(payload.csrf_token);
        }
      } else {
        setError("The sign-in response was incomplete. Please try again.");
      }
    } catch {
      setError("The authentication service could not be reached.");
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f4f8f7] px-6">
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <span className="size-2.5 animate-pulse rounded-full bg-teal-600 motion-reduce:animate-none" aria-hidden="true" />
          <p className="text-sm font-medium text-slate-600" role="status">
            Checking your sign-in session...
          </p>
        </div>
      </main>
    );
  }

  if (accessToken && user) {
    return (
      <ProfileDashboard
        accessToken={accessToken}
        onLogout={logout}
        onSessionExpired={handleSessionExpired}
        refreshAccessToken={refreshAccessToken}
        user={user}
      />
    );
  }

  return (
    <main className="relative isolate flex min-h-screen items-center justify-center overflow-hidden bg-[#f4f8f7] px-4 py-8 sm:px-6 sm:py-12">
      <div className="pointer-events-none absolute -left-36 top-[-9rem] -z-10 size-[28rem] rounded-full bg-teal-100/70 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-48 -right-32 -z-10 size-[32rem] rounded-full bg-cyan-100/60 blur-3xl" aria-hidden="true" />
      <section className="grid w-full max-w-5xl overflow-hidden rounded-[2rem] border border-slate-200/80 bg-white shadow-[0_28px_80px_-36px_rgba(15,57,61,0.28)] md:min-h-[38rem] md:grid-cols-[0.9fr_1.1fr]">
        <aside className="relative hidden flex-col justify-between overflow-hidden bg-[#103f43] p-10 text-white md:flex lg:p-12">
          <div className="pointer-events-none absolute -right-24 top-24 size-72 rounded-full border border-white/10" aria-hidden="true" />
          <div className="pointer-events-none absolute -right-8 top-40 size-40 rounded-full border border-white/10" aria-hidden="true" />
          <div className="relative">
            <div className="flex items-center gap-3">
              <span className="grid size-11 place-items-center rounded-2xl bg-white/10 ring-1 ring-white/20" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" className="size-6 text-teal-200">
                  <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
                </svg>
              </span>
              <span className="text-lg font-semibold tracking-tight">HealthProfile</span>
            </div>
            <p className="mt-16 text-xs font-semibold uppercase tracking-[0.22em] text-teal-200">
              Your wellness, in focus
            </p>
            <h2 className="mt-4 max-w-sm text-4xl font-semibold leading-tight tracking-tight lg:text-[2.75rem]">
              A clearer picture of your wellbeing.
            </h2>
            <p className="mt-5 max-w-sm text-sm leading-7 text-teal-50/75">
              Keep your health preferences and personal wellness goals together in one thoughtful space.
            </p>
          </div>
          <p className="relative text-xs text-teal-100/60">
            A personal space for your wellness information.
          </p>
        </aside>

        <div className="flex flex-col justify-center px-6 py-9 sm:px-10 sm:py-12 lg:px-14">
          <div className="mb-8 flex items-center gap-3 md:hidden">
            <span className="grid size-10 place-items-center rounded-xl bg-teal-50 text-teal-800 ring-1 ring-teal-100" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" className="size-5">
                <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
              </svg>
            </span>
            <span className="text-base font-semibold tracking-tight text-slate-900">HealthProfile</span>
          </div>

          <div>
            <p className="text-sm font-semibold text-teal-800">
              {mode === "signup" ? "Get started" : "Welcome back"}
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950 sm:text-[2.1rem]">
              {mode === "signup" ? "Create your account" : "Sign in to continue"}
            </h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {mode === "signup"
                ? "Create a standard-user account."
                : "Sign in to your standard-user account."}
            </p>
          </div>

          <form className="mt-8 space-y-5" onSubmit={submit}>
            {mode === "signup" && (
              <label className="block text-sm font-medium text-slate-700">
                Full name
                <input
                  autoComplete="name"
                  className="mt-2 block min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus-visible:border-teal-700 focus-visible:ring-4 focus-visible:ring-teal-700/10 motion-reduce:transition-none"
                  maxLength={150}
                  onChange={(event) => setFullName(event.target.value)}
                  required
                  value={fullName}
                />
              </label>
            )}
            <label className="block text-sm font-medium text-slate-700">
              Email
              <input
                autoComplete="email"
                className="mt-2 block min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus-visible:border-teal-700 focus-visible:ring-4 focus-visible:ring-teal-700/10 motion-reduce:transition-none"
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Password
              <input
                autoComplete={
                  mode === "signup" ? "new-password" : "current-password"
                }
                className="mt-2 block min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-400 focus-visible:border-teal-700 focus-visible:ring-4 focus-visible:ring-teal-700/10 motion-reduce:transition-none"
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            {error && (
              <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-800" role="alert">
                {error}
              </p>
            )}
            {message && (
              <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-800" role="status">
                {message}
              </p>
            )}
            <button
              className="flex min-h-12 w-full items-center justify-center rounded-xl bg-[#14575a] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#10474a] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/25 disabled:cursor-not-allowed disabled:opacity-55 motion-reduce:transition-none"
              disabled={busy}
              type="submit"
            >
              {busy
                ? "Please wait..."
                : mode === "signup"
                  ? "Create account"
                  : "Sign in"}
            </button>
          </form>

          <div className="mt-6 flex flex-col items-start gap-4 border-t border-slate-100 pt-5 sm:flex-row sm:items-center sm:justify-between">
            <button
              className="min-h-10 text-left text-sm font-medium text-teal-800 underline decoration-teal-300 underline-offset-4 transition hover:text-teal-950 focus-visible:rounded focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/15 motion-reduce:transition-none"
              onClick={() => {
                setMode(mode === "signup" ? "login" : "signup");
                setError("");
                setMessage("");
              }}
              type="button"
            >
              {mode === "signup"
                ? "Already have an account? Sign in"
                : "Need an account? Sign up"}
            </button>
            <a
              className="min-h-10 inline-flex items-center text-sm font-medium text-slate-500 transition hover:text-slate-800 focus-visible:rounded focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/15 motion-reduce:transition-none"
              href="/admin"
            >
              Administrator sign in
            </a>
          </div>
        </div>
      </section>
    </main>
  );
}
