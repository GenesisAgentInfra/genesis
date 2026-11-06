async def submit_report(report):
    result = third_party.submit(report)
    await notify(result)
    return result
