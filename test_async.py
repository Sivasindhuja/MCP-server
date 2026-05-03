import asyncio
import time
from APIWrapper import Obsidian

api = Obsidian(api_key="YOUR_API_KEY")


async def call_once():
    start = time.time()
    await api.search("project")
    end = time.time()
    return end - start


async def main():
    print("Running 10 concurrent requests...\n")

    start = time.time()

    tasks = [call_once() for _ in range(10)]
    results = await asyncio.gather(*tasks)

    end = time.time()

    print("Individual times:", [round(r, 3) for r in results])
    print("Total time:", round(end - start, 3))


if __name__ == "__main__":
    asyncio.run(main())