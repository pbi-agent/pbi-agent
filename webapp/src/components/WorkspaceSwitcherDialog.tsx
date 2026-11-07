import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangleIcon, CheckIcon, FolderOpenIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  fetchRecentWorkspaces,
  pickWorkspace,
  switchWorkspace,
} from "../api";
import { cn } from "../lib/utils";
import { resetWorkspaceScopedClientState } from "../workspaceState";
import type { BootstrapPayload, WorkspacePickerPayload } from "../types";
import { Alert, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Separator } from "./ui/separator";

type WorkspaceSwitcherDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function WorkspaceSwitcherDialog({
  open,
  onOpenChange,
}: WorkspaceSwitcherDialogProps) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const recentQuery = useQuery({
    queryKey: ["workspaces", "recent"],
    queryFn: fetchRecentWorkspaces,
    enabled: open,
  });

  function applyWorkspaceSwitch(bootstrap: BootstrapPayload) {
    resetWorkspaceScopedClientState(client, bootstrap);
    void navigate("/sessions");
    onOpenChange(false);
  }

  const switchMutation = useMutation({
    mutationFn: switchWorkspace,
    onSuccess: (payload) => applyWorkspaceSwitch(payload.bootstrap),
  });

  const pickMutation = useMutation({
    mutationFn: pickWorkspace,
    onSuccess: (payload: WorkspacePickerPayload) => {
      if (payload.status === "switched" && payload.bootstrap) {
        applyWorkspaceSwitch(payload.bootstrap);
      }
    },
  });

  const pickerMessage = pickMutation.data?.status !== "switched"
    ? pickMutation.data?.message
    : null;
  const pickerUnavailableMessage =
    pickerMessage ??
    (recentQuery.data?.picker_available === false
      ? "Folder picking is not available in this environment."
      : null);
  const mutationError =
    switchMutation.error instanceof Error
      ? switchMutation.error.message
      : pickMutation.error instanceof Error
        ? pickMutation.error.message
        : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-dvh flex-col sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Switch workspace</DialogTitle>
          <DialogDescription>
            Choose a recent folder. Running work stays in its original workspace.
          </DialogDescription>
        </DialogHeader>

        {mutationError ? (
          <Alert variant="destructive">
            <AlertDescription>{mutationError}</AlertDescription>
          </Alert>
        ) : null}
        <div className="flex max-h-80 min-h-0 flex-col gap-1 overflow-y-auto">
          {recentQuery.isLoading ? (
            <div className="px-3 py-6 text-center text-sm text-muted-foreground">
              Loading recent workspaces…
            </div>
          ) : recentQuery.data?.workspaces.length ? (
            recentQuery.data.workspaces.map((workspace) => (
              <button
                key={workspace.directory_key}
                type="button"
                aria-current={workspace.is_current ? "page" : undefined}
                data-current={workspace.is_current ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50",
                  workspace.is_current && "bg-muted",
                )}
                disabled={switchMutation.isPending}
                onClick={() => {
                  if (!workspace.is_current) {
                    switchMutation.mutate(workspace.directory_key);
                  }
                }}
              >
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <div className="truncate text-sm font-medium text-foreground">
                    {workspace.display_path}
                  </div>
                  <div className="truncate font-mono text-xs text-muted-foreground">
                    {workspace.is_sandbox ? "Sandbox · " : ""}
                    {workspace.root_path}
                  </div>
                </div>
                {workspace.is_current ? (
                  <CheckIcon className="size-4 text-muted-foreground" />
                ) : null}
              </button>
            ))
          ) : (
            <div className="px-3 py-6 text-center text-sm text-muted-foreground">
              No recent workspaces yet.
            </div>
          )}
        </div>

        <Separator />

        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full"
          onClick={() => pickMutation.mutate()}
          disabled={pickMutation.isPending}
        >
          <FolderOpenIcon data-icon="inline-start" />
          Choose folder…
        </Button>
        {pickerUnavailableMessage ? (
          <Alert data-workspace-picker-warning="">
            <AlertTriangleIcon />
            <AlertDescription>{pickerUnavailableMessage}</AlertDescription>
          </Alert>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}