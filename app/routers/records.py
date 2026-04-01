from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta
import json
import re  
from zhipuai import ZhipuAI 

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/records", tags=["Records"])

client = ZhipuAI(api_key="a31f7b3b6d73434d8ce69b63411f7313.7bfBGcxsSeAWWRqh")

def get_ai_scores(user_input: str, streak_days: int):
    prompt = f"""
    你是一个硬核健身游戏的 AI 数值策划。请根据用户的打卡内容，分配本次训练的【经验值(EXP)】。
    输入内容: "{user_input}"
    当前连胜: {streak_days} 天

    打分规则 (单项分数在 0-30 之间，最高绝对不超过 40)：
    1. upper (上肢): 练胸/练背/练肩/俯卧撑/引体，给 15-30 分。
    2. lower (下肢): 跑步(每公里给5-8分)/练腿/深蹲，给 15-30 分。
    3. core (核心): 平板支撑(每60秒给10-15分)/练腹肌，给 15-30 分。
    4. cardio (心肺): 跑步(每公里给5-8分)/有氧，给 15-30 分。
    5. discipline (自律): 基础 5 分 + (连胜天数 * 2)，上限 20 分。

    绝对禁止输出多余文本、Markdown标记！只允许输出 JSON 字典！
    {{"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": 0}}
    """
    try:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
        )
        res_text = response.choices[0].message.content
        match = re.search(r'\{[\s\S]*\}', res_text)
        if match:
            return json.loads(match.group(0))
        else:
            return {"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": 10}
    except Exception as e:
        return {"upper": 5, "lower": 5, "core": 5, "cardio": 5, "discipline": 5}

@router.post("/", response_model=schemas.RecordResponse)
def create_record(record: schemas.RecordCreate, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user: raise HTTPException(status_code=401, detail="登录已失效")

    streak = 1 
    
    # 🌟 核心升级：为 AI 精准喂入数据，附带用户备注
    notes_str = f" 附加描述: {record.notes}" if record.notes else ""
    if record.activity_type == "plank":
        ai_input = f"平板支撑 {record.duration_seconds} 秒。{notes_str}"
    elif record.activity_type == "run":
        ai_input = f"户外跑步 {record.distance} 公里。{notes_str}"
    else:
        qty_str = f" {record.duration_seconds} 次" if record.duration_seconds > 0 else ""
        ai_input = f"自由训练动作: {record.notes}{qty_str}。"

    scores = get_ai_scores(ai_input, streak)

    new_record = models.Record(
        **record.model_dump(), 
        user_id=current_user_id,
        upper=scores.get("upper", 0),
        lower=scores.get("lower", 0),
        core=scores.get("core", 0),
        cardio=scores.get("cardio", 0),
        discipline=scores.get("discipline", 0)
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record

@router.get("/", response_model=List[schemas.RecordResponse])
def get_all_records(db: Session = Depends(get_db)):
    return db.query(models.Record).join(models.User).order_by(models.Record.record_date.desc()).limit(50).all()

@router.post("/{record_id}/like")
def toggle_like(record_id: int, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    record = db.query(models.Record).filter(models.Record.id == record_id).first()
    if not record: raise HTTPException(status_code=404)
    existing_like = db.query(models.Like).filter(models.Like.record_id == record_id, models.Like.user_id == current_user_id).first()
    if existing_like:
        db.delete(existing_like)
    else:
        db.add(models.Like(user_id=current_user_id, record_id=record_id))
    db.commit()
    return {"message": "success"}

@router.delete("/{id}")
def delete_record(id: int, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    record_query = db.query(models.Record).filter(models.Record.id == id)
    record = record_query.first()
    if not record or record.user_id != current_user_id: raise HTTPException(status_code=403)
    record_query.delete(synchronize_session=False)
    db.commit()
    return {"status": "success"}

@router.get("/leaderboard/{activity_type}/{days}")
def get_leaderboard(activity_type: str, days: int, db: Session = Depends(get_db)):
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    if activity_type == "plank":
        results = db.query(models.User.username, func.sum(models.Record.duration_seconds).label("total_val")).join(models.Record).filter(models.Record.activity_type == activity_type, models.Record.record_date >= cutoff_date).group_by(models.User.username).order_by(func.sum(models.Record.duration_seconds).desc()).limit(10).all()
    else:
        results = db.query(models.User.username, func.sum(models.Record.distance).label("total_val")).join(models.Record).filter(models.Record.activity_type == activity_type, models.Record.record_date >= cutoff_date).group_by(models.User.username).order_by(func.sum(models.Record.distance).desc()).limit(10).all()
    return [{"username": r.username, "max_value": round(r.total_val, 2) if r.total_val else 0} for r in results]

@router.get("/streaks/{activity_type}", response_model=List[schemas.StreakEntry])
def get_streak_leaderboard(activity_type: str, db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    streak_data = []
    today = datetime.utcnow().date()
    for user in users:
        recs = db.query(models.Record.record_date).filter(models.Record.user_id == user.id, models.Record.activity_type == activity_type).order_by(models.Record.record_date.desc()).all()
        if not recs: continue
        unique_dates = sorted(list(set([r[0].date() for r in recs])), reverse=True)
        if not unique_dates: continue
        if unique_dates[0] < today - timedelta(days=1): streak = 0
        else:
            streak = 1
            curr = unique_dates[0]
            for d in unique_dates[1:]:
                if d == curr - timedelta(days=1): streak += 1; curr = d
                else: break
        if streak > 0: streak_data.append({"username": user.username, "current_streak": streak})
    streak_data.sort(key=lambda x: x["current_streak"], reverse=True)
    return streak_data[:10]
