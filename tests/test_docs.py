"""The user-facing documents name the paths and commands the CLI really has."""

import re
from pathlib import Path

import pytest
from genesis_ci.agent_setup import Agent, Scope, skill_destinations

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ("docs/install.md", "docs/usage.md")
TRANSLATED = ("README.md", *GUIDES)
DOCUMENTS = (
    "AGENTS.md",
    "README.md",
    "README.zh-CN.md",
    *GUIDES,
    *(name.replace(".md", ".zh-CN.md") for name in GUIDES),
)


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def shell_blocks(text: str) -> list[str]:
    return re.findall(r"```sh\n(.*?)```", text, flags=re.DOTALL)


@pytest.mark.parametrize("name", DOCUMENTS)
def test_local_links_lead_to_files(name):
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", read(name)):
        if target.startswith(("http://", "https://")):
            continue
        assert (ROOT / name).parent.joinpath(target).is_file(), f"{name} links to {target}"


@pytest.mark.parametrize("name", DOCUMENTS)
def test_result_page_is_named_where_render_writes_it(name):
    text = read(name)
    assert ".genesis/view.html" not in text
    if "view.html" in text and name not in ("docs/install.md", "docs/install.zh-CN.md"):
        assert ".genesis/out/latest/" in text


@pytest.mark.parametrize("name", TRANSLATED)
def test_translation_keeps_the_commands(name):
    assert shell_blocks(read(name.replace(".md", ".zh-CN.md"))) == shell_blocks(read(name))


@pytest.mark.parametrize("name", ["docs/install.md", "docs/install.zh-CN.md"])
def test_install_guide_names_the_directories_the_installer_writes(name, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    text = read(name)
    for agent in (Agent.claude, Agent.codex):
        [destination] = skill_destinations(agent, Scope.user, None)
        assert (
            f"| `--agent {agent.value}` | `~/{destination.relative_to(tmp_path.resolve())}` |"
            in text
        )
