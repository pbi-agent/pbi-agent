from __future__ import annotations

import fnmatch
from typing import Callable

# All entries are stored case-folded so that the lookup in
# ``should_skip_directory_name`` (which also case-folds its argument) works
# correctly for mixed-case names like "CVS" or "DerivedData".
SKIP_DIRECTORY_NAMES: frozenset[str] = frozenset(
    name.casefold()
    for name in {
        # -- Version control ---------------------------------------------------
        ".git",
        ".hg",
        ".svn",
        ".bzr",
        "CVS",
        "_darcs",
        ".fossil",
        ".jj",
        # -- Python ------------------------------------------------------------
        "__pycache__",
        ".venv",
        "venv",
        "site-packages",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".eggs",
        ".hypothesis",
        ".pytype",
        ".pyre",
        ".pyright",
        "__pypackages__",
        ".ipynb_checkpoints",
        ".pixi",
        ".conda",
        ".mamba",
        ".pdm-build",
        ".pdm-python",
        ".pants.d",
        ".pants.workdir",
        # -- JavaScript / Node -------------------------------------------------
        "node_modules",
        "bower_components",
        "jspm_packages",
        ".yarn",
        ".pnp",
        ".parcel-cache",
        ".turbo",
        ".nx",
        ".npm",
        ".pnpm-store",
        ".angular",
        ".svelte-kit",
        "__sapper__",
        ".rush",
        ".lerna",
        ".deno",
        ".bun",
        ".webpack",
        ".rollup",
        ".vite",
        ".esbuild",
        ".swc",
        ".expo",
        # -- Java / JVM --------------------------------------------------------
        ".gradle",
        ".m2",
        ".mvn",
        ".sbt",
        ".metals",
        ".bloop",
        ".bsp",
        # -- .NET --------------------------------------------------------------
        ".nuget",
        # -- Rust --------------------------------------------------------------
        ".cargo",
        # -- Ruby --------------------------------------------------------------
        ".bundle",
        "sorbet",
        # -- C / C++ -----------------------------------------------------------
        "CMakeFiles",
        "cmake-build-debug",
        "cmake-build-release",
        ".ccache",
        "autom4te.cache",
        # -- Bazel -------------------------------------------------------------
        "bazel-bin",
        "bazel-out",
        "bazel-testlogs",
        "bazel-genfiles",
        ".bazel",
        "_bazel_cache",
        # -- Swift / iOS -------------------------------------------------------
        ".build",
        "DerivedData",
        "Pods",
        "Carthage",
        "xcuserdata",
        # -- Dart / Flutter ----------------------------------------------------
        ".dart_tool",
        ".pub-cache",
        ".flutter-plugins",
        ".flutter-plugins-dependencies",
        # -- Haskell -----------------------------------------------------------
        ".stack-work",
        "dist-newstyle",
        # -- Elixir ------------------------------------------------------------
        ".elixir_ls",
        # -- Zig ---------------------------------------------------------------
        "zig-cache",
        "zig-out",
        # -- R -----------------------------------------------------------------
        "renv",
        "packrat",
        ".Rproj.user",
        # -- IDE / Editor ------------------------------------------------------
        ".idea",
        ".vscode",
        ".vs",
        ".eclipse",
        ".fleet",
        ".zed",
        ".cursor",
        # -- Framework build outputs -------------------------------------------
        ".next",
        ".nuxt",
        ".output",
        "storybook-static",
        ".docusaurus",
        ".astro",
        # -- Infrastructure / deploy -------------------------------------------
        ".terraform",
        ".terragrunt-cache",
        ".serverless",
        "cdk.out",
        ".pulumi",
        ".vagrant",
        ".molecule",
        ".vercel",
        ".netlify",
        ".amplify",
        ".firebase",
        # -- Coverage ----------------------------------------------------------
        "htmlcov",
        ".nyc_output",
        # -- Caches ------------------------------------------------------------
        ".cache",
        ".sass-cache",
        ".eslintcache",
        ".stylelintcache",
        ".prettiercache",
        # -- Temp / OS ---------------------------------------------------------
        ".tmp",
        ".temp",
        "$RECYCLE.BIN",
        "System Volume Information",
    }
)


def should_skip_directory_name(name: str) -> bool:
    return name.casefold() in SKIP_DIRECTORY_NAMES


# ---------------------------------------------------------------------------
# Shared glob matching
# ---------------------------------------------------------------------------


def build_glob_matcher(glob_pattern: str | None) -> Callable[[str, str], bool]:
    """Return a ``(relative_path, name) -> bool`` predicate for *glob_pattern*.

    When *glob_pattern* is ``None`` or blank the returned matcher accepts
    everything.
    """
    if not isinstance(glob_pattern, str) or not glob_pattern.strip():
        return lambda relative_path, name: True

    normalized_pattern = glob_pattern.replace("\\", "/").strip()
    if "/" in normalized_pattern:
        pattern_parts = tuple(part for part in normalized_pattern.split("/") if part)
        return lambda relative_path, name: _match_relative_path(
            relative_path, pattern_parts
        )
    return lambda relative_path, name: fnmatch.fnmatch(name, normalized_pattern)


def _match_relative_path(
    relative_path: str, pattern_parts: tuple[str, ...]
) -> bool:
    path_parts = tuple(part for part in relative_path.split("/") if part)
    return _match_path_parts(path_parts, pattern_parts, 0, 0)


def _match_path_parts(
    path_parts: tuple[str, ...],
    pattern_parts: tuple[str, ...],
    path_index: int,
    pattern_index: int,
) -> bool:
    while True:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)

        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return _match_globstar(
                path_parts, pattern_parts, path_index, pattern_index + 1
            )

        if path_index >= len(path_parts):
            return False

        if not fnmatch.fnmatchcase(path_parts[path_index], pattern_part):
            return False

        path_index += 1
        pattern_index += 1


def _match_globstar(
    path_parts: tuple[str, ...],
    pattern_parts: tuple[str, ...],
    path_index: int,
    next_pattern_index: int,
) -> bool:
    for next_path_index in range(path_index, len(path_parts) + 1):
        if _match_path_parts(
            path_parts, pattern_parts, next_path_index, next_pattern_index
        ):
            return True
    return False
