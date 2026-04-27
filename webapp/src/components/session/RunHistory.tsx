import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2Icon, ChevronDownIcon, Clock3Icon, DotIcon } from "lucide-react";
import { fetchSessionRuns } from "../../api";
import type { RunSession } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { RunDetailModal } from "./RunDetailModal";

export function RunHistory({ sessionId }: { sessionId: string }) {
  const [selectedRun, setSelectedRun] = useState<RunSession | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const runsQuery = useQuery({
    queryKey: ["session-runs", sessionId],
    queryFn: () => fetchSessionRuns(sessionId),
    staleTime: 0,
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      return runs.some((run) => isRunActive(run.status)) ? 2_000 : false;
    },
  });

  const runs = [...(runsQuery.data ?? [])].sort(compareRunsNewestFirst);
  const hasRuns = runs.length > 0;

  return (
    <>
      <DropdownMenu open={isOpen} onOpenChange={(open) => {
        setIsOpen(open);
        if (open) void runsQuery.refetch();
      }}>
        <div className="run-history">
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="run-history__toggle"
              disabled={runsQuery.isLoading && !hasRuns}
              aria-label="Toggle run history"
            >
              <Clock3Icon data-icon="inline-start" />
              <span className="run-history__label">
                Runs{hasRuns ? ` (${runs.length})` : ""}
              </span>
              <ChevronDownIcon data-icon="inline-end" />
            </Button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="run-history__panel">
            {runsQuery.isLoading ? (
              <div className="run-history__loading">
                <LoadingSpinner size="sm" />
              </div>
            ) : runsQuery.isError ? (
              <div className="run-history__empty">Failed to load runs.</div>
            ) : !hasRuns ? (
              <div className="run-history__empty">No runs recorded yet.</div>
            ) : (
              <div className="run-history__list">
                {runs.map((run) => (
                  <RunCard
                    key={run.run_session_id}
                    run={run}
                    onSelect={() => {
                      setIsOpen(false);
                      setSelectedRun(run);
                    }}
                  />
                ))}
              </div>
            )}
          </DropdownMenuContent>
        </div>
      </DropdownMenu>

      {selectedRun ? (
        <RunDetailModal
          runSessionId={selectedRun.run_session_id}
          onClose={() => setSelectedRun(null)}
        />
      ) : null}
    </>
  );
}

function RunCard({
  run,
  onSelect,
}: {
  run: RunSession;
  onSelect: () => void;
}) {
  const statusModifier =
    run.status === "completed" ? "completed"
    : run.status === "failed" ? "failed"
    : run.status === "started" ? "running"
    : "idle";

  const agentLabel = run.agent_name ?? run.agent_type ?? "agent";
  const modelLabel = run.model ?? "unknown";
  const durationLabel = run.total_duration_ms != null
    ? formatDuration(run.total_duration_ms)
    : null;
  const totalTokens =
    run.input_tokens + run.output_tokens + run.reasoning_tokens + run.tool_use_tokens;

  return (
    <button
      type="button"
      className="run-card"
      onClick={onSelect}
    >
      <div className="run-card__header">
        <Badge variant="secondary" className={`run-card__status status-pill status-pill--${statusModifier}`}>
          {run.status}
        </Badge>
        <span className="run-card__agent">{agentLabel}</span>
        {run.parent_run_session_id ? (
          <Badge variant="outline" className="run-card__badge run-card__badge--sub">sub</Badge>
        ) : null}
      </div>
      <div className="run-card__meta">
        <span className="run-card__model">{modelLabel}</span>
        {run.provider ? (
          <>
            <DotIcon className="run-card__sep" aria-hidden="true" />
            <span>{run.provider}</span>
          </>
        ) : null}
        {durationLabel ? (
          <>
            <DotIcon className="run-card__sep" aria-hidden="true" />
            <span>{durationLabel}</span>
          </>
        ) : null}
      </div>
      <div className="run-card__stats">
        {totalTokens > 0 ? (
          <span className="run-card__stat">{formatCount(totalTokens)} tok</span>
        ) : null}
        {run.total_api_calls > 0 ? (
          <span className="run-card__stat">{run.total_api_calls} API calls</span>
        ) : null}
        {run.total_tool_calls > 0 ? (
          <span className="run-card__stat">{run.total_tool_calls} tool calls</span>
        ) : null}
        {run.error_count > 0 ? (
          <span className="run-card__stat run-card__stat--error">{run.error_count} errors</span>
        ) : null}
        {run.estimated_cost_usd > 0 ? (
          <span className="run-card__stat">${run.estimated_cost_usd.toFixed(4)}</span>
        ) : null}
      </div>
      <div className="run-card__time">
        <CheckCircle2Icon aria-hidden="true" />
        {formatTimestamp(run.started_at)}
      </div>
    </button>
  );
}

function isRunActive(status: string): boolean {
  return status !== "completed" && status !== "failed" && status !== "interrupted";
}

function compareRunsNewestFirst(a: RunSession, b: RunSession): number {
  return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rs = Math.round(s % 60);
  return `${m}m ${rs}s`;
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}
