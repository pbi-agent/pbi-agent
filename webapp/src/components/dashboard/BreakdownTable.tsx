import { useState } from "react";
import type { ProviderBreakdown } from "../../types";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";

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
      <Card className="dashboard-panel">
        <CardHeader className="dashboard-panel__header">
          <CardTitle className="dashboard-panel__title">Provider / Model Breakdown</CardTitle>
        </CardHeader>
        <CardContent className="dashboard-panel__body dashboard-panel__empty">
          No run data available.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="dashboard-panel">
      <CardHeader className="dashboard-panel__header">
        <CardTitle className="dashboard-panel__title">Provider / Model Breakdown</CardTitle>
      </CardHeader>
      <CardContent className="dashboard-panel__body">
        <div className="dashboard-table-wrap">
          <Table className="dashboard-table">
            <TableHeader>
              <TableRow>
                <TableHead>
                  <Button variant="ghost" size="sm" onClick={() => toggleSort("provider")}>
                  Provider {sortIndicator("provider")}
                  </Button>
                </TableHead>
                <TableHead>
                  <Button variant="ghost" size="sm" onClick={() => toggleSort("model")}>
                  Model {sortIndicator("model")}
                  </Button>
                </TableHead>
                <TableHead>
                  <Button variant="ghost" size="sm" onClick={() => toggleSort("run_count")}>
                  Runs {sortIndicator("run_count")}
                  </Button>
                </TableHead>
                <TableHead>
                  <Button variant="ghost" size="sm" onClick={() => toggleSort("total_tokens")}>
                  Tokens {sortIndicator("total_tokens")}
                  </Button>
                </TableHead>
                <TableHead>
                  <Button variant="ghost" size="sm" onClick={() => toggleSort("total_cost")}>
                  Cost {sortIndicator("total_cost")}
                  </Button>
                </TableHead>
                <TableHead>
                  <Button variant="ghost" size="sm" onClick={() => toggleSort("avg_duration_ms")}>
                  Avg Duration {sortIndicator("avg_duration_ms")}
                  </Button>
                </TableHead>
                <TableHead>
                  <Button variant="ghost" size="sm" onClick={() => toggleSort("error_count")}>
                  Errors {sortIndicator("error_count")}
                  </Button>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((row, i) => (
                <TableRow key={`${row.provider ?? "provider"}-${row.model ?? "model"}-${i}`}>
                  <TableCell>{row.provider ?? "--"}</TableCell>
                  <TableCell className="mono">{row.model ?? "--"}</TableCell>
                  <TableCell>{row.run_count}</TableCell>
                  <TableCell>{formatNumber(row.total_tokens)}</TableCell>
                  <TableCell>{formatCost(row.total_cost)}</TableCell>
                  <TableCell>{formatDuration(row.avg_duration_ms)}</TableCell>
                  <TableCell className={row.error_count > 0 ? "text-error" : ""}>
                    {row.error_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
