import {
  type ClipboardEvent,
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import {
  ArrowUpIcon,
  BadgeDollarSignIcon,
  ImageIcon,
  PlusIcon,
  TerminalIcon,
  XIcon,
} from "lucide-react";
import { searchFileMentions, searchSlashCommands } from "../../api";
import type { FileMentionItem, SlashCommandItem } from "../../types";
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

export interface ComposerHandle {
  focus: () => void;
}

interface ComposerProps {
  inputEnabled: boolean;
  sessionEnded: boolean;
  liveSessionId: string | null;
  supportsImageInputs: boolean;
  isSubmitting: boolean;
  onSubmit: (payload: { text: string; images: File[] }) => Promise<void>;
}

type ActiveCompletionRange = {
  start: number;
  end: number;
  query: string;
};

type CompletionMode = "mention" | "slash";

type CompletionItem =
  | {
      kind: "mention";
      key: string;
      mention: FileMentionItem;
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

const EMAIL_PREFIX_PATTERN = /[a-zA-Z0-9._%+-]$/;
const SUPPORTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function parseActiveMention(
  text: string,
  cursorIndex: number,
): ActiveCompletionRange | null {
  if (cursorIndex < 0 || cursorIndex > text.length) {
    return null;
  }

  const beforeCursor = text.slice(0, cursorIndex);
  const atIndex = beforeCursor.lastIndexOf("@");
  if (atIndex < 0) {
    return null;
  }
  if (atIndex > 0 && EMAIL_PREFIX_PATTERN.test(text[atIndex - 1])) {
    return null;
  }

  const candidate = text.slice(atIndex + 1, cursorIndex);
  for (let index = 0; index < candidate.length; index += 1) {
    const char = candidate[index];
    const previous = index > 0 ? candidate[index - 1] : "";
    if ((char === " " || char === "\n" || char === "\t") && previous !== "\\") {
      return null;
    }
  }

  return {
    start: atIndex,
    end: cursorIndex,
    query: candidate.replaceAll("\\ ", " "),
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
  supportsImageInputs,
  isSubmitting,
  onSubmit,
}, ref) {
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
  const [completionSelectedIndex, setCompletionSelectedIndex] = useState(0);
  const completionRequestIdRef = useRef(0);
  const pendingImagesRef = useRef<PendingImage[]>([]);
  const refocusAfterSubmitRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const actionMenuRef = useRef<HTMLDivElement>(null);

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
    Boolean(liveSessionId) && inputEnabled && !sessionEnded && !isSubmitting;
  const shellInput = input.trimStart();
  const isShellMode = shellInput.startsWith("!");
  const shellCommandPreview = shellInput.slice(1).trim();
  const isActionMenuOpen = canSend && !isShellMode && actionMenuOpen;
  const activeSlashCommand = parseActiveSlashCommand(input, cursorIndex);
  const activeMention = activeSlashCommand
    ? null
    : parseActiveMention(input, cursorIndex);
  const activeCompletionMode = activeSlashCommand
    ? "slash"
    : activeMention
      ? "mention"
      : null;
  const activeCompletionQuery = activeSlashCommand?.query ?? activeMention?.query ?? null;

  const closeCompletions = useCallback(() => {
    setCompletionMode(null);
    setCompletionItems([]);
    setCompletionOpen(false);
    setCompletionLoading(false);
    setCompletionError(null);
    setCompletionSelectedIndex(0);
  }, []);

  const syncCursor = useCallback(() => {
    setCursorIndex(textareaRef.current?.selectionStart ?? 0);
  }, []);

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
          : buildSlashReplacement(item.command, textValue, cursorValue);
      if (!nextState) {
        return null;
      }

      applyInputState(nextState.nextInput, nextState.nextCursor);
      return nextState;
    },
    [applyInputState, buildMentionReplacement, buildSlashReplacement, cursorIndex, input],
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

  useEffect(() => {
    if (!isActionMenuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const menu = actionMenuRef.current;
      if (!menu || menu.contains(event.target as Node)) {
        return;
      }
      setActionMenuOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [isActionMenuOpen]);

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
        await onSubmit({
          text: trimmed,
          images: pendingImages.map((image) => image.file),
        });
        refocusAfterSubmitRef.current = true;
        clearPendingImages();
        setInput("");
        setAttachmentMessage(null);
        setCursorIndex(0);
        closeCompletions();
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
      } catch (error) {
        setAttachmentMessage(
          error instanceof Error ? error.message : "Unable to send the message.",
        );
      }
    },
    [clearPendingImages, closeCompletions, onSubmit, pendingImages],
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
    setCompletionLoading(true);
    if (completionMode !== activeCompletionMode) {
      setCompletionItems([]);
      setCompletionSelectedIndex(0);
    }

    const requestId = completionRequestIdRef.current + 1;
    completionRequestIdRef.current = requestId;
    const timeoutId = window.setTimeout(() => {
      void (async () => {
        try {
          const items =
            activeCompletionMode === "slash"
              ? (await searchSlashCommands(activeCompletionQuery, 8)).map(
                  (command): CompletionItem => ({
                    kind: "slash",
                    key: command.name,
                    command,
                  }),
                )
              : (await searchFileMentions(activeCompletionQuery, 8)).map(
                  (mention): CompletionItem => ({
                    kind: "mention",
                    key: mention.path,
                    mention,
                  }),
                );
          if (completionRequestIdRef.current !== requestId) return;
          setCompletionItems(items);
          setCompletionLoading(false);
          setCompletionSelectedIndex((previousIndex) =>
            items.length === 0 ? 0 : Math.min(previousIndex, items.length - 1),
          );
        } catch {
          if (completionRequestIdRef.current !== requestId) return;
          setCompletionLoading(false);
          setCompletionError(
            activeCompletionMode === "slash"
              ? "Unable to load commands"
              : "Unable to load files",
          );
        }
      })();
    }, activeCompletionMode === "slash" ? 60 : 120);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [
    activeCompletionMode,
    activeCompletionQuery,
    canSend,
    closeCompletions,
    completionMode,
  ]);

  const handleSubmit = async (event?: FormEvent<HTMLFormElement>) => {
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
      if (hasCompletionItems && event.key === "ArrowUp") {
        event.preventDefault();
        setCompletionSelectedIndex(
          (prev) => (prev - 1 + completionItems.length) % completionItems.length,
        );
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

  const showCompletionStatus = completionLoading && completionItems.length > 0;
  const showCompletionEmptyState =
    completionItems.length === 0 &&
    (completionLoading || completionError !== null || completionOpen);
  const completionEmptyText = completionLoading
    ? completionMode === "slash"
      ? "Searching commands..."
      : "Searching files..."
    : completionError ??
      (completionMode === "slash" ? "No matching commands" : "No matching files");
  const completionLabel =
    completionMode === "slash"
      ? "Slash command suggestions"
      : "Workspace file suggestions";
  const attachmentStatus =
    attachmentMessage ??
    (pendingImages.length > 0
      ? `${pendingImages.length} image${pendingImages.length === 1 ? "" : "s"} attached`
      : null);

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

      <div
        className={`composer__input-row ${isShellMode ? "composer__input-row--shell" : ""}`}
      >
        <DropdownMenu
          open={isActionMenuOpen}
          onOpenChange={(open) => setActionMenuOpen(canSend && !isShellMode && open)}
        >
          <div className="composer__action-menu" ref={actionMenuRef}>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                className="composer__action-trigger"
                disabled={!canSend || isShellMode}
                aria-label="Actions"
                title={isShellMode ? "Images cannot be attached to shell commands" : "Actions"}
              >
                <PlusIcon />
              </Button>
            </DropdownMenuTrigger>
          </div>
          <DropdownMenuContent className="composer__action-popover" align="start">
            <DropdownMenuGroup>
              <DropdownMenuItem
                className="composer__action-item"
                onClick={() => {
                  setActionMenuOpen(false);
                  fileInputRef.current?.click();
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
          <InputGroupTextarea
            ref={textareaRef}
            name="message"
            aria-label="Message"
            className="composer__textarea"
            value={input}
            onChange={(event) => {
              setInput(event.target.value);
              setCursorIndex(event.target.selectionStart ?? event.target.value.length);
              autoResize();
            }}
            onClick={syncCursor}
            onKeyDown={handleKeyDown}
            onKeyUp={syncCursor}
            onPaste={handleTextareaPaste}
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
            <InputGroupButton
              type="submit"
              aria-label={isShellMode ? "Run command" : "Send message"}
              className="composer__send"
              disabled={!canSend}
              title={isShellMode ? "Run command (Enter)" : "Send (Enter)"}
              size="icon-sm"
            >
              {isShellMode ? <BadgeDollarSignIcon /> : <ArrowUpIcon />}
            </InputGroupButton>
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
                    {item.kind === "slash" ? item.command.name : `@${item.mention.path}`}
                    {item.kind === "slash" && item.command.description ? (
                      <span className="composer__completion-description">
                        {` (${item.command.description})`}
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
                ) : null}
              </Button>
            ))
          ) : showCompletionEmptyState ? (
            <div className="composer__completion-empty">{completionEmptyText}</div>
          ) : null}
          {showCompletionStatus ? (
            <div className="composer__completion-status">
              {completionMode === "slash" ? "Updating commands..." : "Updating results..."}
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
                <span className="composer__attachment-name" title={image.file.name}>
                  {image.file.name}
                </span>
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
