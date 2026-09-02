import { describe, expect, it } from "vitest";

import { socketUrl, toAlert, toSummary } from "@/lib/api";
import { mergeAlert, scenarioOf } from "@/lib/live";

describe("socketUrl", () => {
  it("keeps a plain origin on ws", () => {
    expect(socketUrl("http://localhost:8000")).toBe("ws://localhost:8000/live");
  });

  it("upgrades a secure origin to wss, which a browser requires on an https page", () => {
    expect(socketUrl("https://example.onrender.com")).toBe("wss://example.onrender.com/live");
  });

  it("ignores a path on the base", () => {
    expect(socketUrl("https://example.onrender.com/api")).toBe("wss://example.onrender.com/live");
  });
});

describe("toAlert", () => {
  const stream = {
    transaction_id: "949634",
    epoch: "1531088808.0",
    customer_id: "225",
    terminal_id: "6271",
    amount: "141.95",
    score: "0.9989",
    latency_ms: "1.6",
    is_fraud: "1",
    scenario: "3",
  };

  const queue = {
    transaction_id: 949634,
    tx_datetime: "2018-07-08T22:26:48",
    customer_id: 225,
    terminal_id: 6271,
    amount: 141.95,
    score: 0.9989,
    latency_ms: 1.6,
    outcome: 1,
    scenario: 3,
  };

  it("reads the stream shape, whose fields are all strings", () => {
    const alert = toAlert(stream);

    expect(alert.transactionId).toBe(949634);
    expect(alert.amount).toBeCloseTo(141.95);
    expect(alert.outcome).toBe(1);
  });

  it("reads the queue shape, whose fields are numbers", () => {
    expect(toAlert(queue).transactionId).toBe(949634);
    expect(toAlert(queue).txDatetime).toBe("2018-07-08T22:26:48");
  });

  it("gives both shapes the same alert", () => {
    expect(toAlert(stream)).toEqual(toAlert(queue));
  });

  it("keeps an unresolved outcome null rather than zero", () => {
    expect(toAlert({ ...queue, outcome: null }).outcome).toBeNull();
  });
});

describe("toSummary", () => {
  it("carries a null precision through, since no alerts is not zero precision", () => {
    const summary = toSummary({
      alerts: 0,
      resolved: 0,
      frauds: 0,
      precision: null,
      latency_p50_ms: null,
      latency_p95_ms: null,
      by_scenario: {},
    });

    expect(summary.precision).toBeNull();
    expect(summary.byScenario).toEqual({});
  });
});

describe("mergeAlert", () => {
  const alert = (transactionId: number) => toAlert({ transaction_id: transactionId, epoch: "0" });

  it("puts the newest alert first", () => {
    const feed = mergeAlert([alert(1)], alert(2));

    expect(feed.map((item) => item.transactionId)).toEqual([2, 1]);
  });

  it("drops a redelivered transaction rather than showing it twice", () => {
    const feed = mergeAlert([alert(2), alert(1)], alert(1));

    expect(feed.map((item) => item.transactionId)).toEqual([1, 2]);
  });

  it("holds the feed to its limit", () => {
    const feed = [alert(3), alert(2), alert(1)];

    expect(mergeAlert(feed, alert(4), 2)).toHaveLength(2);
  });
});

describe("scenarioOf", () => {
  it("names a legitimate transaction a false alarm whatever its scenario", () => {
    const alert = toAlert({ transaction_id: 1, epoch: "0", outcome: 0, scenario: 0 });

    expect(scenarioOf(alert).label).toBe("False alarm");
  });

  it("names the compromised terminal, which only labels reach", () => {
    const alert = toAlert({ transaction_id: 1, epoch: "0", outcome: 1, scenario: 2 });

    expect(scenarioOf(alert).label).toBe("Terminal");
  });
});
