import { EditIcon, PlusIcon, Trash2Icon } from "lucide-react";
import type { ModelProfileView, ProviderView } from "../../types";
import { EMPTY_SELECT_VALUE, fromSelectValueNullable, toSelectValue } from "../../lib/selectValues";
import { EmptyState } from "../shared/EmptyState";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { SettingsList, SettingsPanel, SettingsSection } from "./settings-layout";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

const TOOL_VISIBILITY_LABELS: Record<string, string> = {
  "read-image": "Read image",
  write: "Write",
  web: "Web",
  "sub-agent": "Sub-agent",
  shell: "Shell",
};

function toolVisibilityLabel(allowedTools: string[] | null): string {
  if (allowedTools === null) {
    return "All tools";
  }
  if (allowedTools.length === 0) {
    return "No built-ins";
  }
  return allowedTools
    .map((tool) => TOOL_VISIBILITY_LABELS[tool] ?? tool)
    .join(", ");
}

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
  if (profile.reasoning_mode) {
    runtimeParts.push(profile.reasoning_mode);
  }
  if (r.service_tier) {
    runtimeParts.push(r.service_tier);
  }

  return (
    <Card size="sm" data-model-profile-card>
      <CardHeader>
        <CardTitle>{profile.name}</CardTitle>
        <CardDescription>
          {profile.provider.name} · {runtimeParts.join(" · ")}
        </CardDescription>
        <CardAction>
          <div className="flex flex-wrap items-center gap-1">
            <Button type="button" variant="ghost" size="sm" onClick={onEdit}>
              <EditIcon data-icon="inline-start" />
              Edit
            </Button>
            <Button type="button" variant="destructive" size="sm" onClick={onDelete}>
              <Trash2Icon data-icon="inline-start" />
              Delete
            </Button>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1">
          <Badge size="meta" variant="secondary">
            Tools: {toolVisibilityLabel(profile.allowed_tools)}
          </Badge>
        </div>
      </CardContent>
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
      onClick={onCreate}
      disabled={providers.length === 0}
    >
      <PlusIcon data-icon="inline-start" />
      Add Profile
    </Button>
  );

  return (
    <SettingsSection>
      <SettingsPanel
        title="Model Profiles"
        description="Runtime configuration combining a provider with model settings"
        actions={
          providers.length === 0 ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex">{addProfileButton}</span>
              </TooltipTrigger>
              <TooltipContent>Add an LLM provider first</TooltipContent>
            </Tooltip>
          ) : (
            addProfileButton
          )
        }
      >
        <div className="flex flex-col gap-2" data-settings-active-control>
          <span className="text-sm font-medium">Active default</span>
          <Select
            value={toSelectValue(activeProfileId)}
            onValueChange={(value) =>
              onSetActiveProfile(fromSelectValueNullable(value))
            }
          >
            <SelectTrigger aria-label="Active default profile" className="w-full max-w-md">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EMPTY_SELECT_VALUE}>No default</SelectItem>
              {profiles.map((profile) => (
                <SelectItem key={profile.id} value={profile.id}>
                  {profile.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {profiles.length === 0 ? (
          <EmptyState title="No profiles configured" description="Add an LLM provider, then create a model profile to configure runtime settings." />
        ) : (
          <SettingsList>
            {profiles.map((profile) => (
              <ProfileCard
                key={profile.id}
                profile={profile}
                onEdit={() => onEdit(profile)}
                onDelete={() => onDelete(profile)}
              />
            ))}
          </SettingsList>
        )}
      </SettingsPanel>
    </SettingsSection>
  );
}
