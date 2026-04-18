import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
    <div className="settings-item settings-item--provider">
      <div className="settings-item__info">
        <div className="settings-item__name">{provider.name}</div>
        <div className="settings-item__id">{provider.id}</div>
        <div className="settings-item__meta">
          <span className="settings-item__tag">{providerKindLabel(provider.kind, options)}</span>
          <span className="settings-item__tag settings-item__tag--accent">
            {authModeLabel(provider, options)}
          </span>
          <span
            className={`settings-item__tag ${
              authStatus.session_status === "connected"
                ? "settings-item__tag--success"
                : authStatus.session_status === "expired"
                  ? "settings-item__tag--warning"
                  : ""
            }`}
          >
            {authStatusLabel(authStatus)}
          </span>
          {provider.auth_mode === "api_key" && provider.has_secret && (
            <span className="settings-item__tag settings-item__tag--success">
              {provider.secret_source === "env_var"
                ? (provider.secret_env_var ?? "env var")
                : "key: set"}
            </span>
          )}
          {authStatus.plan_type && (
            <span className="settings-item__tag">{authStatus.plan_type}</span>
          )}
          {provider.responses_url && (
            <span className="settings-item__tag" title={provider.responses_url}>
              custom responses URL
            </span>
          )}
          {provider.generic_api_url && (
            <span className="settings-item__tag" title={provider.generic_api_url}>
              custom API URL
            </span>
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
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={onConnect}
              disabled={isBusy}
            >
              {authStatus.has_session ? "Reconnect" : "Connect"}
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={onRefresh}
              disabled={isBusy || !authStatus.can_refresh}
            >
              Refresh
            </button>
            <button
              type="button"
              className="btn btn--ghost-danger btn--sm"
              onClick={onDisconnect}
              disabled={isBusy || !authStatus.has_session}
            >
              Disconnect
            </button>
          </>
        )}
        <button type="button" className="btn btn--ghost btn--sm" onClick={onEdit}>
          Edit
        </button>
        <button
          type="button"
          className="btn btn--ghost-danger btn--sm"
          onClick={onDelete}
          disabled={isBusy}
        >
          Delete
        </button>
      </div>
    </div>
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
    <div className="settings-item">
      <div className="settings-item__info">
        <div className="settings-item__name">
          {profile.name}
          {profile.is_active_default && (
            <span className="settings-item__tag settings-item__tag--accent">
              default
            </span>
          )}
        </div>
        <div className="settings-item__id">{profile.id}</div>
        <div className="settings-item__meta">
          <span className="settings-item__tag">{profile.provider.name}</span>
          <span className="settings-item__tag">
            {providerKindLabel(profile.provider.kind, options)}
          </span>
        </div>
        <div className="runtime-summary">{runtimeParts.join(" · ")}</div>
      </div>
      <div className="settings-item__actions">
        <button type="button" className="btn btn--ghost btn--sm" onClick={onEdit}>
          Edit
        </button>
        <button
          type="button"
          className="btn btn--ghost-danger btn--sm"
          onClick={onDelete}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function CommandCard({ command }: { command: CommandView }) {
  return (
    <div className="settings-item settings-item--command">
      <div className="settings-item__info">
        <div className="settings-item__name">{command.name}</div>
        <div className="settings-item__id">{command.id}</div>
        <div className="settings-item__meta">
          <span className="settings-item__tag settings-item__tag--accent">
            {command.slash_alias}
          </span>
          <span className="settings-item__tag">{command.path}</span>
        </div>
        {command.description && (
          <div className="settings-item__summary">{command.description}</div>
        )}
        <pre className="settings-item__instructions">{command.instructions}</pre>
      </div>
    </div>
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
          <div className="settings-error-banner">
            Failed to load settings: {(configQuery.error as Error)?.message ?? "Unknown error"}
          </div>
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
          <div className="settings-inline-note settings-onboarding-guide">
            <strong>First-time setup:</strong> To start using the app, complete these
            steps:
            <ol>
              <li>Add a provider and finish any sign-in step</li>
              <li>Create a model profile that uses that provider</li>
            </ol>
          </div>
        )}

        {pageError && <div className="settings-error-banner">{pageError}</div>}

        <div className="settings-panel">
          <div className="settings-panel__header">
            <div>
              <div className="settings-panel__title">Providers</div>
              <div className="settings-panel__subtitle">
                LLM provider connections and credentials
              </div>
            </div>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setModal({ type: "create-provider" })}
            >
              + Add Provider
            </button>
          </div>
          <div className="settings-panel__body">
            {providers.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state__title">No providers configured</div>
                <div className="empty-state__description">
                  Add a provider to start using model profiles.
                </div>
              </div>
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
          </div>
        </div>

        <div className="settings-panel">
          <div className="settings-panel__header">
            <div>
              <div className="settings-panel__title">Model Profiles</div>
              <div className="settings-panel__subtitle">
                Runtime configuration combining a provider with model settings
              </div>
            </div>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setModal({ type: "create-profile" })}
              disabled={providers.length === 0}
              title={providers.length === 0 ? "Add a provider first" : undefined}
            >
              + Add Profile
            </button>
          </div>
          <div className="settings-panel__body">
            <div className="active-profile-control">
              <span className="active-profile-control__label">Active default</span>
              <select
                name="active-profile"
                className="active-profile-control__select"
                value={active_profile_id ?? ""}
                onChange={(e) => {
                  void handleSetActiveProfile(e.target.value || null);
                }}
              >
                <option value="">No default</option>
                {model_profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </div>

            {model_profiles.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state__title">No profiles configured</div>
                <div className="empty-state__description">
                  Add a model profile to configure runtime settings.
                </div>
              </div>
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
          </div>
        </div>

        <div className="settings-panel">
          <div className="settings-panel__header">
            <div>
              <div className="settings-panel__title">Commands</div>
              <div className="settings-panel__subtitle">
                Project command files for single-turn prompt presets
              </div>
            </div>
          </div>
          <div className="settings-panel__body">
            <div className="settings-inline-note">
              Add Markdown files under <code>.agents/commands/</code>; a file like
              <code>.agents/commands/review.md</code> becomes <code>/review</code>.
            </div>

            {commands.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state__title">No commands found</div>
                <div className="empty-state__description">
                  Add project command files under .agents/commands/.
                </div>
              </div>
            ) : (
              commands.map((command) => <CommandCard key={command.id} command={command} />)
            )}
          </div>
        </div>
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
