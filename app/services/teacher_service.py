from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import (
    Achievement,
    Answer,
    AuditLog,
    Chat,
    ChatMember,
    Question,
    Reward,
    RewardClaim,
    User,
    UserAchievement,
)
from app.services.gamification import GamificationService

class TeacherService:
    @staticmethod
    async def _require_teacher(session: AsyncSession, teacher_max_id: str) -> User:
        user_res = await session.execute(
            select(User).where(User.max_user_id == teacher_max_id)
        )
        teacher = user_res.scalar_one_or_none()
        if teacher is None:
            raise PermissionError("Teacher user not found")
        if teacher.role not in ("teacher", "admin"):
            member_res = await session.execute(
                select(ChatMember).where(ChatMember.user_max_id == teacher_max_id, ChatMember.role == "teacher")
            )
            if member_res.scalars().first() is None:
                raise PermissionError("Only teachers or administrators can perform this action")
        return teacher

    @classmethod
    async def claim_reward(
        cls,
        session: AsyncSession,
        student_max_id: str,
        reward_id: int,
        chat_id: Optional[str] = None,
    ) -> RewardClaim:
        student_res = await session.execute(
            select(User).where(User.max_user_id == student_max_id)
        )
        student = student_res.scalar_one_or_none()
        if student is None:
            raise ValueError("Student not found")

        reward_res = await session.execute(
            select(Reward).where(Reward.id == reward_id)
        )
        reward = reward_res.scalar_one_or_none()
        if reward is None:
            raise ValueError("Reward not found")
        if not reward.is_active:
            raise ValueError("Reward is inactive")

        if reward.created_by_teacher_id and str(reward.created_by_teacher_id) == str(student_max_id):
            raise ValueError("Преподаватель не может обменивать созданные им награды")

        target_chat = chat_id or reward.chat_id
        member = None
        if target_chat:
            mem_res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_max_id == target_chat,
                    ChatMember.user_max_id == student_max_id,
                )
            )
            member = mem_res.scalar_one_or_none()
            if member is None:
                raise ValueError("Вы не являетесь участником этого чата")

        current_balance = member.balance_spasibki if member is not None else student.balance_spasibki
        if current_balance < reward.cost_spasibki:
            raise ValueError(f"Недостаточно спасибок в этом чате (у вас {current_balance})")

        if member is not None:
            member.balance_spasibki -= reward.cost_spasibki
        student.balance_spasibki = max(0, student.balance_spasibki - reward.cost_spasibki)

        claim = RewardClaim(
            reward_id=reward.id,
            student_max_id=student_max_id,
            chat_id=target_chat,
            status="requested",
            created_at=datetime.now(timezone.utc),
        )
        session.add(claim)
        await session.flush()

        audit = AuditLog(
            actor_max_id=student_max_id,
            target_user_max_id=student_max_id,
            target_type="reward_claim",
            target_id=str(claim.id),
            action="claim_reward",
            details=f"reward_id={reward.id},cost={reward.cost_spasibki}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(audit)
        await session.commit()
        return claim

    @classmethod
    async def review_reward_claim(
        cls,
        session: AsyncSession,
        teacher_max_id: str,
        claim_id: int,
        decision: str,
    ) -> RewardClaim:
        await cls._require_teacher(session, teacher_max_id)

        claim_res = await session.execute(
            select(RewardClaim).where(RewardClaim.id == claim_id)
        )
        claim = claim_res.scalar_one_or_none()
        if claim is None:
            raise ValueError("Reward claim not found")
        if claim.status != "requested":
            raise ValueError("Reward claim is already processed")
        if claim.student_max_id and str(claim.student_max_id) == str(teacher_max_id):
            raise ValueError("Преподаватель не может рассматривать собственные заявки")

        if decision not in ("approved", "rejected", "approve", "reject"):
            raise ValueError("Invalid decision status")

        normalized = "approved" if decision in ("approved", "approve") else "rejected"
        claim.status = normalized

        if normalized == "rejected":
            rew_res = await session.execute(
                select(Reward).where(Reward.id == claim.reward_id)
            )
            reward = rew_res.scalar_one_or_none()
            if reward is not None:
                if claim.chat_id:
                    mem_res = await session.execute(
                        select(ChatMember).where(
                            ChatMember.chat_max_id == claim.chat_id,
                            ChatMember.user_max_id == claim.student_max_id,
                        )
                    )
                    mem = mem_res.scalar_one_or_none()
                    if mem is not None:
                        mem.balance_spasibki += reward.cost_spasibki
                stu_res = await session.execute(
                    select(User).where(User.max_user_id == claim.student_max_id)
                )
                student = stu_res.scalar_one_or_none()
                if student is not None:
                    student.balance_spasibki += reward.cost_spasibki

        audit = AuditLog(
            actor_max_id=teacher_max_id,
            target_user_max_id=claim.student_max_id,
            target_type="reward_claim",
            target_id=str(claim.id),
            action=f"review_reward_{normalized}",
            details=f"claim_id={claim.id},decision={normalized}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(audit)
        await session.commit()
        return claim

    @classmethod
    async def adjust_student_balance(
        cls,
        session: AsyncSession,
        teacher_max_id: str,
        student_max_id: str,
        delta_spasibki: int,
        delta_xp: int = 0,
        reason: str = "",
        chat_id: Optional[str] = None,
    ) -> User:
        await cls._require_teacher(session, teacher_max_id)

        stu_res = await session.execute(
            select(User).where(User.max_user_id == student_max_id)
        )
        student = stu_res.scalar_one_or_none()
        if student is None:
            raise ValueError("Student not found")

        if chat_id:
            mem_res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_max_id == chat_id,
                    ChatMember.user_max_id == student_max_id,
                )
            )
            mem = mem_res.scalar_one_or_none()
            if mem is not None:
                mem.balance_spasibki = max(0, mem.balance_spasibki + delta_spasibki)

        student.balance_spasibki = max(0, student.balance_spasibki + delta_spasibki)
        student.xp = max(0, student.xp + delta_xp)
        student.rank = GamificationService.calculate_rank(student.xp)

        audit = AuditLog(
            actor_max_id=teacher_max_id,
            target_user_max_id=student_max_id,
            target_type="user",
            target_id=student_max_id,
            action="adjust_balance",
            details=f"delta_spasibki={delta_spasibki},delta_xp={delta_xp},reason={reason},chat_id={chat_id}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(audit)
        await session.commit()
        return student

    @classmethod
    async def create_reward(
        cls,
        session: AsyncSession,
        teacher_max_id: str,
        title: str,
        description: str,
        cost_spasibki: int,
        chat_id: Optional[str] = None,
    ) -> Reward:
        await cls._require_teacher(session, teacher_max_id)

        reward = Reward(
            created_by_teacher_id=teacher_max_id,
            chat_id=chat_id,
            title=title,
            description=description,
            cost_spasibki=cost_spasibki,
            is_active=True,
        )
        session.add(reward)
        await session.flush()

        audit = AuditLog(
            actor_max_id=teacher_max_id,
            target_user_max_id=None,
            target_type="reward",
            target_id=str(reward.id),
            action="create_reward",
            details=f"title={title},cost={cost_spasibki},chat_id={chat_id}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(audit)
        await session.commit()
        return reward

    @classmethod
    async def delete_reward(
        cls,
        session: AsyncSession,
        teacher_max_id: str,
        reward_id: int,
    ) -> bool:
        await cls._require_teacher(session, teacher_max_id)

        rew_res = await session.execute(
            select(Reward).where(Reward.id == reward_id)
        )
        reward = rew_res.scalar_one_or_none()
        if reward is None:
            raise ValueError("Награда не найдена")

        reward.is_active = False
        audit = AuditLog(
            actor_max_id=teacher_max_id,
            target_user_max_id=None,
            target_type="reward",
            target_id=str(reward.id),
            action="delete_reward",
            details=f"reward_id={reward_id},title={reward.title}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(audit)
        await session.commit()
        return True

    @classmethod
    async def get_teacher_overview(
        cls,
        session: AsyncSession,
        teacher_max_id: str,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await cls._require_teacher(session, teacher_max_id)

        if not chat_id or chat_id == "all":
            return {
                "pending_claims": [],
                "active_questions": [],
                "total_students": 0,
                "issued_rewards": [],
                "class_pulse": {
                    "total_questions_week": 0,
                    "resolved_questions_week": 0,
                    "resolution_rate": 0,
                    "top_helper_name": "—",
                    "time_saved_hours": 0.0,
                },
            }

        claims_query = (
            select(RewardClaim, Reward, User)
            .join(Reward, RewardClaim.reward_id == Reward.id)
            .join(User, RewardClaim.student_max_id == User.max_user_id)
            .where(
                RewardClaim.status == "requested",
                RewardClaim.chat_id == chat_id,
                RewardClaim.student_max_id != teacher_max_id,
            )
            .order_by(RewardClaim.created_at.desc())
        )

        claims_res = await session.execute(claims_query)
        pending_claims = [
            {
                "claim_id": c.id,
                "reward_id": r.id,
                "reward_title": r.title,
                "cost_spasibki": r.cost_spasibki,
                "student_max_id": u.max_user_id,
                "student_name": u.display_name,
                "chat_id": c.chat_id or r.chat_id,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c, r, u in claims_res.all()
        ]

        q_query = (
            select(Question, User)
            .join(User, Question.author_max_id == User.max_user_id)
            .where(Question.status == "open", Question.group_chat_id == chat_id)
            .order_by(Question.created_at.desc())
            .limit(20)
        )

        q_res = await session.execute(q_query)
        active_questions = [
            {
                "id": q.id,
                "author_name": u.display_name,
                "author_max_id": u.max_user_id,
                "text": q.text,
                "subject": q.subject,
                "chat_title": q.group_chat_title,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q, u in q_res.all()
        ]

        students_query = (
            select(func.count(ChatMember.id))
            .where(
                ChatMember.chat_max_id == chat_id,
                ChatMember.role != "teacher",
                ChatMember.user_max_id != teacher_max_id,
            )
        )
        students_count_res = await session.execute(students_query)
        total_students = students_count_res.scalar_one() or 0

        issued_query = (
            select(RewardClaim, Reward, User)
            .join(Reward, RewardClaim.reward_id == Reward.id)
            .join(User, RewardClaim.student_max_id == User.max_user_id)
            .where(
                RewardClaim.status == "approved",
                RewardClaim.chat_id == chat_id,
                RewardClaim.student_max_id != teacher_max_id,
            )
            .order_by(RewardClaim.created_at.desc())
            .limit(25)
        )

        issued_res = await session.execute(issued_query)
        issued_rewards = [
            {
                "id": f"claim_{c.id}",
                "student_name": u.display_name,
                "reward_title": r.title,
                "cost_spasibki": r.cost_spasibki,
                "date": c.created_at.strftime("%d.%m %H:%M") if c.created_at else "",
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c, r, u in issued_res.all()
        ]

        choice_query = (
            select(AuditLog, User)
            .join(User, AuditLog.target_user_max_id == User.max_user_id)
            .where(
                AuditLog.actor_max_id == teacher_max_id,
                AuditLog.action == "adjust_balance",
                AuditLog.details.like(f"%chat_id={chat_id}%"),
                AuditLog.target_user_max_id != teacher_max_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(15)
        )
        choice_query = choice_query.order_by(AuditLog.created_at.desc()).limit(15)

        choice_res = await session.execute(choice_query)
        for log, u in choice_res.all():
            issued_rewards.append({
                "id": f"choice_{log.id}",
                "student_name": u.display_name,
                "reward_title": "⭐️ Выбор учителя (+20 спасибок)",
                "cost_spasibki": 20,
                "date": log.created_at.strftime("%d.%m %H:%M") if log.created_at else "",
                "created_at": log.created_at.isoformat() if log.created_at else "",
            })

        issued_rewards.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        class_pulse = await cls.get_class_pulse(session, chat_id)

        return {
            "pending_claims": pending_claims,
            "active_questions": active_questions,
            "total_students": total_students,
            "issued_rewards": issued_rewards,
            "class_pulse": class_pulse,
        }

    @classmethod
    async def get_class_pulse(cls, session: AsyncSession, chat_id: Optional[str]) -> Dict[str, Any]:
        since_week = datetime.now(timezone.utc) - timedelta(days=7)
        if not chat_id or chat_id == "all":
            chat_cond = True
        else:
            chat_cond = (Question.group_chat_id == chat_id)

        total_q_week_query = select(func.count(Question.id)).where(
            chat_cond,
            Question.created_at >= since_week,
        )
        total_q_week = (await session.execute(total_q_week_query)).scalar_one() or 0

        resolved_q_week_query = select(func.count(Question.id)).where(
            chat_cond,
            Question.status == "resolved",
            Question.created_at >= since_week,
        )
        resolved_q_week = (await session.execute(resolved_q_week_query)).scalar_one() or 0

        resolution_rate = int((resolved_q_week / total_q_week) * 100) if total_q_week > 0 else (100 if resolved_q_week > 0 else 0)

        top_helper_query = (
            select(User.display_name, func.count(Answer.id).label("cnt"))
            .join(Answer, Answer.author_max_id == User.max_user_id)
            .join(Question, Answer.question_id == Question.id)
            .where(
                chat_cond,
                Answer.status == "accepted",
                Answer.created_at >= since_week,
                User.role != "teacher",
            )
            .group_by(User.id)
            .order_by(func.count(Answer.id).desc())
            .limit(1)
        )
        top_helper_row = (await session.execute(top_helper_query)).first()
        top_helper_name = top_helper_row[0] if top_helper_row else "—"

        return {
            "total_questions_week": total_q_week,
            "resolved_questions_week": resolved_q_week,
            "resolution_rate": resolution_rate,
            "top_helper_name": top_helper_name,
            "time_saved_hours": round(resolved_q_week * 0.25, 1),
        }
