import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDownIcon, Clock3Icon } from "lucide-react";
import { fetchSessionRuns } from "../../api";
import type { RunSession } from "../../types";
import { StatusPill } from "../shared/StatusPill";
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
              className="session-topbar-control run-history__toggle"
              disabled={runsQuery.isLoading && !hasRuns}
              aria-label="Toggle run history"
            >
              <Clock3Icon data-icon="inline-start" />
              <span className="run-history__label">
                {hasRuns ? `${runs.length}` : ""}
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
  const agentLabel = run.agent_name ?? run.agent_type ?? "agent";
  const modelLabel = run.model ?? "unknown";
  const totalTokens = totalRunTokens(run);
  const durationLabel = formatDuration(run.total_duration_ms);
  const detailSummary = [
    modelLabel,
    `${formatCount(totalTokens)} tok`,
    formatCost(run.estimated_cost_usd),
  ].join(" · ");

  return (
    <button
      type="button"
      className="run-card"
      onClick={onSelect}
    >
      <div className="run-card__header">
        <StatusPill status={run.status} size="meta" className="run-card__status" />
        <span className="run-card__agent" title={agentLabel}>{agentLabel}</span>
        {durationLabel ? <span className="run-card__duration">{durationLabel}</span> : null}
      </div>
      <div className="run-card__summary" title={detailSummary}>
        <span className="run-card__summary-text">{detailSummary}</span>
      </div>
    </button>
  );
}

function isRunActive(status: string): boolean {
  return !["completed", "interrupted", "ended", "failed", "stale"].includes(status);
}

function compareRunsNewestFirst(a: RunSession, b: RunSession): number {
  return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
}

function totalRunTokens(run: RunSession): number {
  if (run.provider_total_tokens > 0) return run.provider_total_tokens;
  return run.input_tokens + run.output_tokens + run.reasoning_tokens;
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatDuration(durationMs: number | null): string | null {
  if (durationMs === null) return null;
  if (durationMs <= 0) return "0s";
  const totalSeconds = Math.max(1, Math.round(durationMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h${minutes}m`;
  if (minutes > 0) return `${minutes}m${seconds}s`;
  return `${seconds}s`;
}

function formatCost(cost: number): string {
  if (cost === 0) return "$0.00";
  if (cost >= 0.01) return `$${cost.toFixed(2)}`;
  return `$${cost.toFixed(4)}`;
}
