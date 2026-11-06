async def submit_report(report):
    result = third_party.submit(report)
    callback = registry[name]
    await callback(result)
    return result
