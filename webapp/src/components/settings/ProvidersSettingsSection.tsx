import {
  CheckCircle2Icon,
  EditIcon,
  GaugeIcon,
  PlugZapIcon,
  PlusIcon,
  Trash2Icon,
  UnplugIcon,
} from "lucide-react";
import type { ConfigOptions, ProviderAuthStatus, ProviderView } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";

function providerKindLabel(providerKind: string, options: ConfigOptions): string {
  return options.provider_metadata[providerKind]?.label ?? providerKind;
}

function authStatusLabel(status: ProviderAuthStatus): string {
  if (status.auth_mode === "api_key") {
    return "API key";
  }
  switch (status.session_status) {
    case "connected":
      return "connected";
    case "expired":
      return "expired";
    default:
      return "not connected";
  }
}

function supportsUsageLimits(provider: ProviderView): boolean {
  return (
    provider.auth_mode !== "api_key" &&
    provider.auth_status.session_status === "connected"
  );
}

function ProviderCard({
  provider,
  options,
  isBusy,
  onEdit,
  onDelete,
  onConnect,
  onRefresh,
  onDisconnect,
  onShowUsage,
}: {
  provider: ProviderView;
  options: ConfigOptions;
  isBusy: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onConnect: () => void;
  onRefresh: () => void;
  onDisconnect: () => void;
  onShowUsage: () => void;
}) {
  const authStatus = provider.auth_status;
  const showAuthActions = provider.auth_mode !== "api_key";
  const showUsageAction = supportsUsageLimits(provider);

  // Build compact subtitle
  const subtitleParts: string[] = [providerKindLabel(provider.kind, options)];
  if (authStatus.email) {
    subtitleParts.push(authStatus.email);
  } else {
    subtitleParts.push(authStatusLabel(authStatus));
  }

  return (
    <Card className="settings-item settings-item--provider provider-card">
      <div className="provider-card__info">
        <span className="settings-item__name">{provider.name}</span>
        {subtitleParts.length > 0 && (
          <div className="provider-card__subtitle">
            {subtitleParts.join(" · ")}
          </div>
        )}
      </div>
      <div className="provider-card__actions">
        {showAuthActions && (
          <>
            <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onConnect} disabled={isBusy}>
              <PlugZapIcon data-icon="inline-start" />
              {authStatus.has_session ? "Reconnect" : "Connect"}
            </Button>
            <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onRefresh} disabled={isBusy || !authStatus.can_refresh}>
              <CheckCircle2Icon data-icon="inline-start" />
              Refresh
            </Button>
            {showUsageAction && (
              <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onShowUsage}>
                <GaugeIcon data-icon="inline-start" />
                Usage
              </Button>
            )}
            <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onDisconnect} disabled={isBusy || !authStatus.has_session}>
              <UnplugIcon data-icon="inline-start" />
              Disconnect
            </Button>
          </>
        )}
        <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onEdit}>
          <EditIcon data-icon="inline-start" />
          Edit
        </Button>
        <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onDelete} disabled={isBusy}>
          <Trash2Icon data-icon="inline-start" />
          Delete
        </Button>
      </div>
    </Card>
  );
}

export function ProvidersSettingsSection({
  providers,
  options,
  busyProviderId,
  onCreate,
  onEdit,
  onDelete,
  onConnect,
  onRefresh,
  onDisconnect,
  onShowUsage,
}: {
  providers: ProviderView[];
  options: ConfigOptions;
  busyProviderId: string | null;
  onCreate: () => void;
  onEdit: (provider: ProviderView) => void;
  onDelete: (provider: ProviderView) => void;
  onConnect: (provider: ProviderView) => void;
  onRefresh: (providerId: string) => void;
  onDisconnect: (providerId: string) => void;
  onShowUsage: (provider: ProviderView) => void;
}) {
  return (
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Providers</CardTitle>
            <div className="settings-panel__subtitle">LLM provider connections and credentials</div>
          </div>
          <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onCreate}>
            <PlusIcon data-icon="inline-start" />
            Add Provider
          </Button>
        </CardHeader>
        <CardContent className="settings-panel__body">
          {providers.length === 0 ? (
            <EmptyState title="No providers configured" description="Add a provider to start using model profiles." />
          ) : (
            providers.map((provider) => (
              <ProviderCard
                key={provider.id}
                provider={provider}
                options={options}
                isBusy={busyProviderId === provider.id}
                onEdit={() => onEdit(provider)}
                onDelete={() => onDelete(provider)}
                onConnect={() => onConnect(provider)}
                onRefresh={() => onRefresh(provider.id)}
                onDisconnect={() => onDisconnect(provider.id)}
                onShowUsage={() => onShowUsage(provider)}
              />
            ))
          )}
        </CardContent>
      </Card>
    </section>
  );
}
