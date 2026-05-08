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
  updateMaintenanceConfig,
  updateModelProfile,
  updateProvider,
} from "../../api";
import { ApiError } from "../../api";
import type {
  ConfigBootstrapPayload,
  ModelProfileView,
  ProviderView,
} from "../../types";
import { useSettingsDialog } from "../../hooks/useSettingsDialog";
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
import { CommandsSettingsSection } from "./CommandsSettingsSection";
import { ModelProfilesSettingsSection } from "./ModelProfilesSettingsSection";
import type { ProfilePayload } from "./ModelProfileModal";
import { ModelProfileModal } from "./ModelProfileModal";
import { MaintenanceSettingsSection } from "./MaintenanceSettingsSection";
import { NotificationsSettingsSection } from "./NotificationsSettingsSection";
import { ProviderAuthFlowModal } from "./ProviderAuthFlowModal";
import { ProviderUsageLimitsDialog } from "./ProviderUsageLimitsDialog";
import { ProvidersSettingsSection } from "./ProvidersSettingsSection";
import type { ProviderPayload } from "./ProviderModal";
import { ProviderModal } from "./ProviderModal";

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

const STALE_MESSAGE =
  "Settings were changed while you were editing. Please review and resubmit.";

type SettingsTabId = "appearance" | "notifications" | "providers" | "model-profiles" | "commands" | "maintenance";

const SETTINGS_NAV_GROUPS: Array<{
  label: string;
  items: Array<{ id: SettingsTabId; label: string; description: string }>;
}> = [
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
    label: "Server",
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
        id: "commands",
        label: "Commands",
        description: "Prompt presets",
      },
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

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { open, closeSettings } = useSettingsDialog();
  const [activeTab, setActiveTab] = useState<SettingsTabId>("notifications");
  const [modal, setModal] = useState<ModalState>({ type: "none" });
  const [pageError, setPageError] = useState<string | null>(null);
  const [busyProviderId, setBusyProviderId] = useState<string | null>(null);

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

  async function handleSaveMaintenance(retentionDays: number): Promise<void> {
    try {
      await updateMaintenanceConfig(retentionDays, getRevision());
      await invalidateBoth();
    } catch (err) {
      wrapStale(err);
    }
  }

  if (configQuery.isLoading) {
    return (
      <Dialog open={open} onOpenChange={(v) => { if (!v) closeSettings(); }}>
        <DialogPortal>
          <DialogOverlay className="settings-dialog__overlay" />
          <div className="settings-dialog">
            <DialogPrimitive.Content asChild aria-describedby={undefined}>
              <div className="settings-dialog__panel">
                <DialogTitle className="sr-only">Settings</DialogTitle>
                <div className="center-spinner">
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
          <DialogOverlay className="settings-dialog__overlay" />
          <div className="settings-dialog">
            <DialogPrimitive.Content asChild aria-describedby={undefined}>
              <div className="settings-dialog__panel settings-dialog__panel--error">
                <DialogTitle className="sr-only">Settings</DialogTitle>
                <div className="settings-error-layout">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
className="settings-nav__header-close app-close-icon-button"
                  onClick={closeSettings}
                >
                  <XIcon />
                  <span className="sr-only">Close</span>
                </Button>
                <Alert variant="destructive" className="settings-error-banner">
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

  const { providers, model_profiles, commands, active_profile_id, maintenance, options } =
    configQuery.data;

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) closeSettings(); }}>
      <DialogPortal>
        <DialogOverlay className="settings-dialog__overlay" />
        <div className="settings-dialog">
          <DialogPrimitive.Content asChild aria-describedby={undefined}>
            <div className="settings-dialog__panel">
              <DialogTitle className="sr-only">Settings</DialogTitle>
              <div className="settings-page__inner">
              <div className="settings-shell">
                <aside className="settings-nav" aria-label="Settings sections">
                  <div className="settings-nav__header">
                    <div className="settings-nav__eyebrow">Settings</div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
className="settings-nav__header-close app-close-icon-button"
                      onClick={closeSettings}
                    >
                      <XIcon />
                      <span className="sr-only">Close</span>
                    </Button>
                  </div>
                  {SETTINGS_NAV_GROUPS.map((group) => (
                    <div className="settings-nav__group" key={group.label}>
                      <div className="settings-nav__group-label">{group.label}</div>
                      <div className="settings-nav__items">
                        {group.items.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            className={`settings-nav__item ${activeTab === item.id ? "settings-nav__item--active" : ""}`}
                            aria-pressed={activeTab === item.id}
                            onClick={() => setActiveTab(item.id)}
                          >
                            <span className="settings-nav__item-label">{item.label}</span>
                            <span className="settings-nav__item-description">{item.description}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </aside>

                <div className="settings-tab-content">
                  {(model_profiles.length === 0 || pageError) && (
                    <div className="settings-global-alerts">
                      {model_profiles.length === 0 && (
                        <Alert className="settings-inline-note settings-onboarding-guide">
                          <AlertDescription>
                            <strong>First-time setup:</strong> To start using the app, complete these
                            steps:
                            <ol>
                              <li>Add a provider and finish any sign-in step</li>
                              <li>Create a model profile that uses that provider</li>
                            </ol>
                          </AlertDescription>
                        </Alert>
                      )}

                      {pageError && (
                        <Alert variant="destructive" className="settings-error-banner">
                          <AlertTriangleIcon />
                          <AlertDescription>{pageError}</AlertDescription>
                        </Alert>
                      )}
                    </div>
                  )}

                  {activeTab === "appearance" && <AppearanceSettingsSection />}

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

                  {activeTab === "model-profiles" && (
                    <ModelProfilesSettingsSection
                      profiles={model_profiles}
                      providers={providers}
                      activeProfileId={active_profile_id}
                      onSetActiveProfile={(profileId) => {
                        void handleSetActiveProfile(profileId);
                      }}
                      onCreate={() => setModal({ type: "create-profile" })}
                      onEdit={(profile) => setModal({ type: "edit-profile", profile })}
                      onDelete={(profile) => setModal({ type: "delete-profile", profile })}
                    />
                  )}

                  {activeTab === "commands" && <CommandsSettingsSection commands={commands} />}

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
          providers={providers}
          options={options}
          onSave={(payload) => saveProfile(payload)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
      {modal.type === "edit-profile" && (
        <ModelProfileModal
          profile={modal.profile}
          providers={providers}
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
