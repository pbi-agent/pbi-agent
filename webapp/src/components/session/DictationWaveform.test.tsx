import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { DictationWaveform } from "./DictationWaveform";

describe("DictationWaveform", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders an accessible labelled wave band with the requested bar count", () => {
    render(
      <DictationWaveform
        barCount={6}
        getFrequencyData={() => new Uint8Array(0)}
        label="Recording audio"
      />,
    );

    const band = screen.getByRole("img", { name: "Recording audio" });
    expect(band.querySelectorAll(".composer__waveform-bar")).toHaveLength(6);
  });

  it("scales bars from the live frequency spectrum", () => {
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation(() => 0);

    const data = new Uint8Array([255, 255, 255, 255]);
    render(
      <DictationWaveform barCount={2} getFrequencyData={() => data} />,
    );

    const bars = document.querySelectorAll<HTMLSpanElement>(
      ".composer__waveform-bar",
    );
    expect(bars).toHaveLength(2);
    expect(bars[0]?.style.transform).toBe("scaleY(1.000)");
    expect(rafSpy).toHaveBeenCalled();
  });

  it("stretches the active voice frequency band across all bars", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 0);

    const data = new Uint8Array(64);
    data.fill(255, 1, 24);

    render(
      <DictationWaveform barCount={16} getFrequencyData={() => data} />,
    );

    const bars = document.querySelectorAll<HTMLSpanElement>(
      ".composer__waveform-bar",
    );
    expect(bars).toHaveLength(16);
    expect(bars[0]?.style.transform).toBe("scaleY(1.000)");
    expect(bars[15]?.style.transform).toBe("scaleY(1.000)");
  });

  it("stops the animation frame loop on unmount", () => {
    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame");
    vi.spyOn(window, "requestAnimationFrame").mockReturnValue(42);

    const { unmount } = render(
      <DictationWaveform getFrequencyData={() => new Uint8Array([1])} />,
    );
    unmount();

    expect(cancelSpy).toHaveBeenCalledWith(42);
  });
});
