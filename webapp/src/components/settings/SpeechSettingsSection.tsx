import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { startLocalSttDownload } from "../../api";
import {
  LOCAL_STT_STATUS_QUERY_KEY,
  localSttDownloadPercent,
  useLocalSttStatus,
} from "../../hooks/useLocalSttStatus";
import { LOCAL_STT_PROVIDER_ID } from "../../types";
import type { ConfigOptions, LocalSttStatus, ProviderView } from "../../types";
import { EMPTY_SELECT_VALUE, fromSelectValue, toSelectValue } from "../../lib/selectValues";
import { EmptyState } from "../shared/EmptyState";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { SettingsPanel, SettingsSection } from "./settings-layout";

function providerKindLabel(providerKind: string, options: ConfigOptions): string {
  return options.provider_metadata[providerKind]?.label ?? providerKind;
}

function providerSupportsStt(
  provider: ProviderView,
): boolean {
  return provider.supports_stt;
}

function providerHasCredentials(provider: ProviderView): boolean {
  if (provider.auth_mode === "api_key") {
    return provider.has_secret;
  }
  return provider.auth_status.session_status === "connected";
}

function providerOptionLabel(
  provider: ProviderView,
  options: ConfigOptions,
): string {
  return `${provider.name} (${providerKindLabel(provider.kind, options)})`;
}

const LOCAL_STT_LABEL = "On this device (Parakeet v3)";

function formatMegabytes(bytes: number): string {
  return `${Math.round(bytes / 1_000_000)} MB`;
}

function LocalSttStatusNotice({
  status,
  onDownload,
}: {
  status: LocalSttStatus | undefined;
  onDownload: () => void;
}) {
  if (!status) return null;
  if (status.state === "ready") {
    return (
      <Alert>
        <AlertDescription>
          The speech model is installed. Audio is transcribed on this machine
          and never sent to a provider.
        </AlertDescription>
      </Alert>
    );
  }
  if (status.state === "downloading") {
    const percent = localSttDownloadPercent(status);
    return (
      <Alert>
        <AlertDescription>
          <div className="flex flex-col gap-2">
            <span>
              Downloading the speech model: {percent}% of{" "}
              {formatMegabytes(status.total_bytes)}. Dictation becomes
              available when it finishes.
            </span>
            <Progress value={percent} aria-label="Speech model download" />
          </div>
        </AlertDescription>
      </Alert>
    );
  }
  if (status.state === "unsupported") {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          On-device speech-to-text is not available on this platform. Choose
          another provider.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert variant={status.state === "failed" ? "destructive" : "default"}>
      <AlertDescription>
        <div className="flex flex-wrap items-center gap-3">
          <span className="min-w-0 flex-1">
            {status.state === "failed"
              ? `The speech model download failed: ${status.error ?? "unknown error"}.`
              : `The speech model (${formatMegabytes(status.total_bytes)}) is not installed yet.`}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={onDownload}>
            {status.state === "failed" ? "Retry download" : "Download"}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}

export function SpeechSettingsSection({
  providers,
  options,
  sttProviderId,
  onSave,
}: {
  providers: ProviderView[];
  options: ConfigOptions;
  sttProviderId: string | null;
  onSave: (providerId: string | null) => Promise<void>;
}) {
  const [selectedProviderId, setSelectedProviderId] = useState(
    sttProviderId ?? "",
  );
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedProviderId(sttProviderId ?? "");
    setError(null);
  }, [sttProviderId]);

  const sttProviders = useMemo(
    () => providers.filter(providerSupportsStt),
    [providers],
  );
  const credentialedProviders = useMemo(
    () => sttProviders.filter(providerHasCredentials),
    [sttProviders],
  );
  const missingCredentialProviders = useMemo(
    () => sttProviders.filter((provider) => !providerHasCredentials(provider)),
    [sttProviders],
  );

  const queryClient = useQueryClient();
  const localStatus = useLocalSttStatus();
  const localSelected = sttProviderId === LOCAL_STT_PROVIDER_ID;
  const localSelectable = Boolean(
    localStatus && localStatus.state !== "unsupported",
  );

  const activeProvider = sttProviderId
    ? providers.find((provider) => provider.id === sttProviderId)
    : null;
  const activeProviderUnavailable = Boolean(
    sttProviderId &&
      !localSelected &&
      !credentialedProviders.some((provider) => provider.id === sttProviderId),
  );
  const showSelector =
    credentialedProviders.length > 0 || localSelectable || Boolean(sttProviderId);

  async function refreshLocalStatus() {
    await queryClient.invalidateQueries({ queryKey: LOCAL_STT_STATUS_QUERY_KEY });
  }

  async function handleLocalDownload() {
    setError(null);
    try {
      queryClient.setQueryData(
        LOCAL_STT_STATUS_QUERY_KEY,
        await startLocalSttDownload(),
      );
      await refreshLocalStatus();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleProviderChange(providerId: string) {
    setSelectedProviderId(providerId);
    setIsSaving(true);
    setError(null);
    try {
      await onSave(providerId || null);
      if (providerId === LOCAL_STT_PROVIDER_ID) {
        // Selecting the local engine starts its download on the server.
        await refreshLocalStatus();
      }
    } catch (err) {
      setError((err as Error).message);
      setSelectedProviderId(sttProviderId ?? "");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <SettingsSection>
      <SettingsPanel
        title="Speech-to-text"
        description="Choose a saved provider or the on-device model for dictation and transcription."
        actions={
          <Badge variant="info" size="meta">
            STT
          </Badge>
        }
      >
          {showSelector ? (
            <>
              <div
                data-settings-active-control=""
                className="flex flex-wrap items-center gap-3"
              >
                <span className="text-sm font-medium">
                  Active default
                </span>
                <Select
                  value={toSelectValue(selectedProviderId)}
                  disabled={isSaving}
                  onValueChange={(value) =>
                    void handleProviderChange(fromSelectValue(value))
                  }
                >
                  <SelectTrigger
                    id="stt-provider"
                    aria-label="Speech-to-text provider"
                    data-settings-active-select=""
                    className="min-w-0 flex-1"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={EMPTY_SELECT_VALUE}>
                      No speech provider
                    </SelectItem>
                  {(localSelectable || localSelected) && (
                    <SelectItem
                      value={LOCAL_STT_PROVIDER_ID}
                      disabled={!localSelectable}
                    >
                      {LOCAL_STT_LABEL}
                    </SelectItem>
                  )}
                  {activeProviderUnavailable && sttProviderId && (
                    <SelectItem value={sttProviderId} disabled>
                      {activeProvider
                        ? `${providerOptionLabel(activeProvider, options)} — credentials needed`
                        : `${sttProviderId} — unavailable`}
                    </SelectItem>
                  )}
                  {credentialedProviders.map((provider) => (
                    <SelectItem key={provider.id} value={provider.id}>
                      {providerOptionLabel(provider, options)}
                    </SelectItem>
                  ))}
                  </SelectContent>
                </Select>
              </div>

              {localSelected && (
                <LocalSttStatusNotice
                  status={localStatus}
                  onDownload={() => void handleLocalDownload()}
                />
              )}

              {activeProviderUnavailable && (
                <Alert>
                  <AlertDescription>
                    The selected speech provider is not ready. Add credentials
                    or clear the selection.
                  </AlertDescription>
                </Alert>
              )}
            </>
          ) : (
            <EmptyState
              title="No speech-to-text provider ready"
              description="Add OpenAI, xAI, Google, Deepgram, or ElevenLabs provider credentials first."
            />
          )}

          {missingCredentialProviders.length > 0 && (
            <Alert>
              <AlertDescription>
                These speech-capable providers need credentials before
                selection:{" "}
                {missingCredentialProviders
                  .map((provider) => providerOptionLabel(provider, options))
                  .join(", ")}
                .
              </AlertDescription>
            </Alert>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
      </SettingsPanel>
    </SettingsSection>
  );
}