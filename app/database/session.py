import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlmodel import SQLModel, select, delete, or_, not_, text
from app.config import get_settings
from app.database.models import (
    Achievement,
    Answer,
    Chat,
    ChatMember,
    Question,
    Reward,
    RewardClaim,
    User,
    UserAchievement,
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

READY_REWARDS = [
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Освобождение от одного домашнего задания",
        "description": "Возможность не сдавать или сдать позже любое обычное домашнее задание по согласованию с учителем.",
        "cost_spasibki": 7,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Выбор соседа по парте на неделю",
        "description": "Право выбрать соседа по парте на уроках в течение одной учебной недели.",
        "cost_spasibki": 5,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Консультация с учителем перед проверочной",
        "description": "20 минут персонального разбора трудных тем и задач перед контрольной работой.",
        "cost_spasibki": 4,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Своя тема проекта",
        "description": "Право защитить проект или доклад на самостоятельно выбранную интересную тему.",
        "cost_spasibki": 6,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Иммунитет от ответа у доски на 1 урок",
        "description": "Возможность пропустить вызов к доске на одном уроке по вашему выбору.",
        "cost_spasibki": 6,
        "is_active": True,
    },
]

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session_factory() as session:
        try:
            await session.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR"))
            await session.commit()
        except Exception:
            pass

        for item in DEFAULT_ACHIEVEMENTS:
            ach_res = await session.execute(select(Achievement).where(Achievement.code == item["code"]))
            ach_obj = ach_res.scalar_one_or_none()
            if not ach_obj:
                session.add(Achievement(**item))
            else:
                ach_obj.icon_url = item.get("icon_url")
                ach_obj.name_ru = item["name_ru"]
                ach_obj.description_ru = item["description_ru"]

        keep_titles = [r["title"] for r in READY_REWARDS]
        await session.execute(
            delete(Reward).where(
                Reward.created_by_teacher_id == "teacher_admin",
                Reward.chat_id.is_(None),
                not_(Reward.title.in_(keep_titles)),
            )
        )
        for r in READY_REWARDS:
            existing_r_res = await session.execute(
                select(Reward).where(
                    Reward.created_by_teacher_id == "teacher_admin",
                    Reward.chat_id.is_(None),
                    Reward.title == r["title"],
                )
            )
            existing_r = existing_r_res.scalar_one_or_none()
            if not existing_r:
                session.add(Reward(**r))
            else:
                existing_r.cost_spasibki = r["cost_spasibki"]
                existing_r.description = r["description"]

        await session.execute(text("UPDATE chat_members SET balance_spasibki = 0 WHERE role = 'teacher'"))
        await session.execute(text("UPDATE users SET balance_spasibki = 0 WHERE role IN ('teacher', 'admin')"))

        dummy_user_ids = ["1001", "1002", "1003", "1004", "1005", "9999", "teacher_1", "student_demo", "test_user"]
        await session.execute(delete(ChatMember).where(ChatMember.user_max_id.in_(dummy_user_ids)))
        await session.execute(delete(User).where(User.max_user_id.in_(dummy_user_ids)))
        await session.execute(delete(Question).where(Question.author_max_id.in_(dummy_user_ids)))
        await session.execute(delete(Answer).where(Answer.author_max_id.in_(dummy_user_ids)))
        await session.execute(delete(UserAchievement).where(UserAchievement.user_max_id.in_(dummy_user_ids)))
        await session.execute(delete(RewardClaim).where(RewardClaim.student_max_id.in_(dummy_user_ids)))
        await session.execute(delete(Chat).where(Chat.max_chat_id.in_(["chat_7b", "chat_8a"])))

        try:
            await session.execute(text("ALTER TABLE questions ADD COLUMN user_message_id VARCHAR"))
            await session.commit()
        except Exception:
            pass

        try:
            await session.execute(text("ALTER TABLE chat_members ADD COLUMN balance_spasibki INTEGER DEFAULT 5"))
            await session.commit()
        except Exception:
            pass

        try:
            await session.execute(text("UPDATE chat_members SET balance_spasibki = 5 WHERE balance_spasibki IS NULL"))
            await session.commit()
        except Exception:
            pass

        teacher_ids_subq = select(User.max_user_id).where(User.role.in_(["teacher", "admin"]))
        await session.execute(delete(RewardClaim).where(RewardClaim.student_max_id.in_(teacher_ids_subq)))
        await session.execute(text("UPDATE chat_members SET balance_spasibki = 0 WHERE role = 'teacher'"))
        await session.execute(text("UPDATE users SET balance_spasibki = 0 WHERE role IN ('teacher', 'admin')"))

        dialog_subq = select(Chat.max_chat_id).where(
            or_(
                Chat.title == "Диалог",
                Chat.title.ilike("%диалог%"),
                Chat.max_chat_id.in_(select(User.max_user_id)),
            )
        )
        bad_chat_ids = (await session.execute(dialog_subq)).scalars().all()
        if bad_chat_ids:
            await session.execute(delete(ChatMember).where(ChatMember.chat_max_id.in_(bad_chat_ids)))
            await session.execute(delete(Chat).where(Chat.max_chat_id.in_(bad_chat_ids)))

        await session.commit()

async def get_db_session():
    async with async_session_factory() as session:
        yield session
