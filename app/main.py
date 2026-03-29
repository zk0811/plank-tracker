from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # 新增导入
from . import models
from .database import engine
from .routers import users, records

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PlankTracker API",
    description="用于团队平板支撑打卡的轻量级后端服务",
    version="1.0.0"
)

# ====== 配置 CORS 跨域中间件 ======
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有域名访问（开发阶段极其方便，部署上线时再改成具体的域名）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有请求方法 (GET, POST, OPTIONS 等)
    allow_headers=["*"],  # 允许所有请求头
)
# ==================================

app.include_router(users.router)
app.include_router(records.router)

@app.get("/")
def read_root():
    return {"status": "success", "message": "欢迎来到 PlankTracker API！后端服务已成功启动。"}