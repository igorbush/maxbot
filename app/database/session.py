import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings
from app.database.models import (
    Base,
    Achievement,
    Reward,
    User,
    DEFAULT_ACHIEVEMENTS,
)

settings = get_settings()

db_url = settings.DATABASE_URL
if db_url.startswith("sqlite+aiosqlite:///"):
    path = db_url.replace("sqlite+aiosqlite:///", "")
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
elif db_url.startswith("sqlite:///"):
    path = db_url.replace("sqlite:///", "")
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

engine = create_async_engine(db_url)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        res = await session.execute(select(Achievement).limit(1))
        if res.scalar_one_or_none() is None:
            for item in DEFAULT_ACHIEVEMENTS:
                session.add(Achievement(**item))

            demo_users = [
                User(max_user_id="1001", display_name="Аркадий", role="student", balance_spasibki=18, xp=480, rank="Знаток"),
                User(max_user_id="1002", display_name="Маша", role="student", balance_spasibki=9, xp=290, rank="Знаток"),
                User(max_user_id="1003", display_name="Иван", role="student", balance_spasibki=3, xp=110, rank="Любитель"),
                User(max_user_id="9999", display_name="Мария Ивановна", role="teacher", balance_spasibki=0, xp=0, rank="Учитель"),
                User(max_user_id="teacher_1", display_name="Учитель", role="teacher", balance_spasibki=0, xp=0, rank="Учитель"),
            ]
            for u in demo_users:
                session.add(u)

            demo_rewards = [
                Reward(created_by_teacher_id="9999", title="Освобождение от одного ДЗ", description="Можно сдать одно домашнее задание позже или не сдавать", cost_spasibki=50, is_active=True),
                Reward(created_by_teacher_id="9999", title="Выбор соседа по парте", description="Возможность пересесть на неделю к выбранному однокласснику", cost_spasibki=30, is_active=True),
                Reward(created_by_teacher_id="9999", title="Консультация с учителем", description="30 минут индивидуального разбора трудной темы перед контрольной", cost_spasibki=20, is_active=True),
                Reward(created_by_teacher_id="9999", title="Своя тема проекта", description="Право выбрать нестандартную тему для школьного проекта", cost_spasibki=40, is_active=True),
            ]
            for r in demo_rewards:
                session.add(r)

            await session.commit()

async def get_db_session():
    async with async_session_factory() as session:
        yield session

