import type * as React from "react";

import { Badge } from "../ui/badge";

const runningStatuses = new Set(["running", "started", "starting", "waiting_for_input"]);
const completedStatuses = new Set(["completed", "interrupted", "ended"]);

function statusVariant(status: string): "secondary" | "running" | "completed" | "failed" {
  if (runningStatuses.has(status)) return "running";
  if (completedStatuses.has(status)) return "completed";
  if (status === "failed") return "failed";
  return "secondary";
}

type StatusPillProps = Omit<React.ComponentProps<typeof Badge>, "asChild" | "variant"> & {
  status: string;
};

export function StatusPill({ status, className, size, children, ...props }: StatusPillProps) {
  return (
    <Badge
      variant={statusVariant(status)}
      size={size}
      className={className}
      {...props}
    >
      {children ?? status}
    </Badge>
  );
}
