/**
 * Map a workspace path to a Shiki language id for syntax highlighting.
 *
 * Pure, extension-driven. Returns `undefined` for unknown extensions so the
 * caller can fall back to plain text rendering. Filename-only matches (e.g.
 * `Dockerfile`, `Makefile`) are honored before extension lookup.
 */

const FILENAME_LANGUAGES: Record<string, string> = {
  dockerfile: "dockerfile",
  containerfile: "dockerfile",
  makefile: "make",
  gemfile: "ruby",
  rakefile: "ruby",
  cmakelists: "cmake",
};

const EXTENSION_LANGUAGES: Record<string, string> = {
  // Python
  py: "python",
  pyi: "python",
  pyw: "python",
  // TypeScript / JavaScript
  ts: "typescript",
  mts: "typescript",
  cts: "typescript",
  tsx: "tsx",
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  jsx: "jsx",
  // Data / config
  json: "json",
  jsonc: "jsonc",
  json5: "json5",
  yml: "yaml",
  yaml: "yaml",
  toml: "toml",
  ini: "ini",
  env: "dotenv",
  properties: "properties",
  // Markup
  md: "markdown",
  markdown: "markdown",
  mdx: "mdx",
  html: "html",
  htm: "html",
  xml: "xml",
  svg: "xml",
  vue: "vue",
  svelte: "svelte",
  // Stylesheets
  css: "css",
  scss: "scss",
  sass: "sass",
  less: "less",
  // Shell
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  fish: "fish",
  ps1: "powershell",
  // Systems / compiled
  rs: "rust",
  go: "go",
  java: "java",
  kt: "kotlin",
  kts: "kotlin",
  scala: "scala",
  c: "c",
  h: "c",
  cpp: "cpp",
  cc: "cpp",
  cxx: "cpp",
  hpp: "cpp",
  hh: "cpp",
  cs: "csharp",
  swift: "swift",
  m: "objective-c",
  mm: "objective-cpp",
  // Scripting
  rb: "ruby",
  php: "php",
  lua: "lua",
  pl: "perl",
  r: "r",
  dart: "dart",
  // Database / query
  sql: "sql",
  graphql: "graphql",
  gql: "graphql",
  // Other
  diff: "diff",
  patch: "diff",
  dockerfile: "dockerfile",
  tf: "hcl",
  hcl: "hcl",
  proto: "proto",
};

/**
 * Normalize a path/filename to a Shiki language id, or `undefined` if no
 * mapping is known. Case-insensitive.
 */
export function languageForPath(path: string | undefined | null): string | undefined {
  if (!path) return undefined;
  const segment = path.split(/[\\/]/).pop() ?? "";
  if (!segment) return undefined;

  const lowered = segment.toLowerCase();
  if (FILENAME_LANGUAGES[lowered]) return FILENAME_LANGUAGES[lowered];

  const dot = lowered.lastIndexOf(".");
  if (dot <= 0 || dot === lowered.length - 1) return undefined;
  const ext = lowered.slice(dot + 1);
  return EXTENSION_LANGUAGES[ext];
}

/**
 * Commands that print a file's contents verbatim to stdout. The first
 * non-flag argument is treated as the source path for language detection.
 */
const FILE_PRINT_COMMANDS: ReadonlySet<string> = new Set([
  "cat",
  "bat",
  "head",
  "tail",
  "less",
  "more",
  "type",
]);

/**
 * Heuristically infer a Shiki language id for a shell command's stdout.
 *
 * Conservative on purpose: only recognizes a handful of patterns where the
 * output format is unambiguous. Returns `undefined` when nothing matches so
 * the caller falls back to plain text.
 *
 * Recognized patterns:
 * - `git diff` / `git show` / `git log -p` / bare `diff` → `diff`
 * - `cat`/`bat`/`head`/`tail`/`less`/`more`/`type <file>` → language of the
 *   first non-flag argument resolved via {@link languageForPath}.
 */
export function inferShellOutputLanguage(
  command: string | undefined | null,
): string | undefined {
  if (!command) return undefined;
  const trimmed = command.trim();
  if (!trimmed) return undefined;

  if (/^(git\s+(diff|show)|git\s+log\s+.*-p|diff)\b/.test(trimmed)) {
    return "diff";
  }

  const tokens = trimmed.split(/\s+/);
  if (tokens.length < 2) return undefined;
  const head = tokens[0]?.split(/[\\/]/).pop()?.toLowerCase() ?? "";
  if (!FILE_PRINT_COMMANDS.has(head)) return undefined;

  for (const token of tokens.slice(1)) {
    if (!token || token.startsWith("-")) continue;
    const language = languageForPath(token);
    if (language) return language;
  }
  return undefined;
}
