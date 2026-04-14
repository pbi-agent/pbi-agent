import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRunDetail } from "../../api";
import type { ObservabilityEvent, RunSession } from "../../types";
import { LoadingSpinner } from "../shared/LoadingSpinner";

export function RunDetailModal({
  runSessionId,
  onClose,
  scope,
}: {
  runSessionId: string;
  onClose: () => void;
  scope?: "workspace" | "global";
}) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const detailQuery = useQuery({
    queryKey: ["run-detail", runSessionId, scope],
    queryFn: () => fetchRunDetail(runSessionId, scope),
  });

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-card modal-card--wide"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Run detail"
      >
        <div className="modal-card__header">
          <h2 className="modal-card__title">Run Detail</h2>
          <button
            type="button"
            className="modal-card__close"
            onClick={onClose}
            aria-label="Close"
          >
            &times;
          </button>
        </div>

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
      </div>
    </div>
  );
}

function RunSummary({ run }: { run: RunSession }) {
  const statusModifier =
    run.status === "completed" ? "completed"
    : run.status === "failed" ? "failed"
    : run.status === "started" ? "running"
    : "idle";

  const durationLabel = run.total_duration_ms != null
    ? formatDurationLong(run.total_duration_ms)
    : "--";

  return (
    <div className="run-summary">
      <div className="run-summary__row">
        <SummaryField label="Status">
          <span className={`status-pill status-pill--${statusModifier}`}>{run.status}</span>
        </SummaryField>
        <SummaryField label="Agent">{run.agent_name ?? run.agent_type ?? "--"}</SummaryField>
        <SummaryField label="Provider">{run.provider ?? "--"}</SummaryField>
        <SummaryField label="Model">
          <span className="run-summary__mono">{run.model ?? "--"}</span>
        </SummaryField>
        <SummaryField label="Duration">{durationLabel}</SummaryField>
      </div>

      <div className="run-summary__row">
        <SummaryField label="Input tok">{fmt(run.input_tokens)}</SummaryField>
        <SummaryField label="Output tok">{fmt(run.output_tokens)}</SummaryField>
        <SummaryField label="Reasoning tok">{fmt(run.reasoning_tokens)}</SummaryField>
        <SummaryField label="Cached tok">{fmt(run.cached_input_tokens)}</SummaryField>
        <SummaryField label="Tool-use tok">{fmt(run.tool_use_tokens)}</SummaryField>
      </div>

      <div className="run-summary__row">
        <SummaryField label="API calls">{String(run.total_api_calls)}</SummaryField>
        <SummaryField label="Tool calls">{String(run.total_tool_calls)}</SummaryField>
        <SummaryField label="Errors">{String(run.error_count)}</SummaryField>
        <SummaryField label="Cost">{run.estimated_cost_usd > 0 ? `$${run.estimated_cost_usd.toFixed(4)}` : "--"}</SummaryField>
      </div>

      {run.started_at || run.ended_at ? (
        <div className="run-summary__row">
          <SummaryField label="Started">{formatFullTimestamp(run.started_at)}</SummaryField>
          <SummaryField label="Ended">{run.ended_at ? formatFullTimestamp(run.ended_at) : "--"}</SummaryField>
        </div>
      ) : null}
    </div>
  );
}

function SummaryField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="run-summary__field">
      <span className="run-summary__label">{label}</span>
      <span className="run-summary__value">{children}</span>
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
      <button
        type="button"
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

        {event.model ? (
          <span className="event-row__model">{event.model}</span>
        ) : null}

        <span className="event-row__spacer" />

        {event.success === false ? (
          <span className="event-row__badge event-row__badge--error">fail</span>
        ) : event.success === true ? (
          <span className="event-row__badge event-row__badge--ok">ok</span>
        ) : null}

        {event.status_code != null ? (
          <span className={`event-row__badge${event.status_code >= 400 ? " event-row__badge--error" : ""}`}>
            {event.status_code}
          </span>
        ) : null}

        {event.duration_ms != null ? (
          <span className="event-row__duration">{formatDurationShort(event.duration_ms)}</span>
        ) : event.tool_duration_ms != null ? (
          <span className="event-row__duration">{formatDurationShort(event.tool_duration_ms)}</span>
        ) : null}

        {event.total_tokens != null && event.total_tokens > 0 ? (
          <span className="event-row__tokens">{fmt(event.total_tokens)} tok</span>
        ) : null}

        {hasPayload ? (
          <svg className={`event-row__chevron${expanded ? " event-row__chevron--open" : ""}`} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="9 6 15 12 9 18" />
          </svg>
        ) : null}
      </button>

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
      <pre className="payload-section__content">{text}</pre>
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
