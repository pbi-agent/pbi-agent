import { Spinner } from "../ui/spinner";

export function LoadingSpinner({
  size = "md",
}: {
  size?: "sm" | "md" | "lg";
}) {
  if (size === "sm") return <Spinner className="size-3" />;
  if (size === "lg") return <Spinner className="size-6" />;
  return <Spinner />;
}
