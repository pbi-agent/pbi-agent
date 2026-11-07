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
import { SettingsPanel, SettingsSection } from "./settings-layout";
import { Checkbox } from "../ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "../ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

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
    <SettingsSection>
      <SettingsPanel
        title="Notifications"
        description="Alerts for interactive questions and finished sessions"
      >
          <FieldGroup>
            <Field orientation="horizontal">
              <Checkbox
                id="desktop-notifications"
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

            <Field orientation="horizontal">
              <Checkbox
                id="sound-notifications"
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
                    <div className="flex flex-wrap items-center gap-2">
                      <FieldLabel htmlFor="notification-sound">
                        Notification sound
                      </FieldLabel>
                      <Select
                        value={preferences.soundId}
                        onValueChange={(nextSoundId) => {
                          if (isNotificationSoundId(nextSoundId)) {
                            setNotificationSoundId(nextSoundId);
                          }
                        }}
                      >
                        <SelectTrigger
                          id="notification-sound"
                          size="sm"
                          className="w-48"
                          aria-describedby="notification-sound-description"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                        {NOTIFICATION_SOUND_OPTIONS.map((option) => (
                          <SelectItem key={option.id} value={option.id}>
                            {option.label}
                          </SelectItem>
                        ))}
                        </SelectContent>
                      </Select>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            type="button"
                            variant="outline"
                            size="icon-sm"
                            aria-label="Preview notification sound"
                            onClick={() => {
                              void playNotificationSound(preferences.soundId);
                            }}
                          >
                            <PlayIcon data-icon="inline-start" aria-hidden="true" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Preview notification sound</TooltipContent>
                      </Tooltip>
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
      </SettingsPanel>
    </SettingsSection>
  );
}
