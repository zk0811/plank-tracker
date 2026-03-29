from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, utils
from ..database import get_db
from ..auth import create_access_token  # 引入 JWT 工具

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/register", response_model=schemas.TokenResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user: raise HTTPException(status_code=400, detail="用户名已被注册")

    new_user = models.User(username=user.username, hashed_password=utils.hash_password(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 🌟 生成 JWT Token
    token = create_access_token({"user_id": new_user.id})
    return {"access_token": token, "user": new_user}


@router.post("/login", response_model=schemas.TokenResponse)
def login_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if not db_user or not utils.verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="账号或密码错误！")

    # 🌟 生成 JWT Token
    token = create_access_token({"user_id": db_user.id})
    return {"access_token": token, "user": db_user}