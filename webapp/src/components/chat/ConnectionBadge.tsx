export function ConnectionBadge({
  connection,
}: {
  connection: "disconnected" | "connecting" | "connected";
}) {
  const label =
    connection === "connected" ? "Connected"
    : connection === "connecting" ? "Connecting..."
    : "Disconnected";

  return (
    <div className="connection-badge">
      <span className={`indicator-dot indicator-dot--${connection}`} />
      <span>{label}</span>
    </div>
  );
}
