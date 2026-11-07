import { useCallback, useEffect, useRef, useState, type JSX, type KeyboardEvent, type RefObject, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { MessageSquareQuoteIcon, XIcon } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { cn } from "@/lib/utils";

const ASSISTANT_CONTENT_SELECTOR = "[data-timeline-entry=\"assistant\"] [data-timeline-content]";
const VIEWPORT_GUTTER = 8;
const SHORTCUT_GAP = 14;
const COMPOSE_WIDTH = 360;

type Anchor = { top: number; bottom: number; left: number };

type PopoverState =
  | { mode: "shortcut"; quote: string; anchor: Anchor }
  | { mode: "compose"; quote: string; anchor: Anchor };

function closestElement(node: Node | null): Element | null {
  if (!node) return null;
  return node instanceof Element ? node : node.parentElement;
}

function assistantSelection(container: HTMLElement | null): { quote: string; anchor: Anchor } | null {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const quote = selection.toString().trim();
  if (!quote) return null;
  const startContent = closestElement(selection.anchorNode)?.closest(ASSISTANT_CONTENT_SELECTOR);
  const endContent = closestElement(selection.focusNode)?.closest(ASSISTANT_CONTENT_SELECTOR);
  if (!startContent || startContent !== endContent) return null;
  if (container && !container.contains(startContent)) return null;
  const rect = selection.getRangeAt(0).getBoundingClientRect();
  return {
    quote,
    anchor: { top: rect.top, bottom: rect.bottom, left: rect.left + rect.width / 2 },
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, Math.max(min, max)));
}

export function ReplySelectionPopover({
  containerRef,
  onAddReply,
}: {
  containerRef?: RefObject<HTMLElement | null>;
  onAddReply: (quote: string, comment: string) => void;
}): JSX.Element | null {
  const [state, setState] = useState<PopoverState | null>(null);
  const [comment, setComment] = useState("");
  const [size, setSize] = useState({ width: 0, height: 0 });
  const popoverRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<PopoverState | null>(null);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const close = useCallback(() => {
    setState(null);
    setComment("");
  }, []);

  useEffect(() => {
    const handlePointerUp = (event: MouseEvent) => {
      if (popoverRef.current?.contains(event.target as Node)) return;
      if (stateRef.current?.mode === "compose") return;
      // Wait for the browser to finalize the selection.
      window.setTimeout(() => {
        const next = assistantSelection(containerRef?.current ?? null);
        setState(next ? { mode: "shortcut", ...next } : null);
      }, 0);
    };
    const handlePointerDown = (event: MouseEvent) => {
      if (popoverRef.current?.contains(event.target as Node)) return;
      if (stateRef.current) close();
    };
    const handleSelectionChange = () => {
      if (stateRef.current?.mode !== "shortcut") return;
      if (!assistantSelection(containerRef?.current ?? null)) setState(null);
    };
    const handleScroll = () => {
      if (stateRef.current?.mode === "shortcut") setState(null);
    };
    document.addEventListener("mouseup", handlePointerUp);
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("selectionchange", handleSelectionChange);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mouseup", handlePointerUp);
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("selectionchange", handleSelectionChange);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [close, containerRef]);

  useEffect(() => {
    const element = popoverRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    setSize((current) =>
      current.width === rect.width && current.height === rect.height
        ? current
        : { width: rect.width, height: rect.height },
    );
  }, [state, comment]);

  if (!state) return null;

  const submit = () => {
    const trimmed = comment.trim();
    if (!trimmed) return;
    onAddReply(state.quote, trimmed);
    window.getSelection()?.removeAllRanges();
    close();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  // Clamp on both axes so the floating UI keeps a gutter from every viewport edge.
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const width = size.width || (state.mode === "compose" ? COMPOSE_WIDTH : 80);
  const height = size.height || 32;
  const left = clamp(state.anchor.left - width / 2, VIEWPORT_GUTTER, viewportWidth - width - VIEWPORT_GUTTER);
  const above = state.anchor.top - height - SHORTCUT_GAP;
  const top = clamp(
    above >= VIEWPORT_GUTTER ? above : state.anchor.bottom + SHORTCUT_GAP,
    VIEWPORT_GUTTER,
    viewportHeight - height - VIEWPORT_GUTTER,
  );

  return createPortal(
    <div
      ref={popoverRef}
      className={cn(
        "fixed top-(--reply-top) left-(--reply-left) z-50 isolate rounded-md border border-border bg-popover text-popover-foreground",
        state.mode === "compose" ? "w-sm max-w-full p-3 shadow-md" : "p-0.5 shadow-lg",
      )}
      data-reply-selection={state.mode}
      style={{ "--reply-top": `${top}px`, "--reply-left": `${left}px` } as CSSProperties}
      role={state.mode === "compose" ? "dialog" : undefined}
      aria-label={state.mode === "compose" ? "Reply to selection" : undefined}
    >
      {state.mode === "shortcut" ? (
        <Button
          type="button"
          size="sm"
          variant="default"
         
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setState({ ...state, mode: "compose" })}
        >
          <MessageSquareQuoteIcon data-icon="inline-start" aria-hidden="true" />
          Reply
        </Button>
      ) : (
        <div className="flex flex-col gap-2">
          <blockquote className="m-0 line-clamp-4 border-l-2 border-border pl-2 text-xs wrap-anywhere whitespace-pre-wrap text-muted-foreground">{state.quote}</blockquote>
          <Textarea
            autoFocus
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Add your comment…"
            aria-label="Reply comment"
            className="max-h-40 min-h-16"
            rows={2}
          />
          <div className="flex items-center justify-end gap-1">
            <span className="mr-auto min-w-0 flex-1 text-xs text-muted-foreground">Enter to add · Shift+Enter for newline</span>
            <Button type="button" size="sm" variant="ghost" onClick={close}>
              <XIcon data-icon="inline-start" aria-hidden="true" />
              Cancel
            </Button>
            <Button type="button" size="sm" onClick={submit} disabled={!comment.trim()}>
              Add to message
            </Button>
          </div>
        </div>
      )}
    </div>,
    document.body,
  );
}
