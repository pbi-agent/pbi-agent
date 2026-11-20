import { workspaceFileTargetForLink } from "./workspaceFileLinks";

const origin = "http://127.0.0.1:7424";
const knownFiles = new Set(["LICENSE", "docs/Makefile"]);

describe("workspaceFileTargetForLink", () => {
  it.each([
    ["docs/04_commercial_assessment.md", "docs/04_commercial_assessment.md"],
    [`${origin}/sessions/docs/04_commercial_assessment.md`, "docs/04_commercial_assessment.md"],
    ["/sessions/docs/Pilot%20criteria.md?view=raw#scope", "docs/Pilot criteria.md"],
    ["./LICENSE", "LICENSE"],
    ["docs/Makefile#target", "docs/Makefile"],
    ["src/app.ts:42", "src/app.ts"],
    ["app.ts:42:7", "app.ts"],
    ["Dockerfile", "Dockerfile"],
    ["/home/me/my%20repo/src/app.ts", "src/app.ts"],
    ["/home/me/my repo/src/app.ts:12", "src/app.ts"],
    ["file:///home/me/my%20repo/docs/Makefile", "docs/Makefile"],
    [`${origin}/sessions/session-1/sub-agents/docs/report.md`, "docs/report.md"],
  ])("resolves workspace link %s", (href, path) => {
    expect(workspaceFileTargetForLink(href, origin, knownFiles, "/home/me/my repo")?.path).toBe(path);
  });

  it.each([
    ["C:/Users/Me/Repo/src/app.ts", "src/app.ts"],
    ["/c:/users/me/repo/src/app.ts", "src/app.ts"],
    ["file:///C:/Users/Me/Repo/README.md", "README.md"],
  ])("resolves Windows workspace link %s", (href, path) => {
    expect(workspaceFileTargetForLink(href, origin, knownFiles, "C:\\Users\\Me\\Repo")?.path).toBe(path);
  });

  it.each([
    "https://example.org/sessions/docs/report.md",
    "http://127.0.0.1:7680/sessions/docs/report.md",
    "//example.org/sessions/docs/report.md",
    "mailto:person@example.org",
    "#scope",
    "/settings",
    "/sessions/session-1",
    "/sessions/session-1/sub-agents/worker.v2",
    "../outside.md",
    "/sessions/docs/%2e%2e/outside.md",
    `${origin}/sessions/docs/../outside.md`,
    "docs%2Foutside.md",
    "docs/%5Coutside.md",
    "docs/%00invalid.md",
    "docs/foo%.md",
    "/home/me/other/app.ts",
    "/home/me/my repo/../secret.md",
    "/home/me/my repo/bin",
    "file:///etc/passwd",
    "D:/Users/Me/Repo/src/app.ts",
  ])("does not intercept %s", (href) => {
    expect(workspaceFileTargetForLink(href, origin, knownFiles, "/home/me/my repo")).toBeNull();
  });

  it.each([
    ["src/app.ts", null],
    ["src/app.ts:42", { start: 42, end: 42 }],
    ["src/app.ts:42:7", { start: 42, end: 42 }],
    ["src/app.ts:42-50", { start: 42, end: 50 }],
    ["src/app.ts:50-42", { start: 50, end: 50 }],
    ["src/app.ts#L7", { start: 7, end: 7 }],
    ["src/app.ts?plain=1#L7-L9", { start: 7, end: 9 }],
    ["src/app.ts#L7-9", { start: 7, end: 9 }],
    ["src/app.ts#scope", null],
    ["src/app.ts:0", null],
    ["/home/me/my repo/src/app.ts:12#L99", { start: 12, end: 12 }],
  ])("reads the line range of %s", (href, lines) => {
    expect(workspaceFileTargetForLink(href, origin, knownFiles, "/home/me/my repo")).toEqual({
      path: "src/app.ts",
      lines,
    });
  });
});
