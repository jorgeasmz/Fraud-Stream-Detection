"use client";

import { useEffect, useState } from "react";

import { AlertTable } from "@/components/AlertTable";
import { StatsPanel } from "@/components/StatsPanel";
import { type Alert, type Summary, fetchAlerts, fetchSummary, socketUrl, toAlert } from "@/lib/api";
import { FEED_LIMIT, mergeAlert } from "@/lib/live";

const SUMMARY_INTERVAL_MS = 5_000;

export default function Page() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    // The socket carries what arrives while it is open, so the backlog is fetched.
    fetchAlerts(FEED_LIMIT).then(setAlerts).catch(() => setAlerts([]));
  }, []);

  useEffect(() => {
    const read = () => fetchSummary().then(setSummary).catch(() => undefined);
    read();
    const timer = setInterval(read, SUMMARY_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const open = () => {
      socket = new WebSocket(socketUrl());
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => {
        const arriving = toAlert(JSON.parse(event.data));
        setAlerts((feed) => mergeAlert(feed, arriving));
      };
      socket.onclose = () => {
        setConnected(false);
        // A free instance sleeps, so a closed socket is reopened rather than reported.
        if (!closed) retry = setTimeout(open, 3_000);
      };
    };

    open();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, []);

  return (
    <main>
      <header>
        <h1>Fraud Stream Detection</h1>
        <p className="lede">
          Transactions from the held-out period, scored as they arrive and ranked for a team
          that works a hundred alerts a day. Each row is a transaction the detector placed
          above that operating point.
        </p>
        <p className="status">
          <span className={`dot ${connected ? "on" : ""}`} aria-hidden />
          {connected ? "Live" : "Reconnecting"}
        </p>
      </header>

      <StatsPanel summary={summary} />
      <AlertTable alerts={alerts} />

      <p className="note">
        Precision is measured over alerts whose dispute has resolved. A compromised terminal
        is reachable only through past labels, which arrive seven days after the transaction
        they judge, and no detector fitted without them exceeds chance on that pattern.
      </p>
    </main>
  );
}
