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
import { Button } from "../ui/button";
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
      <div className="run-detail">
        {detailQuery.isLoading ? (
          <div className="run-detail__loading">
            <LoadingSpinner size="md" />
          </div>
        ) : detailQuery.isError ? (
          <div className="run-detail__error">Failed to load run details.</div>
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
    <section className="run-header" aria-label="Run summary">
      {/* Top bar: identity + key metrics */}
      <div className="run-header__topbar">
        <StatusPill status={run.status} size="meta" className="run-header__status" />
        <span className="run-header__agent">
          <BotIcon data-icon="inline-start" />
          {agentLabel}
        </span>
        <span className="run-header__sep" aria-hidden="true">·</span>
        <span className="run-header__model">
          {providerLabel}
          <span className="run-header__sep" aria-hidden="true">/</span>
          <span className="run-header__model-name">{modelLabel}</span>
        </span>
        {reasoningEffortLabel ? (
          <>
            <span className="run-header__sep" aria-hidden="true">·</span>
            <span className="run-header__model">{reasoningEffortLabel}</span>
          </>
        ) : null}
        <span className="run-header__topbar-spacer" />
        <span className="run-header__kpi">
          <ClockIcon />
          <span className="run-header__kpi-value">{durationLabel}</span>
        </span>
        <span className="run-header__kpi-divider" aria-hidden="true" />
        <span className="run-header__kpi run-header__kpi--accent">
          <CircleDollarSignIcon />
          <span className="run-header__kpi-value">{costLabel}</span>
        </span>
      </div>

      {run.fatal_error ? (
        <Alert variant="destructive" className="run-header__alert">
          <TriangleAlertIcon />
          <AlertDescription>{run.fatal_error}</AlertDescription>
        </Alert>
      ) : null}

      {/* Stats grid — all metrics in one uniform row */}
      <div className="run-header__grid">
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
        <div className="run-header__timeline">
          {run.started_at ? (
            <span className="run-header__time">
              <ClockIcon data-icon="inline-start" />
              <span className="run-header__time-label">Started</span>
              <span>{formatFullTimestamp(run.started_at)}</span>
            </span>
          ) : null}
          {run.started_at && run.ended_at ? (
            <ChevronRightIcon className="run-header__time-arrow" aria-hidden="true" />
          ) : null}
          {run.ended_at ? (
            <span className="run-header__time">
              <span className="run-header__time-label">Ended</span>
              <span>{formatFullTimestamp(run.ended_at)}</span>
            </span>
          ) : null}
        </div>
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
    <div className={`run-header__cell${tone === "danger" ? " run-header__cell--danger" : ""}`}>
      <span className="run-header__cell-value">
        {Icon ? <Icon /> : null}
        {value}
      </span>
      <span className="run-header__cell-label">{label}</span>
    </div>
  );
}

function EventTimeline({ events }: { events: ObservabilityEvent[] }) {
  if (events.length === 0) {
    return <div className="run-detail__empty">No events recorded for this run.</div>;
  }

  return (
    <div className="event-timeline">
      <h3 className="event-timeline__heading">Events ({events.length})</h3>
      <div className="event-timeline__list">
        {events.map((event) => (
          <EventRow key={`${event.run_session_id}-${event.step_index}`} event={event} />
        ))}
      </div>
    </div>
  );
}

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
    <div className={`event-row event-row--${typeModifier}`}>
      <Button
        type="button"
        variant="ghost"
        className="event-row__header"
        onClick={() => { if (hasPayload) setExpanded((v) => !v); }}
        aria-expanded={hasPayload ? expanded : undefined}
        disabled={!hasPayload}
      >
        <span className="event-row__index">#{event.step_index}</span>
        <span className={`event-row__type event-row__type--${typeModifier}`}>{event.event_type}</span>

        {event.tool_name ? (
          <span className="event-row__tool">{event.tool_name}</span>
        ) : null}

        <span className="event-row__spacer" />

        {event.success === false ? (
          <StatusPill status="failed" size="meta" className="event-row__status">fail</StatusPill>
        ) : event.success === true ? (
          <StatusPill status="completed" size="meta" className="event-row__status">ok</StatusPill>
        ) : null}

        {event.duration_ms != null ? (
          <span className="event-row__duration">{formatDurationShort(event.duration_ms)}</span>
        ) : event.tool_duration_ms != null ? (
          <span className="event-row__duration">{formatDurationShort(event.tool_duration_ms)}</span>
        ) : null}

        {event.total_tokens != null && event.total_tokens > 0 ? (
          <span className="event-row__tokens">{fmt(event.total_tokens)}</span>
        ) : null}

        {hasPayload ? (
          <ChevronRightIcon className={`event-row__chevron${expanded ? " event-row__chevron--open" : ""}`} aria-hidden="true" />
        ) : null}
      </Button>

      {expanded && hasPayload ? (
        <div className="event-row__body">
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

          <div className="event-row__meta-row">
            {event.provider ? <span>Provider: {event.provider}</span> : null}
            {event.url ? <span className="event-row__url">URL: {event.url}</span> : null}
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
    <div className={`payload-section${variant === "error" ? " payload-section--error" : ""}`}>
      <span className="payload-section__label">{label}</span>
      <div className="payload-section__content-card">
        <pre className="payload-section__content">{text}</pre>
        <CopyShortcut
          text={text}
          ariaLabel={`Copy ${label}`}
          className="timeline-entry__action-button payload-section__copy"
        />
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
