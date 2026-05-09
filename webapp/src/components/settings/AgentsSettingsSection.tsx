import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  DownloadIcon,
  FolderGit2Icon,
  PlusIcon,
  SearchIcon,
  SparklesIcon,
} from "lucide-react";
import {
  ApiError,
  fetchAgentCandidates,
  installAgent,
} from "../../api";
import type {
  AgentCandidateView,
  AgentCandidatesPayload,
  AgentInstallPayload,
  AgentView,
  ConfigBootstrapPayload,
} from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../ui/card";
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

function AgentCard({ agent }: { agent: AgentView }) {
  return (
    <Card className="settings-item settings-item--provider skill-card">
      <div className="provider-card__info">
        <span className="settings-item__name">{agent.name}</span>
        {agent.description ? (
          <div className="settings-item__summary skill-card__description">
            {agent.description}
          </div>
        ) : null}
        <div className="provider-card__subtitle">{agent.path}</div>
      </div>
      <Badge variant="outline" className="settings-item__tag">
        Project agent
      </Badge>
    </Card>
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
  candidate: AgentCandidateView;
  isInstalling: boolean;
  disabled: boolean;
  onInstall: () => void;
}) {
  return (
    <div className="skill-candidate">
      <div className="skill-candidate__main">
        <div className="skill-candidate__name">{candidate.agent_name}</div>
        <p className="skill-candidate__description">
          {candidate.description || "No description provided."}
        </p>
        {candidate.subpath ? (
          <Badge variant="secondary" className="skill-candidate__subpath">
            {candidate.subpath}
          </Badge>
        ) : null}
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
  listing: AgentCandidatesPayload | null,
): string | null {
  return listing?.source ?? null;
}

export function AgentsSettingsSection({ agents }: { agents: AgentView[] }) {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [customSource, setCustomSource] = useState("");
  const [listing, setListing] = useState<AgentCandidatesPayload | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [installingAgent, setInstallingAgent] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [conflictRetry, setConflictRetry] = useState<{
    source: string | null;
    agentName: string;
  } | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function resetDialogState() {
    setCustomSource("");
    setListing(null);
    setLoadingCandidates(false);
    setCandidatesError(null);
    setInstallingAgent(null);
    setInstallError(null);
    setConflictRetry(null);
  }

  async function loadCandidates(source: string | null) {
    setLoadingCandidates(true);
    setCandidatesError(null);
    setInstallError(null);
    setConflictRetry(null);
    try {
      const response = await fetchAgentCandidates(source);
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
    response: AgentInstallPayload,
    agentName: string,
  ) {
    queryClient.setQueryData<ConfigBootstrapPayload>(
      ["config-bootstrap"],
      (current) =>
        current
          ? {
              ...current,
              agents: response.agents,
              config_revision: response.config_revision,
            }
          : current,
    );
    setSuccessMessage(
      `Installed ${agentName}. New sessions can delegate to it immediately; active sessions can run /reload.`,
    );
    closeAddDialog();
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["config-bootstrap"] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap"] }),
    ]);
  }

  async function handleInstall(
    candidate: AgentCandidateView,
    force = false,
    overrideSource?: string | null,
  ) {
    const source = overrideSource ?? candidateInstallSource(listing);
    setInstallingAgent(candidate.agent_name);
    setInstallError(null);
    if (!force) setConflictRetry(null);
    try {
      const response = await installAgent({
        source,
        agent_name: candidate.agent_name,
        ...(force ? { force: true } : {}),
      });
      await applyInstallResponse(response, candidate.agent_name);
    } catch (err) {
      const message = (err as Error).message;
      setInstallError(message);
      if (err instanceof ApiError && err.status === 409) {
        setConflictRetry({ source, agentName: candidate.agent_name });
      } else {
        setConflictRetry(null);
      }
    } finally {
      setInstallingAgent(null);
    }
  }

  function handleBrowseCustomSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const source = customSource.trim();
    void loadCandidates(source || null);
  }

  const candidates = listing?.candidates ?? [];
  const sourceLabel = listing?.source ?? "Official catalog";
  const isBusy = loadingCandidates || installingAgent !== null;

  return (
    <section className="settings-section settings-section--active">
      {successMessage ? (
        <Alert className="settings-inline-note skills-success-note">
          <CheckCircle2Icon />
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Alert className="settings-inline-note skills-reload-note">
        <SparklesIcon />
        <AlertDescription>
          New sessions see installed agents immediately. Active sessions can run{" "}
          <code className="command-hint__path">/reload</code> before the next model request.
        </AlertDescription>
      </Alert>

      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Project Agents</CardTitle>
            <div className="settings-panel__subtitle">
              Installed sub-agents from .agents/agents
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
            Add Agent
          </Button>
        </CardHeader>
        <CardContent className="settings-panel__body">
          {agents.length === 0 ? (
            <EmptyState
              title="No project agents installed"
              description="Add agents from the official catalog, GitHub, or a server-side local path."
            />
          ) : (
            agents.map((agent) => <AgentCard key={agent.id} agent={agent} />)
          )}
        </CardContent>
      </Card>

      <Dialog
        open={addOpen}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) closeAddDialog();
        }}
      >
        <DialogContent className="task-form-dialog skill-add-dialog">
          <DialogHeader>
            <DialogTitle>Add Project Agent</DialogTitle>
            <DialogDescription>
              Browse the official catalog or provide a GitHub source, tree URL,
              or server-side local path.
            </DialogDescription>
          </DialogHeader>

          <div className="task-form skill-add-dialog__form">
            <div className="task-form__body skill-add-dialog__body">
              <form
                className="skill-source-form"
                onSubmit={handleBrowseCustomSource}
              >
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="agent-source">Custom source</FieldLabel>
                    <div className="skill-source-form__row">
                      <Input
                        id="agent-source"
                        className="task-form__input"
                        value={customSource}
                        onChange={(event) => setCustomSource(event.target.value)}
                        placeholder="owner/repo or /path/to/agents"
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
                      Available agents
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
                    <AlertTitle>Could not load agents</AlertTitle>
                    <AlertDescription>{candidatesError}</AlertDescription>
                  </Alert>
                ) : null}

                {installError ? (
                  <Alert variant="destructive" className="task-form__error">
                    <AlertCircleIcon />
                    <AlertTitle>Could not install agent</AlertTitle>
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
                                  agent_name: conflictRetry.agentName,
                                  description: "",
                                  subpath: null,
                                },
                                true,
                                conflictRetry.source,
                              )
                            }
                            disabled={installingAgent !== null}
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
                      title="No agents found"
                      description="Try another source or browse the official catalog."
                    />
                  ) : (
                    candidates.map((candidate) => (
                      <CandidateCard
                        key={`${sourceLabel}:${candidate.agent_name}`}
                        candidate={candidate}
                        isInstalling={installingAgent === candidate.agent_name}
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
    </section>
  );
}
