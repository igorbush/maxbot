from datetime import datetime, timezone
from typing import Any, Optional, Union
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.database.models import Answer, Chat, ChatMember, Question, User
from app.database.session import async_session_factory
from app.services.anti_cheat import AntiCheatService
from app.services.gamification import GamificationService
from app.services.max_client import (
    KeyboardBuilder,
    MaxBotClient,
    build_callback_button,
    build_link_button,
    build_main_menu_keyboard,
    build_question_keyboard,
    build_verification_keyboard,
    format_inline_keyboard,
    get_bot_client,
)

def to_int_id(val: Any) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s.startswith("-") and s[1:].isdigit():
        return -int(s[1:])
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits:
        val_int = int(digits)
        return -val_int if s.startswith("-") else val_int
    return None

def extract_display_name(sender: dict[str, Any], fallback_id: str = "") -> str:
    first = (sender.get("first_name") or "").strip()
    last = (sender.get("last_name") or "").strip()
    if first and last:
        return f"{first} {last}"
    if first:
        return first
    name = (sender.get("name") or "").strip()
    if name:
        return name
    username = (sender.get("username") or "").strip()
    if username:
        return f"@{username}"
    return "Одноклассник"

class BotService:
    def __init__(self, client: Optional[MaxBotClient] = None) -> None:
        self.client = client or get_bot_client()

    async def ensure_user(
        self,
        session: AsyncSession,
        max_user_id: Union[int, str],
        sender: Optional[dict[str, Any]] = None,
        default_role: str = "student",
    ) -> User:
        uid_str = str(max_user_id).strip()
        sender_dict = sender or {}
        new_name = extract_display_name(sender_dict, uid_str)

        stmt = select(User).where(User.max_user_id == uid_str)
        res = await session.execute(stmt)
        user = res.scalars().first()

        if user is None:
            user = User(
                max_user_id=uid_str,
                display_name=new_name,
                role=default_role,
                balance_spasibki=0,
                xp=0,
                rank="Новичок",
            )
            session.add(user)
            await session.flush()
        else:
            if new_name != "Одноклассник" and (user.display_name == "Одноклассник" or user.display_name.startswith("Ученик")):
                user.display_name = new_name
                await session.flush()

        return user

    async def ensure_chat(
        self,
        session: AsyncSession,
        chat_id: Union[int, str],
        client: MaxBotClient,
    ) -> Chat:
        cid_str = str(chat_id).strip()
        stmt = select(Chat).where(Chat.max_chat_id == cid_str)
        res = await session.execute(stmt)
        chat = res.scalars().first()

        if chat is None:
            title = "Чат класса"
            owner_id = None
            try:
                chat_data = await client.get_chat(chat_id)
                if isinstance(chat_data, dict):
                    title = chat_data.get("title") or title
                    if chat_data.get("owner_id"):
                        owner_id = str(chat_data.get("owner_id"))
            except Exception:
                pass

            chat = Chat(
                max_chat_id=cid_str,
                title=title,
                owner_id=owner_id,
            )
            session.add(chat)
            await session.flush()

        return chat

    async def check_and_update_membership(
        self,
        session: AsyncSession,
        chat: Chat,
        user: User,
    ) -> str:
        is_owner = (chat.owner_id and str(user.max_user_id) == str(chat.owner_id))

        stmt = select(ChatMember).where(
            ChatMember.chat_max_id == chat.max_chat_id,
            ChatMember.user_max_id == user.max_user_id,
        )
        res = await session.execute(stmt)
        member = res.scalars().first()

        assigned_role = "teacher" if is_owner else "student"

        if member is None:
            member = ChatMember(
                chat_max_id=chat.max_chat_id,
                user_max_id=user.max_user_id,
                role=assigned_role,
            )
            session.add(member)
            await session.flush()
        elif is_owner and member.role != "teacher":
            member.role = "teacher"
            await session.flush()

        if is_owner and user.role != "teacher":
            user.role = "teacher"
            await session.flush()

        return member.role

    async def handle_ask_command(
        self,
        session: AsyncSession,
        message: dict[str, Any],
        client: MaxBotClient,
    ) -> None:
        settings = get_settings()
        recipient = message.get("recipient", {})
        chat_type = recipient.get("chat_type")
        raw_chat_id = message.get("chat_id") or recipient.get("chat_id")
        sender = message.get("sender", {})
        raw_sender_id = str(sender.get("user_id", ""))

        user = await self.ensure_user(session, raw_sender_id, sender=sender)
        sender_name = user.display_name

        raw_text = (
            message.get("body", {}).get("text")
            if isinstance(message.get("body"), dict)
            else None
        ) or message.get("text") or ""
        raw_text = raw_text.strip()
        parts = raw_text.split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            target_uid = to_int_id(raw_sender_id) or raw_sender_id
            await client.send_message(
                user_id=target_uid,
                text="ℹ️ Чтобы задать вопрос классу, укажите его текст:\n`/ask Как решить задачу №5 по геометрии?`",
            )
            return

        question_text = parts[1].strip()

        chat_title = "Чат класса"
        if raw_chat_id and chat_type != "dialog":
            chat = await self.ensure_chat(session, raw_chat_id, client)
            await self.check_and_update_membership(session, chat, user)
            chat_title = chat.title

        webapp_url = f"{settings.WEBAPP_BASE_URL.rstrip('/')}/?user_id={user.max_user_id}"
        keyboard = build_question_keyboard(webapp_url)

        announcement = (
            f"❓ Вопрос от {sender_name}:\n"
            f"«{question_text}»\n\n"
            f"👉 Ответьте реплаем (ответом) на это сообщение, чтобы помочь однокласснику! "
            f"За полезный ответ вы получите +50 XP и +1 спасибку 🪙."
        )

        target_chat_id = to_int_id(raw_chat_id) or raw_chat_id
        target_uid = to_int_id(raw_sender_id) or raw_sender_id

        if target_chat_id and target_chat_id != 0 and chat_type != "dialog" and target_chat_id != target_uid:
            resp = await client.send_message(chat_id=target_chat_id, text=announcement, attachments=keyboard)
            group_cid = str(target_chat_id)
        else:
            resp = await client.send_message(user_id=target_uid, text=announcement, attachments=keyboard)
            group_cid = str(target_uid)

        bot_msg = resp.get("message", {})
        bot_mid = (
            bot_msg.get("body", {}).get("mid")
            if isinstance(bot_msg.get("body"), dict)
            else None
        ) or bot_msg.get("id") or bot_msg.get("mid") or ""

        question = Question(
            group_chat_id=group_cid,
            group_chat_title=chat_title,
            group_message_id=str(bot_mid),
            author_max_id=user.max_user_id,
            author_name=sender_name,
            text=question_text,
            status="open",
        )
        session.add(question)
        await session.flush()
        await GamificationService.evaluate_achievements(session, user.max_user_id)
        await session.commit()

    async def handle_reply_message(
        self,
        session: AsyncSession,
        message: dict[str, Any],
        client: MaxBotClient,
        reply_to_mid: str,
    ) -> None:
        recipient = message.get("recipient", {})
        chat_type = recipient.get("chat_type")
        raw_chat_id = message.get("chat_id") or recipient.get("chat_id")
        sender = message.get("sender", {})
        raw_sender_id = str(sender.get("user_id", ""))

        user = await self.ensure_user(session, raw_sender_id, sender=sender)
        sender_name = user.display_name

        stmt = select(Question).where(
            Question.group_message_id == str(reply_to_mid),
            Question.status == "open",
        )
        res = await session.execute(stmt)
        question = res.scalar_one_or_none()
        if question is None:
            return

        is_same_author = (
            str(question.author_max_id).strip().lower() == user.max_user_id.strip().lower()
            or str(question.author_max_id).strip().lower() == raw_sender_id.strip().lower()
            or to_int_id(question.author_max_id) == to_int_id(raw_sender_id)
        )
        target_chat = to_int_id(raw_chat_id) or raw_chat_id
        target_uid = to_int_id(raw_sender_id) or raw_sender_id

        if is_same_author or not AntiCheatService.validate_answer_eligibility(question.author_max_id, user.max_user_id):
            reject_text = f"⚠️ {sender_name}, нельзя отвечать на собственный вопрос в Лиге Помощников."
            if target_chat and target_chat != 0 and chat_type != "dialog" and target_chat != target_uid:
                await client.send_message(chat_id=target_chat, text=reject_text)
            else:
                await client.send_message(user_id=target_uid, text=reject_text)
            return

        incoming_mid = (
            message.get("body", {}).get("mid")
            if isinstance(message.get("body"), dict)
            else None
        ) or message.get("id") or message.get("mid") or ""
        answer_text = (
            message.get("body", {}).get("text")
            if isinstance(message.get("body"), dict)
            else None
        ) or message.get("text") or ""

        answer = Answer(
            question_id=question.id,
            author_max_id=user.max_user_id,
            author_name=sender_name,
            group_message_id=str(incoming_mid),
            text=answer_text,
            status="pending",
        )
        session.add(answer)
        await session.flush()

        keyboard = KeyboardBuilder.question_verification_keyboard(answer.id)
        author_target_uid = to_int_id(question.author_max_id)

        chat_label = f" в «{question.group_chat_title}»" if question.group_chat_title else ""
        dm_resp = await client.send_message(
            user_id=author_target_uid,
            text=(
                f"📬 {sender_name} ответил на ваш вопрос{chat_label}:\n"
                f"«{answer_text}»\n\n"
                f"Помог ли этот ответ разобраться?"
            ),
            attachments=keyboard,
        )
        dm_msg = dm_resp.get("message", {})
        dm_mid = (
            dm_msg.get("body", {}).get("mid")
            if isinstance(dm_msg.get("body"), dict)
            else None
        ) or dm_msg.get("id") or dm_msg.get("mid")
        if dm_mid:
            answer.dm_approval_message_id = str(dm_mid)
        await session.commit()

    async def handle_manage_command(
        self,
        session: AsyncSession,
        message: dict[str, Any],
        client: MaxBotClient,
    ) -> None:
        settings = get_settings()
        recipient = message.get("recipient", {})
        chat_type = recipient.get("chat_type")
        raw_chat_id = message.get("chat_id") or recipient.get("chat_id")
        sender = message.get("sender", {})
        raw_sender_id = str(sender.get("user_id", ""))

        user = await self.ensure_user(session, raw_sender_id, sender=sender)
        target_uid = to_int_id(raw_sender_id)
        target_chat = to_int_id(raw_chat_id) or raw_chat_id
        is_group = target_chat and target_chat != 0 and chat_type != "dialog" and target_chat != target_uid

        if raw_chat_id and chat_type != "dialog":
            chat = await self.ensure_chat(session, raw_chat_id, client)
            await self.check_and_update_membership(session, chat, user)

        if user.role not in ("teacher", "admin"):
            err_text = "⛔ Панель управления доступна создателям и учителям классов."
            if is_group:
                await client.send_message(chat_id=target_chat, text=err_text)
            else:
                await client.send_message(user_id=target_uid, text=err_text)
            return

        base_url = settings.WEBAPP_BASE_URL.rstrip("/")
        webapp_url = f"{base_url}/?user_id={user.max_user_id}"
        keyboard = KeyboardBuilder.teacher_menu_keyboard(webapp_url)
        menu_text = f"👨‍🏫 Кабинет учителя для {user.display_name}:\nУправляйте лавкой наград, подтверждайте заявки и поощряйте учеников:"
        if is_group:
            await client.send_message(chat_id=target_chat, text=menu_text, attachments=keyboard)
        else:
            await client.send_message(user_id=target_uid, text=menu_text, attachments=keyboard)

    async def handle_message_callback(
        self,
        session: AsyncSession,
        callback: dict[str, Any],
        client: MaxBotClient,
    ) -> None:
        settings = get_settings()
        callback_id = str(callback.get("callback_id", ""))
        payload = str(callback.get("payload", "")).strip()
        user_info = callback.get("user", {})
        raw_user_id = str(user_info.get("user_id", ""))

        user = await self.ensure_user(session, raw_user_id, sender=user_info)
        webapp_url = f"{settings.WEBAPP_BASE_URL.rstrip('/')}/?user_id={user.max_user_id}"

        if payload.startswith("menu:"):
            action = payload.replace("menu:", "")
            if action == "ask_info":
                info_text = (
                    "📌 Как задать вопрос:\n\n"
                    "1. В чате вашего класса напишите команду:\n"
                    "`/ask <текст вопроса>`\n\n"
                    "2. Например:\n"
                    "`/ask Ребята, как решить №12 по алгебре?`\n\n"
                    "3. Одноклассники увидят вопрос и ответят вам реплаем."
                )
                kb = format_inline_keyboard([[build_link_button("📱 Открыть Сферум", url=webapp_url)]])
                await client.answer_callback(callback_id=callback_id, notification="Инструкция по вопросу")
                await client.send_message(user_id=to_int_id(user.max_user_id), text=info_text, attachments=kb)
                return

            if action == "how_to_answer":
                info_text = (
                    "💡 Как помочь однокласснику:\n\n"
                    "1. Нажмите «Ответить» (Reply) на сообщение бота с вопросом.\n"
                    "2. Напишите понятное решение или объяснение задачи.\n"
                    "3. Автор подтвердит ответ, и вам начислятся +50 XP и +1 спасибка 🪙!"
                )
                await client.answer_callback(callback_id=callback_id, notification="Как ответить")
                await client.send_message(user_id=to_int_id(user.max_user_id), text=info_text)
                return

            if action == "profile":
                h_res = await session.execute(
                    select(Answer).where(Answer.author_max_id == user.max_user_id, Answer.status == "accepted")
                )
                helped_cnt = len(h_res.scalars().all())

                q_res = await session.execute(
                    select(Question).where(Question.author_max_id == user.max_user_id)
                )
                q_cnt = len(q_res.scalars().all())

                prof_text = (
                    f"👤 Профиль: {user.display_name}\n"
                    f"🎖 Звание: {user.rank}\n"
                    f"⭐️ Опыт: {user.xp} XP\n"
                    f"🪙 Баланс: {user.balance_spasibki} спасибок\n"
                    f"🤝 Помог классу: {helped_cnt} раз\n"
                    f"❓ Задал вопросов: {q_cnt}"
                )
                kb = format_inline_keyboard([[build_link_button("📱 Открыть в Сферуме", url=webapp_url)]])
                await client.answer_callback(callback_id=callback_id, notification="Профиль обновлён")
                await client.send_message(user_id=to_int_id(user.max_user_id), text=prof_text, attachments=kb)
                return

            if action == "top":
                top_res = await session.execute(
                    select(User).where(User.role == "student").order_by(User.xp.desc()).limit(5)
                )
                leaders = top_res.scalars().all()
                lines = ["🏆 Топ помощников школы:\n"]
                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                for idx, s in enumerate(leaders):
                    m = medals[idx] if idx < len(medals) else f"#{idx+1}"
                    lines.append(f"{m} {s.display_name} — {s.xp} XP (🪙 {s.balance_spasibki})")
                top_text = "\n".join(lines)
                kb = format_inline_keyboard([[build_link_button("📱 Полная доска почёта", url=webapp_url)]])
                await client.answer_callback(callback_id=callback_id, notification="Доска почёта")
                await client.send_message(user_id=to_int_id(user.max_user_id), text=top_text, attachments=kb)
                return

            if action == "shop":
                shop_text = (
                    f"🎁 Школьная лавка наград\n\n"
                    f"Ваш текущий баланс: {user.balance_spasibki} спасибок 🪙\n\n"
                    f"В лавке доступны награды от учителей: освобождение от ДЗ, выбор соседа по парте и другие бонусы."
                )
                kb = format_inline_keyboard([[build_link_button("🛍 Перейти в лавку", url=webapp_url)]])
                await client.answer_callback(callback_id=callback_id, notification="Лавка наград")
                await client.send_message(user_id=to_int_id(user.max_user_id), text=shop_text, attachments=kb)
                return

            if action == "teacher":
                teacher_text = (
                    f"🎓 Кабинет учителя\n\n"
                    f"Здравствуйте, {user.display_name}! В веб-кабинете вы можете проверять заявки на награды и поощрять активных учеников."
                )
                kb = format_inline_keyboard([[build_link_button("👨‍🏫 Открыть кабинет", url=webapp_url)]])
                await client.answer_callback(callback_id=callback_id, notification="Кабинет учителя")
                await client.send_message(user_id=to_int_id(user.max_user_id), text=teacher_text, attachments=kb)
                return

        answer_id: Optional[int] = None
        decision: Optional[str] = None

        if payload.startswith("verify_help:"):
            parts = payload.split(":")
            if len(parts) >= 3 and parts[1].isdigit():
                answer_id = int(parts[1])
                decision = parts[2]

        if answer_id is None or decision not in ("yes", "no"):
            return

        ans_stmt = select(Answer).where(Answer.id == answer_id)
        ans_res = await session.execute(ans_stmt)
        answer = ans_res.scalar_one_or_none()
        if answer is None:
            await client.answer_callback(callback_id=callback_id, notification="Ответ не найден")
            return

        if answer.status != "pending":
            await client.answer_callback(callback_id=callback_id, notification="Ответ уже подтверждён ранее")
            return

        q_stmt = select(Question).where(Question.id == answer.question_id)
        q_res = await session.execute(q_stmt)
        question = q_res.scalar_one_or_none()
        if question is None:
            await client.answer_callback(callback_id=callback_id, notification="Вопрос не найден")
            return

        is_author = (
            str(question.author_max_id).strip().lower() == user.max_user_id.strip().lower()
            or str(question.author_max_id).strip().lower() == raw_user_id.strip().lower()
            or to_int_id(question.author_max_id) == to_int_id(raw_user_id)
        )
        if not is_author:
            await client.answer_callback(
                callback_id=callback_id,
                notification="Только автор вопроса может подтвердить ответ!",
            )
            return

        helper_uid = to_int_id(answer.author_max_id)
        group_cid = to_int_id(question.group_chat_id) or question.group_chat_id
        helper_name = answer.author_name or "Одноклассник"

        if decision == "yes":
            spasibki, xp = await GamificationService.award_gratitude(session, question, answer)
            await client.answer_callback(
                callback_id=callback_id,
                notification="Благодарность отправлена!",
                message={"text": f"✅ Вы подтвердили, что ответ от {helper_name} помог! Вопрос успешно закрыт."},
            )

            helper_res = await session.execute(select(User).where(User.max_user_id == answer.author_max_id))
            helper_user = helper_res.scalar_one_or_none()
            h_balance = helper_user.balance_spasibki if helper_user else 1

            helper_kb = format_inline_keyboard([
                [build_link_button("📱 Посмотреть баланс", url=f"{settings.WEBAPP_BASE_URL.rstrip('/')}/?user_id={answer.author_max_id}")]
            ])

            await client.send_message(
                user_id=helper_uid,
                text=(
                    f"🎉 {user.display_name} подтвердил(а), что ваш ответ помог!\n\n"
                    f"Вам начислено: +{spasibki} спасибка 🪙 и +{xp} XP ⭐️!\n"
                    f"Текущий баланс: {h_balance} спасибок."
                ),
                attachments=helper_kb,
            )

            if group_cid and str(group_cid).strip() != "0" and to_int_id(group_cid) != helper_uid:
                await client.send_message(
                    chat_id=group_cid,
                    text=f"🎉 Вопрос закрыт! Спасибо {helper_name} за помощь для {user.display_name}! 👏",
                )
        else:
            answer.status = "rejected"
            await session.commit()
            await client.answer_callback(
                callback_id=callback_id,
                notification="Ответ отмечен как неподошедший",
                message={"text": f"Принято. Вопрос остаётся открытым для других одноклассников."},
            )
            await client.send_message(
                user_id=helper_uid,
                text=f"{user.display_name} отметил(а), что ответ не полностью помог решить задачу, но спасибо за участие!",
            )

    async def handle_bot_started(
        self,
        session: AsyncSession,
        update: dict[str, Any],
        client: MaxBotClient,
    ) -> None:
        settings = get_settings()
        user_info = update.get("user", {})
        uid = str(user_info.get("user_id", ""))
        user = await self.ensure_user(session, uid, sender=user_info)
        chat_id = update.get("chat_id")
        user_target = to_int_id(uid)
        c_id = to_int_id(chat_id)

        webapp_url = f"{settings.WEBAPP_BASE_URL.rstrip('/')}/?user_id={user.max_user_id}"
        keyboard = build_main_menu_keyboard(webapp_url, is_teacher=(user.role in ("teacher", "admin")))

        welcome_text = (
            f"Привет, {user.display_name}! 🎓\n\n"
            f"Добро пожаловать в Лигу Помощников Сферума!\n"
            f"Здесь одноклассники помогают друг другу с домашкой, копят опыт, открывают звания и обменивают спасибки на школьные награды.\n\n"
            f"Выберите действие с помощью кнопок ниже:"
        )

        if c_id and c_id != 0 and c_id != user_target:
            await client.send_message(chat_id=c_id, text=welcome_text, attachments=keyboard)
        else:
            await client.send_message(user_id=user_target, text=welcome_text, attachments=keyboard)

    async def handle_message_created(
        self,
        session: AsyncSession,
        message: dict[str, Any],
        client: MaxBotClient,
    ) -> None:
        settings = get_settings()
        raw_text = (
            message.get("body", {}).get("text")
            if isinstance(message.get("body"), dict)
            else None
        ) or message.get("text") or ""
        text = raw_text.strip()

        recipient = message.get("recipient", {})
        chat_type = recipient.get("chat_type")
        raw_chat_id = message.get("chat_id") or recipient.get("chat_id")
        sender = message.get("sender", {})
        raw_sender_id = str(sender.get("user_id", ""))

        user = await self.ensure_user(session, raw_sender_id, sender=sender)

        if raw_chat_id and chat_type != "dialog":
            chat = await self.ensure_chat(session, raw_chat_id, client)
            await self.check_and_update_membership(session, chat, user)

        if text.startswith("/ask"):
            await self.handle_ask_command(session, message, client)
            return

        if text.startswith("/manage"):
            await self.handle_manage_command(session, message, client)
            return

        if text.startswith(("/start", "/help", "/menu")) or text.lower() in ("привет", "здравствуйте", "помощь", "меню", "хелп", "start", "help", "menu"):
            target_chat = to_int_id(raw_chat_id) or raw_chat_id
            target_uid = to_int_id(raw_sender_id)
            webapp_url = f"{settings.WEBAPP_BASE_URL.rstrip('/')}/?user_id={user.max_user_id}"
            keyboard = build_main_menu_keyboard(webapp_url, is_teacher=(user.role in ("teacher", "admin")))

            help_text = (
                f"👋 Привет, {user.display_name}! Я бот «Лига Помощников» Сферума 🎓\n\n"
                f"📌 Как работает бот:\n"
                f"• В чате класса спросите: `/ask <текст вопроса>`\n"
                f"• Отвечайте реплаем (ответом) на вопросы друзей, чтобы помочь\n"
                f"• Автор подтвердит ответ, и вы получите +50 XP и +1 спасибку 🪙\n\n"
                f"Выберите раздел в меню:"
            )

            if target_chat and target_chat != 0 and chat_type != "dialog" and target_chat != target_uid:
                await client.send_message(chat_id=target_chat, text=help_text, attachments=keyboard)
            else:
                await client.send_message(user_id=target_uid, text=help_text, attachments=keyboard)
            return

        reply_to_mid = None
        if "reply_to" in message and message["reply_to"]:
            rt = message["reply_to"]
            if isinstance(rt, dict):
                reply_to_mid = rt.get("id") or rt.get("mid")
            else:
                reply_to_mid = str(rt)
        elif "link" in message and isinstance(message["link"], dict):
            link = message["link"]
            reply_to_mid = link.get("id") or link.get("mid")
            if not reply_to_mid and "message" in link and isinstance(link["message"], dict):
                reply_to_mid = link["message"].get("mid") or link["message"].get("id")

        if reply_to_mid:
            await self.handle_reply_message(session, message, client, str(reply_to_mid))

    async def dispatch(
        self,
        session: AsyncSession,
        update: dict[str, Any],
        client: Optional[MaxBotClient] = None,
    ) -> None:
        active_client = client or self.client
        utype = update.get("update_type")
        if utype == "message_created":
            await self.handle_message_created(session, update.get("message", {}), active_client)
        elif utype == "message_callback":
            await self.handle_message_callback(session, update.get("callback", {}), active_client)
        elif utype == "bot_started":
            await self.handle_bot_started(session, update, active_client)

default_bot_service = BotService()

async def handle_update(
    arg1: Any = None,
    arg2: Any = None,
    *,
    session: Optional[AsyncSession] = None,
    update: Optional[dict[str, Any]] = None,
    client: Optional[MaxBotClient] = None,
) -> None:
    target_session: Optional[AsyncSession] = session
    target_update: Optional[dict[str, Any]] = update

    if isinstance(arg1, AsyncSession):
        target_session = arg1
        if isinstance(arg2, dict):
            target_update = arg2
    elif isinstance(arg1, dict):
        target_update = arg1
        if isinstance(arg2, AsyncSession):
            target_session = arg2

    if target_update is None:
        return

    active_client = client or get_bot_client()

    if target_session is not None:
        await default_bot_service.dispatch(target_session, target_update, client=active_client)
    else:
        async with async_session_factory() as new_session:
            await default_bot_service.dispatch(new_session, target_update, client=active_client)
