import {
  CheckCircle2Icon,
  FileCode2Icon,
  MinusIcon,
  PlusIcon,
  XCircleIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  type ReactElement,
  type ReactNode,
  type RefObject,
  type UIEvent,
} from "react";
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
export type GitDiffLayout = "stacked" | "split";

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

type SplitDiffRow =
  | {
      key: string;
      kind: "pair";
      oldLine: DiffLine | null;
      newLine: DiffLine | null;
      oldInlineParts?: InlinePart[];
      newInlineParts?: InlinePart[];
      focused?: boolean;
      showTopRadius?: boolean;
    }
  | {
      key: string;
      kind: "spanning";
      line: DiffLine;
      showTopRadius?: boolean;
    }
  | { key: string; kind: "collapsed"; count: number };

type InlinePart = {
  key: string;
  text: string;
  changed: boolean;
};

const OPERATION_LABELS: Record<string, string> = {
  create_file: "Created",
  update_file: "Updated",
  delete_file: "Deleted",
  move_file: "Moved",
};

const FAILED_OPERATION_LABELS: Record<string, string> = {
  create_file: "Create failed",
  update_file: "Update failed",
  delete_file: "Delete failed",
  move_file: "Move failed",
};

/**
 * Tools whose completed metadata is rendered with the git-diff layout. The
 * Python side (`agent/tool_display.py::_display_apply_patch_result`) routes
 * `apply_patch`, `replace_in_file`, and `write_file` through
 * `display.patch_result(...)`, which populates `path` + `diff` on the metadata
 * for all three. Callers should keep this set aligned with the Python
 * `_PATCH_DISPLAY_TOOL_NAMES` constant.
 */
export const FILE_EDIT_TOOL_NAMES: ReadonlySet<string> = new Set([
  "apply_patch",
  "replace_in_file",
  "write_file",
]);

export function isApplyPatchToolMetadata(
  metadata: ApplyPatchToolMetadata | undefined,
): metadata is ApplyPatchToolMetadata {
  return Boolean(
    metadata?.tool_name &&
      FILE_EDIT_TOOL_NAMES.has(metadata.tool_name) &&
      metadata.path,
  );
}

export function GitDiffResult({
  metadata,
  layout = "stacked",
}: {
  metadata: ApplyPatchToolMetadata;
  layout?: GitDiffLayout;
}) {
  const oldSplitScrollRef = useRef<HTMLDivElement | null>(null);
  const newSplitScrollRef = useRef<HTMLDivElement | null>(null);
  const oldSplitTableRef = useRef<HTMLTableElement | null>(null);
  const newSplitTableRef = useRef<HTMLTableElement | null>(null);
  const syncingSplitScrollRef = useRef(false);
  const handleSplitPaneScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    if (syncingSplitScrollRef.current) return;
    const source = event.currentTarget;
    const target =
      source === oldSplitScrollRef.current
        ? newSplitScrollRef.current
        : oldSplitScrollRef.current;
    if (!target) return;

    const maxSourceLeft = Math.max(0, source.scrollWidth - source.clientWidth);
    const maxTargetLeft = Math.max(0, target.scrollWidth - target.clientWidth);
    const leftRatio = maxSourceLeft > 0 ? source.scrollLeft / maxSourceLeft : null;
    const maxSourceTop = Math.max(0, source.scrollHeight - source.clientHeight);
    const maxTargetTop = Math.max(0, target.scrollHeight - target.clientHeight);
    const topRatio = maxSourceTop > 0 ? source.scrollTop / maxSourceTop : null;

    syncingSplitScrollRef.current = true;
    target.scrollLeft = leftRatio === null ? source.scrollLeft : maxTargetLeft * leftRatio;
    target.scrollTop = topRatio === null ? source.scrollTop : maxTargetTop * topRatio;
    window.requestAnimationFrame(() => {
      syncingSplitScrollRef.current = false;
    });
  }, []);

  useLayoutEffect(() => {
    if (layout !== "split") return;
    const measureSplitPaneWidth = () => {
      const tables = [oldSplitTableRef.current, newSplitTableRef.current].filter(
        (table): table is HTMLTableElement => table !== null,
      );
      for (const table of tables) {
        table.style.minWidth = "100%";
      }
      const oldWidth = oldSplitTableRef.current?.scrollWidth ?? 0;
      const newWidth = newSplitTableRef.current?.scrollWidth ?? 0;
      const nextWidth = Math.max(oldWidth, newWidth);
      for (const table of tables) {
        table.style.minWidth = nextWidth > 0 ? `${nextWidth}px` : "100%";
      }
    };

    measureSplitPaneWidth();
    window.addEventListener("resize", measureSplitPaneWidth);
    return () => {
      window.removeEventListener("resize", measureSplitPaneWidth);
    };
  }, [layout, metadata.diff, metadata.path]);

  useEffect(() => {
    if (layout !== "split") return;
    syncingSplitScrollRef.current = false;
    if (oldSplitScrollRef.current) {
      oldSplitScrollRef.current.scrollLeft = 0;
      oldSplitScrollRef.current.scrollTop = 0;
    }
    if (newSplitScrollRef.current) {
      newSplitScrollRef.current.scrollLeft = 0;
      newSplitScrollRef.current.scrollTop = 0;
    }
  }, [layout, metadata.diff, metadata.path]);

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
  const title = titleFor(metadata);
  const fileCountLabel = fileCountDescription(metadata);
  const visibleBlocks =
    parsed.blocks.length > 0
      ? compactContextBlocks(parsed.blocks)
      : groupDiffLines(emptyStateLines());
  const footerLabel = footerSummary(parsed);
  const splitRows = layout === "split" ? buildSplitRows(visibleBlocks) : [];

  return (
    <Card
      size="sm"
      className="git-diff-result"
      data-status={metadata.success === false ? "failed" : "done"}
      data-layout={layout}
    >
      <CardHeader className="git-diff-result__header">
        <div className="git-diff-result__title-row">
          <span className="git-diff-result__file-icon" aria-hidden="true">
            <FileCode2Icon />
          </span>
          <div className="git-diff-result__title-copy">
            <CardTitle className="git-diff-result__title">
              {title}
            </CardTitle>
            <CardDescription className="git-diff-result__description">
              <span>{operationLabel}</span>
              {fileCountLabel ? <span>{fileCountLabel}</span> : null}
              {metadata.detail ? <span>{metadata.detail}</span> : null}
            </CardDescription>
          </div>
        </div>
        <CardAction className="git-diff-result__actions">
          <Badge
            variant={metadata.success === false ? "destructive" : "secondary"}
            size="meta"
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
              size="meta"
              className="git-diff-result__stat git-diff-result__stat--added"
            >
              <PlusIcon data-icon="inline-start" />
              {parsed.added}
            </Badge>
            <Badge
              variant="outline"
              size="meta"
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
          {layout === "split" ? (
            <div
              className="git-diff-result__split"
              role="group"
              aria-label="Split diff panes"
            >
              <div
                ref={oldSplitScrollRef}
                className="git-diff-result__split-pane git-diff-result__split-pane--old"
                onScroll={handleSplitPaneScroll}
              >
                {renderSplitPaneTable("old", splitRows, {
                  ref: oldSplitTableRef,
                })}
              </div>
              <div
                ref={newSplitScrollRef}
                className="git-diff-result__split-pane git-diff-result__split-pane--new"
                onScroll={handleSplitPaneScroll}
              >
                {renderSplitPaneTable("new", splitRows, {
                  ref: newSplitTableRef,
                })}
              </div>
            </div>
          ) : (
            <table className="git-diff-result__table git-diff-result__table--stacked">
              <tbody>{visibleBlocks.flatMap((block) => renderBlock(block))}</tbody>
            </table>
          )}
        </div>
        <div className="git-diff-result__footer">
          <span>{footerLabel}</span>
          {metadata.call_id ? (
            <Badge variant="ghost" size="meta" className="git-diff-result__call-id">
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
          <Badge variant="secondary" size="meta" className="git-diff-result__status">
            <CheckCircle2Icon data-icon="inline-start" />
            Done
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

function isSuccessfulDeleteFile(metadata: ApplyPatchToolMetadata): boolean {
  const count =
    typeof metadata.operation_count === "number" ? metadata.operation_count : 1;
  return metadata.operation === "delete_file" && metadata.success !== false && count <= 1;
}

function operationLabelFor(metadata: ApplyPatchToolMetadata): string {
  if (metadata.success === false) {
    return FAILED_OPERATION_LABELS[metadata.operation ?? ""] ?? "Patch failed";
  }
  return OPERATION_LABELS[metadata.operation ?? ""] ?? metadata.operation ?? "Edited";
}

function titleFor(metadata: ApplyPatchToolMetadata): string {
  const primaryPath = metadata.path ?? "Unknown file";
  const affectedPaths = Array.isArray(metadata.affected_paths)
    ? metadata.affected_paths.filter(
        (path): path is string => typeof path === "string" && path.length > 0,
      )
    : [];
  const paths = uniquePaths([primaryPath, ...affectedPaths]);
  const count =
    typeof metadata.operation_count === "number" &&
    metadata.operation_count > paths.length
      ? metadata.operation_count
      : paths.length;
  if (count <= 1 || paths.length <= 1) {
    return primaryPath;
  }
  if (paths.length === 2 && count === 2) {
    return `${paths[0]} + ${paths[1]}`;
  }
  const hiddenCount = Math.max(0, count - 2);
  return `${paths[0]} + ${paths[1]}${
    hiddenCount > 0 ? ` + ${hiddenCount} file${hiddenCount === 1 ? "" : "s"}` : ""
  }`;
}

function fileCountDescription(metadata: ApplyPatchToolMetadata): string | null {
  const count =
    typeof metadata.operation_count === "number" ? metadata.operation_count : null;
  return count && count > 1 ? `${count} files` : null;
}

function uniquePaths(paths: string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const path of paths) {
    if (seen.has(path)) {
      continue;
    }
    seen.add(path);
    unique.push(path);
  }
  return unique;
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
      const hunkMatch = rawLine.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/);
      if (hunkMatch) {
        oldNumber = Number(hunkMatch[1]);
        newNumber = Number(hunkMatch[2]);
      }
      const anchor = rawLine.slice(2).trim();
      return {
        key,
        kind: "hunk",
        text: anchor || "Section",
        oldNumber: null,
        newNumber: null,
      };
    }
    if (
      rawLine.startsWith("***")
      || rawLine.startsWith("diff --git ")
      || rawLine.startsWith("index ")
      || rawLine.startsWith("new file mode ")
      || rawLine.startsWith("deleted file mode ")
      || rawLine.startsWith("similarity index ")
      || rawLine.startsWith("rename from ")
      || rawLine.startsWith("rename to ")
      || rawLine.startsWith("Binary files ")
      || rawLine.startsWith("--- ")
      || rawLine.startsWith("+++ ")
    ) {
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

function buildSplitRows(blocks: DiffBlock[]): SplitDiffRow[] {
  return blocks.flatMap((block) => splitRowsForBlock(block));
}

function splitRowsForBlock(block: DiffBlock): SplitDiffRow[] {
  if (block.kind === "change") {
    return splitRowsForChangeBlock(block);
  }
  const rows: SplitDiffRow[] = block.lines.map((line, index) => {
    if (line.kind === "context") {
      return {
        key: `${block.key}-split-${line.key}`,
        kind: "pair",
        oldLine: line,
        newLine: line,
        showTopRadius: index === 0,
      };
    }
    return {
      key: `${block.key}-split-${line.key}`,
      kind: "spanning",
      line,
      showTopRadius: index === 0,
    };
  });
  if (block.kind === "context" && block.collapsed && block.collapsed > 0) {
    rows.splice(CONTEXT_EDGE_LINES, 0, {
      key: `${block.key}-split-collapsed`,
      kind: "collapsed",
      count: block.collapsed,
    });
  }
  return rows;
}

function splitRowsForChangeBlock(
  block: Extract<DiffBlock, { kind: "change" }>,
): SplitDiffRow[] {
  const rowCount = Math.max(block.removed.length, block.added.length);
  const pairable = isPairableReplacementBlock(block);
  const rows: SplitDiffRow[] = [];
  for (let index = 0; index < rowCount; index += 1) {
    const removed = block.removed[index] ?? null;
    const added = block.added[index] ?? null;
    let oldInlineParts: InlinePart[] | undefined;
    let newInlineParts: InlinePart[] | undefined;
    if (pairable && removed && added) {
      const inline = diffInline(removed.text, added.text);
      oldInlineParts = inline.oldParts;
      newInlineParts = inline.newParts;
    }
    rows.push({
      key: `${block.key}-split-${index}-${removed?.key ?? "empty"}-${added?.key ?? "empty"}`,
      kind: "pair",
      oldLine: removed,
      newLine: added,
      oldInlineParts,
      newInlineParts,
      focused:
        oldInlineParts?.some((part) => part.changed)
        || newInlineParts?.some((part) => part.changed)
        || false,
    });
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

function renderSplitPaneTable(
  side: "old" | "new",
  rows: SplitDiffRow[],
  options: {
    ref: RefObject<HTMLTableElement | null>;
  },
): ReactElement {
  return (
    <table
      ref={options.ref}
      className="git-diff-result__split-table"
    >
      <colgroup>
        <col className="git-diff-result__col git-diff-result__col--gutter" />
        <col className="git-diff-result__col git-diff-result__col--marker" />
        <col className="git-diff-result__col git-diff-result__col--code" />
      </colgroup>
      <tbody>{rows.map((row) => renderSplitPaneRow(side, row))}</tbody>
    </table>
  );
}

function renderSplitPaneRow(
  side: "old" | "new",
  row: SplitDiffRow,
): ReactElement {
  if (row.kind === "pair") {
    const line = side === "old" ? row.oldLine : row.newLine;
    const inlineParts =
      side === "old" ? row.oldInlineParts : row.newInlineParts;
    return (
      <tr
        key={`${side}-${row.key}`}
        className="git-diff-result__line git-diff-result__line--split"
        data-focused={row.focused ? "true" : undefined}
        data-group-start={row.showTopRadius ? "true" : undefined}
      >
        {renderSplitSideCells(side, line, inlineParts)}
      </tr>
    );
  }

  if (row.kind === "collapsed") {
    const renderCollapsedContent = side === "old";
    return (
      <tr
        key={`${side}-${row.key}`}
        className="git-diff-result__line git-diff-result__line--collapsed"
        aria-hidden={renderCollapsedContent ? undefined : "true"}
      >
        <td
          className="git-diff-result__split-spanning git-diff-result__split-spanning--collapsed"
          colSpan={3}
        >
          {renderCollapsedContent ? (
            <>
              <span className="git-diff-result__split-spanning-marker">⋯</span>
              <code>{row.count} unchanged lines</code>
            </>
          ) : (
            <span className="git-diff-result__split-spanning-placeholder">
              &nbsp;
            </span>
          )}
        </td>
      </tr>
    );
  }

  const renderSpanningContent = side === "old";
  return (
    <tr
      key={`${side}-${row.key}`}
      className={`git-diff-result__line git-diff-result__line--${row.line.kind}`}
      data-group-start={row.showTopRadius ? "true" : undefined}
      aria-hidden={renderSpanningContent ? undefined : "true"}
    >
      <td
        className={`git-diff-result__split-spanning git-diff-result__split-spanning--${row.line.kind}`}
        colSpan={3}
      >
        {renderSpanningContent ? (
          <>
            <span className="git-diff-result__split-spanning-marker">
              {markerForLine(row.line.kind)}
            </span>
            <code>{row.line.text || " "}</code>
          </>
        ) : (
          <span className="git-diff-result__split-spanning-placeholder">
            &nbsp;
          </span>
        )}
      </td>
    </tr>
  );
}

function renderSplitSideCells(
  side: "old" | "new",
  line: DiffLine | null,
  inlineParts: InlinePart[] | undefined,
): ReactElement[] {
  const kind = line?.kind ?? "empty";
  const number = line ? (side === "old" ? line.oldNumber : line.newNumber) : null;
  const cellClass =
    `git-diff-result__split-cell git-diff-result__split-cell--${side} `
    + `git-diff-result__split-cell--${kind}`;
  return [
    <td
      key={`${side}-gutter`}
      className={`git-diff-result__gutter git-diff-result__gutter--${side} ${cellClass}`}
    >
      {number ?? ""}
    </td>,
    <td key={`${side}-marker`} className={`git-diff-result__marker ${cellClass}`}>
      {line ? markerForLine(line.kind) : ""}
    </td>,
    <td key={`${side}-code`} className={`git-diff-result__code ${cellClass}`}>
      <code>{line ? renderCode(line, inlineParts) : " "}</code>
    </td>,
  ];
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
