import json
import os
from collections import defaultdict
from functools import wraps
from typing import List

from fastapi import HTTPException, Depends
from jose import jwt, JWTError
from starlette import status

from handlers.auth import get_user, ALGORITHM, oauth2_scheme, SECRET_KEY
from models.user import TokenData, User

# 存储访问信息的字典
access_stats = {
    "total_visits": 0,
    "user_visits": defaultdict(int),
    "endpoint_visits": defaultdict(int)
}


fake_users_db = {
    "admin": {
        "username": "admin",
        "full_name": "CUIT CCA",
        "email": "cuitcca@gmail.com",
        "hashed_password": "$2b$12$DZCc4DB5ML25syhkVdTs4.sY5/Yif65cd9HlXOiG03LbLTlftMpGm",
        "disabled": False,
        "role": "admin"
    },
    "cy": {
        "username": "cy",
        "full_name": "Chuan Yue",
        "email": "w2399147152@gmail.com",
        "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
        "disabled": False,
        "role": "user"
    }
}


def role_required(allowed_roles: List[str]):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = await get_current_active_user(*args, **kwargs)
            current_role = current_user.role
            print(current_role)
            print(allowed_roles)
            if current_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient privileges",
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

if __name__ == '__main__':
    print()