from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read_workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def assert_release_gates(workflow: str) -> None:
    expected_commands = [
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run pytest",
        "bun run test:web",
        "bun run lint",
        "bun run typecheck",
        "bun run web:api-types",
        "git diff --exit-code -- webapp/src/api-types.generated.ts",
        "bun run web:build",
        "git diff --exit-code -- src/pbi_agent/web/static/app",
        "bun run docs:build",
    ]

    for command in expected_commands:
        assert command in workflow


def test_tests_workflow_runs_local_release_validation_gates() -> None:
    assert_release_gates(read_workflow("tests.yml"))


def test_release_workflow_runs_validation_gates_and_changelog_notes() -> None:
    workflow = read_workflow("release.yml")

    assert 'bun-version: "1.3.11"' in workflow
    assert "bun install --frozen-lockfile" in workflow
    assert_release_gates(workflow)
    assert "docs/changelog/v$VERSION.md" in workflow
    assert "--notes-file" in workflow


def test_publish_workflow_rebuilds_static_assets_before_distribution() -> None:
    workflow = read_workflow("publish.yml")

    build_index = workflow.index("bun run web:build")
    diff_index = workflow.index("git diff --exit-code -- src/pbi_agent/web/static/app")
    distribution_index = workflow.index("python -m build")

    assert 'bun-version: "1.3.11"' in workflow
    assert "bun install --frozen-lockfile" in workflow
    assert build_index < diff_index < distribution_index


def test_docs_deploy_workflow_pins_bun_version() -> None:
    workflow = read_workflow("deploy-docs.yml")

    assert 'bun-version: "1.3.11"' in workflow
