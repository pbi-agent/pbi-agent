import { lazy, Suspense } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchBootstrap } from "../api";
import { useTaskEvents } from "../hooks/useTaskEvents";
import { LoadingSpinner } from "./shared/LoadingSpinner";

const ChatPage = lazy(() =>
  import("./chat/ChatPage").then((m) => ({ default: m.ChatPage })),
);
const BoardPage = lazy(() =>
  import("./board/BoardPage").then((m) => ({ default: m.BoardPage })),
);

export function AppShell() {
  useTaskEvents();

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchBootstrap,
    staleTime: 30_000,
  });

  const bootstrap = bootstrapQuery.data;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__brand">
          <strong>Agent</strong> Control Room
        </div>
        <nav className="topnav">
          <NavLink to="/" end>Chat</NavLink>
          <NavLink to="/board">Board</NavLink>
        </nav>
        <div className="runtime-meta">
          <span className="runtime-meta__pill">{bootstrap?.provider ?? "..."}</span>
          <span className="runtime-meta__pill">{bootstrap?.model ?? "..."}</span>
        </div>
      </header>

      <main className="app-main">
        <Suspense fallback={<div className="center-spinner"><LoadingSpinner size="lg" /></div>}>
          <Routes>
            <Route path="/" element={<ChatPage workspaceRoot={bootstrap?.workspace_root} />} />
            <Route path="/board" element={<BoardPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
