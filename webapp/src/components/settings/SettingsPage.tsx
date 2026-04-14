import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createModelProfile,
  createProvider,
  deleteModelProfile,
  deleteProvider,
  fetchConfigBootstrap,
  setActiveModelProfile,
  updateModelProfile,
  updateProvider,
} from "../../api";
import { ApiError } from "../../api";
import type {
  ConfigBootstrapPayload,
  ModelProfileView,
  ModeView,
  ProviderView,
} from "../../types";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import type { ProfilePayload } from "./ModelProfileModal";
import { ModelProfileModal } from "./ModelProfileModal";
import type { ProviderPayload } from "./ProviderModal";
import { ProviderModal } from "./ProviderModal";

// ── Card sub-components ──────────────────────────────────────────────────────

function ProviderCard({
  provider,
  onEdit,
  onDelete,
}: {
  provider: ProviderView;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="settings-item">
      <div className="settings-item__info">
        <div className="settings-item__name">{provider.name}</div>
        <div className="settings-item__id">{provider.id}</div>
        <div className="settings-item__meta">
          <span className="settings-item__tag">{provider.kind}</span>
          {provider.has_secret && (
            <span className="settings-item__tag settings-item__tag--success">
              {provider.secret_source === "env_var"
                ? (provider.secret_env_var ?? "env var")
                : "key: set"}
            </span>
          )}
          {provider.responses_url && (
            <span
              className="settings-item__tag"
              title={provider.responses_url}
            >
              custom responses URL
            </span>
          )}
          {provider.generic_api_url && (
            <span
              className="settings-item__tag"
              title={provider.generic_api_url}
            >
              custom API URL
            </span>
          )}
        </div>
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

function ProfileCard({
  profile,
  onEdit,
  onDelete,
}: {
  profile: ModelProfileView;
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
          <span className="settings-item__tag">{profile.provider.kind}</span>
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

function CommandCard({
  command,
}: {
  command: ModeView;
}) {
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

// ── Modal state discriminated union ─────────────────────────────────────────

type ModalState =
  | { type: "none" }
  | { type: "create-provider" }
  | { type: "edit-provider"; provider: ProviderView }
  | { type: "delete-provider"; provider: ProviderView }
  | { type: "create-profile" }
  | { type: "edit-profile"; profile: ModelProfileView }
  | { type: "delete-profile"; profile: ModelProfileView };

const STALE_MESSAGE =
  "Settings were changed while you were editing. Please review and resubmit.";

// ── SettingsPage ─────────────────────────────────────────────────────────────

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [modal, setModal] = useState<ModalState>({ type: "none" });
  const [pageError, setPageError] = useState<string | null>(null);

  const configQuery = useQuery({
    queryKey: ["config-bootstrap"],
    queryFn: fetchConfigBootstrap,
    staleTime: 30_000,
  });

  // ── Helpers ────────────────────────────────────────────────────────────────

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
      // Business-logic conflict (e.g. "still references it") – surface
      // the real backend message so the user knows what to fix.
      throw err;
    }
    throw err;
  }

  // ── Provider handlers ──────────────────────────────────────────────────────

  async function saveProvider(
    payload: ProviderPayload,
    existingId?: string,
  ): Promise<void> {
    try {
      if (existingId) {
        await updateProvider(existingId, payload, getRevision());
      } else {
        await createProvider(payload, getRevision());
      }
      await invalidateBoth();
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

  // ── Profile handlers ───────────────────────────────────────────────────────

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

  async function handleSetActiveProfile(
    profileId: string | null,
  ): Promise<void> {
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

  // ── Render ─────────────────────────────────────────────────────────────────

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
            Failed to load settings:{" "}
            {(configQuery.error as Error)?.message ?? "Unknown error"}
          </div>
        </div>
      </div>
    );
  }

  const {
    providers,
    model_profiles,
    modes: commands,
    active_profile_id,
    options,
  } = configQuery.data;

  return (
    <div className="settings-page">
      <div className="settings-page__inner">
        {model_profiles.length === 0 && (
          <div className="settings-inline-note settings-onboarding-guide">
            <strong>First-time setup:</strong> To start using the app, complete these steps:
            <ol>
              <li>Add a provider with your API credentials</li>
              <li>Create a model profile that uses that provider</li>
            </ol>
          </div>
        )}

        {pageError && (
          <div className="settings-error-banner">{pageError}</div>
        )}

        {/* ── Providers panel ── */}
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
              providers.map((p) => (
                <ProviderCard
                  key={p.id}
                  provider={p}
                  onEdit={() => setModal({ type: "edit-provider", provider: p })}
                  onDelete={() =>
                    setModal({ type: "delete-provider", provider: p })
                  }
                />
              ))
            )}
          </div>
        </div>

        {/* ── Model Profiles panel ── */}
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
              title={
                providers.length === 0
                  ? "Add a provider first"
                  : undefined
              }
            >
              + Add Profile
            </button>
          </div>
          <div className="settings-panel__body">
            <div className="active-profile-control">
              <span className="active-profile-control__label">
                Active default
              </span>
              <select
                name="active-profile"
                className="active-profile-control__select"
                value={active_profile_id ?? ""}
                onChange={(e) =>
                  void handleSetActiveProfile(e.target.value || null)
                }
              >
                <option value="">No default</option>
                {model_profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
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
              model_profiles.map((p) => (
                <ProfileCard
                  key={p.id}
                  profile={p}
                  onEdit={() => setModal({ type: "edit-profile", profile: p })}
                  onDelete={() =>
                    setModal({ type: "delete-profile", profile: p })
                  }
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
              Add Markdown files under <code>.agents/commands/</code>; a file
              like <code>.agents/commands/review.md</code> becomes{" "}
              <code>/review</code>.
            </div>

            {commands.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state__title">No commands found</div>
                <div className="empty-state__description">
                  Add project command files under .agents/commands/.
                </div>
              </div>
            ) : (
              commands.map((command) => (
                <CommandCard
                  key={command.id}
                  command={command}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {/* ── Modals ── */}
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
              Delete provider <strong>{modal.provider.name}</strong>? This
              cannot be undone.
            </>
          }
          onConfirm={() => deleteProviderById(modal.provider.id)}
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
              Delete profile <strong>{modal.profile.name}</strong>? This cannot
              be undone.
            </>
          }
          onConfirm={() => deleteProfileById(modal.profile.id)}
          onClose={() => setModal({ type: "none" })}
        />
      )}
    </div>
  );
}
