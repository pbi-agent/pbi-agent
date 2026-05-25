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
      <DialogContent className="task-form-dialog workspace-switcher-dialog">
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
        <div className="workspace-switcher-dialog__list">
          {recentQuery.isLoading ? (
            <div className="workspace-switcher-dialog__empty">
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
                  "workspace-switcher-dialog__workspace",
                  workspace.is_current &&
                    "workspace-switcher-dialog__workspace--current",
                )}
                disabled={switchMutation.isPending}
                onClick={() => {
                  if (!workspace.is_current) {
                    switchMutation.mutate(workspace.directory_key);
                  }
                }}
              >
                <div className="workspace-switcher-dialog__workspace-text">
                  <div className="workspace-switcher-dialog__workspace-name">
                    {workspace.display_path}
                  </div>
                  <div className="workspace-switcher-dialog__workspace-path">
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
            <div className="workspace-switcher-dialog__empty">
              No recent workspaces yet.
            </div>
          )}
        </div>

        <Separator />

        <Button
          type="button"
          variant="outline"
          size="lg"
          className="workspace-switcher-dialog__pick-button"
          onClick={() => pickMutation.mutate()}
          disabled={pickMutation.isPending}
        >
          <FolderOpenIcon data-icon="inline-start" />
          Choose folder…
        </Button>
        {pickerUnavailableMessage ? (
          <Alert className="workspace-switcher-dialog__warning">
            <AlertTriangleIcon />
            <AlertDescription>{pickerUnavailableMessage}</AlertDescription>
          </Alert>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}