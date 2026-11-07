import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BotIcon,
  BrainIcon,
  ChevronRightIcon,
  CircleDollarSignIcon,
  ClockIcon,
  DatabaseIcon,
  ServerIcon,
  TriangleAlertIcon,
  WrenchIcon,
} from "lucide-react";
import { fetchRunDetail } from "../../api";
import type { ObservabilityEvent, RunSession } from "../../types";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { FormDialog } from "../ui/form-dialog";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { CopyShortcut } from "../shared/CopyShortcut";
import { Alert, AlertDescription } from "../ui/alert";
import { StatusPill } from "../shared/StatusPill";

export function RunDetailModal({
  runSessionId,
  onClose,
  scope,
}: {
  runSessionId: string;
  onClose: () => void;
  scope?: "workspace" | "global";
}) {
  const detailQuery = useQuery({
    queryKey: ["run-detail", runSessionId, scope],
    queryFn: () => fetchRunDetail(runSessionId, scope),
    refetchInterval: (query) => {
      const run = query.state.data?.run;
      return run && isRunActive(run.status) ? 2_000 : false;
    },
  });

  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Run Detail"
      description="Detailed metrics and event timeline for this agent run"
      size="wide"
    >
      <div className="flex min-w-0 flex-col gap-4">
        {detailQuery.isLoading ? (
          <div className="flex items-center justify-center p-8">
            <LoadingSpinner size="md" />
          </div>
        ) : detailQuery.isError ? (
          <div className="p-5 text-center text-sm text-destructive">Failed to load run details.</div>
        ) : detailQuery.data ? (
          <>
            <RunSummary run={detailQuery.data.run} />
            <EventTimeline events={detailQuery.data.events} />
          </>
        ) : null}
      </div>
    </FormDialog>
  );
}

function isRunActive(status: string): boolean {
  return !["completed", "interrupted", "ended", "failed", "stale"].includes(status);
}

function RunSummary({ run }: { run: RunSession }) {
  const durationLabel = run.total_duration_ms != null
    ? formatDurationLong(run.total_duration_ms)
    : "--";
  const costLabel = run.estimated_cost_usd > 0
    ? `$${run.estimated_cost_usd.toFixed(4)}`
    : "--";
  const agentLabel = run.agent_name ?? run.agent_type ?? "--";
  const providerLabel = run.provider ?? "--";
  const modelLabel = run.model ?? "--";
  const reasoningEffort = run.reasoning_effort?.trim();
  const reasoningEffortLabel = reasoningEffort && reasoningEffort.toLowerCase() !== "none"
    ? reasoningEffort
    : null;
  const hasTimeline = Boolean(run.started_at || run.ended_at);

  return (
    <section
      className="flex flex-col overflow-hidden rounded-lg border border-border bg-muted/40"
      aria-label="Run summary"
    >
      {/* Top bar: identity + key metrics */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <StatusPill status={run.status} size="meta" data-run-status="" />
        <span className="inline-flex items-center gap-1 text-sm font-semibold whitespace-nowrap text-foreground">
          <BotIcon className="size-3.5 text-muted-foreground" />
          {agentLabel}
        </span>
        <span className="text-muted-foreground/50" aria-hidden="true">·</span>
        <span className="inline-flex items-center gap-0.5 font-mono text-xs whitespace-nowrap text-muted-foreground">
          {providerLabel}
          <span className="text-muted-foreground/50" aria-hidden="true">/</span>
          <span className="text-foreground">{modelLabel}</span>
        </span>
        {reasoningEffortLabel ? (
          <>
            <span className="text-muted-foreground/50" aria-hidden="true">·</span>
            <span className="inline-flex items-center font-mono text-xs whitespace-nowrap text-muted-foreground">
              {reasoningEffortLabel}
            </span>
          </>
        ) : null}
        <span className="flex-1" />
        <span className="inline-flex items-center gap-1 font-mono text-sm whitespace-nowrap text-muted-foreground">
          <ClockIcon className="size-3.5 opacity-60" />
          <span className="font-semibold text-foreground">{durationLabel}</span>
        </span>
        <Separator orientation="vertical" className="h-5" />
        <span className="inline-flex items-center gap-1 font-mono text-sm whitespace-nowrap text-muted-foreground">
          <CircleDollarSignIcon className="size-3.5 opacity-60" />
          <span className="text-base font-semibold text-foreground">{costLabel}</span>
        </span>
      </div>

      {run.fatal_error ? (
        <div className="px-4 pb-3">
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertDescription>{run.fatal_error}</AlertDescription>
          </Alert>
        </div>
      ) : null}

      <Separator />

      {/* Stats grid — all metrics in one uniform row */}
      <div className="grid grid-cols-4 gap-px bg-border sm:grid-cols-7">
        <KpiCell icon={ServerIcon} value={fmt(run.total_api_calls)} label="API" />
        <KpiCell icon={WrenchIcon} value={fmt(run.total_tool_calls)} label="Tools" />
        <KpiCell
          icon={TriangleAlertIcon}
          value={fmt(run.error_count)}
          label="Errors"
          tone={run.error_count > 0 ? "danger" : undefined}
        />
        <KpiCell value={fmt(run.input_tokens)} label="Input" />
        <KpiCell value={fmt(run.output_tokens)} label="Output" />
        <KpiCell icon={BrainIcon} value={fmt(run.reasoning_tokens)} label="Reasoning" />
        <KpiCell icon={DatabaseIcon} value={fmt(run.cached_input_tokens)} label="Cached" />
      </div>

      {/* Timeline footer */}
      {hasTimeline ? (
        <>
          <Separator />
          <div className="flex flex-wrap items-center gap-2 px-4 py-2 font-mono text-xs text-muted-foreground">
            {run.started_at ? (
              <span className="inline-flex items-center gap-1">
                <ClockIcon className="size-3" />
                <span className="font-sans font-medium">Started</span>
                <span>{formatFullTimestamp(run.started_at)}</span>
              </span>
            ) : null}
            {run.started_at && run.ended_at ? (
              <ChevronRightIcon className="size-3 opacity-60" aria-hidden="true" />
            ) : null}
            {run.ended_at ? (
              <span className="inline-flex items-center gap-1">
                <span className="font-sans font-medium">Ended</span>
                <span>{formatFullTimestamp(run.ended_at)}</span>
              </span>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

function KpiCell({
  icon: Icon,
  value,
  label,
  tone,
}: {
  icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  value: string;
  label: string;
  tone?: "danger";
}) {
  return (
    <div
      data-tone={tone}
      className="group/kpi flex flex-col items-center gap-0.5 bg-card px-2 py-2 text-center"
    >
      <span className="inline-flex items-center gap-1 font-mono text-sm font-semibold text-foreground group-data-[tone=danger]/kpi:text-destructive">
        {Icon ? <Icon className="size-3 opacity-60" /> : null}
        {value}
      </span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

function EventTimeline({ events }: { events: ObservabilityEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="p-5 text-center text-sm text-muted-foreground">
        No events recorded for this run.
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <h3 className="text-sm font-semibold text-foreground">Events ({events.length})</h3>
      <div className="flex min-w-0 flex-col gap-1">
        {events.map((event) => (
          <EventRow key={`${event.run_session_id}-${event.step_index}`} event={event} />
        ))}
      </div>
    </div>
  );
}

const EVENT_TYPE_CLASS_NAME: Record<string, string> = {
  api: "text-primary",
  tool: "text-primary",
  error: "text-destructive",
  lifecycle: "text-foreground",
  step: "text-muted-foreground",
  default: "text-muted-foreground",
};

function EventRow({ event }: { event: ObservabilityEvent }) {
  const [expanded, setExpanded] = useState(false);

  const typeModifier = eventTypeModifier(event.event_type);
  const hasPayload = Boolean(
    event.request_payload
    || event.response_payload
    || event.tool_input
    || event.tool_output
    || event.error_message
    || event.request_config
    || event.metadata,
  );

  return (
    <div
      data-event-type={typeModifier}
      className="min-w-0 overflow-hidden rounded-md border border-border bg-card"
    >
      <Button
        type="button"
        variant="ghost"
        className="w-full justify-start"
        onClick={() => { if (hasPayload) setExpanded((v) => !v); }}
        aria-expanded={hasPayload ? expanded : undefined}
        disabled={!hasPayload}
      >
        <span className="font-mono text-xs text-muted-foreground">#{event.step_index}</span>
        <span className={cn("font-mono text-xs font-medium", EVENT_TYPE_CLASS_NAME[typeModifier])}>
          {event.event_type}
        </span>

        {event.tool_name ? (
          <span className="truncate font-mono text-xs text-foreground">{event.tool_name}</span>
        ) : null}

        <span className="flex-1" />

        {event.success === false ? (
          <StatusPill status="failed" size="meta" data-event-status="">fail</StatusPill>
        ) : event.success === true ? (
          <StatusPill status="completed" size="meta" data-event-status="">ok</StatusPill>
        ) : null}

        {event.duration_ms != null ? (
          <span className="font-mono text-xs text-muted-foreground">{formatDurationShort(event.duration_ms)}</span>
        ) : event.tool_duration_ms != null ? (
          <span className="font-mono text-xs text-muted-foreground">{formatDurationShort(event.tool_duration_ms)}</span>
        ) : null}

        {event.total_tokens != null && event.total_tokens > 0 ? (
          <span className="font-mono text-xs text-muted-foreground">{fmt(event.total_tokens)}</span>
        ) : null}

        {hasPayload ? (
          <ChevronRightIcon
            data-open={expanded ? "true" : "false"}
            className="text-muted-foreground transition-transform data-[open=true]:rotate-90"
            aria-hidden="true"
          />
        ) : null}
      </Button>

      {expanded && hasPayload ? (
        <div className="flex min-w-0 flex-col gap-3 border-t border-border p-3">
          {event.error_message ? (
            <PayloadSection label="Error" value={event.error_message} variant="error" />
          ) : null}
          {event.tool_name ? (
            <>
              {event.tool_input != null ? <PayloadSection label="Tool Input" value={event.tool_input} /> : null}
              {event.tool_output != null ? <PayloadSection label="Tool Output" value={event.tool_output} /> : null}
            </>
          ) : null}
          {event.request_payload != null ? <PayloadSection label="Request" value={event.request_payload} /> : null}
          {event.response_payload != null ? <PayloadSection label="Response" value={event.response_payload} /> : null}
          {event.request_config != null ? <PayloadSection label="Config" value={event.request_config} /> : null}
          {event.metadata != null ? <PayloadSection label="Metadata" value={event.metadata} /> : null}

          <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-muted-foreground">
            {event.provider ? <span>Provider: {event.provider}</span> : null}
            {event.url ? <span className="break-all">URL: {event.url}</span> : null}
            {event.tool_call_id ? <span>Call ID: {event.tool_call_id}</span> : null}
            {event.prompt_tokens != null ? <span>Prompt: {fmt(event.prompt_tokens)} tok</span> : null}
            {event.completion_tokens != null ? <span>Completion: {fmt(event.completion_tokens)} tok</span> : null}
            <span>Time: {formatFullTimestamp(event.timestamp)}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PayloadSection({
  label,
  value,
  variant,
}: {
  label: string;
  value: unknown;
  variant?: "error";
}) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);

  return (
    <div data-variant={variant} className="group/payload flex min-w-0 flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="relative min-w-0 rounded-md border border-border bg-muted group-data-[variant=error]/payload:border-destructive/40 group-data-[variant=error]/payload:bg-destructive/10">
        <pre className="max-h-80 overflow-auto p-3 pr-12 font-mono text-xs leading-normal break-words whitespace-pre-wrap text-foreground">
          {text}
        </pre>
        <div className="absolute top-2 right-2">
          <CopyShortcut text={text} ariaLabel={`Copy ${label}`} />
        </div>
      </div>
    </div>
  );
}

function eventTypeModifier(eventType: string): string {
  if (eventType.includes("error") || eventType === "run_error") return "error";
  if (eventType.includes("tool")) return "tool";
  if (eventType.includes("model") || eventType === "api_call") return "api";
  if (eventType === "run_start" || eventType === "run_end") return "lifecycle";
  if (eventType.includes("step")) return "step";
  return "default";
}

function formatDurationLong(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rs = Math.round(s % 60);
  return `${m}m ${rs}s`;
}

function formatDurationShort(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatFullTimestamp(iso: string): string {
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
