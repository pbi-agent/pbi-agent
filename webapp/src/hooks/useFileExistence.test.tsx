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

const FILE_INDEX_METADATA = {
  index_generation: "test-generation",
  index_revision: 1,
  truncated: false,
  search_approximated: false,
} as const;

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
      ...FILE_INDEX_METADATA,
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
      ...FILE_INDEX_METADATA,
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
    expect(init?.exact).toBe(true);
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    expect(result.current.isFileKnown("docs/file name.md")).toBe(false);
  });

  it("retries instead of caching misses while the file index is scanning", async () => {
    vi.mocked(searchFileMentions)
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
        items: [],
        scan_status: "scanning",
        is_stale: false,
        file_count: 0,
        error: null,
      })
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
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
      ...FILE_INDEX_METADATA,
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

  it("invalidates cached misses when the file index revision changes", async () => {
    vi.mocked(searchFileMentions)
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
        items: [],
        scan_status: "ready",
        is_stale: false,
        file_count: 0,
        error: null,
      })
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
        index_revision: 2,
        items: [{ path: "src/new.py", kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      });

    const { result, rerender } = renderHook(
      ({ revision }) =>
        useFileExistence(["src/new.py"], {
          workspaceKey: "workspace-a",
          indexGeneration: "test-generation",
          indexRevision: revision,
        }),
      { initialProps: { revision: 1 } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });
    expect(result.current.isFileKnown("src/new.py")).toBe(false);

    rerender({ revision: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    expect(searchFileMentions).toHaveBeenCalledTimes(2);
    expect(result.current.isFileKnown("src/new.py")).toBe(true);
  });

  it("accepts a lower revision when the index generation changes", async () => {
    vi.mocked(searchFileMentions)
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
        index_generation: "old-generation",
        index_revision: 5,
        items: [],
        scan_status: "ready",
        is_stale: false,
        file_count: 0,
        error: null,
      })
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
        index_generation: "new-generation",
        items: [{ path: "src/new.py", kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      });

    const { result, rerender } = renderHook(
      ({ generation, revision }) =>
        useFileExistence(["src/new.py"], {
          workspaceKey: "workspace-a",
          indexGeneration: generation,
          indexRevision: revision,
        }),
      {
        initialProps: {
          generation: "old-generation",
          revision: 5,
        },
      },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });
    expect(result.current.isFileKnown("src/new.py")).toBe(false);

    rerender({ generation: "new-generation", revision: 1 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    expect(searchFileMentions).toHaveBeenCalledTimes(2);
    expect(result.current.isFileKnown("src/new.py")).toBe(true);
  });

  it("uses a newer revision learned from an existence response", async () => {
    vi.mocked(searchFileMentions).mockResolvedValueOnce({
      ...FILE_INDEX_METADATA,
      index_revision: 2,
      items: [{ path: "src/new.py", kind: "file" }],
      scan_status: "ready",
      is_stale: false,
      file_count: 1,
      error: null,
    });

    const { result } = renderHook(() =>
      useFileExistence(["src/new.py"], {
        workspaceKey: "workspace-a",
        indexRevision: 1,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    expect(result.current.isFileKnown("src/new.py")).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });
    expect(searchFileMentions).toHaveBeenCalledTimes(1);
  });

  it("does not regress the observed revision when an older response arrives last", async () => {
    vi.mocked(searchFileMentions).mockImplementation(async (query) => {
      if (query === "src/first.py") {
        return {
          ...FILE_INDEX_METADATA,
          index_revision: 2,
          items: [{ path: query, kind: "file" }],
          scan_status: "ready",
          is_stale: false,
          file_count: 2,
          error: null,
        };
      }
      await Promise.resolve();
      return {
        ...FILE_INDEX_METADATA,
        items: [{ path: query, kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      };
    });

    const { result } = renderHook(() =>
      useFileExistence(["src/first.py", "src/second.py"], {
        workspaceKey: "workspace-a",
        indexRevision: 1,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    expect(result.current.isFileKnown("src/first.py")).toBe(true);
  });

  it("scopes cached existence results to the workspace", async () => {
    vi.mocked(searchFileMentions)
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
        items: [{ path: "src/main.py", kind: "file" }],
        scan_status: "ready",
        is_stale: false,
        file_count: 1,
        error: null,
      })
      .mockResolvedValueOnce({
        ...FILE_INDEX_METADATA,
        items: [],
        scan_status: "ready",
        is_stale: false,
        file_count: 0,
        error: null,
      });

    const { result, rerender } = renderHook(
      ({ workspaceKey }) =>
        useFileExistence(["src/main.py"], {
          workspaceKey,
          indexRevision: 1,
        }),
      { initialProps: { workspaceKey: "workspace-a" } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });
    expect(result.current.isFileKnown("src/main.py")).toBe(true);

    rerender({ workspaceKey: "workspace-b" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(750);
    });

    expect(searchFileMentions).toHaveBeenCalledTimes(2);
    expect(result.current.isFileKnown("src/main.py")).toBe(false);
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
