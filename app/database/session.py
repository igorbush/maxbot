import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlmodel import SQLModel, select, delete, or_, text
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
        "cost_spasibki": 5,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Выбор соседа по парте на неделю",
        "description": "Право выбрать соседа по парте на уроках в течение одной учебной недели.",
        "cost_spasibki": 2,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Индивидуальная консультация учителя",
        "description": "20 минут персонального разбора трудных тем и задач перед контрольной работой.",
        "cost_spasibki": 1,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Иммунитет от ответа у доски на 1 урок",
        "description": "Возможность пропустить вызов к доске на одном уроке по вашему выбору.",
        "cost_spasibki": 3,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Своя тема проекта",
        "description": "Право защитить проект или доклад на самостоятельно выбранную интересную тему.",
        "cost_spasibki": 3,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Право пересдачи самостоятельной работы",
        "description": "Возможность переписать одну самостоятельную работу для повышения четвертной оценки.",
        "cost_spasibki": 4,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Дополнительный балл к проверочной",
        "description": "Плюс один балл к итоговой оценке за одну проверочную работу в четверти.",
        "cost_spasibki": 5,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Ассистент учителя на уроке",
        "description": "Помощь педагогу в подготовке интерактивных материалов и проведении урока.",
        "cost_spasibki": 2,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Музыкальный плейлист на перемене",
        "description": "Право поставить подборку любимых треков на перемене.",
        "cost_spasibki": 1,
        "is_active": True,
    },
    {
        "created_by_teacher_id": "teacher_admin",
        "chat_id": None,
        "title": "Диплом знатока и помощника",
        "description": "Именная почётная грамота от учителя за активную взаимовыручку для учебного портфолио.",
        "cost_spasibki": 5,
        "is_active": True,
    },
]

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with async_session_factory() as session:
        res = await session.execute(select(Achievement).limit(1))
        if res.scalar_one_or_none() is None:
            for item in DEFAULT_ACHIEVEMENTS:
                session.add(Achievement(**item))

        rew_res = await session.execute(select(Reward).limit(1))
        if rew_res.scalar_one_or_none() is None:
            for r in READY_REWARDS:
                session.add(Reward(**r))
        else:
            existing_rewards = (await session.execute(select(Reward))).scalars().all()
            for r in existing_rewards:
                if r.cost_spasibki > 10:
                    r.cost_spasibki = max(1, r.cost_spasibki // 10)

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
