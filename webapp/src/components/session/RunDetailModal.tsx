import { createContext, useContext, useMemo, useState } from "react";
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
import { fetchRunDetail, fetchRunEvent } from "../../api";
import type { ObservabilityEventSummary, RunDetail, RunSession } from "../../types";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { FormDialog } from "../ui/form-dialog";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { CopyShortcut } from "../shared/CopyShortcut";
import { Alert, AlertDescription } from "../ui/alert";
import { StatusPill } from "../shared/StatusPill";
import { Badge } from "../ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "../ui/collapsible";
import { TruncatedText } from "../TruncatedText";
import {
  buildRunTrace,
  countSpans,
  formatSpanDuration,
  type TraceSpan,
  type TraceSpanType,
} from "./runTrace";

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
            <TraceTimeline detail={detailQuery.data} scope={scope} />
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
    ? formatSpanDuration(run.total_duration_ms)
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

type RunScope = "workspace" | "global" | undefined;

type TraceUi = {
  scope: RunScope;
  /** Span ids whose children are collapsed. */
  collapsed: ReadonlySet<string>;
  /** Span ids whose payload details are open. */
  detailsOpen: ReadonlySet<string>;
  toggleCollapsed: (spanId: string) => void;
  toggleDetails: (spanId: string) => void;
};

const TraceUiContext = createContext<TraceUi | null>(null);

function useTraceUi(): TraceUi {
  const ui = useContext(TraceUiContext);
  if (!ui) throw new Error("Trace rows must render inside TraceTimeline.");
  return ui;
}

function toggled(ids: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(ids);
  if (!next.delete(id)) next.add(id);
  return next;
}

function TraceTimeline({ detail, scope }: { detail: RunDetail; scope: RunScope }) {
  const root = useMemo(() => buildRunTrace(detail), [detail]);
  // Row state lives here, keyed by span id, so it survives a parent row being
  // collapsed (which unmounts its children) and rows moving while a run is live.
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  const [detailsOpen, setDetailsOpen] = useState<ReadonlySet<string>>(() => new Set());
  const ui = useMemo<TraceUi>(
    () => ({
      scope,
      collapsed,
      detailsOpen,
      toggleCollapsed: (spanId) => setCollapsed((ids) => toggled(ids, spanId)),
      toggleDetails: (spanId) => setDetailsOpen((ids) => toggled(ids, spanId)),
    }),
    [scope, collapsed, detailsOpen],
  );

  if (root.children.length === 0 && root.status !== "running") {
    return (
      <div className="p-5 text-center text-sm text-muted-foreground">
        No events recorded for this run.
      </div>
    );
  }

  return (
    <TraceUiContext.Provider value={ui}>
      <div className="@container/trace flex min-w-0 flex-col gap-2">
        <h3 className="text-sm font-semibold text-foreground">Trace ({countSpans(root)})</h3>
        <TraceRow span={root} isRoot />
      </div>
    </TraceUiContext.Provider>
  );
}

const SPAN_TYPE_LABEL: Record<TraceSpanType, string> = {
  agent: "Agent",
  chat: "Chat",
  tool: "Tool",
  hook: "Hook",
  error: "Error",
  event: "Event",
};

const SPAN_TYPE_VARIANT = {
  agent: "trace-agent",
  chat: "trace-chat",
  tool: "trace-tool",
  hook: "trace-event",
  error: "trace-error",
  event: "trace-event",
} as const satisfies Record<TraceSpanType, string>;

function TraceRow({ span, isRoot = false }: { span: TraceSpan; isRoot?: boolean }) {
  const ui = useTraceUi();
  const childrenOpen = !ui.collapsed.has(span.id);
  const event = span.event;
  const hasChildren = span.children.length > 0;
  const hasDetails = event != null && (event.has_payload || Boolean(event.error_message));
  const showDetails = hasDetails && ui.detailsOpen.has(span.id);

  return (
    <Collapsible open={childrenOpen} onOpenChange={() => ui.toggleCollapsed(span.id)}>
      <div
        data-slot="trace-span"
        data-span-type={span.type}
        data-root={isRoot ? "" : undefined}
        className="min-w-0 overflow-hidden rounded-2xl border border-border/60 bg-card shadow-sm transition-colors duration-200 animate-in fade-in slide-in-from-bottom-1 hover:border-border hover:bg-muted/50 motion-reduce:animate-none data-root:border-trace-bar/60"
      >
        <div className="flex items-center gap-1 pr-4 pl-2">
          {hasChildren ? (
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`${childrenOpen ? "Collapse" : "Expand"} ${span.label}`}
              >
                <ChevronRightIcon
                  data-open={childrenOpen ? "true" : "false"}
                  className="transition-transform data-[open=true]:rotate-90"
                  aria-hidden="true"
                />
              </Button>
            </CollapsibleTrigger>
          ) : (
            <span className="size-7 shrink-0" aria-hidden="true" />
          )}
          <button
            type="button"
            className="flex min-h-14 min-w-0 flex-1 items-center gap-3 rounded-md text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/50 enabled:cursor-pointer in-data-root:min-h-16"
            onClick={() => ui.toggleDetails(span.id)}
            aria-expanded={hasDetails ? showDetails : undefined}
            disabled={!hasDetails}
          >
            <TruncatedText className="min-w-0 flex-1 truncate text-base font-medium text-foreground in-data-root:font-semibold">
              {span.label}
            </TruncatedText>
            {span.status === "failed" ? (
              <StatusPill status="failed" size="meta" data-span-status="">fail</StatusPill>
            ) : span.status === "running" && !isRoot ? (
              <StatusPill status="running" size="meta" data-span-status="">running</StatusPill>
            ) : null}
            <span className="flex w-16 shrink-0 justify-center">
              <Badge variant={SPAN_TYPE_VARIANT[span.type]} size="meta">
                {SPAN_TYPE_LABEL[span.type]}
              </Badge>
            </span>
            <span className="w-20 shrink-0 font-mono text-sm whitespace-nowrap text-muted-foreground tabular-nums">
              {span.durationMs != null ? formatSpanDuration(span.durationMs) : ""}
            </span>
            <span
              data-slot="trace-bar-track"
              className="relative h-2 w-32 shrink-0 @max-lg/trace:hidden @3xl/trace:w-64"
              aria-hidden="true"
            >
              {span.bar ? (
                <span
                  data-slot="trace-bar"
                  className="absolute inset-y-0 left-(--trace-bar-offset) w-(--trace-bar-width) origin-left animate-trace-bar rounded-full bg-trace-bar shadow-sm shadow-trace-bar/60 motion-reduce:animate-none"
                  style={{
                    "--trace-bar-offset": `${(span.bar.offset * 100).toFixed(2)}%`,
                    "--trace-bar-width": `${(span.bar.width * 100).toFixed(2)}%`,
                  } as React.CSSProperties}
                />
              ) : null}
            </span>
          </button>
        </div>

        {showDetails ? <SpanDetails event={event} /> : null}
      </div>

      {hasChildren ? (
        <CollapsibleContent animated>
          <div className="flex min-w-0 flex-col gap-2 pt-2 pl-5 @2xl/trace:pl-8">
            {span.children.map((child) => (
              <TraceRow key={child.id} span={child} />
            ))}
          </div>
        </CollapsibleContent>
      ) : null}
    </Collapsible>
  );
}

function SpanDetails({ event }: { event: ObservabilityEventSummary }) {
  const { scope } = useTraceUi();
  // Payloads can be large, so they are fetched per event when a row is opened.
  // A recorded event never changes, so it is fetched once.
  const payloadQuery = useQuery({
    queryKey: ["run-event", event.run_session_id, event.step_index, scope],
    queryFn: () => fetchRunEvent(event.run_session_id, event.step_index, scope),
    enabled: event.has_payload,
    staleTime: Infinity,
  });
  const full = payloadQuery.data;

  return (
    <div className="flex min-w-0 flex-col gap-3 border-t border-border p-3">
      {event.error_message ? (
        <PayloadSection label="Error" value={event.error_message} variant="error" />
      ) : null}
      {payloadQuery.isLoading ? (
        <div className="flex items-center justify-center p-3">
          <LoadingSpinner size="sm" />
        </div>
      ) : payloadQuery.isError ? (
        <div className="text-sm text-destructive">Failed to load event details.</div>
      ) : null}
      {full ? (
        <>
          {full.tool_input != null ? <PayloadSection label="Tool Input" value={full.tool_input} /> : null}
          {full.tool_output != null ? <PayloadSection label="Tool Output" value={full.tool_output} /> : null}
          {full.request_payload != null ? <PayloadSection label="Request" value={full.request_payload} /> : null}
          {full.response_payload != null ? <PayloadSection label="Response" value={full.response_payload} /> : null}
          {full.request_config != null ? <PayloadSection label="Config" value={full.request_config} /> : null}
          {hasContent(full.metadata) ? <PayloadSection label="Metadata" value={full.metadata} /> : null}
        </>
      ) : null}

      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-muted-foreground">
        <span>Step: #{event.step_index}</span>
        {event.provider ? <span>Provider: {event.provider}</span> : null}
        {event.url ? <span className="break-all">URL: {event.url}</span> : null}
        {event.tool_call_id ? <span>Call ID: {event.tool_call_id}</span> : null}
        {event.prompt_tokens != null ? <span>Prompt: {fmt(event.prompt_tokens)} tok</span> : null}
        {event.completion_tokens != null ? <span>Completion: {fmt(event.completion_tokens)} tok</span> : null}
        {event.total_tokens != null && event.total_tokens > 0 ? (
          <span>Total: {fmt(event.total_tokens)} tok</span>
        ) : null}
        <span>Time: {formatFullTimestamp(event.timestamp)}</span>
      </div>
    </div>
  );
}

function hasContent(value: unknown): boolean {
  if (value == null) return false;
  return typeof value !== "object" || Object.keys(value).length > 0;
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
