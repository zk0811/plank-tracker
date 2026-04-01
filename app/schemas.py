from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class UserBase(BaseModel):
    username: str

class RecordBase(BaseModel):
    duration_seconds: int
    notes: Optional[str] = None
    # 🌟 新增字段验证
    activity_type: str = "plank"
    distance: Optional[float] = None

class RecordCreate(RecordBase):
    pass

# 🌟 新增：专门用于返回点赞用户的信息格式
class LikeResponse(BaseModel):
    user: UserBase
    class Config:
        from_attributes = True

class RecordResponse(RecordBase):
    id: int
    record_date: datetime
    user_id: int
    owner: UserBase
    # 🌟 核心改动：把 likes 从 int 改成了点赞对象的列表！
    likes: List[LikeResponse] = []
    
    # 🌟 终极防弹修改：加上 Optional！允许数据库里有空值，如果没有就默认为 0，完美兼容老数据！
    upper: Optional[int] = 0
    lower: Optional[int] = 0
    core: Optional[int] = 0
    cardio: Optional[int] = 0
    discipline: Optional[int] = 0

    class Config:
        from_attributes = True

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime
    records: List[RecordResponse] = []
    class Config:
        from_attributes = True

class LeaderboardEntry(BaseModel):
    username: str
    max_value: float
    class Config:
        from_attributes = True

class StreakEntry(BaseModel):
    username: str
    current_streak: int
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
