import type { QueryClient } from "@tanstack/react-query";

import { useSessionStore } from "./store";
import type { BootstrapPayload } from "./types";

const WORKSPACE_SCOPED_QUERY_PREFIXES = [
  "sessions",
  "session",
  "session-runs",
  "tasks",
  "board-stages",
  "dashboard-stats",
  "dashboard-runs",
  "dashboard-run-filter-values",
  "run-detail",
  "file-mentions",
  "skill-mentions",
  "slash-commands",
];

export function resetWorkspaceScopedClientState(
  client: QueryClient,
  bootstrap?: BootstrapPayload,
) {
  useSessionStore.getState().resetAllSessions();
  client.removeQueries({
    predicate: (query) => {
      const firstKey = query.queryKey[0];
      return typeof firstKey === "string"
        && WORKSPACE_SCOPED_QUERY_PREFIXES.includes(firstKey);
    },
  });
  if (bootstrap) {
    client.setQueryData(["bootstrap"], bootstrap);
  }
  void client.invalidateQueries({ queryKey: ["bootstrap"] });
  void client.invalidateQueries({ queryKey: ["config-bootstrap"] });
  void client.invalidateQueries({ queryKey: ["workspaces", "recent"] });
}
