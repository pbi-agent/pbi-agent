import { useEffect, useState } from "react";
import type { ModelProfileView } from "../../types";
import { EMPTY_SELECT_VALUE, fromSelectValue, toSelectValue } from "../../lib/selectValues";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { SettingsPanel, SettingsSection } from "./settings-layout";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

export function PromptEnhancementSettingsSection({
  profiles,
  profileId,
  onSave,
}: {
  profiles: ModelProfileView[];
  profileId: string | null;
  onSave: (profileId: string | null) => Promise<void>;
}) {
  const [selectedProfileId, setSelectedProfileId] = useState(profileId ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedProfileId(profileId ?? "");
    setError(null);
  }, [profileId]);

  async function handleProfileChange(nextProfileId: string) {
    setSelectedProfileId(nextProfileId);
    setIsSaving(true);
    setError(null);
    try {
      await onSave(nextProfileId || null);
    } catch (err) {
      setError((err as Error).message);
      setSelectedProfileId(profileId ?? "");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <SettingsSection>
      <SettingsPanel
        title="Prompt enhancement"
        description="Choose the model profile used to improve composer drafts."
        actions={
          <Badge variant="info" size="meta">
            AI
          </Badge>
        }
      >
        <div className="flex flex-col gap-2" data-settings-active-control>
          <span className="text-sm font-medium">Model profile</span>
          <Select
            value={toSelectValue(selectedProfileId)}
            disabled={isSaving}
            onValueChange={(value) =>
              void handleProfileChange(fromSelectValue(value))
            }
          >
            <SelectTrigger
              id="prompt-enhancement-profile"
              aria-label="Prompt enhancement model profile"
              className="w-full max-w-md"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={EMPTY_SELECT_VALUE}>Current model</SelectItem>
              {profiles.map((profile) => (
                <SelectItem key={profile.id} value={profile.id}>
                  {profile.name} ({profile.provider.name})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </SettingsPanel>
    </SettingsSection>
  );
}