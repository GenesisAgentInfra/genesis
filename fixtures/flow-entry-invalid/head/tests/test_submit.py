async def test_submit_report():
    result = await submit_report({})
    assert result is not None
