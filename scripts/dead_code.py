#!/usr/bin/env python3
"""Run Vulture dead-code detection with a repo-friendly summary.

This wrapper is intentionally advisory by default: Vulture exits with status 3
when it finds unused code, but this script returns success unless
``--fail-on-findings`` is set. That makes it useful for first-pass evaluation
without breaking local workflows or CI before a whitelist is established.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATHS = ("src/pbi_agent", "tests")
DEFAULT_MIN_CONFIDENCE = 100
FINDING_RE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+): (?P<message>.*?) "
    r"\((?P<confidence>\d+)% confidence, (?P<size>\d+) lines?\)$"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str
    confidence: int
    size: int

    @property
    def kind(self) -> str:
        if self.message.startswith("unused "):
            return " ".join(self.message.split(" ", 2)[:2])
        if self.message.startswith("unreachable code"):
            return "unreachable code"
        return self.message.split(" ", 1)[0]


def parse_finding(line: str) -> Finding | None:
    match = FINDING_RE.match(line)
    if not match:
        return None
    return Finding(
        path=match.group("path"),
        line=int(match.group("line")),
        message=match.group("message"),
        confidence=int(match.group("confidence")),
        size=int(match.group("size")),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Vulture against the Python backend and summarize likely dead code.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=list(DEFAULT_PATHS),
        help=f"Files/directories to scan (default: {' '.join(DEFAULT_PATHS)}).",
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=DEFAULT_MIN_CONFIDENCE,
        help=f"Minimum Vulture confidence to report (default: {DEFAULT_MIN_CONFIDENCE}).",
    )
    parser.add_argument(
        "--exclude",
        default=None,
        help="Comma-separated Vulture exclude patterns.",
    )
    parser.add_argument(
        "--ignore-decorators",
        default=None,
        help="Comma-separated Vulture decorator ignore patterns, e.g. @router.get,@pytest.fixture.",
    )
    parser.add_argument(
        "--ignore-names",
        default=None,
        help="Comma-separated Vulture name ignore patterns.",
    )
    parser.add_argument(
        "--no-sort-by-size",
        action="store_true",
        help="Do not ask Vulture to sort unused functions/classes by size.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print Vulture's raw output after the summary.",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit non-zero when Vulture reports findings.",
    )
    return parser.parse_args(argv)


def build_vulture_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "vulture",
        *args.paths,
        "--min-confidence",
        str(args.min_confidence),
    ]
    if not args.no_sort_by_size:
        command.append("--sort-by-size")
    if args.exclude:
        command.extend(("--exclude", args.exclude))
    if args.ignore_decorators:
        command.extend(("--ignore-decorators", args.ignore_decorators))
    if args.ignore_names:
        command.extend(("--ignore-names", args.ignore_names))
    return command


def summarize(findings: list[Finding], raw_lines: list[str]) -> str:
    if not findings and not raw_lines:
        return "No dead-code findings reported by Vulture."

    lines = ["Dead-code findings from Vulture", ""]
    if findings:
        total_size = sum(finding.size for finding in findings)
        lines.append(f"Total: {len(findings)} findings, {total_size} reported lines")
        lines.append("")

        by_confidence = Counter(finding.confidence for finding in findings)
        confidence_bits = ", ".join(
            f"{confidence}%: {count}"
            for confidence, count in sorted(by_confidence.items(), reverse=True)
        )
        lines.append(f"By confidence: {confidence_bits}")

        by_kind = Counter(finding.kind for finding in findings)
        lines.append("By kind:")
        for kind, count in by_kind.most_common():
            lines.append(f"  - {kind}: {count}")
        lines.append("")

        by_path: dict[str, list[Finding]] = defaultdict(list)
        for finding in findings:
            by_path[finding.path].append(finding)
        lines.append("By file:")
        for path, file_findings in sorted(by_path.items()):
            file_size = sum(finding.size for finding in file_findings)
            lines.append(
                f"  - {path}: {len(file_findings)} findings, {file_size} lines"
            )
        lines.append("")

        lines.append("Findings:")
        for finding in findings:
            lines.append(
                f"  - {finding.path}:{finding.line}: {finding.message} "
                f"({finding.confidence}% confidence, {finding.size} lines)"
            )
    else:
        lines.append(
            "Vulture produced output, but this wrapper could not parse it as findings."
        )

    if raw_lines:
        lines.append("")
        lines.append("Raw Vulture output:")
        lines.extend(f"  {line}" for line in raw_lines)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    missing_paths = [path for path in args.paths if not Path(path).exists()]
    if missing_paths:
        print(
            f"error: scan path does not exist: {', '.join(missing_paths)}",
            file=sys.stderr,
        )
        return 2

    command = build_vulture_command(args)
    completed = subprocess.run(  # noqa: S603 - command is built from sys.executable plus local args.
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")

    raw_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    findings = [
        finding for line in raw_lines if (finding := parse_finding(line)) is not None
    ]
    print(summarize(findings, raw_lines if args.raw else []))

    if completed.returncode not in (0, 3):
        return completed.returncode
    if findings and args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
