import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 🌟 核心改造：读取云端环境变量
# 如果在云端，系统会读取 "DATABASE_URL" (指向 Postgres)
# 如果在本地，读不到该变量，就默认继续使用本地的 sqlite
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./plank.db")

# 针对不同数据库类型，使用不同的引擎配置
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # 本地 SQLite 配置
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # 修复某些云平台 (如 Render/Heroku) 默认提供的 postgres:// 协议前缀问题
    if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    # 云端 PostgreSQL 配置
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()