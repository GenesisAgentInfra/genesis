import json

from genesis_ci.cli import app
from genesis_contracts.models import AnalysisResponse
from test_git_snapshot import commit, write
from typer.testing import CliRunner


def test_auth_keeps_key_outside_repo_and_binds_it_to_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "user-config"))
    monkeypatch.delenv("GENESIS_API_KEY", raising=False)
    monkeypatch.delenv("GENESIS_SERVICE_URL", raising=False)
    result = CliRunner().invoke(
        app, ["auth", "--service-url", "https://ci.example.test"], input="test-only-key\n"
    )
    assert result.exit_code == 0, result.output
    assert "test-only-key" not in result.output
    from genesis_ci.config import credentials_path, resolve_connection

    assert credentials_path().stat().st_mode & 0o777 == 0o600
    assert resolve_connection(None) == ("https://ci.example.test", "test-only-key")
    assert resolve_connection("https://other.example.test") == ("https://other.example.test", None)


def test_one_command_freezes_worktree_and_keeps_local_report(source_repo, tmp_path):
    write(source_repo, "app.py", "def run():\n    return 1\n")
    base = commit(source_repo)
    write(source_repo, "app.py", "def run():\n    return 2\n")
    output = tmp_path / "analysis"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--repo",
            str(source_repo),
            "--base",
            base,
            "--offline",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2, result.output
    report = AnalysisResponse.model_validate_json((output / "report.json").read_bytes())
    assert report.scope.execution_mode == "offline"
    assert report.scope.head_revision.startswith("worktree:")
    assert report.scope.base_revision == base
    assert (output / "snapshot" / "snapshot.json").exists()
    assert json.loads((output / "complete.json").read_text())["analysis_status"] == "partial"


def test_online_analysis_requires_send_consent_and_keeps_local_report(
    source_repo, tmp_path, monkeypatch
):
    import httpx

    write(source_repo, "app.py", "def run():\n    return 1\n")
    base = commit(source_repo)
    write(source_repo, "app.py", "def run():\n    return 2\n")
    monkeypatch.setenv("GENESIS_API_KEY", "test-key")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        httpx.Client,
        "send",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("No consent: network forbidden")),
    )
    output = tmp_path / "analysis"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--repo",
            str(source_repo),
            "--base",
            base,
            "--service-url",
            "https://ci.example.test",
            "--output",
            str(output),
        ],
        input="n\n",
    )
    assert result.exit_code == 2, result.output
    report = AnalysisResponse.model_validate_json((output / "report.json").read_bytes())
    assert any(item.code == "send_not_confirmed" for item in report.limitations)
    assert (output / "send-preview.txt").exists()


def test_fork_pr_forces_offline_even_when_send_was_requested(source_repo, tmp_path, monkeypatch):
    write(source_repo, "app.py", "def run(): return 1\n")
    base = commit(source_repo)
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "head": {"repo": {"full_name": "outsider/project"}},
                    "base": {"repo": {"full_name": "owner/project"}},
                }
            }
        )
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GENESIS_API_KEY", "do-not-send")
    output = tmp_path / "analysis"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--repo",
            str(source_repo),
            "--base",
            base,
            "--service-url",
            "https://ci.example.test",
            "--accept-send",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2, result.output
    report = AnalysisResponse.model_validate_json((output / "report.json").read_bytes())
    assert any(item.code == "fork_pr_offline" for item in report.limitations)


def test_flows_init_produces_only_reviewable_drafts_without_overwriting_map(source_repo, tmp_path):
    import yaml
    from genesis_contracts.models import FlowsDocument

    write(source_repo, "app.py", "def helper(): return 1\ndef run(): return helper()\n")
    commit(source_repo)
    destination = tmp_path / "flows.draft.yaml"
    result = CliRunner().invoke(
        app,
        ["flows", "init", "--repo", str(source_repo), "--offline", "--output", str(destination)],
    )
    assert result.exit_code == 2, result.output
    draft = FlowsDocument.model_validate(yaml.safe_load(destination.read_text()))
    assert any("app.py#run" in flow.entries for flow in draft.flows)
    assert all(flow.status == "draft" and not flow.acceptance for flow in draft.flows)
    assert not (source_repo / ".genesis/flows.yaml").exists()
    before = destination.read_bytes()
    again = CliRunner().invoke(
        app,
        ["flows", "init", "--repo", str(source_repo), "--offline", "--output", str(destination)],
    )
    assert again.exit_code == 1
    assert destination.read_bytes() == before


def test_invalid_saved_credentials_preserve_report_and_explicit_override(
    source_repo, tmp_path, monkeypatch
):
    from genesis_ci.config import credentials_path, resolve_connection

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("GENESIS_API_KEY", raising=False)
    monkeypatch.delenv("GENESIS_SERVICE_URL", raising=False)
    path = credentials_path()
    path.parent.mkdir(parents=True)
    path.write_text("not json")
    path.chmod(0o600)
    write(source_repo, "app.py", "def run(): return 1\n")
    base = commit(source_repo)
    output = tmp_path / "report"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--repo",
            str(source_repo),
            "--base",
            base,
            "--service-url",
            "https://ci.example.test",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2, result.output
    report = AnalysisResponse.model_validate_json((output / "report.json").read_bytes())
    assert any(item.code == "invalid_api_key" for item in report.limitations)
    monkeypatch.setenv("GENESIS_API_KEY", "explicit-test-key")
    assert resolve_connection("https://ci.example.test") == (
        "https://ci.example.test",
        "explicit-test-key",
    )


def test_config_errors_do_not_print_customer_values(source_repo, tmp_path):
    sentinel = "SYNTHETIC_SECRET_MUST_NOT_LOG"
    write(source_repo, ".genesis/config.toml", f'api_key = "{sentinel}"\n')
    result = CliRunner().invoke(app, ["analyze", "--repo", str(source_repo), "--offline"])
    assert result.exit_code == 1
    assert sentinel not in result.output


def test_default_analysis_explains_missing_semantic_setup(source_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-config"))
    monkeypatch.delenv("GENESIS_API_KEY", raising=False)
    monkeypatch.delenv("GENESIS_SERVICE_URL", raising=False)
    write(source_repo, "app.py", "def run(): return 1\n")
    base = commit(source_repo)
    output = tmp_path / "unconfigured"
    result = CliRunner().invoke(
        app, ["analyze", "--repo", str(source_repo), "--base", base, "--output", str(output)]
    )
    assert result.exit_code == 2, result.output
    report = AnalysisResponse.model_validate_json((output / "report.json").read_bytes())
    assert any(
        "API key" in item.message and "genesis auth" in item.message for item in report.limitations
    )


def test_flow_draft_respects_configured_payload_budget(source_repo, tmp_path):
    write(source_repo, "app.py", "def run():\n" + "    # detail\n" * 100 + "    return 1\n")
    commit(source_repo)
    write(
        source_repo, ".genesis/config.toml", "input_token_budget = 100\nmax_excerpt_chars = 100\n"
    )
    output = tmp_path / "limited.yaml"
    result = CliRunner().invoke(
        app, ["flows", "init", "--repo", str(source_repo), "--offline", "--output", str(output)]
    )
    assert result.exit_code == 1, result.output
    assert not output.exists()


def test_empty_remote_draft_retains_static_entries_and_partial_exit(
    source_repo, tmp_path, monkeypatch
):
    import httpx
    import yaml
    from genesis_ci.client import SemanticClient

    write(source_repo, "app.py", "def submit_report():\n    return True\n")
    commit(source_repo)
    monkeypatch.setenv("GENESIS_API_KEY", "synthetic-key")
    monkeypatch.setenv("GENESIS_SERVICE_URL", "https://ci.example.test")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "")
    sent = []

    def endpoint(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(
            200,
            json={
                "request_id": body["request_id"],
                "snapshot_id": body["snapshot_id"],
                "flows": [],
            },
        )

    monkeypatch.setattr(
        "genesis_ci.client.SemanticClient",
        lambda url, key: SemanticClient(
            url,
            key,
            transport=httpx.MockTransport(endpoint),
        ),
    )
    destination = tmp_path / "draft.yaml"
    result = CliRunner().invoke(
        app,
        [
            "flows",
            "init",
            "--repo",
            str(source_repo),
            "--output",
            str(destination),
            "--accept-send",
        ],
    )
    assert result.exit_code == 2, result.output
    assert len(sent) == 1
    document = yaml.safe_load(destination.read_text())
    assert {entry for flow in document["flows"] for entry in flow["entries"]} == {
        "app.py#submit_report"
    }
    assert all(flow["status"] == "draft" and not flow["acceptance"] for flow in document["flows"])
    metadata = json.loads(destination.with_suffix(".metadata.json").read_text())
    assert metadata["mode"] == "offline"
    assert "provider_output_invalid" in metadata["reason"]
