from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("Record", back_populates="owner")


# ... 前面的 User 类保持不变 ...

class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)

    # 🌟 新增：运动类型，默认是平板支撑
    activity_type = Column(String, default="plank", index=True)

    # 🌟 新增：跑步距离 (公里)，平板支撑不填这个
    distance = Column(Float, nullable=True)

    duration_seconds = Column(Integer, nullable=False)  # 平板是秒，跑步可以存总秒数
    record_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="records")
    likes = relationship("Like", back_populates="record", cascade="all, delete-orphan")


# ... 后面的 Like 类保持不变 ...
# 🌟 全新引入：点赞关系表
class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_id = Column(Integer, ForeignKey("records.id"), nullable=False)

    # 关联回用户和记录
    user = relationship("User")
    record = relationship("Record", back_populates="likes")