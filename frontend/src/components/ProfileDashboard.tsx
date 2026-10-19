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
  const [profileLoadFailed, setProfileLoadFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState("");
  const [saveSucceeded, setSaveSucceeded] = useState(false);

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
        if (!response.ok) {
          throw new Error(errorMessage(payload as ApiError));
        }
        if (active) {
          setProfile(payload as HealthProfile);
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
    setSaveSucceeded(false);

    try {
      const requestOptions: RequestInit = {
        method: "PATCH",
        headers: {
          authorization: `Bearer ${accessToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify(profile),
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
      if (!response.ok) {
        setError(errorMessage(payload as ApiError));
        return;
      }

      setProfile(payload as HealthProfile);
      setSaveSucceeded(true);
    } catch {
      setError("Could not reach the profile service. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function logout() {
    setLoggingOut(true);
    setError("");
    setSaveSucceeded(false);
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
    "mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm";
  const labelClass = "block text-sm font-medium text-zinc-800";

  return (
    <main className="min-h-screen bg-zinc-50 px-4 py-8 sm:px-6 lg:py-12">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-zinc-500">HealthProfile</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950 sm:text-3xl">
              Your health profile
            </h1>
            <p className="mt-2 text-sm text-zinc-600">
              Signed in as {user.email}
            </p>
          </div>
          <button
            className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-100 disabled:opacity-50"
            disabled={loggingOut}
            onClick={logout}
            type="button"
          >
            {loggingOut ? "Signing out..." : "Log out"}
          </button>
        </header>

        <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-8">
          {loading ? (
            <p className="py-8 text-sm text-zinc-600" role="status">
              Loading your profile...
            </p>
          ) : profileLoadFailed ? (
            <div className="py-4">
              <p
                className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800"
                role="alert"
              >
                {error}
              </p>
              <button
                className="mt-4 rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-100"
                onClick={() => setReloadKey((current) => current + 1)}
                type="button"
              >
                Try again
              </button>
            </div>
          ) : (
            <form className="space-y-6" onSubmit={saveProfile}>
              <div>
                <h2 className="text-lg font-semibold text-zinc-950">
                  Personal and wellness details
                </h2>
                <p className="mt-1 text-sm text-zinc-600">
                  Only share information you are comfortable providing.
                </p>
              </div>

              {error && (
                <p
                  className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800"
                  role="alert"
                >
                  {error}
                </p>
              )}
              {saveSucceeded && (
                <p
                  className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-800"
                  role="status"
                >
                  Changes have been saved successfully.
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

              <fieldset className="rounded-xl border border-zinc-200 p-4 sm:p-5">
                <legend className="px-2 text-sm font-semibold text-zinc-900">
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
                <p className="mt-3 text-xs text-zinc-500">
                  Enter all three details or leave all three blank.
                </p>
              </fieldset>

              <div className="flex flex-wrap items-center gap-4 border-t border-zinc-100 pt-5">
                <button
                  className="rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={saving}
                  type="submit"
                >
                  {saving ? "Saving..." : "Save changes"}
                </button>
                
              </div>
            </form>
          )}
          {!loading && !profileLoadFailed && error && (
            <button
              className="mt-4 text-sm font-medium text-zinc-700 underline"
              onClick={logout}
              type="button"
            >
              Return to sign in
            </button>
          )}
        </section>
      </div>
    </main>
  );
}
