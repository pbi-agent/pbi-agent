import { useCallback, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CSSProperties } from "react";
import type { UsagePayload } from "../../types";

const SIZE = 22;
const STROKE = 3;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const TOOLTIP_GUTTER = 16;
const TOOLTIP_OFFSET = 12;
const TOOLTIP_ARROW_SIZE = 10;
const TOOLTIP_ARROW_GUTTER = 12;

type TooltipPlacement = "top" | "bottom";

type TooltipPosition = {
  arrowLeft: number;
  left: number;
  placement: TooltipPlacement;
  top: number;
};

function formatTokens(n: number): string {
  return n.toLocaleString();
}

function contextStatus(usagePercent: number): "normal" | "warning" | "critical" {
  if (usagePercent >= 100) return "critical";
  if (usagePercent >= 80) return "warning";
  return "normal";
}

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

export function UsageBar({
  compactThreshold,
  usage,
}: {
  compactThreshold: number | null;
  usage: UsagePayload | null;
}) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const tooltipId = useId();
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState<TooltipPosition | null>(null);
  const threshold = compactThreshold && compactThreshold > 0 ? compactThreshold : null;
  const contextTokens = usage?.context_tokens ?? null;
  const hasUsage = typeof contextTokens === "number" && contextTokens > 0;
  const usagePercent = hasUsage && threshold ? (contextTokens / threshold) * 100 : 0;
  const clampedPercent = Math.min(Math.max(usagePercent, 0), 100);
  const status = contextStatus(usagePercent);
  const progressOffset = CIRCUMFERENCE * (1 - clampedPercent / 100);

  const usageLabel = hasUsage ? formatTokens(contextTokens) : "—";
  const thresholdLabel = threshold ? formatTokens(threshold) : "—";
  const percentLabel =
    hasUsage && threshold ? `${usagePercent.toFixed(1)}%` : null;
  const ariaValueText =
    hasUsage && threshold
      ? `${usageLabel} of ${thresholdLabel} context tokens used`
      : "Context window usage unavailable";

  const updateTooltipPosition = useCallback(() => {
    const trigger = triggerRef.current;
    const tooltip = tooltipRef.current;
    if (!trigger || !tooltip || typeof window === "undefined") return;

    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    const triggerCenterX = triggerRect.left + triggerRect.width / 2;
    const preferredTop = triggerRect.bottom + TOOLTIP_OFFSET;
    const topSpace = triggerRect.top - TOOLTIP_OFFSET - TOOLTIP_GUTTER;
    const bottomSpace = viewportHeight - preferredTop - TOOLTIP_GUTTER;
    const placement: TooltipPlacement =
      bottomSpace >= tooltipRect.height || bottomSpace >= topSpace ? "bottom" : "top";
    const unclampedTop = placement === "bottom"
      ? preferredTop
      : triggerRect.top - TOOLTIP_OFFSET - tooltipRect.height;
    const top = clamp(
      unclampedTop,
      TOOLTIP_GUTTER,
      viewportHeight - tooltipRect.height - TOOLTIP_GUTTER,
    );
    const unclampedLeft = triggerCenterX - tooltipRect.width / 2;
    const left = clamp(
      unclampedLeft,
      TOOLTIP_GUTTER,
      viewportWidth - tooltipRect.width - TOOLTIP_GUTTER,
    );
    const arrowLeft = clamp(
      triggerCenterX - left - TOOLTIP_ARROW_SIZE / 2,
      TOOLTIP_ARROW_GUTTER,
      tooltipRect.width - TOOLTIP_ARROW_SIZE - TOOLTIP_ARROW_GUTTER,
    );

    setTooltipPosition({ arrowLeft, left, placement, top });
  }, []);

  useLayoutEffect(() => {
    if (!tooltipOpen) return;
    updateTooltipPosition();
    window.addEventListener("resize", updateTooltipPosition);
    window.addEventListener("scroll", updateTooltipPosition, true);
    return () => {
      window.removeEventListener("resize", updateTooltipPosition);
      window.removeEventListener("scroll", updateTooltipPosition, true);
    };
  }, [tooltipOpen, updateTooltipPosition]);

  // This tooltip is positioned locally instead of using the shared Radix
  // TooltipContent because Radix Popper only shifts on the placement's main
  // axis (`crossAxis: false`). The gauge can sit near both top and side
  // viewport edges, so we clamp both axes here to keep a real viewport gutter.
  const tooltip = tooltipOpen
    ? createPortal(
        <div
          ref={tooltipRef}
          id={tooltipId}
          role="tooltip"
          data-placement={tooltipPosition?.placement ?? "bottom"}
          className="context-gauge__tooltip-content"
          style={
            tooltipPosition
              ? {
                  "--context-gauge-arrow-left": `${tooltipPosition.arrowLeft}px`,
                  left: `${tooltipPosition.left}px`,
                  top: `${tooltipPosition.top}px`,
                  visibility: "visible",
                } as CSSProperties
              : undefined
          }
        >
          <div className="context-gauge__tooltip">
            <div className="context-gauge__tooltip-row">
              <span className="context-gauge__tooltip-value">{usageLabel}</span>
              <span className="context-gauge__tooltip-sep">/</span>
              <span className="context-gauge__tooltip-value">
                {thresholdLabel}
              </span>
              <span className="context-gauge__tooltip-unit">tokens</span>
            </div>
            {percentLabel ? (
              <div className="context-gauge__tooltip-meta">
                {percentLabel} of compaction threshold
              </div>
            ) : (
              <div className="context-gauge__tooltip-meta">
                No response usage yet
              </div>
            )}
          </div>
          <span className="context-gauge__tooltip-arrow" aria-hidden="true" />
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`context-gauge context-gauge--${status}`}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={hasUsage && threshold ? Math.round(clampedPercent) : 0}
        aria-valuetext={ariaValueText}
        aria-label="Context window usage"
        aria-describedby={tooltipOpen ? tooltipId : undefined}
        onBlur={() => setTooltipOpen(false)}
        onFocus={() => setTooltipOpen(true)}
        onMouseEnter={() => setTooltipOpen(true)}
        onMouseLeave={() => setTooltipOpen(false)}
      >
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="context-gauge__svg"
          aria-hidden="true"
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            className="context-gauge__track"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={progressOffset}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            className="context-gauge__indicator"
          />
        </svg>
      </button>
      {tooltip}
    </>
  );
}
