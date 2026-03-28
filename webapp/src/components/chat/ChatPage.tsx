import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import {
  createChatSession,
  fetchSessions,
  requestNewChat,
  submitChatInput,
} from "../../api";
import { useChatStore } from "../../store";
import { useLiveChatEvents } from "../../hooks/useLiveChatEvents";
import { ConnectionBadge } from "./ConnectionBadge";
import { SessionSidebar } from "./SessionSidebar";
import { ChatTimeline } from "./ChatTimeline";
import { UsageBar } from "./UsageBar";
import { Composer } from "./Composer";

export function ChatPage({
  workspaceRoot,
}: {
  workspaceRoot: string | undefined;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const {
    liveSessionId,
    connection,
    inputEnabled,
    waitMessage,
    sessionUsage,
    turnUsage,
    sessionEnded,
    fatalError,
    items,
    subAgents,
  } = useChatStore(
    useShallow((s) => ({
      liveSessionId: s.liveSessionId,
      connection: s.connection,
      inputEnabled: s.inputEnabled,
      waitMessage: s.waitMessage,
      sessionUsage: s.sessionUsage,
      turnUsage: s.turnUsage,
      sessionEnded: s.sessionEnded,
      fatalError: s.fatalError,
      items: s.items,
      subAgents: s.subAgents,
    })),
  );

  const switchLiveSession = useChatStore((s) => s.switchLiveSession);
  const clearTimeline = useChatStore((s) => s.clearTimeline);

  const sessionsQuery = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
    refetchInterval: 12_000,
  });

  const createSessionMutation = useMutation({
    mutationFn: createChatSession,
    onSuccess: (session) => switchLiveSession(session.live_session_id),
  });

  const sendInputMutation = useMutation({
    mutationFn: (payload: { text: string; image_paths: string[] }) => {
      if (!liveSessionId) throw new Error("No live session available.");
      return submitChatInput(liveSessionId, payload);
    },
  });

  const newChatMutation = useMutation({
    mutationFn: () => {
      if (!liveSessionId) throw new Error("No live session available.");
      return requestNewChat(liveSessionId);
    },
    onSuccess: () => clearTimeline(),
  });

  const startedRef = useRef(false);
  const mutateRef = useRef(createSessionMutation.mutate);
  mutateRef.current = createSessionMutation.mutate;

  useLiveChatEvents(liveSessionId);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    mutateRef.current(liveSessionId ? { live_session_id: liveSessionId } : {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async (text: string, imagePaths: string[]) => {
    await sendInputMutation.mutateAsync({ text, image_paths: imagePaths });
  };

  return (
    <section className={`chat-layout ${sidebarOpen ? "chat-layout--sidebar-open" : ""}`}>
      <div className={`sidebar ${sidebarOpen ? "sidebar--open" : ""}`}>
        <SessionSidebar
          sessions={sessionsQuery.data ?? []}
          isLoading={sessionsQuery.isLoading}
          activeSessionId={null}
          workspaceRoot={workspaceRoot}
          onNewSession={() => createSessionMutation.mutate({})}
          onResumeSession={(sessionId) =>
            createSessionMutation.mutate({ resume_session_id: sessionId })
          }
          onToggle={() => setSidebarOpen((prev) => !prev)}
          isOpen={sidebarOpen}
        />
      </div>

      <div className="chat-panel">
        <ConnectionBadge connection={connection} />

        {waitMessage ? <div className="banner banner--wait">{waitMessage}</div> : null}
        {fatalError ? <div className="banner banner--error">{fatalError}</div> : null}

        <ChatTimeline
          items={items}
          subAgents={subAgents}
          connection={connection}
        />

        <UsageBar sessionUsage={sessionUsage} turnUsage={turnUsage} />

        <Composer
          inputEnabled={inputEnabled}
          sessionEnded={sessionEnded}
          liveSessionId={liveSessionId}
          onSubmit={handleSubmit}
        />
      </div>
    </section>
  );
}
