import { useEffect, useRef, useState } from "react";
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
};

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
export function CodeBlock({ value, language, path, className }: CodeBlockProps) {
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
  const wrapperClassName = cn("tool-result__code", className);

  if (highlightedHtml) {
    return (
      <div
        className={wrapperClassName}
        data-language={resolvedLanguage}
        data-highlighted="true"
        dangerouslySetInnerHTML={{ __html: highlightedHtml }}
      />
    );
  }

  return (
    <pre
      className={cn("tool-result__pre", className)}
      data-language={resolvedLanguage}
      data-highlighted="false"
    >
      {value}
    </pre>
  );
}
