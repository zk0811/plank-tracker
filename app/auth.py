import jwt
from datetime import datetime, timedelta
from fastapi import Header, HTTPException

SECRET_KEY = "super-secret-plank-key-do-not-share" # 生产环境应当放在环境变量中
ALGORITHM = "HS256"

# 生成 Token
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=30) # Token 有效期 30 天
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 校验 Token 并获取当前用户ID (作为 FastAPI 的依赖注入)
def get_current_user(authorization: str = Header(...)):
    try:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token 格式错误")
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")