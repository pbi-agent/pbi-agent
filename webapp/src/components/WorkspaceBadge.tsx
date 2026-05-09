import { useQuery } from "@tanstack/react-query";
import { fetchBootstrap } from "../api";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

type WorkspaceBadgeProps = {
  className?: string;
  textClassName?: string;
  tooltipSide?: "top" | "right" | "bottom" | "left";
  tooltipAlign?: "start" | "center" | "end";
};

export function WorkspaceBadge({
  className,
  textClassName,
  tooltipSide = "right",
  tooltipAlign = "center",
}: WorkspaceBadgeProps) {
  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchBootstrap,
    staleTime: 30_000,
  });

  const bootstrap = bootstrapQuery.data;
  const workspaceDisplayPath = bootstrap?.workspace_display_path;
  const folderLabel = workspaceDisplayPath
    ? workspaceDisplayPath.split(/[/\\]/).filter(Boolean).slice(-2).join("/")
    : null;
  const workspaceBadgeLabel = bootstrap?.is_sandbox && folderLabel
    ? `Sandbox · ${folderLabel}`
    : folderLabel;

  if (!workspaceBadgeLabel) return null;

  const workspaceBadge = (
    <Badge
      variant="outline"
      className={cn("app-sidebar__workspace-badge", className)}
    >
      <span className={cn("app-sidebar__workspace-badge-text", textClassName)}>
        {workspaceBadgeLabel}
      </span>
    </Badge>
  );

  return workspaceDisplayPath ? (
    <Tooltip>
      <TooltipTrigger asChild>{workspaceBadge}</TooltipTrigger>
      <TooltipContent side={tooltipSide} align={tooltipAlign}>
        {workspaceDisplayPath}
      </TooltipContent>
    </Tooltip>
  ) : workspaceBadge;
}
