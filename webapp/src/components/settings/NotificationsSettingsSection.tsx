import { BellIcon, PlayIcon, Volume2Icon } from "lucide-react";
import {
  NOTIFICATION_SOUND_OPTIONS,
  getBrowserNotificationPermission,
  isNotificationSoundId,
  playNotificationSound,
  requestDesktopNotificationPermission,
  setDesktopNotificationsEnabled,
  setNotificationSoundId,
  setSoundNotificationsEnabled,
  useNotificationPreferences,
  type BrowserNotificationPermission,
} from "../../lib/notificationPreferences";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Checkbox } from "../ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";

function notificationPermissionLabel(
  permission: BrowserNotificationPermission,
  desktopEnabled: boolean,
): string {
  switch (permission) {
    case "unsupported":
      return "Browser notifications are not supported here.";
    case "denied":
      return "Notifications are blocked in this browser.";
    case "granted":
      return desktopEnabled
        ? "Desktop notifications are enabled."
        : "Desktop permission is granted, but notifications are disabled.";
    default:
      return "Desktop notifications have not been enabled.";
  }
}

export function NotificationsSettingsSection() {
  const preferences = useNotificationPreferences();
  const permission = getBrowserNotificationPermission();
  const desktopChecked = preferences.desktopEnabled && permission === "granted";
  const desktopUnavailable =
    permission === "unsupported" || (permission === "denied" && !preferences.desktopEnabled);

  async function handleDesktopCheckedChange(checked: boolean | "indeterminate") {
    if (checked === true) {
      await requestDesktopNotificationPermission();
      return;
    }
    setDesktopNotificationsEnabled(false);
  }

  return (
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div>
            <CardTitle className="settings-panel__title">Notifications</CardTitle>
            <CardDescription className="settings-panel__subtitle">
              Alerts for interactive questions and finished sessions
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="settings-panel__body settings-notifications">
          <FieldGroup>
            <Field orientation="horizontal" className="settings-notifications__field">
              <Checkbox
                id="desktop-notifications"
                className="settings-notifications__checkbox"
                checked={desktopChecked}
                disabled={desktopUnavailable}
                onCheckedChange={(checked) => {
                  void handleDesktopCheckedChange(checked);
                }}
              />
              <FieldContent>
                <FieldLabel htmlFor="desktop-notifications">
                  <BellIcon data-icon="inline-start" />
                  Desktop notifications
                </FieldLabel>
                <FieldDescription>
                  Show a browser notification when an ask_user question arrives or a session
                  finishes while this tab is hidden or unfocused. {notificationPermissionLabel(permission, desktopChecked)}
                </FieldDescription>
              </FieldContent>
            </Field>

            <Field orientation="horizontal" className="settings-notifications__field">
              <Checkbox
                id="sound-notifications"
                className="settings-notifications__checkbox"
                checked={preferences.soundEnabled}
                onCheckedChange={(checked) => {
                  setSoundNotificationsEnabled(checked === true);
                }}
              />
              <FieldContent>
                <FieldLabel htmlFor="sound-notifications">
                  <Volume2Icon data-icon="inline-start" />
                  Sound notifications
                </FieldLabel>
                <FieldDescription>
                  Play the selected sound for the same hidden or unfocused alerts.
                </FieldDescription>
                {preferences.soundEnabled && (
                  <>
                    <div className="settings-notifications__sound-row">
                      <FieldLabel
                        htmlFor="notification-sound"
                        className="settings-notifications__sound-label"
                      >
                        Notification sound
                      </FieldLabel>
                      <NativeSelect
                        id="notification-sound"
                        size="sm"
                        className="settings-notifications__sound-select"
                        value={preferences.soundId}
                        onChange={(event) => {
                          const nextSoundId = event.target.value;
                          if (isNotificationSoundId(nextSoundId)) {
                            setNotificationSoundId(nextSoundId);
                          }
                        }}
                        aria-describedby="notification-sound-description"
                      >
                        {NOTIFICATION_SOUND_OPTIONS.map((option) => (
                          <NativeSelectOption key={option.id} value={option.id}>
                            {option.label}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-sm"
                        className="settings-notifications__sound-preview"
                        aria-label="Preview notification sound"
                        title="Preview notification sound"
                        onClick={() => {
                          void playNotificationSound(preferences.soundId);
                        }}
                      >
                        <PlayIcon aria-hidden="true" />
                      </Button>
                    </div>
                    <FieldDescription id="notification-sound-description">
                      {
                        NOTIFICATION_SOUND_OPTIONS.find(
                          (option) => option.id === preferences.soundId,
                        )?.description
                      }
                    </FieldDescription>
                  </>
                )}
              </FieldContent>
            </Field>
          </FieldGroup>
        </CardContent>
      </Card>
    </section>
  );
}
