/**
 * Lazy Shiki highlighter wrapper.
 *
 * Shiki is dynamically imported on the first highlight call so the initial
 * webapp bundle stays unaffected for sessions that never read a code file.
 * The underlying singleton highlighter caches loaded grammars/themes between
 * calls. On any failure we resolve to `null` so the caller can fall back to
 * plain text rendering instead of surfacing an error to the user.
 */

const LIGHT_THEME = "github-light";
const DARK_THEME = "github-dark";

type CodeToHtml = (
  code: string,
  options: {
    lang: string;
    themes: { light: string; dark: string };
    defaultColor?: false;
  },
) => Promise<string>;

let codeToHtmlPromise: Promise<CodeToHtml | null> | null = null;

async function getCodeToHtml(): Promise<CodeToHtml | null> {
  if (!codeToHtmlPromise) {
    codeToHtmlPromise = import("shiki")
      .then((mod) => mod.codeToHtml as CodeToHtml)
      .catch((error) => {
        console.warn("[pbi-agent] failed to load shiki highlighter", error);
        return null;
      });
  }
  return codeToHtmlPromise;
}

export async function highlightCode(
  code: string,
  language: string,
): Promise<string | null> {
  if (!code || !language) return null;
  const codeToHtml = await getCodeToHtml();
  if (!codeToHtml) return null;
  try {
    return await codeToHtml(code, {
      lang: language,
      themes: { light: LIGHT_THEME, dark: DARK_THEME },
      defaultColor: false,
    });
  } catch (error) {
    console.warn(
      `[pbi-agent] failed to highlight ${language} snippet`,
      error,
    );
    return null;
  }
}

/** Test-only hook to reset the cached dynamic import between cases. */
export function __resetShikiCacheForTests(): void {
  codeToHtmlPromise = null;
}
