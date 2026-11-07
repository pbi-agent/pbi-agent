import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Dialog as DialogPrimitive } from "radix-ui";
import { AlertTriangleIcon, XIcon } from "lucide-react";
import {
  createModelProfile,
  createProvider,
  deleteModelProfile,
  deleteProvider,
  fetchConfigBootstrap,
  logoutProviderAuth,
  refreshProviderAuth,
  setActiveModelProfile,
  setPromptEnhancementProfile,
  setSttProvider,
  updateMaintenanceConfig,
  updateModelProfile,
  updateProvider,
  updateUserProfile,
} from "../../api";
import { ApiError } from "../../api";
import type {
  ConfigBootstrapPayload,
  ModelProfileView,
  ProviderView,
  UserProfile,
} from "../../types";
import { useSettingsDialog } from "../../hooks/useSettingsDialog";
import { cn } from "@/lib/utils";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from "../ui/dialog";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import { AppearanceSettingsSection } from "./AppearanceSettingsSection";
import { AgentsSettingsSection } from "./AgentsSettingsSection";
import { ChannelsSettingsSection } from "./ChannelsSettingsSection";
import { CommandsSettingsSection } from "./CommandsSettingsSection";
import { ModelProfilesSettingsSection } from "./ModelProfilesSettingsSection";
import type { ProfilePayload } from "./ModelProfileModal";
import { ModelProfileModal } from "./ModelProfileModal";
import { MaintenanceSettingsSection } from "./MaintenanceSettingsSection";
import { HooksSettingsSection } from "./HooksSettingsSection";
import { NotificationsSettingsSection } from "./NotificationsSettingsSection";
import { ProviderAuthFlowModal } from "./ProviderAuthFlowModal";
import { ProviderUsageLimitsDialog } from "./ProviderUsageLimitsDialog";
import { ProvidersSettingsSection } from "./ProvidersSettingsSection";
import { ProfileSettingsSection } from "./ProfileSettingsSection";
import { PromptEnhancementSettingsSection } from "./PromptEnhancementSettingsSection";
import type { ProviderPayload } from "./ProviderModal";
import { ProviderModal } from "./ProviderModal";
import { SkillsSettingsSection } from "./SkillsSettingsSection";
import { SpeechSettingsSection } from "./SpeechSettingsSection";

type ModalState =
  | { type: "none" }
  | { type: "create-provider" }
  | { type: "edit-provider"; provider: ProviderView }
  | { type: "delete-provider"; provider: ProviderView }
  | { type: "provider-auth"; provider: ProviderView }
  | { type: "provider-usage"; provider: ProviderView }
  | { type: "create-profile" }
  | { type: "edit-profile"; profile: ModelProfileView }
  | { type: "delete-profile"; profile: ModelProfileView };

type UserProfileDraftState = {
  profile: UserProfile;
  sourceRevision: string;
};

const STALE_MESSAGE =
  "Settings were changed while you were editing. Please review and resubmit.";

type SettingsTabId =
  | "profile"
  | "appearance"
  | "notifications"
  | "providers"
  | "prompt-enhancement"
  | "speech"
  | "model-profiles"
  | "skills"
  | "channels"
  | "commands"
  | "agents"
  | "hooks"
  | "maintenance";

const SETTINGS_NAV_GROUPS: Array<{
  label: string;
  items: Array<{ id: SettingsTabId; label: string; description: string }>;
}> = [
    {
      label: "General",
      items: [
        {
          id: "profile",
          label: "Profile",
          description: "Identity and global instructions",
        },
      ],
    },
    {
      label: "Models",
      items: [
        {
          id: "providers",
          label: "Providers",
          description: "Connections and credentials",
        },
        {
          id: "model-profiles",
          label: "Model Profiles",
          description: "Runtime defaults",
        },
        {
          id: "speech",
          label: "Speech-to-text",
          description: "Dictation provider",
        },
        {
          id: "prompt-enhancement",
          label: "Prompt enhancement",
          description: "Composer model profile",
        },
      ],
    },
    {
      label: "Project",
      items: [
        {
          id: "commands",
          label: "Commands",
          description: "Prompt presets",
        },
        {
          id: "skills",
          label: "Skills",
          description: "Agent capabilities",
        },
        {
          id: "agents",
          label: "Agents",
          description: "Delegated workers",
        },
        {
          id: "hooks",
          label: "Hooks",
          description: "Command hook review",
        },
        {
          id: "channels",
          label: "Channels",
          description: "Messaging channels",
        },
      ],
    },
    {
      label: "Desktop",
      items: [
        {
          id: "appearance",
          label: "Appearance",
          description: "Theme and display",
        },
        {
          id: "notifications",
          label: "Notifications",
          description: "Desktop and sound alerts",
        },
      ],
    },
    {
      label: "Data",
      items: [
        {
          id: "maintenance",
          label: "Maintenance",
          description: "Retention and cleanup",
        },
      ],
    },
  ];

function shouldPromptProviderAuth(provider: ProviderView): boolean {
  return provider.auth_mode !== "api_key";
}

function providerSupportsModelProfiles(
  provider: ProviderView,
  data: ConfigBootstrapPayload,
): boolean {
  return (
    data.options.provider_metadata[provider.kind]?.supports_model_profiles !==
    false
  );
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { open, closeSettings } = useSettingsDialog();
  const [activeTab, setActiveTab] = useState<SettingsTabId>("providers");
  const [modal, setModal] = useState<ModalState>({ type: "none" });
  const [pageError, setPageError] = useState<string | null>(null);
  const [busyProviderId, setBusyProviderId] = useState<string | null>(null);
  const [userProfileDraft, setUserProfileDraft] =
    useState<UserProfileDraftState | null>(null);

  const configQuery = useQuery({
    queryKey: ["config-bootstrap"],
    queryFn: fetchConfigBootstrap,
    staleTime: 30_000,
  });

  function getRevision(): string {
    return (
      queryClient.getQueryData<ConfigBootstrapPayload>(["config-bootstrap"])
        ?.config_revision ?? ""
    );
  }

  async function invalidateBoth() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["config-bootstrap"] }),
      queryClient.invalidateQueries({ queryKey: ["bootstrap"] }),
    ]);
  }

  function handleStale() {
    void queryClient.refetchQueries({ queryKey: ["config-bootstrap"] });
  }

  function wrapStale(err: unknown): never {
    if (err instanceof ApiError && err.status === 409) {
      if (err.message.includes("Config has changed")) {
        handleStale();
        throw new Error(STALE_MESSAGE);
      }
      throw err;
    }
    throw err;
  }

  async function saveProvider(
    payload: ProviderPayload,
    existingId?: string,
  ): Promise<void> {
    try {
      const response = existingId
        ? await updateProvider(existingId, payload, getRevision())
        : await createProvider(payload, getRevision());
      if (existingId) {
        await invalidateBoth();
        setModal({ type: "none" });
        return;
      }

      await invalidateBoth();
      if (shouldPromptProviderAuth(response.provider)) {
        setModal({ type: "provider-auth", provider: response.provider });
        return;
      }
      setModal({ type: "none" });
    } catch (err) {
      wrapStale(err);
    }
  }

  async function deleteProviderById(providerId: string): Promise<void> {
    try {
      await deleteProvider(providerId, getRevision());
      await invalidateBoth();
      setModal({ type: "none" });
    } catch (err) {
      wrapStale(err);
    }
  }

  async function handleRefreshProviderAuth(providerId: string): Promise<void> {
    setPageError(null);
    setBusyProviderId(providerId);
    try {
      await refreshProviderAuth(providerId);
      await invalidateBoth();
    } catch (err) {
      setPageError((err as Error).message);
    } finally {
      setBusyProviderId(null);
    }
  }

  async function handleDisconnectProviderAuth(providerId: string): Promise<void> {
    setPageError(null);
    setBusyProviderId(providerId);
    try {
      await logoutProviderAuth(providerId);
      await invalidateBoth();
    } catch (err) {
      setPageError((err as Error).message);
    } finally {
      setBusyProviderId(null);
    }
  }

  async function saveProfile(
    payload: ProfilePayload,
    existingId?: string,
  ): Promise<void> {
    try {
      if (existingId) {
        await updateModelProfile(existingId, payload, getRevision());
      } else {
        await createModelProfile(payload, getRevision());
      }
      await invalidateBoth();
      setModal({ type: "none" });
    } catch (err) {
      wrapStale(err);
    }
  }

  async function deleteProfileById(profileId: string): Promise<void> {
    try {
      await deleteModelProfile(profileId, getRevision());
      await invalidateBoth();
      setModal({ type: "none" });
    } catch (err) {
      wrapStale(err);
    }
  }

  async function handleSetActiveProfile(profileId: string | null): Promise<void> {
    setPageError(null);
    try {
      await setActiveModelProfile(profileId, getRevision());
      await invalidateBoth();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        handleStale();
        setPageError(STALE_MESSAGE);
      } else {
        setPageError((err as Error).message);
      }
    }
  }

  async function handleSetSttProvider(providerId: string | null): Promise<void> {
    try {
      await setSttProvider(providerId, getRevision());
      await invalidateBoth();
    } catch (err) {
      wrapStale(err);
    }
  }

  async function handleSetPromptEnhancementProfile(
    profileId: string | null,
  ): Promise<void> {
    try {
      await setPromptEnhancementProfile(profileId, getRevision());
      await invalidateBoth();
    } catch (err) {
      wrapStale(err);
    }
  }

  async function handleSaveMaintenance(retentionDays: number): Promise<void> {
    try {
      await updateMaintenanceConfig(retentionDays, getRevision());
      await invalidateBoth();
    } catch (err) {
      wrapStale(err);
    }
  }

  async function handleSaveUserProfile(
    profile: ConfigBootstrapPayload["user_profile"],
  ): Promise<void> {
    try {
      await updateUserProfile(
        profile,
        userProfileDraft?.sourceRevision ?? getRevision(),
      );
      await invalidateBoth();
      setUserProfileDraft(null);
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.message.includes("Config has changed")
      ) {
        await queryClient.refetchQueries({ queryKey: ["config-bootstrap"] });
        const latestRevision = getRevision();
        setUserProfileDraft((current) =>
          current ? { ...current, sourceRevision: latestRevision } : current,
        );
        throw new Error(STALE_MESSAGE);
      }
      wrapStale(err);
    }
  }

  function handleUserProfileDraftChange(profile: UserProfile) {
    setUserProfileDraft((current) => ({
      profile,
      sourceRevision: current?.sourceRevision ?? getRevision(),
    }));
  }

  if (configQuery.isLoading) {
    return (
      <Dialog open={open} onOpenChange={(v) => { if (!v) closeSettings(); }}>
        <DialogPortal>
          <DialogOverlay />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
            <DialogPrimitive.Content asChild aria-describedby={undefined}>
              <div className="relative flex h-full max-h-192 w-full max-w-6xl flex-col overflow-hidden rounded-xl bg-background text-foreground shadow-lg ring-1 ring-foreground/10 duration-150 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95">
                <DialogTitle className="sr-only">Settings</DialogTitle>
                <div className="flex flex-1 items-center justify-center">
                  <LoadingSpinner size="lg" />
                </div>
              </div>
            </DialogPrimitive.Content>
          </div>
        </DialogPortal>
      </Dialog>
    );
  }

  if (configQuery.isError || !configQuery.data) {
    return (
      <Dialog open={open} onOpenChange={(v) => { if (!v) closeSettings(); }}>
        <DialogPortal>
          <DialogOverlay />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
            <DialogPrimitive.Content asChild aria-describedby={undefined}>
              <div className="relative flex h-auto w-full max-w-6xl flex-col overflow-hidden rounded-xl bg-background text-foreground shadow-lg ring-1 ring-foreground/10 duration-150 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95">
                <DialogTitle className="sr-only">Settings</DialogTitle>
                <div className="flex flex-col items-end gap-3 p-4">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={closeSettings}
                  >
                    <XIcon />
                    <span className="sr-only">Close</span>
                  </Button>
                  <Alert variant="destructive">
                    <AlertTriangleIcon />
                    <AlertDescription>
                      Failed to load settings: {(configQuery.error as Error)?.message ?? "Unknown error"}
                    </AlertDescription>
                  </Alert>
                </div>
              </div>
            </DialogPrimitive.Content>
          </div>
        </DialogPortal>
      </Dialog>
    );
  }

  const configData = configQuery.data;
  const {
    providers,
    model_profiles,
    commands,
    skills,
    agents,
    user_profile,
    active_profile_id,
    stt_provider_id,
    prompt_enhancement_profile_id,
    maintenance,
    options,
  } = configData;
  const modelCapableProviders = providers.filter((provider) =>
    providerSupportsModelProfiles(provider, configData),
  );

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) closeSettings(); }}>
      <DialogPortal>
        <DialogOverlay />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          <DialogPrimitive.Content asChild aria-describedby={undefined}>
            <div className="relative flex h-full max-h-192 w-full max-w-6xl flex-col overflow-hidden rounded-xl bg-background text-foreground shadow-lg ring-1 ring-foreground/10 duration-150 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95">
              <DialogTitle className="sr-only">Settings</DialogTitle>
              <div className="flex min-h-0 flex-1 flex-col">
                <div className="flex min-h-0 flex-1 flex-col md:flex-row">
                  <aside
                    className="flex min-w-0 shrink-0 flex-col gap-3 border-b md:w-60 border-border bg-muted/40 p-3 md:min-h-0 md:gap-5 md:overflow-hidden md:border-r md:border-b-0 md:px-3 md:py-5"
                    aria-label="Settings sections"
                  >
                    <div className="flex items-center justify-between gap-2 px-2">
                      <div className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                        Settings
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        onClick={closeSettings}
                      >
                        <XIcon />
                        <span className="sr-only">Close</span>
                      </Button>
                    </div>
                    <nav className="flex min-h-0 gap-4 overflow-x-auto md:flex-col md:overflow-y-auto">
                      {SETTINGS_NAV_GROUPS.map((group) => (
                        <div className="flex min-w-0 flex-col gap-1" data-settings-nav-group key={group.label}>
                          <div className="px-2 text-xs font-medium text-muted-foreground" data-settings-nav-group-label>
                            {group.label}
                          </div>
                          <div className="flex gap-1 md:flex-col">
                            {group.items.map((item) => (
                              <button
                                key={item.id}
                                type="button"
                                className={cn(
                                  "flex w-full min-w-0 flex-col items-start gap-0.5 rounded-md border border-transparent px-3 py-2 text-left text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
                                  activeTab === item.id && "border-border bg-muted text-foreground shadow-xs",
                                )}
                                aria-pressed={activeTab === item.id}
                                onClick={() => setActiveTab(item.id)}
                              >
                                <span className="text-sm font-medium whitespace-nowrap" data-settings-nav-label>
                                  {item.label}
                                </span>
                                <span className="hidden max-w-full truncate text-xs text-muted-foreground md:block">
                                  {item.description}
                                </span>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </nav>
                  </aside>

                  <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain p-4 md:p-5">
                    {(model_profiles.length === 0 || pageError) && (
                      <div className="flex flex-col gap-3">
                        {model_profiles.length === 0 && (
                          <Alert>
                            <AlertDescription>
                              <strong>First-time setup:</strong> To start using the app, complete these
                              steps:
                              <ol className="mt-1 list-decimal pl-5">
                                <li>Add an LLM provider and finish any sign-in step</li>
                                <li>Create a model profile that uses that provider</li>
                              </ol>
                            </AlertDescription>
                          </Alert>
                        )}

                        {pageError && (
                          <Alert variant="destructive">
                            <AlertTriangleIcon />
                            <AlertDescription>{pageError}</AlertDescription>
                          </Alert>
                        )}
                      </div>
                    )}

                    {activeTab === "appearance" && <AppearanceSettingsSection />}

                    {activeTab === "profile" && (
                      <ProfileSettingsSection
                        profile={user_profile}
                        draft={userProfileDraft?.profile ?? user_profile}
                        onDraftChange={handleUserProfileDraftChange}
                        onSave={handleSaveUserProfile}
                      />
                    )}

                    {activeTab === "notifications" && <NotificationsSettingsSection />}

                    {activeTab === "providers" && (
                      <ProvidersSettingsSection
                        providers={providers}
                        options={options}
                        busyProviderId={busyProviderId}
                        onCreate={() => setModal({ type: "create-provider" })}
                        onEdit={(provider) => setModal({ type: "edit-provider", provider })}
                        onDelete={(provider) => setModal({ type: "delete-provider", provider })}
                        onConnect={(provider) => setModal({ type: "provider-auth", provider })}
                        onRefresh={(providerId) => {
                          void handleRefreshProviderAuth(providerId);
                        }}
                        onDisconnect={(providerId) => {
                          void handleDisconnectProviderAuth(providerId);
                        }}
                        onShowUsage={(provider) => setModal({ type: "provider-usage", provider })}
                      />
                    )}

                    {activeTab === "speech" && (
                      <SpeechSettingsSection
                        providers={providers}
                        options={options}
                        sttProviderId={stt_provider_id}
                        onSave={handleSetSttProvider}
                      />
                    )}

                    {activeTab === "prompt-enhancement" && (
                      <PromptEnhancementSettingsSection
                        profiles={model_profiles}
                        profileId={prompt_enhancement_profile_id}
                        onSave={handleSetPromptEnhancementProfile}
                      />
                    )}

                    {activeTab === "model-profiles" && (
                      <ModelProfilesSettingsSection
                        profiles={model_profiles}
                        providers={modelCapableProviders}
                        activeProfileId={active_profile_id}
                        onSetActiveProfile={(profileId) => {
                          void handleSetActiveProfile(profileId);
                        }}
                        onCreate={() => setModal({ type: "create-profile" })}
                        onEdit={(profile) => setModal({ type: "edit-profile", profile })}
                        onDelete={(profile) => setModal({ type: "delete-profile", profile })}
                      />
                    )}

                    {activeTab === "skills" && <SkillsSettingsSection skills={skills} />}

                    {activeTab === "commands" && <CommandsSettingsSection commands={commands} />}

                    {activeTab === "agents" && <AgentsSettingsSection agents={agents} />}

                    {activeTab === "hooks" && <HooksSettingsSection />}

                    {activeTab === "channels" && <ChannelsSettingsSection />}

                    {activeTab === "maintenance" && (
                      <MaintenanceSettingsSection
                        maintenance={maintenance}
                        onSave={handleSaveMaintenance}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </DialogPrimitive.Content>
        </div>
      </DialogPortal>

      {modal.type === "create-provider" && (
        <ProviderModal
          options={options}
          onSave={(payload) => saveProvider(payload)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "edit-provider" && (
        <ProviderModal
          provider={modal.provider}
          options={options}
          onSave={(payload) => saveProvider(payload, modal.provider.id)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "delete-provider" && (
        <DeleteConfirmModal
          title="Delete Provider"
          body={
            <>
              Delete provider <strong>{modal.provider.name}</strong>? This cannot be
              undone.
            </>
          }
          onConfirm={() => deleteProviderById(modal.provider.id)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "provider-auth" && (
        <ProviderAuthFlowModal
          provider={modal.provider}
          options={options}
          onClose={() => setModal({ type: "none" })}
          onCompleted={invalidateBoth}
        />
      )}
      {modal.type === "provider-usage" && (
        <ProviderUsageLimitsDialog
          provider={modal.provider}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "create-profile" && (
        <ModelProfileModal
          providers={modelCapableProviders}
          options={options}
          onSave={(payload) => saveProfile(payload)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "edit-profile" && (
        <ModelProfileModal
          profile={modal.profile}
          providers={modelCapableProviders}
          options={options}
          onSave={(payload) => saveProfile(payload, modal.profile.id)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "delete-profile" && (
        <DeleteConfirmModal
          title="Delete Profile"
          body={
            <>
              Delete profile <strong>{modal.profile.name}</strong>? This cannot be
              undone.
            </>
          }
          onConfirm={() => deleteProfileById(modal.profile.id)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
    </Dialog>
  );
}
