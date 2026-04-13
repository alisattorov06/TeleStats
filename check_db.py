import asyncio
from sqlalchemy import select
from database import AsyncSessionLocal, Chat, Stats

async def check():
    async with AsyncSessionLocal() as session:
        chats = await session.execute(select(Chat))
        print("--- CHATS ---")
        for c in chats.scalars():
            print(f"ID: {c.id}, TG_ID: {c.tg_id}, Title: {c.title}")
            
        stats = await session.execute(select(Stats))
        print("\n--- STATS ---")
        for s in stats.scalars():
            print(f"Chat ID: {s.chat_id}, Date: {s.date}, Members: {s.members_count}, Posts: {s.posts_count}")

if __name__ == "__main__":
    asyncio.run(check())
