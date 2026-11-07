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
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { SettingsPanel, SettingsSection } from "./settings-layout";
import { Field, FieldGroup, FieldLabel } from "../ui/field";
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
    <SettingsSection>
      <SettingsPanel
        title="Channels"
        description="Connect workspace-scoped messaging channels to this project."
      >
        {channelsQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoadingSpinner size="sm" />
            <span>Loading channels…</span>
          </div>
        ) : channelsQuery.isError || !channelsQuery.data ? (
          <Alert variant="destructive">
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
      </SettingsPanel>
    </SettingsSection>
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
    <Card size="sm">
      <CardHeader>
        <CardTitle>
          <div className="flex items-center gap-2">
            <SendIcon
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <span>Telegram</span>
            <Badge variant={statusVariant} size="meta">
              {statusLabel}
            </Badge>
          </div>
        </CardTitle>
        <CardAction>
          <div className="flex items-center gap-2">
            <FieldLabel htmlFor="telegram-channel-enabled">Enabled</FieldLabel>
            <Switch
              id="telegram-channel-enabled"
              size="sm"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {telegram.status.error && (
            <Alert variant="destructive">
              <AlertDescription>{telegram.status.error}</AlertDescription>
            </Alert>
          )}

          <Separator />

          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel>Token source</FieldLabel>
                <Select
                  value={tokenSource}
                  onValueChange={(value) =>
                    setTokenSource(value === "secret" ? "secret" : "env")
                  }
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="env">Environment variable</SelectItem>
                    <SelectItem value="secret">Stored token</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              {tokenSource === "env" ? (
                <Field>
                  <FieldLabel>Environment variable</FieldLabel>
                  <Input
                    value={tokenEnvVar}
                    onChange={(event) => setTokenEnvVar(event.target.value)}
                    placeholder="PBI_AGENT_TELEGRAM_BOT_TOKEN"
                  />
                </Field>
              ) : (
                <Field>
                  <FieldLabel>Bot token {tokenHint}</FieldLabel>
                  <Input
                    value={tokenSecret}
                    onChange={(event) => setTokenSecret(event.target.value)}
                    placeholder={
                      telegram.has_token_secret
                        ? "Stored token hidden"
                        : "123:abc"
                    }
                    type="password"
                  />
                </Field>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel>Allowed user IDs</FieldLabel>
                <Textarea
                  value={allowedUsers}
                  onChange={(event) => setAllowedUsers(event.target.value)}
                  placeholder="One Telegram user ID per line"
                />
              </Field>
              <Field>
                <FieldLabel>Allowed chat/channel IDs</FieldLabel>
                <Textarea
                  value={allowedChats}
                  onChange={(event) => setAllowedChats(event.target.value)}
                  placeholder="One group, supergroup, or channel ID per line"
                />
              </Field>
            </div>
          </FieldGroup>

          <Separator />

          <div className="flex flex-wrap items-center justify-end gap-2">
            {telegram.last_update_id != null && (
              <span className="mr-auto text-xs text-muted-foreground">
                Last update #{telegram.last_update_id}
              </span>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onRestart}
              disabled={busy}
            >
              <RefreshCwIcon data-icon="inline-start" />
              Restart
            </Button>
            <Button
              type="button"
              size="sm"
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
