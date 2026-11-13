import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "../../lib/utils";

interface DictationTimelineProps {
  /**
   * Returns the live byte frequency spectrum (0-255 per bin) of the recorded
   * microphone input, or `null`/empty when no data is available yet.
   */
  getFrequencyData: () => Uint8Array | null;
  className?: string;
  label?: string;
}

/** Enough 4 px steps to fill the widest composer; the overflow is clipped. */
const BAR_COUNT = 360;
const BAR_STEP_PX = 4;
const MIN_BAR_PX = 2;
const MAX_BAR_PX = 24;
/** One bar of history is added per interval. */
const SAMPLE_INTERVAL_MS = 60;
const NOISE_FLOOR = 10;
/** Speech sits in the lower part of the analyser's range. */
const VOICE_BIN_FRACTION = 0.45;
const BAR_HEIGHT_VAR = "--dictation-bar-height";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** Loudness of the voice band, from 0 (silence) to 1. */
export function voiceLevel(data: Uint8Array | null): number {
  if (!data || data.length === 0) return 0;
  const end = Math.max(1, Math.ceil(data.length * VOICE_BIN_FRACTION));
  // Skip the DC bin when there is anything else to read.
  const start = end > 1 ? 1 : 0;
  let sum = 0;
  let peak = 0;
  for (let index = start; index < end; index += 1) {
    const value = data[index] ?? 0;
    sum += value;
    peak = Math.max(peak, value);
  }
  // Blend the average with the peak so a single strong harmonic still shows.
  const blended = 0.6 * (sum / (end - start)) + 0.4 * peak;
  const normalized = Math.max(0, (blended - NOISE_FLOOR) / (255 - NOISE_FLOOR));
  return Math.min(1, Math.pow(normalized, 0.7));
}

export function formatElapsed(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function barHeightPx(level: number): number {
  return Math.round(MIN_BAR_PX + level * (MAX_BAR_PX - MIN_BAR_PX));
}

/**
 * Recording indicator that replaces the composer text while dictating: a live
 * dot, the elapsed time, and a loudness history that scrolls in from the right
 * and fades out on the left.
 */
export function DictationTimeline({
  getFrequencyData,
  className,
  label = "Recording audio",
}: DictationTimelineProps) {
  const rowRef = useRef<HTMLDivElement | null>(null);
  const barRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const getFrequencyDataRef = useRef(getFrequencyData);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    getFrequencyDataRef.current = getFrequencyData;
  }, [getFrequencyData]);

  const bars = useMemo(
    () => Array.from({ length: BAR_COUNT }, (_, index) => index),
    [],
  );

  useEffect(() => {
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const heights = new Int16Array(BAR_COUNT).fill(MIN_BAR_PX);
    const applied = new Int16Array(BAR_COUNT);
    const paintBars = () => {
      for (let index = 0; index < BAR_COUNT; index += 1) {
        const height = heights[index] ?? MIN_BAR_PX;
        if (applied[index] === height) continue;
        applied[index] = height;
        barRefs.current[index]?.style.setProperty(BAR_HEIGHT_VAR, `${height}px`);
      }
    };
    paintBars();
    if (prefersReducedMotion()) return;

    let frame: number | null = null;
    let stopped = false;
    let sampleStartedAt: number | null = null;
    let loudest = 0;
    // Some environments (test mocks) run requestAnimationFrame callbacks
    // synchronously; without this guard the loop would recurse without end.
    let inFrame = false;

    const tick = (now: number) => {
      if (stopped || inFrame) return;
      inFrame = true;
      loudest = Math.max(loudest, voiceLevel(getFrequencyDataRef.current()));
      sampleStartedAt ??= now;
      let progress = (now - sampleStartedAt) / SAMPLE_INTERVAL_MS;
      if (progress >= 1) {
        // Commit the loudest moment of the interval as the newest bar.
        heights.copyWithin(0, 1);
        heights[BAR_COUNT - 1] = barHeightPx(loudest);
        paintBars();
        loudest = 0;
        sampleStartedAt = now;
        progress = 0;
      }
      // The newest bar starts one step beyond the right edge and slides in.
      const offset = BAR_STEP_PX * (1 - progress);
      if (rowRef.current) {
        rowRef.current.style.transform = `translateX(${offset.toFixed(2)}px)`;
      }
      frame = window.requestAnimationFrame(tick);
      inFrame = false;
    };
    frame = window.requestAnimationFrame(tick);

    return () => {
      stopped = true;
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div
      className={cn("flex min-h-10 min-w-0 flex-1 items-center gap-3 px-3", className)}
      role="img"
      aria-label={label}
    >
      <span className="relative flex size-2 shrink-0">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-destructive/60 motion-reduce:animate-none" />
        <span className="relative inline-flex size-2 rounded-full bg-destructive" />
      </span>
      <span
        data-dictation-elapsed=""
        className="shrink-0 text-sm text-muted-foreground tabular-nums"
      >
        {formatElapsed(elapsedSeconds)}
      </span>
      <div className="relative h-7 min-w-0 flex-1 overflow-hidden mask-l-from-80%">
        <div
          ref={rowRef}
          className="absolute inset-y-0 right-0 flex items-center gap-0.5 will-change-transform"
        >
          {bars.map((index) => (
            <span
              key={index}
              ref={(node) => {
                barRefs.current[index] = node;
              }}
              data-dictation-bar=""
              className="h-(--dictation-bar-height) w-0.5 shrink-0 rounded-full bg-foreground/80"
            />
          ))}
        </div>
      </div>
    </div>
  );
}
