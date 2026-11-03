"use client";

import { FormEvent, useState } from "react";

type PredictionInput = {
  days_ahead: string;
  previous_no_shows: string;
  sms_reminder: "yes" | "no";
  weekday: string;
};

type PredictionResponse = {
  model_version: string;
  display_version: string;
  predicted_label: "no_show" | "attended";
  probability_no_show: number;
  notice: string;
};

type ApiError = {
  detail?: string;
  [field: string]: unknown;
};

type Props = {
  accessToken: string;
  onSessionExpired: () => void;
  refreshAccessToken: () => Promise<string | null>;
};

const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function getErrorMessage(payload: ApiError) {
  if (typeof payload.detail === "string") {
    return payload.detail;
  }

  const messages = Object.entries(payload).flatMap(([field, value]) => {
    const errors = Array.isArray(value) ? value : [value];
    return errors
      .filter((error): error is string => typeof error === "string")
      .map((error) => `${field}: ${error}`);
  });
  return messages.length
    ? messages.join(" ")
    : "The prediction request could not be completed.";
}

function isPredictionResponse(value: unknown): value is PredictionResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const response = value as Partial<PredictionResponse>;
  return (
    typeof response.model_version === "string" &&
    typeof response.display_version === "string" &&
    (response.predicted_label === "no_show" ||
      response.predicted_label === "attended") &&
    typeof response.probability_no_show === "number" &&
    Number.isFinite(response.probability_no_show) &&
    response.probability_no_show >= 0 &&
    response.probability_no_show <= 1 &&
    typeof response.notice === "string"
  );
}

export default function NoShowPrediction({
  accessToken,
  onSessionExpired,
  refreshAccessToken,
}: Props) {
  const [input, setInput] = useState<PredictionInput>({
    days_ahead: "14",
    previous_no_shows: "1",
    sms_reminder: "yes",
    weekday: "Wednesday",
  });
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const inputClass =
    "mt-1.5 block min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition hover:border-slate-400 focus-visible:border-teal-700 focus-visible:ring-4 focus-visible:ring-teal-700/10 motion-reduce:transition-none";
  const labelClass = "block text-sm font-semibold text-slate-700";

  function updateNumber(
    field: "days_ahead" | "previous_no_shows",
    value: string,
  ) {
    setInput((current) => ({ ...current, [field]: value }));
  }

  async function submitPrediction(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setError("");
    setResult(null);
    const daysAhead =
      input.days_ahead.trim() === "" ? NaN : Number(input.days_ahead);
    const previousNoShows =
      input.previous_no_shows.trim() === ""
        ? NaN
        : Number(input.previous_no_shows);

    if (
      !Number.isInteger(daysAhead) ||
      daysAhead < 0 ||
      daysAhead > 60 ||
      !Number.isInteger(previousNoShows) ||
      previousNoShows < 0 ||
      previousNoShows > 5 ||
      !WEEKDAYS.includes(input.weekday)
    ) {
      setError("Enter valid values for each prediction field.");
      return;
    }

    const predictionInput = {
      ...input,
      days_ahead: daysAhead,
      previous_no_shows: previousNoShows,
    };
    setLoading(true);
    try {
      const requestOptions: RequestInit = {
        method: "POST",
        headers: {
          authorization: `Bearer ${accessToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify(predictionInput),
        cache: "no-store",
      };
      let response = await fetch("/api/predictions/no-show/", requestOptions);
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
        response = await fetch("/api/predictions/no-show/", requestOptions);
      }

      const payload = (await response.json()) as
        | PredictionResponse
        | ApiError;
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (!response.ok) {
        throw new Error(getErrorMessage(payload as ApiError));
      }
      if (!isPredictionResponse(payload)) {
        throw new Error("The prediction service returned an invalid response.");
      }
      setResult(payload);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not reach the prediction service. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      aria-labelledby="no-show-prediction-title"
      className="mt-7 overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_20px_60px_-40px_rgba(15,57,61,0.35)]"
    >
      <div className="border-b border-slate-100 bg-gradient-to-r from-teal-50/80 via-white to-white px-5 py-5 sm:px-8">
        <p className="text-xs font-semibold uppercase tracking-[0.17em] text-teal-800">
          Educational tool
        </p>
        <h2
          className="mt-1 text-lg font-semibold tracking-tight text-slate-900"
          id="no-show-prediction-title"
        >
          No-Show Prediction
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Explore how the synthetic model responds to example inputs. This does
          not book or represent a real appointment.
        </p>
      </div>
      <div className="p-5 sm:p-8">
        <form className="space-y-5" onSubmit={submitPrediction}>
          <div className="grid gap-5 sm:grid-cols-2">
            <label className={labelClass}>
              Days ahead
              <input
                className={inputClass}
                max={60}
                min={0}
                onChange={(event) =>
                  updateNumber("days_ahead", event.target.value)
                }
                required
                step={1}
                type="number"
                value={input.days_ahead}
              />
            </label>
            <label className={labelClass}>
              Previous no-shows
              <input
                className={inputClass}
                max={5}
                min={0}
                onChange={(event) =>
                  updateNumber("previous_no_shows", event.target.value)
                }
                required
                step={1}
                type="number"
                value={input.previous_no_shows}
              />
            </label>
            <label className={labelClass}>
              SMS reminder
              <select
                className={inputClass}
                onChange={(event) =>
                  setInput((current) => ({
                    ...current,
                    sms_reminder: event.target.value as "yes" | "no",
                  }))
                }
                value={input.sms_reminder}
              >
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </label>
            <label className={labelClass}>
              Weekday
              <select
                className={inputClass}
                onChange={(event) =>
                  setInput((current) => ({
                    ...current,
                    weekday: event.target.value,
                  }))
                }
                value={input.weekday}
              >
                {WEEKDAYS.map((weekday) => (
                  <option key={weekday} value={weekday}>
                    {weekday}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {error && (
            <div>
              <p
                className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-800"
                role="alert"
              >
                {error}
              </p>
              {!loading && (
                <button
                  className="mt-3 min-h-10 text-sm font-semibold text-teal-800 underline decoration-teal-300 underline-offset-4 focus-visible:rounded focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/15"
                  onClick={() => void submitPrediction()}
                  type="button"
                >
                  Retry prediction
                </button>
              )}
            </div>
          )}

          <button
            className="inline-flex min-h-12 items-center justify-center rounded-xl bg-[#14575a] px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#10474a] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-teal-700/25 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
            disabled={loading}
            type="submit"
          >
            {loading ? "Running prediction..." : "Get prediction"}
          </button>
          {loading && (
            <p className="text-sm font-medium text-slate-600" role="status">
              Requesting a prediction from the synthetic model...
            </p>
          )}
        </form>

        {result && (
          <div
            aria-live="polite"
            className="mt-6 rounded-2xl border border-teal-100 bg-teal-50/60 p-5"
          >
            <h3 className="text-base font-semibold text-slate-900">
              Prediction result
            </h3>
            <dl className="mt-4 grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Predicted label
                </dt>
                <dd className="mt-1 text-sm font-semibold text-slate-900">
                  {result.predicted_label.replace("_", " ")}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  No-show probability
                </dt>
                <dd className="mt-1 text-sm font-semibold text-slate-900">
                  {(result.probability_no_show * 100).toFixed(1)}%
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Model version
                </dt>
                <dd className="mt-1 text-sm font-semibold text-slate-900">
                  {result.display_version}
                </dd>
              </div>
            </dl>
            <p className="mt-4 text-sm leading-6 text-slate-700">
              {result.notice}
            </p>
          </div>
        )}

        <p className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
          Experimental prediction from a fully synthetic educational dataset;
          not a clinical or real-world risk estimate. Do not use for clinical or
          appointment decisions.
        </p>
      </div>
    </section>
  );
}
