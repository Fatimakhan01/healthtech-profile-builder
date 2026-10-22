"use client";

import { FormEvent, useEffect, useState } from "react";

type AuthUser = {
  id: number;
  email: string;
  full_name: string;
  role: string;
};

type HealthProfile = {
  full_name: string;
  age_range: string;
  contact_preference: string;
  wellness_goals: string;
  allergies: string;
  emergency_contact_name: string;
  emergency_contact_relationship: string;
  emergency_contact_phone: string;
  lifestyle_notes: string;
};

type ApiError = {
  detail?: string;
  [field: string]: unknown;
};

const emptyProfile: HealthProfile = {
  full_name: "",
  age_range: "",
  contact_preference: "email",
  wellness_goals: "",
  allergies: "",
  emergency_contact_name: "",
  emergency_contact_relationship: "",
  emergency_contact_phone: "",
  lifestyle_notes: "",
};

function errorMessage(payload: ApiError) {
  if (typeof payload.detail === "string") {
    return payload.detail;
  }

  const messages = Object.entries(payload).flatMap(([field, value]) => {
    const errors = Array.isArray(value) ? value : [value];
    return errors
      .filter((error): error is string => typeof error === "string")
      .map((error) => `${field}: ${error}`);
  });
  return messages.length ? messages.join(" ") : "The request could not be completed.";
}

type Props = {
  user: AuthUser;
  accessToken: string;
  onLogout: () => Promise<boolean>;
  onSessionExpired: () => void;
  refreshAccessToken: () => Promise<string | null>;
};

export default function ProfileDashboard({
  user,
  accessToken,
  onLogout,
  onSessionExpired,
  refreshAccessToken,
}: Props) {
  const [profile, setProfile] = useState<HealthProfile>(emptyProfile);
  const [loading, setLoading] = useState(true);
  const [profileExists, setProfileExists] = useState(false);
  const [profileLoadFailed, setProfileLoadFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    let active = true;

    async function loadProfile() {
      setLoading(true);
      setProfileLoadFailed(false);
      setError("");
      try {
        let response = await fetch("/api/profile/me/", {
          headers: { authorization: `Bearer ${accessToken}` },
          cache: "no-store",
        });
        if (response.status === 401) {
          const refreshedToken = await refreshAccessToken();
          if (!refreshedToken) {
            onSessionExpired();
            return;
          }
          response = await fetch("/api/profile/me/", {
            headers: { authorization: `Bearer ${refreshedToken}` },
            cache: "no-store",
          });
        }
        const payload = (await response.json()) as HealthProfile | ApiError;

        if (response.status === 401) {
          onSessionExpired();
          return;
        }
        if (response.status === 404) {
          if (active) {
            setProfile(emptyProfile);
            setProfileExists(false);
          }
          return;
        }
        if (!response.ok) {
          throw new Error(errorMessage(payload as ApiError));
        }
        if (active) {
          setProfile(payload as HealthProfile);
          setProfileExists(true);
        }
      } catch (requestError) {
        if (active) {
          setProfileLoadFailed(true);
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Could not load your profile.",
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadProfile();
    return () => {
      active = false;
    };
  }, [accessToken, onSessionExpired, refreshAccessToken, reloadKey]);

  function updateField(field: keyof HealthProfile, value: string) {
    setProfile((current) => ({ ...current, [field]: value }));
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccessMessage("");

    try {
      const requestOptions: RequestInit = {
        method: profileExists ? "PATCH" : "POST",
        headers: {
          authorization: `Bearer ${accessToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          full_name: profile.full_name,
          age_range: profile.age_range,
          contact_preference: profile.contact_preference,
          wellness_goals: profile.wellness_goals,
          allergies: profile.allergies,
          emergency_contact_name: profile.emergency_contact_name,
          emergency_contact_relationship: profile.emergency_contact_relationship,
          emergency_contact_phone: profile.emergency_contact_phone,
          lifestyle_notes: profile.lifestyle_notes,
        }),
      };
      let response = await fetch("/api/profile/me/", requestOptions);
      if (response.status === 401) {
        const refreshedToken = await refreshAccessToken();
        if (!refreshedToken) {
          onSessionExpired();
          return;
        }
        requestOptions.headers = {
          authorization: `Bearer ${refreshedToken}`,
          "content-type": "application/json",
        };
        response = await fetch("/api/profile/me/", requestOptions);
      }
      const payload = (await response.json()) as HealthProfile | ApiError;

      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (response.status === 404 && profileExists) {
        setProfileExists(false);
        setError("Your profile no longer exists. Submit again to create it.");
        return;
      }
      if (response.status === 409) {
        setProfileLoadFailed(true);
        setError("A profile already exists. Reload your profile to continue.");
        return;
      }
      if (!response.ok) {
        setError(errorMessage(payload as ApiError));
        return;
      }

      setProfile(payload as HealthProfile);
      setProfileExists(true);
      setSuccessMessage(
        profileExists
          ? "Changes have been saved successfully."
          : "Your profile has been created.",
      );
    } catch {
      setError("Could not reach the profile service. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteProfile() {
    if (!profileExists || !window.confirm("Delete your health profile? Your account will remain active.")) {
      return;
    }

    setDeleting(true);
    setError("");
    setSuccessMessage("");
    try {
      const requestOptions: RequestInit = {
        method: "DELETE",
        headers: { authorization: `Bearer ${accessToken}` },
      };
      let response = await fetch("/api/profile/me/", requestOptions);
      if (response.status === 401) {
        const refreshedToken = await refreshAccessToken();
        if (!refreshedToken) {
          onSessionExpired();
          return;
        }
        requestOptions.headers = { authorization: `Bearer ${refreshedToken}` };
        response = await fetch("/api/profile/me/", requestOptions);
      }

      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (response.status === 404) {
        setProfile(emptyProfile);
        setProfileExists(false);
        setSuccessMessage("Your profile was already deleted. Your account remains active.");
        return;
      }
      if (!response.ok) {
        const payload = (await response.json()) as ApiError;
        setError(errorMessage(payload));
        return;
      }

      setProfile(emptyProfile);
      setProfileExists(false);
      setSuccessMessage("Your profile was deleted. Your account remains active.");
    } catch {
      setError("Could not reach the profile service. Please try again.");
    } finally {
      setDeleting(false);
    }
  }

  async function logout() {
    setLoggingOut(true);
    setError("");
    setSuccessMessage("");
    try {
      const loggedOut = await onLogout();
      if (!loggedOut) {
        setError("Could not end your session. Please try logging out again.");
      }
    } finally {
      setLoggingOut(false);
    }
  }

  const inputClass =
    "mt-1.5 block min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition hover:border-slate-400 focus-visible:border-teal-700 focus-visible:ring-4 focus-visible:ring-teal-700/10 motion-reduce:transition-none";
  const labelClass = "block text-sm font-semibold text-slate-700";

  return (
    <main className="min-h-screen bg-[#f4f8f7] px-4 py-7 sm:px-6 sm:py-10 lg:py-12">
      <div className="mx-auto max-w-4xl">
        <header className="mb-7 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200/80 bg-white px-5 py-4 shadow-sm sm:mb-8 sm:px-7">
          <div className="flex items-center gap-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-teal-50 text-teal-800 ring-1 ring-teal-100" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" className="size-6">
                <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
              </svg>
            </span>
            <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-800">HealthProfile</p>
            <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-950 sm:text-2xl">
              Your health profile
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Signed in as {user.email}
            </p>
            </div>
          </div>
          <button
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/15 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
            disabled={loggingOut}
            onClick={logout}
            type="button"
          >
            {loggingOut ? "Signing out..." : "Log out"}
          </button>
        </header>

        <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_20px_60px_-40px_rgba(15,57,61,0.35)]">
          <div className="border-b border-slate-100 bg-gradient-to-r from-teal-50/80 via-white to-white px-5 py-5 sm:px-8">
            <p className="text-xs font-semibold uppercase tracking-[0.17em] text-teal-800">Your details</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">Personal and wellness information</h2>
            <p className="mt-1 text-sm text-slate-600">Keep the details you choose to share up to date.</p>
          </div>
          <div className="p-5 sm:p-8">
          {loading ? (
            <div className="flex items-center gap-3 py-8 text-sm font-medium text-slate-600" role="status">
              <span className="size-2.5 animate-pulse rounded-full bg-teal-600 motion-reduce:animate-none" aria-hidden="true" />
              Loading your profile...
            </div>
          ) : profileLoadFailed ? (
            <div className="py-4">
              <p
                className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-800"
                role="alert"
              >
                {error}
              </p>
              <button
                className="mt-4 inline-flex min-h-11 items-center justify-center rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/15 motion-reduce:transition-none"
                onClick={() => setReloadKey((current) => current + 1)}
                type="button"
              >
                Try again
              </button>
            </div>
          ) : (
            <form className="space-y-6" onSubmit={saveProfile}>
              <div>
                <p className="text-sm leading-6 text-slate-600">
                  {profileExists
                    ? "Only share information you are comfortable providing."
                    : "You do not have a profile yet. Complete the fields below to create one. Your account remains active."}
                </p>
              </div>

              {error && (
                <p
                  className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-800"
                  role="alert"
                >
                  {error}
                </p>
              )}
              {successMessage && (
                <p
                  className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-800"
                  role="status"
                >
                  {successMessage}
                </p>
              )}

              <div className="grid gap-5 sm:grid-cols-2">
                <label className={labelClass}>
                  Full name
                  <input
                    className={inputClass}
                    maxLength={150}
                    onChange={(event) =>
                      updateField("full_name", event.target.value)
                    }
                    required
                    value={profile.full_name}
                  />
                </label>
                <label className={labelClass}>
                  Age range
                  <select
                    className={inputClass}
                    onChange={(event) =>
                      updateField("age_range", event.target.value)
                    }
                    value={profile.age_range}
                  >
                    <option value="">Not specified</option>
                    <option value="under_18">Under 18</option>
                    <option value="18_24">18-24</option>
                    <option value="25_34">25-34</option>
                    <option value="35_44">35-44</option>
                    <option value="45_54">45-54</option>
                    <option value="55_64">55-64</option>
                    <option value="65_plus">65 and over</option>
                    <option value="not_say">Prefer not to say</option>
                  </select>
                </label>
                <label className={labelClass}>
                  Contact preference
                  <select
                    className={inputClass}
                    onChange={(event) =>
                      updateField("contact_preference", event.target.value)
                    }
                    value={profile.contact_preference}
                  >
                    <option value="email">Email</option>
                    <option value="phone">Phone</option>
                    <option value="none">No preference</option>
                  </select>
                </label>
                <label className={labelClass}>
                  Wellness goals
                  <textarea
                    className={inputClass}
                    maxLength={1000}
                    onChange={(event) =>
                      updateField("wellness_goals", event.target.value)
                    }
                    rows={3}
                    value={profile.wellness_goals}
                  />
                </label>
                <label className={labelClass}>
                  Allergies (optional)
                  <textarea
                    className={inputClass}
                    maxLength={1000}
                    onChange={(event) =>
                      updateField("allergies", event.target.value)
                    }
                    rows={3}
                    value={profile.allergies}
                  />
                </label>
                <label className={labelClass}>
                  Lifestyle notes (optional)
                  <textarea
                    className={inputClass}
                    maxLength={1000}
                    onChange={(event) =>
                      updateField("lifestyle_notes", event.target.value)
                    }
                    rows={3}
                    value={profile.lifestyle_notes}
                  />
                </label>
              </div>

              <fieldset className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 sm:p-5">
                <legend className="px-2 text-sm font-semibold text-slate-800">
                  Emergency contact (optional)
                </legend>
                <div className="grid gap-5 sm:grid-cols-3">
                  <label className={labelClass}>
                    Name
                    <input
                      className={inputClass}
                      maxLength={150}
                      onChange={(event) =>
                        updateField("emergency_contact_name", event.target.value)
                      }
                      value={profile.emergency_contact_name}
                    />
                  </label>
                  <label className={labelClass}>
                    Relationship
                    <input
                      className={inputClass}
                      maxLength={50}
                      onChange={(event) =>
                        updateField(
                          "emergency_contact_relationship",
                          event.target.value,
                        )
                      }
                      value={profile.emergency_contact_relationship}
                    />
                  </label>
                  <label className={labelClass}>
                    Phone
                    <input
                      className={inputClass}
                      maxLength={20}
                      onChange={(event) =>
                        updateField(
                          "emergency_contact_phone",
                          event.target.value,
                        )
                      }
                      type="tel"
                      value={profile.emergency_contact_phone}
                    />
                  </label>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-500">
                  Enter all three details or leave all three blank.
                </p>
              </fieldset>

              <div className="flex flex-wrap items-center gap-4 border-t border-slate-100 pt-5">
                <button
                  className="inline-flex min-h-12 items-center justify-center rounded-xl bg-[#14575a] px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#10474a] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/25 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
                  disabled={saving || deleting}
                  type="submit"
                >
                  {saving
                    ? profileExists
                      ? "Saving..."
                      : "Creating..."
                    : profileExists
                      ? "Save changes"
                      : "Create profile"}
                </button>
                {profileExists && (
                  <button
                    className="inline-flex min-h-12 items-center justify-center rounded-xl border border-rose-300 bg-white px-6 py-3 text-sm font-semibold text-rose-700 shadow-sm transition hover:bg-rose-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-rose-700/15 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
                    disabled={saving || deleting}
                    onClick={deleteProfile}
                    type="button"
                  >
                    {deleting ? "Deleting..." : "Delete profile"}
                  </button>
                )}
              </div>
            </form>
          )}
          {!loading && !profileLoadFailed && error && (
            <button
              className="mt-4 min-h-10 text-sm font-semibold text-teal-800 underline decoration-teal-300 underline-offset-4 focus-visible:rounded focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/15"
              onClick={logout}
              type="button"
            >
              Return to sign in
            </button>
          )}
          </div>
        </section>
      </div>
    </main>
  );
}
