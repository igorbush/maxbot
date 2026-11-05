from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, desc
from app.database import get_session
from app.models import (
    User, Question, Achievement, UserAchievement,
    Reward, RewardRequest, calculate_level
)

api_router = APIRouter()


class BuyRewardRequest(BaseModel):
    user_id: int
    reward_id: int


class ReviewRewardRequest(BaseModel):
    teacher_id: int
    request_id: int
    action: str


class CreateRewardRequest(BaseModel):
    teacher_id: int
    title: str
    description: str
    price_coins: int
    icon: Optional[str] = "🎁"


class AwardTeacherChoiceRequest(BaseModel):
    teacher_id: int
    student_id: int


@api_router.get("/profile")
def get_profile(
    user_id: int = Query(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.max_user_id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    all_users = session.exec(select(User).where(User.role == "student").order_by(desc(User.xp))).all()
    rank = 1
    for idx, u in enumerate(all_users):
        if u.id == user.id:
            rank = idx + 1
            break

    level_info = calculate_level(user.xp)

    return {
        "id": user.id,
        "max_user_id": user.max_user_id,
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "coins": user.coins,
        "helped_count": user.helped_count,
        "questions_count": user.questions_count,
        "rank": rank,
        "total_students": len(all_users),
        "level": level_info,
    }


@api_router.get("/leaderboard")
def get_leaderboard(session: Session = Depends(get_session)):
    students = session.exec(
        select(User).where(User.role == "student").order_by(desc(User.xp)).limit(20)
    ).all()

    result = []
    for idx, s in enumerate(students):
        level_info = calculate_level(s.xp)
        result.append({
            "rank": idx + 1,
            "max_user_id": s.max_user_id,
            "name": s.name,
            "username": s.username,
            "xp": s.xp,
            "coins": s.coins,
            "level_title": level_info["title"],
            "helped_count": s.helped_count,
        })
    return result


@api_router.get("/achievements")
def get_achievements(
    user_id: int = Query(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.max_user_id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    achievements = session.exec(select(Achievement)).all()
    user_achs = session.exec(
        select(UserAchievement).where(UserAchievement.user_id == user.id)
    ).all()
    unlocked_map = {ua.achievement_id: ua.unlocked_at for ua in user_achs}

    result = []
    for ach in achievements:
        is_unlocked = ach.id in unlocked_map
        result.append({
            "id": ach.id,
            "code": ach.code,
            "title": ach.title,
            "description": ach.description,
            "icon": ach.icon,
            "xp_reward": ach.xp_reward,
            "coins_reward": ach.coins_reward,
            "is_unlocked": is_unlocked,
            "unlocked_at": unlocked_map[ach.id].strftime("%d.%m.%Y") if is_unlocked else None,
        })
    return result


@api_router.get("/rewards")
def get_rewards(
    user_id: int = Query(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.max_user_id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    rewards = session.exec(select(Reward).where(Reward.is_active == True)).all()

    requests = session.exec(
        select(RewardRequest, Reward)
        .join(Reward, RewardRequest.reward_id == Reward.id)
        .where(RewardRequest.user_id == user.id)
        .order_by(desc(RewardRequest.created_at))
    ).all()

    my_requests = []
    for req, rew in requests:
        my_requests.append({
            "id": req.id,
            "reward_title": rew.title,
            "reward_icon": rew.icon,
            "price_coins": rew.price_coins,
            "status": req.status,
            "created_at": req.created_at.strftime("%d.%m %H:%M"),
        })

    return {
        "user_coins": user.coins,
        "rewards": [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "price_coins": r.price_coins,
                "icon": r.icon,
            }
            for r in rewards
        ],
        "my_requests": my_requests,
    }


@api_router.post("/rewards/buy")
def buy_reward(
    data: BuyRewardRequest,
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.max_user_id == data.user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    reward = session.exec(select(Reward).where(Reward.id == data.reward_id)).first()
    if not reward or not reward.is_active:
        raise HTTPException(status_code=404, detail="Награда не найдена")

    if user.coins < reward.price_coins:
        return {"success": False, "error": f"Не хватает спасибок! Нужно {reward.price_coins}, а у вас {user.coins}"}

    user.coins -= reward.price_coins
    req = RewardRequest(
        user_id=user.id,
        reward_id=reward.id,
        status="pending"
    )
    session.add(user)
    session.add(req)
    session.commit()

    return {
        "success": True,
        "message": f"Заявка на '{reward.title}' отправлена учителю на подтверждение!",
        "new_coins": user.coins,
    }


@api_router.get("/teacher/requests")
def get_teacher_requests(
    teacher_id: int = Query(...),
    session: Session = Depends(get_session)
):
    teacher = session.exec(select(User).where(User.max_user_id == teacher_id)).first()
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступ запрещен. Требуется роль учителя.")

    pending_requests = session.exec(
        select(RewardRequest, Reward, User)
        .join(Reward, RewardRequest.reward_id == Reward.id)
        .join(User, RewardRequest.user_id == User.id)
        .where(RewardRequest.status == "pending")
        .order_by(desc(RewardRequest.created_at))
    ).all()

    result = []
    for req, rew, u in pending_requests:
        result.append({
            "id": req.id,
            "student_name": u.name,
            "student_id": u.max_user_id,
            "reward_title": rew.title,
            "reward_icon": rew.icon,
            "price_coins": rew.price_coins,
            "created_at": req.created_at.strftime("%d.%m %H:%M"),
        })
    return result


@api_router.post("/teacher/request/review")
def review_teacher_request(
    data: ReviewRewardRequest,
    session: Session = Depends(get_session)
):
    teacher = session.exec(select(User).where(User.max_user_id == data.teacher_id)).first()
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступ разрешен только учителям.")

    req = session.exec(select(RewardRequest).where(RewardRequest.id == data.request_id)).first()
    if not req:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    req.reviewed_at = datetime.now(timezone.utc)

    if data.action == "approve":
        req.status = "approved"
        session.add(req)
        session.commit()
        return {"success": True, "message": "Заявка успешно одобрена!"}
    else:
        req.status = "rejected"
        student = session.exec(select(User).where(User.id == req.user_id)).first()
        reward = session.exec(select(Reward).where(Reward.id == req.reward_id)).first()
        if student and reward:
            student.coins += reward.price_coins
            session.add(student)
        session.add(req)
        session.commit()
        return {"success": True, "message": "Заявка отклонена, спасибки возвращены ученику."}


@api_router.post("/teacher/reward/create")
def create_reward_by_teacher(
    data: CreateRewardRequest,
    session: Session = Depends(get_session)
):
    teacher = session.exec(select(User).where(User.max_user_id == data.teacher_id)).first()
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступ разрешен только учителям.")

    new_reward = Reward(
        title=data.title,
        description=data.description,
        price_coins=data.price_coins,
        icon=data.icon or "🎁",
        created_by_teacher_id=teacher.id,
    )
    session.add(new_reward)
    session.commit()
    return {"success": True, "message": f"Награда '{data.title}' успешно добавлена в лавку!"}


@api_router.post("/teacher/award_badge")
def award_teacher_choice(
    data: AwardTeacherChoiceRequest,
    session: Session = Depends(get_session)
):
    teacher = session.exec(select(User).where(User.max_user_id == data.teacher_id)).first()
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступ разрешен только учителям.")

    student = session.exec(select(User).where(User.max_user_id == data.student_id)).first()
    if not student:
        raise HTTPException(status_code=404, detail="Ученик не найден")

    ach = session.exec(select(Achievement).where(Achievement.code == "teacher_choice")).first()
    if not ach:
        raise HTTPException(status_code=404, detail="Достижение не найдено")

    existing = session.exec(
        select(UserAchievement).where(
            UserAchievement.user_id == student.id,
            UserAchievement.achievement_id == ach.id
        )
    ).first()

    if existing:
        return {"success": False, "message": "Ученик уже имеет это достижение!"}

    ua = UserAchievement(user_id=student.id, achievement_id=ach.id)
    student.xp += ach.xp_reward
    student.coins += ach.coins_reward
    session.add(ua)
    session.add(student)
    session.commit()

    return {
        "success": True,
        "message": f"Достижение '{ach.title}' успешно вручено ученику {student.name}! (+{ach.xp_reward} XP, +{ach.coins_reward} спасибок)"
    }


@api_router.get("/demo/users")
def get_demo_users(session: Session = Depends(get_session)):
    users = session.exec(select(User)).all()
    return [
        {
            "id": u.id,
            "max_user_id": u.max_user_id,
            "name": u.name,
            "role": u.role,
            "coins": u.coins,
            "xp": u.xp
        }
        for u in users
    ]
