import { describe, expect, it } from "vitest";
import {
  getWorkspaceFileIcon,
  getWorkspaceFolderIcon,
} from "./workspaceFileIcons";

describe("workspace file icons", () => {
  it.each([
    ["src/app.ts", "typescript"],
    ["src/app.test.ts", "test-ts"],
    ["src/App.tsx", "react_ts"],
    ["package.json", "nodejs"],
    ["bun.lock", "bun"],
    [".gitignore", "git"],
    [".env.local", "tune"],
    ["README.md", "readme"],
    ["styles/global.css", "css"],
    ["public/logo.png", "image"],
  ])("maps %s to the Material Icon Theme %s icon", (path, iconName) => {
    const icon = getWorkspaceFileIcon(path);

    expect(icon.iconName).toBe(iconName);
    expect(icon.url).toContain(".svg");
  });

  it("uses the requested fallback icon when no file association matches", () => {
    const icon = getWorkspaceFileIcon("upload.unknown-extension", "image");

    expect(icon.iconName).toBe("image");
    expect(icon.url).toContain(".svg");
  });

  it.each([
    ["src", false, "folder-src"],
    ["src", true, "folder-src-open"],
    ["styles", true, "folder-css-open"],
    [".github/workflows", false, "folder-gh-workflows"],
    ["unknown-folder", false, "folder"],
    ["unknown-folder", true, "folder-open"],
  ])("maps folder %s expanded=%s to %s", (path, expanded, iconName) => {
    const icon = getWorkspaceFolderIcon(path, expanded);

    expect(icon.iconName).toBe(iconName);
    expect(icon.url).toContain(".svg");
  });
});