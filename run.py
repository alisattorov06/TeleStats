import asyncio
import uvicorn

from api import app
from bot import start_bot


async def main():
    # Botni backgroundda ishga tushiramiz
    bot_task = asyncio.create_task(start_bot())

    # Uvicorn serverni async ishga tushirish
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=10000,
        log_level="info"
    )
    server = uvicorn.Server(config)

    api_task = asyncio.create_task(server.serve())

    # Ikkalasini parallel kutamiz
    await asyncio.gather(bot_task, api_task)


if __name__ == "__main__":
    asyncio.run(main())
