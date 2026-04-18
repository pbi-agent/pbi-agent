import { useEffect, useState, type FormEvent } from "react";
import type { ConfigOptions, ProviderView } from "../../types";

type SecretMode = "none" | "env_var" | "plaintext";

interface FormState {
  name: string;
  id: string;
  kind: string;
  auth_mode: string;
  secretMode: SecretMode;
  api_key: string;
  api_key_env: string;
  responses_url: string;
  generic_api_url: string;
}

function initForm(provider?: ProviderView, options?: ConfigOptions): FormState {
  if (provider) {
    return {
      name: provider.name,
      id: provider.id,
      kind: provider.kind,
      auth_mode: provider.auth_mode,
      secretMode:
        provider.secret_source === "env_var"
          ? "env_var"
          : provider.secret_source === "plaintext"
            ? "plaintext"
            : "none",
      api_key: "",
      api_key_env: provider.secret_env_var ?? "",
      responses_url: provider.responses_url ?? "",
      generic_api_url: provider.generic_api_url ?? "",
    };
  }

  const defaultKind = options?.provider_kinds[0] ?? "openai";
  const defaultMeta = options?.provider_metadata[defaultKind];
  return {
    name: "",
    id: "",
    kind: defaultKind,
    auth_mode: defaultMeta?.default_auth_mode ?? "api_key",
    secretMode: "env_var",
    api_key: "",
    api_key_env: "",
    responses_url: "",
    generic_api_url: "",
  };
}

export type ProviderPayload = {
  id?: string | null;
  name: string;
  kind: string;
  auth_mode?: string | null;
  api_key?: string | null;
  api_key_env?: string | null;
  responses_url?: string | null;
  generic_api_url?: string | null;
};

interface Props {
  provider?: ProviderView;
  options: ConfigOptions;
  onSave: (payload: ProviderPayload) => Promise<void>;
  onClose: () => void;
}

export function ProviderModal({ provider, options, onSave, onClose }: Props) {
  const isEdit = !!provider;
  const [form, setForm] = useState<FormState>(() => initForm(provider, options));
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  function set(updates: Partial<FormState>) {
    setForm((prev) => {
      const next = { ...prev, ...updates };
      if (updates.kind && updates.kind !== prev.kind) {
        const nextMeta = options.provider_metadata[updates.kind];
        next.auth_mode = nextMeta?.default_auth_mode ?? "api_key";
      }
      return next;
    });
  }

  const kindMeta = options.provider_metadata[form.kind];
  const authModes = kindMeta?.auth_modes ?? ["api_key"];
  const showAuthModePicker = authModes.length > 1;
  const isApiKeyAuth = form.auth_mode === "api_key";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsPending(true);
    setError(null);

    const payload: ProviderPayload = {
      name: form.name.trim(),
      kind: form.kind,
      auth_mode: form.auth_mode,
    };

    if (!isEdit && form.id.trim()) {
      payload.id = form.id.trim();
    }

    if (isApiKeyAuth) {
      if (form.secretMode === "env_var") {
        payload.api_key_env = form.api_key_env.trim() || null;
        payload.api_key = null;
      } else if (form.secretMode === "plaintext") {
        const trimmedKey = form.api_key.trim();
        if (trimmedKey) {
          payload.api_key = trimmedKey;
        } else if (!isEdit) {
          payload.api_key = null;
        }
        payload.api_key_env = null;
      } else {
        payload.api_key = null;
        payload.api_key_env = null;
      }
    } else {
      payload.api_key = null;
      payload.api_key_env = null;
    }

    if (kindMeta?.supports_responses_url) {
      payload.responses_url = form.responses_url.trim() || null;
      payload.generic_api_url = null;
    } else if (kindMeta?.supports_generic_api_url) {
      payload.generic_api_url = form.generic_api_url.trim() || null;
      payload.responses_url = null;
    } else {
      payload.responses_url = null;
      payload.generic_api_url = null;
    }

    try {
      await onSave(payload);
    } catch (err) {
      setError((err as Error).message);
      setIsPending(false);
    }
  }

  const secretModes: { value: SecretMode; label: string }[] = [
    { value: "env_var", label: "Env var" },
    { value: "plaintext", label: "API key" },
    { value: "none", label: "None" },
  ];

  const authModeMetadata = kindMeta?.auth_mode_metadata ?? {};
  const selectedAuthModeMetadata = authModeMetadata[form.auth_mode];
  const accountAuthLabel = selectedAuthModeMetadata?.account_label;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-card__header">
          <h2 className="modal-card__title">
            {isEdit ? "Edit Provider" : "Add Provider"}
          </h2>
          <button
            type="button"
            className="modal-card__close"
            onClick={onClose}
            disabled={isPending}
          >
            &times;
          </button>
        </div>

        <form
          className="task-form"
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
        >
          <div className="task-form__field">
            <label className="task-form__label">Name</label>
            <input
              name="provider-name"
              className="task-form__input"
              value={form.name}
              onChange={(e) => set({ name: e.target.value })}
              required
              autoFocus
              placeholder="e.g. My OpenAI"
            />
          </div>

          {!isEdit && (
            <div className="task-form__field">
              <label className="task-form__label">ID (optional)</label>
              <input
                name="provider-id"
                className="task-form__input"
                value={form.id}
                onChange={(e) => set({ id: e.target.value })}
                placeholder="Auto-generated from name"
              />
              <span className="task-form__hint">
                Leave blank to auto-generate from the name.
              </span>
            </div>
          )}

          <div className="task-form__field">
            <label className="task-form__label">Kind</label>
            <select
              name="provider-kind"
              className="task-form__select"
              value={form.kind}
              onChange={(e) => set({ kind: e.target.value })}
            >
              {options.provider_kinds.map((k) => (
                <option key={k} value={k}>
                  {options.provider_metadata[k]?.label ?? k}
                </option>
              ))}
            </select>
            {kindMeta?.description && (
              <span className="task-form__hint">{kindMeta.description}</span>
            )}
          </div>

          {showAuthModePicker && (
            <div className="task-form__field">
              <label className="task-form__label">Authentication</label>
              <div className="secret-mode-tabs provider-auth-mode-tabs">
                {authModes.map((authMode) => (
                  <button
                    key={authMode}
                    type="button"
                    className={`secret-mode-tab${form.auth_mode === authMode ? " active" : ""}`}
                    onClick={() => set({ auth_mode: authMode })}
                  >
                    {authModeMetadata[authMode]?.label ?? authMode}
                  </button>
                ))}
              </div>
            </div>
          )}

          {isApiKeyAuth ? (
            <div className="task-form__field">
              <label className="task-form__label">Credential source</label>
              <div className="secret-mode-tabs">
                {secretModes.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    className={`secret-mode-tab${form.secretMode === value ? " active" : ""}`}
                    onClick={() => set({ secretMode: value })}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="settings-inline-note provider-auth-inline-note">
              Save this provider to continue directly into sign-in for your{" "}
              {accountAuthLabel ?? "account"}.
            </div>
          )}

          {isApiKeyAuth && form.secretMode === "env_var" && (
            <div className="task-form__field">
              <label className="task-form__label">
                Environment variable name
              </label>
              <input
                name="api-key-env"
                className="task-form__input"
                value={form.api_key_env}
                onChange={(e) => set({ api_key_env: e.target.value })}
                placeholder="e.g. OPENAI_API_KEY"
              />
            </div>
          )}

          {isApiKeyAuth && form.secretMode === "plaintext" && (
            <div className="task-form__field">
              <label className="task-form__label">
                API key
                {isEdit ? " (leave blank to keep current)" : ""}
              </label>
              <input
                name="api-key"
                className="task-form__input"
                type="password"
                value={form.api_key}
                onChange={(e) => set({ api_key: e.target.value })}
                placeholder={isEdit ? "Enter new key to update" : "sk-…"}
                autoComplete="new-password"
              />
            </div>
          )}

          {kindMeta?.supports_responses_url && (
            <div className="task-form__field">
              <label className="task-form__label">
                Responses URL override
              </label>
              <input
                name="responses-url"
                className="task-form__input"
                type="text"
                value={form.responses_url}
                onChange={(e) => set({ responses_url: e.target.value })}
                placeholder={
                  kindMeta.default_responses_url ??
                  "https://api.example.com/v1/responses"
                }
              />
              <span className="task-form__hint">
                Leave blank to use the provider default.
              </span>
            </div>
          )}

          {kindMeta?.supports_generic_api_url && (
            <div className="task-form__field">
              <label className="task-form__label">API base URL</label>
              <input
                name="generic-api-url"
                className="task-form__input"
                type="text"
                value={form.generic_api_url}
                onChange={(e) => set({ generic_api_url: e.target.value })}
                placeholder={
                  kindMeta.default_generic_api_url ??
                  "https://api.example.com/v1"
                }
              />
              <span className="task-form__hint">
                Leave blank to use the provider default.
              </span>
            </div>
          )}

          {error && <div className="task-form__error">{error}</div>}

          <button
            type="submit"
            className="task-form__submit"
            disabled={isPending}
          >
            {isPending
              ? "Saving…"
              : isEdit
                ? "Save Changes"
                : "Add Provider"}
          </button>
        </form>
      </div>
    </div>
  );
}
