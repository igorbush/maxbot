from typing import Optional
from sqlmodel import select
from maxapi import Bot, Dispatcher
from maxapi.filters.command import Command, CommandStart
from maxapi.types import MessageCreated, MessageCallback, BotStarted
from maxapi.types import CallbackButton, LinkButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import get_settings
from app.database.session import async_session_factory
from app.database.models import User, Chat, ChatMember, Question, Answer, Reward
from app.services.gamification import GamificationService

settings = get_settings()
dp = Dispatcher()

def extract_display_name(user) -> str:
    if not user:
        return "Ученик"
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    full = f"{first} {last}".strip()
    if full:
        return full
    username = getattr(user, "username", "") or ""
    if username:
        return username
    user_id = getattr(user, "user_id", "")
    return f"Школьник {user_id}"

def build_main_menu_keyboard(webapp_url: str):
    builder = InlineKeyboardBuilder()
    builder.add(LinkButton(text="📱 Открыть WebApp", url=webapp_url))
    builder.add(CallbackButton(text="❓ Как спросить?", payload="menu:ask_info"))
    builder.add(CallbackButton(text="👤 Мой профиль", payload="menu:profile"))
    builder.add(CallbackButton(text="🏆 Рейтинг", payload="menu:top"))
    builder.add(CallbackButton(text="🎁 Лавка", payload="menu:shop"))
    builder.add(CallbackButton(text="🎓 Кабинет учителя", payload="menu:teacher"))
    builder.adjust(1, 2, 2, 1)
    return builder

def build_question_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="↩ Ответьте реплаем на этот вопрос", payload="noop"))
    builder.adjust(1)
    return builder

def build_approval_keyboard(answer_id: int):
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="✅ Помог (+50 XP)", payload=f"help_accept:{answer_id}"))
    builder.add(CallbackButton(text="❌ Не помог", payload=f"help_reject:{answer_id}"))
    builder.adjust(2)
    return builder

async def ensure_user_and_chat(session, user_id: str, display_name: str, chat_id: Optional[str] = None, chat_title: Optional[str] = None, owner_id: Optional[str] = None):
    res_user = await session.execute(select(User).where(User.max_user_id == user_id))
    user = res_user.scalar_one_or_none()

    is_chat_creator = bool(owner_id and str(owner_id) == str(user_id))
    initial_role = "teacher" if is_chat_creator else "student"

    if not user:
        user = User(
            max_user_id=user_id,
            display_name=display_name,
            role=initial_role,
            balance_spasibki=5,
            xp=50,
            rank="Новичок",
        )
        session.add(user)
    else:
        if display_name and not display_name.startswith("Школьник "):
            user.display_name = display_name
        if is_chat_creator and user.role != "teacher":
            user.role = "teacher"

    if chat_id:
        res_chat = await session.execute(select(Chat).where(Chat.max_chat_id == chat_id))
        chat_row = res_chat.scalar_one_or_none()
        if not chat_row:
            chat_row = Chat(
                max_chat_id=chat_id,
                title=chat_title or "Школьный чат",
                owner_id=owner_id,
            )
            session.add(chat_row)
        else:
            if chat_title:
                chat_row.title = chat_title
            if owner_id and not chat_row.owner_id:
                chat_row.owner_id = owner_id

        res_member = await session.execute(
            select(ChatMember).where(ChatMember.chat_max_id == chat_id, ChatMember.user_max_id == user_id)
        )
        member_row = res_member.scalar_one_or_none()
        if not member_row:
            member_row = ChatMember(
                chat_max_id=chat_id,
                user_max_id=user_id,
                role="teacher" if is_chat_creator else user.role,
            )
            session.add(member_row)

    await session.commit()
    return user

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    print(f"[БОТ] Бот запущен пользователем {user_name} (ID: {user_id})")

    async with async_session_factory() as session:
        await ensure_user_and_chat(session, user_id=user_id, display_name=user_name)

    webapp_url = f"{settings.WEBAPP_BASE_URL}?user_id={user_id}"
    kb = build_main_menu_keyboard(webapp_url)

    text = (
        f"👋 Привет, {user_name}!\n\n"
        f"Добро пожаловать в «Лигу Помощников» — бот взаимопомощи для школьников в мессенджере MAX!\n\n"
        f"🔹 Задавайте вопросы по домашке командой /ask в чате класса.\n"
        f"🔹 Отвечайте реплаем на вопросы одноклассников, получайте XP и монетки-спасибки 🪙!\n"
        f"🔹 Обменивайте спасибки на классные школьные бонусы в лавке наград!\n\n"
        f"Используйте кнопки ниже для быстрого управления:"
    )
    if event.chat:
        chat_target = int(event.chat.chat_id) if str(event.chat.chat_id).isdigit() else event.chat.chat_id
        await event.bot.send_message(chat_id=chat_target, text=text, attachments=[kb.as_markup()])

@dp.message_created(CommandStart())
@dp.message_created(Command("start"))
async def on_start_command(event: MessageCreated):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    chat_id = str(event.chat.chat_id) if event.chat else ""
    chat_title = getattr(event.chat, "title", None) or "Диалог"
    owner_id = str(event.chat.owner_id) if event.chat and getattr(event.chat, "owner_id", None) else None

    print(f"[БОТ] Команда /start от {user_name} (ID: {user_id}) в '{chat_title}'")

    async with async_session_factory() as session:
        await ensure_user_and_chat(session, user_id=user_id, display_name=user_name, chat_id=chat_id, chat_title=chat_title, owner_id=owner_id)

    webapp_url = f"{settings.WEBAPP_BASE_URL}?user_id={user_id}"
    kb = build_main_menu_keyboard(webapp_url)

    text = (
        f"👋 Рады видеть, {user_name}!\n\n"
        f"«Лига Помощников» готова к работе. Вы можете открыть мини-приложение, проверить звание или посмотреть доступные награды."
    )
    await event.message.answer(text=text, attachments=[kb.as_markup()])

@dp.message_created(Command("help"))
async def on_help_command(event: MessageCreated):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    print(f"[БОТ] Команда /help от {user_name}")

    webapp_url = f"{settings.WEBAPP_BASE_URL}?user_id={user_id}"
    kb = build_main_menu_keyboard(webapp_url)

    text = (
        f"📖 Как пользоваться «Лигой Помощников»:\n\n"
        f"1. Добавьте бота в чат вашего класса.\n"
        f"2. Чтобы задать вопрос, напишите: /ask <ваш вопрос>\n"
        f"3. Чтобы помочь, ответьте реплаем (Reply) на сообщение бота с вопросом.\n"
        f"4. Автор вопроса нажимает кнопку «Помог», и вам начисляется +50 XP и +1 спасибка 🪙!\n"
        f"5. В лавке обменивайте спасибки на школьные бонусы от учителя!"
    )
    await event.message.answer(text=text, attachments=[kb.as_markup()])

@dp.message_created(Command("manage"))
async def on_manage_command(event: MessageCreated):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    print(f"[БОТ] Команда /manage от {user_name}")

    async with async_session_factory() as session:
        res = await session.execute(select(User).where(User.max_user_id == user_id))
        user = res.scalar_one_or_none()
        is_teacher = bool(user and user.role in ("teacher", "admin"))

    webapp_url = f"{settings.WEBAPP_BASE_URL}?user_id={user_id}"

    if is_teacher:
        text = (
            f"🎓 Кабинет учителя для {user_name}\n\n"
            f"Здесь вы можете одобрять запросы учеников на награды, добавлять новые школьные бонусы и отмечать лучших помощников наградой «Выбор учителя»."
        )
    else:
        text = (
            f"🎓 Кабинет учителя\n\n"
            f"Этот раздел предназначен для педагогов и создателей чатов классов. В WebApp вы можете посмотреть статус своих наград."
        )

    builder = InlineKeyboardBuilder()
    builder.add(LinkButton(text="📱 Открыть кабинет в WebApp", url=webapp_url))
    await event.message.answer(text=text, attachments=[builder.as_markup()])

@dp.message_created(Command("ask"))
async def on_ask_command(event: MessageCreated):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    chat_id = str(event.chat.chat_id) if event.chat else ""
    chat_title = getattr(event.chat, "title", None) or "Класс"
    owner_id = str(event.chat.owner_id) if event.chat and getattr(event.chat, "owner_id", None) else None

    raw_text = event.message.body.text if event.message and event.message.body else ""
    parts = raw_text.split(maxsplit=1)
    question_text = parts[1].strip() if len(parts) > 1 else ""

    if not question_text:
        await event.message.answer(
            text="❗ Пожалуйста, укажите текст вопроса.\n\nПример:\n/ask Ребята, подскажите, как решить номер 4 по геометрии?"
        )
        return

    mid = event.message.body.mid if event.message and event.message.body else f"msg_{user_id}"

    async with async_session_factory() as session:
        await ensure_user_and_chat(session, user_id=user_id, display_name=user_name, chat_id=chat_id, chat_title=chat_title, owner_id=owner_id)

        q = Question(
            group_chat_id=chat_id,
            group_chat_title=chat_title,
            group_message_id=mid,
            author_max_id=user_id,
            author_name=user_name,
            text=question_text,
            status="open",
        )
        session.add(q)
        await session.commit()
        await session.refresh(q)

        print(f"[БОТ] Опубликован вопрос #{q.id} от {user_name} в чате '{chat_title}': «{question_text}»")

    kb = build_question_keyboard()
    card_text = (
        f"❓ ВОПРОС ПО УЧЁБЕ #{q.id}\n\n"
        f"👤 Автор: {user_name}\n"
        f"🏫 Класс: {chat_title}\n\n"
        f"«{question_text}»\n\n"
        f"👉 Чтобы помочь, нажмите 'Ответить' (Reply) на это сообщение!"
    )
    await event.message.answer(text=card_text, attachments=[kb.as_markup()])

@dp.message_created()
async def on_generic_message(event: MessageCreated):
    if not event.message or not event.message.body:
        return

    raw_text = event.message.body.text or ""
    if raw_text.startswith("/"):
        return

    if not event.message.link or not event.message.link.message:
        return

    parent_mid = event.message.link.message.mid
    if not parent_mid:
        return

    helper_id = str(event.from_user.user_id) if event.from_user else ""
    helper_name = extract_display_name(event.from_user)
    chat_id = str(event.chat.chat_id) if event.chat else ""
    chat_title = getattr(event.chat, "title", None) or "Класс"
    answer_mid = event.message.body.mid

    async with async_session_factory() as session:
        res_q = await session.execute(
            select(Question).where(Question.group_message_id == parent_mid, Question.status == "open")
        )
        question = res_q.scalar_one_or_none()
        if not question:
            return

        if helper_id == question.author_max_id:
            await event.message.reply(text="Вы не можете отвечать на свой собственный вопрос! 😊")
            return

        await ensure_user_and_chat(session, user_id=helper_id, display_name=helper_name, chat_id=chat_id, chat_title=chat_title)

        ans = Answer(
            question_id=question.id,
            author_max_id=helper_id,
            author_name=helper_name,
            group_message_id=answer_mid,
            text=raw_text,
            status="pending",
        )
        session.add(ans)
        await session.commit()
        await session.refresh(ans)

        print(f"[БОТ] Ответ на вопрос #{question.id} от {helper_name}: «{raw_text}»")

    author_target = int(question.author_max_id) if question.author_max_id.isdigit() else question.author_max_id
    approval_kb = build_approval_keyboard(ans.id)
    dm_text = (
        f"🤝 Вам ответил(а) {helper_name} на вопрос #{question.id}:\n\n"
        f"«{raw_text}»\n\n"
        f"Помогло ли вам это объяснение?"
    )

    try:
        await event.bot.send_message(user_id=author_target, text=dm_text, attachments=[approval_kb.as_markup()])
        await event.message.reply(text=f"Ответ от {helper_name} отправлен автору вопроса на подтверждение! ✅")
    except Exception:
        await event.message.reply(text=f"Ответ от {helper_name} зафиксирован! Автору вопроса нужно открыть диалог с ботом для подтверждения.")

@dp.message_callback()
async def on_callback_query(event: MessageCallback):
    payload = event.callback.payload if event.callback else ""
    user_id = str(event.callback.user.user_id) if event.callback and event.callback.user else ""
    user_name = extract_display_name(event.callback.user) if event.callback else "Ученик"

    print(f"[БОТ] Нажата кнопка '{payload}' от {user_name} (ID: {user_id})")

    if payload == "noop":
        if event.callback and event.callback.callback_id:
            await event.bot.send_callback(callback_id=event.callback.callback_id, notification="Ответьте реплаем на вопрос!")
        return

    if payload.startswith("help_accept:"):
        ans_id = int(payload.split(":")[1])
        async with async_session_factory() as session:
            res_ans = await session.execute(select(Answer).where(Answer.id == ans_id))
            answer = res_ans.scalar_one_or_none()
            if not answer or answer.status != "pending":
                if event.callback and event.callback.callback_id:
                    await event.bot.send_callback(callback_id=event.callback.callback_id, notification="Ответ уже обработан.")
                return

            res_q = await session.execute(select(Question).where(Question.id == answer.question_id))
            question = res_q.scalar_one_or_none()
            if not question or str(question.author_max_id) != str(user_id):
                if event.callback and event.callback.callback_id:
                    await event.bot.send_callback(callback_id=event.callback.callback_id, notification="Только автор вопроса может подтвердить помощь!")
                return

            await GamificationService.award_gratitude(
                session=session,
                question_id=question.id,
                answer_id=answer.id,
                author_id=user_id,
                helper_id=answer.author_max_id,
            )

            print(f"[БОТ] Помощь подтверждена! Вопрос #{question.id} решён, {answer.author_name} получил +50 XP и +1 спасибку")

        try:
            await event.message.edit(text=f"✅ Помощь принята! {answer.author_name} получил(а) +50 XP и +1 спасибку 🪙. Спасибо!")
        except Exception:
            pass

        try:
            chat_target = int(question.group_chat_id) if question.group_chat_id.isdigit() else question.group_chat_id
            celeb_text = (
                f"🎉 Вопрос #{question.id} успешно решён!\n"
                f"Помог(ла): {answer.author_name} (+50 XP, +1 🪙)\n"
                f"Автор {question.author_name} поблагодарил(а) за помощь! 👏"
            )
            await event.bot.send_message(chat_id=chat_target, text=celeb_text)
        except Exception:
            pass

        if event.callback and event.callback.callback_id:
            await event.bot.send_callback(callback_id=event.callback.callback_id, notification="Помощь принята!")
        return

    if payload.startswith("help_reject:"):
        ans_id = int(payload.split(":")[1])
        async with async_session_factory() as session:
            res_ans = await session.execute(select(Answer).where(Answer.id == ans_id))
            answer = res_ans.scalar_one_or_none()
            if answer:
                answer.status = "rejected"
                await session.commit()

        try:
            await event.message.edit(text="❌ Ответ отклонён. Вопрос остаётся открытым для других одноклассников.")
        except Exception:
            pass

        if event.callback and event.callback.callback_id:
            await event.bot.send_callback(callback_id=event.callback.callback_id, notification="Ответ отклонён")
        return

    webapp_url = f"{settings.WEBAPP_BASE_URL}?user_id={user_id}"
    kb = build_main_menu_keyboard(webapp_url)

    if payload == "menu:ask_info":
        info_text = (
            f"❓ Как задать вопрос классу:\n\n"
            f"1. Откройте чат вашего класса.\n"
            f"2. Отправьте сообщение:\n"
            f"/ask <текст вашего вопроса>\n\n"
            f"Бот создаст карточку с вопросом. Одноклассники смогут ответить реплаем, а вы выберете лучший ответ!"
        )
        try:
            await event.message.edit(text=info_text, attachments=[kb.as_markup()])
        except Exception:
            pass

    elif payload == "menu:profile":
        async with async_session_factory() as session:
            res_user = await session.execute(select(User).where(User.max_user_id == user_id))
            u = res_user.scalar_one_or_none()
            rank_name = u.rank if u else "Новичок"
            xp_val = u.xp if u else 0
            coins_val = u.balance_spasibki if u else 0
            role_title = "Учитель 🎓" if (u and u.role == "teacher") else "Школьник"

        profile_text = (
            f"👤 Профиль в Лиге Помощников:\n\n"
            f"Имя: {user_name}\n"
            f"Статус: {role_title}\n"
            f"Звание: {rank_name}\n"
            f"Опыт: {xp_val} XP\n"
            f"Баланс: {coins_val} спасибок 🪙\n\n"
            f"Откройте WebApp для подробной статистики и достижений."
        )
        try:
            await event.message.edit(text=profile_text, attachments=[kb.as_markup()])
        except Exception:
            pass

    elif payload == "menu:top":
        async with async_session_factory() as session:
            leaders_res = await session.execute(
                select(User).where(User.role == "student").order_by(User.xp.desc()).limit(5)
            )
            leaders = leaders_res.scalars().all()

        lines = ["🏆 Топ-5 помощников школы:\n"]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for idx, leader in enumerate(leaders):
            m = medals[idx] if idx < len(medals) else "▫️"
            lines.append(f"{m} {leader.display_name} — {leader.xp} XP ({leader.balance_spasibki} 🪙)")

        top_text = "\n".join(lines) + "\n\nПолная таблица лидеров доступна в WebApp."
        try:
            await event.message.edit(text=top_text, attachments=[kb.as_markup()])
        except Exception:
            pass

    elif payload == "menu:shop":
        async with async_session_factory() as session:
            rewards_res = await session.execute(
                select(Reward).where(Reward.is_active == True).order_by(Reward.cost_spasibki.asc()).limit(4)
            )
            rewards = rewards_res.scalars().all()

        lines = ["🎁 Школьная лавка наград:\n"]
        for r in rewards:
            lines.append(f"• {r.title} — 🪙 {r.cost_spasibki} спасибок")

        shop_text = "\n".join(lines) + "\n\nОбменять спасибки можно во вкладке «Лавка» в WebApp!"
        try:
            await event.message.edit(text=shop_text, attachments=[kb.as_markup()])
        except Exception:
            pass

    elif payload == "menu:teacher":
        teacher_text = (
            f"🎓 Кабинет учителя\n\n"
            f"Педагоги могут создавать классные награды, одобрять запросы школьников и вручать бейджи «Выбор учителя» прямо в WebApp."
        )
        try:
            await event.message.edit(text=teacher_text, attachments=[kb.as_markup()])
        except Exception:
            pass

    if event.callback and event.callback.callback_id:
        try:
            await event.bot.send_callback(callback_id=event.callback.callback_id)
        except Exception:
            pass
