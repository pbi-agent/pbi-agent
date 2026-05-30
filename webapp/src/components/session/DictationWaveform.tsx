import { useEffect, useMemo, useRef } from "react";

import { cn } from "../../lib/utils";

interface DictationWaveformProps {
  /**
   * Returns the live byte frequency spectrum (0-255 per bin) of the recorded
   * microphone input, or `null`/empty when no data is available yet.
   */
  getFrequencyData: () => Uint8Array | null;
  /** Number of bars rendered in the wave band. */
  barCount?: number;
  className?: string;
  label?: string;
}

const DEFAULT_BAR_COUNT = 64;
const MIN_BAR_SCALE = 0.08;
const FREQUENCY_NOISE_FLOOR = 8;
const ACTIVE_BIN_PEAK_RATIO = 0.14;
const VOICE_BIN_FRACTION = 0.45;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function getDisplayFrequencyRange(data: Uint8Array): { start: number; end: number } {
  const bins = data.length;
  if (bins <= 2) {
    return { start: 0, end: bins };
  }

  // Raw analyser data spans the full Nyquist range, but speech mostly lives in
  // the lower portion. Detect the active speech band and stretch that range
  // across the whole visualizer so dictation does not animate only at the left.
  const voiceLimit = Math.max(2, Math.min(bins, Math.ceil(bins * VOICE_BIN_FRACTION)));
  let peak = 0;
  for (let index = 1; index < voiceLimit; index += 1) {
    peak = Math.max(peak, data[index] ?? 0);
  }

  if (peak <= FREQUENCY_NOISE_FLOOR) {
    return { start: 1, end: voiceLimit };
  }

  const activeFloor = Math.max(FREQUENCY_NOISE_FLOOR, peak * ACTIVE_BIN_PEAK_RATIO);
  let lastActiveBin = 1;
  for (let index = 1; index < voiceLimit; index += 1) {
    if ((data[index] ?? 0) >= activeFloor) {
      lastActiveBin = index;
    }
  }

  return { start: 1, end: Math.max(2, lastActiveBin + 1) };
}

function sampleFrequencyScale(
  data: Uint8Array,
  range: { start: number; end: number },
  index: number,
  total: number,
): number {
  if (data.length === 0 || total <= 0 || range.end <= range.start) {
    return MIN_BAR_SCALE;
  }

  const position = range.start + ((index + 0.5) / total) * (range.end - range.start);
  const lower = Math.min(range.end - 1, Math.max(range.start, Math.floor(position)));
  const upper = Math.min(range.end - 1, lower + 1);
  const fraction = Math.max(0, Math.min(1, position - lower));
  const rawLower = data[lower] ?? 0;
  const rawUpper = data[upper] ?? rawLower;
  const raw = rawLower + (rawUpper - rawLower) * fraction;
  const normalized = Math.max(0, (raw - FREQUENCY_NOISE_FLOOR) / (255 - FREQUENCY_NOISE_FLOOR));
  const shaped = Math.pow(normalized, 0.55);
  return MIN_BAR_SCALE + shaped * (1 - MIN_BAR_SCALE);
}

/**
 * Live wave band that monitors the microphone frequency spectrum while the user
 * dictates. Renders a row of bars whose heights track the audio input so the
 * composer chat box can be replaced with a responsive recording indicator.
 */
export function DictationWaveform({
  getFrequencyData,
  barCount = DEFAULT_BAR_COUNT,
  className,
  label = "Recording audio",
}: DictationWaveformProps) {
  const barRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const frameRef = useRef<number | null>(null);
  const getFrequencyDataRef = useRef(getFrequencyData);

  useEffect(() => {
    getFrequencyDataRef.current = getFrequencyData;
  }, [getFrequencyData]);

  const bars = useMemo(
    () => Array.from({ length: Math.max(1, barCount) }, (_, index) => index),
    [barCount],
  );

  useEffect(() => {
    const reduceMotion = prefersReducedMotion();
    const total = bars.length;
    let stopped = false;
    // Guards against environments where requestAnimationFrame invokes its
    // callback synchronously (e.g. some test mocks), which would otherwise
    // recurse without bound.
    let inFrame = false;

    const applyScale = (index: number, scale: number) => {
      const node = barRefs.current[index];
      if (node) {
        node.style.transform = `scaleY(${scale.toFixed(3)})`;
      }
    };

    const paint = () => {
      const data = getFrequencyDataRef.current();
      if (data && data.length > 0) {
        const range = getDisplayFrequencyRange(data);
        for (let index = 0; index < total; index += 1) {
          applyScale(index, sampleFrequencyScale(data, range, index, total));
        }
      } else {
        for (let index = 0; index < total; index += 1) {
          applyScale(index, MIN_BAR_SCALE);
        }
      }
    };

    const tick = () => {
      if (stopped || inFrame) return;
      inFrame = true;
      paint();
      if (!reduceMotion) {
        frameRef.current = window.requestAnimationFrame(tick);
      }
      inFrame = false;
    };

    tick();

    return () => {
      stopped = true;
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [bars]);

  return (
    <div
      className={cn("composer__waveform", className)}
      role="img"
      aria-label={label}
    >
      <div className="composer__waveform-bars" aria-hidden="true">
        {bars.map((index) => (
          <span
            key={index}
            ref={(node) => {
              barRefs.current[index] = node;
            }}
            className="composer__waveform-bar"
            style={{ transform: `scaleY(${MIN_BAR_SCALE})` }}
          />
        ))}
      </div>
    </div>
  );
}
