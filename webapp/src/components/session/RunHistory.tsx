import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSessionRuns } from "../../api";
import type { RunSession, UsagePayload } from "../../types";
import { StatusPill } from "../shared/StatusPill";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { RunDetailModal } from "./RunDetailModal";
import { UsageBar } from "./UsageBar";

export function RunHistory({
  sessionId,
  compactThreshold,
  usage,
}: {
  sessionId: string;
  compactThreshold: number | null;
  usage: UsagePayload | null;
}) {
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
        <div className="relative inline-flex">
          <DropdownMenuTrigger asChild>
            <UsageBar
              interactive
              tooltipSuppressed={isOpen}
              compactThreshold={compactThreshold}
              usage={usage}
            />
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="w-max max-w-screen min-w-70">
            {runsQuery.isLoading ? (
              <div className="flex items-center justify-center p-5 text-xs text-muted-foreground">
                <LoadingSpinner size="sm" />
              </div>
            ) : runsQuery.isError ? (
              <div className="flex items-center justify-center p-5 text-xs text-muted-foreground">Failed to load runs.</div>
            ) : !hasRuns ? (
              <div className="flex items-center justify-center p-5 text-xs text-muted-foreground">No runs recorded yet.</div>
            ) : (
              <div className="flex w-max max-w-full min-w-0 flex-col">
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
      className="flex w-full min-w-0 cursor-pointer flex-col items-stretch gap-px rounded-md px-2 py-1 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-1 focus-visible:ring-ring"
      onClick={onSelect}
    >
      <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
        <StatusPill status={run.status} size="meta" />
        <span className="max-w-34 min-w-0 truncate text-xs font-medium text-foreground" title={agentLabel}>{agentLabel}</span>
        {durationLabel ? <span className="shrink-0 font-mono text-xs whitespace-nowrap text-muted-foreground">{durationLabel}</span> : null}
      </div>
      <div className="flex max-w-full min-w-0 items-center overflow-hidden font-mono text-xs whitespace-nowrap text-muted-foreground" title={detailSummary}>
        <span className="block min-w-0 flex-1 truncate">{detailSummary}</span>
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
