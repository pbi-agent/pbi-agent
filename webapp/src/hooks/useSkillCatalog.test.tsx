import { renderHook, waitFor } from "@testing-library/react";
import { searchSkillMentions } from "../api";
import { resetSkillCatalogForTest, useSkillCatalog } from "./useSkillCatalog";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    searchSkillMentions: vi.fn(),
  };
});

describe("useSkillCatalog", () => {
  beforeEach(() => {
    resetSkillCatalogForTest();
    vi.mocked(searchSkillMentions).mockReset();
  });

  it("dedupes concurrent fetches", async () => {
    vi.mocked(searchSkillMentions).mockResolvedValue({
      items: [{ name: "compress", description: "Compress", path: ".agents/skills/compress/SKILL.md" }],
    });

    const first = renderHook(() => useSkillCatalog());
    const second = renderHook(() => useSkillCatalog());

    await waitFor(() => {
      expect(first.result.current.has("compress")).toBe(true);
      expect(second.result.current.has("compress")).toBe(true);
    });
    expect(searchSkillMentions).toHaveBeenCalledTimes(1);
    expect(searchSkillMentions).toHaveBeenCalledWith("", 200);
  });

  it("surfaces an empty set on error", async () => {
    vi.mocked(searchSkillMentions).mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useSkillCatalog());

    await waitFor(() => expect(searchSkillMentions).toHaveBeenCalledTimes(1));
    expect(result.current.size).toBe(0);
  });
});
