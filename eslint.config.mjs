import js from "@eslint/js";
import { plugin as shadcn } from "@shadcn/lint";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import path from "node:path";
import { fileURLToPath } from "node:url";
import tseslint from "typescript-eslint";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const typeCheckedParserOptions = {
  projectService: true,
  tsconfigRootDir: rootDir,
};

const shadcnStrictFiles = [
  "webapp/src/**/*.tsx",
  "webapp/src/components/settings/**/*.tsx",
  "webapp/src/components/board/**/*.tsx",
  "webapp/src/components/dashboard/**/*.tsx",
];

function shadcnRules(level) {
  return {
    "shadcn/no-raw-colors": level,
    "shadcn/no-arbitrary-values": level,
    "shadcn/no-inline-styles": level,
    "shadcn/no-unknown-classes": level,
    "shadcn/require-static-classes": level,
    "shadcn/no-restyle": [level, { allow: ["layout"] }],
  };
}

export default tseslint.config(
  {
    ignores: [
      "node_modules/**",
      "src/pbi_agent/web/static/app/**",
      "docs/.vitepress/dist/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    files: ["webapp/src/**/*.{ts,tsx}"],
    languageOptions: {
      globals: globals.browser,
      parserOptions: typeCheckedParserOptions,
    },
    plugins: {
      "react-hooks": reactHooks,
      shadcn,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
    },
  },
  {
    // shadcn design-system policy. Refactored areas are listed in
    // `shadcnStrictFiles` and fail on violations; the rest warn until migrated.
    files: ["webapp/src/**/*.tsx"],
    ignores: ["webapp/src/components/ui/**", "webapp/src/**/*.test.tsx"],
    rules: shadcnRules("warn"),
  },
  {
    files: shadcnStrictFiles,
    ignores: ["webapp/src/components/ui/**", "webapp/src/**/*.test.tsx"],
    rules: shadcnRules("error"),
  },
  {
    files: ["webapp/vite.config.ts"],
    languageOptions: {
      globals: globals.node,
      parserOptions: typeCheckedParserOptions,
    },
  },
);
