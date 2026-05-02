import {
  NOTIFICATION_PREFERENCES_STORAGE_KEY,
  playNotificationSound,
  readNotificationPreferences,
  requestDesktopNotificationPermission,
  resetNotificationPreferencesForTests,
  setNotificationPreferences,
} from "./notificationPreferences";

type NotificationPermissionValue = "default" | "denied" | "granted";

const originalNotification = globalThis.Notification;
const originalAudioContext = window.AudioContext;

function installNotificationMock(
  permission: NotificationPermissionValue,
  requestResult: NotificationPermissionValue,
) {
  class NotificationMock {
    static permission = permission;
    static requestPermission = vi.fn().mockResolvedValue(requestResult);
  }

  Object.defineProperty(globalThis, "Notification", {
    configurable: true,
    writable: true,
    value: NotificationMock,
  });
  return NotificationMock;
}

function restoreBrowserGlobals() {
  if (originalNotification) {
    Object.defineProperty(globalThis, "Notification", {
      configurable: true,
      writable: true,
      value: originalNotification,
    });
  } else {
    Reflect.deleteProperty(globalThis, "Notification");
  }

  Object.defineProperty(window, "AudioContext", {
    configurable: true,
    writable: true,
    value: originalAudioContext,
  });
}

describe("notification preferences", () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetNotificationPreferencesForTests();
  });

  afterEach(() => {
    restoreBrowserGlobals();
    resetNotificationPreferencesForTests();
    vi.clearAllMocks();
  });

  it("defaults desktop and sound notifications to disabled", () => {
    expect(readNotificationPreferences()).toEqual({
      desktopEnabled: false,
      soundEnabled: false,
    });
  });

  it("persists notification preferences in localStorage", () => {
    setNotificationPreferences({ desktopEnabled: true, soundEnabled: true });

    expect(readNotificationPreferences()).toEqual({
      desktopEnabled: true,
      soundEnabled: true,
    });
    expect(
      JSON.parse(
        window.localStorage.getItem(NOTIFICATION_PREFERENCES_STORAGE_KEY) ?? "{}",
      ),
    ).toEqual({ desktopEnabled: true, soundEnabled: true });
  });

  it("requests desktop notification permission before enabling desktop notifications", async () => {
    const notificationMock = installNotificationMock("default", "granted");

    const permission = await requestDesktopNotificationPermission();

    expect(notificationMock.requestPermission).toHaveBeenCalledTimes(1);
    expect(permission).toBe("granted");
    expect(readNotificationPreferences().desktopEnabled).toBe(true);
  });

  it("keeps desktop notifications disabled when permission is denied", async () => {
    installNotificationMock("default", "denied");

    const permission = await requestDesktopNotificationPermission();

    expect(permission).toBe("denied");
    expect(readNotificationPreferences().desktopEnabled).toBe(false);
  });

  it("plays a short sound when Web Audio is available", async () => {
    const start = vi.fn();
    const stop = vi.fn();
    const close = vi.fn();
    const connect = vi.fn();
    const addEventListener = vi.fn((_event: string, callback: () => void) => callback());
    const setValueAtTime = vi.fn();
    const exponentialRampToValueAtTime = vi.fn();

    class AudioContextMock {
      state = "running" as AudioContextState;
      currentTime = 1;
      destination = {} as AudioDestinationNode;
      close = close;
      resume = vi.fn();

      createOscillator() {
        return {
          type: "sine" as OscillatorType,
          frequency: { setValueAtTime, exponentialRampToValueAtTime },
          connect,
          start,
          stop,
          addEventListener,
        };
      }

      createGain() {
        return {
          gain: { setValueAtTime, exponentialRampToValueAtTime },
          connect,
        };
      }
    }

    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      writable: true,
      value: AudioContextMock,
    });

    await playNotificationSound();

    expect(start).toHaveBeenCalledTimes(1);
    expect(stop).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("does not throw when Web Audio is unavailable", async () => {
    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      writable: true,
      value: undefined,
    });

    await expect(playNotificationSound()).resolves.toBeUndefined();
  });
});
