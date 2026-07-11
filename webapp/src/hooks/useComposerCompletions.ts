import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  searchMentions,
  searchSkillMentions,
  searchSlashCommands,
} from "../api";
import type {
  AgentMentionItem,
  FileMentionItem,
  SkillMentionItem,
  SlashCommandItem,
} from "../types";

export type CompletionMode = "mention" | "skill" | "slash";

export type CompletionItem =
  | {
      kind: "mention";
      key: string;
      mention: FileMentionItem;
    }
  | {
      kind: "agent";
      key: string;
      agent: AgentMentionItem;
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

type UseComposerCompletionsOptions = {
  enabled: boolean;
  mode: CompletionMode | null;
  query: string | null;
  mentionTokenKey: string | null;
  workspaceKey: string | null;
  fileIndexGeneration: string | null;
};

const FILE_MENTION_POLL_INTERVAL_MS = 500;
const COMPLETION_RESULT_LIMIT = 8;
const SLASH_COMMAND_COMPLETION_LIMIT = 200;

export function useComposerCompletions({
  enabled,
  mode,
  query,
  mentionTokenKey,
  workspaceKey,
  fileIndexGeneration,
}: UseComposerCompletionsOptions): {
  completionMode: CompletionMode | null;
  completionItems: CompletionItem[];
  completionOpen: boolean;
  completionLoading: boolean;
  completionError: string | null;
  completionStatusMessage: string | null;
  completionSelectedIndex: number;
  fileIndexGeneration: string | null;
  fileIndexRevision: number | null;
  setCompletionSelectedIndex: Dispatch<SetStateAction<number>>;
  closeCompletions: () => void;
} {
  const [completionMode, setCompletionMode] = useState<CompletionMode | null>(
    null,
  );
  const [completionItems, setCompletionItems] = useState<CompletionItem[]>([]);
  const [completionOpen, setCompletionOpen] = useState(false);
  const [completionLoading, setCompletionLoading] = useState(false);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [completionStatusMessage, setCompletionStatusMessage] = useState<
    string | null
  >(null);
  const [completionSelectedIndex, setCompletionSelectedIndex] = useState(0);
  const [observedIndex, setObservedIndex] = useState<{
    workspaceKey: string | null;
    sourceGeneration: string | null;
    generation: string | null;
    revision: number | null;
  } | null>(null);
  const completionRequestIdRef = useRef(0);
  const activeCompletionRef = useRef<{
    mode: CompletionMode | null;
    query: string | null;
  }>({ mode: null, query: null });
  const mentionRefreshRef = useRef<{
    tokenKey: string | null;
    dispatched: boolean;
  }>({ tokenKey: null, dispatched: false });

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

  useEffect(() => {
    activeCompletionRef.current = { mode, query };
  }, [mode, query]);

  useEffect(() => {
    if (mode !== "mention" || mentionTokenKey === null) {
      mentionRefreshRef.current = { tokenKey: null, dispatched: false };
      return;
    }
    if (mentionRefreshRef.current.tokenKey !== mentionTokenKey) {
      mentionRefreshRef.current = {
        tokenKey: mentionTokenKey,
        dispatched: false,
      };
    }
  }, [mentionTokenKey, mode]);

  useEffect(() => {
    if (!enabled || mode === null || query === null) {
      completionRequestIdRef.current += 1;
      const closeTimeoutId = window.setTimeout(closeCompletions, 0);
      return () => window.clearTimeout(closeTimeoutId);
    }

    const requestId = completionRequestIdRef.current + 1;
    completionRequestIdRef.current = requestId;
    const requestMode = mode;
    const requestQuery = query;
    const requestMentionTokenKey = mentionTokenKey;
    let cancelled = false;
    let timeoutId: number | undefined;
    const prepareTimeoutId = window.setTimeout(() => {
      if (!isCurrentRequest()) return;
      setCompletionOpen(true);
      setCompletionMode(requestMode);
      setCompletionError(null);
      setCompletionStatusMessage(null);
      setCompletionLoading(true);
      setCompletionItems([]);
      setCompletionSelectedIndex(0);
    }, 0);

    const isCurrentRequest = () =>
      !cancelled
      && completionRequestIdRef.current === requestId
      && activeCompletionRef.current.mode === requestMode
      && activeCompletionRef.current.query === requestQuery;

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
                items: (
                  await searchSlashCommands(
                    requestQuery,
                    SLASH_COMMAND_COMPLETION_LIMIT,
                  )
                ).map((command): CompletionItem => ({
                  kind: "slash",
                  key: command.name,
                  command,
                })),
                loading: false,
                statusMessage: null,
                errorMessage: null,
                shouldPoll: false,
              }
            : requestMode === "skill"
              ? await searchSkillMentions(
                  requestQuery,
                  COMPLETION_RESULT_LIMIT,
                ).then((result) => ({
                  items: result.items.map((skill): CompletionItem => ({
                    kind: "skill",
                    key: skill.name,
                    skill,
                  })),
                  loading: false,
                  statusMessage: null,
                  errorMessage: null,
                  shouldPoll: false,
                }))
              : await (async () => {
                  const shouldRefreshFiles =
                    requestMentionTokenKey !== null
                    && mentionRefreshRef.current.tokenKey
                      === requestMentionTokenKey
                    && !mentionRefreshRef.current.dispatched;
                  if (shouldRefreshFiles) {
                    mentionRefreshRef.current.dispatched = true;
                  }
                  const mentionResult = await searchMentions(
                    requestQuery,
                    COMPLETION_RESULT_LIMIT,
                    shouldRefreshFiles ? { refresh: true } : undefined,
                  );
                  return {
                    items: mentionResult.items.map(
                      (item): CompletionItem =>
                        item.kind === "agent"
                          ? {
                              kind: "agent",
                              key: `agent:${item.name}`,
                              agent: item,
                            }
                          : {
                              kind: "mention",
                              key: `file:${item.path}`,
                              mention: item,
                            },
                    ),
                    loading:
                      mentionResult.scan_status === "scanning"
                      && mentionResult.items.length === 0,
                    statusMessage:
                      mentionResult.scan_status === "scanning"
                        ? mentionResult.is_stale
                          ? "Refreshing file index..."
                          : "Indexing files..."
                        : mentionResult.truncated
                          ? "File index limit reached; some files may be omitted."
                          : mentionResult.search_approximated
                            ? "Fuzzy search limited; some matches may be omitted."
                          : null,
                    errorMessage:
                      mentionResult.scan_status === "failed"
                        ? mentionResult.error ?? "Unable to index workspace files"
                        : null,
                    shouldPoll: mentionResult.scan_status === "scanning",
                    fileIndexGeneration: mentionResult.index_generation,
                    fileIndexRevision: mentionResult.index_revision,
                  };
                })();
        if (!isCurrentRequest()) return;
        setCompletionItems(payload.items);
        setCompletionLoading(payload.loading);
        setCompletionStatusMessage(payload.statusMessage);
        setCompletionError(payload.errorMessage);
        if ("fileIndexRevision" in payload) {
          setObservedIndex({
            workspaceKey,
            sourceGeneration: fileIndexGeneration,
            generation: payload.fileIndexGeneration,
            revision: payload.fileIndexRevision,
          });
        }
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
              : "Unable to load files and agents",
        );
      }
    };

    scheduleSearch(mode === "slash" ? 60 : 120);

    return () => {
      cancelled = true;
      window.clearTimeout(prepareTimeoutId);
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [
    closeCompletions,
    enabled,
    fileIndexGeneration,
    mentionTokenKey,
    mode,
    query,
    workspaceKey,
  ]);

  return {
    completionMode,
    completionItems,
    completionOpen,
    completionLoading,
    completionError,
    completionStatusMessage,
    completionSelectedIndex,
    fileIndexGeneration:
      observedIndex?.workspaceKey === workspaceKey
        && observedIndex.sourceGeneration === fileIndexGeneration
        ? observedIndex.generation
        : null,
    fileIndexRevision:
      observedIndex?.workspaceKey === workspaceKey
        && observedIndex.sourceGeneration === fileIndexGeneration
        ? observedIndex.revision
        : null,
    setCompletionSelectedIndex,
    closeCompletions,
  };
}