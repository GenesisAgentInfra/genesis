"""Project static associations into the existing acceptance-tests report section."""

from genesis_contracts.models import Finding

from ..rules import identity


def test_findings(entries):
    result = []
    eligible = [
        entry
        for entry in entries
        if entry.side.value == "head" and entry.definition.association.targets
    ]
    for entry in eligible[:50]:
        definition = entry.definition
        assertions = len(definition.assertions)
        result.append(
            Finding(
                finding_id=identity("static_test_context", definition.test_id),
                category="acceptance_tests",
                severity="info",
                basis=("code_fact",),
                statement=f"{definition.symbol_id}: static association to {list(definition.association.targets)}; {assertions} recognized assertion expressions, {len(entry.fixture_candidates)} fixture candidates, {len(entry.mock_uses)} patch configurations.",
                evidence_ids=definition.evidence_ids,
                condition="Calls, fixture setup and mock configuration are distinct candidate relationships; no tests were run and business acceptance coverage is not proven.",
                gap="No supported assert, mock assertion or pytest.raises context was found in this test body."
                if not assertions
                else "; ".join(entry.limitations) or None,
            )
        )
    if len(eligible) > 50:
        last = result[-1]
        result[-1] = last.model_copy(
            update={
                "gap": ((last.gap + " ") if last.gap else "")
                + f"Report shows 50 of {len(eligible)} associated tests; tests.json retains the complete static index."
            }
        )
    return tuple(result)


test_findings.__test__ = False
