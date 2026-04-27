import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangleIcon, CheckCircle2Icon, EditIcon, PlugZapIcon, PlusIcon, Trash2Icon, UnplugIcon } from "lucide-react";
import {
  createModelProfile,
  createProvider,
  deleteModelProfile,
  deleteProvider,
  fetchConfigBootstrap,
  logoutProviderAuth,
  refreshProviderAuth,
  setActiveModelProfile,
  updateModelProfile,
  updateProvider,
} from "../../api";
import { ApiError } from "../../api";
import type {
  CommandView,
  ConfigBootstrapPayload,
  ConfigOptions,
  ModelProfileView,
  ProviderAuthStatus,
  ProviderView,
} from "../../types";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import type { ProfilePayload } from "./ModelProfileModal";
import { ModelProfileModal } from "./ModelProfileModal";
import { ProviderAuthFlowModal } from "./ProviderAuthFlowModal";
import type { ProviderPayload } from "./ProviderModal";
import { ProviderModal } from "./ProviderModal";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { EmptyState } from "../shared/EmptyState";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";

function authModeLabel(provider: ProviderView, options: ConfigOptions): string {
  return (
    options.provider_metadata[provider.kind]?.auth_mode_metadata[provider.auth_mode]
      ?.label ?? provider.auth_mode
  );
}

function providerKindLabel(providerKind: string, options: ConfigOptions): string {
  return options.provider_metadata[providerKind]?.label ?? providerKind;
}

function authStatusLabel(status: ProviderAuthStatus): string {
  if (status.auth_mode === "api_key") {
    return "API key";
  }
  switch (status.session_status) {
    case "connected":
      return "connected";
    case "expired":
      return "expired";
    default:
      return "not connected";
  }
}

function formatAuthExpiry(expiresAt: number | null): string | null {
  if (!expiresAt) {
    return null;
  }
  return new Date(expiresAt * 1000).toLocaleString();
}

function ProviderCard({
  provider,
  options,
  isBusy,
  onEdit,
  onDelete,
  onConnect,
  onRefresh,
  onDisconnect,
}: {
  provider: ProviderView;
  options: ConfigOptions;
  isBusy: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onConnect: () => void;
  onRefresh: () => void;
  onDisconnect: () => void;
}) {
  const authStatus = provider.auth_status;
  const authExpires = formatAuthExpiry(authStatus.expires_at);
  const showAuthActions = provider.auth_mode !== "api_key";

  return (
    <Card className="settings-item settings-item--provider">
      <div className="settings-item__info">
        <div className="settings-item__name">{provider.name}</div>
        <div className="settings-item__id">{provider.id}</div>
        <div className="settings-item__meta">
          <Badge variant="secondary" className="settings-item__tag">{providerKindLabel(provider.kind, options)}</Badge>
          <Badge variant="outline" className="settings-item__tag settings-item__tag--accent">
            {authModeLabel(provider, options)}
          </Badge>
          <Badge
            variant="secondary"
            className={`settings-item__tag ${authStatus.session_status === "connected"
                ? "settings-item__tag--success"
                : authStatus.session_status === "expired"
                  ? "settings-item__tag--warning"
                  : ""
              }`}
          >
            {authStatusLabel(authStatus)}
          </Badge>
          {provider.auth_mode === "api_key" && provider.has_secret && (
            <Badge variant="secondary" className="settings-item__tag settings-item__tag--success">
              {provider.secret_source === "env_var"
                ? (provider.secret_env_var ?? "env var")
                : "key: set"}
            </Badge>
          )}
          {authStatus.plan_type && (
            <Badge variant="outline" className="settings-item__tag">{authStatus.plan_type}</Badge>
          )}
          {provider.responses_url && (
            <Badge variant="outline" className="settings-item__tag" title={provider.responses_url}>
              custom responses URL
            </Badge>
          )}
          {provider.generic_api_url && (
            <Badge variant="outline" className="settings-item__tag" title={provider.generic_api_url}>
              custom API URL
            </Badge>
          )}
        </div>
        {(authStatus.email || authExpires || authStatus.backend) && (
          <div className="settings-item__summary">
            {authStatus.email && <div>{authStatus.email}</div>}
            {authStatus.backend && <div>Backend: {authStatus.backend}</div>}
            {authExpires && <div>Expires: {authExpires}</div>}
          </div>
        )}
      </div>
      <div className="settings-item__actions settings-item__actions--provider">
        {showAuthActions && (
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="task-card__action-button"
              onClick={onConnect}
              disabled={isBusy}
            >
              <PlugZapIcon data-icon="inline-start" />
              {authStatus.has_session ? "Reconnect" : "Connect"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="task-card__action-button"
              onClick={onRefresh}
              disabled={isBusy || !authStatus.can_refresh}
            >
              <CheckCircle2Icon data-icon="inline-start" />
              Refresh
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="task-card__action-button"
              onClick={onDisconnect}
              disabled={isBusy || !authStatus.has_session}
            >
              <UnplugIcon data-icon="inline-start" />
              Disconnect
            </Button>
          </>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="task-card__action-button"
          onClick={onEdit}
        >
          <EditIcon data-icon="inline-start" />
          Edit
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="task-card__action-button"
          onClick={onDelete}
          disabled={isBusy}
        >
          <Trash2Icon data-icon="inline-start" />
          Delete
        </Button>
      </div>
    </Card>
  );
}

function ProfileCard({
  profile,
  options,
  onEdit,
  onDelete,
}: {
  profile: ModelProfileView;
  options: ConfigOptions;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const r = profile.resolved_runtime;
  const runtimeParts: string[] = [r.model];
  if (r.reasoning_effort && r.reasoning_effort !== "none") {
    runtimeParts.push(r.reasoning_effort);
  }
  if (r.service_tier) {
    runtimeParts.push(r.service_tier);
  }

  return (
    <Card className="settings-item">
      <div className="settings-item__info">
        <div className="settings-item__name">
          {profile.name}
          {profile.is_active_default && (
            <Badge variant="outline" className="settings-item__tag settings-item__tag--accent">
              default
            </Badge>
          )}
        </div>
        <div className="settings-item__id">{profile.id}</div>
        <div className="settings-item__meta">
          <Badge variant="outline" className="settings-item__tag">{profile.provider.name}</Badge>
          <Badge variant="outline" className="settings-item__tag">
            {providerKindLabel(profile.provider.kind, options)}
          </Badge>
        </div>
        <div className="runtime-summary">{runtimeParts.join(" · ")}</div>
      </div>
      <div className="settings-item__actions">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="task-card__action-button"
          onClick={onEdit}
        >
          <EditIcon data-icon="inline-start" />
          Edit
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="task-card__action-button"
          onClick={onDelete}
        >
          <Trash2Icon data-icon="inline-start" />
          Delete
        </Button>
      </div>
    </Card>
  );
}

function CommandCard({ command }: { command: CommandView }) {
  return (
    <Card className="settings-item settings-item--command">
      <div className="settings-item__info">
        <div className="settings-item__name">{command.name}</div>
        <div className="settings-item__id">{command.id}</div>
        <div className="settings-item__meta">
          <Badge variant="outline" className="settings-item__tag settings-item__tag--accent">
            {command.slash_alias}
          </Badge>
          <Badge variant="secondary" className="settings-item__tag">{command.path}</Badge>
        </div>
        {command.description && (
          <div className="settings-item__summary">{command.description}</div>
        )}
        <pre className="settings-item__instructions">{command.instructions}</pre>
      </div>
    </Card>
  );
}

type ModalState =
  | { type: "none" }
  | { type: "create-provider" }
  | { type: "edit-provider"; provider: ProviderView }
  | { type: "delete-provider"; provider: ProviderView }
  | { type: "provider-auth"; provider: ProviderView }
  | { type: "create-profile" }
  | { type: "edit-profile"; profile: ModelProfileView }
  | { type: "delete-profile"; profile: ModelProfileView };

const STALE_MESSAGE =
  "Settings were changed while you were editing. Please review and resubmit.";

function shouldPromptProviderAuth(provider: ProviderView): boolean {
  return provider.auth_mode !== "api_key";
}

export function SettingsPage() {
  const queryClient = useQueryClient();
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

  if (configQuery.isLoading) {
    return (
      <div className="center-spinner">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (configQuery.isError || !configQuery.data) {
    return (
      <div className="settings-page">
        <div className="settings-page__inner">
          <Alert variant="destructive" className="settings-error-banner">
            <AlertTriangleIcon />
            <AlertDescription>
              Failed to load settings: {(configQuery.error as Error)?.message ?? "Unknown error"}
            </AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  const { providers, model_profiles, commands, active_profile_id, options } =
    configQuery.data;

  return (
    <div className="settings-page">
      <div className="settings-page__inner">
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

        <Card className="settings-panel">
          <CardHeader className="settings-panel__header">
            <div>
              <CardTitle className="settings-panel__title">Providers</CardTitle>
              <div className="settings-panel__subtitle">
                LLM provider connections and credentials
              </div>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="task-card__action-button"
              onClick={() => setModal({ type: "create-provider" })}
            >
              <PlusIcon data-icon="inline-start" />
              Add Provider
            </Button>
          </CardHeader>
          <CardContent className="settings-panel__body">
            {providers.length === 0 ? (
              <EmptyState
                title="No providers configured"
                description="Add a provider to start using model profiles."
              />
            ) : (
              providers.map((provider) => (
                <ProviderCard
                  key={provider.id}
                  provider={provider}
                  options={options}
                  isBusy={busyProviderId === provider.id}
                  onEdit={() => setModal({ type: "edit-provider", provider })}
                  onDelete={() => setModal({ type: "delete-provider", provider })}
                  onConnect={() => setModal({ type: "provider-auth", provider })}
                  onRefresh={() => {
                    void handleRefreshProviderAuth(provider.id);
                  }}
                  onDisconnect={() => {
                    void handleDisconnectProviderAuth(provider.id);
                  }}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card className="settings-panel">
          <CardHeader className="settings-panel__header">
            <div>
              <CardTitle className="settings-panel__title">Model Profiles</CardTitle>
              <div className="settings-panel__subtitle">
                Runtime configuration combining a provider with model settings
              </div>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="task-card__action-button"
              onClick={() => setModal({ type: "create-profile" })}
              disabled={providers.length === 0}
              title={providers.length === 0 ? "Add a provider first" : undefined}
            >
              <PlusIcon data-icon="inline-start" />
              Add Profile
            </Button>
          </CardHeader>
          <CardContent className="settings-panel__body">
            <div className="active-profile-control">
              <span className="active-profile-control__label">Active default</span>
              <NativeSelect
                name="active-profile"
                className="active-profile-control__select"
                value={active_profile_id ?? ""}
                onChange={(e) => {
                  void handleSetActiveProfile(e.target.value || null);
                }}
              >
                <NativeSelectOption value="">No default</NativeSelectOption>
                {model_profiles.map((profile) => (
                  <NativeSelectOption key={profile.id} value={profile.id}>
                    {profile.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>

            {model_profiles.length === 0 ? (
              <EmptyState
                title="No profiles configured"
                description="Add a model profile to configure runtime settings."
              />
            ) : (
              model_profiles.map((profile) => (
                <ProfileCard
                  key={profile.id}
                  profile={profile}
                  options={options}
                  onEdit={() => setModal({ type: "edit-profile", profile })}
                  onDelete={() => setModal({ type: "delete-profile", profile })}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card className="settings-panel">
          <CardHeader className="settings-panel__header">
            <div>
              <CardTitle className="settings-panel__title">Commands</CardTitle>
              <div className="settings-panel__subtitle">
                Project command files for single-turn prompt presets
              </div>
            </div>
          </CardHeader>
          <CardContent className="settings-panel__body">
            <Alert className="settings-inline-note">
              <AlertDescription>
                Add Markdown files under <code>.agents/commands/</code>; a file like
                <code>.agents/commands/review.md</code> becomes <code>/review</code>.
              </AlertDescription>
            </Alert>

            {commands.length === 0 ? (
              <EmptyState
                title="No commands found"
                description="Add project command files under .agents/commands/."
              />
            ) : (
              commands.map((command) => <CommandCard key={command.id} command={command} />)
            )}
          </CardContent>
        </Card>
      </div>

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
    </div>
  );
}
