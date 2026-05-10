import {
  type ClipboardEvent,
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type SyntheticEvent,
} from "react";
import {
  ArrowUpIcon,
  BadgeDollarSignIcon,
  ImageIcon,
  PlusIcon,
  SquareIcon,
  TerminalIcon,
  XIcon,
} from "lucide-react";
import { searchFileMentions, searchSkillMentions, searchSlashCommands } from "../../api";
import type { FileMentionItem, SkillMentionItem, SlashCommandItem } from "../../types";
import { cn } from "../../lib/utils";
import { useFileExistence } from "../../hooks/useFileExistence";
import { useSkillCatalog } from "../../hooks/useSkillCatalog";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "../ui/input-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

export interface ComposerHandle {
  focus: () => void;
}

interface ComposerProps {
  inputEnabled: boolean;
  sessionEnded: boolean;
  liveSessionId: string | null;
  /** Chronological oldest-to-newest user input text for the current conversation. */
  inputHistory?: string[];
  canCreateSession?: boolean;
  supportsImageInputs: boolean;
  interactiveMode: boolean;
  isSubmitting: boolean;
  onSubmit: (payload: { text: string; images: File[] }) => Promise<void>;
  canInterrupt?: boolean;
  isInterrupting?: boolean;
  restoredInput?: string | null;
  onRestoredInputConsumed?: () => void;
  onInterrupt?: () => void;
}

type ActiveCompletionRange = {
  start: number;
  end: number;
  query: string;
};

type CompletionMode = "mention" | "skill" | "slash";

type CompletionItem =
  | {
      kind: "mention";
      key: string;
      mention: FileMentionItem;
    }
  | {
      kind: "skill";
      key: string;
      skill: SkillMentionItem;
    }
  | {
      kind: "slash";
      key: string;
      command: SlashCommandItem;
    };

type PendingImage = {
  id: string;
  file: File;
  previewUrl: string;
  source: "picker" | "clipboard";
};

type ImageFileInput = HTMLInputElement & {
  showPicker?: () => void;
};

const SUPPORTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const TOKEN_BOUNDARY_PATTERN = /[\s()[\]{}'"`,;]/;
const FILE_MENTION_POLL_INTERVAL_MS = 500;

function parseActiveMention(
  text: string,
  cursorIndex: number,
): ActiveCompletionRange | null {
  if (cursorIndex < 0 || cursorIndex > text.length) {
    return null;
  }

  let tokenStart = cursorIndex;
  while (tokenStart > 0 && !TOKEN_BOUNDARY_PATTERN.test(text[tokenStart - 1])) {
    tokenStart -= 1;
  }
  let tokenEnd = cursorIndex;
  while (tokenEnd < text.length && !TOKEN_BOUNDARY_PATTERN.test(text[tokenEnd])) {
    tokenEnd += 1;
  }

  if (text[tokenStart] !== "@" || text[tokenStart + 1] === "/") {
    return null;
  }
  if (tokenStart > 0 && !TOKEN_BOUNDARY_PATTERN.test(text[tokenStart - 1])) {
    return null;
  }

  const candidate = text.slice(tokenStart + 1, cursorIndex);
  return {
    start: tokenStart,
    end: tokenEnd,
    query: candidate.replaceAll("\\ ", " "),
  };
}

function parseActiveSkillTag(
  text: string,
  cursorIndex: number,
): ActiveCompletionRange | null {
  if (cursorIndex < 0 || cursorIndex > text.length) {
    return null;
  }

  let tokenStart = cursorIndex;
  while (tokenStart > 0 && !TOKEN_BOUNDARY_PATTERN.test(text[tokenStart - 1])) {
    tokenStart -= 1;
  }
  let tokenEnd = cursorIndex;
  while (tokenEnd < text.length && !TOKEN_BOUNDARY_PATTERN.test(text[tokenEnd])) {
    tokenEnd += 1;
  }

  if (text[tokenStart] !== "$") {
    return null;
  }
  const nextCharacter = text[tokenStart + 1] ?? "";
  if (["(", "{"].includes(nextCharacter) || /\d/.test(nextCharacter)) {
    return null;
  }
  if (tokenStart > 0 && !TOKEN_BOUNDARY_PATTERN.test(text[tokenStart - 1])) {
    return null;
  }

  return {
    start: tokenStart,
    end: tokenEnd,
    query: text.slice(tokenStart + 1, cursorIndex),
  };
}

function parseActiveSlashCommand(
  text: string,
  cursorIndex: number,
): ActiveCompletionRange | null {
  if (cursorIndex <= 0 || cursorIndex > text.length || !text.startsWith("/")) {
    return null;
  }

  const firstWhitespaceIndex = text.search(/\s/);
  const commandEnd = firstWhitespaceIndex >= 0 ? firstWhitespaceIndex : text.length;
  if (cursorIndex > commandEnd) {
    return null;
  }

  return {
    start: 0,
    end: cursorIndex,
    query: text.slice(1, cursorIndex),
  };
}

function escapeMentionPath(path: string): string {
  return path.replaceAll(" ", "\\ ");
}

type HighlightSegment =
  | { kind: "text"; text: string }
  | { kind: "mention" | "skill"; text: string };

type HighlightValidators = {
  skillNames: Set<string>;
  isFileKnown: (token: string) => boolean;
  isShellMode: boolean;
};

function findNextHighlightCandidate(
  text: string,
  cursor: number,
): { start: number; kind: "mention" | "skill"; end: number } | null {
  for (let index = cursor; index < text.length; index += 1) {
    const character = text[index];
    if (character !== "@" && character !== "$") continue;
    const previous = index > 0 ? text[index - 1] : " ";
    if (index > 0 && !TOKEN_BOUNDARY_PATTERN.test(previous)) continue;
    const next = text[index + 1] ?? "";
    if (character === "@") {
      if (next === "/" || next === "") continue;
      let end = index + 1;
      while (end < text.length) {
        if (text[end] === "\\" && text[end + 1] === " ") {
          end += 2;
          continue;
        }
        if (TOKEN_BOUNDARY_PATTERN.test(text[end])) break;
        end += 1;
      }
      return { start: index, kind: "mention", end };
    }
    if (next === "" || next === "(" || next === "{" || /\d/.test(next)) continue;
    let end = index + 1;
    while (end < text.length && /[A-Za-z0-9_-]/.test(text[end])) end += 1;
    return { start: index, kind: "skill", end };
  }
  return null;
}

function appendHighlightSegment(segments: HighlightSegment[], segment: HighlightSegment): void {
  if (segment.kind === "text" && segment.text.length === 0) return;
  const previous = segments.at(-1);
  if (previous?.kind === "text" && segment.kind === "text") {
    previous.text += segment.text;
    return;
  }
  segments.push(segment);
}

function collectComposerFileTokens(text: string, shellMode: boolean): string[] {
  if (shellMode) return [];
  const tokens = new Set<string>();
  let cursor = 0;
  while (cursor < text.length) {
    const candidate = findNextHighlightCandidate(text, cursor);
    if (!candidate) break;
    if (candidate.kind === "mention") {
      tokens.add(text.slice(candidate.start + 1, candidate.end).replaceAll("\\ ", " "));
    }
    cursor = candidate.end;
  }
  return Array.from(tokens);
}

function parseComposerHighlightSegments(
  text: string,
  { skillNames, isFileKnown, isShellMode: shellMode }: HighlightValidators,
): HighlightSegment[] {
  if (shellMode) return [{ kind: "text", text }];

  const segments: HighlightSegment[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    const candidate = findNextHighlightCandidate(text, cursor);
    if (!candidate) {
      appendHighlightSegment(segments, { kind: "text", text: text.slice(cursor) });
      break;
    }
    appendHighlightSegment(segments, { kind: "text", text: text.slice(cursor, candidate.start) });

    const tokenText = text.slice(candidate.start, candidate.end);
    const shouldHighlight = candidate.kind === "skill"
      ? skillNames.has(tokenText.slice(1))
      : isFileKnown(tokenText.slice(1).replaceAll("\\ ", " "));
    appendHighlightSegment(segments, {
      kind: shouldHighlight ? candidate.kind : "text",
      text: tokenText,
    });
    cursor = candidate.end;
  }

  return segments.length > 0 ? segments : [{ kind: "text", text }];
}

function replaceTextRange(
  text: string,
  start: number,
  end: number,
  replacement: string,
): { nextInput: string; nextCursor: number } {
  const safeStart = Math.max(0, Math.min(start, text.length));
  const safeEnd = Math.max(safeStart, Math.min(end, text.length));
  const prefix = text.slice(0, safeStart);
  const suffix = text.slice(safeEnd);
  const insertion = suffix.startsWith(" ") ? replacement : `${replacement} `;
  return {
    nextInput: `${prefix}${insertion}${suffix}`,
    nextCursor: safeStart + insertion.length,
  };
}

function imageFingerprint(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer({
  inputEnabled,
  sessionEnded,
  liveSessionId,
  inputHistory = [],
  canCreateSession = false,
  supportsImageInputs,
  interactiveMode,
  isSubmitting,
  onSubmit,
  canInterrupt = false,
  isInterrupting = false,
  restoredInput = null,
  onRestoredInputConsumed,
  onInterrupt,
}, ref) {
  const showStopButton = canInterrupt;
  const [input, setInput] = useState("");
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [attachmentMessage, setAttachmentMessage] = useState<string | null>(null);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [cursorIndex, setCursorIndex] = useState(0);
  const [completionMode, setCompletionMode] = useState<CompletionMode | null>(null);
  const [completionItems, setCompletionItems] = useState<CompletionItem[]>([]);
  const [completionOpen, setCompletionOpen] = useState(false);
  const [completionLoading, setCompletionLoading] = useState(false);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [completionStatusMessage, setCompletionStatusMessage] = useState<string | null>(null);
  const [completionSelectedIndex, setCompletionSelectedIndex] = useState(0);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [historyDraft, setHistoryDraft] = useState<string | null>(null);
  const completionRequestIdRef = useRef(0);
  const activeCompletionRef = useRef<{
    mode: CompletionMode | null;
    query: string | null;
  }>({ mode: null, query: null });
  const pendingImagesRef = useRef<PendingImage[]>([]);
  const refocusAfterSubmitRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<ImageFileInput>(null);

  useImperativeHandle(ref, () => ({
    focus: () => textareaRef.current?.focus(),
  }));

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const canSend =
    (Boolean(liveSessionId) || canCreateSession) && inputEnabled && !sessionEnded && !isSubmitting;
  const shellInput = input.trimStart();
  const isShellMode = useMemo(() => input.trimStart().startsWith("!"), [input]);
  const skillNames = useSkillCatalog();
  const fileTokens = useMemo(
    () => collectComposerFileTokens(input, isShellMode),
    [input, isShellMode],
  );
  const { isFileKnown } = useFileExistence(fileTokens);
  const shellCommandPreview = shellInput.slice(1).trim();
  const isActionMenuOpen = canSend && !isShellMode && actionMenuOpen;
  const highlightSegments = parseComposerHighlightSegments(input, {
    skillNames,
    isFileKnown,
    isShellMode,
  });
  const activeSlashCommand = parseActiveSlashCommand(input, cursorIndex);
  const activeMention = activeSlashCommand
    ? null
    : parseActiveMention(input, cursorIndex);
  const activeSkillTag = activeSlashCommand || activeMention || isShellMode
    ? null
    : parseActiveSkillTag(input, cursorIndex);
  const activeCompletionMode = activeSlashCommand
    ? "slash"
    : activeMention
      ? "mention"
      : activeSkillTag
        ? "skill"
        : null;
  const activeCompletionQuery = activeSlashCommand?.query ?? activeMention?.query ?? activeSkillTag?.query ?? null;

  const closeCompletions = useCallback(() => {
    completionRequestIdRef.current += 1;
    setCompletionMode(null);
    setCompletionItems([]);
    setCompletionOpen(false);
    setCompletionLoading(false);
    setCompletionError(null);
    setCompletionStatusMessage(null);
    setCompletionSelectedIndex(0);
  }, []);

  const resetHistoryBrowsing = useCallback(() => {
    setHistoryIndex(null);
    setHistoryDraft(null);
  }, []);

  const syncCursor = useCallback(() => {
    setCursorIndex(textareaRef.current?.selectionStart ?? 0);
  }, []);

  const syncHighlightScroll = useCallback(() => {
    if (!textareaRef.current || !highlightRef.current) return;
    highlightRef.current.scrollTop = textareaRef.current.scrollTop;
    highlightRef.current.scrollLeft = textareaRef.current.scrollLeft;
  }, []);

  useEffect(() => {
    activeCompletionRef.current = {
      mode: activeCompletionMode,
      query: activeCompletionQuery,
    };
  }, [activeCompletionMode, activeCompletionQuery]);

  useEffect(() => {
    syncHighlightScroll();
  }, [input, syncHighlightScroll]);

  const applyInputState = useCallback(
    (nextInput: string, nextCursor: number) => {
      setInput(nextInput);
      setCursorIndex(nextCursor);
      closeCompletions();

      window.requestAnimationFrame(() => {
        const nextElement = textareaRef.current;
        if (!nextElement) return;
        nextElement.focus();
        nextElement.selectionStart = nextCursor;
        nextElement.selectionEnd = nextCursor;
        autoResize();
      });
    },
    [autoResize, closeCompletions],
  );

  const applyHistoryInput = useCallback(
    (nextInput: string, shouldExitHistory = false) => {
      setInput(nextInput);
      setCursorIndex(nextInput.length);
      if (shouldExitHistory) {
        resetHistoryBrowsing();
      }
      closeCompletions();

      window.requestAnimationFrame(() => {
        const nextElement = textareaRef.current;
        if (!nextElement) return;
        nextElement.focus();
        nextElement.selectionStart = nextInput.length;
        nextElement.selectionEnd = nextInput.length;
        autoResize();
      });
    },
    [autoResize, closeCompletions, resetHistoryBrowsing],
  );

  const buildMentionReplacement = useCallback(
    (
      item: FileMentionItem,
      currentText: string,
      currentCursor: number,
    ): { nextInput: string; nextCursor: number } | null => {
      const currentMention = parseActiveMention(currentText, currentCursor);
      if (!currentMention) {
        return null;
      }

      const escapedPath = escapeMentionPath(item.path);
      return replaceTextRange(
        currentText,
        currentMention.start,
        currentMention.end,
        `@${escapedPath}`,
      );
    },
    [],
  );

  const buildSkillReplacement = useCallback(
    (
      item: SkillMentionItem,
      currentText: string,
      currentCursor: number,
    ): { nextInput: string; nextCursor: number } | null => {
      const currentSkill = parseActiveSkillTag(currentText, currentCursor);
      if (!currentSkill) {
        return null;
      }

      return replaceTextRange(
        currentText,
        currentSkill.start,
        currentSkill.end,
        `$${item.name}`,
      );
    },
    [],
  );

  const buildSlashReplacement = useCallback(
    (
      item: SlashCommandItem,
      currentText: string,
      currentCursor: number,
    ): { nextInput: string; nextCursor: number } | null => {
      const currentSlash = parseActiveSlashCommand(currentText, currentCursor);
      if (!currentSlash) {
        return null;
      }

      return replaceTextRange(currentText, 0, currentSlash.end, item.name);
    },
    [],
  );

  const applyCompletion = useCallback(
    (
      item: CompletionItem,
      currentText?: string,
      currentCursor?: number,
    ): { nextInput: string; nextCursor: number } | null => {
      const textValue = currentText ?? textareaRef.current?.value ?? input;
      const cursorValue =
        currentCursor ?? textareaRef.current?.selectionStart ?? cursorIndex;
      const nextState =
        item.kind === "mention"
          ? buildMentionReplacement(item.mention, textValue, cursorValue)
          : item.kind === "skill"
            ? buildSkillReplacement(item.skill, textValue, cursorValue)
            : buildSlashReplacement(item.command, textValue, cursorValue);
      if (!nextState) {
        return null;
      }

      resetHistoryBrowsing();
      applyInputState(nextState.nextInput, nextState.nextCursor);
      return nextState;
    },
    [applyInputState, buildMentionReplacement, buildSkillReplacement, buildSlashReplacement, cursorIndex, input, resetHistoryBrowsing],
  );

  const appendFiles = useCallback(
    (files: File[], source: PendingImage["source"]) => {
      if (!supportsImageInputs) {
        setAttachmentMessage("The current provider does not support image inputs.");
        return;
      }

      const nextFiles = files.filter((file) => SUPPORTED_IMAGE_TYPES.has(file.type));
      if (nextFiles.length === 0) {
        setAttachmentMessage("Only PNG, JPEG, and WEBP images are supported.");
        return;
      }

      setPendingImages((current) => {
        const seen = new Set(current.map((item) => imageFingerprint(item.file)));
        const additions = nextFiles
          .filter((file) => {
            const fingerprint = imageFingerprint(file);
            if (seen.has(fingerprint)) {
              return false;
            }
            seen.add(fingerprint);
            return true;
          })
          .map((file) => ({
            id: `${source}-${crypto.randomUUID()}`,
            file,
            previewUrl: URL.createObjectURL(file),
            source,
          }));
        if (additions.length === 0) {
          return current;
        }
        return [...current, ...additions];
      });
      setAttachmentMessage(null);
    },
    [supportsImageInputs],
  );

  useEffect(() => {
    pendingImagesRef.current = pendingImages;
  }, [pendingImages]);

  useEffect(() => {
    if (!restoredInput) {
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      resetHistoryBrowsing();
      setInput(restoredInput);
      setCursorIndex(restoredInput.length);
      onRestoredInputConsumed?.();
      const element = textareaRef.current;
      if (!element) return;
      element.focus();
      element.selectionStart = restoredInput.length;
      element.selectionEnd = restoredInput.length;
      autoResize();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [autoResize, onRestoredInputConsumed, resetHistoryBrowsing, restoredInput]);

  const inputHistorySignature = useMemo(() => JSON.stringify(inputHistory), [inputHistory]);
  const inputHistorySignatureRef = useRef(inputHistorySignature);

  useEffect(() => {
    if (inputHistorySignatureRef.current === inputHistorySignature) {
      return undefined;
    }

    inputHistorySignatureRef.current = inputHistorySignature;
    if (historyIndex === null && historyDraft === null) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      if (historyIndex !== null) {
        applyHistoryInput(historyDraft ?? "", true);
        return;
      }
      resetHistoryBrowsing();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [
    applyHistoryInput,
    historyDraft,
    historyIndex,
    inputHistorySignature,
    resetHistoryBrowsing,
  ]);

  useEffect(() => {
    if (!refocusAfterSubmitRef.current || !canSend) {
      return undefined;
    }

    refocusAfterSubmitRef.current = false;
    const animationFrame = window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [canSend]);

  useEffect(() => {
    return () => {
      for (const image of pendingImagesRef.current) {
        URL.revokeObjectURL(image.previewUrl);
      }
    };
  }, []);

  const clearPendingImages = useCallback(() => {
    setPendingImages((current) => {
      for (const image of current) {
        URL.revokeObjectURL(image.previewUrl);
      }
      return [];
    });
  }, []);

  const removePendingImage = useCallback((imageId: string) => {
    setPendingImages((current) => {
      const target = current.find((image) => image.id === imageId);
      if (target) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return current.filter((image) => image.id !== imageId);
    });
  }, []);

  const openImagePicker = useCallback(() => {
    if (!canSend || isShellMode) {
      return;
    }

    if (!supportsImageInputs) {
      setAttachmentMessage("The current provider does not support image inputs.");
      return;
    }

    setActionMenuOpen(false);
    const inputElement = fileInputRef.current;
    if (!inputElement) {
      return;
    }

    if (typeof inputElement.showPicker === "function") {
      inputElement.showPicker();
      return;
    }

    inputElement.click();
  }, [canSend, isShellMode, supportsImageInputs]);

  const submitValue = useCallback(
    async (textValue: string) => {
      const trimmed = textValue.trim();
      if (!trimmed && pendingImages.length === 0) return;
      if (trimmed.startsWith("!") && pendingImages.length > 0) {
        setAttachmentMessage(
          "Shell commands cannot include image attachments.",
        );
        return;
      }

      try {
        refocusAfterSubmitRef.current = true;
        await onSubmit({
          text: trimmed,
          images: pendingImages.map((image) => image.file),
        });
        clearPendingImages();
        resetHistoryBrowsing();
        setInput("");
        setAttachmentMessage(null);
        setCursorIndex(0);
        closeCompletions();
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
      } catch (error) {
        refocusAfterSubmitRef.current = false;
        setAttachmentMessage(
          error instanceof Error ? error.message : "Unable to send the message.",
        );
      }
    },
    [clearPendingImages, closeCompletions, onSubmit, pendingImages, resetHistoryBrowsing],
  );

  useEffect(() => {
    if (!canSend || activeCompletionMode === null || activeCompletionQuery === null) {
      completionRequestIdRef.current += 1;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- completion UI must reset immediately when the query becomes invalid; deferring this causes stale suggestions to flash.
      closeCompletions();
      return undefined;
    }

    setCompletionOpen(true);
    setCompletionMode(activeCompletionMode);
    setCompletionError(null);
    setCompletionStatusMessage(null);
    setCompletionLoading(true);
    setCompletionItems([]);
    setCompletionSelectedIndex(0);

    const requestId = completionRequestIdRef.current + 1;
    completionRequestIdRef.current = requestId;
    const requestMode = activeCompletionMode;
    const requestQuery = activeCompletionQuery;
    let cancelled = false;
    let timeoutId: number | undefined;

    const isCurrentRequest = () =>
      !cancelled &&
      completionRequestIdRef.current === requestId &&
      activeCompletionRef.current.mode === requestMode &&
      activeCompletionRef.current.query === requestQuery;

    const scheduleSearch = (delayMs: number) => {
      timeoutId = window.setTimeout(() => {
        void runSearch();
      }, delayMs);
    };

    const runSearch = async () => {
      if (!isCurrentRequest()) return;
      try {
        const payload =
          requestMode === "slash"
            ? {
                items: (await searchSlashCommands(requestQuery, 8)).map(
                  (command): CompletionItem => ({
                    kind: "slash",
                    key: command.name,
                    command,
                  }),
                ),
                loading: false,
                statusMessage: null,
                errorMessage: null,
                shouldPoll: false,
              }
            : requestMode === "skill"
              ? await searchSkillMentions(requestQuery, 8).then((result) => ({
                  items: result.items.map(
                    (skill): CompletionItem => ({
                      kind: "skill",
                      key: skill.name,
                      skill,
                    }),
                  ),
                  loading: false,
                  statusMessage: null,
                  errorMessage: null,
                  shouldPoll: false,
                }))
              : await searchFileMentions(requestQuery, 8).then((result) => ({
                  items: result.items.map(
                    (mention): CompletionItem => ({
                      kind: "mention",
                      key: mention.path,
                      mention,
                    }),
                  ),
                  loading: result.scan_status === "scanning" && result.items.length === 0,
                  statusMessage: result.is_stale
                    ? "Refreshing file index..."
                    : result.scan_status === "scanning"
                      ? "Indexing files..."
                      : null,
                  errorMessage:
                    result.scan_status === "failed"
                      ? result.error ?? "Unable to index workspace files"
                      : null,
                  shouldPoll: result.scan_status === "scanning",
                }));
        if (!isCurrentRequest()) return;
        setCompletionItems(payload.items);
        setCompletionLoading(payload.loading);
        setCompletionStatusMessage(payload.statusMessage);
        setCompletionError(payload.errorMessage);
        setCompletionSelectedIndex((previousIndex) =>
          payload.items.length === 0
            ? 0
            : Math.min(previousIndex, payload.items.length - 1),
        );
        if (payload.shouldPoll) {
          scheduleSearch(FILE_MENTION_POLL_INTERVAL_MS);
        }
      } catch {
        if (!isCurrentRequest()) return;
        setCompletionLoading(false);
        setCompletionStatusMessage(null);
        setCompletionError(
          requestMode === "slash"
            ? "Unable to load commands"
            : requestMode === "skill"
              ? "Unable to load skills"
              : "Unable to load files",
        );
      }
    };

    scheduleSearch(activeCompletionMode === "slash" ? 60 : 120);

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [
    activeCompletionMode,
    activeCompletionQuery,
    canSend,
    closeCompletions,
  ]);

  const handleSubmit = async (event?: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event?.preventDefault();
    await submitValue(input);
  };

  const handleSlashEnter = useCallback(async () => {
    const currentText = textareaRef.current?.value ?? input;
    const currentCursor = textareaRef.current?.selectionStart ?? cursorIndex;
    const selectedCompletion =
      completionMode === "slash"
        ? (completionItems[completionSelectedIndex] ?? completionItems[0])
        : undefined;

    if (selectedCompletion?.kind === "slash") {
      const nextState = buildSlashReplacement(
        selectedCompletion.command,
        currentText,
        currentCursor,
      );
      if (nextState) {
        await submitValue(nextState.nextInput);
        return;
      }
    }

    if (activeSlashCommand) {
      try {
        const commands = await searchSlashCommands(activeSlashCommand.query, 8);
        const firstMatch = commands[0];
        if (firstMatch) {
          const nextState = buildSlashReplacement(
            firstMatch,
            currentText,
            currentCursor,
          );
          if (nextState) {
            await submitValue(nextState.nextInput);
            return;
          }
        }
      } catch {
        // Fall back to submitting the current slash input unchanged.
      }
    }

    await submitValue(currentText);
  }, [
    activeSlashCommand,
    buildSlashReplacement,
    completionItems,
    completionMode,
    completionSelectedIndex,
    cursorIndex,
    input,
    submitValue,
  ]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (completionOpen) {
      const hasCompletionItems = completionItems.length > 0;
      if (hasCompletionItems && event.key === "ArrowDown") {
        event.preventDefault();
        setCompletionSelectedIndex((prev) => (prev + 1) % completionItems.length);
        return;
      }
      if (!hasCompletionItems && event.key === "ArrowDown") {
        event.preventDefault();
        return;
      }
      if (hasCompletionItems && event.key === "ArrowUp") {
        event.preventDefault();
        setCompletionSelectedIndex(
          (prev) => (prev - 1 + completionItems.length) % completionItems.length,
        );
        return;
      }
      if (!hasCompletionItems && event.key === "ArrowUp") {
        event.preventDefault();
        return;
      }
      if (hasCompletionItems && event.key === "Tab") {
        event.preventDefault();
        void applyCompletion(
          completionItems[completionSelectedIndex] ?? completionItems[0],
        );
        return;
      }
      if (event.key === "Enter" && !event.shiftKey && completionMode === "slash") {
        event.preventDefault();
        void handleSlashEnter();
        return;
      }
      if (hasCompletionItems && event.key === "Enter") {
        event.preventDefault();
        void applyCompletion(
          completionItems[completionSelectedIndex] ?? completionItems[0],
        );
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeCompletions();
        return;
      }
    }

    const hasModifier = event.altKey || event.ctrlKey || event.metaKey || event.shiftKey;
    if (!hasModifier && event.key === "ArrowUp" && inputHistory.length > 0 && pendingImages.length === 0) {
      const historyMatchesCurrentInput = inputHistorySignatureRef.current === inputHistorySignature;
      const activeHistoryIndex = historyMatchesCurrentInput ? historyIndex : null;
      const element = event.currentTarget;
      const selectionStart = element.selectionStart ?? 0;
      const cursorIsOnFirstLine = element.value.lastIndexOf("\n", Math.max(0, selectionStart - 1)) === -1;
      if (activeHistoryIndex !== null || input.length === 0 || cursorIsOnFirstLine) {
        event.preventDefault();
        const nextIndex = activeHistoryIndex === null
          ? inputHistory.length - 1
          : Math.max(0, activeHistoryIndex - 1);
        if (activeHistoryIndex === null) {
          inputHistorySignatureRef.current = inputHistorySignature;
          setHistoryDraft(input);
        }
        setHistoryIndex(nextIndex);
        applyHistoryInput(inputHistory[nextIndex] ?? "");
        return;
      }
    }

    const historyMatchesCurrentInput = inputHistorySignatureRef.current === inputHistorySignature;
    const activeHistoryIndex = historyMatchesCurrentInput ? historyIndex : null;
    if (!hasModifier && event.key === "ArrowDown" && activeHistoryIndex !== null) {
      const activeHistoryDraft = historyMatchesCurrentInput ? historyDraft : null;
      event.preventDefault();
      const nextIndex = activeHistoryIndex + 1;
      if (nextIndex < inputHistory.length) {
        setHistoryIndex(nextIndex);
        applyHistoryInput(inputHistory[nextIndex] ?? "");
      } else {
        applyHistoryInput(activeHistoryDraft ?? "", true);
      }
      return;
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitValue(input);
    }
  };

  const handleTextareaPaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      const clipboardImages = Array.from(event.clipboardData.items)
        .filter((item) => item.kind === "file")
        .map((item) => item.getAsFile())
        .filter((file): file is File => file !== null);
      if (clipboardImages.length === 0) {
        return;
      }
      event.preventDefault();
      if (isShellMode) {
        setAttachmentMessage("Images cannot be attached to shell commands.");
        return;
      }
      appendFiles(clipboardImages, "clipboard");
    },
    [appendFiles, isShellMode],
  );

  const showCompletionStatus = completionStatusMessage !== null && completionItems.length > 0;
  const showCompletionEmptyState =
    completionItems.length === 0 &&
    (completionLoading || completionError !== null || completionOpen);
  const completionEmptyText = completionError ?? (completionLoading
    ? completionStatusMessage ??
      (completionMode === "slash"
        ? "Searching commands..."
        : completionMode === "skill"
          ? "Searching skills..."
          : "Searching files...")
    : completionStatusMessage ??
      (completionMode === "slash"
        ? "No matching commands"
        : completionMode === "skill"
          ? "No matching skills"
          : "No matching files"));
  const completionLabel =
    completionMode === "slash"
      ? "Slash command suggestions"
      : completionMode === "skill"
        ? "Skill suggestions"
        : "Workspace file suggestions";
  const attachmentStatus =
    attachmentMessage ??
    (pendingImages.length > 0
      ? `${pendingImages.length} image${pendingImages.length === 1 ? "" : "s"} attached`
      : null);
  const inputRowClassName = cn(
    "composer__input-row",
    isShellMode && "composer__input-row--shell",
    interactiveMode && "composer__input-row--interactive",
  );

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        void handleSubmit(event);
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        name="image-upload"
        accept="image/png,image/jpeg,image/webp"
        multiple
        hidden
        onChange={(event) => {
          const files = event.target.files ? Array.from(event.target.files) : [];
          appendFiles(files, "picker");
          event.target.value = "";
        }}
      />

      <div className={inputRowClassName}>
        <DropdownMenu
          open={isActionMenuOpen}
          onOpenChange={(open) => setActionMenuOpen(canSend && !isShellMode && open)}
        >
          <div className="composer__action-menu">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="composer__action-tooltip-trigger">
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      className="composer__action-trigger"
                      disabled={!canSend || isShellMode}
                      aria-label="Actions"
                    >
                      <PlusIcon />
                    </Button>
                  </DropdownMenuTrigger>
                </span>
              </TooltipTrigger>
              <TooltipContent side="top">
                {isShellMode ? "Images cannot be attached to shell commands" : "Actions"}
              </TooltipContent>
            </Tooltip>
          </div>
          <DropdownMenuContent className="composer__action-popover" align="start">
            <DropdownMenuGroup>
              <DropdownMenuItem
                className="composer__action-item"
                onSelect={(event) => {
                  event.preventDefault();
                  openImagePicker();
                }}
                disabled={!supportsImageInputs}
              >
                <ImageIcon />
                <span className="composer__action-item-label">Image</span>
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        {isShellMode ? (
          <div className="composer__mode-pill composer__mode-pill--shell" aria-label="Shell command mode">
            <TerminalIcon data-icon="inline-start" />
            <span>Shell</span>
          </div>
        ) : null}
        <InputGroup className="composer__textarea-wrap">
          <div ref={highlightRef} className="composer__textarea-highlights" aria-hidden="true">
            {highlightSegments.map((segment, index) => (
              segment.kind === "text" ? (
                <span key={`highlight-${index}`}>{segment.text}</span>
              ) : (
                <span
                  key={`highlight-${index}`}
                  className={`composer__textarea-highlight composer__textarea-highlight--${segment.kind}`}
                >
                  {segment.text}
                </span>
              )
            ))}
          </div>
          <InputGroupTextarea
            ref={textareaRef}
            name="message"
            aria-label="Message"
            className="composer__textarea"
            value={input}
            onChange={(event) => {
              resetHistoryBrowsing();
              setInput(event.target.value);
              setCursorIndex(event.target.selectionStart ?? event.target.value.length);
              autoResize();
            }}
            onClick={syncCursor}
            onKeyDown={handleKeyDown}
            onKeyUp={syncCursor}
            onPaste={handleTextareaPaste}
            onScroll={syncHighlightScroll}
            onSelect={syncCursor}
            placeholder={
              sessionEnded
                ? "Start a new session to continue..."
                : isShellMode
                  ? "Run a shell command..."
                  : "Send a message..."
            }
            rows={1}
            disabled={!canSend}
          />
        </InputGroup>
        <InputGroup className="composer__send-group">
          <InputGroupAddon align="inline-end">
            {showStopButton ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="composer__input-tooltip-trigger">
                    <InputGroupButton
                      type="button"
                      aria-label="Interrupt assistant turn"
                      className="composer__stop"
                      disabled={isInterrupting}
                      onClick={onInterrupt}
                      size="icon-sm"
                    >
                      <SquareIcon
                        aria-hidden="true"
                        className="composer__stop-icon"
                        fill="currentColor"
                        strokeWidth={0}
                      />
                    </InputGroupButton>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  {isInterrupting ? "Interrupting current turn…" : "Stop the assistant"}
                </TooltipContent>
              </Tooltip>
            ) : (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="composer__input-tooltip-trigger">
                    <InputGroupButton
                      type="submit"
                      aria-label={isShellMode ? "Run command" : "Send message"}
                      className="composer__send"
                      disabled={!canSend}
                      size="icon-sm"
                    >
                      {isShellMode ? <BadgeDollarSignIcon /> : <ArrowUpIcon />}
                    </InputGroupButton>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  {isShellMode ? "Run command (Enter)" : "Send (Enter)"}
                </TooltipContent>
              </Tooltip>
            )}
          </InputGroupAddon>
        </InputGroup>
      </div>

      {isShellMode ? (
        <div className="composer__mode-status composer__mode-status--shell">
          {shellCommandPreview
            ? "Enter will run this command in the workspace shell."
            : "Shell command mode: type a command after !"}
        </div>
      ) : null}

      {completionOpen ? (
        <div className="composer__completions" role="listbox" aria-label={completionLabel}>
          {completionItems.length > 0 ? (
            completionItems.map((item, index) => (
              <Button
                key={item.key}
                type="button"
                variant="ghost"
                className={`composer__completion-item ${index === completionSelectedIndex ? "composer__completion-item--active" : ""}`}
                onMouseDown={(event) => {
                  event.preventDefault();
                  void applyCompletion(item);
                }}
              >
                <span className="composer__completion-copy">
                  <span className="composer__completion-label">
                    {item.kind === "slash"
                      ? item.command.name
                      : item.kind === "skill"
                        ? `$${item.skill.name}`
                        : `@${item.mention.path}`}
                    {item.kind === "slash" && item.command.description ? (
                      <span className="composer__completion-description">
                        {` (${item.command.description})`}
                      </span>
                    ) : null}
                    {item.kind === "skill" && item.skill.description ? (
                      <span className="composer__completion-description">
                        {` (${item.skill.description})`}
                      </span>
                    ) : null}
                  </span>
                </span>
                {item.kind === "mention" ? (
                  <span
                    className={`composer__completion-kind composer__completion-kind--${item.mention.kind}`}
                  >
                    {item.mention.kind}
                  </span>
                ) : item.kind === "skill" ? (
                  <span className="composer__completion-kind composer__completion-kind--skill">
                    skill
                  </span>
                ) : null}
              </Button>
            ))
          ) : showCompletionEmptyState ? (
            <div className="composer__completion-empty">{completionEmptyText}</div>
          ) : null}
          {showCompletionStatus ? (
            <div className="composer__completion-status">
              {completionStatusMessage}
            </div>
          ) : null}
        </div>
      ) : null}

      {pendingImages.length > 0 ? (
        <div className="composer__attachments" aria-label="Pending image attachments">
          {pendingImages.map((image) => (
            <div key={image.id} className="composer__attachment-card">
              <img
                src={image.previewUrl}
                alt={image.file.name}
                className="composer__attachment-preview"
              />
              <div className="composer__attachment-copy">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="composer__attachment-name">
                      {image.file.name}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{image.file.name}</TooltipContent>
                </Tooltip>
                <span className="composer__attachment-meta">
                  {Math.max(1, Math.round(image.file.size / 1024))} KB
                </span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="composer__attachment-remove"
                onClick={() => removePendingImage(image.id)}
                aria-label={`Remove ${image.file.name}`}
                disabled={!canSend}
              >
                <XIcon aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      {attachmentStatus ? (
        <div
          className={`composer__attachment-status ${attachmentMessage ? "composer__attachment-status--error" : ""}`}
        >
          {attachmentStatus}
        </div>
      ) : null}

    </form>
  );
});
