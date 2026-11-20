"use client";

import { FormEvent, useEffect, useState } from "react";

type Props = {
  accessToken: string;
  onSessionExpired: () => void;
  refreshAccessToken: () => Promise<string | null>;
};

type MetricSet = {
  accuracy: number;
  precision: number;
  recall: number;
  f1_score: number;
  roc_auc: number;
  average_precision: number;
  confusion_matrix: number[][];
};

type ModelComparison = {
  dataset_description: string;
  random_seed: number;
  split_strategy: string;
  split_sizes: { train: number; validation: number; test: number };
  selected_model: string;
  training_metrics: Record<
    string,
    {
      validation: MetricSet;
      training?: MetricSet;
    }
  >;
  test_metrics: MetricSet;
};

type ModelMetadata = {
  model_name: string;
  model_version: string;
  dataset_description: string;
  feature_schema: Record<string, { type: string; meaning: string }>;
  random_seed: number;
  split_strategy: string;
};

type PCARecord = {
  row_index: number;
  pca_1: number;
  pca_2: number;
  kmeans_cluster: number;
  dbscan_cluster: number;
};

type ClusteringReport = {
  report_version: number;
  dataset: {
    description: string;
    row_count: number;
    feature_schema: Record<string, { type: string; meaning: string }>;
    target_used: boolean;
  };
  random_seed: number;
  kmeans: {
    parameters: { selected_k?: number; n_init: number; random_state: number };
    selected_k: number;
    selected_silhouette: number;
    selected_cluster_counts: Record<string, number>;
    elbow_and_silhouette: Array<{
      n_clusters: number;
      inertia: number;
      silhouette: number | null;
    }>;
  };
  dbscan: {
    parameters: { eps: number; min_samples: number; metric: string };
    cluster_counts_including_noise: Record<string, number>;
    silhouette: number | null;
    silhouette_status: string;
  };
  visualization: {
    explained_variance_ratio: number[];
    coordinates: PCARecord[];
  };
};

type DashboardPayload = {
  supervised: ModelComparison;
  supervised_metadata: ModelMetadata;
  clustering: ClusteringReport;
};

type FAQResponse = {
  answer: string;
  insufficient_information: boolean;
  citations: Array<{ title: string; filename: string }>;
};

type Section =
  | "overview"
  | "predictive"
  | "segmentation"
  | "assistant"
  | "governance";
type ClusterMethod = "kmeans" | "dbscan";

const SECTIONS: Array<{ id: Section; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "predictive", label: "Predictive Analytics" },
  { id: "segmentation", label: "Engagement Segmentation" },
  { id: "assistant", label: "Clinic Assistant" },
  { id: "governance", label: "Model Governance" },
];

const MODEL_NAMES = [
  ["LogisticRegression", "Logistic Regression"],
  ["RandomForestClassifier", "Random Forest"],
  ["GradientBoostingClassifier", "Gradient Boosting"],
] as const;

const COLORS = [
  "#0f766e",
  "#2563eb",
  "#64748b",
  "#0e7490",
  "#4f46e5",
  "#15803d",
  "#a16207",
  "#475569",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isDashboardPayload(value: unknown): value is DashboardPayload {
  if (!isRecord(value)) return false;
  return (
    isRecord(value.supervised) &&
    isRecord(value.supervised_metadata) &&
    isRecord(value.clustering) &&
    isRecord(value.supervised.training_metrics) &&
    isRecord(value.clustering.kmeans) &&
    isRecord(value.clustering.dbscan) &&
    isRecord(value.clustering.visualization)
  );
}

function formatPercent(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(1)}%`
    : "N/A";
}

function formatScore(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(3)
    : "N/A";
}

async function responsePayload(response: Response) {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

function errorText(payload: unknown) {
  if (isRecord(payload) && typeof payload.detail === "string") {
    return payload.detail;
  }
  return "The dashboard service could not complete the request.";
}

function StateMessage({
  children,
  error = false,
}: {
  children: React.ReactNode;
  error?: boolean;
}) {
  return (
    <p
      className={`rounded-xl border px-4 py-3 text-sm leading-6 ${
        error
          ? "border-rose-200 bg-rose-50 text-rose-800"
          : "border-slate-200 bg-white text-slate-600"
      }`}
      role={error ? "alert" : "status"}
    >
      {children}
    </p>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-slate-950">
        {value}
      </p>
    </div>
  );
}

function ConfusionMatrix({ matrix }: { matrix: number[][] }) {
  const cells = [
    { label: "True attended", value: matrix?.[0]?.[0] },
    { label: "False no-show", value: matrix?.[0]?.[1] },
    { label: "Missed no-show", value: matrix?.[1]?.[0] },
    { label: "True no-show", value: matrix?.[1]?.[1] },
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[19rem] border-separate border-spacing-1 text-center text-xs">
        <caption className="sr-only">
          Confusion matrix, actual classes by predicted classes
        </caption>
        <thead>
          <tr>
            <th className="p-2 text-left font-medium text-slate-500">Actual / predicted</th>
            <th className="p-2 font-medium text-slate-500">Attended</th>
            <th className="p-2 font-medium text-slate-500">No-show</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th className="p-2 text-left font-medium text-slate-600">Attended</th>
            <td className="rounded-lg bg-teal-50 p-3 font-semibold tabular-nums text-teal-950">
              {typeof cells[0].value === "number" ? cells[0].value : "N/A"}
            </td>
            <td className="rounded-lg bg-slate-100 p-3 font-semibold tabular-nums text-slate-800">
              {typeof cells[1].value === "number" ? cells[1].value : "N/A"}
            </td>
          </tr>
          <tr>
            <th className="p-2 text-left font-medium text-slate-600">No-show</th>
            <td className="rounded-lg bg-slate-100 p-3 font-semibold tabular-nums text-slate-800">
              {typeof cells[2].value === "number" ? cells[2].value : "N/A"}
            </td>
            <td className="rounded-lg bg-teal-50 p-3 font-semibold tabular-nums text-teal-950">
              {typeof cells[3].value === "number" ? cells[3].value : "N/A"}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function PredictiveAnalyticsSection({ data }: { data: DashboardPayload }) {
  const models = MODEL_NAMES.map(([key, label]) => ({
    key,
    label,
    validation: data.supervised.training_metrics[key]?.validation,
  })).filter((model) => model.validation);

  if (!models.length) {
    return <StateMessage>No supervised comparison metrics are available.</StateMessage>;
  }
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-800">
          Predictive performance
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
          Predictive analytics
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Compare the existing model results on the validation split. Confusion
          matrices show actual classes in rows and predicted classes in columns.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {models.map(({ key, label, validation }) => (
          <article
            className="rounded-2xl border border-slate-200 bg-white p-5"
            key={key}
          >
            <h3 className="text-base font-semibold text-slate-950">{label}</h3>
            <p className="mt-1 text-xs text-slate-500">
              Validation set · {data.supervised.split_sizes.validation.toLocaleString()} synthetic records
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <MetricCard label="Accuracy" value={formatPercent(validation.accuracy)} />
              <MetricCard label="Precision" value={formatPercent(validation.precision)} />
              <MetricCard label="Recall" value={formatPercent(validation.recall)} />
              <MetricCard label="F1" value={formatPercent(validation.f1_score)} />
              <MetricCard label="ROC-AUC" value={formatScore(validation.roc_auc)} />
              <MetricCard label="PR-AUC (AP)" value={formatScore(validation.average_precision)} />
            </div>
            <h4 className="mb-1 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-600">
              Confusion matrix
            </h4>
            <ConfusionMatrix matrix={validation.confusion_matrix} />
          </article>
        ))}
      </div>
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="text-base font-semibold text-slate-950">Feature importance</h3>
        <p className="mt-1 text-sm leading-6 text-slate-600">
          Importance is specific to a model and evaluation split; it does not
          show causation. The current dashboard data response does not include
          the feature-importance report, so values are not displayed here.
        </p>
      </section>
    </div>
  );
}

function OverviewSection({ data }: { data: DashboardPayload }) {
  const selectedMetrics =
    data.supervised.training_metrics[data.supervised.selected_model]?.validation;
  const selectedModel =
    MODEL_NAMES.find(([key]) => key === data.supervised.selected_model)?.[1] ??
    data.supervised.selected_model;
  const clusterCount = Object.keys(
    data.clustering.kmeans.selected_cluster_counts,
  ).length;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-800">
          Intelligence overview
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
          At a glance
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          A concise view of model performance and engagement segmentation,
          using fictional synthetic data for demonstration.
        </p>
      </div>
      {selectedMetrics ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label={`${selectedModel} · validation F1`} value={formatPercent(selectedMetrics.f1_score)} />
          <MetricCard label="Validation ROC-AUC" value={formatScore(selectedMetrics.roc_auc)} />
          <MetricCard label="Training records" value={data.supervised.split_sizes.train.toLocaleString()} />
          <MetricCard label="Engagement records" value={data.clustering.dataset.row_count.toLocaleString()} />
        </div>
      ) : (
        <StateMessage>Selected model validation metrics are unavailable.</StateMessage>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Predictive analytics
          </p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">
            Three model approaches
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Logistic Regression, Random Forest, and Gradient Boosting are
            compared using the same validation split. The currently selected
            model is {selectedModel}.
          </p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Engagement segmentation
          </p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">
            K-Means and DBSCAN
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            The current K-Means view contains {clusterCount} descriptive
            segments. These groupings summarize synthetic data only and are
            not diagnoses or validated clinical risk categories.
          </p>
        </article>
      </div>
      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
        <h3 className="text-sm font-semibold text-slate-900">Data context</h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {data.supervised.dataset_description} Clustering uses a separate
          dataset of {data.clustering.dataset.row_count.toLocaleString()} rows.
          Results are educational and should not be used for care decisions.
        </p>
      </section>
    </div>
  );
}

function ClusterPlot({
  report,
  method,
}: {
  report: ClusteringReport;
  method: ClusterMethod;
}) {
  const coordinates = report.visualization.coordinates;
  if (!coordinates.length) {
    return <StateMessage>No PCA coordinates are available in the clustering report.</StateMessage>;
  }
  const width = 720;
  const height = 360;
  const padding = { top: 24, right: 24, bottom: 52, left: 62 };
  const xValues = coordinates.map((point) => point.pca_1);
  const yValues = coordinates.map((point) => point.pca_2);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  const xRange = maxX - minX || 1;
  const yRange = maxY - minY || 1;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const clusters = method === "kmeans" ? report.kmeans.selected_cluster_counts : report.dbscan.cluster_counts_including_noise;
  const clusterColor = (label: number) =>
    label === -1
      ? "#94a3b8"
      : COLORS[Math.abs(label) % COLORS.length];
  const xExplained = formatPercent(report.visualization.explained_variance_ratio[0]);
  const yExplained = formatPercent(report.visualization.explained_variance_ratio[1]);

  return (
    <div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <svg
          aria-label={`PCA scatter plot of synthetic engagement records, colored by ${method === "kmeans" ? "K-Means" : "DBSCAN"} segment`}
          className="h-auto min-w-[34rem] w-full"
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          {[0, 1, 2, 3, 4].map((tick) => {
            const x = padding.left + (tick / 4) * plotWidth;
            const y = padding.top + (tick / 4) * plotHeight;
            const xValue = minX + (tick / 4) * xRange;
            const yValue = maxY - (tick / 4) * yRange;
            return (
              <g key={tick}>
                <line x1={x} y1={padding.top} x2={x} y2={height - padding.bottom} stroke="#e2e8f0" />
                <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#e2e8f0" />
                <text x={x} y={height - padding.bottom + 18} textAnchor="middle" fill="#64748b" fontSize="10">
                  {xValue.toFixed(1)}
                </text>
                <text x={padding.left - 10} y={y + 3} textAnchor="end" fill="#64748b" fontSize="10">
                  {yValue.toFixed(1)}
                </text>
              </g>
            );
          })}
          {coordinates.map((point) => {
            const x = padding.left + ((point.pca_1 - minX) / xRange) * plotWidth;
            const y = padding.top + ((maxY - point.pca_2) / yRange) * plotHeight;
            const cluster = method === "kmeans" ? point.kmeans_cluster : point.dbscan_cluster;
            return (
              <circle
                cx={x}
                cy={y}
                fill={clusterColor(cluster)}
                key={`${point.row_index}-${method}`}
                opacity="0.72"
                r="2.6"
              >
                <title>{`Synthetic record ${point.row_index + 1}; ${cluster === -1 ? "noise point" : `segment ${cluster}`}`}</title>
              </circle>
            );
          })}
          <text fill="#334155" fontSize="11" fontWeight="600" x={width / 2} y={height - 8} textAnchor="middle">
            Principal component 1 · {xExplained} variance
          </text>
          <text fill="#334155" fontSize="11" fontWeight="600" x="14" y={height / 2} textAnchor="middle" transform={`rotate(-90 14 ${height / 2})`}>
            Principal component 2 · {yExplained} variance
          </text>
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {Object.entries(clusters).map(([label, count]) => (
          <span
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700"
            key={label}
          >
            <span
              aria-hidden="true"
              className="size-2.5 rounded-full"
              style={{ backgroundColor: clusterColor(Number(label)) }}
            />
            {label === "-1" ? "Noise points" : `Segment ${label}`} · {count}
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">
        PCA is shown for visualization only. Clustering was calculated using
        all five standardized engagement features, not these two components.
      </p>
    </div>
  );
}

function ClusteringSection({ report }: { report: ClusteringReport }) {
  const [method, setMethod] = useState<ClusterMethod>("kmeans");
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-800">
          Engagement segmentation
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
          Segmentation methods
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          {report.dataset.description} These descriptive groups are not
          diagnoses or validated clinical risk categories.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold text-slate-900">K-Means</h3>
              <p className="mt-1 text-sm text-slate-600">
                Selected k = {report.kmeans.selected_k}
              </p>
            </div>
            <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-900">
              Silhouette {formatScore(report.kmeans.selected_silhouette)}
            </span>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            {Object.keys(report.kmeans.selected_cluster_counts).length} clusters
            · random seed {report.random_seed}
          </p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold text-slate-900">DBSCAN</h3>
              <p className="mt-1 text-sm text-slate-600">
                eps {report.dbscan.parameters.eps} · min samples{" "}
                {report.dbscan.parameters.min_samples}
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
              Silhouette {formatScore(report.dbscan.silhouette)}
            </span>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            {Object.keys(report.dbscan.cluster_counts_including_noise).filter((label) => label !== "-1").length} segments
            · {report.dbscan.cluster_counts_including_noise["-1"] ?? 0} noise points
          </p>
        </article>
      </div>
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold text-slate-900">PCA projection</h3>
            <p className="mt-1 text-xs text-slate-500">
              {report.visualization.coordinates.length.toLocaleString()} synthetic records · PCA projection
            </p>
          </div>
          <div className="inline-flex rounded-xl bg-slate-100 p-1" role="group" aria-label="Cluster method">
            {(["kmeans", "dbscan"] as const).map((value) => (
              <button
                aria-pressed={method === value}
                className={`min-h-9 rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-1 ${method === value ? "bg-white text-teal-900 shadow-sm" : "text-slate-600 hover:text-slate-900"}`}
                key={value}
                onClick={() => setMethod(value)}
                type="button"
              >
                {value === "kmeans" ? "K-Means" : "DBSCAN"}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4">
          <ClusterPlot method={method} report={report} />
        </div>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="font-semibold text-slate-950">K-Means selection metrics</h3>
        <p className="mt-1 text-sm text-slate-600">
          Inertia and silhouette scores across the evaluated cluster counts.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="py-3">Segments (k)</th><th>Inertia</th><th>Silhouette</th></tr>
            </thead>
            <tbody>
              {report.kmeans.elbow_and_silhouette.map((row) => (
                <tr className="border-t border-slate-100" key={row.n_clusters}>
                  <td className="py-2 font-medium text-slate-800">{row.n_clusters}</td>
                  <td className="tabular-nums text-slate-600">{formatScore(row.inertia)}</td>
                  <td className="tabular-nums text-slate-600">{formatScore(row.silhouette)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function AssistantSection({
  accessToken,
  onSessionExpired,
  refreshAccessToken,
}: Props) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<FAQResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAnswer(null);
    setError("");
    setLoading(true);
    const request = (token: string) =>
      fetch("/api/clinic-faq/ask/", {
        method: "POST",
        headers: {
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ question }),
        cache: "no-store",
      });

    try {
      let response = await request(accessToken);
      if (response.status === 401) {
        const freshToken = await refreshAccessToken();
        if (!freshToken) {
          onSessionExpired();
          return;
        }
        response = await request(freshToken);
      }
      const payload = await responsePayload(response);
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (!response.ok) throw new Error(errorText(payload));
      if (
        !isRecord(payload) ||
        typeof payload.answer !== "string" ||
        typeof payload.insufficient_information !== "boolean" ||
        !Array.isArray(payload.citations)
      ) {
        throw new Error("The FAQ service returned an invalid response.");
      }
      setAnswer(payload as FAQResponse);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not reach the FAQ service.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-800">
          Approved policy guidance
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
          Clinic Assistant
        </h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-600">
          Ask a general question about scheduling, cancellations, late arrivals,
          or reminders. Do not include personal or patient-specific information.
        </p>
      </div>
      <form className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5" onSubmit={submitQuestion}>
        <label className="block text-sm font-semibold text-slate-700" htmlFor="clinic-faq-question">
          Your question
          <textarea
            className="mt-2 block min-h-28 w-full rounded-lg border border-slate-300 bg-white px-3.5 py-3 text-sm font-normal text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-teal-700 focus:ring-2 focus:ring-teal-700/15"
            id="clinic-faq-question"
            maxLength={1000}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="How can I request an appointment?"
            required
            value={question}
          />
        </label>
        {error && <StateMessage error>{error}</StateMessage>}
        <button
          className="inline-flex min-h-11 items-center justify-center rounded-lg bg-teal-800 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={loading || !question.trim()}
          type="submit"
        >
          {loading ? "Searching approved policies…" : "Submit question"}
        </button>
      </form>
      {loading && <StateMessage>Searching approved policy passages…</StateMessage>}
      {answer && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-slate-950">Assistant response</h3>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${answer.insufficient_information ? "bg-amber-50 text-amber-900" : "bg-teal-50 text-teal-900"}`}>
              {answer.insufficient_information ? "More information needed" : "Policy-supported response"}
            </span>
          </div>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-700">
            {answer.answer}
          </p>
          {answer.citations.length > 0 && (
            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Sources
              </h4>
              <ul className="mt-3 space-y-2">
                {answer.citations.map((citation) => (
                  <li
                    className="border-l-2 border-teal-700 pl-3 text-sm"
                    key={`${citation.filename}-${citation.title}`}
                  >
                    <span className="block font-medium text-slate-900">{citation.title}</span>
                    <span className="mt-0.5 block text-xs text-slate-500">{citation.filename}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
      <p className="text-xs leading-5 text-slate-500">
        Responses are based on approved fictional policy examples and are not medical advice.
      </p>
    </div>
  );
}

function GovernanceSection({ data }: { data: DashboardPayload }) {
  const metadata = data.supervised_metadata;
  const validation =
    data.supervised.training_metrics[metadata.model_name]?.validation;
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-800">
          Reproducibility and oversight
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
          Model Governance
        </h2>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-slate-950">Supervised model</h3>
          <dl className="mt-4 space-y-3 text-sm">
            <div><dt className="text-slate-500">Model</dt><dd className="mt-0.5 font-medium text-slate-800">{metadata.model_name}</dd></div>
            <div><dt className="text-slate-500">Version</dt><dd className="mt-0.5 break-all font-mono text-xs text-slate-800">{metadata.model_version}</dd></div>
            <div><dt className="text-slate-500">Dataset</dt><dd className="mt-0.5 text-slate-800">{metadata.dataset_description}</dd></div>
            <div><dt className="text-slate-500">Split / seed</dt><dd className="mt-0.5 text-slate-800">{metadata.split_strategy} · {metadata.random_seed}</dd></div>
          </dl>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-slate-950">Validation performance</h3>
          {validation ? (
            <>
              <p className="mt-1 text-xs text-slate-500">Validation metrics · sourced from the supervised report</p>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <MetricCard label="Accuracy" value={formatPercent(validation.accuracy)} />
                <MetricCard label="Precision" value={formatPercent(validation.precision)} />
                <MetricCard label="Recall" value={formatPercent(validation.recall)} />
                <MetricCard label="F1" value={formatPercent(validation.f1_score)} />
                <MetricCard label="ROC-AUC" value={formatScore(validation.roc_auc)} />
                <MetricCard label="PR-AUC (AP)" value={formatScore(validation.average_precision)} />
              </div>
            </>
          ) : <StateMessage>Selected model metrics are unavailable.</StateMessage>}
          <p className="mt-3 text-xs text-slate-500">
            Clustering seed: {data.clustering.random_seed} · K-Means silhouette: {formatScore(data.clustering.kmeans.selected_silhouette)} · DBSCAN silhouette: {formatScore(data.clustering.dbscan.silhouette)}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Segmentation report version: {data.clustering.report_version}
          </p>
        </article>
      </div>
      <section className="rounded-2xl border border-teal-200 bg-teal-50/60 p-5">
        <h3 className="font-semibold text-teal-950">Synthetic-data notice</h3>
        <p className="mt-2 text-sm leading-6 text-teal-950/80">
          All supervised and clustering records are fictional synthetic examples.
          No real patient records are used. Predictions and cluster groupings are
          educational demonstrations, not clinical or operational guidance.
        </p>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="font-semibold text-slate-950">Limitations and appropriate use</h3>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">
          <li>Metrics reflect synthetic datasets and may not generalize to real-world settings.</li>
          <li>The selected supervised model has modest validation performance and can produce false positives and false negatives.</li>
          <li>Cluster assignments describe the generated data only; they are not diagnoses, risk scores, or clinical profiles.</li>
          <li>PCA compresses dimensions for visualization and can obscure structure present in the full feature space.</li>
          <li>FAQ answers are limited to the approved fictional policy passages and may abstain when those examples lack the requested detail.</li>
        </ul>
        <h4 className="mb-2 mt-5 text-sm font-semibold text-slate-800">Supervised input schema</h4>
        <div className="grid gap-2 sm:grid-cols-2">
          {Object.entries(metadata.feature_schema).map(([name, feature]) => (
            <div className="rounded-lg bg-slate-50 px-3 py-2" key={name}>
              <p className="text-xs font-semibold text-slate-800">{name} <span className="font-normal text-slate-500">· {feature.type}</span></p>
              <p className="mt-1 text-xs leading-5 text-slate-600">{feature.meaning}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default function MLDashboard({
  accessToken,
  onSessionExpired,
  refreshAccessToken,
}: Props) {
  const [activeSection, setActiveSection] = useState<Section>("overview");
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    async function loadDashboard() {
      setLoading(true);
      setError("");
      try {
        let token = accessToken;
        let response = await fetch("/api/ml-dashboard/", {
          headers: { authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (response.status === 401) {
          const refreshed = await refreshAccessToken();
          if (!refreshed) {
            onSessionExpired();
            return;
          }
          token = refreshed;
          response = await fetch("/api/ml-dashboard/", {
            headers: { authorization: `Bearer ${token}` },
            cache: "no-store",
          });
        }
        const payload = await responsePayload(response);
        if (response.status === 401) {
          onSessionExpired();
          return;
        }
        if (!response.ok) throw new Error(errorText(payload));
        if (!isDashboardPayload(payload)) {
          throw new Error("The dashboard returned an invalid report format.");
        }
        if (active) setData(payload);
      } catch (loadError) {
        if (active) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Could not load the ML dashboard.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadDashboard();
    return () => {
      active = false;
    };
  }, [accessToken, onSessionExpired, refreshAccessToken, reloadKey]);

  function renderSectionContent(section: Section) {
    if (!data) return null;
    switch (section) {
      case "overview":
        return <OverviewSection data={data} />;
      case "predictive":
        return <PredictiveAnalyticsSection data={data} />;
      case "segmentation":
        return <ClusteringSection report={data.clustering} />;
      case "assistant":
        return (
          <AssistantSection
            accessToken={accessToken}
            onSessionExpired={onSessionExpired}
            refreshAccessToken={refreshAccessToken}
          />
        );
      case "governance":
        return <GovernanceSection data={data} />;
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-5 py-6 sm:px-8 sm:py-7">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-800">
          HealthProfile
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
          HealthProfile Intelligence
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Clinical insights, predictive analytics &amp; policy assistance
        </p>
      </div>
      <div className="border-b border-slate-200 px-3 py-3 sm:px-5">
        <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="ML dashboard sections">
          {SECTIONS.map((section) => (
            <button
              aria-selected={activeSection === section.id}
              aria-controls={`ml-panel-${section.id}`}
              className={`min-h-10 shrink-0 rounded-lg px-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 sm:px-4 ${activeSection === section.id ? "bg-teal-800 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"}`}
              id={`ml-tab-${section.id}`}
              key={section.id}
              onClick={() => setActiveSection(section.id)}
              onKeyDown={(event) => {
                const tabs = Array.from(
                  event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                    '[role="tab"]',
                  ) ?? [],
                );
                const currentIndex = tabs.indexOf(event.currentTarget);
                const nextIndex =
                  event.key === "ArrowRight"
                    ? (currentIndex + 1) % tabs.length
                    : event.key === "ArrowLeft"
                      ? (currentIndex - 1 + tabs.length) % tabs.length
                      : event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? tabs.length - 1
                          : -1;
                if (nextIndex >= 0) {
                  event.preventDefault();
                  tabs[nextIndex].focus();
                  tabs[nextIndex].click();
                }
              }}
              role="tab"
              tabIndex={activeSection === section.id ? 0 : -1}
              type="button"
            >
              {section.label}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-5 bg-slate-50/50 p-4 sm:p-7">
        {loading ? (
          <StateMessage>Loading analytics and policy reports…</StateMessage>
        ) : error ? (
          <>
            <StateMessage error>{error}</StateMessage>
            <button
              className="min-h-10 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
              onClick={() => setReloadKey((current) => current + 1)}
              type="button"
            >
              Retry
            </button>
          </>
        ) : !data ? (
          <StateMessage>No analytics report data is available.</StateMessage>
        ) : (
          SECTIONS.map((section) => (
            <div
              aria-labelledby={`ml-tab-${section.id}`}
              hidden={activeSection !== section.id}
              id={`ml-panel-${section.id}`}
              key={section.id}
              role="tabpanel"
              tabIndex={0}
            >
              {renderSectionContent(section.id)}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
