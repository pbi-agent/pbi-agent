import { useEffect, useState } from "react";
import type * as React from "react";

import { cn } from "../lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

type TruncatedTextProps = Omit<React.ComponentProps<"span">, "children"> & {
  children: string;
  tooltipSide?: "top" | "right" | "bottom" | "left";
  tooltipAlign?: "start" | "center" | "end";
  /**
   * Identity of the thing the text describes. When set, a text change under
   * the same identity (e.g. a generated title replacing a placeholder) fades
   * the new text in; a change of identity swaps the text without animation.
   */
  transitionKey?: string;
};

function isClipped(element: HTMLElement): boolean {
  if (element.scrollWidth > element.clientWidth) return true;
  // scrollWidth/clientWidth are rounded to integers, so an overflow of less
  // than a pixel still draws an ellipsis; compare fractional widths as well.
  const range = document.createRange();
  range.selectNodeContents(element);
  if (typeof range.getBoundingClientRect !== "function") return false;
  const style = window.getComputedStyle(element);
  const contentWidth =
    element.getBoundingClientRect().width
    - (Number.parseFloat(style.paddingLeft) || 0)
    - (Number.parseFloat(style.paddingRight) || 0);
  return range.getBoundingClientRect().width - contentWidth > 0.05;
}

/** Single-line text that shows its full content in a tooltip only when clipped. */
export function TruncatedText({
  children,
  className,
  tooltipSide = "bottom",
  tooltipAlign = "center",
  transitionKey,
  ...props
}: TruncatedTextProps) {
  const [open, setOpen] = useState(false);
  const [element, setElement] = useState<HTMLSpanElement | null>(null);
  const [shown, setShown] = useState({ transitionKey, text: children, revision: 0 });

  if (shown.transitionKey !== transitionKey || shown.text !== children) {
    const sameSubject =
      transitionKey !== undefined && shown.transitionKey === transitionKey;
    setShown({
      transitionKey,
      text: children,
      revision: sameSubject ? shown.revision + 1 : 0,
    });
    // The open tooltip described the previous text; let the next hover or
    // focus decide again whether the new text is clipped.
    setOpen(false);
  }

  // The text itself is not focusable: mirror hover for keyboard users by
  // following focus on the enclosing link or button.
  useEffect(() => {
    const focusTarget = element?.closest<HTMLElement>("a, button");
    if (!element || !focusTarget) return;
    const handleFocus = () => {
      if (focusTarget.matches(":focus-visible")) setOpen(isClipped(element));
    };
    const handleBlur = () => setOpen(false);
    focusTarget.addEventListener("focus", handleFocus);
    focusTarget.addEventListener("blur", handleBlur);
    return () => {
      focusTarget.removeEventListener("focus", handleFocus);
      focusTarget.removeEventListener("blur", handleBlur);
    };
  }, [element]);

  return (
    <Tooltip
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen && element !== null && isClipped(element));
      }}
    >
      <TooltipTrigger asChild>
        <span
          // Remounting on each revision replays the enter animation.
          key={shown.revision}
          ref={setElement}
          data-text-transition={shown.revision > 0 ? "" : undefined}
          className={cn(
            "min-w-0 truncate",
            shown.revision > 0 &&
              "animate-in duration-500 ease-out fade-in-0 blur-in-2 slide-in-from-bottom-1 motion-reduce:animate-none",
            className,
          )}
          {...props}
        >
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent side={tooltipSide} align={tooltipAlign} className="wrap-anywhere">
        {children}
      </TooltipContent>
    </Tooltip>
  );
}
