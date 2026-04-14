import { useState } from "react";
import type { ProviderBreakdown } from "../../types";

type SortKey =
  | "provider"
  | "model"
  | "run_count"
  | "total_tokens"
  | "total_cost"
  | "avg_duration_ms"
  | "error_count";

type BreakdownTableProps = {
  breakdown: ProviderBreakdown[];
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function formatCost(usd: number): string {
  if (usd >= 100) return `$${usd.toFixed(0)}`;
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(4)}`;
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "--";
  if (ms < 1_000) return `${Math.round(ms)}ms`;
  return `${(ms / 1_000).toFixed(1)}s`;
}

export function BreakdownTable({ breakdown }: BreakdownTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("total_tokens");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...breakdown].sort((a, b) => {
    const av = a[sortKey] ?? "";
    const bv = b[sortKey] ?? "";
    if (typeof av === "number" && typeof bv === "number") {
      return sortAsc ? av - bv : bv - av;
    }
    return sortAsc
      ? String(av).localeCompare(String(bv))
      : String(bv).localeCompare(String(av));
  });

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return null;
    return <span className="sort-arrow">{sortAsc ? "\u25B2" : "\u25BC"}</span>;
  }

  if (breakdown.length === 0) {
    return (
      <div className="dashboard-panel">
        <div className="dashboard-panel__header">
          <h2 className="dashboard-panel__title">Provider / Model Breakdown</h2>
        </div>
        <div className="dashboard-panel__body dashboard-panel__empty">
          No run data available.
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-panel">
      <div className="dashboard-panel__header">
        <h2 className="dashboard-panel__title">Provider / Model Breakdown</h2>
      </div>
      <div className="dashboard-panel__body">
        <div className="dashboard-table-wrap">
          <table className="dashboard-table">
            <thead>
              <tr>
                <th onClick={() => toggleSort("provider")}>
                  Provider {sortIndicator("provider")}
                </th>
                <th onClick={() => toggleSort("model")}>
                  Model {sortIndicator("model")}
                </th>
                <th onClick={() => toggleSort("run_count")}>
                  Runs {sortIndicator("run_count")}
                </th>
                <th onClick={() => toggleSort("total_tokens")}>
                  Tokens {sortIndicator("total_tokens")}
                </th>
                <th onClick={() => toggleSort("total_cost")}>
                  Cost {sortIndicator("total_cost")}
                </th>
                <th onClick={() => toggleSort("avg_duration_ms")}>
                  Avg Duration {sortIndicator("avg_duration_ms")}
                </th>
                <th onClick={() => toggleSort("error_count")}>
                  Errors {sortIndicator("error_count")}
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => (
                <tr key={i}>
                  <td>{row.provider ?? "--"}</td>
                  <td className="mono">{row.model ?? "--"}</td>
                  <td>{row.run_count}</td>
                  <td>{formatNumber(row.total_tokens)}</td>
                  <td>{formatCost(row.total_cost)}</td>
                  <td>{formatDuration(row.avg_duration_ms)}</td>
                  <td className={row.error_count > 0 ? "text-error" : ""}>
                    {row.error_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
