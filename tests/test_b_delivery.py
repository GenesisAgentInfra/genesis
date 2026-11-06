import json
import shutil

from genesis_ci.cli import app
from genesis_ci.snapshot_store import save_snapshot
from test_pipeline import changed_snapshot
from typer.testing import CliRunner


def test_source_evidence_report_is_explicit_and_uses_only_frozen_bytes(source_repo, tmp_path):
    captured = changed_snapshot(source_repo)
    frozen = tmp_path / "snapshot"
    save_snapshot(captured, frozen)
    shutil.rmtree(source_repo)
    ordinary = tmp_path / "ordinary"
    normal = CliRunner().invoke(
        app, ["analyze", "--snapshot", str(frozen), "--offline", "--output", str(ordinary)]
    )
    assert normal.exit_code == 2, normal.output
    assert not (ordinary / "review-with-source.md").exists()
    private = tmp_path / "private"
    detailed = CliRunner().invoke(
        app,
        [
            "analyze",
            "--snapshot",
            str(frozen),
            "--offline",
            "--include-source-evidence",
            "--output",
            str(private),
        ],
    )
    assert detailed.exit_code == 2, detailed.output
    text = (private / "review-with-source.md").read_text()
    assert "client.responses.create" in text
    assert "old-model" in text and "new-model" in text
    assert (private / "review-with-source.md").stat().st_mode & 0o777 == 0o600
    assert json.loads((private / "report.json").read_text()) == json.loads(
        (ordinary / "report.json").read_text()
    )
