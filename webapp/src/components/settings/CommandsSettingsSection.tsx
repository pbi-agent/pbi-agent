import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  DownloadIcon,
  EyeIcon,
  FileTextIcon,
  FolderGit2Icon,
  PlusIcon,
  SearchIcon,
} from "lucide-react";
import { ApiError, fetchCommandCandidates, installCommand } from "../../api";
import type {
  CommandCandidateView,
  CommandCandidatesPayload,
  CommandInstallPayload,
  CommandView,
  ConfigBootstrapPayload,
} from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { SettingsPreviewDialog } from "./SettingsPreviewDialog";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { SettingsPanel, SettingsSection } from "./settings-layout";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "../ui/field";
import { Input } from "../ui/input";
import { Separator } from "../ui/separator";
import { Skeleton } from "../ui/skeleton";

function ConfigListBadge({
  label,
  items,
}: {
  label: string;
  items: string[] | null;
}) {
  if (!items?.length) return null;
  return (
    <Badge size="meta" variant="outline">
      {label}: {items.join(", ")}
    </Badge>
  );
}

function CommandCard({
  command,
  onPreview,
}: {
  command: CommandView;
  onPreview: () => void;
}) {
  return (
    <Card size="sm" data-settings-command-card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words">{command.name}</CardTitle>
        {command.description ? (
          <CardDescription>{command.description}</CardDescription>
        ) : null}
        <CardDescription className="break-all">{command.path}</CardDescription>
      </CardHeader>
      <CardFooter>
        <div className="flex w-full flex-wrap items-center justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onPreview}>
            <EyeIcon data-icon="inline-start" />
            Preview
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
}

function CommandPreviewBadges({ command }: { command: CommandView }) {
  return (
    <div
      className="flex flex-wrap gap-1"
      role="group"
      aria-label="Command metadata"
    >
      <Badge size="meta" variant="secondary">
        {command.slash_alias}
      </Badge>
      {command.model_profile_id ? (
        <Badge size="meta" variant="outline">
          Profile: {command.model_profile_id}
        </Badge>
      ) : null}
      <ConfigListBadge label="Tools" items={command.allowed_tools} />
      <ConfigListBadge label="Skills" items={command.skills} />
      <ConfigListBadge label="Sub-agents" items={command.sub_agents} />
    </div>
  );
}

function CandidateSkeleton() {
  return (
    <div className="flex min-w-0 items-start gap-3 rounded-lg border border-border p-3">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-24" />
      </div>
      <Skeleton className="h-8 w-20 shrink-0" />
    </div>
  );
}

function CandidateCard({
  candidate,
  isInstalling,
  disabled,
  onInstall,
}: {
  candidate: CommandCandidateView;
  isInstalling: boolean;
  disabled: boolean;
  onInstall: () => void;
}) {
  return (
    <div className="flex min-w-0 items-start gap-3 rounded-lg border border-border p-3">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="text-sm font-medium break-words">{candidate.name}</div>
        <p className="text-sm text-muted-foreground">
          {candidate.description || `Install ${candidate.slash_alias}.`}
        </p>
        <div className="flex flex-wrap gap-1">
          <Badge size="meta" variant="secondary">
            {candidate.slash_alias}
          </Badge>
          {candidate.model_profile_id ? (
            <Badge size="meta" variant="outline">
              Profile: {candidate.model_profile_id}
            </Badge>
          ) : null}
          {candidate.subpath ? (
            <Badge size="meta" variant="outline">
              {candidate.subpath}
            </Badge>
          ) : null}
        </div>
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={onInstall}
        disabled={disabled}
        className="shrink-0"
      >
        {isInstalling ? (
          <LoadingSpinner size="sm" />
        ) : (
          <DownloadIcon data-icon="inline-start" />
        )}
        Install
      </Button>
    </div>
  );
}

function candidateInstallSource(
  listing: CommandCandidatesPayload | null,
): string | null {
  return listing?.source ?? null;
}

export function CommandsSettingsSection({
  commands,
}: {
  commands: CommandView[];
}) {
  const queryClient = useQueryClient();
  const [previewCommand, setPreviewCommand] = useState<CommandView | null>(
    null,
  );
  const [addOpen, setAddOpen] = useState(false);
  const [customSource, setCustomSource] = useState("");
  const [listing, setListing] = useState<CommandCandidatesPayload | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [installingCommand, setInstallingCommand] = useState<string | null>(
    null,
  );
  const [installError, setInstallError] = useState<string | null>(null);
  const [conflictRetry, setConflictRetry] = useState<{
    source: string | null;
    name: string;
    commandName: string;
    slashAlias: string;
  } | null>(null);

  function resetDialogState() {
    setCustomSource("");
    setListing(null);
    setLoadingCandidates(false);
    setCandidatesError(null);
    setInstallingCommand(null);
    setInstallError(null);
    setConflictRetry(null);
  }

  async function loadCandidates(source: string | null) {
    setLoadingCandidates(true);
    setCandidatesError(null);
    setInstallError(null);
    setConflictRetry(null);
    try {
      const response = await fetchCommandCandidates(source);
      setListing(response);
    } catch (err) {
      setListing(null);
      setCandidatesError((err as Error).message);
    } finally {
      setLoadingCandidates(false);
    }
  }

  function openAddDialog() {
    resetDialogState();
    setAddOpen(true);
    void loadCandidates(null);
  }

  function closeAddDialog() {
    setAddOpen(false);
    resetDialogState();
  }

  async function applyInstallResponse(response: CommandInstallPayload) {
    queryClient.setQueryData<ConfigBootstrapPayload>(
      ["config-bootstrap"],
      (current) =>
        current
          ? {
              ...current,
              commands: response.commands,
              config_revision: response.config_revision,
            }
          : current,
    );
    closeAddDialog();
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["config-bootstrap"] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap"] }),
    ]);
  }

  async function handleInstall(
    candidate: CommandCandidateView,
    force = false,
    overrideSource?: string | null,
  ) {
    const source = overrideSource ?? candidateInstallSource(listing);
    setInstallingCommand(candidate.command_id);
    setInstallError(null);
    if (!force) setConflictRetry(null);
    try {
      const response = await installCommand({
        source,
        command_name: candidate.command_id,
        ...(force ? { force: true } : {}),
      });
      await applyInstallResponse(response);
    } catch (err) {
      const message = (err as Error).message;
      setInstallError(message);
      if (err instanceof ApiError && err.status === 409) {
        setConflictRetry({
          source,
          name: candidate.name,
          commandName: candidate.command_id,
          slashAlias: candidate.slash_alias,
        });
      } else {
        setConflictRetry(null);
      }
    } finally {
      setInstallingCommand(null);
    }
  }

  function handleBrowseCustomSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const source = customSource.trim();
    void loadCandidates(source || null);
  }

  const candidates = listing?.candidates ?? [];
  const sourceLabel = listing?.source ?? "Official catalog";
  const isBusy = loadingCandidates || installingCommand !== null;

  return (
    <SettingsSection>
      <SettingsPanel
        title="Project Commands"
        description="Installed slash commands from .agents/commands"
        actions={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={openAddDialog}
          >
            <PlusIcon data-icon="inline-start" />
            Add Command
          </Button>
        }
      >
        {commands.length === 0 ? (
          <EmptyState
            title="No commands found"
            description="Add commands from the official catalog, GitHub, or a server-side local path."
          />
        ) : (
          commands.map((command) => (
            <CommandCard
              key={command.id}
              command={command}
              onPreview={() => setPreviewCommand(command)}
            />
          ))
        )}
      </SettingsPanel>

      <Dialog
        open={addOpen}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) closeAddDialog();
        }}
      >
        <DialogContent className="max-h-screen overflow-hidden sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add Project Command</DialogTitle>
            <DialogDescription>
              Browse the official catalog or provide a GitHub source, tree URL,
              or server-side local path.
            </DialogDescription>
          </DialogHeader>

          <div className="flex min-h-0 flex-col">
            <div className="flex min-h-0 flex-col gap-4 overflow-y-auto">
              <form
                className="flex flex-col"
                onSubmit={handleBrowseCustomSource}
              >
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="command-source">
                      Custom source
                    </FieldLabel>
                    <div className="flex gap-2">
                      <Input
                        id="command-source"
                        className="flex-1"
                        value={customSource}
                        onChange={(event) =>
                          setCustomSource(event.target.value)
                        }
                        placeholder="owner/repo or /path/to/commands"
                        disabled={isBusy}
                      />
                      <Button
                        type="submit"
                        variant="outline"
                        disabled={isBusy}
                      >
                        {loadingCandidates ? (
                          <LoadingSpinner size="sm" />
                        ) : (
                          <SearchIcon data-icon="inline-start" />
                        )}
                        Browse
                      </Button>
                    </div>
                    <FieldDescription>
                      Use owner/repo, a GitHub URL, a tree URL, or a path
                      available to the web server.
                    </FieldDescription>
                  </Field>
                </FieldGroup>
              </form>

              <Separator />

              <section className="flex min-w-0 flex-col gap-3">
                <header className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 flex-col gap-1">
                    <div className="text-sm font-medium">
                      Available commands
                    </div>
                    <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
                      <FolderGit2Icon
                        className="size-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      <span className="min-w-0 truncate">{sourceLabel}</span>
                      {listing?.ref ? (
                        <Badge size="meta" variant="outline">
                          {listing.ref}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                </header>

                {candidatesError ? (
                  <Alert variant="destructive">
                    <AlertCircleIcon />
                    <AlertTitle>Could not load commands</AlertTitle>
                    <AlertDescription>{candidatesError}</AlertDescription>
                  </Alert>
                ) : null}

                {installError ? (
                  <Alert variant="destructive">
                    <AlertCircleIcon />
                    <AlertTitle>Could not install command</AlertTitle>
                    <AlertDescription>
                      <div className="flex flex-col items-start gap-2">
                        <span>{installError}</span>
                        {conflictRetry ? (
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            onClick={() =>
                              void handleInstall(
                                {
                                  name: conflictRetry.name,
                                  command_id: conflictRetry.commandName,
                                  slash_alias: conflictRetry.slashAlias,
                                  description: "",
                                  model_profile_id: null,
                                  subpath: null,
                                },
                                true,
                                conflictRetry.source,
                              )
                            }
                            disabled={installingCommand !== null}
                          >
                            Replace existing
                          </Button>
                        ) : null}
                      </div>
                    </AlertDescription>
                  </Alert>
                ) : null}

                <div className="flex min-w-0 flex-col gap-2" aria-live="polite">
                  {loadingCandidates ? (
                    <>
                      <CandidateSkeleton />
                      <CandidateSkeleton />
                      <CandidateSkeleton />
                    </>
                  ) : candidates.length === 0 && !candidatesError ? (
                    <EmptyState
                      title="No commands found"
                      description="Try another source or browse the official catalog."
                    />
                  ) : (
                    candidates.map((candidate) => (
                      <CandidateCard
                        key={`${sourceLabel}:${candidate.command_id}`}
                        candidate={candidate}
                        isInstalling={
                          installingCommand === candidate.command_id
                        }
                        disabled={isBusy}
                        onInstall={() => void handleInstall(candidate)}
                      />
                    ))
                  )}
                </div>
              </section>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {previewCommand ? (
        <SettingsPreviewDialog
          title={previewCommand.name}
          path={previewCommand.path}
          content={previewCommand.instructions}
          icon={FileTextIcon}
          headerContent={<CommandPreviewBadges command={previewCommand} />}
          onClose={() => setPreviewCommand(null)}
        />
      ) : null}
    </SettingsSection>
  );
}
