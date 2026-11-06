"""Public onboarding uses the real client pipeline with only mocked HTTP."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from genesis_ci import config
from genesis_ci.cli import app
from genesis_ci.client import SemanticClient
from genesis_ci.public_trial import OFFICIAL_SERVICE_URL, public_trial_key
from genesis_contracts.models import AnalysisResponse, SectionStatuses
from test_git_snapshot import commit, write
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for name in ("GENESIS_API_KEY", "GENESIS_SERVICE_URL", "GITHUB_EVENT_NAME", "CI"):
        monkeypatch.delenv(name, raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("Tests must not access live trial or model services")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)


@pytest.fixture
def change(source_repo):
    write(source_repo, "app.py", "def run():\n    return 1\n")
    base = commit(source_repo)
    write(source_repo, "app.py", "def run():\n    return 2\n")
    return source_repo, base


def invoke_analysis(change, tmp_path, *extra, answer=""):
    repo, base = change
    output = tmp_path / "analysis"
    result = CliRunner().invoke(
        app,
        ["analyze", "--repo", str(repo), "--base", base, "--output", str(output), *extra],
        input=answer,
    )
    assert result.exit_code in {0, 2}, result.output
    report = AnalysisResponse.model_validate_json((output / "report.json").read_bytes())
    return result, report, output


def mock_service(monkeypatch, *, status=200):
    sent = []

    def endpoint(request):
        sent.append(request)
        if request.url.path == "/capabilities":
            assert "Authorization" not in request.headers
            return httpx.Response(200, json={})
        if status != 200:
            return httpx.Response(status, json={"message": "untrusted remote detail"})
        body = json.loads(request.content)
        if request.url.path == "/v1/flows/draft":
            response = {
                "request_id": body["request_id"],
                "snapshot_id": body["snapshot_id"],
                "flows": [
                    {
                        "id": "app-run",
                        "name": "Run the application",
                        "description": "Synthetic reviewed entry draft.",
                        "entries": [body["candidate_entries"][0]],
                    }
                ],
            }
        else:
            assert request.url.path == "/v1/analyze"
            response = {
                "request_id": body["request_id"],
                "snapshot_id": body["snapshot_id"],
                "semantic_version": "synthetic-test",
                "section_status": {
                    name: {"status": "analyzed"} for name in SectionStatuses.model_fields
                },
            }
        return httpx.Response(200, json=response)

    monkeypatch.setattr(
        "genesis_ci.client.SemanticClient",
        lambda url, key: SemanticClient(url, key, transport=httpx.MockTransport(endpoint)),
    )
    return sent


def test_clean_install_uses_bundled_trial_without_saving_credentials():
    connection = config.resolve_service_connection(None)
    assert connection.public_trial
    assert connection.service_url == OFFICIAL_SERVICE_URL
    assert connection.api_key == public_trial_key()
    assert connection.api_key not in repr(connection)
    assert not config.credentials_path().exists()


@pytest.mark.parametrize("setting", ["flag", "env"])
@pytest.mark.parametrize("origin", [OFFICIAL_SERVICE_URL, "https://custom.example.test"])
def test_explicit_url_without_key_never_selects_trial(monkeypatch, origin, setting):
    if setting == "env":
        monkeypatch.setenv("GENESIS_SERVICE_URL", origin)
    connection = config.resolve_service_connection(origin if setting == "flag" else None)
    assert connection.service_url == origin
    assert connection.api_key is None
    assert not connection.public_trial


def test_personal_precedence_and_origin_binding(monkeypatch):
    config.save_credentials("personal-saved-key", "https://saved.example.test")
    original = config.credentials_path().read_bytes()
    assert config.resolve_connection(None) == ("https://saved.example.test", "personal-saved-key")
    monkeypatch.setenv("GENESIS_API_KEY", "personal-env-key")
    assert config.resolve_connection(None) == ("https://saved.example.test", "personal-env-key")
    monkeypatch.setenv("GENESIS_SERVICE_URL", "https://env.example.test")
    assert config.resolve_connection(None) == ("https://env.example.test", "personal-env-key")
    assert config.resolve_connection("https://flag.example.test") == (
        "https://flag.example.test",
        "personal-env-key",
    )
    monkeypatch.delenv("GENESIS_API_KEY")
    assert config.resolve_connection(None) == ("https://env.example.test", None)
    assert not config.resolve_service_connection(None).public_trial
    assert config.credentials_path().read_bytes() == original


def test_environment_key_without_url_uses_official_service_as_personal(monkeypatch):
    monkeypatch.setenv("GENESIS_API_KEY", "personal-env-key")
    connection = config.resolve_service_connection(None)
    assert connection.service_url == OFFICIAL_SERVICE_URL
    assert connection.api_key == "personal-env-key"
    assert not connection.public_trial


@pytest.mark.parametrize("link_parent", [False, True])
def test_dangling_credential_symlinks_do_not_enable_trial(tmp_path, link_parent):
    path = config.credentials_path()
    link = path.parent if link_parent else path
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "missing-target", target_is_directory=link_parent)
    with pytest.raises(ValueError, match="symbolic link"):
        config.resolve_service_connection(None)


@pytest.mark.parametrize("name", ["GENESIS_API_KEY", "GENESIS_SERVICE_URL"])
@pytest.mark.parametrize("value", ["", " ", "invalid\nvalue"])
def test_invalid_environment_settings_never_enable_trial(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        config.resolve_service_connection(None)


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        "{}",
        '{"api_key": "personal-key"}',
        '{"service_url": "https://custom.example.test"}',
        '{"service_url": "https://custom.example.test", "api_key": ""}',
    ],
)
def test_invalid_saved_configuration_never_enables_trial(monkeypatch, contents):
    path = config.credentials_path()
    path.parent.mkdir(parents=True)
    path.write_text(contents)
    path.chmod(0o600)
    with pytest.raises(ValueError):
        config.resolve_service_connection(None)
    monkeypatch.setenv("GENESIS_API_KEY", "explicit-key")
    assert config.resolve_connection("https://custom.example.test") == (
        "https://custom.example.test",
        "explicit-key",
    )


@pytest.mark.parametrize("answer", ["n\n", ""])
def test_trial_decline_or_eof_makes_no_http(change, tmp_path, monkeypatch, answer):
    sent = mock_service(monkeypatch)
    result, report, _ = invoke_analysis(change, tmp_path, answer=answer)
    assert result.exit_code == 2
    assert "官方公共试用" in result.output
    assert any(item.code == "send_not_confirmed" for item in report.limitations)
    assert sent == []


@pytest.mark.parametrize("flag", ["--offline", "--preview-only"])
def test_trial_local_modes_make_no_http(change, tmp_path, monkeypatch, flag):
    sent = mock_service(monkeypatch)
    if flag == "--offline":
        monkeypatch.setattr(
            config,
            "resolve_service_connection",
            lambda _: pytest.fail("Offline must not read credentials"),
        )
    result, report, _ = invoke_analysis(change, tmp_path, flag, "--accept-send")
    assert result.exit_code == 2
    assert report.scope.execution_mode == "offline"
    assert sent == []


def test_fork_guard_precedes_trial_resolution(change, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "missing-event.json"))
    monkeypatch.setattr(
        config,
        "resolve_service_connection",
        lambda _: pytest.fail("Fork must not read credentials"),
    )
    sent = mock_service(monkeypatch)
    _, report, _ = invoke_analysis(change, tmp_path, "--accept-send")
    assert any(item.code == "fork_pr_offline" for item in report.limitations)
    assert sent == []


@pytest.mark.parametrize("approve_by_flag", [False, True])
def test_trial_analysis_uses_same_wire_pipeline_and_keeps_key_out_of_artifacts(
    change, tmp_path, monkeypatch, approve_by_flag
):
    sent = mock_service(monkeypatch)
    flags = ["--accept-send"] if approve_by_flag else []
    result, report, output = invoke_analysis(change, tmp_path, *flags, answer="y\n")
    assert report.scope.execution_mode == "semantic"
    assert [request.url.path for request in sent] == ["/capabilities", "/v1/analyze"]
    assert all(str(request.url).startswith(OFFICIAL_SERVICE_URL + "/") for request in sent)
    key = public_trial_key()
    assert sent[1].headers["Authorization"] == "Bearer " + key
    payload = json.loads(sent[1].content)
    assert payload["facts"] and payload["evidence"] and payload["excerpts"]
    assert not payload["intents"] and not payload["flows"]
    assert key not in result.output
    assert not config.credentials_path().exists()
    for path in output.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes(), str(path)


@pytest.mark.parametrize(
    ("status", "code", "message"),
    [
        (401, "invalid_api_key", "公共试用凭证已失效"),
        (402, "quota_exceeded", "公共试用共享额度已用完"),
        (503, "service_unavailable", "公共试用暂时无法完成分析"),
        (504, "analysis_timeout", "公共试用分析超时"),
    ],
)
def test_trial_failure_explains_recovery_without_retry(
    change, tmp_path, monkeypatch, status, code, message
):
    sent = mock_service(monkeypatch, status=status)
    result, report, output = invoke_analysis(change, tmp_path, "--accept-send")
    assert result.exit_code == 2
    assert any(item.code == code and message in item.message for item in report.limitations)
    assert message in result.output
    assert message in (output / "report.md").read_text()
    assert message in (output / "summary.md").read_text()
    assert len(sent) == 2
    assert "untrusted remote detail" not in result.output


@pytest.mark.parametrize("status", [401, 402, 503])
def test_personal_failure_never_retries_with_trial(change, tmp_path, monkeypatch, status):
    config.save_credentials("personal-key", "https://custom.example.test")
    before = config.credentials_path().read_bytes()
    sent = mock_service(monkeypatch, status=status)
    result, _, _ = invoke_analysis(change, tmp_path, "--accept-send")
    assert result.exit_code == 2
    assert "公共试用" not in result.output
    assert len(sent) == 2
    assert all(request.url.host == "custom.example.test" for request in sent)
    assert sent[1].headers["Authorization"] == "Bearer personal-key"
    assert config.credentials_path().read_bytes() == before


def test_custom_origin_without_key_never_sends_trial(change, tmp_path, monkeypatch):
    sent = mock_service(monkeypatch)
    _, report, _ = invoke_analysis(
        change, tmp_path, "--service-url", "https://custom.example.test", "--accept-send"
    )
    assert any(item.code == "invalid_api_key" for item in report.limitations)
    assert sent == []


@pytest.mark.parametrize("answer", ["n\n", "y\n"])
def test_flow_drafting_uses_trial_only_after_consent(change, tmp_path, monkeypatch, answer):
    repo, _ = change
    sent = mock_service(monkeypatch)
    destination = tmp_path / "flows.draft.yaml"
    result = CliRunner().invoke(
        app, ["flows", "init", "--repo", str(repo), "--output", str(destination)], input=answer
    )
    assert result.exit_code == (0 if answer == "y\n" else 2), result.output
    assert len(sent) == (1 if answer == "y\n" else 0)
    if sent:
        assert str(sent[0].url) == OFFICIAL_SERVICE_URL + "/v1/flows/draft"
        assert sent[0].headers["Authorization"] == "Bearer " + public_trial_key()
    assert "官方公共试用" in result.output
    assert public_trial_key() not in destination.read_text() + result.output
    assert not config.credentials_path().exists()


def test_trial_draft_failure_preserves_static_draft(change, tmp_path, monkeypatch):
    repo, _ = change
    sent = mock_service(monkeypatch, status=402)
    destination = tmp_path / "flows.draft.yaml"
    result = CliRunner().invoke(
        app,
        ["flows", "init", "--repo", str(repo), "--output", str(destination), "--accept-send"],
    )
    assert result.exit_code == 2, result.output
    assert "公共试用共享额度已用完" in result.output
    assert "app.py#run" in destination.read_text()
    assert len(sent) == 1
    metadata = json.loads(destination.with_suffix(".metadata.json").read_text())
    assert metadata["mode"] == "offline"
    assert "公共试用共享额度已用完" in metadata["reason"]
    assert public_trial_key() not in json.dumps(metadata)


def test_secret_audit_exception_is_exact_and_asset_specific():
    spec = importlib.util.spec_from_file_location(
        "public_boundary_audit", ROOT / "scripts/check_public_boundary.py"
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    data = (ROOT / audit.PUBLIC_TRIAL_ASSET).read_bytes()
    assert not audit.has_unapproved_secret(audit.PUBLIC_TRIAL_ASSET, data)
    assert audit.has_unapproved_secret("some-other-file.json", data)
    assert audit.has_unapproved_secret(audit.PUBLIC_TRIAL_ASSET, data + b" ")
    unrelated = ("gci_" + "x" * 48).encode()
    assert audit.has_unapproved_secret(audit.PUBLIC_TRIAL_ASSET, unrelated)
    assert audit.has_unapproved_secret("other.py", unrelated)
