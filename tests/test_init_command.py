from __future__ import annotations

from pathlib import Path

import pytest

from pbi_agent.init_command import init_report


def test_init_report_copies_bundled_template_into_destination(tmp_path: Path) -> None:
    dest = tmp_path / "new-report"

    returned = init_report(dest)

    assert returned == dest
    assert (dest / "template_report.pbip").is_file()
    assert (dest / "template_report.Report" / "definition.pbir").is_file()
    assert (
        dest / "template_report.SemanticModel" / "definition" / "model.tmdl"
    ).is_file()


def test_init_report_raises_when_destination_contains_template_without_force(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "existing-report"
    dest.mkdir()
    (dest / "template_report.pbip").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="File already exists"):
        init_report(dest, force=False)
