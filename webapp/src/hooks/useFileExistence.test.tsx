import { act, renderHook } from "@testing-library/react";
import { searchFileMentions } from "../api";
import { resetFileExistenceForTest, useFileExistence } from "./useFileExistence";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    searchFileMentions: vi.fn(),
  };
});

describe("useFileExistence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetFileExistenceForTest();
    vi.mocked(searchFileMentions).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("treats only exact path equality as known and honors debounce", async () => {
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [{ path: "src/main.py", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });

    const { result } = renderHook(() => useFileExistence(["src/main.py"]));

    expect(searchFileMentions).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(749);
    });
    expect(searchFileMentions).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(result.current.isFileKnown("src/main.py")).toBe(true);
  });

  it("unescapes spaces before lookup and marks non-exact matches unknown", async () => {
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [{ path: "docs/file name.md.bak", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });

    const { result } = renderHook(() => useFileExistence(["docs/file\\ name.md"]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    const [query, limit, init] = vi.mocked(searchFileMentions).mock.calls[0] ?? [];
    expect(query).toBe("docs/file name.md");
    expect(limit).toBe(8);
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    expect(result.current.isFileKnown("docs/file name.md")).toBe(false);
  });

  it("retries instead of caching misses while the file index is scanning", async () => {
    vi.mocked(searchFileMentions)
      .mockResolvedValueOnce({
        items: [],
        scan_status: "scanning",
        is_stale: false,
        file_count: 0,
        error: null,
      })
      .mockResolvedValueOnce({
        items: [{ path: "src/main.py", kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      });

    const { result } = renderHook(() => useFileExistence(["src/main.py"]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });
    expect(result.current.isFileKnown("src/main.py")).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    expect(searchFileMentions).toHaveBeenCalledTimes(2);
    expect(result.current.isFileKnown("src/main.py")).toBe(true);
  });

  it("caches repeated tokens", async () => {
    vi.mocked(searchFileMentions).mockResolvedValue({
      items: [{ path: "src/main.py", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });

    const { rerender } = renderHook(({ tokens }) => useFileExistence(tokens), {
      initialProps: { tokens: ["src/main.py", "src/main.py"] },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });
    expect(searchFileMentions).toHaveBeenCalledTimes(1);

    rerender({ tokens: ["src/main.py"] });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    expect(searchFileMentions).toHaveBeenCalledTimes(1);
  });

  it("aborts pending requests when token changes", async () => {
    const abortSignals: AbortSignal[] = [];
    vi.mocked(searchFileMentions).mockImplementation((_query, _limit, init) => {
      if (init?.signal) abortSignals.push(init.signal);
      return new Promise(() => undefined);
    });

    const { rerender } = renderHook(({ tokens }) => useFileExistence(tokens), {
      initialProps: { tokens: ["src/old.py"] },
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });
    rerender({ tokens: ["src/new.py"] });

    expect(abortSignals[0]?.aborted).toBe(true);
  });
});
