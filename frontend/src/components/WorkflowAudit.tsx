"use client";

import { useCallback, useEffect, useState } from "react";

type WorkflowJob = {
  id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed";
  attempt_count: number;
  max_attempts: number;
  duration_ms: number;
  result: Record<string, unknown> | null;
  failure_code: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

type AuditResponse = {
  detail?: string;
  results?: WorkflowJob[];
  count?: number;
  monitoring?: {
    job_counts: Record<string, number>;
    failure_rate: number;
    execution_latency_ms: {
      average: number | null;
      minimum: number | null;
      maximum: number | null;
    };
    latest_batch_prediction: {
      record_count: number;
      actual_label_distribution: {
        attended: number;
        no_show: number;
        no_show_rate: number;
      };
      prediction_distribution: {
        attended: number;
        no_show: number;
        no_show_rate: number;
      };
      mean_probability_no_show: number;
      absolute_rate_delta: number;
      drift_threshold: number;
      drift_indicator: string;
      model_version: string | null;
    } | null;
  };
};

async function readResponse(response: Response): Promise<AuditResponse> {
  try {
    return (await response.json()) as AuditResponse;
  } catch {
    return { detail: `Workflow audit API returned HTTP ${response.status}.` };
  }
}

function displayTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function WorkflowAudit() {
  const [jobs, setJobs] = useState<WorkflowJob[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [monitoring, setMonitoring] =
    useState<AuditResponse["monitoring"]>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAudit = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `/api/admin/workflow-jobs/?page_size=20&page=${page}`,
        { cache: "no-store" },
      );
      const payload = await readResponse(response);
      if (!response.ok) {
        throw new Error(payload.detail || "Could not load workflow audit.");
      }
      setJobs(payload.results ?? []);
      setCount(payload.count ?? 0);
      setMonitoring(payload.monitoring);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not load workflow audit.",
      );
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void Promise.resolve().then(loadAudit);
  }, [loadAudit]);

  return (
    <section className="mt-7 overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_20px_60px_-40px_rgba(32,45,74,0.3)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-gradient-to-r from-indigo-50/70 via-white to-white px-5 py-5 sm:px-7">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.17em] text-indigo-700">
            Operations
          </p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">
            Workflow audit
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Read-only job history and aggregate synthetic-data health indicators.
          </p>
        </div>
        <button
          className="inline-flex min-h-10 items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
          disabled={loading}
          onClick={() => void loadAudit()}
          type="button"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>
      <div className="space-y-5 p-5 sm:p-7">
        {error && (
          <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">
            {error}
          </p>
        )}
        {monitoring && (
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Queued", monitoring.job_counts.queued ?? 0],
              ["Running", monitoring.job_counts.running ?? 0],
              ["Succeeded", monitoring.job_counts.succeeded ?? 0],
              ["Failed", monitoring.job_counts.failed ?? 0],
              [
                "Failure rate",
                `${(monitoring.failure_rate * 100).toFixed(1)}%`,
              ],
              [
                "Average latency",
                monitoring.execution_latency_ms.average == null
                  ? "—"
                  : `${monitoring.execution_latency_ms.average} ms`,
              ],
            ].map(([label, value]) => (
              <div
                className="rounded-xl border border-slate-200 bg-slate-50/70 p-3"
                key={label}
              >
                <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {label}
                </dt>
                <dd className="mt-1 text-lg font-semibold text-slate-900">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {monitoring?.latest_batch_prediction && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
            <p>
              Latest synthetic batch baseline comparison:{" "}
              {monitoring.latest_batch_prediction.drift_indicator} (
              {monitoring.latest_batch_prediction.absolute_rate_delta} rate
              delta; threshold{" "}
              {monitoring.latest_batch_prediction.drift_threshold}).
            </p>
            <p className="mt-1">
              Observed no-show rate{" "}
              {monitoring.latest_batch_prediction.actual_label_distribution.no_show_rate}
              {" · "}predicted no-show rate{" "}
              {monitoring.latest_batch_prediction.prediction_distribution.no_show_rate}
              {" · "}mean predicted probability{" "}
              {monitoring.latest_batch_prediction.mean_probability_no_show}
              {" · "}records{" "}
              {monitoring.latest_batch_prediction.record_count}
            </p>
          </div>
        )}
        {loading && jobs.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500" role="status">
            Loading workflow history...
          </p>
        ) : jobs.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
            No workflow jobs have been queued.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-3">Job</th>
                  <th className="px-3 py-3">Type</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Attempts</th>
                  <th className="px-3 py-3">Duration</th>
                  <th className="px-3 py-3">Created</th>
                  <th className="px-3 py-3">Failure code</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td className="px-3 py-3 font-mono text-xs text-slate-600">
                      {job.id.slice(0, 8)}
                    </td>
                    <td className="px-3 py-3 text-slate-700">
                      {job.job_type.replaceAll("_", " ")}
                    </td>
                    <td className="px-3 py-3 capitalize text-slate-700">
                      {job.status}
                    </td>
                    <td className="px-3 py-3 text-slate-700">
                      {job.attempt_count}/{job.max_attempts}
                    </td>
                    <td className="px-3 py-3 text-slate-700">
                      {job.duration_ms} ms
                    </td>
                    <td className="px-3 py-3 text-slate-600">
                      {displayTime(job.created_at)}
                    </td>
                    <td className="px-3 py-3 text-slate-600">
                      {job.failure_code || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
          <p className="text-xs text-slate-500">
            Page {page} of {Math.max(1, Math.ceil(count / 20))} · {count} jobs.
            Detailed inputs, requester identities, and row-level prediction data
            are not displayed.
          </p>
          <div className="flex gap-2">
            <button
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-40"
              disabled={page <= 1 || loading}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              type="button"
            >
              Previous
            </button>
            <button
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-40"
              disabled={page >= Math.ceil(count / 20) || loading}
              onClick={() => setPage((current) => current + 1)}
              type="button"
            >
              Next
            </button>
          </div>
        </footer>
      </div>
    </section>
  );
}
