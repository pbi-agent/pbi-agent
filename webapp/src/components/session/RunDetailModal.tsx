import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ActivityIcon,
  BotIcon,
  BrainIcon,
  ChevronRightIcon,
  CircleDollarSignIcon,
  ClockIcon,
  DatabaseIcon,
  ServerIcon,
  TerminalIcon,
  TriangleAlertIcon,
  WrenchIcon,
  XIcon,
} from "lucide-react";
import { fetchRunDetail } from "../../api";
import type { ObservabilityEvent, RunSession } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
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
    <Dialog open onOpenChange={(open) => {
      if (!open) onClose();
    }}>
      <DialogContent className="modal-card--wide" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Run Detail</DialogTitle>
          <DialogDescription className="sr-only">Detailed metrics and event timeline for this agent run</DialogDescription>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="modal-card__close"
            onClick={onClose}
            aria-label="Close"
          >
            <XIcon />
          </Button>
        </DialogHeader>

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
      </DialogContent>
    </Dialog>
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
    <div className="run-kpi" aria-label="Run key performance indicators">
      {/* Hero row */}
      <div className="run-kpi__hero">
        <div className="run-kpi__hero-card">
          <span className="run-kpi__hero-label">Status</span>
          <Badge variant="secondary" className={`status-pill status-pill--${statusModifier}`}>{run.status}</Badge>
        </div>
        <div className="run-kpi__hero-card">
          <span className="run-kpi__hero-label"><ClockIcon data-icon="inline-start" /> Duration</span>
          <span className="run-kpi__hero-value">{durationLabel}</span>
        </div>
        <div className="run-kpi__hero-card">
          <span className="run-kpi__hero-label"><CircleDollarSignIcon data-icon="inline-start" /> Cost</span>
          <span className="run-kpi__hero-value">{run.estimated_cost_usd > 0 ? `$${run.estimated_cost_usd.toFixed(4)}` : "--"}</span>
        </div>
      </div>

      {/* Counters row */}
      <div className="run-kpi__counters">
        <KpiCounter icon={ServerIcon} label="API calls" value={run.total_api_calls} />
        <KpiCounter icon={WrenchIcon} label="Tool calls" value={run.total_tool_calls} />
        <KpiCounter icon={TriangleAlertIcon} label="Errors" value={run.error_count} variant={run.error_count > 0 ? "danger" : undefined} />
      </div>

      {/* Token breakdown */}
      <div className="run-kpi__tokens">
        <h4 className="run-kpi__tokens-heading"><ActivityIcon data-icon="inline-start" /> Tokens</h4>
        <div className="run-kpi__tokens-grid">
          <TokenStat label="Input" value={run.input_tokens} />
          <TokenStat label="Output" value={run.output_tokens} />
          <TokenStat label="Reasoning" value={run.reasoning_tokens} icon={BrainIcon} />
          <TokenStat label="Cached" value={run.cached_input_tokens} icon={DatabaseIcon} />
          <TokenStat label="Tool-use" value={run.tool_use_tokens} icon={TerminalIcon} />
        </div>
      </div>

      {/* Meta footer */}
      <div className="run-kpi__meta">
        <MetaItem icon={BotIcon} label="Agent" value={run.agent_name ?? run.agent_type ?? "--"} />
        <MetaItem icon={ServerIcon} label="Provider" value={run.provider ?? "--"} />
        <MetaItem label="Model" value={run.model ?? "--"} mono />
        {run.started_at ? <MetaItem icon={ClockIcon} label="Started" value={formatFullTimestamp(run.started_at)} /> : null}
        {run.ended_at ? <MetaItem icon={ClockIcon} label="Ended" value={formatFullTimestamp(run.ended_at)} /> : null}
      </div>
    </div>
  );
}

function KpiCounter({ icon: Icon, label, value, variant }: { icon: React.ComponentType<React.SVGProps<SVGSVGElement>>; label: string; value: number; variant?: "danger" }) {
  return (
    <span className={`run-kpi__counter${variant === "danger" ? " run-kpi__counter--danger" : ""}`}>
      <Icon data-icon="inline-start" />
      <span className="run-kpi__counter-value">{value}</span>
      <span className="run-kpi__counter-label">{label}</span>
    </span>
  );
}

function TokenStat({ label, value, icon: Icon }: { label: string; value: number; icon?: React.ComponentType<React.SVGProps<SVGSVGElement>> }) {
  return (
    <div className="run-kpi__token-stat">
      <span className="run-kpi__token-label">{Icon ? <Icon data-icon="inline-start" /> : null}{label}</span>
      <span className="run-kpi__token-value">{fmt(value)}</span>
    </div>
  );
}

function MetaItem({ icon: Icon, label, value, mono }: { icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>; label: string; value: string; mono?: boolean }) {
  return (
    <span className="run-kpi__meta-item">
      {Icon ? <Icon data-icon="inline-start" /> : null}
      <span className="run-kpi__meta-label">{label}:</span>
      <span className={mono ? "run-kpi__meta-value--mono" : undefined}>{value}</span>
    </span>
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

        {event.model ? (
          <span className="event-row__model">{event.model}</span>
        ) : null}

        <span className="event-row__spacer" />

        {event.success === false ? (
          <Badge variant="destructive" className="event-row__badge event-row__badge--error">fail</Badge>
        ) : event.success === true ? (
          <Badge variant="secondary" className="event-row__badge event-row__badge--ok">ok</Badge>
        ) : null}

        {event.status_code != null ? (
          <Badge variant={event.status_code >= 400 ? "destructive" : "secondary"} className={`event-row__badge${event.status_code >= 400 ? " event-row__badge--error" : ""}`}>
            {event.status_code}
          </Badge>
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