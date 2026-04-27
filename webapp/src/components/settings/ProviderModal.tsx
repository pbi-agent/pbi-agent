import { useState, type FormEvent } from "react";
import type { ConfigOptions, ProviderView } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "../ui/field";
import { Input } from "../ui/input";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";

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
    api_key_env: defaultApiKeyEnv(defaultKind),
    responses_url: "",
    generic_api_url: "",
  };
}

function defaultApiKeyEnv(providerKind: string): string {
  if (providerKind === "azure") return "AZURE_API_KEY";
  if (providerKind === "openai") return "OPENAI_API_KEY";
  if (providerKind === "xai") return "XAI_API_KEY";
  if (providerKind === "google") return "GEMINI_API_KEY";
  if (providerKind === "anthropic") return "ANTHROPIC_API_KEY";
  if (providerKind === "generic") return "GENERIC_API_KEY";
  return "";
}

function responsesUrlLabel(providerKind: string): string {
  return providerKind === "azure"
    ? "Azure endpoint URL"
    : "Responses URL override";
}

function responsesUrlDescription(providerKind: string): string {
  return providerKind === "azure"
    ? "Required. Routes by URL: /openai/v1/responses, /openai/v1, or /anthropic/v1/messages."
    : "Leave blank to use the provider default.";
}

function responsesUrlPlaceholder(
  providerKind: string,
  defaultResponsesUrl: string | null | undefined,
): string {
  if (providerKind === "azure") {
    return "https://<resource>.openai.azure.com/openai/v1/responses";
  }
  return defaultResponsesUrl ?? "https://api.example.com/v1/responses";
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
  const [form, setForm] = useState<FormState>(() =>
    initForm(provider, options),
  );
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(updates: Partial<FormState>) {
    setForm((prev) => {
      const next = { ...prev, ...updates };
      if (updates.kind && updates.kind !== prev.kind) {
        const nextMeta = options.provider_metadata[updates.kind];
        next.auth_mode = nextMeta?.default_auth_mode ?? "api_key";
        if (prev.secretMode === "env_var") {
          next.api_key_env = defaultApiKeyEnv(updates.kind);
        }
        next.responses_url = "";
        next.generic_api_url = "";
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
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !isPending) onClose();
      }}
    >
      <DialogContent className="task-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Provider" : "Add Provider"}</DialogTitle>
        </DialogHeader>

        <form
          className="task-form"
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
        >
          <div className="task-form__body">
            <FieldGroup>
              <Field>
                <FieldLabel>Name</FieldLabel>
                <Input
                  name="provider-name"
                  className="task-form__input"
                  value={form.name}
                  onChange={(e) => set({ name: e.target.value })}
                  required
                  autoFocus
                  placeholder="e.g. My OpenAI"
                />
              </Field>

              {!isEdit && (
                <Field>
                  <FieldLabel>ID (optional)</FieldLabel>
                  <Input
                    name="provider-id"
                    className="task-form__input"
                    value={form.id}
                    onChange={(e) => set({ id: e.target.value })}
                    placeholder="Auto-generated from name"
                  />
                  <FieldDescription>
                    Leave blank to auto-generate from the name.
                  </FieldDescription>
                </Field>
              )}

              <Field>
                <FieldLabel>Kind</FieldLabel>
                <NativeSelect
                  name="provider-kind"
                  className="task-form__select"
                  value={form.kind}
                  onChange={(e) => set({ kind: e.target.value })}
                >
                  {options.provider_kinds.map((k) => (
                    <NativeSelectOption key={k} value={k}>
                      {options.provider_metadata[k]?.label ?? k}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                {kindMeta?.description && (
                  <FieldDescription>{kindMeta.description}</FieldDescription>
                )}
              </Field>

              {showAuthModePicker && (
                <Field>
                  <FieldLabel>Authentication</FieldLabel>
                  <ToggleGroup
                    type="single"
                    value={form.auth_mode}
                    onValueChange={(value) => {
                      if (value) set({ auth_mode: value });
                    }}
                    className="secret-mode-tabs provider-auth-mode-tabs"
                    spacing={1}
                    variant="outline"
                  >
                    {authModes.map((authMode) => (
                      <ToggleGroupItem key={authMode} value={authMode}>
                        {authModeMetadata[authMode]?.label ?? authMode}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                </Field>
              )}

              {isApiKeyAuth ? (
                <Field>
                  <FieldLabel>Credential source</FieldLabel>
                  <ToggleGroup
                    type="single"
                    value={form.secretMode}
                    onValueChange={(value) => {
                      if (value) set({ secretMode: value as SecretMode });
                    }}
                    className="secret-mode-tabs"
                    spacing={1}
                    variant="outline"
                  >
                    {secretModes.map(({ value, label }) => (
                      <ToggleGroupItem key={value} value={value}>
                        {label}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                </Field>
              ) : (
                <Alert className="settings-inline-note provider-auth-inline-note">
                  <AlertDescription>
                    Save this provider to continue directly into sign-in for
                    your {accountAuthLabel ?? "account"}.
                  </AlertDescription>
                </Alert>
              )}

              {isApiKeyAuth && form.secretMode === "env_var" && (
                <Field>
                  <FieldLabel>Environment variable name</FieldLabel>
                  <Input
                    name="api-key-env"
                    className="task-form__input"
                    value={form.api_key_env}
                    onChange={(e) => set({ api_key_env: e.target.value })}
                    placeholder="e.g. OPENAI_API_KEY"
                  />
                </Field>
              )}

              {isApiKeyAuth && form.secretMode === "plaintext" && (
                <Field>
                  <FieldLabel>
                    API key
                    {isEdit ? " (leave blank to keep current)" : ""}
                  </FieldLabel>
                  <Input
                    name="api-key"
                    className="task-form__input"
                    type="password"
                    value={form.api_key}
                    onChange={(e) => set({ api_key: e.target.value })}
                    placeholder={isEdit ? "Enter new key to update" : "sk-…"}
                    autoComplete="new-password"
                  />
                </Field>
              )}

              {kindMeta?.supports_responses_url && (
                <Field>
                  <FieldLabel>{responsesUrlLabel(form.kind)}</FieldLabel>
                  <Input
                    name="responses-url"
                    className="task-form__input"
                    type="text"
                    value={form.responses_url}
                    onChange={(e) => set({ responses_url: e.target.value })}
                    placeholder={responsesUrlPlaceholder(
                      form.kind,
                      kindMeta.default_responses_url,
                    )}
                    required={form.kind === "azure"}
                  />
                  <FieldDescription>
                    {responsesUrlDescription(form.kind)}
                  </FieldDescription>
                </Field>
              )}

              {kindMeta?.supports_generic_api_url && (
                <Field>
                  <FieldLabel>API base URL</FieldLabel>
                  <Input
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
                  <FieldDescription>
                    Leave blank to use the provider default.
                  </FieldDescription>
                </Field>
              )}
            </FieldGroup>

            {error && (
              <Alert variant="destructive" className="task-form__error">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter className="task-form__footer">
            <Button
              type="button"
              variant="outline"
              className="task-form__action-button"
              onClick={onClose}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="default"
              className="task-form__action-button"
              disabled={isPending}
            >
              {isPending ? "Saving…" : isEdit ? "Save Changes" : "Add Provider"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
