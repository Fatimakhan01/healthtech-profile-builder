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
      <main className="flex min-h-screen items-center justify-center px-6">
        <p className="text-sm text-zinc-600" role="status">
          Checking your sign-in session...
        </p>
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
    <main className="mx-auto flex min-h-screen w-full max-w-xl items-center px-6 py-12">
      <section className="w-full rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm">
        <h1 className="text-3xl font-semibold tracking-tight">HealthProfile</h1>
        <p className="mt-2 text-sm text-zinc-600">
          {mode === "signup"
            ? "Create a standard-user account."
            : "Sign in to your standard-user account."}
        </p>

        <form className="mt-8 space-y-5" onSubmit={submit}>
          {mode === "signup" && (
            <label className="block text-sm font-medium">
              Full name
              <input
                autoComplete="name"
                className="mt-2 block w-full rounded-lg border border-zinc-300 px-3 py-2"
                maxLength={150}
                onChange={(event) => setFullName(event.target.value)}
                required
                value={fullName}
              />
            </label>
          )}
          <label className="block text-sm font-medium">
            Email
            <input
              autoComplete="email"
              className="mt-2 block w-full rounded-lg border border-zinc-300 px-3 py-2"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input
              autoComplete={
                mode === "signup" ? "new-password" : "current-password"
              }
              className="mt-2 block w-full rounded-lg border border-zinc-300 px-3 py-2"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          {error && (
            <p className="text-sm text-red-700" role="alert">
              {error}
            </p>
          )}
          {message && (
            <p className="text-sm text-green-800" role="status">
              {message}
            </p>
          )}
          <button
            className="w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
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

        <button
          className="mt-5 text-sm text-zinc-700 underline underline-offset-4"
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
      </section>
    </main>
  );
}
