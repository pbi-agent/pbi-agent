import { cn } from "../../lib/utils";
import type { ConnectionState } from "../../store";

type BadgeConnectionState = ConnectionState | "ready";

export function ConnectionBadge({
  connection,
}: {
  connection: BadgeConnectionState;
}) {
  const label =
    connection === "connected" ? "Connected"
    : connection === "ready" ? "Ready"
    : connection === "connecting" ? "Connecting..."
    : connection === "reconnecting" ? "Reconnecting..."
    : connection === "recovering" ? "Recovering..."
    : connection === "recovered" ? "Recovered"
    : connection === "recovery_failed" ? "Recovery failed"
    : "Disconnected";

  return (
    <div
      className="inline-flex items-center justify-center"
      aria-label={label}
      data-connection={connection}
    >
      <span
        className={cn(
          "size-2 shrink-0 rounded-full",
          connection === "connected" || connection === "ready" || connection === "recovered"
            ? "bg-primary"
            : connection === "recovery_failed"
              ? "bg-destructive"
              : connection === "disconnected"
                ? "bg-muted-foreground"
                : "animate-pulse bg-chart-4",
        )}
      />
    </div>
  );
}
