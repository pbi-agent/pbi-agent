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
    assert "twine upload dist/*" in workflow
    assert 'gh release create "$TAG"' in workflow
    assert 'gh release edit "$TAG" --draft=false --latest' in workflow


def test_release_workflow_fails_when_changelog_notes_are_missing() -> None:
    workflow = read_workflow("release.yml")

    notes_file_index = workflow.index('NOTES_FILE="docs/changelog/v$VERSION.md"')
    missing_check_index = workflow.index('[ ! -f "$NOTES_FILE" ]')
    exit_index = workflow.index("exit 1", missing_check_index)
    upload_index = workflow.index("twine upload dist/*")
    create_index = workflow.index('gh release create "$TAG"')
    publish_index = workflow.index('gh release edit "$TAG" --draft=false --latest')
    notes_arg_index = workflow.index('--notes-file "$NOTES_FILE"')

    assert notes_file_index < missing_check_index < exit_index < create_index
    assert create_index < upload_index < publish_index
    assert create_index < notes_arg_index
    assert "Release for pbi-agent version $VERSION" not in workflow


def test_release_workflow_rejects_release_target_mismatch_before_publishing() -> None:
    workflow = read_workflow("release.yml")

    release_view_index = workflow.index(
        'gh release view "$TAG" --json targetCommitish --jq .targetCommitish'
    )
    mismatch_index = workflow.index(
        '[ -n "$release_target" ] && [ "$release_target" != "$GITHUB_SHA" ]'
    )
    exit_index = workflow.index("exit 1", mismatch_index)
    create_index = workflow.index('gh release create "$TAG"')
    upload_index = workflow.index("twine upload dist/*")
    publish_index = workflow.index('gh release edit "$TAG" --draft=false --latest')

    assert release_view_index < mismatch_index < exit_index < create_index
    assert create_index < upload_index < publish_index


def test_release_workflow_rejects_existing_tag_before_publishing() -> None:
    workflow = read_workflow("release.yml")

    tag_check_index = workflow.index('git ls-remote --tags origin "refs/tags/$TAG"')
    existing_tag_index = workflow.index('[ -n "$tag_ref" ] && [ -z "$release_target" ]')
    exit_index = workflow.index("exit 1", existing_tag_index)
    create_index = workflow.index('gh release create "$TAG"')
    upload_index = workflow.index("twine upload dist/*")
    publish_index = workflow.index('gh release edit "$TAG" --draft=false --latest')

    assert tag_check_index < existing_tag_index < exit_index < create_index
    assert create_index < upload_index < publish_index
    assert "without a matching GitHub release" in workflow


def test_release_workflow_rejects_existing_pypi_without_matching_draft() -> None:
    workflow = read_workflow("release.yml")

    pypi_check_index = workflow.index("https://pypi.org/pypi/{}/{}/json")
    pypi_collision_index = workflow.index("without a matching draft release")
    create_index = workflow.index('gh release create "$TAG"')
    upload_index = workflow.index("twine upload dist/*")
    publish_index = workflow.index('gh release edit "$TAG" --draft=false --latest')

    assert "urllib.request" in workflow
    assert pypi_check_index < pypi_collision_index < create_index
    assert create_index < upload_index < publish_index


def test_release_workflow_skips_when_package_version_did_not_change() -> None:
    workflow = read_workflow("release.yml")

    fetch_depth_index = workflow.index("fetch-depth: 0")
    before_index = workflow.index("BEFORE_SHA: ${{ github.event.before }}")
    previous_version_index = workflow.index("previous_version = tomllib.loads")
    should_release_index = workflow.index(
        "should_release = previous_version != version"
    )
    skip_index = workflow.index("Package version did not change; skipping release.")
    guard_index = workflow.index(
        "if: ${{ steps.version.outputs.should_release == 'true' }}"
    )
    upload_index = workflow.index("twine upload dist/*")
    publish_index = workflow.index('gh release edit "$TAG" --draft=false --latest')

    assert fetch_depth_index < before_index < previous_version_index
    assert previous_version_index < should_release_index < skip_index
    assert skip_index < guard_index < upload_index < publish_index


def test_release_workflow_rebuilds_static_assets_before_distribution() -> None:
    workflow = read_workflow("release.yml")

    build_index = workflow.index("bun run web:build")
    diff_index = workflow.index("git diff --exit-code -- src/pbi_agent/web/static/app")
    distribution_index = workflow.index("python -m build")

    assert 'bun-version: "1.3.11"' in workflow
    assert "bun install --frozen-lockfile" in workflow
    assert build_index < diff_index < distribution_index


def test_release_workflow_creates_draft_before_pypi_then_publishes_release() -> None:
    workflow = read_workflow("release.yml")

    build_index = workflow.index("python -m build")
    create_index = workflow.index('gh release create "$TAG"')
    upload_index = workflow.index("twine upload dist/*")
    publish_index = workflow.index('gh release edit "$TAG" --draft=false --latest')

    assert build_index < create_index < upload_index < publish_index


def test_release_workflow_reuses_draft_for_partial_release_recovery() -> None:
    workflow = read_workflow("release.yml")

    draft_check_index = workflow.index(
        'gh release view "$TAG" --json isDraft --jq .isDraft'
    )
    reuse_index = workflow.index("Reusing draft release $TAG for $GITHUB_SHA.")
    pypi_recovery_index = workflow.index(
        'echo "PyPI version $VERSION already exists; publishing existing draft release."'
    )
    skip_upload_index = workflow.index(
        'echo "upload_pypi=false" >> "$GITHUB_OUTPUT"', pypi_recovery_index
    )
    upload_guard_index = workflow.index(
        "steps.draft_release.outputs.upload_pypi == 'true'"
    )
    publish_guard_index = workflow.index(
        "steps.draft_release.outputs.publish_release == 'true'"
    )
    publish_index = workflow.index('gh release edit "$TAG" --draft=false --latest')

    assert draft_check_index < reuse_index < pypi_recovery_index < skip_upload_index
    assert skip_upload_index < upload_guard_index < publish_guard_index < publish_index


def test_release_workflow_does_not_skip_existing_pypi_artifacts() -> None:
    workflow = read_workflow("release.yml")

    upload_index = workflow.index("twine upload dist/*")
    assert "--skip-existing" not in workflow
    assert workflow.index("python -m build") < upload_index


def test_publish_workflow_is_not_a_downstream_release_side_effect() -> None:
    assert not (WORKFLOWS / "publish.yml").exists()


def test_docs_deploy_workflow_pins_bun_version() -> None:
    workflow = read_workflow("deploy-docs.yml")

    assert 'bun-version: "1.3.11"' in workflow
