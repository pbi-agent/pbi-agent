import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlertIcon, ShieldCheckIcon } from "lucide-react";
import { disableHook, enableHook, fetchHooks, trustHook } from "../../api";
import type { HookListPayload, HookView } from "../../types";
import { EmptyState } from "../shared/EmptyState";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import type * as React from "react";
import { cn } from "../../lib/utils";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";
import {
  SettingsList,
  SettingsPanel,
  SettingsSection,
} from "./settings-layout";
import { Alert, AlertDescription } from "../ui/alert";

export function HooksSettingsSection() {
  const queryClient = useQueryClient();
  const hooksQuery = useQuery({
    queryKey: ["hooks"],
    queryFn: fetchHooks,
    staleTime: 10_000,
  });
  const mutation = useMutation({
    mutationFn: async (action: {
      type: "trust" | "enable" | "disable";
      key: string;
    }) => {
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
    <SettingsSection>
      <SettingsPanel
        title="Hooks"
        description="Review declarative command hooks before they can run."
      >
        {hooksQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoadingSpinner size="sm" />
            <span>Loading hooks…</span>
          </div>
        ) : hooksQuery.isError || !data ? (
          <Alert variant="destructive">
            <AlertDescription>
              Failed to load hooks:{" "}
              {(hooksQuery.error as Error)?.message ?? "Unknown error"}
            </AlertDescription>
          </Alert>
        ) : (
          <>
            {data.trust_bypass_active && (
              <Alert>
                <ShieldAlertIcon />
                <AlertDescription>
                  Dangerous hook trust bypass is active; untrusted and modified
                  hooks can run.
                </AlertDescription>
              </Alert>
            )}
            {data.diagnostics.length > 0 && (
              <Alert variant="destructive">
                <AlertDescription>
                  {data.diagnostics.join("\n")}
                </AlertDescription>
              </Alert>
            )}
            {data.hooks.length === 0 ? (
              <EmptyState
                title="No hooks found"
                description="Add ~/.pbi-agent/hooks.json or .agents/hooks.json to configure hooks."
              />
            ) : (
              <SettingsList>
                {data.hooks.map((hook) => (
                  <HookCard
                    key={hook.key}
                    hook={hook}
                    busy={mutation.isPending}
                    onAction={(type) =>
                      mutation.mutate({ type, key: hook.key })
                    }
                  />
                ))}
              </SettingsList>
            )}
          </>
        )}
      </SettingsPanel>
    </SettingsSection>
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
  const needsReview =
    hook.trust_status === "untrusted" || hook.trust_status === "modified";
  const details: Array<[string, React.ReactNode, boolean?]> = [
    ["Command", hook.command],
    ["Status message", hook.status_message || "—"],
    ["Timeout", `${hook.timeout}s`],
    ["Hash", hook.current_hash, true],
    ["Source path", hook.source_path],
  ];
  if (hook.diagnostics.length > 0)
    details.push(["Diagnostics", hook.diagnostics.join("\n")]);
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{hook.event}</CardTitle>
        <CardDescription>
          matcher {hook.matcher || "*"} · {hook.source}
        </CardDescription>
        <CardAction>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Badge
              size="meta"
              variant={
                needsReview
                  ? "warning"
                  : hook.runnable
                    ? "success"
                    : "secondary"
              }
            >
              {hook.managed ? "managed" : hook.trust_status}
            </Badge>
            {hook.runnable ? (
              <ShieldCheckIcon className="size-4" aria-hidden="true" />
            ) : (
              <ShieldAlertIcon className="size-4" aria-hidden="true" />
            )}
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-2 text-sm">
          {details.map(([label, value, mono]) => (
            <div key={label} className="grid min-w-0 gap-0.5">
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd
                className={cn(
                  "min-w-0 break-words whitespace-pre-wrap",
                  mono && "font-mono text-xs",
                )}
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
      {!hook.managed && (
        <CardFooter>
          <div className="flex flex-wrap justify-end gap-2 w-full">
            {needsReview && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
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
              disabled={busy}
              onClick={() => onAction(hook.enabled ? "disable" : "enable")}
            >
              {hook.enabled ? "Disable" : "Enable"}
            </Button>
          </div>
        </CardFooter>
      )}
    </Card>
  );
}
