import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon } from "lucide-react";
import { fetchAllRuns } from "../../api";
import type { AllRunsRun } from "../../types";
import { StatusPill } from "../shared/StatusPill";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import { RunDetailModal } from "../session/RunDetailModal";

type RunsTableProps = {
  startDate?: string;
  endDate?: string;
  scope: "workspace" | "global";
};

const PAGE_SIZE = 25;

function formatDuration(ms: number | null): string {
  if (ms == null) return "--";
  if (ms < 1_000) return `${Math.round(ms)}ms`;
  return `${(ms / 1_000).toFixed(1)}s`;
}

function formatCost(usd: number): string {
  if (usd >= 100) return `$${usd.toFixed(0)}`;
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(4)}`;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function uniqueSortedValues(
  runs: AllRunsRun[],
  getValue: (run: AllRunsRun) => string | null | undefined
): string[] {
  return Array.from(
    new Set(
      runs
        .map((run) => getValue(run)?.trim())
        .filter((value): value is string => Boolean(value))
    )
  ).sort((a, b) => a.localeCompare(b));
}

type SortKey =
  | "started_at"
  | "total_duration_ms"
  | "estimated_cost_usd"
  | "input_tokens"
  | "output_tokens"
  | "error_count";

export function RunsTable({ startDate, endDate, scope }: RunsTableProps) {
  const [page, setPage] = useState(0);
  const [sortBy, setSortBy] = useState<SortKey>("started_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [modelFilter, setModelFilter] = useState<string>("");

  // Detail modal state
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // Reset pagination when external filters (date range or scope) change.
  const externalKey = `${startDate}|${endDate}|${scope}`;
  const [prevExternalKey, setPrevExternalKey] = useState(externalKey);
  if (externalKey !== prevExternalKey) {
    setPrevExternalKey(externalKey);
    setPage(0);
  }

  const runsQuery = useQuery({
    queryKey: [
      "dashboard-runs",
      page,
      sortBy,
      sortDir,
      statusFilter,
      providerFilter,
      modelFilter,
      startDate,
      endDate,
      scope,
    ],
    queryFn: () =>
      fetchAllRuns({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        sort_by: sortBy,
        sort_dir: sortDir,
        status: statusFilter || undefined,
        provider: providerFilter || undefined,
        model: modelFilter || undefined,
        start_date: startDate,
        end_date: endDate,
        scope,
      }),
    staleTime: 15_000,
  });

  const totalCount = runsQuery.data?.total_count ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const runs = useMemo(() => runsQuery.data?.runs ?? [], [runsQuery.data?.runs]);
  const statusOptions = useMemo(
    () => uniqueSortedValues(runs, (run) => run.status),
    [runs]
  );
  const providerOptions = useMemo(
    () => uniqueSortedValues(runs, (run) => run.provider),
    [runs]
  );
  const modelOptions = useMemo(
    () => uniqueSortedValues(runs, (run) => run.model),
    [runs]
  );

  function toggleSort(key: SortKey) {
    if (sortBy === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
    setPage(0);
  }

  function sortIndicator(key: SortKey) {
    if (sortBy !== key) return null;
    return <span className="sort-arrow">{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>;
  }

  function handleRowClick(run: AllRunsRun) {
    setSelectedRunId(run.run_session_id);
  }

  function handleFilterChange() {
    setPage(0);
  }

  return (
    <Card className="dashboard-panel">
      <CardHeader className="dashboard-panel__header">
        <CardTitle className="dashboard-panel__title">All Runs</CardTitle>
        <div className="runs-filters" aria-label="Run filters">
          <NativeSelect
            size="sm"
            className="runs-filter-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              handleFilterChange();
            }}
          >
            <NativeSelectOption value="">All statuses</NativeSelectOption>
            {statusOptions.map((status) => (
              <NativeSelectOption key={status} value={status}>
                {status}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <NativeSelect
            size="sm"
            className="runs-filter-select"
            value={providerFilter}
            onChange={(e) => {
              setProviderFilter(e.target.value);
              handleFilterChange();
            }}
          >
            <NativeSelectOption value="">All providers</NativeSelectOption>
            {providerOptions.map((provider) => (
              <NativeSelectOption key={provider} value={provider}>
                {provider}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <NativeSelect
            size="sm"
            className="runs-filter-select runs-filter-select--model"
            value={modelFilter}
            onChange={(e) => {
              setModelFilter(e.target.value);
              handleFilterChange();
            }}
          >
            <NativeSelectOption value="">All models</NativeSelectOption>
            {modelOptions.map((model) => (
              <NativeSelectOption key={model} value={model}>
                {model}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <Badge variant="outline" className="dashboard-panel__count">{totalCount} total</Badge>
      </CardHeader>

      <CardContent className="dashboard-panel__body">
        {runsQuery.isLoading ? (
          <div className="dashboard-panel__loading">
            <LoadingSpinner size="md" />
          </div>
        ) : runsQuery.isError ? (
          <Alert variant="destructive" className="dashboard-panel__error">
            <AlertTriangleIcon />
            <AlertDescription>Failed to load runs.</AlertDescription>
          </Alert>
        ) : runs.length === 0 ? (
          <div className="dashboard-panel__empty">
            No runs match the current filters.
          </div>
        ) : (
          <>
            <div className="dashboard-table-wrap">
              <Table className="dashboard-table dashboard-table--clickable">
                <TableHeader>
                  <TableRow>
                    <TableHead>Status</TableHead>
                    <TableHead>Session</TableHead>
                    <TableHead>Agent</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("total_duration_ms")}>
                      Duration {sortIndicator("total_duration_ms")}
                      </Button>
                    </TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("input_tokens")}>
                      In Tokens {sortIndicator("input_tokens")}
                      </Button>
                    </TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("output_tokens")}>
                      Out Tokens {sortIndicator("output_tokens")}
                      </Button>
                    </TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("estimated_cost_usd")}>
                      Cost {sortIndicator("estimated_cost_usd")}
                      </Button>
                    </TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("error_count")}>
                      Errors {sortIndicator("error_count")}
                      </Button>
                    </TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("started_at")}>
                      Time {sortIndicator("started_at")}
                      </Button>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((run) => (
                    <TableRow
                      key={run.run_session_id}
                      className="runs-row"
                      onClick={() => handleRowClick(run)}
                    >
                      <TableCell>
                        <StatusPill status={run.status} />
                      </TableCell>
                      <TableCell className="runs-row__session" title={run.session_title ?? undefined}>
                        {run.session_title || "--"}
                      </TableCell>
                      <TableCell>{run.agent_name ?? "--"}</TableCell>
                      <TableCell className="mono">{run.model ?? "--"}</TableCell>
                      <TableCell>{run.provider ?? "--"}</TableCell>
                      <TableCell>{formatDuration(run.total_duration_ms)}</TableCell>
                      <TableCell>{formatNumber(run.input_tokens)}</TableCell>
                      <TableCell>{formatNumber(run.output_tokens)}</TableCell>
                      <TableCell>{formatCost(run.estimated_cost_usd)}</TableCell>
                      <TableCell className={run.error_count > 0 ? "text-error" : ""}>
                        {run.error_count}
                      </TableCell>
                      <TableCell className="runs-row__time">
                        {formatTimestamp(run.started_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            <div className="runs-pagination">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <span className="runs-pagination__info">
                Page {page + 1} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages - 1}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </>
        )}
      </CardContent>

      {/* Run detail modal */}
      {selectedRunId && (
        <RunDetailModal
          runSessionId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
          scope={scope}
        />
      )}
    </Card>
  );
}
