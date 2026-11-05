from typing import Generator
from sqlmodel import SQLModel, create_engine, Session, select
from config import DATABASE_URL
from app.models import User, Achievement, Reward

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def seed_initial_data(session: Session):
    existing_achievements = session.exec(select(Achievement)).all()
    if not existing_achievements:
        default_achievements = [
            Achievement(
                code="first_help",
                title="Первый шаг",
                description="Помочь однокласснику с вопросом в первый раз",
                icon="🌱",
                xp_reward=20,
                coins_reward=10,
            ),
            Achievement(
                code="fast_help",
                title="Скорая помощь",
                description="Ответить и получить 'Спасибо' быстрее чем за 15 минут",
                icon="⚡️",
                xp_reward=30,
                coins_reward=15,
            ),
            Achievement(
                code="helper_5",
                title="Спасатель",
                description="Помочь одноклассникам 5 раз",
                icon="🛟",
                xp_reward=50,
                coins_reward=25,
            ),
            Achievement(
                code="helper_20",
                title="Наставник класса",
                description="Успешно помочь 20 раз",
                icon="🎓",
                xp_reward=150,
                coins_reward=60,
            ),
            Achievement(
                code="math_expert",
                title="Знаток точных наук",
                description="Помочь 5 раз по математике или физике",
                icon="📐",
                xp_reward=40,
                coins_reward=20,
            ),
            Achievement(
                code="humanities_expert",
                title="Гуманитарий",
                description="Помочь 5 раз по литературе, русскому или истории",
                icon="📖",
                xp_reward=40,
                coins_reward=20,
            ),
            Achievement(
                code="teacher_choice",
                title="Выбор учителя",
                description="Получить особое признание учителя за лучшее объяснение темы",
                icon="⭐️",
                xp_reward=100,
                coins_reward=50,
            ),
        ]
        for ach in default_achievements:
            session.add(ach)
        session.commit()

    existing_rewards = session.exec(select(Reward)).all()
    if not existing_rewards:
        default_rewards = [
            Reward(
                title="Освобождение от одного ДЗ",
                description="Право не сдавать одно домашнее задание по согласованию с учителем",
                price_coins=50,
                icon="📝",
            ),
            Reward(
                title="Выбор соседа по парте",
                description="Право выбрать место и соседа по парте на всю следующую неделю",
                price_coins=35,
                icon="🪑",
            ),
            Reward(
                title="Первый выбор темы проекта",
                description="Право первым выбрать тему доклада или учебного проекта",
                price_coins=25,
                icon="🎯",
            ),
            Reward(
                title="Консультация учителя 1-на-1",
                description="15 минут персонального разбора сложной темы с учителем",
                price_coins=40,
                icon="💡",
            ),
        ]
        for rew in default_rewards:
            session.add(rew)
        session.commit()

    existing_users = session.exec(select(User)).all()
    if not existing_users:
        demo_users = [
            User(
                max_user_id=1001,
                name="Аркадий Смирнов",
                username="arkadiy",
                role="student",
                xp=480,
                coins=45,
                helped_count=12,
                questions_count=3,
            ),
            User(
                max_user_id=1002,
                name="Маша Ковалева",
                username="masha_k",
                role="student",
                xp=290,
                coins=30,
                helped_count=7,
                questions_count=6,
            ),
            User(
                max_user_id=1003,
                name="Иван Петров",
                username="ivan_p",
                role="student",
                xp=110,
                coins=15,
                helped_count=3,
                questions_count=5,
            ),
            User(
                max_user_id=9999,
                name="Мария Ивановна (Учитель)",
                username="teacher_maria",
                role="teacher",
                xp=0,
                coins=0,
                helped_count=0,
                questions_count=0,
            ),
        ]
        for u in demo_users:
            session.add(u)
        session.commit()


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_initial_data(session)


def get_or_create_user(
    max_user_id: int,
    name: str = "Ученик",
    username: str = None,
    chat_id: int = None
) -> User:
    with Session(engine) as session:
        statement = select(User).where(User.max_user_id == max_user_id)
        user = session.exec(statement).first()
        if not user:
            user = User(
                max_user_id=max_user_id,
                name=name or "Ученик",
                username=username,
                chat_id=chat_id,
                role="student",
                xp=0,
                coins=10,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            updated = False
            if name and user.name != name:
                user.name = name
                updated = True
            if username and user.username != username:
                user.username = username
                updated = True
            if chat_id and user.chat_id != chat_id:
                user.chat_id = chat_id
                updated = True
            if updated:
                session.add(user)
                session.commit()
                session.refresh(user)
        return user
