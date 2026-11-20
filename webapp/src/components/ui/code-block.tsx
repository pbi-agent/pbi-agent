import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { languageForPath } from "@/lib/code-language";
import { highlightCode } from "@/lib/shiki-highlighter";

type CodeBlockProps = {
  value: string;
  /** Explicit Shiki language id. Wins over `path`-derived detection. */
  language?: string;
  /** Workspace path used to derive a language when `language` is omitted. */
  path?: string;
  className?: string;
  /** `tool` (default): wrapped, compact. `markdown`: unwrapped, taller fenced block. */
  variant?: "tool" | "markdown";
  /**
   * 1-based inclusive line range to highlight and scroll into view. Pass a new
   * object to scroll again to the same range.
   */
  highlightLines?: { start: number; end: number } | null;
};

const LINE_HIGHLIGHT_ATTRIBUTE = "data-line-highlight";
const LINE_HIGHLIGHT_CLASSES =
  "[&_[data-line-highlight]]:inline-block [&_[data-line-highlight]]:min-w-full [&_[data-line-highlight]]:align-top [&_[data-line-highlight]]:bg-primary/15";

const SHIKI_CLASSES =
  "[&_.shiki]:m-0 [&_.shiki]:bg-transparent! [&_.shiki]:text-(--shiki-light,var(--muted-foreground)) [&_.shiki_span]:text-(--shiki-light,inherit) dark:[&_.shiki]:text-(--shiki-dark,var(--muted-foreground)) dark:[&_.shiki_span]:text-(--shiki-dark,inherit)";

const VARIANT_CLASSES = {
  tool: {
    frame: "max-h-[min(36vh,360px)]",
    text: "p-3 whitespace-pre-wrap break-words",
    shiki: "[&_.shiki]:p-3 [&_.shiki]:whitespace-pre-wrap [&_.shiki]:break-words",
  },
  markdown: {
    frame: "max-h-[min(52vh,560px)]",
    text: "p-4 whitespace-pre",
    shiki: "[&_.shiki]:p-4 [&_.shiki]:whitespace-pre",
  },
} as const;

type HighlightState = {
  key: string;
  html: string;
};

/**
 * Renders a code snippet inside a `<pre>` block. When the snippet's language is
 * known and Shiki successfully highlights the code, the plain-text rendering is
 * replaced with Shiki's syntax-highlighted markup. Until then (or on any
 * failure), the plain text is shown so the component is always meaningful and
 * SSR/test friendly.
 *
 * The current Shiki HTML is keyed by the (language, value) pair so stale
 * results from a previous render are ignored without needing to reset state
 * synchronously inside the effect.
 */
export function CodeBlock({
  value,
  language,
  path,
  className,
  variant = "tool",
  highlightLines = null,
}: CodeBlockProps) {
  const resolvedLanguage = language ?? languageForPath(path);
  const currentKey = resolvedLanguage ? `${resolvedLanguage}::${value}` : null;

  const [state, setState] = useState<HighlightState | null>(null);
  const lastJobRef = useRef(0);

  useEffect(() => {
    if (!currentKey || !resolvedLanguage || !value) {
      return;
    }
    const jobId = ++lastJobRef.current;
    let cancelled = false;
    void highlightCode(value, resolvedLanguage).then((html) => {
      if (cancelled || jobId !== lastJobRef.current || !html) return;
      setState({ key: currentKey, html });
    });
    return () => {
      cancelled = true;
    };
  }, [currentKey, resolvedLanguage, value]);

  const highlightedHtml = state && state.key === currentKey ? state.html : null;
  const [container, setContainer] = useState<HTMLElement | null>(null);

  // Shiki renders one `span.line` per source line; the plain fallback mirrors
  // that when a range is requested. Re-run after Shiki swaps in its markup.
  useLayoutEffect(() => {
    if (!container) return;
    const lines = container.querySelectorAll<HTMLElement>(".line");
    lines.forEach((line, index) => {
      const lineNumber = index + 1;
      line.toggleAttribute(
        LINE_HIGHLIGHT_ATTRIBUTE,
        highlightLines !== null && lineNumber >= highlightLines.start && lineNumber <= highlightLines.end,
      );
    });
    if (highlightLines === null || lines.length === 0) return;
    lines[Math.min(highlightLines.start, lines.length) - 1]
      .scrollIntoView?.({ block: "center", inline: "nearest" });
  }, [container, highlightLines, highlightedHtml]);
  const styles = VARIANT_CLASSES[variant];
  const baseClassName = cn(
    "m-0 overflow-auto font-mono text-xs leading-relaxed",
    styles.frame,
  );
  const wrapperClassName = cn(baseClassName, SHIKI_CLASSES, styles.shiki, LINE_HIGHLIGHT_CLASSES, className);

  if (highlightedHtml) {
    return (
      <div
        ref={setContainer}
        className={wrapperClassName}
        data-language={resolvedLanguage}
        data-highlighted="true"
        data-code-block="highlighted"
        dangerouslySetInnerHTML={{ __html: highlightedHtml }}
      />
    );
  }

  return (
    <pre
      ref={setContainer}
      className={cn(baseClassName, "text-muted-foreground", styles.text, LINE_HIGHLIGHT_CLASSES, className)}
      data-language={resolvedLanguage}
      data-highlighted="false"
      data-code-block="plain"
    >
      {highlightLines
        ? value.split("\n").map((line, index, all) => (
          <Fragment key={index}>
            <span className="line">{line}</span>
            {index < all.length - 1 ? "\n" : null}
          </Fragment>
        ))
        : value}
    </pre>
  );
}
