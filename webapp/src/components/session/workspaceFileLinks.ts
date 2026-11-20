import { createContext } from "react";

export const OpenWorkspaceFileLinkContext = createContext<((href: string) => boolean) | null>(null);

export type WorkspaceFileLineRange = { start: number; end: number };
export type WorkspaceFileTarget = { path: string; lines: WorkspaceFileLineRange | null };
export type WorkspaceFileReveal = WorkspaceFileTarget & { workspaceKey: string | null };

// `file.ts:42`, `file.ts:42:7` (column ignored), `file.ts:42-50`.
const LINE_SUFFIX = /:(\d+)(?:-(\d+)|:\d+)?$/;
// GitHub-style `#L42`, `#L42-L50`.
const LINE_HASH = /^#L(\d+)(?:-L?(\d+))?$/i;
const DRIVE_PATH = /^\/?[a-z]:\//i;

function decodeSegments(path: string): string[] | null {
  try {
    return path.split("/").map(decodeURIComponent);
  } catch {
    return null;
  }
}

function lineRange(start: string, end: string | undefined): WorkspaceFileLineRange | null {
  const first = Number(start);
  if (!Number.isSafeInteger(first) || first < 1) return null;
  const last = end === undefined ? first : Number(end);
  return { start: first, end: Number.isSafeInteger(last) && last >= first ? last : first };
}

/** Returns the workspace-relative segments of an absolute path under `workspaceRoot`. */
function stripWorkspaceRoot(path: string, workspaceRoot: string | null | undefined): string[] | null {
  if (!workspaceRoot) return null;
  const rootParts = workspaceRoot.replace(/\\/g, "/").split("/").filter(Boolean);
  const linkParts = decodeSegments(path.replace(/^\//, ""));
  if (!rootParts.length || !linkParts) return null;
  // Windows paths compare case-insensitively.
  const caseInsensitive = /^[a-z]:$/i.test(rootParts[0]);
  const same = (a: string, b: string) => (caseInsensitive ? a.toLowerCase() === b.toLowerCase() : a === b);
  if (linkParts.length <= rootParts.length || !rootParts.every((part, i) => same(part, linkParts[i]))) {
    return null;
  }
  return linkParts.slice(rootParts.length);
}

export function workspaceFileTargetForLink(
  href: string,
  origin: string,
  knownFiles: ReadonlySet<string>,
  workspaceRoot?: string | null,
): WorkspaceFileTarget | null {
  const trimmed = href.trim();
  const hashIndex = trimmed.indexOf("#");
  const hash = hashIndex === -1 ? "" : trimmed.slice(hashIndex);
  // Read the unnormalized pathname so encoded dot segments can't be silently removed.
  let [path] = trimmed.split(/[?#]/, 1);
  if (!path || path.includes("\\")) return null;

  const fileUrl = /^file:\/\/(\/.*)$/i.exec(path);
  const absolute = /^https?:\/\/[^/]+(\/.*)$/i.exec(path);
  if (fileUrl) {
    path = fileUrl[1];
  } else if (absolute) {
    try {
      const url = new URL(path);
      if (url.origin !== origin || url.username || url.password) return null;
    } catch {
      return null;
    }
    path = absolute[1];
  } else if (
    path.startsWith("//")
    || (/^[\w+.-]+:/.test(path) && !DRIVE_PATH.test(path) && !/^[^/:]+:\d+(?:-\d+|:\d+)?$/.test(path))
  ) {
    return null;
  }

  // A raw relative href can only resolve under /sessions/, which is never a useful
  // target, so it always opens in Explorer. Absolute forms must look like files.
  const relative = !path.startsWith("/") && !DRIVE_PATH.test(path);
  let parts: string[] | null;
  if (relative) {
    parts = decodeSegments(path);
  } else {
    parts = stripWorkspaceRoot(path, workspaceRoot);
    if (parts === null) {
      // Relative Markdown links on /sessions/<id> may already have been expanded by the browser.
      if (fileUrl || !path.startsWith("/sessions/")) return null;
      path = path.slice("/sessions/".length);
      if (/^[^/]+\/sub-agents\/[^/]+\/?$/.test(path)) return null;
      // Relative links expanded on /sessions/<id>/sub-agents/<sub-id> keep that route prefix.
      path = path.replace(/^[^/]+\/sub-agents\//, "");
      parts = decodeSegments(path);
    }
  }
  if (!parts?.length) return null;
  const lastPart = parts[parts.length - 1];
  const suffix = LINE_SUFFIX.exec(lastPart);
  if (suffix) parts[parts.length - 1] = lastPart.slice(0, suffix.index);
  const hashLines = LINE_HASH.exec(hash);
  const lines = suffix
    ? lineRange(suffix[1], suffix[2])
    : hashLines ? lineRange(hashLines[1], hashLines[2]) : null;
  if (parts.some((part) => !part || part === ".." || /[\\/:]/.test(part)
    || [...part].some((char) => char.charCodeAt(0) < 32))) return null;
  parts = parts.filter((part) => part !== ".");
  const filename = parts.at(-1);
  if (!filename) return null;

  const candidate = parts.join("/");
  // The tree can still be scanning or omit gitignored files. File-like paths can
  // open directly; the preview API validates the path and handles missing files.
  return relative || knownFiles.has(candidate) || /\.[^\s.]+$/.test(filename)
    ? { path: candidate, lines }
    : null;
}
