import { useState } from "react";
import { AlertTriangleIcon, InfoIcon } from "lucide-react";
import type { UserProfile } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import { Input } from "../ui/input";
import { Separator } from "../ui/separator";
import { Textarea } from "../ui/textarea";
import { SettingsPanel, SettingsSection } from "./settings-layout";

const EMPTY_PROFILE: UserProfile = {
  preferred_name: "",
  role: "",
  about: "",
  preferences: "",
  instructions: "",
};

export function ProfileSettingsSection({
  profile,
  draft,
  onDraftChange,
  onSave,
}: {
  profile: UserProfile;
  draft: UserProfile;
  onDraftChange: (profile: UserProfile) => void;
  onSave: (profile: UserProfile) => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const dirty =
    draft.preferred_name !== profile.preferred_name ||
    draft.role !== profile.role ||
    draft.about !== profile.about ||
    draft.preferences !== profile.preferences ||
    draft.instructions !== profile.instructions;

  function updateField(field: keyof UserProfile, value: string) {
    onDraftChange({ ...draft, [field]: value });
  }

  async function handleSave() {
    setError(null);
    setSaving(true);
    try {
      await onSave(draft);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <SettingsSection>
      <Alert>
        <InfoIcon />
        <AlertDescription>
          Saved globally for every project. Profile content is included in agent
          instructions and sent to the model provider when a new or reloaded
          session runs.
        </AlertDescription>
      </Alert>

      <SettingsPanel
        title="Profile"
        description="Personal context, preferences, and reusable instructions"
      >
          <FieldGroup>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="profile-preferred-name">
                  Preferred name
                </FieldLabel>
                <FieldDescription>
                  How the agent should address you.
                </FieldDescription>
                <Input
                  id="profile-preferred-name"
                  value={draft.preferred_name}
                  maxLength={200}
                  disabled={saving}
                  onChange={(event) =>
                    updateField("preferred_name", event.target.value)
                  }
                  placeholder="Ada"
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="profile-role">Role or occupation</FieldLabel>
                <FieldDescription>
                  Your discipline, role, or area of expertise.
                </FieldDescription>
                <Input
                  id="profile-role"
                  value={draft.role}
                  maxLength={500}
                  disabled={saving}
                  onChange={(event) => updateField("role", event.target.value)}
                  placeholder="Staff software engineer"
                />
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor="profile-about">About you</FieldLabel>
              <FieldDescription>
                Background or context that helps the agent understand your work.
              </FieldDescription>
              <Textarea
                id="profile-about"
                className="min-h-24"
                value={draft.about}
                maxLength={4_000}
                disabled={saving}
                onChange={(event) => updateField("about", event.target.value)}
                placeholder="I build developer tools and maintain Python and TypeScript projects."
              />
            </Field>
          </FieldGroup>

          <Separator />

          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="profile-preferences">Preferences</FieldLabel>
              <FieldDescription>
                Describe how you prefer the agent to communicate, collaborate,
                and present results.
              </FieldDescription>
              <Textarea
                id="profile-preferences"
                className="min-h-24"
                value={draft.preferences}
                maxLength={8_000}
                disabled={saving}
                onChange={(event) =>
                  updateField("preferences", event.target.value)
                }
                placeholder="Keep explanations concise, lead with the outcome, and include validation results."
              />
            </Field>
          </FieldGroup>

          <Separator />

          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="profile-global-instructions">
                Global instructions
              </FieldLabel>
              <FieldDescription>
                Instructions the agent should follow in every session and
                project.
              </FieldDescription>
              <Textarea
                id="profile-global-instructions"
                className="min-h-40"
                value={draft.instructions}
                maxLength={12_000}
                disabled={saving}
                onChange={(event) =>
                  updateField("instructions", event.target.value)
                }
                placeholder="Always preserve existing conventions. Ask before making destructive changes."
              />
            </Field>
          </FieldGroup>

          {error && (
            <Alert variant="destructive">
              <AlertTriangleIcon />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-settings-action-button
              onClick={() => onDraftChange(EMPTY_PROFILE)}
              disabled={saving || Object.values(draft).every((value) => !value)}
            >
              Clear
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-settings-action-button
              onClick={() => void handleSave()}
              disabled={saving || !dirty}
            >
              {saving ? "Saving…" : "Save Changes"}
            </Button>
          </div>
      </SettingsPanel>
    </SettingsSection>
  );
}