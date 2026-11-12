import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchBootstrap } from "../api";
import { cn } from "../lib/utils";
import { MetaBadge } from "./MetaBadge";
import { WorkspaceSwitcherDialog } from "./WorkspaceSwitcherDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

type WorkspaceBadgeProps = {
  className?: string;
  textClassName?: string;
  tooltipSide?: "top" | "right" | "bottom" | "left";
  tooltipAlign?: "start" | "center" | "end";
  /** "text" renders a plain breadcrumb-style label instead of a badge. */
  variant?: "badge" | "text";
};

export function WorkspaceBadge({
  className,
  textClassName,
  tooltipSide = "right",
  tooltipAlign = "center",
  variant = "badge",
}: WorkspaceBadgeProps) {
  const [switcherOpen, setSwitcherOpen] = useState(false);
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

  const isText = variant === "text";
  const workspaceBadge = (
    <button
      type="button"
      className={cn(
        "min-w-0 text-left focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        isText
          ? "truncate rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground"
          : "rounded-full",
        isText && className,
        isText && textClassName,
      )}
      onClick={() => setSwitcherOpen(true)}
      aria-label="Switch workspace"
    >
      {isText ? (
        workspaceBadgeLabel
      ) : (
        <MetaBadge truncate className={className} labelClassName={textClassName}>
          {workspaceBadgeLabel}
        </MetaBadge>
      )}
    </button>
  );

  return (
    <>
      {workspaceDisplayPath ? (
        <Tooltip>
          <TooltipTrigger asChild>{workspaceBadge}</TooltipTrigger>
          <TooltipContent side={tooltipSide} align={tooltipAlign}>
            {workspaceDisplayPath}
          </TooltipContent>
        </Tooltip>
      ) : (
        workspaceBadge
      )}
      <WorkspaceSwitcherDialog
        open={switcherOpen}
        onOpenChange={setSwitcherOpen}
      />
    </>
  );
}
