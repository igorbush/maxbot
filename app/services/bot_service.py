from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlmodel import select, delete, or_, not_
from maxapi import Bot, Dispatcher
from maxapi.filters.command import Command, CommandStart
from maxapi.types import MessageCreated, MessageCallback, BotStarted, BotAdded, UserRemoved, BotRemoved
from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.config import get_settings
from app.database.session import async_session_factory
from app.database.models import User, Chat, ChatMember, Question, Answer, Reward, RewardClaim
from app.services.gamification import GamificationService

settings = get_settings()
dp = Dispatcher()

def extract_display_name(user) -> str:
    if not user:
        return "Участник"
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    full = f"{first} {last}".strip()
    if full:
        return full
    username = getattr(user, "username", "") or ""
    if username:
        return username
    user_id = getattr(user, "user_id", "")
    return f"Участник {user_id}"

def build_main_menu_keyboard(is_teacher: bool = False):
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="❓ Как спросить?", payload="menu:ask_info"))
    builder.add(CallbackButton(text="👤 Мой профиль", payload="menu:profile"))
    builder.add(CallbackButton(text="🪙 Баланс спасибок", payload="menu:balance"))
    builder.adjust(2, 1)
    return builder

async def fetch_user_chat_balances(session, bot: Optional[Bot], user_id: str) -> Tuple[List[Tuple[str, int]], int]:
    query = (
        select(Chat.title, ChatMember.balance_spasibki, Chat.max_chat_id)
        .join(ChatMember, Chat.max_chat_id == ChatMember.chat_max_id)
        .where(
            ChatMember.user_max_id == user_id,
            Chat.title != "Диалог",
            not_(Chat.title.ilike("%диалог%")),
        )
        .order_by(Chat.title.asc())
    )
    res = await session.execute(query)
    rows = res.all()

    active_balances: List[Tuple[str, int]] = []
    removed_chat_ids: List[str] = []

    for title, bal, cid in rows:
        is_member = True
        if bot and cid and user_id and cid.isdigit() and user_id.isdigit():
            try:
                mem = await bot.get_chat_member(chat_id=int(cid), user_id=int(user_id))
                if not mem:
                    is_member = False
            except Exception as e:
                err_text = str(e).lower()
                if any(k in err_text for k in ["not found", "not in chat", "forbidden", "404", "403"]):
                    is_member = False

        if not is_member:
            removed_chat_ids.append(cid)
        else:
            active_balances.append((title, bal if bal is not None else 0))

    if removed_chat_ids:
        await session.execute(
            delete(ChatMember).where(
                ChatMember.user_max_id == user_id,
                ChatMember.chat_max_id.in_(removed_chat_ids),
            )
        )
        await session.commit()

    total_spasibki = sum(b for _, b in active_balances)
    return active_balances, total_spasibki

async def send_response_or_dm(event: MessageCreated, text: str, kb=None, is_group: bool = False):
    attachments = [kb.as_markup()] if kb else None
    if is_group:
        user_id = str(event.from_user.user_id) if event.from_user else ""
        target_uid = int(user_id) if user_id.isdigit() else None
        user_name = extract_display_name(event.from_user)
        if target_uid:
            try:
                await event.bot.send_message(user_id=target_uid, text=text, attachments=attachments)
                await event.message.reply(text=f"{user_name}, я отправил вам информацию в личные сообщения.")
                return
            except Exception:
                await event.message.reply(text=f"{user_name}, чтобы открыть меню, перейдите в личный диалог с ботом.")
                return
    await event.message.answer(text=text, attachments=attachments)

def build_approval_keyboard(answer_id: int):
    builder = InlineKeyboardBuilder()
    builder.add(CallbackButton(text="✅ Помог (+50 XP)", payload=f"help_accept:{answer_id}"))
    builder.add(CallbackButton(text="❌ Не помог", payload=f"help_reject:{answer_id}"))
    builder.adjust(2)
    return builder

async def ensure_user_and_chat(
    session,
    user_id: str,
    display_name: str,
    chat_id: Optional[str] = None,
    chat_title: Optional[str] = None,
    owner_id: Optional[str] = None,
    is_admin: bool = False,
    is_group: bool = False,
):
    res_user = await session.execute(select(User).where(User.max_user_id == user_id))
    user = res_user.scalar_one_or_none()

    is_teacher = is_admin or bool(owner_id and str(owner_id) == str(user_id))

    if not user:
        user = User(
            max_user_id=user_id,
            display_name=display_name,
            role="teacher" if is_teacher else "student",
            balance_spasibki=10,
            xp=100,
            rank="Любитель",
        )
        session.add(user)
    else:
        if display_name and not display_name.startswith("Участник "):
            user.display_name = display_name
        if is_teacher and user.role != "teacher":
            user.role = "teacher"

    if is_group and chat_id and chat_title and chat_title.lower() != "диалог":
        res_chat = await session.execute(select(Chat).where(Chat.max_chat_id == chat_id))
        chat_row = res_chat.scalar_one_or_none()
        if not chat_row:
            chat_row = Chat(
                max_chat_id=chat_id,
                title=chat_title,
                owner_id=owner_id,
            )
            session.add(chat_row)
        else:
            if chat_title:
                chat_row.title = chat_title
            if owner_id and not chat_row.owner_id:
                chat_row.owner_id = owner_id

        member_role = "teacher" if is_teacher else "student"
        res_member = await session.execute(
            select(ChatMember).where(ChatMember.chat_max_id == chat_id, ChatMember.user_max_id == user_id)
        )
        member_row = res_member.scalar_one_or_none()
        if not member_row:
            member_row = ChatMember(
                chat_max_id=chat_id,
                user_max_id=user_id,
                role=member_role,
                balance_spasibki=5,
            )
            session.add(member_row)
        else:
            if is_teacher and member_row.role != "teacher":
                member_row.role = "teacher"

    await session.commit()
    return user

@dp.bot_added()
async def on_bot_added(event: BotAdded):
    chat_id = str(event.chat_id)
    print(f"[БОТ] Бот добавлен в чат {chat_id}")

    try:
        chat_obj = await event.bot.get_chat_by_id(event.chat_id)
        chat_title = chat_obj.title if chat_obj else f"Чат {chat_id}"
        owner_id = str(chat_obj.owner_id) if chat_obj and chat_obj.owner_id else None

        async with async_session_factory() as session:
            res_chat = await session.execute(select(Chat).where(Chat.max_chat_id == chat_id))
            chat_row = res_chat.scalar_one_or_none()
            if not chat_row:
                chat_row = Chat(max_chat_id=chat_id, title=chat_title, owner_id=owner_id)
                session.add(chat_row)
            else:
                chat_row.title = chat_title
                if owner_id:
                    chat_row.owner_id = owner_id

            if owner_id:
                res_m = await session.execute(
                    select(ChatMember).where(ChatMember.chat_max_id == chat_id, ChatMember.user_max_id == owner_id)
                )
                if not res_m.scalar_one_or_none():
                    session.add(ChatMember(chat_max_id=chat_id, user_max_id=owner_id, role="teacher", balance_spasibki=5))

            try:
                admin_res = await event.bot.get_list_admin_chat(event.chat_id)
                if admin_res and hasattr(admin_res, "members") and admin_res.members:
                    for adm in admin_res.members:
                        adm_id = str(adm.user_id)
                        adm_name = f"{adm.first_name or ''} {adm.last_name or ''}".strip() or adm.username or f"Учитель {adm_id}"
                        u_res = await session.execute(select(User).where(User.max_user_id == adm_id))
                        adm_u = u_res.scalar_one_or_none()
                        if not adm_u:
                            session.add(User(max_user_id=adm_id, display_name=adm_name, role="teacher", balance_spasibki=10, xp=100))
                        else:
                            adm_u.role = "teacher"

                        res_adm_m = await session.execute(
                            select(ChatMember).where(ChatMember.chat_max_id == chat_id, ChatMember.user_max_id == adm_id)
                        )
                        adm_m = res_adm_m.scalar_one_or_none()
                        if not adm_m:
                            session.add(ChatMember(chat_max_id=chat_id, user_max_id=adm_id, role="teacher", balance_spasibki=5))
                        else:
                            adm_m.role = "teacher"
            except Exception:
                pass

            await session.commit()
    except Exception as e:
        print(f"[БОТ] Ошибка регистрации чата: {e}")

@dp.user_removed()
async def on_user_removed(event: UserRemoved):
    chat_id = str(event.chat_id)
    user_id = str(event.user.user_id) if event.user else ""
    if chat_id and user_id:
        async with async_session_factory() as session:
            await session.execute(
                delete(ChatMember).where(
                    ChatMember.chat_max_id == chat_id,
                    ChatMember.user_max_id == user_id,
                )
            )
            await session.commit()
            print(f"[БОТ] Участник {user_id} удалён из чата {chat_id}")

@dp.bot_removed()
async def on_bot_removed(event: BotRemoved):
    chat_id = str(event.chat_id)
    if chat_id:
        async with async_session_factory() as session:
            await session.execute(delete(ChatMember).where(ChatMember.chat_max_id == chat_id))
            await session.execute(delete(Chat).where(Chat.max_chat_id == chat_id))
            await session.commit()
            print(f"[БОТ] Бот удалён из чата {chat_id}")

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    print(f"[БОТ] Бот запущен пользователем {user_name} (ID: {user_id})")

    async with async_session_factory() as session:
        await ensure_user_and_chat(session, user_id=user_id, display_name=user_name, is_group=False)

    kb = build_main_menu_keyboard()
    text = (
        f"Здравствуйте, {user_name}!\n\n"
        f"«Лига Помощников» — бот взаимопомощи в мессенджере MAX.\n\n"
        f"• Задавайте вопросы командой /ask в учебном чате группы.\n"
        f"• Отвечайте реплаем на вопросы одноклассников, получайте XP и спасибки.\n"
        f"• Рейтинг класса можно посмотреть прямо в чате командой /top.\n\n"
        f"Используйте кнопки под сообщением для просмотра профиля и справки:"
    )
    if event.chat:
        chat_target = int(event.chat.chat_id) if str(event.chat.chat_id).isdigit() else event.chat.chat_id
        await event.bot.send_message(chat_id=chat_target, text=text, attachments=[kb.as_markup()])

@dp.message_created(CommandStart())
@dp.message_created(Command(["start", "start@ideya_fiks_59_bot"]))
async def on_start_command(event: MessageCreated):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    chat_id = str(event.chat.chat_id) if event.chat else ""
    chat_type = getattr(event.chat, "type", "") or ""
    is_group = bool(chat_type in ("chat", "group", "channel") and getattr(event.chat, "title", None))
    chat_title = event.chat.title if is_group else None
    owner_id = str(event.chat.owner_id) if event.chat and getattr(event.chat, "owner_id", None) else None

    print(f"[БОТ] Команда /start от {user_name} (ID: {user_id})")

    async with async_session_factory() as session:
        await ensure_user_and_chat(
            session,
            user_id=user_id,
            display_name=user_name,
            chat_id=chat_id if is_group else None,
            chat_title=chat_title,
            owner_id=owner_id,
            is_group=is_group,
        )

    kb = build_main_menu_keyboard()
    text = (
        f"Здравствуйте, {user_name}!\n\n"
        f"Лига Помощников готова к работе. Выберите действие на клавиатуре бота:"
    )
    await send_response_or_dm(event, text=text, kb=kb, is_group=is_group)

@dp.message_created(Command(["help", "help@ideya_fiks_59_bot"]))
async def on_help_command(event: MessageCreated):
    user_name = extract_display_name(event.from_user)
    chat_type = getattr(event.chat, "type", "") or ""
    is_group = bool(chat_type in ("chat", "group", "channel") and getattr(event.chat, "title", None))
    print(f"[БОТ] Команда /help от {user_name}")

    kb = build_main_menu_keyboard()
    text = (
        f"Инструкция по работе с Лигой Помощников:\n\n"
        f"1. Добавьте бота в ваш учебный чат.\n"
        f"2. Чтобы задать вопрос, напишите в группе:\n/ask <текст вопроса>\n"
        f"3. Чтобы помочь, ответьте реплаем (Reply) на сообщение с вопросом.\n"
        f"4. Автор вопроса нажимает кнопку «Помог», и помощнику начисляется +50 XP и +1 спасибка.\n"
        f"5. Команда /top в групповом чате выводит рейтинг помощников класса."
    )
    await send_response_or_dm(event, text=text, kb=kb, is_group=is_group)

@dp.message_created(Command(["balance", "balance@ideya_fiks_59_bot", "spasibki", "spasibki@ideya_fiks_59_bot"]))
async def on_balance_command(event: MessageCreated):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    chat_type = getattr(event.chat, "type", "") or ""
    is_group = bool(chat_type in ("chat", "group", "channel") and getattr(event.chat, "title", None))

    if is_group:
        await event.message.reply(
            text=f"{user_name}, баланс спасибок по каждому чату доступен в личном диалоге с ботом."
        )
        return

    async with async_session_factory() as session:
        active_balances, total_spasibki = await fetch_user_chat_balances(session, event.bot, user_id)

    kb = build_main_menu_keyboard()
    if not active_balances:
        balance_text = (
            "🪙 Баланс спасибок:\n\n"
            "Вы пока не состоите в активных учебных чатах с начисленными спасибками.\n\n"
            "Помогайте одноклассникам в группах, отвечая на вопросы реплаем, чтобы заработать спасибки!"
        )
    else:
        lines = ["🪙 Ваш баланс спасибок по чатам:\n"]
        for title, bal in active_balances:
            lines.append(f"• «{title}»: {bal} спасибок")
        lines.append(f"\nВсего: {total_spasibki} спасибок")
        balance_text = "\n".join(lines)

    await event.message.answer(text=balance_text, attachments=[kb.as_markup()])

@dp.message_created(Command(["top", "top@ideya_fiks_59_bot", "rating", "rating@ideya_fiks_59_bot"]))
async def on_top_command(event: MessageCreated):
    chat_id = str(event.chat.chat_id) if event.chat else ""
    chat_type = getattr(event.chat, "type", "") or ""
    is_group = bool(chat_type in ("chat", "group", "channel") and getattr(event.chat, "title", None))
    chat_title = event.chat.title if is_group else "Учебный чат"

    if not is_group:
        await event.message.reply(
            text="Рейтинг рассчитывается для учебных классов. Отправьте команду /top в групповом чате."
        )
        return

    async with async_session_factory() as session:
        leaders_res = await session.execute(
            select(User, ChatMember.balance_spasibki)
            .join(ChatMember, ChatMember.user_max_id == User.max_user_id)
            .where(ChatMember.chat_max_id == chat_id)
            .order_by(User.xp.desc(), ChatMember.balance_spasibki.desc(), User.id.asc())
            .limit(10)
        )
        leaders = leaders_res.all()

    lines = [f"🏆 Топ помощников чата «{chat_title}»:\n"]
    if not leaders:
        lines.append("В этом чате пока нет участников с начисленными баллами.")
    else:
        for idx, (leader, chat_bal) in enumerate(leaders, 1):
            badge = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            bal = chat_bal if chat_bal is not None else leader.balance_spasibki
            lines.append(f"{badge} {leader.display_name} — {leader.xp} XP ({bal} спасибок)")

    await event.message.reply(text="\n".join(lines))

@dp.message_created(Command(["ask", "ask@ideya_fiks_59_bot"]))
async def on_ask_command(event: MessageCreated):
    user_id = str(event.from_user.user_id) if event.from_user else ""
    user_name = extract_display_name(event.from_user)
    chat_id = str(event.chat.chat_id) if event.chat else ""
    chat_type = getattr(event.chat, "type", "") or ""
    is_group = bool(chat_type in ("chat", "group", "channel") and getattr(event.chat, "title", None))
    chat_title = event.chat.title if is_group else "Учебный чат"
    owner_id = str(event.chat.owner_id) if event.chat and getattr(event.chat, "owner_id", None) else None

    if not is_group:
        await event.message.reply(
            text=(
                "💡 Команда /ask работает только в учебных групповых чатах!\n\n"
                "Добавьте бота в ваш групповой чат и задайте вопрос там, "
                "чтобы другие участники могли ответить реплаем и получить баллы взаимопомощи."
            )
        )
        return

    raw_text = event.message.body.text if event.message and event.message.body else ""
    words = raw_text.strip().split()
    if words and words[0].startswith("@"):
        words = words[1:]
    if words and (words[0].lower() == "/ask" or words[0].lower().startswith("/ask@")):
        words = words[1:]
    question_text = " ".join(words).strip()

    if not question_text:
        await event.message.reply(
            text="Пожалуйста, укажите текст вопроса после команды.\n\nПример:\n/ask Ребята, как решить задачу №4 по геометрии?"
        )
        return

    user_mid = str(event.message.body.mid) if event.message and event.message.body else f"msg_{user_id}"

    async with async_session_factory() as session:
        await ensure_user_and_chat(
            session,
            user_id=user_id,
            display_name=user_name,
            chat_id=chat_id if is_group else None,
            chat_title=chat_title,
            owner_id=owner_id,
            is_group=is_group,
        )

        q = Question(
            group_chat_id=chat_id,
            group_chat_title=chat_title,
            group_message_id=user_mid,
            user_message_id=user_mid,
            author_max_id=user_id,
            author_name=user_name,
            text=question_text,
            status="open",
        )
        session.add(q)
        await session.commit()
        await session.refresh(q)

        sent = await event.message.reply(
            text="💡 Вопрос принят в Лигу Помощников! Ответьте на него реплаем, чтобы помочь (+50 XP)."
        )
        if sent and sent.message and sent.message.body and sent.message.body.mid:
            q.group_message_id = str(sent.message.body.mid)
            await session.commit()

        print(f"[БОТ] Вопрос опубликован в чате '{chat_title}' от {user_name}")

async def sync_bot_chats(target_bot: Bot):
    try:
        chats_data = await target_bot.get_chats(count=100)
        if not chats_data or not hasattr(chats_data, "chats") or not chats_data.chats:
            return

        async with async_session_factory() as session:
            for c in chats_data.chats:
                chat_id = str(c.chat_id)
                chat_type = getattr(c, "type", "") or ""
                chat_title = getattr(c, "title", None)

                if chat_type in ("dialog", "user") or not chat_title or chat_title.lower() == "диалог":
                    continue

                owner_id = str(c.owner_id) if getattr(c, "owner_id", None) else None

                res_chat = await session.execute(select(Chat).where(Chat.max_chat_id == chat_id))
                chat_row = res_chat.scalar_one_or_none()
                if not chat_row:
                    chat_row = Chat(max_chat_id=chat_id, title=chat_title, owner_id=owner_id)
                    session.add(chat_row)
                else:
                    chat_row.title = chat_title
                    if owner_id:
                        chat_row.owner_id = owner_id

                if owner_id:
                    res_m = await session.execute(
                        select(ChatMember).where(ChatMember.chat_max_id == chat_id, ChatMember.user_max_id == owner_id)
                    )
                    if not res_m.scalar_one_or_none():
                        session.add(ChatMember(chat_max_id=chat_id, user_max_id=owner_id, role="teacher"))

                try:
                    admins_data = await target_bot.get_list_admin_chat(int(chat_id))
                    if admins_data and hasattr(admins_data, "members") and admins_data.members:
                        for adm in admins_data.members:
                            adm_id = str(adm.user_id)
                            adm_name = f"{adm.first_name or ''} {adm.last_name or ''}".strip() or adm.username or f"Учитель {adm_id}"

                            u_res = await session.execute(select(User).where(User.max_user_id == adm_id))
                            u_row = u_res.scalar_one_or_none()
                            if not u_row:
                                session.add(User(max_user_id=adm_id, display_name=adm_name, role="teacher", balance_spasibki=10, xp=100))
                            else:
                                u_row.role = "teacher"
                                if adm_name and not adm_name.startswith("Учитель "):
                                    u_row.display_name = adm_name

                            am_res = await session.execute(
                                select(ChatMember).where(ChatMember.chat_max_id == chat_id, ChatMember.user_max_id == adm_id)
                            )
                            if not am_res.scalar_one_or_none():
                                session.add(ChatMember(chat_max_id=chat_id, user_max_id=adm_id, role="teacher"))
                            else:
                                am_row = am_res.scalar_one()
                                am_row.role = "teacher"
                except Exception:
                    pass

            await session.commit()
            print("[БОТ] Синхронизация чатов и администраторов завершена")
    except Exception as e:
        print(f"[БОТ] Синхронизация чатов: {e}")

@dp.message_created()
async def on_generic_message(event: MessageCreated):
    if not event.message or not event.message.body:
        return

    chat_id = str(event.chat.chat_id) if event.chat else ""
    chat_type = getattr(event.chat, "type", "") or ""
    chat_title = getattr(event.chat, "title", None)
    is_group = bool(chat_type in ("chat", "group", "channel") and chat_title and chat_title.lower() != "диалог")

    sender_id = str(event.from_user.user_id) if event.from_user else ""
    sender_name = extract_display_name(event.from_user)
    owner_id = str(event.chat.owner_id) if event.chat and getattr(event.chat, "owner_id", None) else None

    if is_group and sender_id:
        async with async_session_factory() as session:
            is_owner = bool(owner_id and owner_id == sender_id)
            await ensure_user_and_chat(
                session,
                user_id=sender_id,
                display_name=sender_name,
                chat_id=chat_id,
                chat_title=chat_title,
                owner_id=owner_id,
                is_admin=is_owner,
                is_group=True,
            )

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
    answer_mid = event.message.body.mid

    async with async_session_factory() as session:
        res_q = await session.execute(
            select(Question).where(
                or_(
                    Question.group_message_id == parent_mid,
                    Question.user_message_id == parent_mid,
                    Question.group_message_id.like(f"%{parent_mid}%"),
                    Question.user_message_id.like(f"%{parent_mid}%"),
                ),
                Question.status == "open",
            )
        )
        question = res_q.scalar_one_or_none()
        if not question:
            return

        if helper_id and question.author_max_id and str(helper_id) == str(question.author_max_id):
            await event.message.reply(
                text="Вы не можете отвечать на собственный вопрос для начисления баллов."
            )
            return

        await ensure_user_and_chat(
            session,
            user_id=helper_id,
            display_name=helper_name,
            chat_id=chat_id if is_group else None,
            chat_title=chat_title,
            is_group=is_group,
        )

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

        print(f"[БОТ] Ответ на вопрос от {helper_name}")

    author_target = int(question.author_max_id) if str(question.author_max_id).isdigit() else None
    approval_kb = build_approval_keyboard(ans.id)
    dm_text = (
        f"Вам ответил(а) {helper_name} на ваш вопрос:\n\n"
        f"«{raw_text}»\n\n"
        f"Помогло ли вам это объяснение?"
    )

    sent_to_author = False
    if author_target:
        try:
            await event.bot.send_message(user_id=author_target, text=dm_text, attachments=[approval_kb.as_markup()])
            sent_to_author = True
        except Exception as e:
            print(f"[БОТ] Не удалось отправить ЛС автору {author_target}: {e}")

    if sent_to_author:
        await event.message.reply(text=f"Ответ от {helper_name} принят и отправлен автору вопроса в личные сообщения для подтверждения.")
    else:
        await event.message.reply(text=f"Ответ от {helper_name} принят! Автору вопроса нужно открыть диалог с ботом, чтобы подтвердить помощь.")

@dp.message_callback()
async def on_callback_query(event: MessageCallback):
    payload = event.callback.payload if event.callback else ""
    user_id = str(event.callback.user.user_id) if event.callback and event.callback.user else ""
    user_name = extract_display_name(event.callback.user) if event.callback else "Ученик"

    print(f"[БОТ] Нажата кнопка '{payload}' от {user_name} (ID: {user_id})")

    if payload.startswith("help_accept:"):
        ans_id = int(payload.split(":")[1])
        helper_name = "Помощник"
        q_id = None
        chat_id = None
        q_author_name = "Автор"
        already_handled = False
        is_already_accepted = False

        async with async_session_factory() as session:
            res_ans = await session.execute(select(Answer).where(Answer.id == ans_id))
            answer = res_ans.scalar_one_or_none()
            if not answer:
                try:
                    await event.edit(text="Ответ не найден или был удалён.", attachments=[])
                except Exception:
                    await event.ack(notification="Ответ не найден")
                return

            helper_name = answer.author_name or "Помощник"
            res_q = await session.execute(select(Question).where(Question.id == answer.question_id))
            question = res_q.scalar_one_or_none()
            if not question:
                try:
                    await event.edit(text="Вопрос не найден или был удалён.", attachments=[])
                except Exception:
                    await event.ack(notification="Вопрос не найден")
                return

            q_id = question.id
            chat_id = question.group_chat_id
            q_author_name = question.author_name or "Автор"

            if user_id and question.author_max_id and str(user_id) != str(question.author_max_id):
                is_teacher_here = False
                res_u = await session.execute(select(User).where(User.max_user_id == user_id))
                u_obj = res_u.scalar_one_or_none()
                if u_obj and u_obj.role in ("teacher", "admin"):
                    is_teacher_here = True
                if not is_teacher_here:
                    try:
                        await event.ack(notification="Только автор вопроса может подтвердить ответ")
                    except Exception:
                        pass
                    return

            if str(answer.author_max_id) == str(question.author_max_id):
                try:
                    await event.edit(text="Нельзя подтверждать помощь самому себе.", attachments=[])
                except Exception:
                    await event.ack(notification="Нельзя подтверждать помощь самому себе")
                return

            if answer.status == "accepted":
                already_handled = True
                is_already_accepted = True
            elif answer.status != "pending":
                already_handled = True
                is_already_accepted = False
            else:
                answer.status = "accepted"
                question.status = "resolved"
                question.resolved_answer_id = answer.id
                question.closed_at = datetime.now(timezone.utc)

                helper_res = await session.execute(select(User).where(User.max_user_id == answer.author_max_id))
                helper = helper_res.scalar_one_or_none()
                if helper is not None:
                    helper.balance_spasibki += 1
                    helper.xp += 50
                    helper.rank = GamificationService.calculate_rank(helper.xp)
                else:
                    helper = User(
                        max_user_id=answer.author_max_id,
                        display_name=answer.author_name or "Ученик",
                        role="student",
                        balance_spasibki=11,
                        xp=150,
                        rank=GamificationService.calculate_rank(150),
                    )
                    session.add(helper)

                if chat_id:
                    cm_res = await session.execute(
                        select(ChatMember).where(
                            ChatMember.chat_max_id == chat_id,
                            ChatMember.user_max_id == answer.author_max_id,
                        )
                    )
                    cm_obj = cm_res.scalar_one_or_none()
                    if cm_obj is not None:
                        cm_obj.balance_spasibki += 1
                    else:
                        session.add(
                            ChatMember(
                                chat_max_id=chat_id,
                                user_max_id=answer.author_max_id,
                                role="student",
                                balance_spasibki=6,
                            )
                        )

                await session.commit()
                print(f"[БОТ] Помощь подтверждена: {helper_name} получил +50 XP и +1 спасибку")

        if already_handled:
            if is_already_accepted:
                text_msg = f"Помощь уже была принята ранее! {helper_name} получил(а) награду."
            else:
                text_msg = "Этот ответ уже обработан ранее."
        else:
            text_msg = f"Помощь принята! {helper_name} получил(а) +50 XP и +1 спасибку. Спасибо за взаимовыручку!"

        try:
            await event.edit(
                text=text_msg,
                attachments=[],
                notification="Помощь принята!" if not already_handled else "Уже обработано",
            )
        except Exception as e_edit:
            print(f"[БОТ] event.edit error: {e_edit}")
            try:
                await event.ack(notification="Помощь принята!")
            except Exception:
                pass

        if not already_handled and chat_id:
            try:
                chat_target = int(chat_id) if str(chat_id).isdigit() else chat_id
                celeb_text = (
                    f"🎉 Вопрос успешно решён!\n\n"
                    f"Помог(ла): {helper_name} (+50 XP, +1 спасибка)\n"
                    f"Автор {q_author_name} поблагодарил(а) за помощь."
                )
                await event.bot.send_message(chat_id=chat_target, text=celeb_text)
            except Exception as e:
                print(f"[БОТ] Ошибка отправки поздравления: {e}")

        return

    if payload.startswith("help_reject:"):
        ans_id = int(payload.split(":")[1])
        async with async_session_factory() as session:
            res_ans = await session.execute(select(Answer).where(Answer.id == ans_id))
            answer = res_ans.scalar_one_or_none()
            if answer:
                res_q = await session.execute(select(Question).where(Question.id == answer.question_id))
                question = res_q.scalar_one_or_none()
                if question and user_id and question.author_max_id and str(user_id) != str(question.author_max_id):
                    is_teacher_here = False
                    res_u = await session.execute(select(User).where(User.max_user_id == user_id))
                    u_obj = res_u.scalar_one_or_none()
                    if u_obj and u_obj.role in ("teacher", "admin"):
                        is_teacher_here = True
                    if not is_teacher_here:
                        try:
                            await event.ack(notification="Только автор вопроса может отклонить ответ")
                        except Exception:
                            pass
                        return

                if answer.status == "pending":
                    answer.status = "rejected"
                    await session.commit()

        try:
            await event.edit(
                text="Ответ отклонён. Вопрос остаётся открытым для других участников.",
                attachments=[],
                notification="Ответ отклонён",
            )
        except Exception:
            await event.ack(notification="Ответ отклонён")
        return

    is_teacher = False
    if user_id:
        async with async_session_factory() as session:
            res_user = await session.execute(select(User).where(User.max_user_id == user_id))
            u_check = res_user.scalar_one_or_none()
            if u_check and u_check.role in ("teacher", "admin"):
                is_teacher = True
            else:
                res_cm = await session.execute(
                    select(ChatMember).where(ChatMember.user_max_id == user_id, ChatMember.role == "teacher")
                )
                if res_cm.scalars().first():
                    is_teacher = True

    kb = build_main_menu_keyboard()

    if payload == "menu:ask_info":
        info_text = (
            f"Как работает взаимопомощь:\n\n"
            f"1. Добавьте бота в ваш учебный чат.\n"
            f"2. Чтобы задать вопрос классу, напишите в группе:\n/ask <текст вопроса>\n\n"
            f"3. Отвечайте реплаем (Reply) на сообщение с вопросом.\n"
            f"4. Автор подтверждает помощь кнопкой «Помог», и помощник получает +50 XP и +1 спасибку.\n\n"
            f"5. Команда /top в групповом чате показывает рейтинг помощников класса."
        )
        try:
            await event.edit(text=info_text, attachments=[kb.as_markup()])
        except Exception:
            await event.ack()

    elif payload == "menu:profile":
        async with async_session_factory() as session:
            res_user = await session.execute(select(User).where(User.max_user_id == user_id))
            u = res_user.scalar_one_or_none()
            rank_name = u.rank if u else "Любитель"
            xp_val = u.xp if u else 0
            active_balances, total_spasibki = await fetch_user_chat_balances(session, event.bot, user_id)

        profile_text = (
            f"Личный профиль:\n\n"
            f"Имя: {user_name}\n"
            f"Звание: {rank_name}\n"
            f"Опыт: {xp_val} XP\n"
            f"Всего спасибок: {total_spasibki}\n\n"
            f"Используйте кнопку «🪙 Баланс спасибок», чтобы посмотреть остаток по каждому чату отдельно, или веб-сервис Лиги Помощников."
        )
        try:
            await event.edit(text=profile_text, attachments=[kb.as_markup()])
        except Exception:
            await event.ack()

    elif payload == "menu:balance":
        async with async_session_factory() as session:
            active_balances, total_spasibki = await fetch_user_chat_balances(session, event.bot, user_id)

        if not active_balances:
            balance_text = (
                "🪙 Баланс спасибок:\n\n"
                "Вы пока не состоите в активных учебных чатах с начисленными спасибками.\n\n"
                "Помогайте одноклассникам в группах, отвечая на вопросы реплаем, чтобы заработать спасибки!"
            )
        else:
            lines = ["🪙 Ваш баланс спасибок по чатам:\n"]
            for title, bal in active_balances:
                lines.append(f"• «{title}»: {bal} спасибок")
            lines.append(f"\nВсего: {total_spasibki} спасибок")
            balance_text = "\n".join(lines)

        try:
            await event.edit(text=balance_text, attachments=[kb.as_markup()])
        except Exception:
            await event.ack()

    elif payload == "menu:top":
        top_text = (
            "Рейтинг участников доступен прямо в вашем учебном чате по команде /top или в веб-сервисе Лиги Помощников."
        )
        try:
            await event.edit(text=top_text, attachments=[kb.as_markup()])
        except Exception:
            await event.ack()

    elif payload == "menu:shop":
        shop_text = (
            "Лавка наград и обмен спасибок на бонусы от преподавателей доступны в веб-сервисе Лиги Помощников."
        )
        try:
            await event.edit(text=shop_text, attachments=[kb.as_markup()])
        except Exception:
            await event.ack()

    elif payload == "menu:teacher":
        teacher_text = (
            "Кабинет учителя доступен в веб-сервисе Лиги Помощников."
        )
        try:
            await event.edit(text=teacher_text, attachments=[kb.as_markup()])
        except Exception:
            await event.ack()

    else:
        try:
            await event.ack()
        except Exception:
            pass
