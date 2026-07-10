import { useState } from "react";
import { AlertTriangleIcon, InfoIcon } from "lucide-react";
import type { UserProfile } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import { Input } from "../ui/input";
import { Separator } from "../ui/separator";
import { Textarea } from "../ui/textarea";

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
    <section className="settings-section settings-section--active">
      <Alert className="settings-inline-note">
        <InfoIcon />
        <AlertDescription>
          Saved globally for every project. Profile content is included in agent
          instructions and sent to the model provider when a new or reloaded
          session runs.
        </AlertDescription>
      </Alert>

      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Profile</CardTitle>
            <div className="settings-panel__subtitle">
              Personal context, preferences, and reusable instructions
            </div>
          </div>
        </CardHeader>

        <CardContent className="settings-panel__body profile-settings-panel__body">
          <FieldGroup>
            <div className="profile-settings-grid">
              <Field>
                <FieldLabel htmlFor="profile-preferred-name">
                  Preferred name
                </FieldLabel>
                <FieldDescription>
                  How the agent should address you.
                </FieldDescription>
                <Input
                  id="profile-preferred-name"
                  className="task-form__input"
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
                  className="task-form__input"
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
                className="task-form__textarea profile-settings-textarea"
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
                className="task-form__textarea profile-settings-textarea"
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
                className="task-form__textarea profile-settings-textarea profile-settings-textarea--instructions"
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

          <div className="settings-panel__actions">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="settings-action-button"
              onClick={() => onDraftChange(EMPTY_PROFILE)}
              disabled={saving || Object.values(draft).every((value) => !value)}
            >
              Clear
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="settings-action-button"
              onClick={() => void handleSave()}
              disabled={saving || !dirty}
            >
              {saving ? "Saving…" : "Save Changes"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}