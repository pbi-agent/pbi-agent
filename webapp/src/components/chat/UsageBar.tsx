import type { UsagePayload } from "../../types";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function UsageBar({
  sessionUsage,
  turnUsage,
}: {
  sessionUsage: UsagePayload | null;
  turnUsage: { usage: UsagePayload; elapsedSeconds?: number } | null;
}) {
  const tokens = formatTokens(sessionUsage?.total_tokens ?? 0);
  const cost = `$${(sessionUsage?.estimated_cost_usd ?? 0).toFixed(2)}`;
  const lastTurn = turnUsage
    ? `${formatTokens(turnUsage.usage.total_tokens)} / ${turnUsage.elapsedSeconds?.toFixed(1) ?? "0.0"}s`
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
