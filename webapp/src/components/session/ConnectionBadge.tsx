export function ConnectionBadge({
  connection,
}: {
  connection: "disconnected" | "connecting" | "connected" | "ready";
}) {
  const label =
    connection === "connected" ? "Connected"
    : connection === "ready" ? "Ready"
    : connection === "connecting" ? "Connecting..."
    : "Disconnected";

  return (
    <div className="connection-badge" aria-label={label}>
      <span className={`indicator-dot indicator-dot--${connection}`} />
    </div>
  );
}
