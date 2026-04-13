import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION, CommandStart
from aiogram.types import ChatMemberUpdated, Message, ReplyKeyboardRemove
from sqlalchemy import select, update
from database import AsyncSessionLocal, Chat, Stats, Settings, MemberAction, init_db
from dotenv import load_dotenv
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
API_URL = "http://localhost:8000/api/notify"

async def notify_dashboard(chat_id, members_count, posts_count):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                API_URL,
                headers={"x-token": ADMIN_TOKEN},
                json={
                    "type": "stats_update",
                    "chat_id": chat_id,
                    "members": members_count,
                    "posts": posts_count
                }
            )
    except Exception as e:
        logging.error(f"Failed to notify dashboard: {e}")

async def get_or_create_chat(session, chat_tg_id, title, username, chat_type):
    result = await session.execute(select(Chat).where(Chat.tg_id == chat_tg_id))
    chat = result.scalar_one_or_none()
    
    if not chat:
        chat = Chat(tg_id=chat_tg_id, title=title, username=username, type=chat_type)
        session.add(chat)
        await session.flush()
        
        settings = Settings(chat_id=chat.id, cleanup_enabled=False)
        session.add(settings)
        
        # Immediate stats population
        count = 0
        try:
            count = await bot.get_chat_member_count(chat_tg_id)
        except Exception:
            pass
            
        stats = Stats(chat_id=chat.id, date=datetime.utcnow().date(), members_count=count)
        session.add(stats)
        await session.flush()
        
        await notify_dashboard(chat.id, count, 0)
        
    return chat

@dp.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated):
    async with AsyncSessionLocal() as session:
        chat_type = "channel" if update.chat.type == "channel" else "group"
        await get_or_create_chat(session, update.chat.id, update.chat.title, update.chat.username, chat_type)
        await session.commit()
    logging.info(f"Bot status updated in {update.chat.title} ({update.chat.type})")

@dp.message(CommandStart())
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        chat_type = "channel" if message.chat.type == "channel" else "group"
        if message.chat.type == "private":
            await message.answer(
                "👋 Salom! Men TeleStats botiman.\n\n"
                "Meni kanal yoki guruhingizga admin qilib qo'shing, "
                "shunda men statistikani yig'ishni boshlayman.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
            
        await get_or_create_chat(session, message.chat.id, message.chat.title, message.chat.username, chat_type)
        await session.commit()
        await message.answer(f"✅ {message.chat.title} muvaffaqiyatli ro'yxatga olindi! Endi statistikani web dashboardda ko'rishingiz mumkin.")

@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(update: ChatMemberUpdated):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Chat).where(Chat.tg_id == update.chat.id))
        chat = result.scalar_one_or_none()
        if chat:
            action = MemberAction(
                chat_id=chat.id,
                user_id=update.new_chat_member.user.id,
                added_by=update.from_user.id if update.from_user.id != update.new_chat_member.user.id else None,
                action_type="join"
            )
            session.add(action)
            
            # Update member count in today's stats
            stats_result = await session.execute(
                select(Stats).where(Stats.chat_id == chat.id, Stats.date == datetime.utcnow().date())
            )
            stats = stats_result.scalar_one_or_none()
            if stats:
                count = await bot.get_chat_member_count(update.chat.id)
                stats.members_count = count
            
            await session.commit()

@dp.message(F.content_type.in_({'new_chat_members', 'left_chat_member'}))
async def clean_service_messages(message: Message):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Settings).join(Chat).where(Chat.tg_id == message.chat.id)
        )
        settings = result.scalar_one_or_none()
        if settings and settings.cleanup_enabled:
            try:
                await message.delete()
            except Exception:
                pass

@dp.message()
async def track_posts_and_stats(message: Message):
    # Register chat if not exists (for existing chats)
    async with AsyncSessionLocal() as session:
        chat_type = "channel" if message.chat.type == "channel" else "group"
        if message.chat.type != "private":
            chat = await get_or_create_chat(session, message.chat.id, message.chat.title, message.chat.username, chat_type)
            
            if message.chat.type == "channel":
                stats_result = await session.execute(
                    select(Stats).where(Stats.chat_id == chat.id, Stats.date == datetime.utcnow().date())
                )
                stats = stats_result.scalar_one_or_none()
                if not stats:
                    stats = Stats(chat_id=chat.id, date=datetime.utcnow().date())
                    session.add(stats)
                
                stats.posts_count += 1
                await session.commit()

async def stats_pusher():
    while True:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Chat))
                chats = result.scalars().all()
                for chat in chats:
                    try:
                        count = await bot.get_chat_member_count(chat.tg_id)
                        stats_result = await session.execute(
                            select(Stats).where(Stats.chat_id == chat.id, Stats.date == datetime.utcnow().date())
                        )
                        stats = stats_result.scalar_one_or_none()
                        if not stats:
                            stats = Stats(chat_id=chat.id, date=datetime.utcnow().date(), members_count=count)
                            session.add(stats)
                        else:
                            stats.members_count = count
                        
                        await session.commit()
                        await notify_dashboard(chat.id, count, stats.posts_count if stats else 0)
                    except Exception as e:
                        logging.error(f"Error updating stats for {chat.title}: {e}")
                        continue
                logging.info("Stats updated and broadcasted for all chats.")
        except Exception as e:
            logging.error(f"Stats pusher error: {e}")
        await asyncio.sleep(60)  # For real-time feeling, check more often for now

async def start_bot():
    await init_db()
    asyncio.create_task(stats_pusher())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_bot())
