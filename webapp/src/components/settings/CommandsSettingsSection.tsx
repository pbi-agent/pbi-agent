import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  DownloadIcon,
  EyeIcon,
  FileTextIcon,
  FolderGit2Icon,
  PlusIcon,
  SearchIcon,
} from "lucide-react";
import {
  ApiError,
  fetchCommandCandidates,
  installCommand,
} from "../../api";
import type {
  CommandCandidateView,
  CommandCandidatesPayload,
  CommandInstallPayload,
  CommandView,
  ConfigBootstrapPayload,
} from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { MarkdownContent } from "../shared/MarkdownContent";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import { Input } from "../ui/input";
import { Separator } from "../ui/separator";
import { Skeleton } from "../ui/skeleton";

function CommandCard({
  command,
  onPreview,
}: {
  command: CommandView;
  onPreview: () => void;
}) {
  return (
    <Card className="settings-item settings-item--provider skill-card command-card">
      <div className="provider-card__info">
        <span className="settings-item__name">{command.name}</span>
        {command.description ? (
          <div className="settings-item__summary skill-card__description">
            {command.description}
          </div>
        ) : null}
        <div className="provider-card__subtitle">{command.path}</div>
      </div>
      <div className="settings-item__actions settings-item__actions--provider command-card__actions">
        <Badge variant="secondary" className="settings-item__tag command-card__alias">
          {command.slash_alias}
        </Badge>
        {command.model_profile_id ? (
          <Badge variant="outline" className="settings-item__tag">
            Profile: {command.model_profile_id}
          </Badge>
        ) : null}
        <Badge variant="outline" className="settings-item__tag">
          Project command
        </Badge>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="task-card__action-button"
          onClick={onPreview}
        >
          <EyeIcon data-icon="inline-start" />
          Preview
        </Button>
      </div>
    </Card>
  );
}

function CommandPreviewDialog({
  command,
  onClose,
}: {
  command: CommandView;
  onClose: () => void;
}) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="command-preview-dialog" aria-describedby={undefined}>
        <DialogHeader className="command-preview-dialog__header">
          <div className="command-preview-dialog__title-row">
            <div
              className="settings-command-icon settings-command-icon--dialog"
              aria-hidden="true"
            >
              <FileTextIcon />
            </div>
            <DialogTitle>{command.name}</DialogTitle>
            <span className="flex-1" />
            <span className="provider-card__subtitle">{command.path}</span>
          </div>
        </DialogHeader>
        <div className="command-preview-dialog__scroll timeline-entry timeline-entry--assistant">
          <div className="timeline-entry__content command-preview-dialog__markdown">
            <MarkdownContent content={command.instructions} />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function CandidateSkeleton() {
  return (
    <div className="skill-candidate">
      <div className="skill-candidate__main">
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
    <div className="skill-candidate">
      <div className="skill-candidate__main">
        <div className="skill-candidate__name">{candidate.name}</div>
        <p className="skill-candidate__description">
          {candidate.description || `Install ${candidate.slash_alias}.`}
        </p>
        <div className="command-candidate__badges">
          <Badge variant="secondary" className="skill-candidate__subpath">
            {candidate.slash_alias}
          </Badge>
          {candidate.model_profile_id ? (
            <Badge variant="outline" className="skill-candidate__subpath">
              Profile: {candidate.model_profile_id}
            </Badge>
          ) : null}
          {candidate.subpath ? (
            <Badge variant="outline" className="skill-candidate__subpath">
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
        className="skill-candidate__action"
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

export function CommandsSettingsSection({ commands }: { commands: CommandView[] }) {
  const queryClient = useQueryClient();
  const [previewCommand, setPreviewCommand] = useState<CommandView | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [customSource, setCustomSource] = useState("");
  const [listing, setListing] = useState<CommandCandidatesPayload | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [installingCommand, setInstallingCommand] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [conflictRetry, setConflictRetry] = useState<{
    source: string | null;
    name: string;
    commandName: string;
    slashAlias: string;
  } | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

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

  async function applyInstallResponse(
    response: CommandInstallPayload,
    commandLabel: string,
  ) {
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
    setSuccessMessage(
      `Installed ${commandLabel}. It is available from the composer command menu immediately.`,
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
      await applyInstallResponse(response, candidate.slash_alias);
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
    <section className="settings-section settings-section--active">
      {successMessage ? (
        <Alert className="settings-inline-note commands-success-note">
          <CheckCircle2Icon />
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Alert className="settings-inline-note commands-hint">
        <AlertDescription>
          Add Markdown files under{" "}
          <code className="command-hint__path">.agents/commands/</code> — a
          file like{" "}
          <code className="command-hint__path">.agents/commands/review.md</code>{" "}
          becomes <code className="command-hint__path">/review</code>.
        </AlertDescription>
      </Alert>

      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Project Commands</CardTitle>
            <div className="settings-panel__subtitle">
              Installed slash commands from .agents/commands
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="task-card__action-button"
            onClick={openAddDialog}
          >
            <PlusIcon data-icon="inline-start" />
            Add Command
          </Button>
        </CardHeader>
        <CardContent className="settings-panel__body">
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
        </CardContent>
      </Card>

      <Dialog
        open={addOpen}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) closeAddDialog();
        }}
      >
        <DialogContent className="task-form-dialog skill-add-dialog command-add-dialog">
          <DialogHeader>
            <DialogTitle>Add Project Command</DialogTitle>
            <DialogDescription>
              Browse the official catalog or provide a GitHub source, tree URL,
              or server-side local path.
            </DialogDescription>
          </DialogHeader>

          <div className="task-form skill-add-dialog__form">
            <div className="task-form__body skill-add-dialog__body">
              <form
                className="skill-source-form command-source-form"
                onSubmit={handleBrowseCustomSource}
              >
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="command-source">Custom source</FieldLabel>
                    <div className="skill-source-form__row">
                      <Input
                        id="command-source"
                        className="task-form__input"
                        value={customSource}
                        onChange={(event) => setCustomSource(event.target.value)}
                        placeholder="owner/repo or /path/to/commands"
                        disabled={isBusy}
                      />
                      <Button
                        type="submit"
                        variant="outline"
                        className="skill-source-form__submit"
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

              <Separator className="skill-add-dialog__divider" />

              <section className="skill-add-dialog__listing">
                <header className="skill-add-dialog__listing-header">
                  <div className="skill-add-dialog__listing-meta">
                    <div className="skill-add-dialog__listing-title">
                      Available commands
                    </div>
                    <div className="skill-add-dialog__source">
                      <FolderGit2Icon aria-hidden="true" />
                      <span className="skill-add-dialog__source-text">
                        {sourceLabel}
                      </span>
                      {listing?.ref ? (
                        <Badge
                          variant="outline"
                          className="skill-add-dialog__source-ref"
                        >
                          {listing.ref}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                </header>

                {candidatesError ? (
                  <Alert variant="destructive" className="task-form__error">
                    <AlertCircleIcon />
                    <AlertTitle>Could not load commands</AlertTitle>
                    <AlertDescription>{candidatesError}</AlertDescription>
                  </Alert>
                ) : null}

                {installError ? (
                  <Alert variant="destructive" className="task-form__error">
                    <AlertCircleIcon />
                    <AlertTitle>Could not install command</AlertTitle>
                    <AlertDescription>
                      <div className="skill-install-error__content">
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

                <div className="skill-candidate-list" aria-live="polite">
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
                        isInstalling={installingCommand === candidate.command_id}
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
        <CommandPreviewDialog
          command={previewCommand}
          onClose={() => setPreviewCommand(null)}
        />
      ) : null}
    </section>
  );
}
