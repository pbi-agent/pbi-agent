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
    <span className={`status-pill status-pill--${modifier}`}>
      {status}
    </span>
  );
}
