import { useSyncExternalStore } from "react";

export type NotificationPreferences = {
  desktopEnabled: boolean;
  soundEnabled: boolean;
};

export type BrowserNotificationPermission =
  | "unsupported"
  | "default"
  | "denied"
  | "granted";

export const NOTIFICATION_PREFERENCES_STORAGE_KEY =
  "pbi-agent.notification-preferences";

const PREFERENCES_CHANGED_EVENT = "pbi-agent:notification-preferences-changed";
const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  desktopEnabled: false,
  soundEnabled: false,
};

let cachedPreferences: NotificationPreferences | null = null;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function parsePreferences(value: string | null): NotificationPreferences {
  if (!value) {
    return DEFAULT_NOTIFICATION_PREFERENCES;
  }
  try {
    const parsed = JSON.parse(value) as Partial<NotificationPreferences>;
    return {
      desktopEnabled: parsed.desktopEnabled === true,
      soundEnabled: parsed.soundEnabled === true,
    };
  } catch {
    return DEFAULT_NOTIFICATION_PREFERENCES;
  }
}

function readStoredPreferences(): NotificationPreferences {
  if (!isBrowser()) {
    return DEFAULT_NOTIFICATION_PREFERENCES;
  }
  try {
    return parsePreferences(
      window.localStorage.getItem(NOTIFICATION_PREFERENCES_STORAGE_KEY),
    );
  } catch {
    return DEFAULT_NOTIFICATION_PREFERENCES;
  }
}

function getCachedPreferences(): NotificationPreferences {
  cachedPreferences ??= readStoredPreferences();
  return cachedPreferences;
}

function emitPreferencesChanged(): void {
  if (!isBrowser()) return;
  window.dispatchEvent(new Event(PREFERENCES_CHANGED_EVENT));
}

function writePreferences(nextPreferences: NotificationPreferences): void {
  cachedPreferences = nextPreferences;
  if (isBrowser()) {
    try {
      window.localStorage.setItem(
        NOTIFICATION_PREFERENCES_STORAGE_KEY,
        JSON.stringify(nextPreferences),
      );
    } catch {
      // Keep the in-memory preference so the current tab still responds.
    }
  }
  emitPreferencesChanged();
}

export function readNotificationPreferences(): NotificationPreferences {
  return getCachedPreferences();
}

export function setNotificationPreferences(
  nextPreferences: Partial<NotificationPreferences>,
): NotificationPreferences {
  const merged = {
    ...getCachedPreferences(),
    ...nextPreferences,
  };
  writePreferences(merged);
  return merged;
}

export function resetNotificationPreferencesForTests(): void {
  cachedPreferences = DEFAULT_NOTIFICATION_PREFERENCES;
  if (isBrowser()) {
    try {
      window.localStorage.removeItem(NOTIFICATION_PREFERENCES_STORAGE_KEY);
    } catch {
      // Ignore unavailable storage in tests and restricted browsers.
    }
  }
  emitPreferencesChanged();
}

function subscribeToNotificationPreferences(onStoreChange: () => void): () => void {
  if (!isBrowser()) {
    return () => {};
  }

  const handleStorage = (event: StorageEvent) => {
    if (event.key !== NOTIFICATION_PREFERENCES_STORAGE_KEY) return;
    cachedPreferences = readStoredPreferences();
    onStoreChange();
  };

  window.addEventListener(PREFERENCES_CHANGED_EVENT, onStoreChange);
  window.addEventListener("storage", handleStorage);
  return () => {
    window.removeEventListener(PREFERENCES_CHANGED_EVENT, onStoreChange);
    window.removeEventListener("storage", handleStorage);
  };
}

export function useNotificationPreferences(): NotificationPreferences {
  return useSyncExternalStore(
    subscribeToNotificationPreferences,
    getCachedPreferences,
    () => DEFAULT_NOTIFICATION_PREFERENCES,
  );
}

export function getBrowserNotificationPermission(): BrowserNotificationPermission {
  if (typeof Notification === "undefined") {
    return "unsupported";
  }
  return Notification.permission;
}

export async function requestDesktopNotificationPermission(): Promise<BrowserNotificationPermission> {
  if (typeof Notification === "undefined") {
    setNotificationPreferences({ desktopEnabled: false });
    return "unsupported";
  }

  const permission = await Notification.requestPermission();
  setNotificationPreferences({ desktopEnabled: permission === "granted" });
  return permission;
}

export function setDesktopNotificationsEnabled(enabled: boolean): NotificationPreferences {
  return setNotificationPreferences({ desktopEnabled: enabled });
}

export function setSoundNotificationsEnabled(enabled: boolean): NotificationPreferences {
  return setNotificationPreferences({ soundEnabled: enabled });
}

type WindowWithAudioContext = Window & typeof globalThis & {
  webkitAudioContext?: typeof AudioContext;
};

export async function playNotificationSound(): Promise<void> {
  if (!isBrowser()) return;

  const AudioContextConstructor =
    window.AudioContext ?? (window as WindowWithAudioContext).webkitAudioContext;
  if (!AudioContextConstructor) return;

  try {
    const audioContext = new AudioContextConstructor();
    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }

    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    const startedAt = audioContext.currentTime;
    const endedAt = startedAt + 0.22;

    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, startedAt);
    oscillator.frequency.exponentialRampToValueAtTime(660, endedAt);
    gain.gain.setValueAtTime(0.0001, startedAt);
    gain.gain.exponentialRampToValueAtTime(0.18, startedAt + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, endedAt);

    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(startedAt);
    oscillator.stop(endedAt);
    oscillator.addEventListener("ended", () => {
      void audioContext.close();
    });
  } catch {
    // Browser audio can be blocked by autoplay policy; notification sound is best-effort.
  }
}
