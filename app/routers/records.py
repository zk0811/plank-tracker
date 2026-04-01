from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta
import json
import re  # 🌟 核心新增：正则表达式库，用来对付 AI 的废话
from zhipuai import ZhipuAI 

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/records", tags=["Records"])

# 🌟 你的 API Key
client = ZhipuAI(api_key="a31f7b3b6d73434d8ce69b63411f7313.7bfBGcxsSeAWWRqh")

# 🌟 进化版 AI：强制过滤 + 经验值分配系统
def get_ai_scores(user_input: str, streak_days: int):
    prompt = f"""
    你是一个硬核健身游戏的 AI 数值策划。请根据用户的打卡内容，为他们分配本次训练的【经验值(EXP)】。
    输入内容: "{user_input}"
    当前连胜: {streak_days} 天

    打分规则 (单次得分必须克制，通常在 5-30 之间，最高不超过 40)：
    1. upper (上肢): 只要包含"练胸/练背/练肩"，给 15-30 分。
    2. lower (下肢): 只要提到"练腿/深蹲/跑步"，给 15-30 分。
    3. core (核心): 平板支撑、练腹肌，给 15-30 分。
    4. cardio (心肺): 跑步、有氧，给 15-30 分。
    5. discipline (自律): 只要打卡就给 5 分基础分，外加 (连胜天数 * 2) 奖励，上限 20 分。

    绝对禁止输出任何前言后语、Markdown标记(如```json)或解释！只允许输出一个合法的 JSON 字典！
    格式如下:
    {{"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": 0}}
    """
    try:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
        )
        res_text = response.choices[0].message.content
        
        # 🌟 核心修复：用“正则镊子”精准提取 JSON 格式的数据，无视多余字符
        match = re.search(r'\{[\s\S]*\}', res_text)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            print("未能提取到 JSON:", res_text)
            return {"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": 10}
            
    except Exception as e:
        print(f"AI 调用彻底失败: {e}")
        # 钓鱼测试：如果真失败了，故意给全部设为 8，这样你一看图表全变成 8 就能发现端倪！
        return {"upper": 8, "lower": 8, "core": 8, "cardio": 8, "discipline": 8}


# 🌟 1. 创建打卡记录
@router.post("/", response_model=schemas.RecordResponse)
def create_record(record: schemas.RecordCreate, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user: 
        raise HTTPException(status_code=401, detail="登录已失效")

    streak = 1 
    
    if record.activity_type == "plank":
        ai_input = f"我坚持做了 {record.duration_seconds} 秒的平板支撑，非常累，核心在燃烧。"
    elif record.activity_type == "run":
        ai_input = f"我完成了 {record.distance} 公里的户外跑步，用时 {record.duration_seconds // 60} 分钟。"
    else:
        qty_str = f" {record.duration_seconds} 次" if record.duration_seconds > 0 else ""
        ai_input = f"我进行了自由训练：{record.notes}{qty_str}。"

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


# 🌟 2. 获取全频道动态
@router.get("/", response_model=List[schemas.RecordResponse])
def get_all_records(db: Session = Depends(get_db)):
    records = db.query(models.Record).join(models.User).order_by(models.Record.record_date.desc()).limit(50).all()
    return records


# 🌟 3. 点赞 / 取消点赞
@router.post("/{record_id}/like")
def toggle_like(record_id: int, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    record = db.query(models.Record).filter(models.Record.id == record_id).first()
    if not record: 
        raise HTTPException(status_code=404, detail="记录不存在")

    existing_like = db.query(models.Like).filter(
        models.Like.record_id == record_id,
        models.Like.user_id == current_user_id
    ).first()

    if existing_like:
        db.delete(existing_like)
        db.commit()
        return {"message": "已取消点赞"}
    else:
        new_like = models.Like(user_id=current_user_id, record_id=record_id)
        db.add(new_like)
        db.commit()
        return {"message": "点赞成功"}


# 🌟 4. 删除自己的打卡记录
@router.delete("/{id}")
def delete_record(id: int, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    record_query = db.query(models.Record).filter(models.Record.id == id)
    record = record_query.first()

    if record == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到该记录")

    if record.user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作！")

    record_query.delete(synchronize_session=False)
    db.commit()
    return {"status": "success", "message": "已撤回"}


# 🌟 5. 周榜 / 月榜 排行榜
@router.get("/leaderboard/{activity_type}/{days}")
def get_leaderboard(activity_type: str, days: int, db: Session = Depends(get_db)):
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    if activity_type == "plank":
        results = db.query(
            models.User.username, 
            func.sum(models.Record.duration_seconds).label("total_val")
        ).join(models.Record, models.User.id == models.Record.user_id)\
         .filter(models.Record.activity_type == activity_type)\
         .filter(models.Record.record_date >= cutoff_date)\
         .group_by(models.User.username)\
         .order_by(func.sum(models.Record.duration_seconds).desc())\
         .limit(10).all()
    else:
        results = db.query(
            models.User.username, 
            func.sum(models.Record.distance).label("total_val")
        ).join(models.Record, models.User.id == models.Record.user_id)\
         .filter(models.Record.activity_type == activity_type)\
         .filter(models.Record.record_date >= cutoff_date)\
         .group_by(models.User.username)\
         .order_by(func.sum(models.Record.distance).desc())\
         .limit(10).all()

    return [{"username": r.username, "max_value": round(r.total_val, 2) if r.total_val else 0} for r in results]


# 🌟 6. 连胜排行榜
@router.get("/streaks/{activity_type}", response_model=List[schemas.StreakEntry])
def get_streak_leaderboard(activity_type: str, db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    streak_data = []
    today = datetime.utcnow().date()
    
    for user in users:
        records = db.query(models.Record.record_date).filter(
            models.Record.user_id == user.id, 
            models.Record.activity_type == activity_type
        ).order_by(models.Record.record_date.desc()).all()

        if not records: continue
        unique_dates = sorted(list(set([r[0].date() for r in records])), reverse=True)
        if not unique_dates: continue

        if unique_dates[0] < today - timedelta(days=1):
            streak = 0
        else:
            streak = 1
            current_check_date = unique_dates[0]
            for d in unique_dates[1:]:
                if d == current_check_date - timedelta(days=1):
                    streak += 1
                    current_check_date = d
                else:
                    break
                    
        if streak > 0: 
            streak_data.append({"username": user.username, "current_streak": streak})

    streak_data.sort(key=lambda x: x["current_streak"], reverse=True)
    return streak_data[:10]
