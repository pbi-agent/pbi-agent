import {
  ApiError,
  deleteModelProfile,
  eventStreamUrl,
  fetchProviderAuthFlow,
  fetchProviderAuthStatus,
  fetchProviderUsageLimits,
  fetchSessions,
  logoutProviderAuth,
  pollProviderAuthFlow,
  refreshProviderAuth,
  setActiveModelProfile,
  startProviderAuthFlow,
  updateSession,
  uploadTaskImages,
  websocketUrl,
} from "./api";

describe("api helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON payloads for successful requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ sessions: [{ session_id: "s-1" }] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchSessions()).resolves.toEqual([{ session_id: "s-1" }]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sessions",
      expect.anything(),
    );
  });

  it("uploads task images as form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ uploads: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await uploadTaskImages([
      new File(["binary"], "task.png", { type: "image/png" }),
    ]);

    const uploadCall = fetchMock.mock.calls[0];
    if (!uploadCall) {
      throw new Error("Expected task image upload call");
    }
    expect(uploadCall[0]).toBe("/api/tasks/images");
    const init = uploadCall[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("updates saved sessions with a PATCH payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session: { session_id: "session-1", title: "New title" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(updateSession("session-1", { title: "New title" })).resolves.toEqual({
      session_id: "session-1",
      title: "New title",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sessions/session-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ title: "New title" }),
      }),
    );
  });

  it("returns undefined for 204 responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteModelProfile("profile-1", "rev-1")).resolves.toBeUndefined();
  });

  it("raises ApiError with the server detail for failed requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "stale config" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(setActiveModelProfile("analysis", "rev-1")).rejects.toEqual(
      expect.objectContaining<ApiError>({
        name: "ApiError",
        message: "stale config",
        status: 409,
      }),
    );
  });

  it("calls provider auth endpoints with the expected payloads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            provider: { id: "openai-chatgpt" },
            auth_status: { session_status: "missing" },
            session: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            provider: { id: "openai-chatgpt" },
            auth_status: { session_status: "missing" },
            flow: { flow_id: "flow-1", status: "pending" },
            session: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            provider: { id: "openai-chatgpt" },
            auth_status: { session_status: "pending" },
            flow: { flow_id: "flow-1", status: "pending" },
            session: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            provider: { id: "openai-chatgpt" },
            auth_status: { session_status: "connected" },
            flow: { flow_id: "flow-1", status: "completed" },
            session: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            provider: { id: "openai-chatgpt" },
            auth_status: { session_status: "connected" },
            session: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            provider: { id: "openai-chatgpt" },
            auth_status: { session_status: "missing" },
            removed: true,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            provider_id: "openai-chatgpt",
            provider_kind: "chatgpt",
            account_label: "user@example.com",
            plan_type: "pro",
            fetched_at: "2026-05-01T00:00:00Z",
            buckets: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await fetchProviderAuthStatus("openai-chatgpt");
    await startProviderAuthFlow("openai-chatgpt", "browser");
    await fetchProviderAuthFlow("openai-chatgpt", "flow-1");
    await pollProviderAuthFlow("openai-chatgpt", "flow-1");
    await refreshProviderAuth("openai-chatgpt");
    await logoutProviderAuth("openai-chatgpt");
    await fetchProviderUsageLimits("openai-chatgpt");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/provider-auth/openai-chatgpt",
      expect.anything(),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/provider-auth/openai-chatgpt/flows",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/provider-auth/openai-chatgpt/flows/flow-1",
      expect.anything(),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/provider-auth/openai-chatgpt/flows/flow-1/poll",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/provider-auth/openai-chatgpt/refresh",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/api/provider-auth/openai-chatgpt",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/api/provider-auth/openai-chatgpt/usage-limits",
      expect.anything(),
    );

    const startCall = fetchMock.mock.calls[1];
    if (!startCall) {
      throw new Error("Expected auth flow start call");
    }
    const startInit = startCall[1] as RequestInit;
    expect(startInit.body).toBe(JSON.stringify({ method: "browser" }));
  });

  it("derives websocket URLs from the current browser location", () => {
    vi.stubGlobal("window", {
      location: {
        protocol: "https:",
        host: "agent.test:9443",
        origin: "https://agent.test:9443",
      },
    });

    expect(websocketUrl("/api/events/live-1")).toBe(
      "wss://agent.test:9443/api/events/live-1",
    );
    expect(eventStreamUrl("/api/events/live-1")).toBe(
      "https://agent.test:9443/api/events/live-1",
    );
  });
});
