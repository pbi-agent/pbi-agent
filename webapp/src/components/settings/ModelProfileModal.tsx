import { useEffect, useMemo, useState, type FormEvent } from "react";
import { fetchProviderModels } from "../../api";
import type {
  ConfigOptions,
  ModelProfileView,
  ProviderModelListPayload,
  ProviderModelView,
  ProviderView,
} from "../../types";
import { EMPTY_SELECT_VALUE, fromSelectValue, toSelectValue } from "../../lib/selectValues";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { FormDialog } from "../ui/form-dialog";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "../ui/field";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Switch } from "../ui/switch";

const TOOL_VISIBILITY_OPTIONS = [
  {
    id: "read",
    label: "Read",
    description: "Read files and search workspace content.",
  },
  {
    id: "write",
    label: "Write",
    description: "Apply patches, replace files, and write files.",
  },
  {
    id: "web",
    label: "Web",
    description: "Fetch URLs and Firecrawl-backed web_search.",
  },
  {
    id: "sub-agent",
    label: "Sub-agent",
    description: "Delegate work to child agents.",
  },
  {
    id: "shell",
    label: "Shell",
    description: "Run workspace shell commands.",
  },
] as const;

type ToolCategory = (typeof TOOL_VISIBILITY_OPTIONS)[number]["id"];
const ALL_TOOL_CATEGORIES = TOOL_VISIBILITY_OPTIONS.map((item) => item.id);

interface FormState {
  name: string;
  id: string;
  provider_id: string;
  model: string;
  sub_agent_model: string;
  reasoning_effort: string;
  max_tokens: string;
  service_tier: string;
  allowed_tools: ToolCategory[];
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
      allowed_tools: normalizeToolCategories(profile.allowed_tools),
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
    allowed_tools: [...ALL_TOOL_CATEGORIES],
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
  allowed_tools?: ToolCategory[] | null;
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

function normalizeToolCategories(
  allowedTools: string[] | null | undefined,
): ToolCategory[] {
  if (allowedTools === null || allowedTools === undefined) {
    return [...ALL_TOOL_CATEGORIES];
  }
  const allowed = new Set(allowedTools);
  return TOOL_VISIBILITY_OPTIONS.filter((item) => allowed.has(item.id)).map(
    (item) => item.id,
  );
}

function serializeToolCategories(
  allowedTools: ToolCategory[],
): ToolCategory[] | null {
  const selected = TOOL_VISIBILITY_OPTIONS.filter((item) =>
    allowedTools.includes(item.id),
  ).map((item) => item.id);
  return selected.length === ALL_TOOL_CATEGORIES.length ? null : selected;
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

  function toggleToolCategory(category: ToolCategory, checked: boolean) {
    setForm((prev) => {
      const selected = new Set(prev.allowed_tools);
      if (checked) {
        selected.add(category);
      } else {
        selected.delete(category);
      }
      return {
        ...prev,
        allowed_tools: TOOL_VISIBILITY_OPTIONS.filter((item) =>
          selected.has(item.id),
        ).map((item) => item.id),
      };
    });
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
          <Select
            value={toSelectValue(args.value)}
            onValueChange={(value) => args.onChange(fromSelectValue(value))}
          >
            <SelectTrigger
              aria-label={args.label}
              className="task-form__select"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EMPTY_SELECT_VALUE}>
                {args.defaultOptionLabel ?? "Provider default"}
              </SelectItem>
            {args.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
            </SelectContent>
          </Select>
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
      allowed_tools: serializeToolCategories(form.allowed_tools),
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
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open && !isPending) onClose();
      }}
      title={isEdit ? "Edit Profile" : "Add Profile"}
      onSubmit={(event) => {
        void handleSubmit(event);
      }}
      isPending={isPending}
      error={error}
      primaryAction={{
        label: isEdit ? "Save Changes" : "Add Profile",
        pendingLabel: "Saving…",
        disabled: providers.length === 0,
      }}
      onCancel={onClose}
    >
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
                <Select
                  value={toSelectValue(form.provider_id)}
                  onValueChange={(value) =>
                    handleProviderChange(fromSelectValue(value))
                  }
                >
                  <SelectTrigger
                    aria-label="Provider"
                    className="task-form__select"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                  {providers.length === 0 && (
                    <SelectItem value={EMPTY_SELECT_VALUE} disabled>
                      No model-capable providers configured
                    </SelectItem>
                  )}
                  {providers.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name} ({providerKindLabel(p.kind)})
                    </SelectItem>
                  ))}
                  </SelectContent>
                </Select>
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
                  <Select
                    value={toSelectValue(form.reasoning_effort)}
                    onValueChange={(value) =>
                      set({ reasoning_effort: fromSelectValue(value) })
                    }
                  >
                    <SelectTrigger
                      aria-label="Reasoning effort"
                      className="task-form__select"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={EMPTY_SELECT_VALUE}>
                        Provider default
                      </SelectItem>
                    {options.reasoning_efforts.map((r) => (
                      <SelectItem key={r} value={r}>
                        {r}
                      </SelectItem>
                    ))}
                    </SelectContent>
                  </Select>
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

              {kindMeta?.supports_service_tier && (
                <Field>
                  <FieldLabel>Service tier</FieldLabel>
                  <Select
                    value={toSelectValue(form.service_tier)}
                    onValueChange={(value) =>
                      set({ service_tier: fromSelectValue(value) })
                    }
                  >
                    <SelectTrigger
                      aria-label="Service tier"
                      className="task-form__select"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={EMPTY_SELECT_VALUE}>
                        Provider default
                      </SelectItem>
                    {options.openai_service_tiers.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                    </SelectContent>
                  </Select>
                </Field>
              )}

              <FieldSet>
                <FieldLegend>Tool visibility</FieldLegend>
                <FieldDescription>
                  Select the built-in tool groups this profile can expose.
                  Clear every group to hide all configurable built-in tools.
                </FieldDescription>
                <FieldGroup>
                  {TOOL_VISIBILITY_OPTIONS.map((tool) => (
                    <Field key={tool.id} orientation="horizontal">
                      <FieldContent>
                        <FieldLabel htmlFor={`profile-tool-${tool.id}`}>
                          {tool.label}
                        </FieldLabel>
                        <FieldDescription>{tool.description}</FieldDescription>
                      </FieldContent>
                      <Switch
                        id={`profile-tool-${tool.id}`}
                        checked={form.allowed_tools.includes(tool.id)}
                        onCheckedChange={(checked) =>
                          toggleToolCategory(tool.id, checked)
                        }
                      />
                    </Field>
                  ))}
                </FieldGroup>
              </FieldSet>

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
    </FormDialog>
  );
}
