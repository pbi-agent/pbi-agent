import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

import { DictationTimeline, formatElapsed, voiceLevel } from "./DictationTimeline";

function barHeights(): string[] {
  return [...document.querySelectorAll<HTMLElement>("[data-dictation-bar]")].map(
    (bar) => bar.style.getPropertyValue("--dictation-bar-height"),
  );
}

/** Captures animation frames so a test can run them at chosen timestamps. */
function controlFrames() {
  const callbacks: FrameRequestCallback[] = [];
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
    callbacks.push(callback);
    return callbacks.length;
  });
  return (now: number) => act(() => callbacks.shift()?.(now));
}

describe("DictationTimeline", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("measures loudness in the voice band", () => {
    expect(voiceLevel(null)).toBe(0);
    expect(voiceLevel(new Uint8Array(0))).toBe(0);
    expect(voiceLevel(new Uint8Array(64))).toBe(0);
    expect(voiceLevel(new Uint8Array(64).fill(255))).toBe(1);

    // Energy above the voice band (hiss) is ignored.
    const hiss = new Uint8Array(64);
    hiss.fill(255, 40);
    expect(voiceLevel(hiss)).toBe(0);

    const quiet = voiceLevel(new Uint8Array(64).fill(60));
    const loud = voiceLevel(new Uint8Array(64).fill(180));
    expect(quiet).toBeGreaterThan(0);
    expect(loud).toBeGreaterThan(quiet);
  });

  it("formats the elapsed time", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(7.9)).toBe("0:07");
    expect(formatElapsed(125)).toBe("2:05");
  });

  it("starts as a labelled row of resting dots", () => {
    controlFrames();
    render(
      <DictationTimeline getFrequencyData={() => null} label="Recording audio" />,
    );

    expect(screen.getByRole("img", { name: "Recording audio" })).toBeInTheDocument();
    const heights = barHeights();
    expect(heights.length).toBeGreaterThan(100);
    expect(new Set(heights)).toEqual(new Set(["2px"]));
  });

  it("scrolls loudness in from the right, one bar per interval", () => {
    const runFrame = controlFrames();
    let data = new Uint8Array(64).fill(255);
    render(<DictationTimeline getFrequencyData={() => data} />);

    runFrame(0);
    expect(barHeights().at(-1)).toBe("2px");

    runFrame(60);
    expect(barHeights().slice(-2)).toEqual(["2px", "24px"]);

    data = new Uint8Array(64);
    runFrame(120);
    expect(barHeights().slice(-3)).toEqual(["2px", "24px", "2px"]);
  });

  it("counts the elapsed recording time", () => {
    vi.useFakeTimers();
    controlFrames();
    render(<DictationTimeline getFrequencyData={() => null} />);
    const elapsed = document.querySelector("[data-dictation-elapsed]");

    expect(elapsed).toHaveTextContent("0:00");
    act(() => {
      vi.advanceTimersByTime(65_000);
    });
    expect(elapsed).toHaveTextContent("1:05");
  });

  it("stays still when reduced motion is requested", () => {
    const rafSpy = vi.spyOn(window, "requestAnimationFrame");
    vi.stubGlobal("matchMedia", () => ({ matches: true }));

    render(<DictationTimeline getFrequencyData={() => new Uint8Array(64).fill(255)} />);

    expect(rafSpy).not.toHaveBeenCalled();
    expect(new Set(barHeights())).toEqual(new Set(["2px"]));
  });

  it("stops the animation frame loop on unmount", () => {
    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame");
    vi.spyOn(window, "requestAnimationFrame").mockReturnValue(42);

    const { unmount } = render(<DictationTimeline getFrequencyData={() => null} />);
    unmount();

    expect(cancelSpy).toHaveBeenCalledWith(42);
  });
});
