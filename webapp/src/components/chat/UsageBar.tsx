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
  return (
    <div className="usage-bar">
      <div className="usage-bar__item">
        <span className="usage-bar__value">
          {formatTokens(sessionUsage?.total_tokens ?? 0)}
        </span>
        <span className="usage-bar__label">Session tokens</span>
      </div>
      <div className="usage-bar__item">
        <span className="usage-bar__value">
          ${(sessionUsage?.estimated_cost_usd ?? 0).toFixed(4)}
        </span>
        <span className="usage-bar__label">Cost</span>
      </div>
      <div className="usage-bar__item">
        <span className="usage-bar__value">
          {turnUsage
            ? `${formatTokens(turnUsage.usage.total_tokens)} / ${turnUsage.elapsedSeconds?.toFixed(1) ?? "0.0"}s`
            : "\u2014"}
        </span>
        <span className="usage-bar__label">Last turn</span>
      </div>
    </div>
  );
}
