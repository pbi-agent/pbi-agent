import { useEffect, useMemo, useState, type FormEvent } from "react";
import { fetchProviderModels } from "../../api";
import type {
  ConfigOptions,
  ModelProfileView,
  ProviderModelListPayload,
  ProviderModelView,
  ProviderView,
} from "../../types";
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

type WebSearchMode = "default" | "true" | "false";

interface FormState {
  name: string;
  id: string;
  provider_id: string;
  model: string;
  sub_agent_model: string;
  reasoning_effort: string;
  max_tokens: string;
  service_tier: string;
  web_search: WebSearchMode;
  max_tool_workers: string;
  max_retries: string;
  compact_threshold: string;
}

function initForm(
  profile?: ModelProfileView,
  providers?: ProviderView[],
): FormState {
  if (profile) {
    return {
      name: profile.name,
      id: profile.id,
      provider_id: profile.provider_id,
      model: profile.model ?? "",
      sub_agent_model: profile.sub_agent_model ?? "",
      reasoning_effort: profile.reasoning_effort ?? "",
      max_tokens: profile.max_tokens?.toString() ?? "",
      service_tier: profile.service_tier ?? "",
      web_search:
        profile.web_search === true
          ? "true"
          : profile.web_search === false
            ? "false"
            : "default",
      max_tool_workers: profile.max_tool_workers?.toString() ?? "",
      max_retries: profile.max_retries?.toString() ?? "",
      compact_threshold: profile.compact_threshold?.toString() ?? "",
    };
  }
  return {
    name: "",
    id: "",
    provider_id: providers?.[0]?.id ?? "",
    model: "",
    sub_agent_model: "",
    reasoning_effort: "",
    max_tokens: "",
    service_tier: "",
    web_search: "default",
    max_tool_workers: "",
    max_retries: "",
    compact_threshold: "",
  };
}

export type ProfilePayload = {
  id?: string | null;
  name: string;
  provider_id: string;
  model?: string | null;
  sub_agent_model?: string | null;
  reasoning_effort?: string | null;
  max_tokens?: number | null;
  service_tier?: string | null;
  web_search?: boolean | null;
  max_tool_workers?: number | null;
  max_retries?: number | null;
  compact_threshold?: number | null;
};

interface Props {
  profile?: ModelProfileView;
  providers: ProviderView[];
  options: ConfigOptions;
  onSave: (payload: ProfilePayload) => Promise<void>;
  onClose: () => void;
}

type ModelFieldMode = "select" | "custom";

function toInt(s: string): number | null {
  const n = parseInt(s, 10);
  return isNaN(n) ? null : n;
}

function formatModelLabel(model: ProviderModelView): string {
  if (model.display_name && model.display_name !== model.id) {
    return `${model.display_name} (${model.id})`;
  }
  return model.id;
}

function matchesKnownModel(
  value: string,
  providerModels: ProviderModelListPayload | null,
): boolean {
  const trimmed = value.trim();
  if (!trimmed || !providerModels) {
    return false;
  }
  return providerModels.models.some(
    (model) => model.id === trimmed || model.aliases.includes(trimmed),
  );
}

function currentModelOption(
  value: string,
  providerModels: ProviderModelListPayload | null,
): { value: string; label: string } | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  if (!providerModels) {
    return { value: trimmed, label: `${trimmed} (custom)` };
  }
  const matched = providerModels.models.find(
    (model) => model.id === trimmed || model.aliases.includes(trimmed),
  );
  if (!matched) {
    return { value: trimmed, label: `${trimmed} (custom)` };
  }
  if (matched.id === trimmed) {
    return null;
  }
  return {
    value: trimmed,
    label: `${trimmed} (alias for ${matched.id})`,
  };
}

function preferredModelMode(
  value: string,
  providerModels: ProviderModelListPayload | null,
): ModelFieldMode {
  if (!value.trim()) {
    return "select";
  }
  return matchesKnownModel(value, providerModels) ? "select" : "custom";
}

export function ModelProfileModal({
  profile,
  providers,
  options,
  onSave,
  onClose,
}: Props) {
  const isEdit = !!profile;
  const [form, setForm] = useState<FormState>(() =>
    initForm(profile, providers),
  );
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providerModels, setProviderModels] =
    useState<ProviderModelListPayload | null>(null);
  const [providerModelsPending, setProviderModelsPending] = useState(false);
  const [providerModelsError, setProviderModelsError] = useState<string | null>(
    null,
  );
  const [modelMode, setModelMode] = useState<ModelFieldMode>("custom");
  const [subAgentModelMode, setSubAgentModelMode] =
    useState<ModelFieldMode>("custom");

  function set(updates: Partial<FormState>) {
    setForm((prev) => ({ ...prev, ...updates }));
  }

  const selectedProvider = providers.find((p) => p.id === form.provider_id);
  const kindMeta = selectedProvider
    ? options.provider_metadata[selectedProvider.kind]
    : null;
  const discoveredModelsAvailable = Boolean(
    providerModels &&
    providerModels.discovery_supported &&
    !providerModels.error &&
    providerModels.models.length > 0,
  );
  const modelOptions = useMemo(() => {
    if (!providerModels) {
      return [];
    }
    const options = providerModels.models.map((model) => ({
      value: model.id,
      label: formatModelLabel(model),
    }));
    const extraOptions = [
      currentModelOption(form.model, providerModels),
    ].filter(
      (option): option is { value: string; label: string } => option !== null,
    );
    return [...extraOptions, ...options];
  }, [form.model, providerModels]);
  const subAgentModelOptions = useMemo(() => {
    if (!providerModels) {
      return [];
    }
    const options = providerModels.models.map((model) => ({
      value: model.id,
      label: formatModelLabel(model),
    }));
    const extraOptions = [
      currentModelOption(form.sub_agent_model, providerModels),
    ].filter(
      (option): option is { value: string; label: string } => option !== null,
    );
    return [...extraOptions, ...options];
  }, [form.sub_agent_model, providerModels]);

  useEffect(() => {
    let cancelled = false;
    if (!form.provider_id) {
      return () => {
        cancelled = true;
      };
    }

    queueMicrotask(() => {
      if (cancelled) {
        return;
      }
      setProviderModelsPending(true);
      setProviderModels(null);
      setProviderModelsError(null);
      void fetchProviderModels(form.provider_id)
        .then((payload) => {
          if (cancelled) {
            return;
          }
          setProviderModels(payload);
          const nextDiscoveredModelsAvailable = Boolean(
            payload.discovery_supported &&
            !payload.error &&
            payload.models.length > 0,
          );
          setModelMode(
            nextDiscoveredModelsAvailable
              ? preferredModelMode(form.model, payload)
              : "custom",
          );
          setSubAgentModelMode(
            nextDiscoveredModelsAvailable
              ? preferredModelMode(form.sub_agent_model, payload)
              : "custom",
          );
        })
        .catch((err) => {
          if (cancelled) {
            return;
          }
          setProviderModels(null);
          setProviderModelsError((err as Error).message);
          setModelMode("custom");
          setSubAgentModelMode("custom");
        })
        .finally(() => {
          if (!cancelled) {
            setProviderModelsPending(false);
          }
        });
    });

    return () => {
      cancelled = true;
    };
  }, [form.model, form.provider_id, form.sub_agent_model]);

  function providerKindLabel(providerKind: string): string {
    return options.provider_metadata[providerKind]?.label ?? providerKind;
  }

  function handleProviderChange(newProviderId: string) {
    const newProvider = providers.find((p) => p.id === newProviderId);
    const newMeta = newProvider
      ? options.provider_metadata[newProvider.kind]
      : null;
    const updates: Partial<FormState> = { provider_id: newProviderId };
    if (!newMeta?.supports_service_tier) {
      updates.service_tier = "";
    }
    set(updates);
  }

  const discoveryMessage =
    providerModelsError ??
    providerModels?.error?.message ??
    (providerModels?.manual_entry_required
      ? "Manual model entry is required for this provider."
      : null);
  const modelFieldHint =
    selectedProvider?.kind === "azure"
      ? "Enter your Azure deployment name. Model discovery is not available for Azure — use a custom value."
      : null;

  function renderModelControl(args: {
    label: string;
    name: string;
    value: string;
    placeholder: string;
    defaultOptionLabel?: string;
    mode: ModelFieldMode;
    setMode: (mode: ModelFieldMode) => void;
    options: Array<{ value: string; label: string }>;
    onChange: (value: string) => void;
  }) {
    if (discoveredModelsAvailable && args.mode === "select") {
      return (
        <>
          <FieldLabel>{args.label}</FieldLabel>
          <NativeSelect
            name={args.name}
            className="task-form__select"
            value={args.value}
            onChange={(e) => args.onChange(e.target.value)}
          >
            <NativeSelectOption value="">
              {args.defaultOptionLabel ?? "Provider default"}
            </NativeSelectOption>
            {args.options.map((option) => (
              <NativeSelectOption key={option.value} value={option.value}>
                {option.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => args.setMode("custom")}
          >
            Custom value
          </Button>
        </>
      );
    }

    return (
      <>
        <FieldLabel>{args.label}</FieldLabel>
        <Input
          name={args.name}
          className="task-form__input"
          value={args.value}
          onChange={(e) => args.onChange(e.target.value)}
          placeholder={args.placeholder}
        />
        {discoveredModelsAvailable && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => args.setMode("select")}
          >
            Choose from provider
          </Button>
        )}
      </>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsPending(true);
    setError(null);

    const payload: ProfilePayload = {
      name: form.name.trim(),
      provider_id: form.provider_id,
      model: form.model.trim() || null,
      sub_agent_model: form.sub_agent_model.trim() || null,
      reasoning_effort: form.reasoning_effort || null,
      max_tokens: toInt(form.max_tokens),
      service_tier: kindMeta?.supports_service_tier
        ? form.service_tier || null
        : null,
      web_search:
        form.web_search === "true"
          ? true
          : form.web_search === "false"
            ? false
            : null,
      max_tool_workers: toInt(form.max_tool_workers),
      max_retries: toInt(form.max_retries),
      compact_threshold: toInt(form.compact_threshold),
    };

    if (!isEdit && form.id.trim()) {
      payload.id = form.id.trim();
    }

    try {
      await onSave(payload);
    } catch (err) {
      setError((err as Error).message);
      setIsPending(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !isPending) onClose();
      }}
    >
      <DialogContent className="task-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Profile" : "Add Profile"}</DialogTitle>
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
                  name="profile-name"
                  className="task-form__input"
                  value={form.name}
                  onChange={(e) => set({ name: e.target.value })}
                  required
                  autoFocus
                  placeholder="e.g. GPT-4o Production"
                />
              </Field>

              {!isEdit && (
                <Field>
                  <FieldLabel>ID (optional)</FieldLabel>
                  <Input
                    name="profile-id"
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
                <FieldLabel>Provider</FieldLabel>
                <NativeSelect
                  name="provider-id"
                  className="task-form__select"
                  value={form.provider_id}
                  onChange={(e) => handleProviderChange(e.target.value)}
                  required
                >
                  {providers.length === 0 && (
                    <NativeSelectOption value="" disabled>
                      No providers configured
                    </NativeSelectOption>
                  )}
                  {providers.map((p) => (
                    <NativeSelectOption key={p.id} value={p.id}>
                      {p.name} ({providerKindLabel(p.kind)})
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>

              <div className="task-form__row">
                <Field>
                  {renderModelControl({
                    label: "Model",
                    name: "model",
                    value: form.model,
                    placeholder: kindMeta?.default_model ?? "provider default",
                    mode: modelMode,
                    setMode: setModelMode,
                    options: modelOptions,
                    onChange: (value) => set({ model: value }),
                  })}
                  {modelFieldHint && (
                    <FieldDescription>{modelFieldHint}</FieldDescription>
                  )}
                </Field>
                <Field>
                  {renderModelControl({
                    label: "Sub-agent model",
                    name: "sub-agent-model",
                    value: form.sub_agent_model,
                    placeholder: form.model.trim() || "same as model",
                    defaultOptionLabel: "Profile main model",
                    mode: subAgentModelMode,
                    setMode: setSubAgentModelMode,
                    options: subAgentModelOptions,
                    onChange: (value) => set({ sub_agent_model: value }),
                  })}
                  <FieldDescription>
                    Leave blank to use this profile&apos;s main model.
                  </FieldDescription>
                </Field>
              </div>

              {(providerModelsPending || discoveryMessage) && (
                <Alert
                  variant={discoveryMessage ? "destructive" : "default"}
                  className={
                    discoveryMessage ? "task-form__error" : "task-form__hint"
                  }
                >
                  <AlertDescription>
                    {providerModelsPending
                      ? "Loading available models…"
                      : discoveryMessage}
                  </AlertDescription>
                </Alert>
              )}

              <div className="task-form__row">
                <Field>
                  <FieldLabel>Reasoning effort</FieldLabel>
                  <NativeSelect
                    name="reasoning-effort"
                    className="task-form__select"
                    value={form.reasoning_effort}
                    onChange={(e) => set({ reasoning_effort: e.target.value })}
                  >
                    <NativeSelectOption value="">
                      Provider default
                    </NativeSelectOption>
                    {options.reasoning_efforts.map((r) => (
                      <NativeSelectOption key={r} value={r}>
                        {r}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field>
                  <FieldLabel>Max tokens</FieldLabel>
                  <Input
                    name="max-tokens"
                    className="task-form__input"
                    type="number"
                    min="0"
                    value={form.max_tokens}
                    onChange={(e) => set({ max_tokens: e.target.value })}
                    placeholder="Provider default"
                  />
                </Field>
              </div>

              <div className="task-form__row">
                {kindMeta?.supports_service_tier ? (
                  <Field>
                    <FieldLabel>Service tier</FieldLabel>
                    <NativeSelect
                      name="service-tier"
                      className="task-form__select"
                      value={form.service_tier}
                      onChange={(e) => set({ service_tier: e.target.value })}
                    >
                      <NativeSelectOption value="">
                        Provider default
                      </NativeSelectOption>
                      {options.openai_service_tiers.map((t) => (
                        <NativeSelectOption key={t} value={t}>
                          {t}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </Field>
                ) : (
                  <Field />
                )}

                <Field>
                  <FieldLabel>Web search</FieldLabel>
                  <NativeSelect
                    name="web-search"
                    className="task-form__select"
                    value={form.web_search}
                    onChange={(e) =>
                      set({ web_search: e.target.value as WebSearchMode })
                    }
                  >
                    <NativeSelectOption value="default">
                      Provider default
                    </NativeSelectOption>
                    <NativeSelectOption value="true">
                      Enabled
                    </NativeSelectOption>
                    <NativeSelectOption value="false">
                      Disabled
                    </NativeSelectOption>
                  </NativeSelect>
                </Field>
              </div>

              <div className="task-form__row">
                <Field>
                  <FieldLabel>Max tool workers</FieldLabel>
                  <Input
                    name="max-tool-workers"
                    className="task-form__input"
                    type="number"
                    min="0"
                    value={form.max_tool_workers}
                    onChange={(e) => set({ max_tool_workers: e.target.value })}
                    placeholder="Default"
                  />
                </Field>
                <Field>
                  <FieldLabel>Max retries</FieldLabel>
                  <Input
                    name="max-retries"
                    className="task-form__input"
                    type="number"
                    min="0"
                    value={form.max_retries}
                    onChange={(e) => set({ max_retries: e.target.value })}
                    placeholder="Default"
                  />
                </Field>
              </div>

              <Field>
                <FieldLabel>Compact threshold</FieldLabel>
                <Input
                  name="compact-threshold"
                  className="task-form__input"
                  type="number"
                  min="0"
                  value={form.compact_threshold}
                  onChange={(e) => set({ compact_threshold: e.target.value })}
                  placeholder="Default"
                />
                <FieldDescription>
                  Token count at which context is compacted.
                </FieldDescription>
              </Field>
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
              disabled={isPending || providers.length === 0}
            >
              {isPending ? "Saving…" : isEdit ? "Save Changes" : "Add Profile"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
