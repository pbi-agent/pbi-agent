import {
  Children,
  createContext,
  isValidElement,
  useContext,
  type ReactElement,
  type ReactNode,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CodeBlock } from "@/components/ui/code-block";
import { cn } from "@/lib/utils";
import { CopyShortcut } from "./CopyShortcut";

const CopyableSnippetContext = createContext(false);

type ElementWithChildren = ReactElement<{ children?: ReactNode }>;
type CodeElement = ReactElement<{ className?: string; children?: ReactNode }>;

function isElementWithChildren(value: ReactNode): value is ElementWithChildren {
  return isValidElement<{ children?: ReactNode }>(value);
}

/** Intrinsic tag of a rendered markdown node, including overridden components. */
function tagOf(element: ReactElement): string | undefined {
  if (typeof element.type === "string") {
    return element.type;
  }
  const node = (element.props as { node?: { tagName?: unknown } }).node;
  return typeof node?.tagName === "string" ? node.tagName : undefined;
}

function reactNodeToText(value: ReactNode): string {
  if (value === null || value === undefined || typeof value === "boolean") {
    return "";
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return (value as ReactNode[]).map((child) => reactNodeToText(child)).join("");
  }
  if (isElementWithChildren(value)) {
    return reactNodeToText(value.props.children);
  }
  return "";
}

function stripSingleTrailingNewline(value: string): string {
  return value.endsWith("\n") ? value.slice(0, -1) : value;
}

function codeElementFromPreChildren(children: ReactNode): CodeElement | undefined {
  let codeElement: CodeElement | undefined;
  Children.forEach(children, (child) => {
    if (codeElement || !isValidElement<{ className?: string; children?: ReactNode }>(child)) {
      return;
    }
    if (tagOf(child) === "code") {
      codeElement = child;
    }
  });
  return codeElement;
}

function languageFromCodeClass(className: string | undefined): string | undefined {
  if (!className) {
    return undefined;
  }
  for (const token of className.split(/\s+/)) {
    const match = /^(?:language|lang)-(.+)$/.exec(token);
    const language = match?.[1]?.trim().toLowerCase();
    if (language) {
      return language;
    }
  }
  return undefined;
}

function codeFenceFromPreChildren(children: ReactNode): {
  language?: string;
  text: string;
} {
  const codeElement = codeElementFromPreChildren(children);
  return {
    language: languageFromCodeClass(codeElement?.props.className),
    text: stripSingleTrailingNewline(
      reactNodeToText(codeElement?.props.children ?? children),
    ),
  };
}

function normalizeTableCell(value: ReactNode): string {
  return reactNodeToText(value).replace(/[\t\n\r ]+/g, " ").trim();
}

function collectTableCells(children: ReactNode): ReactNode[] {
  const cells: ReactNode[] = [];

  function visit(value: ReactNode): void {
    Children.forEach(value, (child) => {
      if (!isElementWithChildren(child)) {
        return;
      }
      if (tagOf(child) === "th" || tagOf(child) === "td") {
        cells.push(child.props.children);
        return;
      }
      visit(child.props.children);
    });
  }

  visit(children);
  return cells;
}

function collectTableRows(children: ReactNode): ReactNode[][] {
  const rows: ReactNode[][] = [];

  function visit(value: ReactNode): void {
    Children.forEach(value, (child) => {
      if (!isElementWithChildren(child)) {
        return;
      }
      if (tagOf(child) === "tr") {
        const cells = collectTableCells(child.props.children);
        if (cells.length > 0) {
          rows.push(cells);
        }
        return;
      }
      visit(child.props.children);
    });
  }

  visit(children);
  return rows;
}

function tableChildrenToTsv(children: ReactNode): string {
  const rows = collectTableRows(children);
  if (rows.length === 0) {
    return reactNodeToText(children).trim();
  }
  return rows
    .map((row) => row.map((cell) => normalizeTableCell(cell)).join("\t"))
    .join("\n");
}

function collectListItems(children: ReactNode): ReactNode[] {
  const items: ReactNode[] = [];

  function visit(value: ReactNode): void {
    Children.forEach(value, (child) => {
      if (!isElementWithChildren(child)) {
        return;
      }
      if (tagOf(child) === "li") {
        items.push(child.props.children);
        return;
      }
      visit(child.props.children);
    });
  }

  visit(children);
  return items;
}

function listChildrenToText(children: ReactNode, ordered: boolean): string {
  const items = collectListItems(children);
  if (items.length === 0) {
    return reactNodeToText(children).trim();
  }
  return items
    .map((item, index) => {
      const marker = ordered ? `${index + 1}.` : "-";
      return `${marker} ${reactNodeToText(item).trim()}`.trimEnd();
    })
    .join("\n");
}

type SnippetKind = "code" | "table" | "blockquote" | "list";

const blockquoteClassName =
  "my-3 rounded-r-sm border-l-4 border-primary/40 bg-muted px-4 py-2 text-muted-foreground";
const tableClassName = "my-3 min-w-full border-collapse text-xs";

function CopyableSnippet({
  children,
  kind,
  text,
}: {
  children: ReactNode;
  kind: SnippetKind;
  text: string;
}) {
  const insideCopyableSnippet = useContext(CopyableSnippetContext);
  if (insideCopyableSnippet || text.trim().length === 0) {
    return <>{children}</>;
  }

  return (
    <div
      className={cn(
        "group/snippet relative *:my-0",
        kind === "list" ? "mt-2 mb-3" : "my-3",
      )}
      data-markdown-copyable-snippet={kind}
    >
      <div className="pointer-events-none absolute top-2 right-2 z-10 flex opacity-0 transition-opacity group-focus-within/snippet:pointer-events-auto group-focus-within/snippet:opacity-100 group-hover/snippet:pointer-events-auto group-hover/snippet:opacity-100">
        <CopyShortcut text={text} ariaLabel="Copy snippet" />
      </div>
      <CopyableSnippetContext.Provider value>
        {children}
      </CopyableSnippetContext.Provider>
    </div>
  );
}

function MarkdownCodeSnippet({
  language,
  text,
}: {
  language?: string;
  text: string;
}) {
  const languageLabel = language ?? "text";
  return (
    <CopyableSnippet kind="code" text={text}>
      <div
        className="overflow-hidden rounded-md border border-border bg-muted"
        data-markdown-code-snippet
        data-language={languageLabel}
      >
        <div className="flex min-h-8 items-center border-b border-border py-2 pr-10 pl-3">
          <span className="font-mono text-xs text-muted-foreground" data-markdown-code-language>{languageLabel}</span>
        </div>
        <CodeBlock value={text} language={language} variant="markdown" />
      </div>
    </CopyableSnippet>
  );
}

const baseMarkdownComponents: Components = {
  p({ children }) {
    return <p className="mb-3 leading-relaxed last:mb-0">{children}</p>;
  },
  h1({ children }) {
    return <h1 className="mt-4 mb-2 text-xl font-semibold first:mt-0">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="mt-4 mb-2 text-lg font-semibold first:mt-0">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="mt-4 mb-2 text-base font-semibold first:mt-0">{children}</h3>;
  },
  h4({ children }) {
    return <h4 className="mt-4 mb-2 text-sm font-semibold first:mt-0">{children}</h4>;
  },
  a({ children, href, title }) {
    return (
      <a
        href={href}
        title={title}
        className="text-primary underline underline-offset-2 transition-colors hover:text-primary/80"
      >
        {children}
      </a>
    );
  },
  ul({ children }) {
    return <ul className="mt-2 mb-3 list-disc pl-5">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="mt-2 mb-3 list-decimal pl-5">{children}</ol>;
  },
  li({ children }) {
    return <li className="mb-1 leading-relaxed last:mb-0">{children}</li>;
  },
  blockquote({ children }) {
    return <blockquote className={blockquoteClassName}>{children}</blockquote>;
  },
  code({ children, className }) {
    // Fenced blocks keep their language class; `pre` renders their text itself.
    if (className) {
      return <code className={className}>{children}</code>;
    }
    return (
      <code className="rounded-sm border border-border bg-muted px-1 py-0.5 font-mono text-xs text-primary">
        {children}
      </code>
    );
  },
  pre({ children }) {
    const { text } = codeFenceFromPreChildren(children);
    return (
      <pre className="my-3 overflow-x-auto rounded-md border border-border bg-muted p-4 font-mono text-xs leading-relaxed">
        <code>{text}</code>
      </pre>
    );
  },
  table({ children }) {
    return <table className={tableClassName}>{children}</table>;
  },
  th({ children }) {
    return (
      <th className="border border-border bg-muted px-3 py-2 text-left align-top font-semibold whitespace-nowrap">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="border border-border px-3 py-2 text-left align-top whitespace-nowrap text-muted-foreground">
        {children}
      </td>
    );
  },
  tr({ children }) {
    return <tr className="even:bg-muted/40">{children}</tr>;
  },
  hr() {
    return <hr className="my-4 border-0 border-t border-border" />;
  },
  strong({ children }) {
    return <strong className="font-semibold">{children}</strong>;
  },
  em({ children }) {
    return <em className="text-muted-foreground italic">{children}</em>;
  },
};

const copyableMarkdownComponents: Components = {
  ...baseMarkdownComponents,
  pre({ children }) {
    const { language, text } = codeFenceFromPreChildren(children);
    return <MarkdownCodeSnippet language={language} text={text} />;
  },
  table({ children }) {
    return (
      <CopyableSnippet kind="table" text={tableChildrenToTsv(children)}>
        <table className={tableClassName}>{children}</table>
      </CopyableSnippet>
    );
  },
  blockquote({ children }) {
    return (
      <CopyableSnippet kind="blockquote" text={reactNodeToText(children).trim()}>
        <blockquote className={blockquoteClassName}>{children}</blockquote>
      </CopyableSnippet>
    );
  },
  ul({ children }) {
    return (
      <CopyableSnippet kind="list" text={listChildrenToText(children, false)}>
        <ul className="mt-2 mb-3 list-disc pl-5">{children}</ul>
      </CopyableSnippet>
    );
  },
  ol({ children }) {
    return (
      <CopyableSnippet kind="list" text={listChildrenToText(children, true)}>
        <ol className="mt-2 mb-3 list-decimal pl-5">{children}</ol>
      </CopyableSnippet>
    );
  },
};

export function MarkdownContent({
  content,
  copyable = false,
}: {
  content: string;
  copyable?: boolean;
}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={copyable ? copyableMarkdownComponents : baseMarkdownComponents}
    >
      {content}
    </ReactMarkdown>
  );
}
