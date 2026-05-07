import { Badge } from "../ui/badge";

export function StatusPill({
  status,
}: {
  status: string;
}) {
  const isRunning = [
    "running",
    "started",
    "starting",
    "waiting_for_input",
  ].includes(status);
  const isComplete = ["completed", "interrupted", "ended"].includes(status);
  const modifier =
    isRunning ? "running"
    : isComplete ? "completed"
    : status === "failed" ? "failed"
    : "idle";

  return (
    <Badge variant="secondary" className={`status-pill status-pill--${modifier}`}>
      {status}
    </Badge>
  );
}
