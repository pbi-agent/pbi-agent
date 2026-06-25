import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCwIcon, SendIcon } from "lucide-react";
import {
  fetchBootstrap,
  fetchChannels,
  restartTelegramChannel,
  updateTelegramChannel,
} from "../../api";
import type {
  ChannelListPayload,
  TelegramChannelUpdatePayload,
} from "../../types";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Separator } from "../ui/separator";
import { Switch } from "../ui/switch";
import { Textarea } from "../ui/textarea";

export function ChannelsSettingsSection() {
  const queryClient = useQueryClient();
  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchBootstrap,
    staleTime: 30_000,
  });
  const channelsQueryKey = [
    "channels",
    bootstrapQuery.data?.workspace_key ?? "pending",
  ];
  const channelsQuery = useQuery({
    queryKey: channelsQueryKey,
    queryFn: fetchChannels,
    enabled: Boolean(bootstrapQuery.data?.workspace_key),
    staleTime: 10_000,
  });
  const updateMutation = useMutation({
    mutationFn: updateTelegramChannel,
    onSuccess: (data) => {
      queryClient.setQueryData<ChannelListPayload>(channelsQueryKey, data);
    },
  });
  const restartMutation = useMutation({
    mutationFn: restartTelegramChannel,
    onSuccess: (data) => {
      queryClient.setQueryData<ChannelListPayload>(channelsQueryKey, data);
    },
  });

  return (
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div className="settings-panel__heading">
            <CardTitle className="settings-panel__title">Channels</CardTitle>
            <CardDescription className="settings-panel__subtitle">
              Connect workspace-scoped messaging channels to this project.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="settings-panel__body">
          {channelsQuery.isLoading ? (
            <div className="settings-hooks__loading">
              <LoadingSpinner size="sm" />
              <span>Loading channels…</span>
            </div>
          ) : channelsQuery.isError || !channelsQuery.data ? (
            <Alert variant="destructive" className="settings-error-banner">
              <AlertDescription>
                Failed to load channels:{" "}
                {(channelsQuery.error as Error)?.message ?? "Unknown error"}
              </AlertDescription>
            </Alert>
          ) : (
            <TelegramChannelCard
              key={JSON.stringify(channelsQuery.data.telegram)}
              data={channelsQuery.data}
              busy={updateMutation.isPending || restartMutation.isPending}
              error={
                updateMutation.error?.message ??
                restartMutation.error?.message ??
                null
              }
              onSave={(payload) => updateMutation.mutate(payload)}
              onRestart={() => restartMutation.mutate()}
            />
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function TelegramChannelCard({
  data,
  busy,
  error,
  onSave,
  onRestart,
}: {
  data: ChannelListPayload;
  busy: boolean;
  error: string | null;
  onSave: (payload: TelegramChannelUpdatePayload) => void;
  onRestart: () => void;
}) {
  const telegram = data.telegram;
  const [enabled, setEnabled] = useState(telegram.enabled);
  const [tokenSource, setTokenSource] = useState<"env" | "secret">(
    telegram.token_source,
  );
  const [tokenEnvVar, setTokenEnvVar] = useState(telegram.token_env_var);
  const [tokenSecret, setTokenSecret] = useState("");
  const [allowedUsers, setAllowedUsers] = useState(
    telegram.allowed_users.join("\n"),
  );
  const [allowedChats, setAllowedChats] = useState(
    telegram.allowed_chats.join("\n"),
  );

  const statusVariant =
    telegram.status.state === "running"
      ? "running"
      : telegram.status.state === "error"
        ? "failed"
        : "secondary";
  const statusLabel =
    telegram.status.state.charAt(0).toUpperCase() +
    telegram.status.state.slice(1);
  const tokenHint = telegram.has_token_secret
    ? "(stored; leave blank to keep)"
    : "";

  return (
    <Card className="settings-item settings-channel-card">
      <CardContent className="settings-channel-card__content">
        <div className="settings-channel-card__header">
          <div className="settings-channel-card__heading">
            <SendIcon className="size-4 text-muted-foreground" aria-hidden="true" />
            <span className="settings-channel-card__title">Telegram</span>
            <Badge variant={statusVariant} size="meta">
              {statusLabel}
            </Badge>
          </div>
          <div className="settings-channel-card__toggle">
            <FieldLabel
              htmlFor="telegram-channel-enabled"
              className="settings-channel-card__toggle-label"
            >
              Enabled
            </FieldLabel>
            <Switch
              id="telegram-channel-enabled"
              size="sm"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </div>
        </div>

        {error && (
          <Alert variant="destructive" className="settings-error-banner">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {telegram.status.error && (
          <Alert variant="destructive" className="settings-error-banner">
            <AlertDescription>{telegram.status.error}</AlertDescription>
          </Alert>
        )}

        <Separator />

        <FieldGroup className="settings-channel-form">
          <div className="settings-channel-grid">
            <Field className="settings-channel-field">
              <FieldLabel>Token source</FieldLabel>
              <Select
                value={tokenSource}
                onValueChange={(value) =>
                  setTokenSource(value === "secret" ? "secret" : "env")
                }
              >
                <SelectTrigger className="settings-channel-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="env">Environment variable</SelectItem>
                  <SelectItem value="secret">Stored token</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            {tokenSource === "env" ? (
              <Field className="settings-channel-field">
                <FieldLabel>Environment variable</FieldLabel>
                <Input
                  className="settings-channel-control"
                  value={tokenEnvVar}
                  onChange={(event) => setTokenEnvVar(event.target.value)}
                  placeholder="PBI_AGENT_TELEGRAM_BOT_TOKEN"
                />
              </Field>
            ) : (
              <Field className="settings-channel-field">
                <FieldLabel>Bot token {tokenHint}</FieldLabel>
                <Input
                  className="settings-channel-control"
                  value={tokenSecret}
                  onChange={(event) => setTokenSecret(event.target.value)}
                  placeholder={
                    telegram.has_token_secret ? "Stored token hidden" : "123:abc"
                  }
                  type="password"
                />
              </Field>
            )}
          </div>

          <div className="settings-channel-grid">
            <Field className="settings-channel-field">
              <FieldLabel>Allowed user IDs</FieldLabel>
              <Textarea
                className="settings-channel-textarea"
                value={allowedUsers}
                onChange={(event) => setAllowedUsers(event.target.value)}
                placeholder="One Telegram user ID per line"
              />
            </Field>
            <Field className="settings-channel-field">
              <FieldLabel>Allowed chat/channel IDs</FieldLabel>
              <Textarea
                className="settings-channel-textarea"
                value={allowedChats}
                onChange={(event) => setAllowedChats(event.target.value)}
                placeholder="One group, supergroup, or channel ID per line"
              />
            </Field>
          </div>
        </FieldGroup>

        <Separator />

        <div className="settings-channel-actions">
          {telegram.last_update_id != null && (
            <span className="settings-channel-meta">
              Last update #{telegram.last_update_id}
            </span>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="settings-channel-button"
            onClick={onRestart}
            disabled={busy}
          >
            <RefreshCwIcon data-icon="inline-start" />
            Restart
          </Button>
          <Button
            type="button"
            size="sm"
            className="settings-channel-button"
            onClick={() =>
              onSave({
                enabled,
                token_source: tokenSource,
                token_env_var: tokenEnvVar,
                token_secret: tokenSecret || null,
                allowed_users: lines(allowedUsers),
                allowed_chats: lines(allowedChats),
              })
            }
            disabled={busy}
          >
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function lines(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}
