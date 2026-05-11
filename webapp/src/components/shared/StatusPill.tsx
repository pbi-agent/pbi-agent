import { Badge } from "../ui/badge";

const runningStatuses = new Set(["running", "started", "starting", "waiting_for_input"]);
const completedStatuses = new Set(["completed", "interrupted", "ended"]);

function statusVariant(status: string): "secondary" | "running" | "completed" | "failed" {
  if (runningStatuses.has(status)) return "running";
  if (completedStatuses.has(status)) return "completed";
  if (status === "failed") return "failed";
  return "secondary";
}

export function StatusPill({ status }: { status: string }) {
  return <Badge variant={statusVariant(status)}>{status}</Badge>;
}
