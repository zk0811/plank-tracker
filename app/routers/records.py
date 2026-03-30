from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta
from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user  # 引入解析当前用户的依赖
from .. import auth

router = APIRouter(prefix="/records", tags=["Records"])


# 🌟 核心安全升级：不需要在 URL 里传 user_id 了，自动从 Header 的 Token 解析
@router.post("/", response_model=schemas.RecordResponse)
def create_record(record: schemas.RecordCreate, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    # 🌟 新增：先去数据库确认这个用户是否真的存在
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        # 如果找不到用户（可能是删库了），返回 401 强制前端跳转登录
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    new_record = models.Record(**record.model_dump(), user_id=current_user_id)
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record


# 🌟 新增：点赞接口
# 🌟 全新升级：真正的点赞 / 取消点赞逻辑
@router.post("/{record_id}/like")
def toggle_like(record_id: int, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user)):
    record = db.query(models.Record).filter(models.Record.id == record_id).first()
    if not record: raise HTTPException(status_code=404, detail="记录不存在")

    # 在点赞表中查找：这个用户有没有给这条记录点过赞？
    existing_like = db.query(models.Like).filter(
        models.Like.record_id == record_id,
        models.Like.user_id == current_user_id
    ).first()

    if existing_like:
        # 如果已经点过了，再次点击就是【取消点赞】
        db.delete(existing_like)
        db.commit()
        return {"message": "已取消点赞"}
    else:
        # 如果没点过，新增点赞记录
        new_like = models.Like(user_id=current_user_id, record_id=record_id)
        db.add(new_like)
        db.commit()
        return {"message": "点赞成功"}
@router.get("/", response_model=List[schemas.RecordResponse])
def get_all_records(db: Session = Depends(get_db)):
    # 🌟 优化：使用 join 连表查询。这能确保只有拥有合法 owner 的记录才会被返回
    # 这样即使数据库里有“孤儿数据”，接口也不会报 500 错误
    records = db.query(models.Record).join(models.User).order_by(models.Record.record_date.desc()).limit(50).all()
    return records

@router.get("/leaderboard/{activity_type}/{days}")
def get_leaderboard(activity_type: str, days: int, db: Session = Depends(get_db)):
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    if activity_type == "plank":
        # 🌟 核心修改：从 func.max 变成 func.sum (累计总秒数)
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
        # 🌟 核心修改：从 func.max 变成 func.sum (累计总公里数)
        results = db.query(
            models.User.username, 
            func.sum(models.Record.distance).label("total_val")
        ).join(models.Record, models.User.id == models.Record.user_id)\
         .filter(models.Record.activity_type == activity_type)\
         .filter(models.Record.record_date >= cutoff_date)\
         .group_by(models.User.username)\
         .order_by(func.sum(models.Record.distance).desc())\
         .limit(10).all()

    # 💡 偷天换日：我们把求和的结果 (total_val) 依然叫作 "max_value" 传给前端
    # 这样前端的 Vue 代码完全不需要动，同时加入了 round 保留两位小数，防止跑步距离出现 10.33333 这种无限数字
    return [{"username": r.username, "max_value": round(r.total_val, 2) if r.total_val else 0} for r in results]

@router.get("/streaks/{activity_type}", response_model=List[schemas.StreakEntry])
def get_streak_leaderboard(activity_type: str, db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    streak_data = []
    today = datetime.utcnow().date()
    for user in users:
        # 增加过滤：只查当前运动类型
        records = db.query(models.Record.record_date).filter(
            models.Record.user_id == user.id, models.Record.activity_type == activity_type
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
        if streak > 0: streak_data.append({"username": user.username, "current_streak": streak})

    streak_data.sort(key=lambda x: x["current_streak"], reverse=True)
    return streak_data[:10]


from fastapi import HTTPException, status

# 🌟 修复点：去掉了 current_user.id，直接用 int(current_user) 进行比对
@router.delete("/{id}")
def delete_record(id: int, db: Session = Depends(get_db), current_user = Depends(auth.get_current_user)):
    # 1. 在数据库里找出这条记录
    record_query = db.query(models.Record).filter(models.Record.id == id)
    record = record_query.first()

    # 2. 如果记录不存在
    if record == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到该记录")

    # 3. 核心安全验证：只能删除自己的记录！（解决 int 报错）
    if record.user_id != int(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作！你只能删除自己的记录。")

    # 4. 执行删除并保存
    record_query.delete(synchronize_session=False)
    db.commit()
    return {"status": "success", "message": "打卡记录已成功撤回"}
