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
  FieldContent,
  FieldDescription,
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
      ? "success"
      : telegram.status.state === "error"
        ? "warning"
        : "secondary";

  return (
    <Card className="settings-item settings-channel-card">
      <CardHeader className="settings-channel-card__header">
        <div className="settings-channel-card__title-row">
          <div className="settings-channel-card__heading">
            <CardTitle className="settings-item__name settings-channel-card__title">
              <SendIcon data-icon="inline-start" />
              Telegram
            </CardTitle>
            <CardDescription className="settings-channel-card__description">
              Text-only polling channel with photo/image document input.
            </CardDescription>
          </div>
          <Badge variant={statusVariant}>{telegram.status.state}</Badge>
        </div>
      </CardHeader>
      <CardContent className="settings-channel-card__content">
        <FieldGroup className="settings-channel-form">
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
          <Field
            orientation="horizontal"
            className="settings-channel-toggle"
          >
            <FieldContent>
              <FieldLabel htmlFor="telegram-channel-enabled">
                Enable Telegram
              </FieldLabel>
              <FieldDescription>
                Accept Telegram messages for this workspace.
              </FieldDescription>
            </FieldContent>
            <Switch
              id="telegram-channel-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </Field>
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
              <FieldLabel>
                Bot token{" "}
                {telegram.has_token_secret ? "(stored; leave blank to keep)" : ""}
              </FieldLabel>
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
          {telegram.last_update_id != null && (
            <p className="text-muted-foreground text-sm">
              Last Telegram update: {telegram.last_update_id}
            </p>
          )}
          <div className="settings-row__actions settings-channel-actions">
            <Button
              type="button"
              variant="outline"
              onClick={onRestart}
              disabled={busy}
            >
              <RefreshCwIcon data-icon="inline-start" />
              Restart
            </Button>
            <Button
              type="button"
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
              Save Telegram
            </Button>
          </div>
        </FieldGroup>
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