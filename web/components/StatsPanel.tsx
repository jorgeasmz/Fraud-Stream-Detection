import type { Summary } from "@/lib/api";

function share(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function millis(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)} ms`;
}

export function StatsPanel({ summary }: { summary: Summary | null }) {
  return (
    <dl className="cards">
      <div className="card">
        <dt>Alerts</dt>
        <dd>{summary ? summary.alerts.toLocaleString() : "—"}</dd>
      </div>
      <div className="card">
        <dt>Precision</dt>
        <dd>{summary ? share(summary.precision) : "—"}</dd>
      </div>
      <div className="card">
        <dt>Frauds caught</dt>
        <dd>{summary ? summary.frauds.toLocaleString() : "—"}</dd>
      </div>
      <div className="card">
        <dt>Latency p50</dt>
        <dd>{summary ? millis(summary.latencyP50Ms) : "—"}</dd>
      </div>
      <div className="card">
        <dt>Latency p95</dt>
        <dd>{summary ? millis(summary.latencyP95Ms) : "—"}</dd>
      </div>
    </dl>
  );
}
