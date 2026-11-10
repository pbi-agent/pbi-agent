import type { CSSProperties, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, Coins, Cpu, Database, Play, Sigma, Wrench, Zap } from "lucide-react";
import { fetchSessionRuns } from "../../api";
import type { UsagePayload } from "../../types";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { FormDialog } from "../ui/form-dialog";
import { Skeleton } from "../ui/skeleton";

const count = (value: number | undefined) => value == null ? "—" : value.toLocaleString();
const compact = (value: number | undefined) => value == null
  ? "—"
  : new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value);
const cost = (value: number | undefined) => value == null ? "—" : `$${value.toFixed(value >= 1 ? 2 : 4)}`;
const pct = (part: number, whole: number) => whole > 0 ? Math.min(100, (part / whole) * 100) : 0;
const FINISHED = ["completed", "interrupted", "ended", "failed", "stale"];

export function SessionStatusDialog({ sessionId, usage, compactThreshold, onClose }: {
  sessionId: string | null;
  usage: UsagePayload | null;
  compactThreshold: number | null;
  onClose: () => void;
}) {
  const runsQuery = useQuery({
    queryKey: ["session-runs", sessionId],
    queryFn: () => fetchSessionRuns(sessionId!),
    enabled: sessionId !== null,
    staleTime: 0,
    refetchInterval: (query) => query.state.data?.some((run) => !FINISHED.includes(run.status)) ? 2_000 : false,
  });
  const runs = runsQuery.data ?? [];
  const sum = (field: "total_api_calls" | "total_tool_calls" | "error_count") =>
    runs.reduce((total, run) => total + run[field], 0);

  const input = usage?.input_tokens ?? 0;
  const cached = Math.min(usage?.cached_input_tokens ?? 0, input);
  const output = usage?.output_tokens ?? 0;
  const tokenTotal = input + output;
  const cacheRate = pct(cached, input);
  const context = usage?.context_tokens ?? 0;
  const contextRate = compactThreshold ? pct(context, compactThreshold) : 0;
  const mainTokens = usage?.main_agent_total_tokens ?? 0;
  const subTokens = usage?.sub_agent_total_tokens ?? 0;

  return (
    <FormDialog open onOpenChange={(open) => { if (!open) onClose(); }}
      title="Session status" description="Live usage for this session, sub-agents included. No model request is made."
      size="lg">
      {!usage ? (
        <Alert><AlertDescription>No usage yet. Metrics appear after the first model response.</AlertDescription></Alert>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary"><Cpu data-icon="inline-start" />{usage?.model || "Model unknown"}</Badge>
        <Badge variant="outline">{usage ? `Tier: ${usage.service_tier || "default"}` : "Tier: —"}</Badge>
      </div>

      <div className="grid min-w-0 gap-3 sm:grid-cols-3">
        <Kpi accent="blue" icon={<Sigma />} label="Total tokens" value={compact(usage?.total_tokens)} hint={count(usage?.total_tokens)} />
        <Kpi accent="emerald" icon={<Coins />} label="Estimated cost" value={cost(usage?.estimated_cost_usd)} hint="USD estimate" />
        <Kpi accent="violet" icon={<Zap />} label="Reasoning" value={compact(usage?.reasoning_tokens)} hint="Within output" />
      </div>

      <Panel accent="blue" title="Token mix" aside={`${count(tokenTotal)} tokens`}>
        <StackedBar segments={[
          { label: "Cached input", value: cached, className: "bg-usage-cyan" },
          { label: "Fresh input", value: input - cached, className: "bg-usage-blue" },
          { label: "Output", value: output, className: "bg-usage-violet" },
        ]} total={tokenTotal} />
        {(usage?.cache_write_tokens || usage?.cache_write_1h_tokens) ? (
          <p className="text-xs text-muted-foreground">
            Cache writes: {count(usage?.cache_write_tokens)} · 1h: {count(usage?.cache_write_1h_tokens)}
          </p>
        ) : null}
      </Panel>

      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        <Panel accent="amber" title="Context window">
          <div className="flex items-center gap-4">
            <Ring value={contextRate} label={compactThreshold ? `${Math.round(contextRate)}%` : "—"}
              className={contextRate >= 85 ? "stroke-usage-rose" : contextRate >= 60 ? "stroke-usage-amber" : "stroke-usage-emerald"} />
            <div className="flex min-w-0 flex-col gap-0.5 text-sm">
              <span className="font-medium tabular-nums">{context > 0 ? count(context) : "No context yet"}</span>
              <span className="text-xs text-muted-foreground">
                {compactThreshold ? `of ${count(compactThreshold)} before compaction` : "Threshold unavailable"}
              </span>
            </div>
          </div>
        </Panel>
        <Panel accent="cyan" title="Cache efficiency">
          <div className="flex items-center gap-4">
            <Ring value={cacheRate} label={input > 0 ? `${Math.round(cacheRate)}%` : "—"} className="stroke-usage-cyan" />
            <div className="flex min-w-0 flex-col gap-0.5 text-sm">
              <span className="font-medium tabular-nums">{count(cached)} cached</span>
              <span className="text-xs text-muted-foreground">of {count(input)} input tokens</span>
            </div>
          </div>
        </Panel>
      </div>

      <Panel accent="violet" title="Agents" aside={subTokens > 0 ? `Sub-agents ${cost(usage?.sub_agent_cost_usd)}` : "No sub-agent usage"}>
        <StackedBar segments={[
          { label: "Main agent", value: mainTokens, className: "bg-usage-blue" },
          { label: "Sub-agents", value: subTokens, className: "bg-usage-violet" },
        ]} total={mainTokens + subTokens} />
      </Panel>

      <section className="flex flex-col gap-2" aria-label="Recorded activity">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-medium">Activity</h3>
          <span className="text-xs text-muted-foreground">Updates when runs finish</span>
        </div>
        {sessionId && runsQuery.isPending ? <Skeleton className="h-16 w-full" /> : runsQuery.isError ? (
          <Alert variant="destructive"><AlertDescription>
            Could not load recorded activity.
            <Button variant="outline" size="sm" onClick={() => void runsQuery.refetch()}>Retry</Button>
          </AlertDescription></Alert>
        ) : (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat accent="blue" icon={<Play />} label="Runs" value={count(runs.length)} />
            <Stat accent="cyan" icon={<Database />} label="API calls" value={count(sum("total_api_calls"))} />
            <Stat accent="violet" icon={<Wrench />} label="Tool calls" value={count(sum("total_tool_calls"))} />
            <Stat accent={sum("error_count") > 0 ? "rose" : "emerald"} icon={<AlertTriangle />} label="Errors" value={count(sum("error_count"))}
              tone={sum("error_count") > 0 ? "text-usage-rose" : undefined} />
          </div>
        )}
      </section>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Bot className="size-3.5" />Sub-agent usage is already included in totals. Cost is an estimate; unknown pricing shows $0.
      </p>
    </FormDialog>
  );
}

type Accent = "blue" | "cyan" | "violet" | "amber" | "emerald" | "rose";

const ACCENTS: Record<Accent, { card: string; icon: string; dot: string }> = {
  blue: { card: "border-usage-blue/30 bg-usage-blue/5", icon: "bg-usage-blue/15 text-usage-blue", dot: "bg-usage-blue" },
  cyan: { card: "border-usage-cyan/30 bg-usage-cyan/5", icon: "bg-usage-cyan/15 text-usage-cyan", dot: "bg-usage-cyan" },
  violet: { card: "border-usage-violet/30 bg-usage-violet/5", icon: "bg-usage-violet/15 text-usage-violet", dot: "bg-usage-violet" },
  amber: { card: "border-usage-amber/30 bg-usage-amber/5", icon: "bg-usage-amber/15 text-usage-amber", dot: "bg-usage-amber" },
  emerald: { card: "border-usage-emerald/30 bg-usage-emerald/5", icon: "bg-usage-emerald/15 text-usage-emerald", dot: "bg-usage-emerald" },
  rose: { card: "border-usage-rose/30 bg-usage-rose/5", icon: "bg-usage-rose/15 text-usage-rose", dot: "bg-usage-rose" },
};

function Panel({ title, aside, accent, children }: { title: string; aside?: string; accent: Accent; children: ReactNode }) {
  return (
    <section aria-label={title} className={cn("flex min-w-0 flex-col gap-3 rounded-lg border p-3", ACCENTS[accent].card)}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium"><span aria-hidden className={cn("size-2 rounded-full", ACCENTS[accent].dot)} />{title}</h3>
        {aside ? <span className="text-xs text-muted-foreground tabular-nums">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Kpi({ icon, label, value, hint, accent }: { icon: ReactNode; label: string; value: string; hint: string; accent: Accent }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1 rounded-lg border p-3", ACCENTS[accent].card)}>
      <span className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className={cn("flex size-6 items-center justify-center rounded-md [&_svg]:size-3.5", ACCENTS[accent].icon)}>{icon}</span>{label}
      </span>
      <span className="truncate text-2xl font-semibold tabular-nums">{value}</span>
      <span className="truncate text-xs text-muted-foreground tabular-nums">{hint}</span>
    </div>
  );
}

function Stat({ icon, label, value, tone, accent }: { icon: ReactNode; label: string; value: string; tone?: string; accent: Accent }) {
  return (
    <div className={cn("flex items-center gap-2.5 rounded-lg border p-2.5", ACCENTS[accent].card)}>
      <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-md [&_svg]:size-4", ACCENTS[accent].icon)}>{icon}</span>
      <div className="flex min-w-0 flex-col">
        <span className={cn("text-base font-semibold tabular-nums", tone)}>{value}</span>
        <span className="truncate text-xs text-muted-foreground">{label}</span>
      </div>
    </div>
  );
}

function StackedBar({ segments, total }: {
  segments: { label: string; value: number; className: string }[];
  total: number;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted" role="img"
        aria-label={segments.map((s) => `${s.label} ${s.value}`).join(", ")}>
        {segments.map((s) => s.value > 0 ? (
          <div key={s.label} className={cn("h-full w-(--seg-width)", s.className)}
            style={{ "--seg-width": `${pct(s.value, total)}%` } as CSSProperties} />
        ) : null)}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {segments.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", s.className)} />
            <span className="text-muted-foreground">{s.label}</span>
            <span className="font-medium tabular-nums">{count(s.value)}</span>
            <span className="text-muted-foreground tabular-nums">{total > 0 ? `${Math.round(pct(s.value, total))}%` : ""}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function Ring({ value, label, className }: { value: number; label: string; className: string }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative size-16 shrink-0">
      <svg viewBox="0 0 64 64" className="size-16 -rotate-90" aria-hidden="true">
        <circle cx="32" cy="32" r={r} fill="none" strokeWidth="6" className="stroke-muted" />
        <circle cx="32" cy="32" r={r} fill="none" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (value / 100) * c} className={cn("transition-all", className)} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold tabular-nums">{label}</span>
    </div>
  );
}
