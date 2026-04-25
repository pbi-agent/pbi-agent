import { LoaderCircleIcon } from "lucide-react";

export function LoadingSpinner({
  size = "md",
}: {
  size?: "sm" | "md" | "lg";
}) {
  const cls = size === "md" ? "spinner" : `spinner spinner--${size}`;
  return <LoaderCircleIcon className={cls} aria-label="Loading" />;
}
