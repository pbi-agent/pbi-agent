import { useEffect, useMemo, useState } from "react";
import type { ConfigOptions, ProviderView } from "../../types";
import { EMPTY_SELECT_VALUE, fromSelectValue, toSelectValue } from "../../lib/selectValues";
import { EmptyState } from "../shared/EmptyState";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

function providerKindLabel(providerKind: string, options: ConfigOptions): string {
  return options.provider_metadata[providerKind]?.label ?? providerKind;
}

function providerSupportsStt(
  provider: ProviderView,
  options: ConfigOptions,
): boolean {
  return options.provider_metadata[provider.kind]?.supports_stt === true;
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
    () => providers.filter((provider) => providerSupportsStt(provider, options)),
    [providers, options],
  );
  const credentialedProviders = useMemo(
    () => sttProviders.filter(providerHasCredentials),
    [sttProviders],
  );
  const missingCredentialProviders = useMemo(
    () => sttProviders.filter((provider) => !providerHasCredentials(provider)),
    [sttProviders],
  );

  const activeProvider = sttProviderId
    ? providers.find((provider) => provider.id === sttProviderId)
    : null;
  const activeProviderUnavailable = Boolean(
    sttProviderId &&
      !credentialedProviders.some((provider) => provider.id === sttProviderId),
  );
  const showSelector = credentialedProviders.length > 0 || Boolean(sttProviderId);

  async function handleProviderChange(providerId: string) {
    setSelectedProviderId(providerId);
    setIsSaving(true);
    setError(null);
    try {
      await onSave(providerId || null);
    } catch (err) {
      setError((err as Error).message);
      setSelectedProviderId(sttProviderId ?? "");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">
              Speech-to-text
            </CardTitle>
            <div className="settings-panel__subtitle">
              Choose the saved provider used for future dictation and
              transcription.
            </div>
          </div>
          <Badge variant="info" size="meta">
            STT
          </Badge>
        </CardHeader>
        <CardContent className="settings-panel__body">
          {showSelector ? (
            <>
              <div className="active-profile-control">
                <span className="active-profile-control__label">
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
                    className="active-profile-control__select"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={EMPTY_SELECT_VALUE}>
                      No speech provider
                    </SelectItem>
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

              {activeProviderUnavailable && (
                <Alert className="settings-inline-note">
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
              description="Add OpenAI, Deepgram, or ElevenLabs provider credentials first."
            />
          )}

          {missingCredentialProviders.length > 0 && (
            <Alert className="settings-inline-note">
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
            <Alert variant="destructive" className="settings-error-banner">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </section>
  );
}