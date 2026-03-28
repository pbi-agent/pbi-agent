export function LoadingSpinner({
  size = "md",
}: {
  size?: "sm" | "md" | "lg";
}) {
  const cls = size === "md" ? "spinner" : `spinner spinner--${size}`;
  return <div className={cls} />;
}
