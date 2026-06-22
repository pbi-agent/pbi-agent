import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";
import { disableHook, enableHook, fetchHooks, trustHook } from "../../api";
import type { HookListPayload, HookView } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Alert, AlertDescription } from "../ui/alert";

export function HooksSettingsSection() {
  const queryClient = useQueryClient();
  const hooksQuery = useQuery({
    queryKey: ["hooks"],
    queryFn: fetchHooks,
    staleTime: 10_000,
  });
  const mutation = useMutation({
    mutationFn: async (action: { type: "trust" | "enable" | "disable"; key: string }) => {
      if (action.type === "trust") return trustHook(action.key);
      if (action.type === "enable") return enableHook(action.key);
      return disableHook(action.key);
    },
    onSuccess: (data) => {
      queryClient.setQueryData<HookListPayload>(["hooks"], data);
      void queryClient.invalidateQueries({ queryKey: ["bootstrap"] });
    },
  });

  const data = hooksQuery.data;
  return (
    <section className="settings-section settings-section--active">
      <Card className="settings-panel">
        <CardHeader className="settings-panel__header">
          <div className="settings-panel__heading">
            <CardTitle className="settings-panel__title">Hooks</CardTitle>
            <CardDescription className="settings-panel__subtitle">
              Review declarative command hooks before they can run.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="settings-panel__body settings-hooks-panel__body">
          {hooksQuery.isLoading ? (
            <div className="settings-hooks__loading">
              <LoadingSpinner size="sm" />
              <span>Loading hooks…</span>
            </div>
          ) : hooksQuery.isError || !data ? (
            <Alert variant="destructive" className="settings-error-banner">
              <AlertDescription>
                Failed to load hooks: {(hooksQuery.error as Error)?.message ?? "Unknown error"}
              </AlertDescription>
            </Alert>
          ) : (
            <>
              {data.trust_bypass_active && (
                <Alert className="settings-inline-note">
                  <ShieldAlertIcon />
                  <AlertDescription>
                    Dangerous hook trust bypass is active; untrusted and modified hooks can run.
                  </AlertDescription>
                </Alert>
              )}
              {data.diagnostics.length > 0 && (
                <Alert variant="destructive" className="settings-error-banner">
                  <AlertDescription>{data.diagnostics.join("\n")}</AlertDescription>
                </Alert>
              )}
              {data.hooks.length === 0 ? (
                <EmptyState
                  title="No hooks found"
                  description="Add ~/.pbi-agent/hooks.json or .agents/hooks.json to configure hooks."
                />
              ) : (
                <div className="settings-card-list">
                  {data.hooks.map((hook) => (
                    <HookCard
                      key={hook.key}
                      hook={hook}
                      busy={mutation.isPending}
                      onAction={(type) => mutation.mutate({ type, key: hook.key })}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function HookCard({
  hook,
  busy,
  onAction,
}: {
  hook: HookView;
  busy: boolean;
  onAction: (type: "trust" | "enable" | "disable") => void;
}) {
  const needsReview = hook.trust_status === "untrusted" || hook.trust_status === "modified";
  return (
    <Card className="settings-item settings-hook-card">
      <div className="settings-hook-card__main">
        <div className="settings-row settings-hook-card__header">
          <div>
            <span className="settings-item__name">{hook.event}</span>
            <div className="provider-card__subtitle">
              matcher {hook.matcher || "*"} · {hook.source}
            </div>
          </div>
          <div className="settings-row__actions settings-hook-card__status">
            <Badge
              size="meta"
              variant={needsReview ? "warning" : hook.runnable ? "success" : "secondary"}
              className="settings-hook-card__badge"
            >
              {hook.managed ? "managed" : hook.trust_status}
            </Badge>
            {hook.runnable ? (
              <ShieldCheckIcon className="settings-hook-card__status-icon" aria-hidden="true" />
            ) : (
              <ShieldAlertIcon className="settings-hook-card__status-icon" aria-hidden="true" />
            )}
          </div>
        </div>
        <dl className="settings-detail-list settings-hook-card__details">
          <div>
            <dt>Command</dt>
            <dd>{hook.command}</dd>
          </div>
          <div>
            <dt>Status message</dt>
            <dd>{hook.status_message || "—"}</dd>
          </div>
          <div>
            <dt>Timeout</dt>
            <dd>{hook.timeout}s</dd>
          </div>
          <div>
            <dt>Hash</dt>
            <dd className="settings-monospace">{hook.current_hash}</dd>
          </div>
          <div>
            <dt>Source path</dt>
            <dd>{hook.source_path}</dd>
          </div>
          {hook.diagnostics.length > 0 && (
            <div>
              <dt>Diagnostics</dt>
              <dd>{hook.diagnostics.join("\n")}</dd>
            </div>
          )}
        </dl>
      </div>
      {!hook.managed && (
        <div className="settings-item__actions settings-hook-card__actions">
          {needsReview && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="settings-action-button"
              disabled={busy}
              onClick={() => onAction("trust")}
            >
              Trust current hash
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="settings-action-button"
            disabled={busy}
            onClick={() => onAction(hook.enabled ? "disable" : "enable")}
          >
            {hook.enabled ? "Disable" : "Enable"}
          </Button>
        </div>
      )}
    </Card>
  );
}