import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchProviderAuthFlow,
  pollProviderAuthFlow,
  startProviderAuthFlow,
} from "../../api";
import type { ProviderAuthFlowResponse, ProviderView } from "../../types";

interface Props {
  provider: ProviderView;
  onClose: () => void;
  onCompleted: () => Promise<void>;
}

function formatDateTime(timestamp: number | null): string | null {
  if (!timestamp) {
    return null;
  }
  return new Date(timestamp * 1000).toLocaleString();
}

export function ProviderAuthFlowModal({ provider, onClose, onCompleted }: Props) {
  const [method, setMethod] = useState<"browser" | "device">("browser");
  const [flowResponse, setFlowResponse] =
    useState<ProviderAuthFlowResponse | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

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
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(event) => event.stopPropagation()}>
        <div className="modal-card__header">
          <h2 className="modal-card__title">Connect ChatGPT account</h2>
          <button
            type="button"
            className="modal-card__close"
            onClick={onClose}
            disabled={isStarting}
          >
            &times;
          </button>
        </div>

        <div className="task-form provider-auth-flow-modal">
          <div className="settings-inline-note provider-auth-inline-note">
            Authorize <strong>{provider.name}</strong> with your ChatGPT subscription
            account. Browser auth is the default; device code works as a fallback.
          </div>

          <div className="task-form__field">
            <label className="task-form__label">Method</label>
            <div className="secret-mode-tabs provider-auth-mode-tabs">
              {([
                ["browser", "Browser"],
                ["device", "Device code"],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`secret-mode-tab${method === value ? " active" : ""}`}
                  onClick={() => setMethod(value)}
                  disabled={isStarting}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {!flow && (
            <div className="provider-auth-actions-row">
              <button
                type="button"
                className="btn btn--primary"
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
              </button>
            </div>
          )}

          {flow && (
            <div className="provider-auth-flow-panel">
              <div className="settings-item__meta">
                <span className="settings-item__tag">
                  {flow.method === "browser" ? "Browser flow" : "Device code"}
                </span>
                <span
                  className={`settings-item__tag ${
                    flow.status === "completed"
                      ? "settings-item__tag--success"
                      : flow.status === "failed"
                        ? "settings-item__tag--error"
                        : ""
                  }`}
                >
                  {flow.status}
                </span>
                {flow.backend && (
                  <span className="settings-item__tag">{flow.backend}</span>
                )}
              </div>

              {flow.method === "browser" && flow.authorization_url && flow.status === "pending" && (
                <div className="provider-auth-flow-block">
                  <div className="provider-auth-flow-label">Authorization URL</div>
                  <a
                    href={flow.authorization_url}
                    target="_blank"
                    rel="noreferrer"
                    className="provider-auth-flow-link"
                  >
                    Open ChatGPT authorization
                  </a>
                  <div className="task-form__hint">
                    Complete the sign-in in the opened tab, then return here.
                  </div>
                </div>
              )}

              {flow.method === "device" && flow.status === "pending" && (
                <div className="provider-auth-flow-block">
                  <div className="provider-auth-flow-label">Verification</div>
                  {flow.verification_url && (
                    <a
                      href={flow.verification_url}
                      target="_blank"
                      rel="noreferrer"
                      className="provider-auth-flow-link"
                    >
                      {flow.verification_url}
                    </a>
                  )}
                  {flow.user_code && (
                    <div className="provider-auth-code-row">
                      <code className="provider-auth-code">{flow.user_code}</code>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => {
                          void copyDeviceCode();
                        }}
                      >
                        Copy code
                      </button>
                    </div>
                  )}
                  {copyFeedback && (
                    <div className="task-form__hint">{copyFeedback}</div>
                  )}
                </div>
              )}

              {flow.status === "pending" && (
                <div className="settings-inline-note provider-auth-inline-note">
                  Waiting for authorization… The page will update automatically.
                </div>
              )}

              {flow.status === "failed" && flow.error_message && (
                <div className="task-form__error">{flow.error_message}</div>
              )}

              {flow.status === "completed" && (
                <div className="settings-inline-note provider-auth-inline-note">
                  Connected{session?.email ? ` as ${session.email}` : ""}
                  {session?.plan_type ? ` (${session.plan_type})` : ""}.
                  {sessionExpires ? ` Expires ${sessionExpires}.` : ""}
                </div>
              )}

              <div className="provider-auth-actions-row">
                {flow.status === "pending" && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => {
                      if (flow.method === "browser") {
                        void fetchProviderAuthFlow(provider.id, flow.flow_id).then(
                          (nextResponse) => handleFlowUpdate(nextResponse),
                          (err: Error) => setError(err.message),
                        );
                      } else {
                        void pollProviderAuthFlow(provider.id, flow.flow_id).then(
                          (nextResponse) => handleFlowUpdate(nextResponse),
                          (err: Error) => setError(err.message),
                        );
                      }
                    }}
                  >
                    Check status
                  </button>
                )}
                {flow.status !== "completed" && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => {
                      void handleStart(method);
                    }}
                    disabled={isStarting}
                  >
                    {isStarting ? "Restarting…" : "Restart flow"}
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  onClick={onClose}
                  disabled={isStarting}
                >
                  {flow.status === "completed" ? "Done" : "Close"}
                </button>
              </div>
            </div>
          )}

          {error && <div className="task-form__error">{error}</div>}
        </div>
      </div>
    </div>
  );
}
