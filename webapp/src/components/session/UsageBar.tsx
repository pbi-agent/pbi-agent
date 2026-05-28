import {
  forwardRef,
  useCallback,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type FocusEvent,
  type MouseEvent,
} from "react";
import { createPortal } from "react-dom";
import type { UsagePayload } from "../../types";
import { cn } from "../../lib/utils";

function composeHandlers<E>(
  theirs: ((event: E) => void) | undefined,
  ours: (event: E) => void,
): (event: E) => void {
  return (event: E) => {
    theirs?.(event);
    ours(event);
  };
}

const SIZE = 22;
const STROKE = 3;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const TOOLTIP_GUTTER = 16;
const TOOLTIP_OFFSET = 12;

type TooltipPlacement = "top" | "bottom";

type TooltipPosition = {
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

type UsageBarOwnProps = {
  compactThreshold: number | null;
  usage: UsagePayload | null;
  /**
   * Renders the gauge as a clickable control (e.g. a dropdown trigger).
   * Hovering still surfaces the usage tooltip; the click is owned by the
   * parent so the same gauge can also open run details.
   */
  interactive?: boolean;
  /** Suppresses the hover tooltip, e.g. while an attached dropdown is open. */
  tooltipSuppressed?: boolean;
};

type UsageBarProps = UsageBarOwnProps &
  Omit<
    ButtonHTMLAttributes<HTMLButtonElement>,
    keyof UsageBarOwnProps | "type" | "role"
  >;

export const UsageBar = forwardRef<HTMLButtonElement, UsageBarProps>(function UsageBar(
  {
    compactThreshold,
    usage,
    interactive = false,
    tooltipSuppressed = false,
    className,
    onBlur,
    onFocus,
    onMouseEnter,
    onMouseLeave,
    ...buttonProps
  },
  forwardedRef,
) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const setTriggerRef = useCallback(
    (node: HTMLButtonElement | null) => {
      triggerRef.current = node;
      if (typeof forwardedRef === "function") {
        forwardedRef(node);
      } else if (forwardedRef) {
        forwardedRef.current = node;
      }
    },
    [forwardedRef],
  );
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
  const interactiveAriaLabel =
    hasUsage && threshold
      ? `Run history. Context usage ${percentLabel} (${usageLabel} of ${thresholdLabel} tokens).`
      : "Run history. Context window usage unavailable.";
  const showTooltip = tooltipOpen && !tooltipSuppressed;

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
    setTooltipPosition({ left, placement, top });
  }, []);

  useLayoutEffect(() => {
    if (!showTooltip) return;
    updateTooltipPosition();
    window.addEventListener("resize", updateTooltipPosition);
    window.addEventListener("scroll", updateTooltipPosition, true);
    return () => {
      window.removeEventListener("resize", updateTooltipPosition);
      window.removeEventListener("scroll", updateTooltipPosition, true);
    };
  }, [showTooltip, updateTooltipPosition]);

  // This tooltip is positioned locally instead of using the shared Radix
  // TooltipContent because Radix Popper only shifts on the placement's main
  // axis (`crossAxis: false`). The gauge can sit near both top and side
  // viewport edges, so we clamp both axes here to keep a real viewport gutter.
  const tooltip = showTooltip
    ? createPortal(
        <div
          ref={tooltipRef}
          id={tooltipId}
          role="tooltip"
          data-app-tooltip=""
          data-placement={tooltipPosition?.placement ?? "bottom"}
          className="context-gauge__tooltip-content"
          style={
            tooltipPosition
              ? {
                  left: `${tooltipPosition.left}px`,
                  top: `${tooltipPosition.top}px`,
                  visibility: "visible",
                }
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
        </div>,
        document.body,
      )
    : null;

  const semanticProps = interactive
    ? { "aria-label": interactiveAriaLabel }
    : {
        role: "progressbar" as const,
        "aria-valuemin": 0,
        "aria-valuemax": 100,
        "aria-valuenow": hasUsage && threshold ? Math.round(clampedPercent) : 0,
        "aria-valuetext": ariaValueText,
        "aria-label": "Context window usage",
      };

  return (
    <>
      <button
        ref={setTriggerRef}
        type="button"
        className={cn(
          `context-gauge context-gauge--${status}`,
          interactive && "context-gauge--interactive",
          className,
        )}
        {...semanticProps}
        aria-describedby={showTooltip ? tooltipId : undefined}
        {...buttonProps}
        onBlur={composeHandlers<FocusEvent<HTMLButtonElement>>(onBlur, () =>
          setTooltipOpen(false),
        )}
        onFocus={composeHandlers<FocusEvent<HTMLButtonElement>>(onFocus, () =>
          setTooltipOpen(true),
        )}
        onMouseEnter={composeHandlers<MouseEvent<HTMLButtonElement>>(onMouseEnter, () =>
          setTooltipOpen(true),
        )}
        onMouseLeave={composeHandlers<MouseEvent<HTMLButtonElement>>(onMouseLeave, () =>
          setTooltipOpen(false),
        )}
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
});
