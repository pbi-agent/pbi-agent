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
    if (child.type === "code") {
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
      if (child.type === "th" || child.type === "td") {
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
      if (child.type === "tr") {
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
      if (child.type === "li") {
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

function CopyableSnippet({
  children,
  className,
  text,
}: {
  children: ReactNode;
  className: string;
  text: string;
}) {
  const insideCopyableSnippet = useContext(CopyableSnippetContext);
  if (insideCopyableSnippet || text.trim().length === 0) {
    return <>{children}</>;
  }

  return (
    <div className={cn("markdown-copyable-snippet", className)}>
      <div className="markdown-copyable-snippet__actions">
        <CopyShortcut
          text={text}
          ariaLabel="Copy snippet"
          className="markdown-copyable-snippet__copy"
        />
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
    <CopyableSnippet className="markdown-copyable-snippet--code" text={text}>
      <div className="markdown-code-snippet" data-language={languageLabel}>
        <div className="markdown-code-snippet__header">
          <span className="markdown-code-snippet__language">{languageLabel}</span>
        </div>
        <CodeBlock
          value={text}
          language={language}
          className="markdown-code-snippet__block"
        />
      </div>
    </CopyableSnippet>
  );
}

const copyableMarkdownComponents: Components = {
  pre({ children }) {
    const { language, text } = codeFenceFromPreChildren(children);
    return <MarkdownCodeSnippet language={language} text={text} />;
  },
  table({ children }) {
    return (
      <CopyableSnippet
        className="markdown-copyable-snippet--table"
        text={tableChildrenToTsv(children)}
      >
        <table>{children}</table>
      </CopyableSnippet>
    );
  },
  blockquote({ children }) {
    return (
      <CopyableSnippet
        className="markdown-copyable-snippet--blockquote"
        text={reactNodeToText(children).trim()}
      >
        <blockquote>{children}</blockquote>
      </CopyableSnippet>
    );
  },
  ul({ children }) {
    return (
      <CopyableSnippet
        className="markdown-copyable-snippet--list"
        text={listChildrenToText(children, false)}
      >
        <ul>{children}</ul>
      </CopyableSnippet>
    );
  },
  ol({ children }) {
    return (
      <CopyableSnippet
        className="markdown-copyable-snippet--list"
        text={listChildrenToText(children, true)}
      >
        <ol>{children}</ol>
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
      components={copyable ? copyableMarkdownComponents : undefined}
    >
      {content}
    </ReactMarkdown>
  );
}
