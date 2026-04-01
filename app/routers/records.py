from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta
import json
from zhipuai import ZhipuAI  # 🌟 新增：引入智谱 AI

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user  # 统一引入解析当前用户的依赖

router = APIRouter(prefix="/records", tags=["Records"])

# 🌟 新增：初始化 AI 教练 (请务必把你的真实 Key 填在下面)
client = ZhipuAI(api_key=a31f7b3b6d73434d8ce69b63411f7313.7bfBGcxsSeAwWRqh)

# 🌟 新增：AI 裁判打分核心系统 (暂未接入路由，先随服务器部署测试环境)
def get_ai_scores(user_input: str, streak_days: int):
    prompt = f"""
    你是一个专业的健身教练。请分析用户的打卡记录并给出0-100的分数。
    打卡内容: "{user_input}"
    用户已连续打卡: {streak_days} 天
    
    请根据动作强度打分：
    - upper (上肢力量): 俯卧撑、引体向上、练胸背肩等
    - lower (下肢力量): 跑步、深蹲等
    - core (核心力量): 平板支撑、俯卧撑辅助等
    - cardio (心肺耐力): 跑步、高频自由动作等
    - discipline (自律): 根据连续天数计算，1天20分，5天100分。
    
    只需返回 JSON 格式，不要任何解释，格式如下:
    {{"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": 0}}
    """
    
    try:
        response = client.chat.completions.create(
            model="glm-4-flash", # 免费模型
            messages=[{"role": "user", "content": prompt}],
        )
        # 解析 AI 返回的 JSON
        res_text = response.choices[0].message.content
        # 处理可能包含的 markdown 代码块符号 (比如 ```json ... ```)
        res_text = res_text.replace('```json', '').replace('```', '').strip()
        return json.loads(res_text)
    except Exception as e:
        # 如果 AI 挂了或者解析失败，给个保底分
        print(f"AI 解析失败: {e}")
        return {"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": min(streak_days * 20, 100)}


# 🌟 1. 创建打卡记录 (兼容平板、跑步、自由训练)
@router.post("/", response_model=schemas.RecordResponse)
def create_record(
    record: schemas.RecordCreate, 
    db: Session = Depends(get_db), 
    current_user_id: int = Depends(get_current_user)
):
    # 先去数据库确认这个用户是否真的存在
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    # record.model_dump() 会自动把前端传来的 notes(动作名称) 和 duration_seconds(数量) 塞进数据库
    new_record = models.Record(**record.model_dump(), user_id=current_user_id)
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record


# 🌟 2. 获取全频道动态 (限制最新 50 条，并连表过滤孤儿数据)
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


# 🌟 4. 删除自己的打卡记录 (撤回功能)
@router.delete("/{id}")
def delete_record(id: int, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    record_query = db.query(models.Record).filter(models.Record.id == id)
    record = record_query.first()

    if record == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到该记录")

    # 核心安全验证：统一使用 current_user_id 比对
    if record.user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作！你只能删除自己的记录。")

    record_query.delete(synchronize_session=False)
    db.commit()
    return {"status": "success", "message": "打卡记录已成功撤回"}


# 🌟 5. 周榜 / 月榜 排行榜 (按累计总和计算)
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
