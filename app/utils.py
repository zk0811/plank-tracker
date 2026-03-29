import bcrypt


def hash_password(password: str) -> str:
    # bcrypt 需要字节 (bytes) 类型，所以要 encode()
    pwd_bytes = password.encode('utf-8')
    # 生成随机盐值
    salt = bcrypt.gensalt()
    # 进行哈希加密
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    # 存入数据库前，把字节解码回字符串 (string)
    return hashed_bytes.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # 验证时同样需要将双方都转换为字节
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_byte_enc = hashed_password.encode('utf-8')

    return bcrypt.checkpw(password_byte_enc, hashed_password_byte_enc)