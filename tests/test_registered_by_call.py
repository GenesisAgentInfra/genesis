"""Entries registered by a call: a framework decorator called on a function, and argparse."""

from test_python_entries import entries

SERVER = """from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memory")
app = FastAPI()


def search(query):
    return query


def health():
    return "ok"


def helper():
    return 1


mcp.tool(name="memory_search")(search)
app.get("/health")(health)
print(helper)
"""
CLI = """import argparse


def cmd_voice(args):
    return "voice"


def cmd_setup(args):
    return "setup"


def cmd_default(args):
    return "default"


def build_parser():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=cmd_default)
    sub = parser.add_subparsers()
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    p = sub.add_parser("voice", help="Speak")
    p.add_argument("--pretty", action="store_true")
    p.set_defaults(func=cmd_voice)
    p = parser
    p.set_defaults(func=cmd_default)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)
"""


def test_a_framework_decorator_called_on_a_function_registers_it(source_repo):
    found, _ = entries(source_repo, {"app/__init__.py": "", "app/server.py": SERVER})
    search = found["app/server.py#search"]
    assert (search.kind, search.detection, search.framework) == ("agent_tool", "adapter", "mcp")
    health = found["app/server.py#health"]
    assert (health.kind, health.framework) == ("http_route", "fastapi")
    assert health.attributes == {"method": "GET", "path": "/health"}
    # Handing a function to any other call registers nothing.
    assert "app/server.py#helper" not in found or found["app/server.py#helper"].kind == "root"


def test_argparse_subcommands_are_cli_entries(source_repo):
    found, _ = entries(source_repo, {"cli/__init__.py": "", "cli/main.py": CLI})
    for name, command in (("cmd_voice", "voice"), ("cmd_setup", "setup")):
        entry = found[f"cli/main.py#{name}"]
        assert (entry.kind, entry.detection, entry.framework) == (
            "cli_command",
            "adapter",
            "argparse",
        )
        assert entry.attributes == {"command": command}
    # The parser's own default is no subcommand.
    assert "cli/main.py#cmd_default" not in found
