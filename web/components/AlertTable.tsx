import type { Alert } from "@/lib/api";
import { scenarioOf } from "@/lib/live";

function money(amount: number): string {
  return amount.toFixed(2);
}

function moment(value: string): string {
  return value.replace("T", " ").slice(0, 16);
}

export function AlertTable({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) {
    return <p className="empty">No alerts yet. The panel fills as the replay runs.</p>;
  }

  return (
    <table>
      <caption>Newest first. The outcome is the resolved label the corpus carries.</caption>
      <thead>
        <tr>
          <th scope="col">Time</th>
          <th scope="col">Amount</th>
          <th scope="col">Score</th>
          <th scope="col">Card</th>
          <th scope="col">Terminal</th>
          <th scope="col">Latency</th>
          <th scope="col">Outcome</th>
        </tr>
      </thead>
      <tbody>
        {alerts.map((alert) => {
          const scenario = scenarioOf(alert);
          const caught = alert.outcome === 1;
          return (
            <tr key={alert.transactionId}>
              <td>{moment(alert.txDatetime)}</td>
              <td>{money(alert.amount)}</td>
              <td>{alert.score.toFixed(3)}</td>
              <td>{alert.customerId}</td>
              <td>{alert.terminalId}</td>
              <td>{alert.latencyMs.toFixed(2)} ms</td>
              <td>
                <span
                  className={`tag ${caught ? "hit" : "miss"}`}
                  title={scenario.description}
                >
                  {scenario.label}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
