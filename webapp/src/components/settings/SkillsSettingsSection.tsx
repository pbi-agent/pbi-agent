import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  DownloadIcon,
  EyeIcon,
  FolderGit2Icon,
  PlusIcon,
  SearchIcon,
  SparklesIcon,
} from "lucide-react";
import {
  ApiError,
  fetchSkillCandidates,
  installSkill,
} from "../../api";
import type {
  ConfigBootstrapPayload,
  SkillCandidateView,
  SkillCandidatesPayload,
  SkillInstallPayload,
  SkillView,
} from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { SettingsPreviewDialog } from "./SettingsPreviewDialog";
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

function SkillCard({
  skill,
  onPreview,
}: {
  skill: SkillView;
  onPreview: () => void;
}) {
  return (
    <Card className="settings-item settings-item--provider skill-card">
      <div className="provider-card__info">
        <span className="settings-item__name">{skill.name}</span>
        {skill.description ? (
          <div className="settings-item__summary skill-card__description">
            {skill.description}
          </div>
        ) : null}
        <div className="provider-card__subtitle">{skill.path}</div>
      </div>
      <div className="settings-item__actions settings-item__actions--provider command-card__actions">
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
  candidate: SkillCandidateView;
  isInstalling: boolean;
  disabled: boolean;
  onInstall: () => void;
}) {
  return (
    <div className="skill-candidate">
      <div className="skill-candidate__main">
        <div className="skill-candidate__name">{candidate.name}</div>
        <p className="skill-candidate__description">
          {candidate.description || "No description provided."}
        </p>
        {candidate.subpath ? (
          <Badge variant="secondary">
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
  listing: SkillCandidatesPayload | null,
): string | null {
  return listing?.source ?? null;
}

export function SkillsSettingsSection({ skills }: { skills: SkillView[] }) {
  const queryClient = useQueryClient();
  const [previewSkill, setPreviewSkill] = useState<SkillView | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [customSource, setCustomSource] = useState("");
  const [listing, setListing] = useState<SkillCandidatesPayload | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [installingSkill, setInstallingSkill] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [conflictRetry, setConflictRetry] = useState<{
    source: string | null;
    skillName: string;
  } | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function resetDialogState() {
    setCustomSource("");
    setListing(null);
    setLoadingCandidates(false);
    setCandidatesError(null);
    setInstallingSkill(null);
    setInstallError(null);
    setConflictRetry(null);
  }

  async function loadCandidates(source: string | null) {
    setLoadingCandidates(true);
    setCandidatesError(null);
    setInstallError(null);
    setConflictRetry(null);
    try {
      const response = await fetchSkillCandidates(source);
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
    response: SkillInstallPayload,
    skillName: string,
  ) {
    queryClient.setQueryData<ConfigBootstrapPayload>(
      ["config-bootstrap"],
      (current) =>
        current
          ? {
              ...current,
              skills: response.skills,
              config_revision: response.config_revision,
            }
          : current,
    );
    setSuccessMessage(
      `Installed ${skillName}. New sessions can use it immediately; active sessions can run /reload.`,
    );
    closeAddDialog();
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["config-bootstrap"] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap"] }),
    ]);
  }

  async function handleInstall(
    candidate: SkillCandidateView,
    force = false,
    overrideSource?: string | null,
  ) {
    const source = overrideSource ?? candidateInstallSource(listing);
    setInstallingSkill(candidate.name);
    setInstallError(null);
    if (!force) setConflictRetry(null);
    try {
      const response = await installSkill({
        source,
        skill_name: candidate.name,
        ...(force ? { force: true } : {}),
      });
      await applyInstallResponse(response, candidate.name);
    } catch (err) {
      const message = (err as Error).message;
      setInstallError(message);
      if (err instanceof ApiError && err.status === 409) {
        setConflictRetry({ source, skillName: candidate.name });
      } else {
        setConflictRetry(null);
      }
    } finally {
      setInstallingSkill(null);
    }
  }

  function handleBrowseCustomSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const source = customSource.trim();
    void loadCandidates(source || null);
  }

  const candidates = listing?.candidates ?? [];
  const sourceLabel = listing?.source ?? "Official catalog";
  const isBusy = loadingCandidates || installingSkill !== null;

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
          New sessions see installed skills immediately. Active sessions can run{" "}
          <code className="command-hint__path">/reload</code> before the next model request.
        </AlertDescription>
      </Alert>

      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Project Skills</CardTitle>
            <div className="settings-panel__subtitle">
              Installed Agent Skills from .agents/skills
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
            Add Skill
          </Button>
        </CardHeader>
        <CardContent className="settings-panel__body">
          {skills.length === 0 ? (
            <EmptyState
              title="No project skills installed"
              description="Add skills from the official catalog, GitHub, or a server-side local path."
            />
          ) : (
            skills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                onPreview={() => setPreviewSkill(skill)}
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
        <DialogContent className="task-form-dialog skill-add-dialog">
          <DialogHeader>
            <DialogTitle>Add Project Skill</DialogTitle>
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
                    <FieldLabel htmlFor="skill-source">Custom source</FieldLabel>
                    <div className="skill-source-form__row">
                      <Input
                        id="skill-source"
                        className="task-form__input"
                        value={customSource}
                        onChange={(event) => setCustomSource(event.target.value)}
                        placeholder="owner/repo or /path/to/skills"
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
                      Available skills
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
                    <AlertTitle>Could not load skills</AlertTitle>
                    <AlertDescription>{candidatesError}</AlertDescription>
                  </Alert>
                ) : null}

                {installError ? (
                  <Alert variant="destructive" className="task-form__error">
                    <AlertCircleIcon />
                    <AlertTitle>Could not install skill</AlertTitle>
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
                                  name: conflictRetry.skillName,
                                  description: "",
                                  subpath: null,
                                },
                                true,
                                conflictRetry.source,
                              )
                            }
                            disabled={installingSkill !== null}
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
                      title="No skills found"
                      description="Try another source or browse the official catalog."
                    />
                  ) : (
                    candidates.map((candidate) => (
                      <CandidateCard
                        key={`${sourceLabel}:${candidate.name}`}
                        candidate={candidate}
                        isInstalling={installingSkill === candidate.name}
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

      {previewSkill ? (
        <SettingsPreviewDialog
          title={previewSkill.name}
          path={previewSkill.path}
          content={previewSkill.instructions}
          icon={SparklesIcon}
          onClose={() => setPreviewSkill(null)}
        />
      ) : null}
    </section>
  );
}
