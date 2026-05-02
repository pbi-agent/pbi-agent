import {
  getBrowserNotificationPermission,
  playNotificationSound,
  type NotificationPreferences,
} from "./notificationPreferences";

export type NotificationNavigate = (destination: string) => void | Promise<void>;

export type AppNotificationRequest = {
  title: string;
  body: string;
  tag: string;
  destination: string;
};

export function shouldNotifyForWindowState(): boolean {
  return document.visibilityState === "hidden" || !document.hasFocus();
}

export function triggerDesktopAndSoundNotification(
  request: AppNotificationRequest,
  preferences: NotificationPreferences,
  navigate: NotificationNavigate,
): boolean {
  let attemptedNotification = false;

  if (
    preferences.desktopEnabled
    && getBrowserNotificationPermission() === "granted"
  ) {
    attemptedNotification = true;
    try {
      const options: NotificationOptions & { renotify?: boolean } = {
        body: request.body,
        icon: "/logo.jpg",
        renotify: true,
        tag: request.tag,
      };
      const notification = new Notification(request.title, options);
      notification.onclick = () => {
        window.focus();
        void navigate(request.destination);
        notification.close();
      };
    } catch {
      // Browser notification construction can fail in restricted contexts.
    }
  }

  if (preferences.soundEnabled) {
    attemptedNotification = true;
    void playNotificationSound();
  }

  return attemptedNotification;
}
