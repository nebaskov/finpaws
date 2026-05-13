from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from pydantic import BaseModel

from app.config import SETTINGS


class TokenPayload(BaseModel):
    sub: str
    email: str
    exp: int


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def issue_token(user_id: str, email: str) -> str:
    exp = datetime.now(tz=UTC) + timedelta(seconds=SETTINGS.jwt_ttl_seconds)
    payload = {"sub": user_id, "email": email, "exp": int(exp.timestamp())}
    return jwt.encode(payload, SETTINGS.jwt_secret, algorithm=SETTINGS.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    data = jwt.decode(token, SETTINGS.jwt_secret, algorithms=[SETTINGS.jwt_algorithm])
    return TokenPayload(**data)
