import { EditIcon, PlusIcon, Trash2Icon } from "lucide-react";
import type { ModelProfileView, ProviderView } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

function ProfileCard({
  profile,
  onEdit,
  onDelete,
}: {
  profile: ModelProfileView;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const r = profile.resolved_runtime;
  const runtimeParts: string[] = [r.model];
  if (r.reasoning_effort && r.reasoning_effort !== "none") {
    runtimeParts.push(r.reasoning_effort);
  }
  if (r.service_tier) {
    runtimeParts.push(r.service_tier);
  }

  return (
    <Card className="settings-item settings-item--provider provider-card">
      <div className="provider-card__info">
        <span className="settings-item__name">{profile.name}</span>
        <div className="provider-card__subtitle">
          {profile.provider.name} · {runtimeParts.join(" · ")}
        </div>
      </div>
      <div className="provider-card__actions">
        <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onEdit}>
          <EditIcon data-icon="inline-start" />
          Edit
        </Button>
        <Button type="button" variant="ghost" size="sm" className="task-card__action-button" onClick={onDelete}>
          <Trash2Icon data-icon="inline-start" />
          Delete
        </Button>
      </div>
    </Card>
  );
}

export function ModelProfilesSettingsSection({
  profiles,
  providers,
  activeProfileId,
  onSetActiveProfile,
  onCreate,
  onEdit,
  onDelete,
}: {
  profiles: ModelProfileView[];
  providers: ProviderView[];
  activeProfileId: string | null;
  onSetActiveProfile: (profileId: string | null) => void;
  onCreate: () => void;
  onEdit: (profile: ModelProfileView) => void;
  onDelete: (profile: ModelProfileView) => void;
}) {
  const addProfileButton = (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="task-card__action-button"
      onClick={onCreate}
      disabled={providers.length === 0}
    >
      <PlusIcon data-icon="inline-start" />
      Add Profile
    </Button>
  );

  return (
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Model Profiles</CardTitle>
            <div className="settings-panel__subtitle">
              Runtime configuration combining a provider with model settings
            </div>
          </div>
          {providers.length === 0 ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex">{addProfileButton}</span>
              </TooltipTrigger>
              <TooltipContent>Add a provider first</TooltipContent>
            </Tooltip>
          ) : addProfileButton}
        </CardHeader>
        <CardContent className="settings-panel__body">
          <div className="active-profile-control">
            <span className="active-profile-control__label">Active default</span>
            <NativeSelect
              name="active-profile"
              className="active-profile-control__select"
              value={activeProfileId ?? ""}
              onChange={(event) => onSetActiveProfile(event.target.value || null)}
            >
              <NativeSelectOption value="">No default</NativeSelectOption>
              {profiles.map((profile) => (
                <NativeSelectOption key={profile.id} value={profile.id}>
                  {profile.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>

          {profiles.length === 0 ? (
            <EmptyState title="No profiles configured" description="Add a model profile to configure runtime settings." />
          ) : (
            profiles.map((profile) => (
              <ProfileCard
                key={profile.id}
                profile={profile}
                onEdit={() => onEdit(profile)}
                onDelete={() => onDelete(profile)}
              />
            ))
          )}
        </CardContent>
      </Card>
    </section>
  );
}
