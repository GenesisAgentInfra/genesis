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


# The language each source suffix the agent engine reads belongs to, as the guides name it.
LANGUAGE_OF_SUFFIX = {
    "c": "C",
    "h": "C",
    "cc": "C++",
    "cpp": "C++",
    "hpp": "C++",
    "cs": "C#",
    "clj": "Clojure",
    "dart": "Dart",
    "ex": "Elixir",
    "exs": "Elixir",
    "erl": "Erlang",
    "go": "Go",
    "java": "Java",
    "js": "JavaScript",
    "jsx": "JavaScript",
    "mjs": "JavaScript",
    "cjs": "JavaScript",
    "jl": "Julia",
    "kt": "Kotlin",
    "kts": "Kotlin",
    "lua": "Lua",
    "m": "Objective-C",
    "mm": "Objective-C",
    "pl": "Perl",
    "php": "PHP",
    "py": "Python",
    "r": "R",
    "rb": "Ruby",
    "rs": "Rust",
    "scala": "Scala",
    "sh": "shell",
    "sql": "SQL",
    "svelte": "Svelte",
    "swift": "Swift",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "vue": "Vue",
}


@pytest.mark.parametrize("name", ["docs/usage.md", "docs/usage.zh-CN.md"])
def test_usage_guide_lists_the_languages_the_cli_reads(name):
    from genesis_ci.agent_map.session import SOURCE_SUFFIXES

    assert set(LANGUAGE_OF_SUFFIX) == SOURCE_SUFFIXES
    [paragraph] = [part for part in read(name).split("\n\n") if "Objective-C" in part]
    for language in set(LANGUAGE_OF_SUFFIX.values()):
        whole_word = rf"(?<![\w+#-]){re.escape(language)}(?![\w+#-])"
        assert re.search(whole_word, paragraph, flags=re.ASCII), language


SKILL = "packages/genesis_ci/src/genesis_ci/assets/skills/genesis/SKILL.md"


@pytest.mark.parametrize("name", ["docs/usage.md", "docs/usage.zh-CN.md", SKILL])
def test_a_review_map_is_not_said_to_hold_only_the_flows_the_changes_reach(name):
    # Rendered before the review has a plan, its map holds every flow found from the
    # code; with a plan, the flows planned. Either way it is no map of the whole project.
    text = " ".join(read(name).split())
    for claim in (
        "only the flows the changes reach",
        "has only the flows the review planned",
        "地图里只有改动走到的流程",
    ):
        assert claim not in text
    assert "map of the whole project" in text or "整个项目的地图" in text


@pytest.mark.parametrize("name", ["docs/usage.md", "docs/usage.zh-CN.md"])
def test_the_guides_say_where_a_risk_on_files_not_analyzed_is_shown(name):
    # The page shows a risk on the changes it names. One that names only changed files
    # Genesis did not analyze is not on it (viewer/tests/presentation.test.mjs).
    [told] = [item for item in read(name).split("\n- ") if "Dockerfile" in item]
    assert "summary.md" in told and "graph.html" in told
