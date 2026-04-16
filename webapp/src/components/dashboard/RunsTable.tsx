import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllRuns } from "../../api";
import type { AllRunsRun } from "../../types";
import { StatusPill } from "../shared/StatusPill";
import { LoadingSpinner } from "../shared/LoadingSpinner";
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
  const runs = runsQuery.data?.runs ?? [];

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
    <div className="dashboard-panel">
      <div className="dashboard-panel__header">
        <h2 className="dashboard-panel__title">All Runs</h2>
        <span className="dashboard-panel__count">{totalCount} total</span>
      </div>

      {/* Filters */}
      <div className="runs-filters">
        <select
          className="runs-filter-select"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            handleFilterChange();
          }}
        >
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="started">Running</option>
        </select>
        <input
          className="runs-filter-input"
          type="text"
          placeholder="Filter provider..."
          value={providerFilter}
          onChange={(e) => {
            setProviderFilter(e.target.value);
            handleFilterChange();
          }}
        />
        <input
          className="runs-filter-input"
          type="text"
          placeholder="Filter model..."
          value={modelFilter}
          onChange={(e) => {
            setModelFilter(e.target.value);
            handleFilterChange();
          }}
        />
      </div>

      <div className="dashboard-panel__body">
        {runsQuery.isLoading ? (
          <div className="dashboard-panel__loading">
            <LoadingSpinner size="md" />
          </div>
        ) : runsQuery.isError ? (
          <div className="dashboard-panel__error">
            Failed to load runs.
          </div>
        ) : runs.length === 0 ? (
          <div className="dashboard-panel__empty">
            No runs match the current filters.
          </div>
        ) : (
          <>
            <div className="dashboard-table-wrap">
              <table className="dashboard-table dashboard-table--clickable">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Session</th>
                    <th>Agent</th>
                    <th>Model</th>
                    <th>Provider</th>
                    <th onClick={() => toggleSort("total_duration_ms")}>
                      Duration {sortIndicator("total_duration_ms")}
                    </th>
                    <th onClick={() => toggleSort("input_tokens")}>
                      In Tokens {sortIndicator("input_tokens")}
                    </th>
                    <th onClick={() => toggleSort("output_tokens")}>
                      Out Tokens {sortIndicator("output_tokens")}
                    </th>
                    <th onClick={() => toggleSort("estimated_cost_usd")}>
                      Cost {sortIndicator("estimated_cost_usd")}
                    </th>
                    <th onClick={() => toggleSort("error_count")}>
                      Errors {sortIndicator("error_count")}
                    </th>
                    <th onClick={() => toggleSort("started_at")}>
                      Time {sortIndicator("started_at")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr
                      key={run.run_session_id}
                      className="runs-row"
                      onClick={() => handleRowClick(run)}
                    >
                      <td>
                        <StatusPill status={run.status} />
                      </td>
                      <td className="runs-row__session" title={run.session_title ?? undefined}>
                        {run.session_title || "--"}
                      </td>
                      <td>{run.agent_name ?? "--"}</td>
                      <td className="mono">{run.model ?? "--"}</td>
                      <td>{run.provider ?? "--"}</td>
                      <td>{formatDuration(run.total_duration_ms)}</td>
                      <td>{formatNumber(run.input_tokens)}</td>
                      <td>{formatNumber(run.output_tokens)}</td>
                      <td>{formatCost(run.estimated_cost_usd)}</td>
                      <td className={run.error_count > 0 ? "text-error" : ""}>
                        {run.error_count}
                      </td>
                      <td className="runs-row__time">
                        {formatTimestamp(run.started_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="runs-pagination">
              <button
                className="btn btn--sm"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </button>
              <span className="runs-pagination__info">
                Page {page + 1} of {totalPages}
              </span>
              <button
                className="btn btn--sm"
                disabled={page >= totalPages - 1}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>

      {/* Run detail modal */}
      {selectedRunId && (
        <RunDetailModal
          runSessionId={selectedRunId}
          onClose={() => setSelectedRunId(null)}
          scope={scope}
        />
      )}
    </div>
  );
}
