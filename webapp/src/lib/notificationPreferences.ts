import { useSyncExternalStore } from "react";

export type NotificationSoundId = "chime" | "bell" | "pop" | "pulse";

export type NotificationSoundOption = {
  id: NotificationSoundId;
  label: string;
  description: string;
};

export type NotificationPreferences = {
  desktopEnabled: boolean;
  soundEnabled: boolean;
  soundId: NotificationSoundId;
};

export type BrowserNotificationPermission =
  | "unsupported"
  | "default"
  | "denied"
  | "granted";

export const NOTIFICATION_PREFERENCES_STORAGE_KEY =
  "pbi-agent.notification-preferences";

export const DEFAULT_NOTIFICATION_SOUND_ID: NotificationSoundId = "chime";

export const NOTIFICATION_SOUND_OPTIONS: NotificationSoundOption[] = [
  {
    id: "chime",
    label: "Chime",
    description: "The original soft descending chime.",
  },
  {
    id: "bell",
    label: "Bell",
    description: "A bright two-tone bell.",
  },
  {
    id: "pop",
    label: "Pop",
    description: "A short, subtle pop.",
  },
  {
    id: "pulse",
    label: "Pulse",
    description: "Two quick alert pulses.",
  },
];

const PREFERENCES_CHANGED_EVENT = "pbi-agent:notification-preferences-changed";
const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  desktopEnabled: false,
  soundEnabled: false,
  soundId: DEFAULT_NOTIFICATION_SOUND_ID,
};

let cachedPreferences: NotificationPreferences | null = null;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function isNotificationSoundId(value: unknown): value is NotificationSoundId {
  return NOTIFICATION_SOUND_OPTIONS.some((option) => option.id === value);
}

function normalizeSoundId(value: unknown): NotificationSoundId {
  return isNotificationSoundId(value) ? value : DEFAULT_NOTIFICATION_SOUND_ID;
}

function normalizePreferences(
  preferences: Partial<NotificationPreferences>,
): NotificationPreferences {
  return {
    desktopEnabled: preferences.desktopEnabled === true,
    soundEnabled: preferences.soundEnabled === true,
    soundId: normalizeSoundId(preferences.soundId),
  };
}

function parsePreferences(value: string | null): NotificationPreferences {
  if (!value) {
    return DEFAULT_NOTIFICATION_PREFERENCES;
  }
  try {
    const parsed = JSON.parse(value) as Partial<NotificationPreferences>;
    return normalizePreferences(parsed);
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
  const merged = normalizePreferences({
    ...getCachedPreferences(),
    ...nextPreferences,
  });
  writePreferences(merged);
  return merged;
}

export function resetNotificationPreferencesForTests(): void {
  cachedPreferences = null;
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

export function setNotificationSoundId(
  soundId: NotificationSoundId,
): NotificationPreferences {
  return setNotificationPreferences({ soundId });
}

type WindowWithAudioContext = Window & typeof globalThis & {
  webkitAudioContext?: typeof AudioContext;
};

type SoundTone = {
  frequency: number;
  endFrequency?: number;
  start: number;
  duration: number;
  volume: number;
  type?: OscillatorType;
};

const NOTIFICATION_SOUND_PATTERNS: Record<NotificationSoundId, SoundTone[]> = {
  chime: [
    { frequency: 880, endFrequency: 660, start: 0, duration: 0.22, volume: 0.18 },
  ],
  bell: [
    { frequency: 988, endFrequency: 1318, start: 0, duration: 0.16, volume: 0.16 },
    { frequency: 659, endFrequency: 784, start: 0.09, duration: 0.24, volume: 0.11 },
  ],
  pop: [
    {
      frequency: 420,
      endFrequency: 180,
      start: 0,
      duration: 0.12,
      volume: 0.16,
      type: "triangle",
    },
  ],
  pulse: [
    { frequency: 740, start: 0, duration: 0.1, volume: 0.14, type: "square" },
    { frequency: 740, start: 0.16, duration: 0.1, volume: 0.14, type: "square" },
  ],
};

function playTone(
  audioContext: AudioContext,
  tone: SoundTone,
  startedAt: number,
): { oscillator: OscillatorNode; endedAt: number } {
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  const toneStartedAt = startedAt + tone.start;
  const toneEndedAt = toneStartedAt + tone.duration;

  oscillator.type = tone.type ?? "sine";
  oscillator.frequency.setValueAtTime(tone.frequency, toneStartedAt);
  if (tone.endFrequency) {
    oscillator.frequency.exponentialRampToValueAtTime(
      tone.endFrequency,
      toneEndedAt,
    );
  }
  gain.gain.setValueAtTime(0.0001, toneStartedAt);
  gain.gain.exponentialRampToValueAtTime(tone.volume, toneStartedAt + 0.025);
  gain.gain.exponentialRampToValueAtTime(0.0001, toneEndedAt);

  oscillator.connect(gain);
  gain.connect(audioContext.destination);
  oscillator.start(toneStartedAt);
  oscillator.stop(toneEndedAt);

  return { oscillator, endedAt: toneEndedAt };
}

export async function playNotificationSound(
  soundId: NotificationSoundId = DEFAULT_NOTIFICATION_SOUND_ID,
): Promise<void> {
  if (!isBrowser()) return;

  const AudioContextConstructor =
    window.AudioContext ?? (window as WindowWithAudioContext).webkitAudioContext;
  if (!AudioContextConstructor) return;

  try {
    const audioContext = new AudioContextConstructor();
    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }

    const startedAt = audioContext.currentTime;
    const pattern = NOTIFICATION_SOUND_PATTERNS[normalizeSoundId(soundId)];
    const playedTones = pattern.map((tone) => playTone(audioContext, tone, startedAt));
    const finalTone = playedTones.reduce((latest, current) =>
      current.endedAt > latest.endedAt ? current : latest,
    );

    finalTone.oscillator.addEventListener("ended", () => {
      void audioContext.close();
    });
  } catch {
    // Browser audio can be blocked by autoplay policy; notification sound is best-effort.
  }
}
