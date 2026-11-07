import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2Icon, CopyIcon, ExternalLinkIcon, RefreshCcwIcon } from "lucide-react";
import {
  fetchProviderAuthFlow,
  pollProviderAuthFlow,
  startProviderAuthFlow,
} from "../../api";
import type {
  ConfigOptions,
  ProviderAuthFlowResponse,
  ProviderView,
} from "../../types";
import { Alert, AlertDescription } from "../ui/alert";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { FormDialog } from "../ui/form-dialog";
import { Field, FieldLabel } from "../ui/field";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";

interface Props {
  provider: ProviderView;
  options: ConfigOptions;
  onClose: () => void;
  onCompleted: () => Promise<void>;
}

function formatDateTime(timestamp: number | null): string | null {
  if (!timestamp) {
    return null;
  }
  return new Date(timestamp * 1000).toLocaleString();
}

export function ProviderAuthFlowModal({
  provider,
  options,
  onClose,
  onCompleted,
}: Props) {
  const authModeMetadata =
    options.provider_metadata[provider.kind]?.auth_mode_metadata[provider.auth_mode];
  const methods = authModeMetadata?.supported_methods ?? [];
  const authModeLabel = authModeMetadata?.label ?? provider.auth_mode;
  const accountLabel = authModeMetadata?.account_label ?? authModeLabel;
  const [method, setMethod] = useState<"browser" | "device">(methods[0] ?? "device");
  const [flowResponse, setFlowResponse] =
    useState<ProviderAuthFlowResponse | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!copyFeedback) {
      return undefined;
    }
    const timeout = window.setTimeout(() => setCopyFeedback(null), 1500);
    return () => window.clearTimeout(timeout);
  }, [copyFeedback]);

  const flow = flowResponse?.flow ?? null;
  const session = flowResponse?.session ?? null;
  const sessionExpires = useMemo(
    () => formatDateTime(session?.expires_at ?? flowResponse?.auth_status.expires_at ?? null),
    [flowResponse, session],
  );

  const handleFlowUpdate = useCallback(
    (nextResponse: ProviderAuthFlowResponse): void => {
      setFlowResponse(nextResponse);
      if (nextResponse.flow.status === "completed") {
        void onCompleted().catch((err: Error) => {
          setError(err.message);
        });
      }
    },
    [onCompleted],
  );

  useEffect(() => {
    if (!flow || flow.status !== "pending") {
      return undefined;
    }

    let cancelled = false;
    const delayMs = Math.max(flow.interval_seconds ?? 2, 1) * 1000;
    const pollOnce = async () => {
      try {
        const nextResponse =
          flow.method === "browser"
            ? await fetchProviderAuthFlow(provider.id, flow.flow_id)
            : await pollProviderAuthFlow(provider.id, flow.flow_id);
        if (cancelled) {
          return;
        }
        handleFlowUpdate(nextResponse);
        if (cancelled) {
          return;
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message);
        }
      }
    };

    const timeout = window.setTimeout(() => {
      void pollOnce();
    }, delayMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [flow, handleFlowUpdate, provider.id]);

  async function handleStart(nextMethod: "browser" | "device") {
    setMethod(nextMethod);
    setIsStarting(true);
    setError(null);
    setCopyFeedback(null);

    try {
      const response = await startProviderAuthFlow(provider.id, nextMethod);
      setFlowResponse(response);
      if (nextMethod === "browser" && response.flow.authorization_url) {
        window.open(response.flow.authorization_url, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsStarting(false);
    }
  }

  async function copyDeviceCode() {
    if (!flow?.user_code) {
      return;
    }
    try {
      await navigator.clipboard.writeText(flow.user_code);
      setCopyFeedback("Code copied");
    } catch {
      setCopyFeedback("Copy failed");
    }
  }

  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open && !isStarting) onClose();
      }}
      title={`Connect ${authModeLabel}`}
    >
      <div className="flex min-w-0 flex-col gap-4">
          <p className="sr-only">
            Authorize {provider.name} with your {accountLabel}.
          </p>
          <Alert>
            <AlertDescription>
              Sign in with {accountLabel} for <strong>{provider.name}</strong>.
            </AlertDescription>
          </Alert>

          {methods.length > 1 && (
            <Field>
              <FieldLabel>Method</FieldLabel>
              <ToggleGroup
                type="single"
                value={method}
                onValueChange={(value) => {
                  if (value === "browser" || value === "device") setMethod(value);
                }}
                data-settings-auth-mode-tabs=""
                spacing={1}
                variant="outline"
              >
                {methods.map((value) => (
                  <ToggleGroupItem
                    key={value}
                    value={value}
                    disabled={isStarting}
                  >
                    {value === "browser" ? "Browser" : "Device code"}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </Field>
          )}

          {!flow && (
            <Button
              type="button"
              className="self-start"
              onClick={() => {
                  void handleStart(method);
                }}
              disabled={isStarting}
            >
              {isStarting
                ? "Starting…"
                : method === "browser"
                  ? "Start browser sign-in"
                  : "Generate device code"}
            </Button>
          )}

          {flow && (
            <div className="flex min-w-0 flex-col gap-3 rounded-lg border border-border p-3">
              <div className="flex flex-wrap gap-1">
                <Badge size="meta" variant="secondary">
                  {flow.method === "browser" ? "Browser flow" : "Device code"}
                </Badge>
                <Badge
                  size="meta"
                  variant={
                    flow.status === "completed"
                      ? "success"
                      : flow.status === "failed"
                        ? "destructive"
                        : "secondary"
                  }
                >
                  {flow.status}
                </Badge>
                {flow.backend && (
                  <Badge size="meta" variant="outline">{flow.backend}</Badge>
                )}
              </div>

              {flow.method === "browser" && flow.authorization_url && flow.status === "pending" && (
                <div className="flex min-w-0 flex-col gap-2">
                  <div className="text-xs font-medium text-muted-foreground">Authorization URL</div>
                  <a
                    href={flow.authorization_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sm break-all text-primary underline-offset-4 hover:underline"
                  >
                    <ExternalLinkIcon aria-hidden="true" />
                    Open authorization
                  </a>
                  <div className="text-xs text-muted-foreground">
                    Complete the sign-in in the opened tab, then return here.
                  </div>
                </div>
              )}

              {flow.method === "device" && flow.status === "pending" && (
                <div className="flex min-w-0 flex-col gap-2">
                  <div className="text-xs font-medium text-muted-foreground">Verification</div>
                  {flow.verification_url && (
                    <a
                      href={flow.verification_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-sm break-all text-primary underline-offset-4 hover:underline"
                    >
                      {flow.verification_url}
                    </a>
                  )}
                  {flow.user_code && (
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="rounded-md bg-muted px-2 py-1 font-mono text-base font-semibold tracking-widest">{flow.user_code}</code>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          void copyDeviceCode();
                        }}
                      >
                        <CopyIcon data-icon="inline-start" />
                        Copy code
                      </Button>
                    </div>
                  )}
                  {copyFeedback && (
                    <div className="text-xs text-muted-foreground">{copyFeedback}</div>
                  )}
                </div>
              )}

              {flow.status === "pending" && (
                <Alert>
                  <AlertDescription>
                  Waiting for authorization… The page will update automatically.
                  </AlertDescription>
                </Alert>
              )}

              {flow.status === "failed" && flow.error_message && (
                <Alert variant="destructive">
                  <AlertDescription>{flow.error_message}</AlertDescription>
                </Alert>
              )}

              {flow.status === "completed" && (
                <Alert>
                  <CheckCircle2Icon />
                  <AlertDescription>
                  Connected
                  {session?.email ? ` as ${session.email}` : ""}
                  {session?.plan_type ? ` (${session.plan_type})` : ""}.
                  {sessionExpires ? ` Expires ${sessionExpires}.` : ""}
                  </AlertDescription>
                </Alert>
              )}

              <div className="flex flex-wrap items-center justify-end gap-2">
                {flow.status === "pending" && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const next =
                        flow.method === "browser"
                          ? fetchProviderAuthFlow(provider.id, flow.flow_id)
                          : pollProviderAuthFlow(provider.id, flow.flow_id);
                      void next.then(
                        (response) => handleFlowUpdate(response),
                        (err: Error) => setError(err.message),
                      );
                    }}
                  >
                    <CheckCircle2Icon data-icon="inline-start" />
                    Check status
                  </Button>
                )}
                {flow.status !== "completed" && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void handleStart(method);
                    }}
                    disabled={isStarting}
                  >
                    <RefreshCcwIcon data-icon="inline-start" />
                    {isStarting ? "Restarting…" : "Restart flow"}
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  onClick={onClose}
                  disabled={isStarting}
                >
                  {flow.status === "completed" ? "Done" : "Close"}
                </Button>
              </div>
            </div>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
      </div>
    </FormDialog>
  );
}
