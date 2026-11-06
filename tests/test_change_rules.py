import pytest
from genesis_contracts.validation import validate_public_response
from test_estimates import PREFIX, source
from test_flow_candidates import run_changes


def findings(result, prefix):
    return [f for f in result.report.findings if f.finding_id.startswith(prefix)]


def test_deleted_sdk_site_has_base_evidence_and_no_savings_claim(source_repo):
    result, _ = run_changes(source_repo, {"app.py": source()}, {"app.py": "def main(): return 1\n"})
    found = findings(result, "sdk_sites_removed")
    assert len(found) == 1 and "savings" in found[0].gap
    assert all(
        r.side == "base" for r in result.local.evidence if r.evidence_id in found[0].evidence_ids
    )


def test_parse_failure_is_not_model_deletion(source_repo):
    result, _ = run_changes(source_repo, {"app.py": source()}, {"app.py": "def invalid(:\n"})
    assert not findings(result, "sdk_sites_removed")


@pytest.mark.parametrize("before,after", [("1", "2"), ("0", "3")])
def test_explicit_retry_count_change_is_structural(source_repo, before, after):
    text = source().replace("OpenAI()", "OpenAI(max_retries=" + before + ")")
    result, _ = run_changes(
        source_repo,
        {"app.py": text},
        {"app.py": text.replace("max_retries=" + before, "max_retries=" + after)},
    )
    assert len(findings(result, "explicit_retry_limit_changed")) == 1
    assert all(e.amount is None for e in result.local.estimates)


@pytest.mark.parametrize("retry", ["dynamic()", "True", "-1"])
def test_dynamic_retry_settings_do_not_get_numeric_claims(source_repo, retry):
    result, _ = run_changes(
        source_repo,
        {"app.py": source().replace("OpenAI()", "OpenAI(max_retries=1)")},
        {"app.py": source().replace("OpenAI()", "OpenAI(max_retries=" + retry + ")")},
    )
    assert not findings(result, "explicit_retry_limit_changed")


def test_model_literal_configuration_is_compared_but_cap_not_usage(source_repo):
    text = source().replace(
        'input="hello world"', 'input="hello world", max_output_tokens=100, temperature=0.1'
    )
    result, _ = run_changes(
        source_repo,
        {"app.py": text},
        {
            "app.py": text.replace("tokens=100", "tokens=200").replace(
                "temperature=0.1", "temperature=0.5"
            )
        },
    )
    found = findings(result, "model_parameter_changed")
    assert len(found) == 2 and all("not output token use" in f.gap for f in found)
    assert all(e.amount is None for e in result.local.estimates)


def test_if_else_polarity_change_at_model_call_is_not_lost(source_repo):
    before = (
        PREFIX
        + 'def main(approved):\n    if approved:\n        return client.responses.create(model="gpt-4.1",input="hi")\n    else:\n        return None\n'
    )
    after = (
        PREFIX
        + 'def main(approved):\n    if approved:\n        return None\n    else:\n        return client.responses.create(model="gpt-4.1",input="hi")\n'
    )
    result, _ = run_changes(source_repo, {"app.py": before}, {"app.py": after})
    assert findings(result, "model_call_conditions_changed")
    assert all(f.deviation is None for f in result.report.findings)
    validate_public_response(result.report)


def test_conditional_check_removal_has_both_sides_and_no_invented_intent(source_repo):
    before = "def submit(approved):\n    if not approved:\n        return False\n    return True\n"
    result, _ = run_changes(
        source_repo, {"app.py": before}, {"app.py": "def submit(approved): return True\n"}
    )
    found = findings(result, "condition_checks_changed")
    assert len(found) == 1 and found[0].deviation is None
    assert {r.side for r in result.local.evidence if r.evidence_id in found[0].evidence_ids} == {
        "base",
        "head",
    }


@pytest.mark.parametrize(
    "handler", ["except Exception: pass", "except: ...", "except* ValueError: pass"]
)
def test_pass_handler_is_explicit_and_does_not_claim_all_errors_swallowed(source_repo, handler):
    text = "def main():\n    try:\n        work()\n    " + handler + "\n"
    result, _ = run_changes(source_repo, {"app.py": "def main(): work()\n"}, {"app.py": text})
    assert findings(result, "exception_pass_handler")
    assert findings(result, "exception_handlers_changed")
    assert len(result.extraction.analysis.exception_handlers) == 1
    assert "may still propagate" in findings(result, "exception_pass_handler")[0].gap


@pytest.mark.parametrize("body", ["raise", "return 1", "log_error()", "if ok:\n            raise"])
def test_nontrivial_handler_not_misclassified_as_pass(source_repo, body):
    text = "def main():\n    try:\n        work()\n    except Exception:\n        " + body + "\n"
    result, _ = run_changes(source_repo, {"app.py": "def main(): work()\n"}, {"app.py": text})
    assert not findings(result, "exception_pass_handler")


def test_nested_handler_belongs_to_nested_function(source_repo):
    before = "def outer():\n    def inner():\n        try: work()\n        except Exception: raise\n    return inner\n"
    result, _ = run_changes(
        source_repo,
        {"app.py": before},
        {"app.py": before.replace("Exception: raise", "Exception: pass")},
    )
    h = next(h for h in result.extraction.analysis.exception_handlers if h.side == "head")
    assert h.symbol_id == "app.py#outer.inner"
    assert findings(result, "exception_pass_handler")[0].statement.startswith("app.py#outer.inner")


@pytest.mark.parametrize("test_body,expected", [("main()", True), ("assert main() == 2", False)])
def test_association_and_assertion_absence_are_distinct(source_repo, test_body, expected):
    result, _ = run_changes(
        source_repo,
        {
            "app.py": "def main(): return 1\n",
            "tests/test_main.py": "from app import main\ndef test_main(): " + test_body + "\n",
        },
        {"app.py": "def main(): return 2\n"},
    )
    assert bool(findings(result, "changed_test_assertions_unknown")) == expected


def test_comment_only_condition_does_not_create_guard_change(source_repo):
    text = "def main(ok):\n    if ok: return 1\n    return 2\n"
    result, _ = run_changes(
        source_repo,
        {"app.py": text},
        {"app.py": text.replace("    if ok:", "    # comment\n    if ok:")},
    )
    assert not findings(result, "condition_checks_changed")
    assert not findings(result, "exception_handlers_changed")


def test_same_length_prompt_change_is_visible(source_repo):
    result, _ = run_changes(
        source_repo, {"app.py": source(prompt='"allow"')}, {"app.py": source(prompt='"block"')}
    )
    assert findings(result, "prompt_content_changed")
    assert not findings(result, "prompt_literal_changed")


def test_missing_base_parse_is_not_new_sdk_site(source_repo):
    result, _ = run_changes(source_repo, {"app.py": "def invalid(:\n"}, {"app.py": source()})
    assert not findings(result, "sdk_sites_added")


def test_branch_guard_metadata_does_not_crash_model_comparison(source_repo):
    text = (
        PREFIX
        + 'def main(action):\n    if action == "yes":\n        return client.responses.create(model="gpt-4.1",input="hi")\n'
    )
    result, _ = run_changes(
        source_repo, {"app.py": text}, {"app.py": text.replace('"yes"', '"no"')}
    )
    assert findings(result, "model_call_conditions_changed")


@pytest.mark.parametrize(
    "body,expected",
    [
        ("await notify()", True),
        ("await asyncio.gather(notify(),notify())", False),
        ("if enabled:\n        await notify()", False),
    ],
)
def test_nonmodel_await_respects_branches_and_gather(source_repo, body, expected):
    before = "import asyncio\nasync def notify(): pass\nasync def run(enabled): pass\n"
    after = "import asyncio\nasync def notify(): pass\nasync def run(enabled):\n    " + body + "\n"
    result, _ = run_changes(source_repo, {"app.py": before}, {"app.py": after})
    assert bool(findings(result, "direct_nonmodel_await_sites_added")) == expected


@pytest.mark.parametrize(
    "body,expected",
    [
        ("await notify()", True),
        ("await asyncio.gather(notify(), notify())", False),
        ("if enabled:\n        await notify()", False),
        ("for _ in range(2):\n        await notify()", False),
    ],
)
def test_new_file_nonmodel_await_uses_known_zero_base_with_existing_scope_limits(
    source_repo, body, expected
):
    added = "import asyncio\nasync def notify(): pass\nasync def run(enabled):\n    " + body + "\n"
    result, _ = run_changes(
        source_repo, {"app.py": "def main(): return True\n"}, {"notifications.py": added}
    )
    change = next(
        item for item in result.local.change_set.files if item.head_path == "notifications.py"
    )
    assert change.change_type == "added" and change.base_path is None
    found = findings(result, "direct_nonmodel_await_sites_added")
    assert bool(found) == expected
    if expected:
        assert len(found) == 1
        assert "notifications.py#run" in found[0].statement
        assert "increase from 0 to 1" in found[0].statement
        refs = {ref.evidence_id: ref for ref in result.local.evidence}
        assert all(
            refs[identifier].side == "head" and refs[identifier].path == "notifications.py"
            for identifier in found[0].evidence_ids
        )
        assert "no latency or invocation count" in found[0].gap
        validate_public_response(result.report)


@pytest.mark.parametrize("unavailable", ["invalid_base", "oversized_base", "invalid_head"])
def test_unavailable_parse_is_not_a_known_zero_base_for_nonmodel_await(source_repo, unavailable):
    from genesis_contracts.python import PythonOptions

    before = "async def notify(): pass\nasync def run(): pass\n"
    after = "async def notify(): pass\nasync def run():\n    await notify()\n"
    options = None
    if unavailable == "invalid_base":
        before = "def invalid(:\n"
    elif unavailable == "oversized_base":
        before = "# " + "x" * 200 + "\n" + before
        options = PythonOptions(max_file_bytes=100)
    else:
        after = "def invalid(:\n"
    result, _ = run_changes(source_repo, {"app.py": before}, {"app.py": after}, options)
    assert result.local.change_set.files[0].change_type == "modified"
    assert not findings(result, "direct_nonmodel_await_sites_added")
