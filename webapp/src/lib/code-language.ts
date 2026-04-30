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
