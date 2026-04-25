import { Badge } from "../ui/badge";

export function StatusPill({
  status,
}: {
  status: string;
}) {
  const modifier =
    status === "running" ? "running"
    : status === "completed" ? "completed"
    : status === "failed" ? "failed"
    : "idle";

  return (
    <Badge variant="secondary" className={`status-pill status-pill--${modifier}`}>
      {status}
    </Badge>
  );
}
