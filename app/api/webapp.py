from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, not_, or_, select
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
from app.database.session import get_db_session
from app.services.auth import get_current_user, require_teacher
from app.services.teacher_service import TeacherService
from app.services.gamification import GamificationService
from app.services.bot_service import send_chat_notification

router = APIRouter(tags=["webapp"])

class AchievementItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name_ru: str
    description_ru: str
    icon_url: Optional[str] = None
    unlocked: bool = False
    awarded_at: Optional[datetime] = None

class ChatItem(BaseModel):
    id: str
    title: str
    role: str = "student"

class ClassPulseResponse(BaseModel):
    total_questions_week: int = 0
    resolved_questions_week: int = 0
    resolution_rate: int = 0
    top_helper_name: str = "—"
    time_saved_hours: float = 0.0

class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    max_user_id: str
    display_name: str
    avatar_url: Optional[str] = None
    role: str
    balance_spasibki: int
    xp: int
    rank: str
    level: int
    helped_count: int = 0
    questions_count: int = 0
    rank_position: int = 1
    streak_days: int = 0
    chats: List[ChatItem] = []
    achievements: List[AchievementItem] = []
    class_pulse: Optional[ClassPulseResponse] = None

class LeaderboardEntry(BaseModel):
    rank_position: int
    max_user_id: str
    display_name: str
    avatar_url: Optional[str] = None
    rank: str
    xp: int
    balance_spasibki: int

class LeaderboardResponse(BaseModel):
    period: str
    items: List[LeaderboardEntry]

class RewardItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by_teacher_id: str
    chat_id: Optional[str] = None
    title: str
    description: str
    cost_spasibki: int
    is_active: bool

class ClaimRewardRequest(BaseModel):
    reward_id: int
    student_max_id: Optional[str] = None
    user_id: Optional[str] = None
    chat_id: Optional[str] = None

class ClaimRewardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reward_id: int
    student_max_id: str
    status: str
    created_at: datetime

class ReviewClaimRequest(BaseModel):
    claim_id: int
    action: Optional[str] = None
    decision: Optional[str] = None

class CreateRewardRequest(BaseModel):
    title: str
    description: str
    cost_spasibki: int
    chat_id: Optional[str] = None

class SyncUserRequest(BaseModel):
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None

class AwardBadgeRequest(BaseModel):
    student_id: str
    badge_code: Optional[str] = "teacher_choice"
    chat_id: Optional[str] = None

class TeacherOverviewResponse(BaseModel):
    pending_claims: List[Dict[str, Any]]
    active_questions: List[Dict[str, Any]]
    total_students: int
    issued_rewards: List[Dict[str, Any]] = []
    class_pulse: Optional[ClassPulseResponse] = None

@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    chat_id: Optional[str] = Query(None),
    avatar_url: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if avatar_url and current_user.avatar_url != avatar_url:
        current_user.avatar_url = avatar_url
        await session.commit()

    bad_chats_q = select(Chat.max_chat_id).where(
        or_(Chat.title == "Диалог", Chat.title.ilike("%диалог%"))
    )
    bad_ids = (await session.execute(bad_chats_q)).scalars().all()
    if bad_ids:
        await session.execute(delete(ChatMember).where(ChatMember.chat_max_id.in_(bad_ids)))
        await session.execute(delete(Chat).where(Chat.max_chat_id.in_(bad_ids)))
        await session.commit()

    query = (
        select(Achievement, UserAchievement.awarded_at)
        .join(UserAchievement, Achievement.id == UserAchievement.achievement_id)
        .where(UserAchievement.user_max_id == current_user.max_user_id)
        .order_by(UserAchievement.awarded_at.desc())
    )
    res = await session.execute(query)
    achievements_data = [
        AchievementItem(
            id=ach.id,
            code=ach.code,
            name_ru=ach.name_ru,
            description_ru=ach.description_ru,
            icon_url=ach.icon_url,
            unlocked=True,
            awarded_at=awarded_at,
        )
        for ach, awarded_at in res.all()
    ]

    if chat_id and chat_id != "all":
        h_res = await session.execute(
            select(func.count(Answer.id))
            .join(Question, Answer.question_id == Question.id)
            .where(
                Answer.author_max_id == current_user.max_user_id,
                Answer.status == "accepted",
                Question.group_chat_id == chat_id,
            )
        )
        helped_count = h_res.scalar_one() or 0

        q_res = await session.execute(
            select(func.count(Question.id)).where(
                Question.author_max_id == current_user.max_user_id,
                Question.group_chat_id == chat_id,
            )
        )
        questions_count = q_res.scalar_one() or 0

        members_res = await session.execute(
            select(ChatMember)
            .where(ChatMember.chat_max_id == chat_id, ChatMember.role != "teacher")
            .order_by(ChatMember.xp.desc(), ChatMember.balance_spasibki.desc(), ChatMember.id.asc())
        )
        chat_members = members_res.scalars().all()
        rank_pos = 1
        for idx, cm in enumerate(chat_members, 1):
            if cm.user_max_id == current_user.max_user_id:
                rank_pos = idx
                break
    else:
        h_res = await session.execute(
            select(func.count(Answer.id)).where(
                Answer.author_max_id == current_user.max_user_id,
                Answer.status == "accepted",
            )
        )
        helped_count = h_res.scalar_one() or 0

        q_res = await session.execute(
            select(func.count(Question.id)).where(
                Question.author_max_id == current_user.max_user_id
            )
        )
        questions_count = q_res.scalar_one() or 0

        all_students_res = await session.execute(
            select(User).where(User.role != "teacher").order_by(User.xp.desc(), User.balance_spasibki.desc(), User.id.asc())
        )
        students = all_students_res.scalars().all()
        rank_pos = 1
        for idx, s in enumerate(students, 1):
            if s.max_user_id == current_user.max_user_id:
                rank_pos = idx
                break

    memberships_res = await session.execute(
        select(Chat, ChatMember.role)
        .join(ChatMember, Chat.max_chat_id == ChatMember.chat_max_id)
        .where(
            ChatMember.user_max_id == current_user.max_user_id,
            Chat.title != "Диалог",
            not_(Chat.title.ilike("%диалог%")),
        )
        .order_by(Chat.title.asc())
    )
    user_chats_map = {
        c.max_chat_id: ChatItem(id=c.max_chat_id, title=c.title, role=r)
        for c, r in memberships_res.all()
    }

    owned_chats_res = await session.execute(
        select(Chat).where(
            Chat.owner_id == current_user.max_user_id,
            Chat.title != "Диалог",
            not_(Chat.title.ilike("%диалог%")),
        )
    )
    for c in owned_chats_res.scalars().all():
        if c.max_chat_id not in user_chats_map:
            user_chats_map[c.max_chat_id] = ChatItem(id=c.max_chat_id, title=c.title, role="teacher")
        else:
            user_chats_map[c.max_chat_id].role = "teacher"

    user_chats = list(user_chats_map.values())
    if not user_chats:
        user_chats = [
            ChatItem(id="my_class", title="Мой учебный чат", role=current_user.role)
        ]

    current_role = current_user.role
    current_balance = current_user.balance_spasibki
    current_xp = current_user.xp
    if chat_id and chat_id != "all":
        for uc in user_chats:
            if uc.id == chat_id:
                current_role = uc.role
                break
        cm_res = await session.execute(
            select(ChatMember).where(
                ChatMember.chat_max_id == chat_id,
                ChatMember.user_max_id == current_user.max_user_id,
            )
        )
        cm_row = cm_res.scalar_one_or_none()
        if cm_row is not None:
            current_balance = cm_row.balance_spasibki
            current_xp = cm_row.xp
        else:
            current_balance = 0
            current_xp = 0
    elif user_chats:
        current_role = user_chats[0].role

    pulse_data = None
    if current_role == "teacher":
        current_balance = 0
        current_xp = 0
        rank_pos = 0
        current_rank = "Преподаватель"
        level = 1
        active_chat_id = chat_id if (chat_id and chat_id != "all") else (user_chats[0].id if user_chats else None)
        pulse_dict = await TeacherService.get_class_pulse(session, active_chat_id)
        pulse_data = ClassPulseResponse(**pulse_dict)
    else:
        current_rank = GamificationService.calculate_rank(current_xp)
        level = (current_xp // 100) + 1

    streak_days = await GamificationService.calculate_streak(session, current_user.max_user_id, chat_id if (chat_id and chat_id != "all") else None)
    return UserProfileResponse(
        id=current_user.id,
        max_user_id=current_user.max_user_id,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        role=current_role,
        balance_spasibki=current_balance,
        xp=current_xp,
        rank=current_rank,
        level=level,
        helped_count=helped_count,
        questions_count=questions_count,
        rank_position=rank_pos,
        streak_days=streak_days,
        chats=user_chats,
        achievements=achievements_data,
        class_pulse=pulse_data,
    )

@router.post("/sync-user")
async def sync_user(
    body: SyncUserRequest,
    session: AsyncSession = Depends(get_db_session),
):
    uid = str(body.user_id).strip()
    full_name = f"{body.first_name or ''} {body.last_name or ''}".strip() or body.username or f"Участник {uid}"
    res = await session.execute(select(User).where(User.max_user_id == uid))
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            max_user_id=uid,
            display_name=full_name,
            avatar_url=body.avatar_url,
            role="student",
            balance_spasibki=0,
            xp=0,
            rank="Новичок",
        )
        session.add(user)
    else:
        user.display_name = full_name
        if body.avatar_url:
            user.avatar_url = body.avatar_url
    await session.commit()
    return {"status": "ok", "display_name": full_name}

@router.get("/chats", response_model=List[ChatItem])
async def get_chats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    bad_chats_q = select(Chat.max_chat_id).where(
        or_(Chat.title == "Диалог", Chat.title.ilike("%диалог%"))
    )
    bad_ids = (await session.execute(bad_chats_q)).scalars().all()
    if bad_ids:
        await session.execute(delete(ChatMember).where(ChatMember.chat_max_id.in_(bad_ids)))
        await session.execute(delete(Chat).where(Chat.max_chat_id.in_(bad_ids)))
        await session.commit()

    mem_res = await session.execute(
        select(Chat, ChatMember.role)
        .join(ChatMember, Chat.max_chat_id == ChatMember.chat_max_id)
        .where(
            ChatMember.user_max_id == current_user.max_user_id,
            Chat.title != "Диалог",
            not_(Chat.title.ilike("%диалог%")),
        )
        .order_by(Chat.title.asc())
    )
    user_chats_map = {
        c.max_chat_id: ChatItem(id=c.max_chat_id, title=c.title, role=r)
        for c, r in mem_res.all()
    }

    owned_chats_res = await session.execute(
        select(Chat).where(
            Chat.owner_id == current_user.max_user_id,
            Chat.title != "Диалог",
            not_(Chat.title.ilike("%диалог%")),
        )
    )
    for c in owned_chats_res.scalars().all():
        if c.max_chat_id not in user_chats_map:
            user_chats_map[c.max_chat_id] = ChatItem(id=c.max_chat_id, title=c.title, role="teacher")
        else:
            user_chats_map[c.max_chat_id].role = "teacher"

    my_chats = list(user_chats_map.values())
    if my_chats:
        return my_chats
    return [ChatItem(id="my_class", title="Мой учебный чат", role=current_user.role)]

@router.get("/achievements", response_model=List[AchievementItem])
async def get_achievements(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    all_res = await session.execute(select(Achievement).order_by(Achievement.id.asc()))
    all_achievements = all_res.scalars().all()

    ua_res = await session.execute(
        select(UserAchievement).where(UserAchievement.user_max_id == current_user.max_user_id)
    )
    user_unlocked = {ua.achievement_id: ua.awarded_at for ua in ua_res.scalars().all()}

    return [
        AchievementItem(
            id=ach.id,
            code=ach.code,
            name_ru=ach.name_ru,
            description_ru=ach.description_ru,
            icon_url=ach.icon_url,
            unlocked=(ach.id in user_unlocked),
            awarded_at=user_unlocked.get(ach.id),
        )
        for ach in all_achievements
    ]

@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    period: str = Query("all_time"),
    chat_id: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    session: AsyncSession = Depends(get_db_session),
):
    if period == "weekly":
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)
        if chat_id and chat_id != "all":
            weekly_query = (
                select(
                    User.max_user_id,
                    User.display_name,
                    User.avatar_url,
                    ChatMember.xp,
                    ChatMember.balance_spasibki,
                    (func.count(Answer.id) * 50).label("week_xp"),
                )
                .join(Answer, Answer.author_max_id == User.max_user_id)
                .join(Question, Answer.question_id == Question.id)
                .join(
                    ChatMember,
                    (ChatMember.user_max_id == User.max_user_id) & (ChatMember.chat_max_id == chat_id),
                )
                .where(
                    Answer.status == "accepted",
                    Answer.created_at >= since_dt,
                    Question.group_chat_id == chat_id,
                    ChatMember.role != "teacher",
                    User.role != "teacher",
                )
                .group_by(User.id, ChatMember.xp, ChatMember.balance_spasibki)
                .order_by(func.count(Answer.id).desc(), ChatMember.xp.desc())
                .offset(offset)
                .limit(limit)
            )
            res = await session.execute(weekly_query)
            rows = res.all()
            items = [
                LeaderboardEntry(
                    rank_position=idx,
                    max_user_id=row[0],
                    display_name=row[1],
                    avatar_url=row[2],
                    rank=GamificationService.calculate_rank(row[3] or 0),
                    xp=row[5],
                    balance_spasibki=row[4] or 0,
                )
                for idx, row in enumerate(rows, offset + 1)
            ]
            return LeaderboardResponse(period=period, items=items)
        else:
            weekly_query = (
                select(
                    User.max_user_id,
                    User.display_name,
                    User.rank,
                    User.balance_spasibki,
                    User.xp,
                    (func.count(Answer.id) * 50).label("week_xp"),
                    User.avatar_url,
                )
                .join(Answer, Answer.author_max_id == User.max_user_id)
                .where(Answer.status == "accepted", Answer.created_at >= since_dt, User.role != "teacher")
                .group_by(User.id)
                .order_by(func.count(Answer.id).desc(), User.xp.desc())
                .offset(offset)
                .limit(limit)
            )
            res = await session.execute(weekly_query)
            rows = res.all()
            items = [
                LeaderboardEntry(
                    rank_position=idx,
                    max_user_id=row[0],
                    display_name=row[1],
                    avatar_url=row[6],
                    rank=row[2],
                    xp=row[5],
                    balance_spasibki=row[3],
                )
                for idx, row in enumerate(rows, offset + 1)
            ]
            return LeaderboardResponse(period=period, items=items)

    if chat_id and chat_id != "all":
        all_time_query = (
            select(User, ChatMember.xp, ChatMember.balance_spasibki)
            .join(
                ChatMember,
                (ChatMember.user_max_id == User.max_user_id) & (ChatMember.chat_max_id == chat_id),
            )
            .where(
                ChatMember.role != "teacher",
                User.role != "teacher",
            )
            .order_by(ChatMember.xp.desc(), ChatMember.balance_spasibki.desc(), User.id.asc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(all_time_query)
        items = [
            LeaderboardEntry(
                rank_position=idx,
                max_user_id=s.max_user_id,
                display_name=s.display_name,
                avatar_url=s.avatar_url,
                rank=GamificationService.calculate_rank(chat_xp or 0),
                xp=chat_xp or 0,
                balance_spasibki=bal or 0,
            )
            for idx, (s, chat_xp, bal) in enumerate(res.all(), offset + 1)
        ]
        return LeaderboardResponse(period=period, items=items)
    else:
        all_time_query = (
            select(User)
            .where(User.role != "teacher")
            .order_by(User.xp.desc(), User.balance_spasibki.desc(), User.id.asc())
            .offset(offset)
            .limit(limit)
        )

    res = await session.execute(all_time_query)
    students = res.scalars().all()
    items = [
        LeaderboardEntry(
            rank_position=idx,
            max_user_id=s.max_user_id,
            display_name=s.display_name,
            avatar_url=s.avatar_url,
            rank=s.rank,
            xp=s.xp,
            balance_spasibki=s.balance_spasibki,
        )
        for idx, s in enumerate(students, offset + 1)
    ]
    return LeaderboardResponse(period=period, items=items)

@router.get("/rewards", response_model=List[RewardItem])
async def get_rewards(
    chat_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if chat_id and chat_id != "all":
        if current_user:
            mem_res = await session.execute(
                select(ChatMember).where(
                    ChatMember.chat_max_id == chat_id,
                    ChatMember.user_max_id == current_user.max_user_id,
                )
            )
            if mem_res.scalar_one_or_none() is None:
                chat_res = await session.execute(
                    select(Chat).where(Chat.max_chat_id == chat_id, Chat.owner_id == current_user.max_user_id)
                )
                if chat_res.scalar_one_or_none() is None:
                    return []

        existing_res = await session.execute(
            select(Reward).where(Reward.is_active == True, Reward.chat_id == chat_id)
        )
        chat_rewards = existing_res.scalars().all()
        if not chat_rewards:
            from app.database.session import READY_REWARDS
            new_rewards = [
                Reward(
                    created_by_teacher_id="teacher_admin",
                    chat_id=chat_id,
                    title=r["title"],
                    description=r["description"],
                    cost_spasibki=r["cost_spasibki"],
                    is_active=True,
                )
                for r in READY_REWARDS
            ]
            session.add_all(new_rewards)
            await session.commit()
            query = select(Reward).where(Reward.is_active == True, Reward.chat_id == chat_id)
        else:
            query = select(Reward).where(Reward.is_active == True, Reward.chat_id == chat_id)
    else:
        query = select(Reward).where(Reward.is_active == True)
    query = query.order_by(Reward.cost_spasibki.asc())
    res = await session.execute(query)
    return res.scalars().all()

@router.post("/rewards/claim", response_model=ClaimRewardResponse)
@router.post("/rewards/buy", response_model=ClaimRewardResponse)
async def claim_reward(
    body: ClaimRewardRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    student_id = body.student_max_id or body.user_id or current_user.max_user_id
    try:
        claim = await TeacherService.claim_reward(
            session=session,
            student_max_id=student_id,
            reward_id=body.reward_id,
            chat_id=body.chat_id,
        )
        return claim
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.get("/my-claims")
async def get_my_claims(
    chat_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    query = (
        select(RewardClaim, Reward)
        .join(Reward, RewardClaim.reward_id == Reward.id)
        .where(RewardClaim.student_max_id == current_user.max_user_id)
    )
    if chat_id and chat_id != "all":
        query = query.where(RewardClaim.chat_id == chat_id)
    query = query.order_by(RewardClaim.created_at.desc())
    res = await session.execute(query)
    return [
        {
            "id": claim.id,
            "reward_id": reward.id,
            "title": reward.title,
            "cost_spasibki": reward.cost_spasibki,
            "chat_id": claim.chat_id,
            "status": claim.status,
            "created_at": claim.created_at.isoformat() if claim.created_at else None,
        }
        for claim, reward in res.all()
    ]

@router.get("/teacher/overview", response_model=TeacherOverviewResponse)
async def get_teacher_overview(
    chat_id: Optional[str] = Query(None),
    current_teacher: User = Depends(require_teacher),
    session: AsyncSession = Depends(get_db_session),
):
    if not chat_id or chat_id == "all":
        return TeacherOverviewResponse(
            pending_claims=[],
            active_questions=[],
            total_students=0,
            issued_rewards=[],
        )
    overview = await TeacherService.get_teacher_overview(
        session=session,
        teacher_max_id=current_teacher.max_user_id,
        chat_id=chat_id,
    )
    return TeacherOverviewResponse(
        pending_claims=overview.get("pending_claims", []),
        active_questions=overview.get("active_questions", []),
        total_students=overview.get("total_students", 0),
        issued_rewards=overview.get("issued_rewards", []),
        class_pulse=overview.get("class_pulse"),
    )

@router.post("/teacher/review-claim")
async def review_reward_claim(
    body: ReviewClaimRequest,
    current_teacher: User = Depends(require_teacher),
    session: AsyncSession = Depends(get_db_session),
):
    decision_val = body.action or body.decision
    if not decision_val:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing action or decision")
    try:
        claim = await TeacherService.review_reward_claim(
            session=session,
            teacher_max_id=current_teacher.max_user_id,
            claim_id=body.claim_id,
            decision=decision_val,
        )
        return {
            "status": "ok",
            "claim_id": claim.id,
            "new_status": claim.status,
        }
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.post("/teacher/rewards", response_model=RewardItem)
async def create_reward(
    body: CreateRewardRequest,
    current_teacher: User = Depends(require_teacher),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        reward = await TeacherService.create_reward(
            session=session,
            teacher_max_id=current_teacher.max_user_id,
            title=body.title,
            description=body.description,
            cost_spasibki=body.cost_spasibki,
            chat_id=body.chat_id if body.chat_id != "all" else None,
        )
        return reward
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/teacher/rewards/{reward_id}")
@router.post("/teacher/rewards/{reward_id}/delete")
async def delete_reward(
    reward_id: int,
    current_teacher: User = Depends(require_teacher),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        await TeacherService.delete_reward(
            session=session,
            teacher_max_id=current_teacher.max_user_id,
            reward_id=reward_id,
        )
        return {"status": "ok", "message": "Награда удалена"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

@router.post("/teacher/award-badge")
async def award_teacher_badge(
    body: AwardBadgeRequest,
    current_teacher: User = Depends(require_teacher),
    session: AsyncSession = Depends(get_db_session),
):
    badge = body.badge_code or "teacher_choice"
    new_codes = await GamificationService.evaluate_achievements(
        session=session,
        user_id=body.student_id,
        context={"manual_code": badge},
    )
    await TeacherService.adjust_student_balance(
        session=session,
        teacher_max_id=current_teacher.max_user_id,
        student_max_id=body.student_id,
        delta_spasibki=20,
        delta_xp=100,
        reason="Награда Выбор учителя",
        chat_id=body.chat_id if body.chat_id != "all" else None,
    )
    if body.chat_id and body.chat_id != "all":
        u_res = await session.execute(select(User).where(User.max_user_id == body.student_id))
        st = u_res.scalar_one_or_none()
        st_name = st.display_name if st else "Ученик"
        await send_chat_notification(
            body.chat_id,
            f"⭐️ Педагог отметил(а) {st_name} специальной наградой «Выбор учителя» (+100 XP и +20 спасибок)! Поздравляем! 👏",
        )
    return {"status": "ok", "awarded": new_codes}

@router.get("/students")
async def list_students(
    chat_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session),
):
    if chat_id and chat_id != "all":
        query = (
            select(User, ChatMember.balance_spasibki, ChatMember.xp)
            .join(ChatMember, ChatMember.user_max_id == User.max_user_id)
            .where(ChatMember.chat_max_id == chat_id, ChatMember.role != "teacher")
            .order_by(User.display_name.asc())
        )
        res = await session.execute(query)
        rows = res.all()
        return [
            {
                "max_user_id": s.max_user_id,
                "display_name": s.display_name,
                "rank": GamificationService.calculate_rank(chat_xp or 0),
                "balance_spasibki": bal if bal is not None else 0,
                "xp": chat_xp if chat_xp is not None else 0,
            }
            for s, bal, chat_xp in rows
        ]
    else:
        query = (
            select(User)
            .where(
                or_(
                    User.role == "student",
                    User.max_user_id.in_(
                        select(ChatMember.user_max_id).where(ChatMember.role != "teacher")
                    ),
                )
            )
            .order_by(User.display_name.asc())
        )
        res = await session.execute(query)
        students = res.scalars().all()
        return [
            {
                "max_user_id": s.max_user_id,
                "display_name": s.display_name,
                "rank": s.rank,
                "balance_spasibki": s.balance_spasibki,
                "xp": s.xp,
            }
            for s in students
        ]
