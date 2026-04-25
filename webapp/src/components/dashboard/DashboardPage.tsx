import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon } from "lucide-react";
import { fetchDashboardStats } from "../../api";
import { Alert, AlertDescription } from "../ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Field, FieldGroup, FieldLabel } from "../ui/field";
import { Input } from "../ui/input";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { MetricsCards } from "./MetricsCards";
import { BreakdownTable } from "./BreakdownTable";
import { RunsTable } from "./RunsTable";

function toLocalDateString(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultDateRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 14);
  return {
    start: toLocalDateString(start),
    end: toLocalDateString(end),
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
        <Card className="dashboard-controls">
          <CardHeader>
            <CardTitle>Observability</CardTitle>
          </CardHeader>
          <CardContent className="dashboard-controls__content">
          <FieldGroup className="dashboard-controls__dates">
            <Field>
              <FieldLabel>From</FieldLabel>
              <Input
                type="date"
                className="dashboard-date-input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel>To</FieldLabel>
              <Input
                type="date"
                className="dashboard-date-input"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </Field>
          </FieldGroup>
          <ToggleGroup
            type="single"
            value={scope}
            onValueChange={(value) => {
              if (value === "workspace" || value === "global") setScope(value);
            }}
            className="dashboard-controls__scope"
            spacing={1}
            variant="outline"
          >
            <ToggleGroupItem value="workspace">Workspace</ToggleGroupItem>
            <ToggleGroupItem value="global">Global</ToggleGroupItem>
          </ToggleGroup>
          </CardContent>
        </Card>

        {/* ── L1: Overview KPIs ─────────────────────── */}
        {statsQuery.isLoading ? (
          <div className="dashboard-loading">
            <LoadingSpinner size="lg" />
          </div>
        ) : statsQuery.isError ? (
          <Alert variant="destructive" className="dashboard-error">
            <AlertTriangleIcon />
            <AlertDescription>
              Failed to load dashboard data. Please try again.
            </AlertDescription>
          </Alert>
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
