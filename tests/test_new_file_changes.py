"""Files that exist on one side only: their module-level code is listed too."""

from test_change_analysis import by_kind, diff

VOICE = """import re

PATTERN = re.compile(r"\\d+")
LIMIT = 10


def count(text):
    return PATTERN.findall(text)[:LIMIT]


if __name__ == "__main__":
    print(count("1 2"))
"""
TEST = "from app.voice import count\n\n\ndef test_count():\n    assert count('1 2') == ['1', '2']\n"


def test_module_level_code_of_a_new_file_is_listed_by_assignment(source_repo):
    changes, report = diff(
        source_repo,
        {"app/core.py": "def run():\n    return 1\n"},
        {
            "app/core.py": "def run():\n    return 1\n",
            "app/voice.py": VOICE,
            "tests/test_voice.py": TEST,
        },
    )
    assert changes == [
        ("source_added", None, "import re"),
        ("source_added", None, 'PATTERN = re.compile(r"\\d+")'),
        ("source_added", None, "LIMIT = 10"),
        ("symbol_added", None, "def count(text):"),
        ("source_added", None, 'if __name__ == "__main__":\n    print(count("1 2"))'),
        ("test_added", None, "test test_count"),
    ]
    # Each constant reaches the code that reads it, and so the tests of that code.
    pattern = next(item for item in report.changes if "PATTERN =" in (item.after.text or ""))
    assert [case.test_id for case in pattern.tests.items] == [
        "head::tests/test_voice.py#test_count"
    ]


def test_module_level_code_of_a_deleted_file_is_listed_too(source_repo):
    legacy = "import math\n\nRATE = 3\n\n\ndef old(x):\n    return math.ceil(x * RATE)\n"
    changes, _ = diff(
        source_repo,
        {"app/core.py": "def run():\n    return 1\n", "app/legacy.py": legacy},
        {"app/core.py": "def run():\n    return 1\n"},
    )
    assert changes == [
        ("source_removed", "import math", None),
        ("source_removed", "RATE = 3", None),
        ("symbol_removed", "def old(x):", None),
    ]


def test_a_renamed_file_is_not_listed_as_new(source_repo):
    text = "LIMIT = 10\n\n\ndef run():\n    return LIMIT\n"
    changes, report = diff(source_repo, {"app/old_name.py": text}, {"app/new_name.py": text})
    assert [kind for kind, _, _ in changes] == ["symbol_moved"]
    assert by_kind(report, "symbol_moved").symbol_id == "app/new_name.py#<module>"
