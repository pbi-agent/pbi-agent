import { useEffect, useState } from "react";
import type { ModelProfileView } from "../../types";
import { EMPTY_SELECT_VALUE, fromSelectValue, toSelectValue } from "../../lib/selectValues";
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
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">
              Prompt enhancement
            </CardTitle>
            <div className="settings-panel__subtitle">
              Choose the model profile used to improve composer drafts.
            </div>
          </div>
          <Badge variant="info" size="meta">
            AI
          </Badge>
        </CardHeader>
        <CardContent className="settings-panel__body">
          <div className="active-profile-control">
            <span className="active-profile-control__label">Model profile</span>
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
                className="active-profile-control__select"
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
            <Alert variant="destructive" className="settings-error-banner">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </section>
  );
}