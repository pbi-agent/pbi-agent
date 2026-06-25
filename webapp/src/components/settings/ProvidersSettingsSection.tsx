import {
  CheckCircle2Icon,
  EditIcon,
  GaugeIcon,
  MoreHorizontalIcon,
  PlugZapIcon,
  PlusIcon,
  Trash2Icon,
  UnplugIcon,
} from "lucide-react";
import type { ConfigOptions, ProviderAuthStatus, ProviderView } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

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
    (provider.kind === "chatgpt" || provider.kind === "github_copilot") &&
    provider.auth_status.session_status === "connected"
  );
}

function supportsModelProfiles(provider: ProviderView, options: ConfigOptions): boolean {
  return options.provider_metadata[provider.kind]?.supports_model_profiles !== false;
}

function supportsStt(provider: ProviderView): boolean {
  return provider.supports_stt;
}

function providerCapabilityBadges(
  provider: ProviderView,
  options: ConfigOptions,
): Array<{ label: string; variant: "secondary" | "info" }> {
  const badges: Array<{ label: string; variant: "secondary" | "info" }> = [];
  if (supportsModelProfiles(provider, options)) {
    badges.push({ label: "Model profiles", variant: "secondary" });
  }
  if (supportsStt(provider)) {
    badges.push({ label: "STT", variant: "info" });
  }
  return badges;
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
  const capabilityBadges = providerCapabilityBadges(provider, options);

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
        {capabilityBadges.length > 0 && (
          <div className="settings-item__meta">
            {capabilityBadges.map((badge) => (
              <Badge key={badge.label} size="meta" variant={badge.variant}>
                {badge.label}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="provider-card__actions">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="settings-action-button"
              aria-label={`Open actions for ${provider.name} provider`}
            >
              <MoreHorizontalIcon />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuGroup>
              {showAuthActions ? (
                <>
                  <DropdownMenuItem onClick={onConnect} disabled={isBusy}>
                    <PlugZapIcon />
                    {authStatus.has_session ? "Reconnect" : "Connect"}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={onRefresh}
                    disabled={isBusy || !authStatus.can_refresh}
                  >
                    <CheckCircle2Icon />
                    Refresh
                  </DropdownMenuItem>
                  {showUsageAction ? (
                    <DropdownMenuItem onClick={onShowUsage}>
                      <GaugeIcon />
                      Usage
                    </DropdownMenuItem>
                  ) : null}
                  <DropdownMenuItem
                    onClick={onDisconnect}
                    disabled={isBusy || !authStatus.has_session}
                  >
                    <UnplugIcon />
                    Disconnect
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              ) : null}
              <DropdownMenuItem onClick={onEdit}>
                <EditIcon />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                onClick={onDelete}
                disabled={isBusy}
              >
                <Trash2Icon />
                Delete
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
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
            <div className="settings-panel__subtitle">Model and speech provider connections and credentials</div>
          </div>
          <Button type="button" variant="ghost" size="sm" className="settings-action-button" onClick={onCreate}>
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
