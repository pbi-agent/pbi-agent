import {
  CheckCircle2Icon,
  FileCode2Icon,
  MinusIcon,
  PlusIcon,
  XCircleIcon,
} from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import type { ApplyPatchToolMetadata } from "../../types";
import { Badge } from "../ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";

type DiffLineKind = "added" | "removed" | "context" | "hunk" | "meta" | "empty";

const EMPTY_DIFF_MESSAGE = "No diff content was provided for this operation.";
const CONTEXT_EDGE_LINES = 3;

type DiffLine = {
  key: string;
  kind: DiffLineKind;
  text: string;
  oldNumber: number | null;
  newNumber: number | null;
};

type DiffLineNumber = { old: number | null; new: number | null };

type ParsedDiff = {
  lines: DiffLine[];
  blocks: DiffBlock[];
  added: number;
  removed: number;
  hunks: number;
  changes: number;
};

type DiffBlock =
  | { key: string; kind: "context"; lines: DiffLine[]; collapsed?: number }
  | { key: string; kind: "change"; removed: DiffLine[]; added: DiffLine[] }
  | { key: string; kind: "meta" | "empty"; lines: DiffLine[] };

type InlinePart = {
  key: string;
  text: string;
  changed: boolean;
};

const OPERATION_LABELS: Record<string, string> = {
  create_file: "Created",
  update_file: "Updated",
  delete_file: "Deleted",
};

const FAILED_OPERATION_LABELS: Record<string, string> = {
  create_file: "Create failed",
  update_file: "Update failed",
  delete_file: "Delete failed",
};

export function isApplyPatchToolMetadata(
  metadata: ApplyPatchToolMetadata | undefined,
): metadata is ApplyPatchToolMetadata {
  return (
    metadata?.tool_name === "apply_patch" || Boolean(metadata?.diff && metadata.path)
  );
}

export function GitDiffResult({ metadata }: { metadata: ApplyPatchToolMetadata }) {
  if (isSuccessfulDeleteFile(metadata)) {
    return <DeletedFileResult metadata={metadata} />;
  }

  const parsed = parseV4aDiff(
    metadata.diff ?? "",
    metadata.operation,
    metadata.diff_line_numbers,
  );
  const operationLabel = operationLabelFor(metadata);
  const statusLabel = metadata.success === false ? "Failed" : "Done";
  const visibleBlocks =
    parsed.blocks.length > 0
      ? compactContextBlocks(parsed.blocks)
      : groupDiffLines(emptyStateLines());
  const footerLabel = footerSummary(parsed);

  return (
    <Card
      size="sm"
      className="git-diff-result"
      data-status={metadata.success === false ? "failed" : "done"}
    >
      <CardHeader className="git-diff-result__header">
        <div className="git-diff-result__title-row">
          <span className="git-diff-result__file-icon" aria-hidden="true">
            <FileCode2Icon />
          </span>
          <div className="git-diff-result__title-copy">
            <CardTitle className="git-diff-result__title">
              {metadata.path ?? "Unknown file"}
            </CardTitle>
            <CardDescription className="git-diff-result__description">
              <span>{operationLabel}</span>
              {metadata.detail ? <span>{metadata.detail}</span> : null}
            </CardDescription>
          </div>
        </div>
        <CardAction className="git-diff-result__actions">
          <Badge
            variant={metadata.success === false ? "destructive" : "secondary"}
            className="git-diff-result__status"
          >
            {metadata.success === false ? (
              <XCircleIcon data-icon="inline-start" />
            ) : (
              <CheckCircle2Icon data-icon="inline-start" />
            )}
            {statusLabel}
          </Badge>
          <div className="git-diff-result__stats" aria-label="Diff summary">
            <Badge
              variant="outline"
              className="git-diff-result__stat git-diff-result__stat--added"
            >
              <PlusIcon data-icon="inline-start" />
              {parsed.added}
            </Badge>
            <Badge
              variant="outline"
              className="git-diff-result__stat git-diff-result__stat--removed"
            >
              <MinusIcon data-icon="inline-start" />
              {parsed.removed}
            </Badge>
          </div>
        </CardAction>
      </CardHeader>

      <CardContent className="git-diff-result__content">
        <div
          className="git-diff-result__viewport git-diff-result__viewport--focused"
          role="region"
          aria-label={`Diff for ${metadata.path ?? "file"}`}
        >
          <table className="git-diff-result__table">
            <tbody>
              {visibleBlocks.flatMap((block) => renderBlock(block))}
            </tbody>
          </table>
        </div>
        <div className="git-diff-result__footer">
          <span>{footerLabel}</span>
          {metadata.call_id ? (
            <Badge variant="ghost" className="git-diff-result__call-id">
              {metadata.call_id}
            </Badge>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function DeletedFileResult({ metadata }: { metadata: ApplyPatchToolMetadata }) {
  const fileName = metadata.path ?? "Unknown file";

  return (
    <Card
      size="sm"
      className="git-diff-result git-diff-result--delete"
      data-operation="delete_file"
      data-status="done"
    >
      <CardContent className="git-diff-result__delete-body">
        <div className="git-diff-result__title-row">
          <span
            className="git-diff-result__file-icon git-diff-result__file-icon--delete"
            aria-hidden="true"
          >
            <FileCode2Icon />
          </span>
          <div className="git-diff-result__title-copy">
            <CardTitle className="git-diff-result__title git-diff-result__title--deleted">
              {fileName}
            </CardTitle>
          </div>
        </div>
        <div className="git-diff-result__actions git-diff-result__actions--delete">
          <Badge variant="secondary" className="git-diff-result__status">
            <CheckCircle2Icon data-icon="inline-start" />
            Done
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

function isSuccessfulDeleteFile(metadata: ApplyPatchToolMetadata): boolean {
  return metadata.operation === "delete_file" && metadata.success !== false;
}

function operationLabelFor(metadata: ApplyPatchToolMetadata): string {
  if (metadata.success === false) {
    return FAILED_OPERATION_LABELS[metadata.operation ?? ""] ?? "Patch failed";
  }
  return OPERATION_LABELS[metadata.operation ?? ""] ?? metadata.operation ?? "Edited";
}

function parseV4aDiff(
  diff: string,
  operation: string | undefined,
  lineNumbers: DiffLineNumber[] | undefined,
): ParsedDiff {
  // The apply_patch tool uses V4A diffs rather than unified git patches. Map
  // those compact +/-/context lines into a git-diff-like view.
  const lines = diff.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  if (lines.length > 0 && lines.at(-1) === "") {
    lines.pop();
  }

  let oldNumber = 1;
  let newNumber = operation === "delete_file" ? 0 : 1;
  let added = 0;
  let removed = 0;
  let hunks = 0;

  const parsedLines: DiffLine[] = lines.map((rawLine, index) => {
    const key = `${index}-${rawLine}`;
    const metadataLineNumber = lineNumbers?.[index];
    if (rawLine.startsWith("@@")) {
      hunks += 1;
      const anchor = rawLine.slice(2).trim();
      return {
        key,
        kind: "hunk",
        text: anchor || "Section",
        oldNumber: null,
        newNumber: null,
      };
    }
    if (rawLine.startsWith("***")) {
      return {
        key,
        kind: "meta",
        text: rawLine,
        oldNumber: null,
        newNumber: null,
      };
    }
    if (rawLine.startsWith("+")) {
      added += 1;
      const line: DiffLine = {
        key,
        kind: "added",
        text: rawLine.slice(1),
        oldNumber: metadataLineNumber?.old ?? null,
        newNumber: metadataLineNumber?.new ?? (newNumber > 0 ? newNumber : null),
      };
      newNumber += 1;
      return line;
    }
    if (rawLine.startsWith("-")) {
      removed += 1;
      const line: DiffLine = {
        key,
        kind: "removed",
        text: rawLine.slice(1),
        oldNumber: metadataLineNumber?.old ?? oldNumber,
        newNumber: metadataLineNumber?.new ?? null,
      };
      oldNumber += 1;
      return line;
    }
    if (rawLine.startsWith(" ")) {
      const line: DiffLine = {
        key,
        kind: "context",
        text: rawLine.slice(1),
        oldNumber: metadataLineNumber?.old ?? oldNumber,
        newNumber: metadataLineNumber?.new ?? (newNumber > 0 ? newNumber : null),
      };
      oldNumber += 1;
      newNumber += 1;
      return line;
    }
    return {
      key,
      kind: "empty",
      text: rawLine,
      oldNumber: null,
      newNumber: null,
    };
  });

  const blocks = groupDiffLines(parsedLines);
  const changes = blocks.filter((block) => block.kind === "change").length;

  return { lines: parsedLines, blocks, added, removed, hunks, changes };
}

function groupDiffLines(lines: DiffLine[]): DiffBlock[] {
  const blocks: DiffBlock[] = [];
  let contextLines: DiffLine[] = [];
  let metaLines: DiffLine[] = [];
  let removedLines: DiffLine[] = [];
  let addedLines: DiffLine[] = [];

  const flushContext = () => {
    if (contextLines.length === 0) return;
    blocks.push({
      key: `context-${blocks.length}-${contextLines[0]?.key ?? "line"}`,
      kind: "context",
      lines: contextLines,
    });
    contextLines = [];
  };
  const flushMeta = () => {
    if (metaLines.length === 0) return;
    blocks.push({
      key: `meta-${blocks.length}-${metaLines[0]?.key ?? "line"}`,
      kind: metaLines.some((line) => line.kind === "empty") ? "empty" : "meta",
      lines: metaLines,
    });
    metaLines = [];
  };
  const flushChange = () => {
    if (removedLines.length === 0 && addedLines.length === 0) return;
    blocks.push({
      key: `change-${blocks.length}-${removedLines[0]?.key ?? addedLines[0]?.key ?? "line"}`,
      kind: "change",
      removed: removedLines,
      added: addedLines,
    });
    removedLines = [];
    addedLines = [];
  };

  for (const line of lines) {
    if (line.kind === "removed") {
      flushContext();
      flushMeta();
      removedLines.push(line);
      continue;
    }
    if (line.kind === "added") {
      flushContext();
      flushMeta();
      addedLines.push(line);
      continue;
    }
    flushChange();
    if (line.kind === "context") {
      flushMeta();
      contextLines.push(line);
      continue;
    }
    flushContext();
    metaLines.push(line);
  }

  flushChange();
  flushContext();
  flushMeta();

  return blocks;
}

function compactContextBlocks(blocks: DiffBlock[]): DiffBlock[] {
  return blocks.map((block) => {
    if (block.kind !== "context" || block.lines.length <= CONTEXT_EDGE_LINES * 2 + 1) {
      return block;
    }
    const head = block.lines.slice(0, CONTEXT_EDGE_LINES);
    const tail = block.lines.slice(-CONTEXT_EDGE_LINES);
    return {
      ...block,
      lines: [...head, ...tail],
      collapsed: block.lines.length - head.length - tail.length,
    };
  });
}

function renderBlock(block: DiffBlock): ReactElement[] {
  if (block.kind === "change") {
    return renderChangeBlock(block);
  }
  const rows: ReactElement[] = block.lines.map((line, index) =>
    renderLine(line, { key: `${block.key}-${line.key}`, showTopRadius: index === 0 }),
  );
  if (block.kind === "context" && block.collapsed && block.collapsed > 0) {
    rows.splice(
      CONTEXT_EDGE_LINES,
      0,
      renderCollapsedRow(`${block.key}-collapsed`, block.collapsed),
    );
  }
  return rows;
}

function renderChangeBlock(block: Extract<DiffBlock, { kind: "change" }>): ReactElement[] {
  if (isPairableReplacementBlock(block)) {
    return block.removed.flatMap((removed, index) => {
      const added = block.added[index];
      const inline = diffInline(removed.text, added.text);
      return [
        renderLine(removed, {
          key: `${block.key}-removed-${removed.key}`,
          inlineParts: inline.oldParts,
        }),
        renderLine(added, {
          key: `${block.key}-added-${added.key}`,
          inlineParts: inline.newParts,
        }),
      ];
    });
  }

  const rows: ReactElement[] = [];
  for (const removed of block.removed) {
    rows.push(renderLine(removed, { key: `${block.key}-removed-${removed.key}` }));
  }
  for (const added of block.added) {
    rows.push(renderLine(added, { key: `${block.key}-added-${added.key}` }));
  }

  return rows;
}

function isPairableReplacementBlock(block: Extract<DiffBlock, { kind: "change" }>): boolean {
  return block.removed.length > 0 && block.removed.length === block.added.length;
}

function renderLine(
  line: DiffLine,
  options: { key: string; inlineParts?: InlinePart[]; showTopRadius?: boolean },
): ReactElement {
  return (
    <tr
      key={options.key}
      className={`git-diff-result__line git-diff-result__line--${line.kind}`}
      data-focused={options.inlineParts?.some((part) => part.changed) ? "true" : undefined}
      data-group-start={options.showTopRadius ? "true" : undefined}
    >
      <td className="git-diff-result__gutter git-diff-result__gutter--old">
        {line.oldNumber ?? ""}
      </td>
      <td className="git-diff-result__gutter git-diff-result__gutter--new">
        {line.newNumber ?? ""}
      </td>
      <td className="git-diff-result__marker">{markerForLine(line.kind)}</td>
      <td className="git-diff-result__code">
        <code>{renderCode(line, options.inlineParts)}</code>
      </td>
    </tr>
  );
}

function renderCode(line: DiffLine, inlineParts: InlinePart[] | undefined): ReactNode {
  if (!inlineParts || inlineParts.length === 0) {
    return line.text || " ";
  }
  return inlineParts.map((part) => (
    <span
      key={part.key}
      className={
        part.changed
          ? `git-diff-result__token git-diff-result__token--${line.kind}`
          : undefined
      }
    >
      {part.text || " "}
    </span>
  ));
}

function renderCollapsedRow(key: string, count: number): ReactElement {
  return (
    <tr key={key} className="git-diff-result__line git-diff-result__line--collapsed">
      <td className="git-diff-result__gutter" />
      <td className="git-diff-result__gutter" />
      <td className="git-diff-result__marker">⋯</td>
      <td className="git-diff-result__code">
        <code>{count} unchanged lines</code>
      </td>
    </tr>
  );
}

function diffInline(oldText: string, newText: string): { oldParts: InlinePart[]; newParts: InlinePart[] } {
  if (oldText === newText) {
    return {
      oldParts: [{ key: "old-same", text: oldText, changed: false }],
      newParts: [{ key: "new-same", text: newText, changed: false }],
    };
  }

  let prefixLength = 0;
  const shortestLength = Math.min(oldText.length, newText.length);
  while (prefixLength < shortestLength && oldText[prefixLength] === newText[prefixLength]) {
    prefixLength += 1;
  }

  let suffixLength = 0;
  while (
    suffixLength < shortestLength - prefixLength &&
    oldText[oldText.length - 1 - suffixLength] === newText[newText.length - 1 - suffixLength]
  ) {
    suffixLength += 1;
  }

  const oldMiddleEnd = oldText.length - suffixLength;
  const newMiddleEnd = newText.length - suffixLength;

  return {
    oldParts: buildInlineParts("old", oldText, prefixLength, oldMiddleEnd),
    newParts: buildInlineParts("new", newText, prefixLength, newMiddleEnd),
  };
}

function buildInlineParts(
  prefix: string,
  text: string,
  changeStart: number,
  changeEnd: number,
): InlinePart[] {
  const parts: InlinePart[] = [];
  const leading = text.slice(0, changeStart);
  const changed = text.slice(changeStart, changeEnd);
  const trailing = text.slice(changeEnd);
  if (leading) parts.push({ key: `${prefix}-before`, text: leading, changed: false });
  if (changed) parts.push({ key: `${prefix}-changed`, text: changed, changed: true });
  if (trailing) parts.push({ key: `${prefix}-after`, text: trailing, changed: false });
  if (parts.length === 0) parts.push({ key: `${prefix}-empty`, text: " ", changed: true });
  return parts;
}

function footerSummary(parsed: ParsedDiff): string {
  if (parsed.changes > 0) {
    return `${parsed.changes} focused change${parsed.changes === 1 ? "" : "s"}`;
  }
  if (parsed.hunks > 0) {
    return `${parsed.hunks} hunk${parsed.hunks === 1 ? "" : "s"}`;
  }
  if (parsed.lines.length > 0) {
    return "Diff parsed";
  }
  return "No diff content";
}

function emptyStateLines(): DiffLine[] {
  return [
    {
      key: "empty",
      kind: "empty",
      text: EMPTY_DIFF_MESSAGE,
      oldNumber: null,
      newNumber: null,
    },
  ];
}

function markerForLine(kind: DiffLineKind): string {
  if (kind === "added") return "+";
  if (kind === "removed") return "-";
  if (kind === "hunk") return "@@";
  return "";
}
