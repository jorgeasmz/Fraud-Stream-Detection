import type { Alert } from "@/lib/api";

export const FEED_LIMIT = 100;

/**
 * Places an alert at the head of the feed, dropping a transaction already there.
 * A consumer group delivers at least once, so the same alert can arrive twice.
 */
export function mergeAlert(feed: Alert[], arriving: Alert, limit = FEED_LIMIT): Alert[] {
  const without = feed.filter((alert) => alert.transactionId !== arriving.transactionId);
  return [arriving, ...without].slice(0, limit);
}

export type Scenario = { label: string; description: string };

/** The simulator's three fraud patterns, which is what the scenario column names. */
export const SCENARIOS: Record<string, Scenario> = {
  "0": { label: "False alarm", description: "The transaction was legitimate" },
  "1": { label: "Amount", description: "Above the threshold no legitimate amount reaches" },
  "2": { label: "Terminal", description: "A compromised terminal, visible only through labels" },
  "3": { label: "Card", description: "A compromised card, spending far above its own average" },
};

export function scenarioOf(alert: Alert): Scenario {
  const key = alert.outcome === 0 ? "0" : String(alert.scenario ?? 0);
  return SCENARIOS[key] ?? SCENARIOS["0"];
}
