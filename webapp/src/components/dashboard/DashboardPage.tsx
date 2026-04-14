import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboardStats } from "../../api";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { MetricsCards } from "./MetricsCards";
import { BreakdownTable } from "./BreakdownTable";
import { RunsTable } from "./RunsTable";

function defaultDateRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 14);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

export function DashboardPage() {
  const defaults = useMemo(() => defaultDateRange(), []);
  const [startDate, setStartDate] = useState(defaults.start);
  const [endDate, setEndDate] = useState(defaults.end);
  const [scope, setScope] = useState<"workspace" | "global">("workspace");

  // Build ISO end-of-day so the backend includes the end date.
  const endDateParam = `${endDate}T23:59:59`;

  const statsQuery = useQuery({
    queryKey: ["dashboard-stats", startDate, endDateParam, scope],
    queryFn: () =>
      fetchDashboardStats({
        start_date: startDate,
        end_date: endDateParam,
        scope,
      }),
    staleTime: 15_000,
  });

  return (
    <div className="dashboard-page">
      <div className="dashboard-page__inner">
        {/* ── Controls ──────────────────────────────── */}
        <div className="dashboard-controls">
          <div className="dashboard-controls__dates">
            <label className="dashboard-date-label">
              From
              <input
                type="date"
                className="dashboard-date-input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </label>
            <label className="dashboard-date-label">
              To
              <input
                type="date"
                className="dashboard-date-input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </label>
          </div>
          <div className="dashboard-controls__scope">
            <button
              type="button"
              className={`btn btn--sm ${scope === "workspace" ? "btn--active" : ""}`}
              onClick={() => setScope("workspace")}
            >
              Workspace
            </button>
            <button
              type="button"
              className={`btn btn--sm ${scope === "global" ? "btn--active" : ""}`}
              onClick={() => setScope("global")}
            >
              Global
            </button>
          </div>
        </div>

        {/* ── L1: Overview KPIs ─────────────────────── */}
        {statsQuery.isLoading ? (
          <div className="dashboard-loading">
            <LoadingSpinner size="lg" />
          </div>
        ) : statsQuery.isError ? (
          <div className="dashboard-error">
            Failed to load dashboard data. Please try again.
          </div>
        ) : statsQuery.data ? (
          <>
            <MetricsCards
              overview={statsQuery.data.overview}
              daily={statsQuery.data.daily}
            />

            {/* ── L2: Breakdown ──────────────────────── */}
            <BreakdownTable breakdown={statsQuery.data.breakdown} />
          </>
        ) : null}

        {/* ── L3: All Runs Table ─────────────────────── */}
        <RunsTable
          startDate={startDate}
          endDate={endDateParam}
          scope={scope}
        />
      </div>
    </div>
  );
}
