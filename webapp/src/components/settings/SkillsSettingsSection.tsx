import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
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
  setAllSkillsEnabled,
  setSkillEnabled,
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
import { Switch } from "../ui/switch";

function SkillCard({
  skill,
  onPreview,
  onToggle,
  toggling,
}: {
  skill: SkillView;
  onPreview: () => void;
  onToggle: (enabled: boolean) => void;
  toggling: boolean;
}) {
  return (
    <Card size="sm" data-settings-item-card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words">
          {skill.name}
          {skill.enabled === false ? (
            <Badge size="meta" variant="secondary">
              disabled
            </Badge>
          ) : null}
        </CardTitle>
        {skill.description ? (
          <CardDescription>{skill.description}</CardDescription>
        ) : null}
        <CardDescription className="break-all">{skill.path}</CardDescription>
      </CardHeader>
      <CardFooter>
        <div className="flex w-full flex-wrap items-center justify-end gap-2">
          <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Switch
              size="sm"
              checked={skill.enabled !== false}
              disabled={toggling}
              onCheckedChange={onToggle}
              aria-label={`${skill.enabled !== false ? "Disable" : "Enable"} ${skill.name}`}
            />
            {skill.enabled !== false ? "Enabled" : "Disabled"}
          </label>
          <Button type="button" variant="ghost" size="sm" onClick={onPreview}>
            <EyeIcon data-icon="inline-start" />
            Preview
          </Button>
        </div>
      </CardFooter>
    </Card>
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
  candidate: SkillCandidateView;
  isInstalling: boolean;
  disabled: boolean;
  onInstall: () => void;
}) {
  return (
    <div className="flex min-w-0 items-start gap-3 rounded-lg border border-border p-3">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="text-sm font-medium break-words">{candidate.name}</div>
        <p className="text-sm text-muted-foreground">
          {candidate.description || "No description provided."}
        </p>
        {candidate.subpath ? (
          <Badge size="meta" variant="secondary">
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
  const [togglingSkill, setTogglingSkill] = useState<string | null>(null);
  const [togglingAll, setTogglingAll] = useState(false);

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

  async function applyInstallResponse(response: SkillInstallPayload) {
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
    closeAddDialog();
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["config-bootstrap"] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap"] }),
    ]);
  }

  async function applySkillListResponse(response: {
    skills: SkillView[];
    config_revision: string;
  }) {
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
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["config-bootstrap"] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap"] }),
    ]);
  }

  async function handleToggleSkill(skill: SkillView, enabled: boolean) {
    setTogglingSkill(skill.name);
    try {
      const response = await setSkillEnabled(skill.name, enabled);
      await applySkillListResponse(response);
    } catch {
      // Keep the tab free of notification cards.
    } finally {
      setTogglingSkill(null);
    }
  }

  async function handleToggleAll(enabled: boolean) {
    setTogglingAll(true);
    try {
      const response = await setAllSkillsEnabled(enabled);
      await applySkillListResponse(response);
    } catch {
      // Keep the tab free of notification cards.
    } finally {
      setTogglingAll(false);
    }
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
      await applyInstallResponse(response);
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
    <SettingsSection>
      <SettingsPanel
        title="Project Skills"
        description="Installed Agent Skills from .agents/skills"
        actions={
          <>
            {skills.length > 0 ? (
              <div
                className="flex items-center gap-1"
                role="group"
                aria-label="Toggle all skills"
              >
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void handleToggleAll(true)}
                  disabled={togglingAll}
                >
                  Enable all
                </Button>
                <Separator orientation="vertical" className="h-4" />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void handleToggleAll(false)}
                  disabled={togglingAll}
                >
                  Disable all
                </Button>
              </div>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={openAddDialog}
            >
              <PlusIcon data-icon="inline-start" />
              Add Skill
            </Button>
          </>
        }
      >
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
              onToggle={(enabled) => void handleToggleSkill(skill, enabled)}
              toggling={togglingSkill === skill.name}
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
            <DialogTitle>Add Project Skill</DialogTitle>
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
                    <FieldLabel htmlFor="skill-source">
                      Custom source
                    </FieldLabel>
                    <div className="flex gap-2">
                      <Input
                        id="skill-source"
                        className="flex-1"
                        value={customSource}
                        onChange={(event) =>
                          setCustomSource(event.target.value)
                        }
                        placeholder="owner/repo or /path/to/skills"
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
                    <div className="text-sm font-medium">Available skills</div>
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
                    <AlertTitle>Could not load skills</AlertTitle>
                    <AlertDescription>{candidatesError}</AlertDescription>
                  </Alert>
                ) : null}

                {installError ? (
                  <Alert variant="destructive">
                    <AlertCircleIcon />
                    <AlertTitle>Could not install skill</AlertTitle>
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

                <div className="flex min-w-0 flex-col gap-2" aria-live="polite">
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
    </SettingsSection>
  );
}
