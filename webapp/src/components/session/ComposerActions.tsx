import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  ArrowUpIcon,
  BadgeDollarSignIcon,
  MicIcon,
  SquareIcon,
  WandSparklesIcon,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
} from "../ui/input-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

export type ComposerDictationState = "idle" | "recording" | "transcribing";

type ComposerActionShortcutEvent = {
  key: string;
  code: string;
  ctrlKey: boolean;
  altKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  repeat: boolean;
};

interface UseComposerActionsParams {
  input: string;
  canSend: boolean;
  isProcessing: boolean;
  showStopButton: boolean;
  isShellMode: boolean;
  dictationState: ComposerDictationState;
  dictationAvailable: boolean;
  hasDictationHandler: boolean;
  onEnhancePrompt?: (text: string) => Promise<string>;
  getCurrentInput: () => string;
  applyEnhancedPrompt: (text: string) => void;
  toggleDictation: () => void;
}

export interface ComposerActionsController {
  canSubmit: boolean;
  canStartDictation: boolean;
  showDictationAction: boolean;
  canEnhancePrompt: boolean;
  showEnhancePromptAction: boolean;
  promptEnhancementPending: boolean;
  promptEnhancementError: string | null;
  clearPromptEnhancementError: () => void;
  enhancePrompt: () => Promise<void>;
  handleShortcut: (event: KeyboardEvent<HTMLElement>) => boolean;
  isPromptEnhancementPending: () => boolean;
}

interface ComposerActionButtonsProps {
  controller: ComposerActionsController;
  showStopButton: boolean;
  isInterrupting?: boolean;
  onInterrupt?: () => void;
  isShellMode: boolean;
  dictationState: ComposerDictationState;
  dictationUnavailableReason: string | null;
  toggleDictation: () => void;
}

export function isComposerActionShortcut(
  event: ComposerActionShortcutEvent,
): boolean {
  const key = event.key.toLowerCase();
  return (
    event.ctrlKey &&
    !event.altKey &&
    !event.metaKey &&
    !event.shiftKey &&
    !event.repeat &&
    (key === " " || key === "spacebar" || event.code === "Space")
  );
}

export function useComposerActions({
  input,
  canSend,
  isProcessing,
  showStopButton,
  isShellMode,
  dictationState,
  dictationAvailable,
  hasDictationHandler,
  onEnhancePrompt,
  getCurrentInput,
  applyEnhancedPrompt,
  toggleDictation,
}: UseComposerActionsParams): ComposerActionsController {
  const [promptEnhancementPending, setPromptEnhancementPending] = useState(false);
  const [promptEnhancementError, setPromptEnhancementError] = useState<string | null>(null);
  const promptEnhancementPendingRef = useRef(false);

  const inputIsEmpty = input.trim().length === 0;
  const trimmedStart = input.trimStart();
  const inputStartsCommand = trimmedStart.startsWith("/") || trimmedStart.startsWith("!");
  const dictationInProgress = dictationState !== "idle";
  const showDictationAction =
    !showStopButton && !isShellMode && (inputIsEmpty || dictationInProgress);
  const canStartDictation =
    canSend && inputIsEmpty && dictationAvailable && hasDictationHandler;
  const showEnhancePromptAction =
    Boolean(onEnhancePrompt) &&
    canSend &&
    !isProcessing &&
    !showStopButton &&
    !isShellMode &&
    !inputIsEmpty &&
    !inputStartsCommand;
  const canEnhancePrompt = showEnhancePromptAction && !promptEnhancementPending;
  const canSubmit = canSend && !promptEnhancementPending;

  const clearPromptEnhancementError = useCallback(() => {
    setPromptEnhancementError(null);
  }, []);

  const enhancePrompt = useCallback(async () => {
    if (promptEnhancementPendingRef.current) return;
    const currentInput = getCurrentInput();
    const trimmed = currentInput.trim();
    const currentTrimmedStart = currentInput.trimStart();
    if (
      !onEnhancePrompt ||
      !canSend ||
      isProcessing ||
      showStopButton ||
      !trimmed ||
      currentTrimmedStart.startsWith("/") ||
      currentTrimmedStart.startsWith("!")
    ) {
      return;
    }

    promptEnhancementPendingRef.current = true;
    setPromptEnhancementPending(true);
    setPromptEnhancementError(null);
    try {
      const enhancedText = await onEnhancePrompt(currentInput);
      applyEnhancedPrompt(enhancedText);
    } catch (error) {
      setPromptEnhancementError(
        error instanceof Error
          ? error.message
          : "Unable to enhance the prompt.",
      );
    } finally {
      promptEnhancementPendingRef.current = false;
      setPromptEnhancementPending(false);
    }
  }, [
    applyEnhancedPrompt,
    canSend,
    getCurrentInput,
    isProcessing,
    onEnhancePrompt,
    showStopButton,
  ]);

  useEffect(() => {
    if (!promptEnhancementError) return undefined;
    const timeoutId = window.setTimeout(() => {
      setPromptEnhancementError(null);
    }, 5000);
    return () => window.clearTimeout(timeoutId);
  }, [promptEnhancementError]);

  const handleShortcut = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (!isComposerActionShortcut(event)) return false;
      if (dictationState !== "recording" && !showDictationAction && !canEnhancePrompt) {
        return false;
      }

      event.preventDefault();
      event.stopPropagation();
      if (dictationState === "recording" || showDictationAction) {
        toggleDictation();
        return true;
      }
      void enhancePrompt();
      return true;
    },
    [
      canEnhancePrompt,
      dictationState,
      enhancePrompt,
      showDictationAction,
      toggleDictation,
    ],
  );

  const isPromptEnhancementPending = useCallback(
    () => promptEnhancementPendingRef.current,
    [],
  );

  return useMemo(
    () => ({
      canSubmit,
      canStartDictation,
      showDictationAction,
      canEnhancePrompt,
      showEnhancePromptAction,
      promptEnhancementPending,
      promptEnhancementError,
      clearPromptEnhancementError,
      enhancePrompt,
      handleShortcut,
      isPromptEnhancementPending,
    }),
    [
      canEnhancePrompt,
      canStartDictation,
      canSubmit,
      clearPromptEnhancementError,
      enhancePrompt,
      handleShortcut,
      isPromptEnhancementPending,
      promptEnhancementError,
      promptEnhancementPending,
      showDictationAction,
      showEnhancePromptAction,
    ],
  );
}

export function ComposerActionButtons({
  controller,
  showStopButton,
  isInterrupting = false,
  onInterrupt,
  isShellMode,
  dictationState,
  dictationUnavailableReason,
  toggleDictation,
}: ComposerActionButtonsProps) {
  const dictationButtonLabel =
    dictationState === "recording"
      ? "Stop dictation recording"
      : dictationState === "transcribing"
        ? "Transcribing dictation"
        : "Start dictation";
  const dictationTooltip =
    dictationState === "recording"
      ? "Recording dictation… Ctrl+Space to stop."
      : dictationState === "transcribing"
        ? "Transcribing dictation…"
        : controller.canStartDictation
          ? "Dictate a message (Ctrl+Space)"
          : dictationUnavailableReason ??
            "Choose a speech-to-text provider in Settings to use dictation.";
  const dictationButtonDisabled =
    dictationState === "transcribing" ||
    (dictationState === "idle" && !controller.canStartDictation);

  return (
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
        ) : controller.showDictationAction ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="composer__input-tooltip-trigger">
                <InputGroupButton
                  type="button"
                  aria-label={dictationButtonLabel}
                  aria-keyshortcuts="Control+Space"
                  aria-pressed={dictationState === "recording"}
                  className={cn(
                    "composer__dictation",
                    dictationState === "recording" &&
                      "composer__dictation--recording",
                    dictationState === "transcribing" &&
                      "composer__dictation--transcribing",
                  )}
                  disabled={dictationButtonDisabled}
                  onClick={toggleDictation}
                  size="icon-sm"
                >
                  {dictationState === "transcribing" ? (
                    <LoadingSpinner size="sm" />
                  ) : (
                    <MicIcon aria-hidden="true" />
                  )}
                </InputGroupButton>
              </span>
            </TooltipTrigger>
            <TooltipContent side="top">{dictationTooltip}</TooltipContent>
          </Tooltip>
        ) : (
          <>
            {controller.showEnhancePromptAction ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="composer__input-tooltip-trigger">
                    <InputGroupButton
                      type="button"
                      aria-label={
                        controller.promptEnhancementPending
                          ? "Enhancing prompt"
                          : "Enhance prompt"
                      }
                      aria-keyshortcuts="Control+Space"
                      className={cn(
                        "composer__enhance",
                        controller.promptEnhancementPending &&
                          "composer__enhance--loading",
                      )}
                      disabled={!controller.canEnhancePrompt}
                      onClick={() => {
                        void controller.enhancePrompt();
                      }}
                      size="icon-sm"
                    >
                      {controller.promptEnhancementPending ? (
                        <LoadingSpinner size="sm" />
                      ) : (
                        <WandSparklesIcon aria-hidden="true" />
                      )}
                    </InputGroupButton>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  {controller.promptEnhancementPending
                    ? "Enhancing prompt…"
                    : "Enhance prompt (Ctrl+Space)"}
                </TooltipContent>
              </Tooltip>
            ) : null}
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="composer__input-tooltip-trigger">
                  <InputGroupButton
                    type="submit"
                    aria-label={isShellMode ? "Run command" : "Send message"}
                    className="composer__send"
                    disabled={!controller.canSubmit}
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
          </>
        )}
      </InputGroupAddon>
    </InputGroup>
  );
}