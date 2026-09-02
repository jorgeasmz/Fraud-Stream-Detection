const DEFAULT_API = "http://localhost:8000";

export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API;

export type Alert = {
  transactionId: number;
  txDatetime: string;
  customerId: number;
  terminalId: number;
  amount: number;
  score: number;
  latencyMs: number;
  outcome: number | null;
  scenario: number | null;
};

export type Summary = {
  alerts: number;
  resolved: number;
  frauds: number;
  precision: number | null;
  latencyP50Ms: number | null;
  latencyP95Ms: number | null;
  byScenario: Record<string, number>;
};

/** The socket lives on the same origin as the API, over the matching scheme. */
export function socketUrl(base: string = apiUrl): string {
  const url = new URL("/live", base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/**
 * The queue endpoint returns numbers and the stream returns strings, since Redis
 * fields are text. Both become one shape here so the table never branches on it.
 */
export function toAlert(raw: Record<string, unknown>): Alert {
  const number = (value: unknown) => Number(value);
  const optional = (value: unknown) =>
    value === null || value === undefined ? null : Number(value);

  return {
    transactionId: number(raw.transaction_id),
    txDatetime:
      typeof raw.tx_datetime === "string"
        ? raw.tx_datetime
        : new Date(number(raw.epoch) * 1000).toISOString().slice(0, 19),
    customerId: number(raw.customer_id),
    terminalId: number(raw.terminal_id),
    amount: number(raw.amount),
    score: number(raw.score),
    latencyMs: number(raw.latency_ms),
    outcome: optional(raw.outcome ?? raw.is_fraud),
    scenario: optional(raw.scenario),
  };
}

export function toSummary(raw: Record<string, unknown>): Summary {
  return {
    alerts: Number(raw.alerts),
    resolved: Number(raw.resolved),
    frauds: Number(raw.frauds),
    precision: raw.precision === null ? null : Number(raw.precision),
    latencyP50Ms: raw.latency_p50_ms === null ? null : Number(raw.latency_p50_ms),
    latencyP95Ms: raw.latency_p95_ms === null ? null : Number(raw.latency_p95_ms),
    byScenario: (raw.by_scenario ?? {}) as Record<string, number>,
  };
}

export async function fetchAlerts(limit = 50, base: string = apiUrl): Promise<Alert[]> {
  const response = await fetch(`${base}/alerts?limit=${limit}`);
  if (!response.ok) throw new Error(`alerts: ${response.status}`);
  const body = await response.json();
  return (body.alerts as Record<string, unknown>[]).map(toAlert);
}

export async function fetchSummary(base: string = apiUrl): Promise<Summary> {
  const response = await fetch(`${base}/stats`);
  if (!response.ok) throw new Error(`stats: ${response.status}`);
  return toSummary(await response.json());
}
