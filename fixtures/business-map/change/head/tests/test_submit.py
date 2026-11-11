import pytest

from expense.api import submit_report


@pytest.mark.parametrize("amount", [50, 500])
async def test_submit_report_status(amount):
    result = await submit_report({"id": "r1", "amount": amount})
    assert result["status"] in {"approved", "pending_approval"}
