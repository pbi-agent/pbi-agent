import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ActivityIcon, AlertTriangleIcon, CalendarIcon } from "lucide-react";
import { fetchDashboardStats } from "../../api";
import { Alert, AlertDescription } from "../ui/alert";
import { Card, CardAction, CardHeader, CardTitle } from "../ui/card";
import { InputGroup, InputGroupAddon, InputGroupInput } from "../ui/input-group";
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
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        {/* ── Header ── */}
        <Card size="sm">
          <CardHeader>
            <CardTitle>
              <div className="flex items-center gap-2">
                <ActivityIcon aria-hidden="true" />
                <h2>Observability</h2>
              </div>
            </CardTitle>
            <CardAction>
              <div className="flex flex-wrap items-center gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-muted-foreground">From</span>
              <InputGroup className="w-auto">
                <InputGroupAddon>
                  <CalendarIcon aria-hidden="true" />
                </InputGroupAddon>
                <InputGroupInput
                  type="date"
                  aria-label="Start date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </InputGroup>
                <span className="text-sm text-muted-foreground">To</span>
              <InputGroup className="w-auto">
                <InputGroupAddon>
                  <CalendarIcon aria-hidden="true" />
                </InputGroupAddon>
                <InputGroupInput
                  type="date"
                  aria-label="End date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </InputGroup>
              </div>
              <ToggleGroup
                type="single"
                value={scope}
                onValueChange={(value) => {
                  if (value === "workspace" || value === "global") setScope(value);
                }}
                variant="outline"
                size="sm"
              >
                <ToggleGroupItem value="workspace">Workspace</ToggleGroupItem>
                <ToggleGroupItem value="global">Global</ToggleGroupItem>
              </ToggleGroup>
              </div>
            </CardAction>
          </CardHeader>
        </Card>

        {/* ── L1: Overview KPIs ─────────────────────── */}
        {statsQuery.isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner size="lg" />
          </div>
        ) : statsQuery.isError ? (
          <Alert variant="destructive">
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
