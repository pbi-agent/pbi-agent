import { useEffect, useState } from "react";
import type { MaintenanceConfig } from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Field, FieldContent, FieldDescription, FieldGroup, FieldLabel } from "../ui/field";
import { Input } from "../ui/input";
import { SettingsNote, SettingsPanel, SettingsSection } from "./settings-layout";

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
    <SettingsSection>
      <SettingsNote>
        Daily startup maintenance purges old sessions, logs, transient web state, and unreferenced web uploads.
      </SettingsNote>
      <SettingsPanel title="Maintenance" description="Retention and cleanup policy">
        <FieldGroup>
          <Field>
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
              className="max-w-40"
              value={retentionDays}
              onChange={(event) => setRetentionDays(event.target.value)}
            />
          </Field>
        </FieldGroup>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="flex justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            data-settings-action-button
            onClick={() => void handleSave()}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save Changes"}
          </Button>
        </div>
      </SettingsPanel>
    </SettingsSection>
  );
}
