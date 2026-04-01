from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta
import json
from zhipuai import ZhipuAI 

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/records", tags=["Records"])

# 🌟 确保这里填的是你带引号的 API Key
client = ZhipuAI(api_key="a31f7b3b6d73434d8ce69b63411f7313.7bfBGcxsSeAWWRqh")

def get_ai_scores(user_input: str, streak_days: int):
    prompt = f"""
    你是一个专业的健身教练。请分析用户的打卡记录并给出0-100的分数。
    打卡内容: "{user_input}"
    用户已连续打卡: {streak_days} 天
    
    请根据动作强度和部位分五个维度打分(0-100)：
    - upper (上肢力量): 俯卧撑、引体向上、练胸背肩等。
    - lower (下肢力量): 跑步、深蹲、练腿等。
    - core (核心力量): 平板支撑、腹肌训练等。
    - cardio (心肺耐力): 跑步、开合跳等有氧。
    - discipline (自律): 1天20分，5天100分，最高100。
    
    只需返回标准的 JSON，不要解释:
    {{"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": 0}}
    """
    try:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
        )
        res_text = response.choices[0].message.content
        res_text = res_text.replace('```json', '').replace('```', '').strip()
        return json.loads(res_text)
    except:
        return {"upper": 0, "lower": 0, "core": 0, "cardio": 0, "discipline": min(streak_days * 20, 100)}

@router.post("/", response_model=schemas.RecordResponse)
def create_record(record: schemas.RecordCreate, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user: raise HTTPException(status_code=401, detail="登录已失效")

    # 🌟 1. 计算当前用户的自律连胜天数 (为了传给 AI)
    # 这里简单简化：直接取该用户今天的记录数+1作为参考，或者复用你的连胜逻辑
    streak = 1 # 默认 1，之后可以优化为查数据库真实连胜

    # 🌟 2. 调用 AI 获取五维分数
    # 如果是自由训练，把动作名称发给 AI；如果是平板/跑步，我们也发给 AI 自动识别
    ai_input = record.notes if record.activity_type == "free" else f"{record.activity_type} {record.duration_seconds}秒"
    scores = get_ai_scores(ai_input, streak)

    # 🌟 3. 将分数塞进数据库记录
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

# ... 其余 get_all_records, toggle_like, delete_record 等函数保持不变 ...
# 请确保保留你代码中原有的 leaderboard 和 streaks 函数
