from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select, desc
from maxapi import F
from maxapi.filters.command import Command, CommandStart
from maxapi.types import (
    MessageCreated, MessageCallback, BotStarted,
    CallbackButton, LinkButton
)
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from config import BASE_URL, SECRET_TEACHER_CODE
from bot.main import bot, dp
from app.database import engine, get_or_create_user
from app.models import (
    User, Question, Achievement, UserAchievement,
    calculate_level
)


def is_night_mode() -> bool:
    msk_time = datetime.now(timezone.utc) + timedelta(hours=3)
    return msk_time.hour >= 22 or msk_time.hour < 7


def check_and_grant_achievements(session: Session, user: User, fast_help: bool = False) -> list[str]:
    newly_unlocked = []

    def award_if_not_had(code: str):
        ach = session.exec(select(Achievement).where(Achievement.code == code)).first()
        if not ach:
            return
        existing = session.exec(
            select(UserAchievement).where(
                UserAchievement.user_id == user.id,
                UserAchievement.achievement_id == ach.id
            )
        ).first()
        if not existing:
            ua = UserAchievement(user_id=user.id, achievement_id=ach.id)
            user.xp += ach.xp_reward
            user.coins += ach.coins_reward
            session.add(ua)
            newly_unlocked.append(f"{ach.icon} «{ach.title}» (+{ach.xp_reward} XP, +{ach.coins_reward} спасибок)")

    if user.helped_count >= 1:
        award_if_not_had("first_help")

    if user.helped_count >= 5:
        award_if_not_had("helper_5")

    if user.helped_count >= 20:
        award_if_not_had("helper_20")

    if fast_help:
        award_if_not_had("fast_help")

    return newly_unlocked


def make_webapp_keyboard(user_id: int) -> list:
    b = InlineKeyboardBuilder()
    webapp_url = f"{BASE_URL}/?user_id={user_id}"
    b.add(LinkButton(text="📱 Открыть Лигу Помощников", url=webapp_url))
    return [b.as_markup()]


@dp.bot_started()
async def on_bot_started(event: BotStarted):
    user_id = event.user.user_id if event.user else 0
    name = event.user.name if event.user else "Ученик"
    username = event.user.username if event.user else None

    user = get_or_create_user(
        max_user_id=user_id,
        name=name,
        username=username,
        chat_id=event.chat_id
    )

    welcome_text = (
        f"👋 Привет, {user.name}!\n\n"
        "Добро пожаловать в **«Лигу Помощников»** — игровое сообщество нашего класса! 🎓\n\n"
        "Здесь ты можешь:\n"
        "• Задавать вопросы по домашке с помощью команды `/ask`\n"
        "• Помогать одноклассникам и получать **опыт (XP)** и **спасибки 🪙**\n"
        "• Расти в званиях от «Новичка» до «Легенды школы»\n"
        "• Обменивать спасибки в **Школьной лавке** на крутые награды от учителя!\n\n"
        "Нажми кнопку ниже, чтобы открыть свой профиль и рейтинг класса 👇"
    )

    await bot.send_message(
        chat_id=event.chat_id,
        text=welcome_text,
        attachments=make_webapp_keyboard(user.max_user_id)
    )


@dp.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    sender = event.message.sender
    chat_id = event.message.recipient.chat_id if event.message.recipient.chat_id else event.message.recipient.user_id

    user = get_or_create_user(
        max_user_id=sender.user_id,
        name=sender.first_name or sender.username or "Ученик",
        username=sender.username,
        chat_id=chat_id
    )

    text = (
        f"👋 Привет, {user.name}!\n\n"
        "Ты в **Лиге Помощников**! 🚀\n\n"
        "📌 **Быстрые команды:**\n"
        "• `/ask [вопрос]` — задать вопрос классу\n"
        "• `/me` — твой профиль, опыт и звание\n"
        "• `/top` — рейтинг лидеров класса\n"
        "• `/help` — подробная справка\n"
        "• `/teacher [код]` — активация роли учителя\n\n"
        "Загляни в мини-приложение, чтобы посмотреть свои достижения и награды:"
    )

    await event.message.answer(
        text=text,
        attachments=make_webapp_keyboard(user.max_user_id)
    )


@dp.message_created(Command("help"))
async def cmd_help(event: MessageCreated):
    text = (
        "📖 **Справка по «Лиге Помощников»**\n\n"
        "1️⃣ **Как задать вопрос?**\n"
        "Напишите: `/ask [текст вопроса]`\n"
        "Пример: `/ask Ребята, как решить №245 по геометрии?`\n\n"
        "2️⃣ **Как помочь и получить XP?**\n"
        "Одноклассник отвечает на вопрос в чате и нажимает кнопку **«💡 Я помог»**.\n"
        "Автор вопроса нажимает кнопку **«⭐️ Сказать спасибо»**.\n"
        "Помощник получает **+15 XP** и **+5 спасибок 🪙**!\n\n"
        "3️⃣ **Зачем нужны спасибки?**\n"
        "Их можно обменять в WebApp на реальные награды от учителя: освобождение от ДЗ, выбор места в классе и другие бонусы!\n\n"
        "🌙 **Тихий час:** с 22:00 до 07:00 опыт не начисляется, чтобы все высыпались перед уроками."
    )
    await event.message.answer(text=text)


@dp.message_created(Command("me"))
async def cmd_me(event: MessageCreated):
    sender = event.message.sender
    chat_id = event.message.recipient.chat_id or event.message.recipient.user_id

    user = get_or_create_user(
        max_user_id=sender.user_id,
        name=sender.first_name or sender.username or "Ученик",
        username=sender.username,
        chat_id=chat_id
    )

    level_info = calculate_level(user.xp)

    pct = level_info["progress_percent"]
    filled = int(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)

    role_str = "🎓 Учитель" if user.role == "teacher" else "🎒 Ученик"

    text = (
        f"👤 **Профиль: {user.name}** ({role_str})\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎖 **Звание:** {level_info['title']} (Уровень {level_info['level']})\n"
        f"⚡️ **Опыт:** {user.xp} / {level_info['next_xp']} XP\n"
        f"[{bar}] {pct}%\n"
        f"🪙 **Спасибки:** {user.coins}\n"
        f"🤝 **Помог одноклассникам:** {user.helped_count} раз\n"
        f"❓ **Задал вопросов:** {user.questions_count}\n"
    )

    await event.message.answer(
        text=text,
        attachments=make_webapp_keyboard(user.max_user_id)
    )


@dp.message_created(Command("top"))
async def cmd_top(event: MessageCreated):
    with Session(engine) as session:
        top_students = session.exec(
            select(User).where(User.role == "student").order_by(desc(User.xp)).limit(5)
        ).all()

        lines = ["🏆 **Топ помощников класса:**\n"]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for idx, s in enumerate(top_students):
            lvl = calculate_level(s.xp)
            lines.append(f"{medals[idx]} **{s.name}** — {s.xp} XP ({lvl['title']}) • {s.helped_count} 🤝")

        lines.append("\nНажмите кнопку ниже, чтобы открыть полный рейтинг:")

    sender_id = event.message.sender.user_id
    await event.message.answer(
        text="\n".join(lines),
        attachments=make_webapp_keyboard(sender_id)
    )


@dp.message_created(Command("teacher"))
async def cmd_teacher(event: MessageCreated):
    text_body = event.message.body.text or ""
    parts = text_body.strip().split(maxsplit=1)

    if len(parts) < 2:
        await event.message.answer(
            text="Использование: `/teacher [секретный_код]`\nСпросите код у классного руководителя."
        )
        return

    code = parts[1].strip()
    sender = event.message.sender

    if code == SECRET_TEACHER_CODE:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.max_user_id == sender.user_id)).first()
            if not user:
                user = get_or_create_user(sender.user_id, sender.first_name, sender.username)
            user.role = "teacher"
            session.add(user)
            session.commit()

        await event.message.answer(
            text=(
                f"🎉 Поздравляем, {sender.first_name}!\n"
                "Вам успешно назначена роль **Учителя** 🎓.\n"
                "Теперь в WebApp вам доступна вкладка **«Учительская»**, где вы можете:\n"
                "• Создавать свои награды для класса\n"
                "• Подтверждать обмен 'спасибок' учеников\n"
                "• Вручать особое достижение «Выбор учителя»"
            ),
            attachments=make_webapp_keyboard(sender.user_id)
        )
    else:
        await event.message.answer(text="❌ Неверный секретный код учителя!")


@dp.message_created(Command("ask"))
async def cmd_ask(event: MessageCreated):
    text_body = event.message.body.text or ""
    parts = text_body.strip().split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await event.message.answer(
            text=(
                "❓ **Как задать вопрос:**\n"
                "Напишите: `/ask [текст вашего вопроса]`\n\n"
                "Например:\n"
                "`/ask Кто понял задачу №3 по физике? Объясните формулу!`"
            )
        )
        return

    question_text = parts[1].strip()
    sender = event.message.sender
    chat_id = event.message.recipient.chat_id or event.message.recipient.user_id

    night_warning = ""
    if is_night_mode():
        night_warning = "\n\n🌙 *Внимание: сейчас тихий час (с 22:00 до 07:00). Вопрос опубликован, но опыт за помощь будет засчитан утром!*"

    with Session(engine) as session:
        user = get_or_create_user(sender.user_id, sender.first_name, sender.username, chat_id)
        user.questions_count += 1
        session.add(user)

        q = Question(
            chat_id=chat_id,
            author_id=user.id,
            subject="Учёба",
            text=question_text,
            status="open"
        )
        session.add(q)
        session.commit()
        session.refresh(q)
        q_id = q.id

    b = InlineKeyboardBuilder()
    b.add(CallbackButton(text="💡 Я помог", payload=f"helped:{q_id}"))
    b.add(CallbackButton(text="⭐️ Сказать спасибо", payload=f"thanks:{q_id}"))
    b.row(LinkButton(text="📱 Открыть Лигу", url=f"{BASE_URL}/?user_id={sender.user_id}"))

    post_text = (
        f"📚 **Новый вопрос от {sender.first_name}:**\n\n"
        f"«{question_text}»\n\n"
        f"👇 Одноклассники, помогите объяснить решение!"
        f"{night_warning}"
    )

    await event.message.answer(
        text=post_text,
        attachments=[b.as_markup()]
    )


@dp.message_callback()
async def on_callback(event: MessageCallback):
    payload = event.callback.payload or ""
    clicker_user = event.callback.user
    clicker_id = clicker_user.user_id

    if payload.startswith("helped:"):
        q_id = int(payload.split(":")[1])

        with Session(engine) as session:
            q = session.exec(select(Question).where(Question.id == q_id)).first()
            if not q:
                await event.answer(notification="Вопрос не найден!")
                return

            author = session.exec(select(User).where(User.id == q.author_id)).first()
            if not author:
                await event.answer(notification="Ошибка автора вопроса.")
                return

            if author.max_user_id == clicker_id:
                await event.answer(notification="❌ Вы не можете помочь самому себе!")
                return

            helper = get_or_create_user(
                max_user_id=clicker_id,
                name=clicker_user.first_name,
                username=clicker_user.username
            )

            q.helper_id = helper.id
            session.add(q)
            session.commit()

        await event.answer(notification=f"Отлично! Автор ({author.name}) теперь может подтвердить вашу помощь кнопкой '⭐️ Сказать спасибо'.")

        await bot.send_message(
            chat_id=event.chat.chat_id if event.chat else clicker_id,
            text=f"💡 **{clicker_user.first_name}** откликнулся на вопрос!\n{author.name}, когда ответ будет понятен, нажми **«⭐️ Сказать спасибо»** под вопросом."
        )

    elif payload.startswith("thanks:"):
        q_id = int(payload.split(":")[1])

        with Session(engine) as session:
            q = session.exec(select(Question).where(Question.id == q_id)).first()
            if not q:
                await event.answer(notification="Вопрос не найден!")
                return

            author = session.exec(select(User).where(User.id == q.author_id)).first()
            if not author:
                await event.answer(notification="Ошибка автора вопроса.")
                return

            if author.max_user_id != clicker_id:
                await event.answer(notification=f"Только автор вопроса ({author.name}) может сказать спасибо!")
                return

            if q.status == "answered":
                await event.answer(notification="За этот вопрос благодарность уже начислена!")
                return

            if not q.helper_id:
                await event.answer(notification="Сначала помощник должен нажать кнопку '💡 Я помог'!")
                return

            helper = session.exec(select(User).where(User.id == q.helper_id)).first()
            if not helper:
                await event.answer(notification="Помощник не найден.")
                return

            if helper.id == author.id:
                await event.answer(notification="Нельзя благодарить самого себя!")
                return

            xp_gained = 15
            coins_gained = 5
            helper.xp += xp_gained
            helper.coins += coins_gained
            helper.helped_count += 1

            author.xp += 2

            q.status = "answered"
            q.answered_at = datetime.now(timezone.utc)

            diff_minutes = (q.answered_at - q.created_at).total_seconds() / 60
            is_fast = diff_minutes <= 15

            unlocked_achievements = check_and_grant_achievements(session, helper, fast_help=is_fast)

            session.add(helper)
            session.add(author)
            session.add(q)
            session.commit()

            helper_name = helper.name
            helper_level = calculate_level(helper.xp)["title"]

        await event.answer(notification=f"Благодарность отправлена {helper_name}!")

        congrats_lines = [
            f"🎉 **{author.name} поблагодарил(а) {helper_name} за помощь!**",
            f"━━━━━━━━━━━━━━━━━━",
            f"⚡️ {helper_name} получает: **+{xp_gained} XP** и **+{coins_gained} спасибок 🪙**!",
            f"🎖 Текущее звание {helper_name}: **{helper_level}**",
        ]

        if unlocked_achievements:
            congrats_lines.append("\n🌟 **РАЗБЛОКИРОВАНО НОВОЕ ДОСТИЖЕНИЕ:**")
            for ach_str in unlocked_achievements:
                congrats_lines.append(f"• {ach_str}")

        await bot.send_message(
            chat_id=event.chat.chat_id if event.chat else clicker_id,
            text="\n".join(congrats_lines),
            attachments=make_webapp_keyboard(clicker_id)
        )
