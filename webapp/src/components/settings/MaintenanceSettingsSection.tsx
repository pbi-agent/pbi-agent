import { useEffect, useState } from "react";
import type { MaintenanceConfig } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Field, FieldContent, FieldDescription, FieldGroup, FieldLabel } from "../ui/field";
import { Input } from "../ui/input";

export function MaintenanceSettingsSection({
  maintenance,
  onSave,
}: {
  maintenance: MaintenanceConfig;
  onSave: (retentionDays: number) => Promise<void>;
}) {
  const [retentionDays, setRetentionDays] = useState(String(maintenance.retention_days));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRetentionDays(String(maintenance.retention_days));
  }, [maintenance.retention_days]);

  async function handleSave() {
    const parsed = Number(retentionDays);
    if (!Number.isInteger(parsed) || parsed < 1) {
      setError("Retention days must be a whole number of at least 1.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await onSave(parsed);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="settings-section settings-section--active">
      <Alert className="settings-inline-note">
        <AlertDescription>
          Daily startup maintenance purges old sessions, logs, transient web state, and unreferenced web uploads.
        </AlertDescription>
      </Alert>
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Maintenance</CardTitle>
            <div className="settings-panel__subtitle">Retention and cleanup policy</div>
          </div>
        </CardHeader>
        <CardContent className="settings-panel__body maintenance-settings-panel__body">
          <FieldGroup>
            <Field className="maintenance-settings-field">
              <FieldContent>
                <FieldLabel htmlFor="maintenance-retention-days">Retention days</FieldLabel>
                <FieldDescription>
                  Data older than this many days is removed during the first startup each UTC day.
                </FieldDescription>
              </FieldContent>
              <Input
                id="maintenance-retention-days"
                type="number"
                min={1}
                className="task-form__input maintenance-settings-field__input"
                value={retentionDays}
                onChange={(event) => setRetentionDays(event.target.value)}
              />
            </Field>
          </FieldGroup>
          {error && <p className="settings-form-error">{error}</p>}
          <div className="settings-panel__actions">
            <Button
              type="button"
              variant="default"
              className="task-form__action-button"
              onClick={() => void handleSave()}
              disabled={saving}
            >
              {saving ? "Saving…" : "Save Changes"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
