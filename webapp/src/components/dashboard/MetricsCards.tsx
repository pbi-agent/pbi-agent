import { useMemo } from "react";
import type { DailyBucket, DashboardOverview } from "../../types";
import { Sparkline } from "./Sparkline";

type MetricsCardsProps = {
  overview: DashboardOverview;
  daily: DailyBucket[];
};

type CardDef = {
  label: string;
  value: string;
  sparkValues: number[];
  accent?: string;
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString();
}

function formatCost(usd: number): string {
  if (usd >= 100) return `$${usd.toFixed(0)}`;
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(4)}`;
}

function formatDuration(ms: number | null): string {
  if (ms == null) return "--";
  if (ms < 1_000) return `${Math.round(ms)}ms`;
  return `${(ms / 1_000).toFixed(1)}s`;
}

export function MetricsCards({ overview, daily }: MetricsCardsProps) {
  const cards = useMemo<CardDef[]>(() => {
    const runsSpark = daily.map((d) => d.runs);
    const tokensSpark = daily.map((d) => d.tokens);
    const costSpark = daily.map((d) => d.cost);
    const errorsSpark = daily.map((d) => d.errors);

    return [
      {
        label: "Sessions",
        value: formatNumber(overview.total_sessions),
        sparkValues: runsSpark,
      },
      {
        label: "Runs",
        value: formatNumber(overview.total_runs),
        sparkValues: runsSpark,
      },
      {
        label: "Total Tokens",
        value: formatNumber(
          overview.total_input_tokens + overview.total_output_tokens,
        ),
        sparkValues: tokensSpark,
      },
      {
        label: "Cost",
        value: formatCost(overview.total_cost),
        sparkValues: costSpark,
      },
      {
        label: "API Calls",
        value: formatNumber(overview.total_api_calls),
        sparkValues: runsSpark,
      },
      {
        label: "Tool Calls",
        value: formatNumber(overview.total_tool_calls),
        sparkValues: runsSpark,
      },
      {
        label: "Errors",
        value: formatNumber(overview.total_errors),
        sparkValues: errorsSpark,
        accent: overview.total_errors > 0 ? "var(--color-error)" : undefined,
      },
      {
        label: "Avg Duration",
        value: formatDuration(overview.avg_duration_ms),
        sparkValues: runsSpark,
      },
    ];
  }, [overview, daily]);

  return (
    <div className="metrics-grid">
      {cards.map((card) => (
        <div className="metric-card" key={card.label}>
          <div className="metric-card__header">
            <span className="metric-card__label">{card.label}</span>
            <Sparkline
              values={card.sparkValues}
              width={80}
              height={24}
              color={card.accent}
            />
          </div>
          <span
            className="metric-card__value"
            style={card.accent ? { color: card.accent } : undefined}
          >
            {card.value}
          </span>
        </div>
      ))}
    </div>
  );
}
