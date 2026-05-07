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
    <div className="connection-badge" aria-label={label}>
      <span className={`indicator-dot indicator-dot--${connection}`} />
    </div>
  );
}
