from openai import AsyncOpenAI

client = AsyncOpenAI()


async def review_with_model(report):
    while True:
        response = await client.responses.create(model="gpt-5", input=str(report))
        if response.output_text:
            return response.output_text
