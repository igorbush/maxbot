import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings
from app.database.models import (
    Base,
    Achievement,
    Chat,
    ChatMember,
    Question,
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

            demo_chats = [
                Chat(max_chat_id="chat_7b", title="7Б Класс (МБОУ СОШ №1)", owner_id="9999"),
                Chat(max_chat_id="chat_8a", title="8А Класс (Физика)", owner_id="9999"),
            ]
            for c in demo_chats:
                session.add(c)

            demo_users = [
                User(max_user_id="1001", display_name="Аркадий Петров", role="student", balance_spasibki=18, xp=480, rank="Знаток"),
                User(max_user_id="1002", display_name="Мария Смирнова", role="student", balance_spasibki=9, xp=290, rank="Знаток"),
                User(max_user_id="1003", display_name="Иван Васильев", role="student", balance_spasibki=3, xp=110, rank="Любитель"),
                User(max_user_id="1004", display_name="Дарья Ковалёва", role="student", balance_spasibki=14, xp=350, rank="Знаток"),
                User(max_user_id="1005", display_name="Артём Морозов", role="student", balance_spasibki=22, xp=520, rank="Эксперт"),
                User(max_user_id="9999", display_name="Мария Ивановна", role="teacher", balance_spasibki=0, xp=0, rank="Учитель"),
                User(max_user_id="teacher_1", display_name="Сергей Викторович", role="teacher", balance_spasibki=0, xp=0, rank="Учитель"),
            ]
            for u in demo_users:
                session.add(u)

            demo_members = [
                ChatMember(chat_max_id="chat_7b", user_max_id="9999", role="teacher"),
                ChatMember(chat_max_id="chat_7b", user_max_id="1001", role="student"),
                ChatMember(chat_max_id="chat_7b", user_max_id="1002", role="student"),
                ChatMember(chat_max_id="chat_7b", user_max_id="1003", role="student"),
                ChatMember(chat_max_id="chat_7b", user_max_id="1004", role="student"),
                ChatMember(chat_max_id="chat_7b", user_max_id="1005", role="student"),
                ChatMember(chat_max_id="chat_8a", user_max_id="9999", role="teacher"),
                ChatMember(chat_max_id="chat_8a", user_max_id="1001", role="student"),
                ChatMember(chat_max_id="chat_8a", user_max_id="1004", role="student"),
            ]
            for m in demo_members:
                session.add(m)

            demo_rewards = [
                Reward(created_by_teacher_id="9999", chat_id="chat_7b", title="Освобождение от одного ДЗ", description="Возможность сдать одно домашнее задание позже или не сдавать", cost_spasibki=50, is_active=True),
                Reward(created_by_teacher_id="9999", chat_id="chat_7b", title="Выбор соседа по парте", description="Возможность пересесть на неделю к выбранному однокласснику", cost_spasibki=30, is_active=True),
                Reward(created_by_teacher_id="9999", chat_id=None, title="Консультация с учителем", description="30 минут разбора трудной темы перед контрольной работой", cost_spasibki=20, is_active=True),
                Reward(created_by_teacher_id="9999", chat_id=None, title="Своя тема проекта", description="Право выбрать нестандартную творческую тему школьного проекта", cost_spasibki=40, is_active=True),
            ]
            for r in demo_rewards:
                session.add(r)

            demo_q = Question(
                group_chat_id="chat_7b",
                group_chat_title="7Б Класс (МБОУ СОШ №1)",
                group_message_id="msg_demo_1",
                author_max_id="1002",
                author_name="Мария Смирнова",
                text="Ребята, помогите решить задачу №5 по геометрии! Не получается построить правильный треугольник.",
                subject="Геометрия",
                status="open",
            )
            session.add(demo_q)

            await session.commit()

async def get_db_session():
    async with async_session_factory() as session:
        yield session
