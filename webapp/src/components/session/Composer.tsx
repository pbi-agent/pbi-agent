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
  ImageIcon,
  PlusIcon,
  TerminalIcon,
  XIcon,
} from "lucide-react";
import { searchSlashCommands } from "../../api";
import type { AgentMentionItem, FileMentionItem, QueuedFollowUp, SkillMentionItem, SlashCommandItem } from "../../types";
import { cn } from "../../lib/utils";
import { serializeReplyMessage, type ReplySnippet } from "../../lib/replySnippets";
import { getComposerDraft, setComposerDraft } from "../../lib/composerDraft";
import { ReplySnippetCard } from "./ReplySnippetCard";
import { createWavRecorder, type WavRecorder } from "../../lib/audioRecorder";
import { DictationWaveform } from "./DictationWaveform";
import {
  ComposerActionButtons,
  isComposerActionShortcut,
  useComposerActions,
  type ComposerDictationState,
} from "./ComposerActions";
import { useFileExistence } from "../../hooks/useFileExistence";
import {
  useComposerCompletions,
  type CompletionItem,
} from "../../hooks/useComposerCompletions";
import { useSkillCatalog, useSkillNamesByPath } from "../../hooks/useSkillCatalog";
import { Badge } from "../ui/badge";
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
  InputGroupTextarea,
} from "../ui/input-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

export interface ComposerHandle {
  focus: () => void;
  addReplySnippet: (quote: string, comment: string) => void;
}

interface ComposerProps {
  inputEnabled: boolean;
  sessionEnded: boolean;
  liveSessionId: string | null;
  workspaceKey?: string | null;
  workspaceFileIndexGeneration?: string | null;
  workspaceFileIndexRevision?: number | null;
  /** Chronological oldest-to-newest user input text for the current conversation. */
  inputHistory?: string[];
  canCreateSession?: boolean;
  supportsImageInputs: boolean;
  interactiveMode: boolean;
  isSubmitting: boolean;
  isProcessing?: boolean;
  canQueueFollowUp?: boolean;
  queuedFollowUps?: QueuedFollowUp[];
  queuedFollowUp?: QueuedFollowUp | null;
  onSubmit: (payload: { text: string; images: File[]; followUpDelivery?: FollowUpTiming }) => Promise<void>;
  onSendQueuedFollowUp?: (id: string) => Promise<void> | void;
  onCancelQueuedFollowUp?: (id: string) => Promise<void> | void;
  isSendingQueuedFollowUp?: boolean;
  canInterrupt?: boolean;
  isInterrupting?: boolean;
  dictationAvailable?: boolean;
  dictationUnavailableReason?: string | null;
  onTranscribeDictation?: (file: File) => Promise<string>;
  onEnhancePrompt?: (text: string) => Promise<string>;
  restoredInput?: string | null;
  onRestoredInputConsumed?: () => void;
  onInterrupt?: () => void;
}

type ActiveCompletionRange = {
  start: number;
  end: number;
  query: string;
};

type PendingImage = {
  id: string;
  file: File;
  previewUrl: string;
  source: "picker" | "clipboard";
};

const COMPLETIONS_PANEL_CLASS =
  "absolute inset-x-3 bottom-full md:inset-x-8 z-30 mb-2 flex max-h-96 min-h-11 flex-col gap-px overflow-y-auto overscroll-contain rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg";

type FollowUpTiming = "checkpoint" | "after_finish";

const FOLLOW_UP_OPTIONS: Array<{
  timing: FollowUpTiming;
  label: string;
  description: string;
  badge: string;
  badgeVariant: "outline" | "secondary";
  badgeKind: string;
}> = [
  {
    timing: "checkpoint",
    label: "After next safe checkpoint",
    description: "Send to the live session as soon as pbi-agent can accept queued input.",
    badge: "soon",
    badgeVariant: "outline",
    badgeKind: "project",
  },
  {
    timing: "after_finish",
    label: "After assistant finishes",
    description: "Queue on the backend and send automatically when the current turn is ready.",
    badge: "later",
    badgeVariant: "secondary",
    badgeKind: "built-in",
  },
];

type ImageFileInput = HTMLInputElement & {
  showPicker?: () => void;
};

const SUPPORTED_IMAGE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/heic",
  "image/heif",
]);
const SUPPORTED_IMAGE_EXTENSIONS = [
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".heic",
  ".heif",
];
const TOKEN_BOUNDARY_PATTERN = /[\s()[\]{}'"`,;]/;
const SLASH_COMMAND_COMPLETION_LIMIT = 200;

function slashCommandKindLabel(kind: SlashCommandItem["kind"]): string {
  switch (kind) {
    case "local_command":
      return "built-in";
    case "command":
      return "project";
    case "extension":
      return "extension";
  }
}

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
  | { kind: "mention" | "skill" | "agent"; text: string };

type HighlightValidators = {
  skillNames: Set<string>;
  isFileKnown: (token: string) => boolean;
  isShellMode: boolean;
};

function findNextHighlightCandidate(
  text: string,
  cursor: number,
): { start: number; kind: "mention" | "skill" | "agent"; end: number } | null {
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
      if (text.slice(end, end + 8) === " (agent)") {
        return { start: index, kind: "agent", end: end + 8 };
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
    const shouldHighlight = candidate.kind === "agent" || (
      candidate.kind === "skill"
        ? skillNames.has(tokenText.slice(1))
        : isFileKnown(tokenText.slice(1).replaceAll("\\ ", " "))
    );
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

function isSupportedImageFile(file: File): boolean {
  if (SUPPORTED_IMAGE_TYPES.has(file.type.toLowerCase())) {
    return true;
  }
  const name = file.name.toLowerCase();
  return SUPPORTED_IMAGE_EXTENSIONS.some((extension) => name.endsWith(extension));
}

function dictationErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Microphone permission was denied.";
    }
    if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
      return "No microphone was found.";
    }
  }
  return error instanceof Error ? error.message : fallback;
}

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer({
  inputEnabled,
  sessionEnded,
  liveSessionId,
  workspaceKey = null,
    workspaceFileIndexGeneration = null,
  workspaceFileIndexRevision = null,
  inputHistory = [],
  canCreateSession = false,
  supportsImageInputs,
  interactiveMode,
  isSubmitting,
  isProcessing = false,
  canQueueFollowUp = false,
  queuedFollowUps,
  queuedFollowUp = null,
  onSubmit,
  onSendQueuedFollowUp,
  onCancelQueuedFollowUp,
  isSendingQueuedFollowUp = false,
  canInterrupt = false,
  isInterrupting = false,
  dictationAvailable = false,
  dictationUnavailableReason = "Choose a speech-to-text provider in Settings to use dictation.",
  onTranscribeDictation,
  onEnhancePrompt,
  restoredInput = null,
  onRestoredInputConsumed,
  onInterrupt,
}, ref) {
  const showStopButton = canInterrupt;
  const [input, setInput] = useState(getComposerDraft);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [replySnippets, setReplySnippets] = useState<ReplySnippet[]>([]);
  const [attachmentMessage, setAttachmentMessage] = useState<string | null>(null);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [cursorIndex, setCursorIndex] = useState(() => getComposerDraft().length);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [historyDraft, setHistoryDraft] = useState<string | null>(null);
  const [dictationState, setDictationState] = useState<ComposerDictationState>("idle");
  const [followUpChoicesOpen, setFollowUpChoicesOpen] = useState(false);
  const [followUpSelectedIndex, setFollowUpSelectedIndex] = useState(0);
  const completionItemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const pendingImagesRef = useRef<PendingImage[]>([]);
  const dictationRecorderRef = useRef<WavRecorder | null>(null);
  const refocusAfterSubmitRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<ImageFileInput>(null);

  useImperativeHandle(ref, () => ({
    focus: () => textareaRef.current?.focus(),
    addReplySnippet: (quote: string, comment: string) => {
      setReplySnippets((current) => [
        ...current,
        { id: `reply-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, quote, comment },
      ]);
      textareaRef.current?.focus();
    },
  }));

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const canSend =
    (Boolean(liveSessionId) || canCreateSession) && inputEnabled && !sessionEnded && !isSubmitting;
  const displayedQueuedFollowUps = queuedFollowUps ?? (queuedFollowUp ? [queuedFollowUp] : []);
  const canSendQueuedFollowUpNow = (item: QueuedFollowUp) =>
    Boolean(liveSessionId)
    && !sessionEnded
    && !isSubmitting
    && inputEnabled
    && Boolean(onSendQueuedFollowUp)
    && (item.delivery === "after_finish" || item.kind === "background_result");
  const canDraftFollowUp =
    Boolean(liveSessionId)
    && canQueueFollowUp
    && !inputEnabled
    && !sessionEnded
    && !isSubmitting;
  const shellInput = input.trimStart();
  const isShellMode = useMemo(() => input.trimStart().startsWith("!"), [input]);
  const skillNames = useSkillCatalog();
  const skillNamesByPath = useSkillNamesByPath();
  const fileTokens = useMemo(
    () => collectComposerFileTokens(input, isShellMode),
    [input, isShellMode],
  );
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
  const mentionActivationSequenceRef = useRef(0);
  const mentionActivationRef = useRef<{
    workspaceKey: string | null;
    start: number;
    query: string;
  } | null>(null);
  let activeMentionTokenKey: string | null = null;
  if (activeMention) {
    const previous = mentionActivationRef.current;
    const continuesPreviousToken =
      previous?.workspaceKey === workspaceKey
      && previous.start === activeMention.start
      && (
        activeMention.query.startsWith(previous.query)
        || previous.query.startsWith(activeMention.query)
      );
    if (!continuesPreviousToken) {
      mentionActivationSequenceRef.current += 1;
    }
    activeMentionTokenKey =
      `${workspaceKey ?? ""}:${activeMention.start}:${mentionActivationSequenceRef.current}`;
    mentionActivationRef.current = {
      workspaceKey,
      start: activeMention.start,
      query: activeMention.query,
    };
  } else {
    mentionActivationRef.current = null;
  }
  const {
    completionMode,
    completionItems,
    completionOpen,
    completionLoading,
    completionError,
    completionStatusMessage,
    completionSelectedIndex,
    fileIndexGeneration: observedFileIndexGeneration,
    fileIndexRevision: observedFileIndexRevision,
    setCompletionSelectedIndex,
    closeCompletions,
  } = useComposerCompletions({
    enabled: canSend || canDraftFollowUp,
    mode: activeCompletionMode,
    query: activeCompletionQuery,
    mentionTokenKey: activeMentionTokenKey,
    workspaceKey,
    fileIndexGeneration: workspaceFileIndexGeneration,
  });
  const effectiveFileIndexGeneration =
    observedFileIndexGeneration ?? workspaceFileIndexGeneration;
  const effectiveFileIndexRevision =
    observedFileIndexGeneration === null
      ? workspaceFileIndexRevision
      : observedFileIndexGeneration === workspaceFileIndexGeneration
        && workspaceFileIndexRevision !== null
        && observedFileIndexRevision !== null
        ? Math.max(observedFileIndexRevision, workspaceFileIndexRevision)
        : observedFileIndexRevision;
  const { isFileKnown } = useFileExistence(fileTokens, {
    workspaceKey,
    indexGeneration: effectiveFileIndexGeneration,
    indexRevision: effectiveFileIndexRevision,
  });
  const shellCommandPreview = shellInput.slice(1).trim();
  const highlightSegments = parseComposerHighlightSegments(input, {
    skillNames,
    isFileKnown,
    isShellMode,
  });

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
    syncHighlightScroll();
  }, [input, syncHighlightScroll]);

  useEffect(() => {
    setComposerDraft(input);
  }, [input]);

  // A draft restored on mount needs the textarea grown to fit it.
  useEffect(() => {
    autoResize();
  }, [autoResize]);

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

  const insertDictationTranscript = useCallback(
    (transcript: string) => {
      const trimmedTranscript = transcript.trim();
      if (!trimmedTranscript) {
        setAttachmentMessage("No speech was detected.");
        return;
      }

      const currentInput = textareaRef.current?.value ?? input;
      const separator =
        currentInput.trim().length === 0 || /\s$/.test(currentInput) ? "" : " ";
      const nextInput = `${currentInput}${separator}${trimmedTranscript}`;
      resetHistoryBrowsing();
      setAttachmentMessage(null);
      applyInputState(nextInput, nextInput.length);
    },
    [applyInputState, input, resetHistoryBrowsing],
  );

  const startDictation = useCallback(async () => {
    if (!dictationAvailable || !onTranscribeDictation) {
      setAttachmentMessage(
        dictationUnavailableReason ??
          "Choose a speech-to-text provider in Settings to use dictation.",
      );
      return;
    }

    setAttachmentMessage(null);
    try {
      const recorder = await createWavRecorder();
      dictationRecorderRef.current = recorder;
      setDictationState("recording");
    } catch (error) {
      dictationRecorderRef.current = null;
      setDictationState("idle");
      setAttachmentMessage(
        dictationErrorMessage(error, "Unable to start dictation recording."),
      );
    }
  }, [dictationAvailable, dictationUnavailableReason, onTranscribeDictation]);

  const stopDictation = useCallback(async () => {
    const recorder = dictationRecorderRef.current;
    if (!recorder) {
      setDictationState("idle");
      return;
    }

    dictationRecorderRef.current = null;
    setDictationState("transcribing");
    try {
      const file = await recorder.stop();
      const transcript = await onTranscribeDictation?.(file);
      insertDictationTranscript(transcript ?? "");
    } catch (error) {
      setAttachmentMessage(
        dictationErrorMessage(error, "Unable to transcribe dictation."),
      );
    } finally {
      setDictationState("idle");
    }
  }, [insertDictationTranscript, onTranscribeDictation]);

  const toggleDictation = useCallback(() => {
    if (dictationState === "recording") {
      void stopDictation();
      return;
    }
    if (dictationState === "idle") {
      void startDictation();
    }
  }, [dictationState, startDictation, stopDictation]);

  const getDictationFrequencyData = useCallback(
    () => dictationRecorderRef.current?.getFrequencyData() ?? null,
    [],
  );

  const applyEnhancedPrompt = useCallback(
    (enhancedText: string) => {
      resetHistoryBrowsing();
      applyInputState(enhancedText, enhancedText.length);
    },
    [applyInputState, resetHistoryBrowsing],
  );
  const getCurrentInput = useCallback(
    () => textareaRef.current?.value ?? input,
    [input],
  );

  const composerActions = useComposerActions({
    input,
    hasReplySnippets: replySnippets.length > 0,
    canSend: canSend || canDraftFollowUp,
    isProcessing,
    showStopButton,
    isShellMode,
    dictationState,
    dictationAvailable,
    hasDictationHandler: Boolean(onTranscribeDictation),
    onEnhancePrompt,
    getCurrentInput,
    applyEnhancedPrompt,
    toggleDictation,
  });
  const isPromptEnhancementPending = composerActions.isPromptEnhancementPending;
  const promptEnhancementPending = composerActions.promptEnhancementPending;
  const composerInputAvailable = (canSend || canDraftFollowUp) && !promptEnhancementPending;
  useEffect(() => {
    if (!composerInputAvailable) {
      closeCompletions();
    }
  }, [closeCompletions, composerInputAvailable]);
  const showFollowUpSubmitButton =
    canDraftFollowUp && (input.trim().length > 0 || replySnippets.length > 0);
  const showActionStopButton = showStopButton && !showFollowUpSubmitButton;
  const showFollowUpReadyAnimation =
    isProcessing
    && canDraftFollowUp
    && !isShellMode
    && dictationState !== "recording"
    && !promptEnhancementPending;
  const showProcessingAnimation =
    (isProcessing && !sessionEnded && !canSend && !canDraftFollowUp) || promptEnhancementPending;
  const processingStatusLabel = promptEnhancementPending
    ? "Enhancing prompt"
    : showFollowUpReadyAnimation
      ? "Assistant is working. You can draft a follow-up."
      : "Assistant is processing";
  const isActionMenuOpen =
    composerInputAvailable && !isShellMode && actionMenuOpen;

  // While recording, the textarea (and its key-capture) is replaced by the
  // waveform, so the stop shortcut is handled at the document level instead.
  useEffect(() => {
    if (dictationState !== "recording") return;
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (!isComposerActionShortcut(event) || event.defaultPrevented) return;
      event.preventDefault();
      void stopDictation();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [dictationState, stopDictation]);

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

      // Tagging a skill's SKILL.md becomes the `$skill` tag for that skill.
      const skillName = skillNamesByPath.get(item.path);
      return replaceTextRange(
        currentText,
        currentMention.start,
        currentMention.end,
        skillName ? `$${skillName}` : `@${escapeMentionPath(item.path)}`,
      );
    },
    [skillNamesByPath],
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

  const buildAgentReplacement = useCallback(
    (
      item: AgentMentionItem,
      currentText: string,
      currentCursor: number,
    ): { nextInput: string; nextCursor: number } | null => {
      const currentMention = parseActiveMention(currentText, currentCursor);
      if (!currentMention) {
        return null;
      }

      return replaceTextRange(
        currentText,
        currentMention.start,
        currentMention.end,
        `@${item.name} (agent)`,
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
          : item.kind === "agent"
            ? buildAgentReplacement(item.agent, textValue, cursorValue)
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
    [applyInputState, buildAgentReplacement, buildMentionReplacement, buildSkillReplacement, buildSlashReplacement, cursorIndex, input, resetHistoryBrowsing],
  );

  const appendFiles = useCallback(
    (files: File[], source: PendingImage["source"]) => {
      if (!supportsImageInputs) {
        setAttachmentMessage("The current provider does not support image inputs.");
        return;
      }

      const nextFiles = files.filter(isSupportedImageFile);
      if (nextFiles.length === 0) {
        setAttachmentMessage(
          "Only PNG, JPEG, WEBP, HEIC, and HEIF images are supported.",
        );
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

  useEffect(() => {
    return () => {
      void dictationRecorderRef.current?.cancel();
      dictationRecorderRef.current = null;
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

  const clearComposerDraft = useCallback(() => {
    clearPendingImages();
    setReplySnippets([]);
    resetHistoryBrowsing();
    setInput("");
    setAttachmentMessage(null);
    setCursorIndex(0);
    closeCompletions();
    setFollowUpChoicesOpen(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [clearPendingImages, closeCompletions, resetHistoryBrowsing]);

  useEffect(() => {
    if (followUpChoicesOpen && !canDraftFollowUp) {
      setFollowUpChoicesOpen(false);
    }
  }, [canDraftFollowUp, followUpChoicesOpen]);

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
    if (!composerInputAvailable || isShellMode) {
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
  }, [composerInputAvailable, isShellMode, supportsImageInputs]);

  const submitValue = useCallback(
    async (textValue: string) => {
      if (isPromptEnhancementPending()) return;
      const trimmed = textValue.trim();
      if (!trimmed && replySnippets.length === 0) return;
      if (trimmed.startsWith("!") && replySnippets.length > 0) {
        setAttachmentMessage("Shell commands cannot include reply snippets.");
        return;
      }
      if (trimmed.startsWith("!") && pendingImages.length > 0) {
        setAttachmentMessage(
          "Shell commands cannot include image attachments.",
        );
        return;
      }
      if (!canSend) {
        if (canDraftFollowUp) {
          closeCompletions();
          setFollowUpSelectedIndex(0);
          setFollowUpChoicesOpen(true);
          setAttachmentMessage(null);
        }
        return;
      }

      try {
        refocusAfterSubmitRef.current = true;
        await onSubmit({
          text: serializeReplyMessage(replySnippets, trimmed),
          images: pendingImages.map((image) => image.file),
        });
        clearComposerDraft();
      } catch (error) {
        refocusAfterSubmitRef.current = false;
        setAttachmentMessage(
          error instanceof Error ? error.message : "Unable to send the message.",
        );
      }
    },
    [canDraftFollowUp, canSend, clearComposerDraft, closeCompletions, isPromptEnhancementPending, onSubmit, pendingImages, replySnippets],
  );

  const queueFollowUp = useCallback(
    async (timing: FollowUpTiming) => {
      if (!canDraftFollowUp) {
        setFollowUpChoicesOpen(false);
        return;
      }
      if (!liveSessionId) {
        setFollowUpChoicesOpen(false);
        return;
      }
      const textValue = textareaRef.current?.value ?? input;
      const trimmed = textValue.trim();
      if (!trimmed && replySnippets.length === 0) return;
      if (trimmed.startsWith("!")) {
        setAttachmentMessage("Shell commands cannot be sent as follow-ups while the assistant is processing.");
        setFollowUpChoicesOpen(false);
        return;
      }
      setFollowUpChoicesOpen(false);
      try {
        await onSubmit({
          text: serializeReplyMessage(replySnippets, trimmed),
          images: pendingImages.map((image) => image.file),
          followUpDelivery: timing,
        });
        clearComposerDraft();
      } catch (error) {
        setAttachmentMessage(
          error instanceof Error
            ? error.message
            : "Unable to queue the follow-up.",
        );
      }
    },
    [canDraftFollowUp, clearComposerDraft, input, liveSessionId, onSubmit, pendingImages, replySnippets],
  );

  useEffect(() => {
    if (!completionOpen) return;
    completionItemRefs.current[completionSelectedIndex]?.scrollIntoView?.({
      block: "nearest",
    });
  }, [completionItems, completionOpen, completionSelectedIndex]);

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
        const commands = await searchSlashCommands(
          activeSlashCommand.query,
          SLASH_COMMAND_COMPLETION_LIMIT,
        );
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

  const activateFollowUpChoice = (timing: FollowUpTiming) => {
    if (!canDraftFollowUp) {
      setFollowUpChoicesOpen(false);
      return;
    }
    void queueFollowUp(timing);
  };

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

    if (followUpChoicesOpen) {
      if (event.key === "ArrowDown" && !event.altKey && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        setFollowUpSelectedIndex((prev) => (prev + 1) % FOLLOW_UP_OPTIONS.length);
        return;
      }
      if (event.key === "ArrowUp" && !event.altKey && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        setFollowUpSelectedIndex(
          (prev) => (prev - 1 + FOLLOW_UP_OPTIONS.length) % FOLLOW_UP_OPTIONS.length,
        );
        return;
      }
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        activateFollowUpChoice(
          FOLLOW_UP_OPTIONS[followUpSelectedIndex]?.timing ?? FOLLOW_UP_OPTIONS[0].timing,
        );
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setFollowUpChoicesOpen(false);
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

  const completionListStatus = completionError ?? completionStatusMessage;
  const showCompletionStatus =
    completionListStatus !== null && completionItems.length > 0;
  const showCompletionEmptyState =
    completionItems.length === 0 &&
    (completionLoading || completionError !== null || completionOpen);
  const completionEmptyText = completionError ?? (completionLoading
    ? completionStatusMessage ??
      (completionMode === "slash"
        ? "Searching commands..."
        : completionMode === "skill"
          ? "Searching skills..."
          : "Searching files and agents...")
    : completionStatusMessage ??
      (completionMode === "slash"
        ? "No matching commands"
        : completionMode === "skill"
          ? "No matching skills"
          : "No matching files or agents"));
  const completionLabel =
    completionMode === "slash"
      ? "Slash command suggestions"
      : completionMode === "skill"
        ? "Skill suggestions"
        : "Workspace file and agent suggestions";
  const attachmentStatus =
    attachmentMessage ??
    (pendingImages.length > 0
      ? `${pendingImages.length} image${pendingImages.length === 1 ? "" : "s"} attached`
      : null);
  const handleComposerKeyDownCapture = (event: KeyboardEvent<HTMLFormElement>) => {
    composerActions.handleShortcut(event);
  };

  return (
    <form
      data-composer=""
      className="relative mx-auto w-full max-w-6xl shrink-0 px-3 py-2 md:px-8"
      onKeyDownCapture={handleComposerKeyDownCapture}
      onSubmit={(event) => {
        void handleSubmit(event);
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        name="image-upload"
              accept="image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif"
        multiple
        hidden
        onChange={(event) => {
          const files = event.target.files ? Array.from(event.target.files) : [];
          appendFiles(files, "picker");
          event.target.value = "";
        }}
      />

      <div
        data-composer-input-row=""
        data-shell={isShellMode ? "" : undefined}
        data-interactive={interactiveMode ? "" : undefined}
        data-processing={showProcessingAnimation ? "" : undefined}
        data-follow-up-ready={showFollowUpReadyAnimation ? "" : undefined}
        data-recording={dictationState === "recording" ? "" : undefined}
        className={cn(
          "relative rounded-lg",
          isShellMode && "*:data-[slot=input-group]:border-chart-4",
          interactiveMode && "*:data-[slot=input-group]:border-primary",
          showProcessingAnimation && "*:data-[slot=input-group]:border-primary/40",
          showFollowUpReadyAnimation && "animate-pulse",
          dictationState === "recording" && "*:data-[slot=input-group]:border-destructive/50",
        )}
      >
        <InputGroup className="h-auto min-h-12">
        <InputGroupAddon align="inline-start">
        <DropdownMenu
          open={isActionMenuOpen}
          onOpenChange={(open) => setActionMenuOpen(composerInputAvailable && !isShellMode && open)}
        >
          <div className="shrink-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <span data-action-tooltip-trigger="" className="inline-flex shrink-0">
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      disabled={!composerInputAvailable || isShellMode}
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
          <DropdownMenuContent className="min-w-40" align="start">
            <DropdownMenuGroup>
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault();
                  openImagePicker();
                }}
                disabled={!supportsImageInputs}
              >
                <ImageIcon />
                <span>Image</span>
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        {isShellMode ? (
          <Badge variant="warning" aria-label="Shell command mode">
            <TerminalIcon data-icon="inline-start" />
            <span>Shell</span>
          </Badge>
        ) : null}
        </InputGroupAddon>
        {dictationState === "recording" ? (
          <DictationWaveform
            getFrequencyData={getDictationFrequencyData}
            label="Recording audio… Ctrl+Space to stop"
          />
        ) : (
        <div className="relative flex min-w-0 flex-1 self-center [&_textarea]:text-transparent [&_textarea]:caret-foreground [&_textarea]:wrap-anywhere [&_textarea]:selection:bg-primary/25">
          <div
            ref={highlightRef}
            className="pointer-events-none absolute inset-0 overflow-hidden px-2.5 py-2 text-base whitespace-pre-wrap wrap-anywhere text-foreground md:text-sm"
            aria-hidden="true"
          >
            {highlightSegments.map((segment, index) => (
              segment.kind === "text" ? (
                <span key={`highlight-${index}`}>{segment.text}</span>
              ) : (
                <span
                  key={`highlight-${index}`}
                  data-highlight={segment.kind}
                  className={cn(
                    // Same pill as timeline tags. The overlay must keep the
                    // textarea's glyph positions, so padding and border are
                    // painted outside the box (ring + offset outline).
                    "rounded-full box-decoration-clone ring-2 outline outline-offset-2",
                    segment.kind === "skill"
                      ? "bg-usage-violet/10 text-usage-violet ring-usage-violet/10 outline-usage-violet/30"
                      : "bg-primary/10 text-primary ring-primary/10 outline-primary/30",
                  )}
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
            className="relative z-10 max-h-50 min-h-5 field-sizing-fixed overflow-y-auto"
            value={input}
            onChange={(event) => {
              resetHistoryBrowsing();
              setInput(event.target.value);
              composerActions.clearPromptEnhancementError();
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
                  : isProcessing
                    ? "Send a follow-up..."
                    : "Send a message..."
            }
            rows={1}
            disabled={!composerInputAvailable}
          />
        </div>
        )}
        {showProcessingAnimation || showFollowUpReadyAnimation ? (
          <span className="sr-only" role="status" aria-live="polite">
            {processingStatusLabel}
          </span>
        ) : null}
        {dictationState === "recording" ? (
          <span className="sr-only" role="status" aria-live="polite">
            Recording dictation
          </span>
        ) : dictationState === "transcribing" ? (
          <span className="sr-only" role="status" aria-live="polite">
            Transcribing dictation
          </span>
        ) : null}
        <ComposerActionButtons
          controller={composerActions}
          showStopButton={showActionStopButton}
          isInterrupting={isInterrupting}
          onInterrupt={onInterrupt}
          isShellMode={isShellMode}
          dictationState={dictationState}
          dictationUnavailableReason={dictationUnavailableReason}
          toggleDictation={toggleDictation}
        />
        </InputGroup>
      </div>

      {isShellMode ? (
        <div className="mt-2 truncate px-2 text-xs text-muted-foreground">
          {shellCommandPreview
            ? "Enter will run this command in the workspace shell."
            : "Shell command mode: type a command after !"}
        </div>
      ) : null}

      {completionOpen ? (
        <div
          className={COMPLETIONS_PANEL_CLASS}
          role="listbox"
          aria-label={completionLabel}
        >
          {completionItems.length > 0 ? (
            completionItems.map((item, index) => (
              <Button
                key={item.key}
                ref={(element) => {
                  completionItemRefs.current[index] = element;
                }}
                type="button"
                variant={index === completionSelectedIndex ? "secondary" : "ghost"}
                role="option"
                aria-selected={index === completionSelectedIndex}
                data-active={index === completionSelectedIndex ? "" : undefined}
                className="h-auto min-h-8 w-full shrink-0 justify-between text-left"
                onMouseDown={(event) => {
                  event.preventDefault();
                  void applyCompletion(item);
                }}
              >
                <span className="flex min-w-0 items-center">
                  <span className="min-w-0 truncate font-mono text-xs">
                    {item.kind === "slash"
                      ? item.command.name
                      : item.kind === "skill"
                        ? `$${item.skill.name}`
                        : item.kind === "agent"
                          ? `@${item.agent.name} (agent)`
                        : `@${item.mention.path}`}
                    {item.kind === "slash" && item.command.description ? (
                      <span className="font-sans font-normal text-muted-foreground">
                        {` (${item.command.description})`}
                      </span>
                    ) : null}
                    {item.kind === "skill" && item.skill.description ? (
                      <span className="font-sans font-normal text-muted-foreground">
                        {` (${item.skill.description})`}
                      </span>
                    ) : null}
                  </span>
                </span>
                {item.kind === "mention" ? (
                  <Badge
                    variant={item.mention.kind === "image" ? "secondary" : "outline"}
                    data-kind={item.mention.kind}
                  >
                    {item.mention.kind}
                  </Badge>
                ) : item.kind === "agent" ? (
                  <Badge variant="outline" data-kind="agent">
                    {item.agent.enabled === false ? "disabled agent" : "agent"}
                  </Badge>
                ) : item.kind === "skill" ? (
                  <Badge variant="outline" data-kind="skill">
                    {item.skill.enabled === false ? "disabled skill" : "skill"}
                  </Badge>
                ) : item.kind === "slash" ? (
                  <Badge
                    variant={
                      item.command.kind === "local_command"
                        ? "secondary"
                        : item.command.kind === "command"
                          ? "outline"
                          : "warning"
                    }
                    data-kind={
                      item.command.kind === "local_command"
                        ? "built-in"
                        : item.command.kind === "command"
                          ? "project"
                          : "extension"
                    }
                  >
                    {slashCommandKindLabel(item.command.kind)}
                  </Badge>
                ) : null}
              </Button>
            ))
          ) : showCompletionEmptyState ? (
            <div className="shrink-0 p-3 text-xs text-muted-foreground">{completionEmptyText}</div>
          ) : null}
          {showCompletionStatus ? (
            <div className="shrink-0 px-3 pb-2 text-xs text-muted-foreground">
                {completionListStatus}
            </div>
          ) : null}
        </div>
      ) : null}

      {followUpChoicesOpen ? (
        <div
          className={COMPLETIONS_PANEL_CLASS}
          role="menu"
          aria-label="Choose follow-up delivery"
        >
          {FOLLOW_UP_OPTIONS.map((option, index) => (
            <Button
              key={option.timing}
              type="button"
              variant={index === followUpSelectedIndex ? "secondary" : "ghost"}
              role="menuitem"
              data-active={index === followUpSelectedIndex ? "" : undefined}
              className="h-auto min-h-14 w-full shrink-0 items-center justify-between text-left whitespace-normal"
              disabled={!canDraftFollowUp}
              onMouseDown={(event) => {
                event.preventDefault();
              }}
              onMouseEnter={() => setFollowUpSelectedIndex(index)}
              onClick={() => {
                activateFollowUpChoice(option.timing);
              }}
            >
              <span className="flex min-w-0 flex-col items-start gap-0.5">
                <span className="text-xs">{option.label}</span>
                <span className="text-xs font-normal text-muted-foreground">
                  {option.description}
                </span>
              </span>
              <Badge variant={option.badgeVariant} data-kind={option.badgeKind}>
                {option.badge}
              </Badge>
            </Button>
          ))}
        </div>
      ) : null}

      {displayedQueuedFollowUps.length > 0 ? (
        <div
          data-follow-up-dock=""
          className="mt-2 flex flex-col gap-3 rounded-lg border bg-card p-3"
          aria-label={displayedQueuedFollowUps.length === 1 ? "Queued follow-up" : "Queued follow-ups"}
        >
          {displayedQueuedFollowUps.map((item) => {
            const imageCount = item.image_count ?? 0;
            const canRestoreItemDraft =
              Boolean(item)
              && !sessionEnded
              && !isSubmitting
              && (inputEnabled || canQueueFollowUp)
              && Boolean(onCancelQueuedFollowUp)
              && !promptEnhancementPending
              && item.kind !== "background_result";
            return (
              <div key={item.id} className="flex w-full flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-xs font-medium text-muted-foreground">
                    {item.failed
                      ? "Queued follow-up failed"
                      : item.kind === "background_result"
                        ? item.auto_wake === false
                          ? `Background result · ${item.task_id ?? ""} · send to continue`
                          : `Background result · ${item.task_id ?? ""} · will wake session`
                      : item.delivery === "checkpoint"
                        ? "Queued follow-up · after next checkpoint"
                        : "Queued follow-up · after assistant finishes"}
                  </span>
                  <span className="max-w-prose truncate text-xs text-muted-foreground">
                    {item.kind === "background_result"
                      ? (item.text.split("\n").find((line) => line.startsWith("command: ")) ?? "")
                      : item.text}
                    {imageCount > 0
                      ? ` · ${imageCount} image${imageCount === 1 ? "" : "s"}`
                      : ""}
                  </span>
                  {item.error ? (
                    <span className="text-xs text-destructive">
                      {item.error}
                    </span>
                  ) : null}
                </div>
                <div
                  data-follow-up-actions=""
                  className="flex shrink-0 flex-wrap items-center justify-end gap-2"
                >
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isSendingQueuedFollowUp || !canRestoreItemDraft}
                    onClick={() => {
                      void (async () => {
                        if (!canRestoreItemDraft) return;
                        await onCancelQueuedFollowUp?.(item.id);
                        setInput(item.text);
                        setCursorIndex(item.text.length);
                        if (imageCount > 0) {
                          setAttachmentMessage("Queued image attachments were removed; attach them again before sending.");
                        }
                        window.requestAnimationFrame(() => {
                          textareaRef.current?.focus();
                          autoResize();
                        });
                      })();
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isSendingQueuedFollowUp || !onCancelQueuedFollowUp}
                    onClick={() => {
                      void onCancelQueuedFollowUp?.(item.id);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isSendingQueuedFollowUp || !canSendQueuedFollowUpNow(item)}
                    onClick={() => {
                      void onSendQueuedFollowUp?.(item.id);
                    }}
                  >
                    {isSendingQueuedFollowUp ? "Sending…" : "Send now"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {replySnippets.length > 0 ? (
        <div
          className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3"
          aria-label="Reply snippets"
        >
          {replySnippets.map((snippet) => (
            <ReplySnippetCard
              key={snippet.id}
              quote={snippet.quote}
              comment={snippet.comment}
              onRemove={
                composerInputAvailable
                  ? () => setReplySnippets((current) => current.filter((item) => item.id !== snippet.id))
                  : undefined
              }
            />
          ))}
        </div>
      ) : null}

      {pendingImages.length > 0 ? (
        <div
          className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4"
          aria-label="Pending image attachments"
        >
          {pendingImages.map((image) => (
            <div
              key={image.id}
              className="flex items-center gap-2 rounded-md border bg-card p-2"
            >
              <img
                src={image.previewUrl}
                alt={image.file.name}
                className="size-13 shrink-0 rounded-sm bg-muted object-contain"
              />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="block max-w-full truncate text-xs text-foreground">
                      {image.file.name}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{image.file.name}</TooltipContent>
                </Tooltip>
                <span className="text-xs text-muted-foreground">
                  {Math.max(1, Math.round(image.file.size / 1024))} KB
                </span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={() => removePendingImage(image.id)}
                aria-label={`Remove ${image.file.name}`}
                disabled={!composerInputAvailable}
              >
                <XIcon aria-hidden="true" />
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      {attachmentStatus ? (
        <div
          className={cn(
            "mt-2 px-2 text-xs",
            attachmentMessage ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {attachmentStatus}
        </div>
      ) : null}

      {composerActions.promptEnhancementError ? (
        <div className="mt-2 px-2 text-xs text-destructive">
          {composerActions.promptEnhancementError}
        </div>
      ) : null}

    </form>
  );
});
