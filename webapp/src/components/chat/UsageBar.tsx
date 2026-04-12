import type { UsagePayload } from "../../types";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function UsageBar({
  sessionUsage,
  turnUsage,
}: {
  sessionUsage: UsagePayload | null;
  turnUsage: { usage: UsagePayload | null; elapsedSeconds?: number } | null;
}) {
  const tokens = formatTokens(sessionUsage?.total_tokens ?? 0);
  const cost = `$${(sessionUsage?.estimated_cost_usd ?? 0).toFixed(2)}`;
  const lastTurn = turnUsage
    ? `${formatTokens(turnUsage.usage?.total_tokens ?? 0)} / ${formatDuration(turnUsage.elapsedSeconds ?? 0)}`
    : null;

  return (
    <div className="usage-pills">
      <span className="usage-pills__item" title="Session tokens">{tokens}</span>
      <span className="usage-pills__sep" />
      <span className="usage-pills__item" title="Estimated cost">{cost}</span>
      {lastTurn ? (
        <>
          <span className="usage-pills__sep" />
          <span className="usage-pills__item" title="Last turn">{lastTurn}</span>
        </>
      ) : null}
    </div>
  );
}
