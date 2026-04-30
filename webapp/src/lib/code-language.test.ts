import { describe, expect, it } from "vitest";
import { languageForPath } from "./code-language";

describe("languageForPath", () => {
  it("maps common extensions to Shiki language ids", () => {
    expect(languageForPath("src/main.py")).toBe("python");
    expect(languageForPath("src/component.tsx")).toBe("tsx");
    expect(languageForPath("src/component.ts")).toBe("typescript");
    expect(languageForPath("src/script.mjs")).toBe("javascript");
    expect(languageForPath("config/data.json")).toBe("json");
    expect(languageForPath("config.YAML")).toBe("yaml");
    expect(languageForPath("README.md")).toBe("markdown");
    expect(languageForPath("Cargo.toml")).toBe("toml");
    expect(languageForPath("install.sh")).toBe("bash");
    expect(languageForPath("style.scss")).toBe("scss");
    expect(languageForPath("query.sql")).toBe("sql");
    expect(languageForPath("main.rs")).toBe("rust");
  });

  it("matches recognized filenames without extensions", () => {
    expect(languageForPath("Dockerfile")).toBe("dockerfile");
    expect(languageForPath("project/Dockerfile")).toBe("dockerfile");
    expect(languageForPath("Makefile")).toBe("make");
    expect(languageForPath("Gemfile")).toBe("ruby");
  });

  it("is case-insensitive across path separators", () => {
    expect(languageForPath("path\\to\\Component.TSX")).toBe("tsx");
    expect(languageForPath("/abs/path/main.PY")).toBe("python");
  });

  it("returns undefined for unknown or unsupported paths", () => {
    expect(languageForPath(undefined)).toBeUndefined();
    expect(languageForPath(null)).toBeUndefined();
    expect(languageForPath("")).toBeUndefined();
    expect(languageForPath("notes.unknownext")).toBeUndefined();
    expect(languageForPath("image.png")).toBeUndefined();
    expect(languageForPath("archive.tar.gz")).toBeUndefined();
    expect(languageForPath("noext")).toBeUndefined();
    expect(languageForPath(".gitignore")).toBeUndefined();
    expect(languageForPath("trailingdot.")).toBeUndefined();
  });
});
