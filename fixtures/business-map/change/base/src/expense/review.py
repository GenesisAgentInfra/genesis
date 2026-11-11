from openai import AsyncOpenAI

client = AsyncOpenAI()


async def review_with_model(report):
    response = await client.responses.create(model="gpt-5", input=str(report))
    return response.output_text
