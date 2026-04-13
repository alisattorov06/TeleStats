import os
from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, Date, Float
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./telestats.db")

# Render/PostgreSQL adjustment
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, index=True)
    title = Column(String)
    username = Column(String, nullable=True)
    type = Column(String)  # 'channel' or 'group'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    stats = relationship("Stats", back_populates="chat", cascade="all, delete-orphan")
    settings = relationship("Settings", back_populates="chat", uselist=False, cascade="all, delete-orphan")
    actions = relationship("MemberAction", back_populates="chat", cascade="all, delete-orphan")

class Stats(Base):
    __tablename__ = "stats"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    date = Column(Date, default=lambda: datetime.utcnow().date())
    members_count = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    avg_views = Column(Float, default=0.0)
    
    chat = relationship("Chat", back_populates="stats")

class MemberAction(Base):
    __tablename__ = "member_actions"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    user_id = Column(BigInteger)
    added_by = Column(BigInteger, nullable=True)
    action_type = Column(String)  # 'join', 'leave', 'add'
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    chat = relationship("Chat", back_populates="actions")

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), unique=True)
    cleanup_enabled = Column(Boolean, default=False)
    
    chat = relationship("Chat", back_populates="settings")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
