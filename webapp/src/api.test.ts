import {
  ApiError,
  deleteModelProfile,
  fetchSessions,
  setActiveModelProfile,
  uploadSessionImages,
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
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
  });

  it("omits the default content type for form uploads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ uploads: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await uploadSessionImages("live-1", [
      new File(["binary"], "diagram.png", { type: "image/png" }),
    ]);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
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

  it("derives websocket URLs from the current browser location", () => {
    vi.stubGlobal("window", {
      location: {
        protocol: "https:",
        host: "agent.test:9443",
      },
    });

    expect(websocketUrl("/api/events/live-1")).toBe(
      "wss://agent.test:9443/api/events/live-1",
    );
  });
});
