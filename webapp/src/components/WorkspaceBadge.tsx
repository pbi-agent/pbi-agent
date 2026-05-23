import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchBootstrap } from "../api";
import { MetaBadge } from "./MetaBadge";
import { WorkspaceSwitcherDialog } from "./WorkspaceSwitcherDialog";
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

  const workspaceBadge = (
    <button
      type="button"
      className="min-w-0 rounded-full text-left focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      onClick={() => setSwitcherOpen(true)}
      aria-label="Switch workspace"
    >
      <MetaBadge truncate className={className} labelClassName={textClassName}>
        {workspaceBadgeLabel}
      </MetaBadge>
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
