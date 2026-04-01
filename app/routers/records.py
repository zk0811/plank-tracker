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

# 🌟 初始化智谱 AI (填入你的 API Key)
client = ZhipuAI(api_key="a31f7b3b6d73434d8ce69b63411f7313.7bfBGcxsSeAWWRqh")

# 🛡️ 强化版：本地智能兜底算法 (Smart Fallback)
# 当 AI 超时或崩溃时，瞬间接管算分，内置丰富健身词库！
def get_smart_fallback(activity_type, notes, duration, distance, streak):
    # 基础自律分：打卡即送 5 分 + 连胜加成
    scores = {"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": min(5 + streak * 2, 20)}
    text = str(notes) if notes else ""
    
    if activity_type == "plank":
        # 平板支撑：精准算分 (基础15分 + 每分钟5分，上限30分)
        scores["core"] = min(15 + (duration // 60) * 5, 30)
    elif activity_type == "run":
        # 跑步：精准算分 (按公里数线性增长)
        dist = distance or 0
        scores["lower"] = min(15 + int(dist * 2), 30)
        scores["cardio"] = min(15 + int(dist * 3), 30)
    else:
        # 自由训练：强化版正则字典，精准捕捉动作语义！
        
        # 1. 上肢关键词扩充
        if re.search(r'(胸|背|肩|臂|推|拉|卧撑|引体|哑铃|杠铃|史密斯|龙门架|飞鸟|划船|二头|三头|上肢|推举)', text):
            scores["upper"] = 25
            
        # 2. 下肢关键词扩充
        if re.search(r'(腿|臀|深蹲|硬拉|下肢|倒蹬|腿举|保加利亚)', text):
            scores["lower"] = 25
            
        # 3. 核心关键词扩充
        if re.search(r'(腹|核心|卷腹|支撑|俄罗斯|马甲线|人鱼线)', text):
            scores["core"] = 25
            
        # 4. 心肺/有氧关键词扩充
        if re.search(r'(跑|跳|有氧|单车|波比|骑|椭圆机|划船机|爬楼机|跳绳)', text):
            scores["cardio"] = 25
            
        # 5. 保底机制：如果用户写了极其冷门的词，为了不让他白练，给予基础鼓励
        if scores["upper"] == 0 and scores["lower"] == 0 and scores["core"] == 0 and scores["cardio"] == 0:
            scores["core"] = 10 
            
    return scores


# 🧠 AI 算分核心引擎
def get_ai_scores(record: schemas.RecordCreate, ai_input: str, streak_days: int):
    prompt = f"""
    你是一个硬核健身游戏的 AI 数值策划。请根据用户的打卡内容，分配本次训练的【经验值(EXP)】。
    输入内容: "{ai_input}"
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
        # 🌟 设定 8 秒超时强制熔断机制
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            timeout=8.0 
        )
        res_text = response.choices[0].message.content
        match = re.search(r'\{[\s\S]*\}', res_text)
        
        if match:
            return json.loads(match.group(0))
        else:
            raise Exception("AI 格式异常")
            
    except Exception as e:
        print(f"🤖 AI 请求异常 ({e})，已无缝切换至本地智能兜底引擎！")
        # 熔断生效，静默调用强化版兜底算法！
        return get_smart_fallback(record.activity_type, record.notes, record.duration_seconds, record.distance, streak_days)


# ==========================================
# 下方为 API 路由接口 (保持原样，提供基础 CRUD 功能)
# ==========================================

@router.post("/", response_model=schemas.RecordResponse)
def create_record(record: schemas.RecordCreate, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user: raise HTTPException(status_code=401, detail="登录已失效")

    streak = 1 
    
    notes_str = f" 附加描述: {record.notes}" if record.notes else ""
    if record.activity_type == "plank":
        ai_input = f"平板支撑 {record.duration_seconds} 秒。{notes_str}"
    elif record.activity_type == "run":
        ai_input = f"户外跑步 {record.distance} 公里。{notes_str}"
    else:
        qty_str = f" {record.duration_seconds} 次" if record.duration_seconds > 0 else ""
        ai_input = f"自由训练动作: {record.notes}{qty_str}。"

    scores = get_ai_scores(record, ai_input, streak)

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
