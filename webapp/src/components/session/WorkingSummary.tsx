import { useState, type CSSProperties } from "react";

export type CountSummaryItem = {
  key: string;
  count: number;
  singular: string;
  plural: string;
};

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function summaryItemLabel(item: CountSummaryItem) {
  return pluralize(item.count, item.singular, item.plural);
}

export function summarizeCountItems(items: CountSummaryItem[]) {
  return items
    .filter((item) => item.count > 0)
    .map(summaryItemLabel)
    .join(", ");
}

export function formatWorkingDuration(seconds: number | null | undefined): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) {
    return null;
  }
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

export function workingSummaryText(
  items: CountSummaryItem[],
  durationSeconds?: number | null,
): string {
  return [
    summarizeCountItems(items),
    formatWorkingDuration(durationSeconds),
  ].filter(Boolean).join(" · ");
}

const ANIMATED_NUMBER_TRACK = Array.from({ length: 30 }, (_, index) => index % 10);

function normalizeDigit(value: number) {
  return ((value % 10) + 10) % 10;
}

function digitSpin(from: number, to: number, direction: 1 | -1) {
  if (from === to) return 0;
  if (direction > 0) return (to - from + 10) % 10;
  return -((from - to + 10) % 10);
}

function AnimatedNumberDigit({ value, direction }: { value: number; direction: 1 | -1 }) {
  const [state, setState] = useState({
    step: value + 10,
    animating: false,
    lastValue: value,
    direction,
  });

  if (state.lastValue !== value || state.direction !== direction) {
    const delta = digitSpin(state.lastValue, value, direction);
    if (delta === 0) {
      setState({ step: value + 10, animating: false, lastValue: value, direction });
    } else {
      setState({
        step: state.step + delta,
        animating: true,
        lastValue: value,
        direction,
      });
    }
  }

  return (
    <span data-slot="animated-number-digit">
      <span
        data-slot="animated-number-strip"
        data-animating={state.animating ? "true" : "false"}
        onTransitionEnd={() => {
          setState((current) => ({
            ...current,
            animating: false,
            step: normalizeDigit(current.step) + 10,
          }));
        }}
        style={{
          "--animated-number-offset": state.step,
        } as CSSProperties}
      >
        {ANIMATED_NUMBER_TRACK.map((digit, index) => (
          <span key={`${digit}-${index}`} data-slot="animated-number-cell" data-digit={digit} />
        ))}
      </span>
    </span>
  );
}

function AnimatedNumber({ value }: { value: number }) {
  const target = Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
  const [state, setState] = useState({ displayValue: target, direction: 1 as 1 | -1 });

  if (state.displayValue !== target) {
    setState({
      displayValue: target,
      direction: target > state.displayValue ? 1 : -1,
    });
  }

  const label = state.displayValue.toString();
  const digits = Array.from(label, (char) => {
    const digit = Number.parseInt(char, 10);
    return Number.isNaN(digit) ? 0 : digit;
  }).reverse();

  return (
    <span data-component="animated-number" className="animated-count-number">
      <span className="animated-count-number__text">{label}</span>
      <span
        data-slot="animated-number-value"
        aria-hidden="true"
        style={{
          "--animated-number-width": `${digits.length}ch`,
        } as CSSProperties}
      >
        {digits.map((digit, index) => (
          <AnimatedNumberDigit key={index} value={digit} direction={state.direction} />
        ))}
      </span>
    </span>
  );
}

function ToolCountSummary({ items }: { items: CountSummaryItem[] }) {
  if (items.length === 0) return null;

  return (
    <span data-component="tool-count-summary">
      {items.map((item, index) => (
        <span key={item.key} data-slot="tool-count-summary-item">
          {index > 0 ? <span data-slot="tool-count-summary-prefix">, </span> : null}
          <span data-component="tool-count-label">
            <AnimatedNumber value={item.count} />
            <span data-slot="tool-count-label-space"> </span>
            <span data-slot="tool-count-label-word">
              {item.count === 1 ? item.singular : item.plural}
            </span>
          </span>
        </span>
      ))}
    </span>
  );
}

export function WorkingSummary({
  items,
  durationSeconds,
  placeholder,
  className,
}: {
  items: CountSummaryItem[];
  durationSeconds?: number | null;
  placeholder?: string | null;
  className?: string;
}) {
  if (placeholder) {
    return (
      <span data-component="working-summary" data-placeholder="true" className={className} aria-hidden="true">
        {placeholder}
      </span>
    );
  }

  const visible = items.filter((item) => item.count > 0);
  const durationLabel = formatWorkingDuration(durationSeconds);
  if (visible.length === 0 && !durationLabel) return null;

  return (
    <span data-component="working-summary" className={className}>
      <ToolCountSummary items={visible} />
      {visible.length > 0 && durationLabel ? (
        <span data-slot="working-summary-separator"> · </span>
      ) : null}
      {durationLabel ? (
        <span data-slot="working-summary-duration">{durationLabel}</span>
      ) : null}
    </span>
  );
}