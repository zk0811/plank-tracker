from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse # 🌟 新增：用于返回文件
from . import models
from .database import engine
from .routers import users, records

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PlankTracker API",
    description="用于团队平板支撑打卡的轻量级后端服务",
    version="1.0.0"
)

# 配置 CORS 跨域中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(records.router)

# ==================================
# 🌟 终极核心修改：拦截首页请求，直接返回你的前端网页！
# ==================================
@app.get("/")
def serve_frontend():
    return FileResponse("frontend/index.html")