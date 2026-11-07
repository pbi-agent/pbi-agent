import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon } from "lucide-react";
import { fetchAllRuns, fetchRunFilterValues } from "../../api";
import { EMPTY_SELECT_VALUE, fromSelectValue, toSelectValue } from "../../lib/selectValues";
import type { AllRunsRun } from "../../types";
import { StatusPill } from "../shared/StatusPill";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Empty, EmptyDescription, EmptyHeader } from "../ui/empty";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
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

function RunSessionTitle({ title }: { title: string | null }) {
  if (!title) return "--";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block truncate">{title}</span>
      </TooltipTrigger>
      <TooltipContent>{title}</TooltipContent>
    </Tooltip>
  );
}

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

  const filterValuesQuery = useQuery({
    queryKey: ["dashboard-run-filter-values", startDate, endDate, scope],
    queryFn: () =>
      fetchRunFilterValues({
        start_date: startDate,
        end_date: endDate,
        scope,
      }),
    staleTime: 60_000,
  });

  const totalCount = runsQuery.data?.total_count ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const runs = useMemo(() => runsQuery.data?.runs ?? [], [runsQuery.data?.runs]);
  const statusOptions = filterValuesQuery.data?.statuses ?? [];
  const providerOptions = filterValuesQuery.data?.providers ?? [];
  const modelOptions = filterValuesQuery.data?.models ?? [];

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
    return <span className="text-xs">{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>;
  }

  function handleRowClick(run: AllRunsRun) {
    setSelectedRunId(run.run_session_id);
  }

  function handleFilterChange() {
    setPage(0);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>All Runs</CardTitle>
        <CardAction>
        <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Run filters">
          <Select
            value={toSelectValue(statusFilter)}
            onValueChange={(value) => {
              setStatusFilter(fromSelectValue(value));
              handleFilterChange();
            }}
          >
            <SelectTrigger
              size="sm"
              aria-label="Status filter"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EMPTY_SELECT_VALUE}>All statuses</SelectItem>
              {statusOptions.map((status) => (
                <SelectItem key={status} value={status}>
                  {status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={toSelectValue(providerFilter)}
            onValueChange={(value) => {
              setProviderFilter(fromSelectValue(value));
              handleFilterChange();
            }}
          >
            <SelectTrigger
              size="sm"
              aria-label="Provider filter"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EMPTY_SELECT_VALUE}>All providers</SelectItem>
              {providerOptions.map((provider) => (
                <SelectItem key={provider} value={provider}>
                  {provider}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={toSelectValue(modelFilter)}
            onValueChange={(value) => {
              setModelFilter(fromSelectValue(value));
              handleFilterChange();
            }}
          >
            <SelectTrigger
              size="sm"
              className="max-w-64"
              aria-label="Model filter"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EMPTY_SELECT_VALUE}>All models</SelectItem>
              {modelOptions.map((model) => (
                <SelectItem key={model} value={model}>
                  {model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Badge variant="outline">{totalCount} total</Badge>
        </div>
        </CardAction>
      </CardHeader>

      <CardContent>
        {runsQuery.isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="md" />
          </div>
        ) : runsQuery.isError ? (
          <Alert variant="destructive">
            <AlertTriangleIcon />
            <AlertDescription>Failed to load runs.</AlertDescription>
          </Alert>
        ) : runs.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyDescription>No runs match the current filters.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <>
            <div className="@container min-w-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Status</TableHead>
                    <TableHead>Session</TableHead>
                    <TableHead className="hidden @5xl:table-cell">Agent</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="hidden @5xl:table-cell">Provider</TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("total_duration_ms")}>
                      Duration {sortIndicator("total_duration_ms")}
                      </Button>
                    </TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("input_tokens")}>
                      In tokens {sortIndicator("input_tokens")}
                      </Button>
                    </TableHead>
                    <TableHead>
                      <Button variant="ghost" size="sm" onClick={() => toggleSort("output_tokens")}>
                      Out tokens {sortIndicator("output_tokens")}
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
                      className="cursor-pointer"
                      data-run-id={run.run_session_id}
                      onClick={() => handleRowClick(run)}
                    >
                      <TableCell>
                        <StatusPill
                          status={run.status}
                          size="meta"
                        />
                      </TableCell>
                      <TableCell>
                        <div className="max-w-28 truncate">
                          <RunSessionTitle title={run.session_title} />
                        </div>
                      </TableCell>
                      <TableCell className="hidden @5xl:table-cell">{run.agent_name ?? "--"}</TableCell>
                      <TableCell><span className="font-mono">{run.model ?? "--"}</span></TableCell>
                      <TableCell className="hidden @5xl:table-cell">{run.provider ?? "--"}</TableCell>
                      <TableCell>{formatDuration(run.total_duration_ms)}</TableCell>
                      <TableCell>{formatNumber(run.input_tokens)}</TableCell>
                      <TableCell>{formatNumber(run.output_tokens)}</TableCell>
                      <TableCell>{formatCost(run.estimated_cost_usd)}</TableCell>
                      <TableCell>
                        <span className={run.error_count > 0 ? "text-destructive" : undefined}>
                          {run.error_count}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="whitespace-normal text-muted-foreground">{formatTimestamp(run.started_at)}</span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-end gap-3 pt-3">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
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
