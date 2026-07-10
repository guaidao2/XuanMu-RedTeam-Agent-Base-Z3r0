import hmac
import secrets
from dataclasses import dataclass
from hashlib import pbkdf2_hmac
from datetime import datetime, timedelta

import jwt
from sqlalchemy import or_
from sqlmodel import select

from config import get_config
from database import get_async_session
from logger import get_logger
from model.sandbox.containers import SandboxContainer
from model.system_user.users import SystemUser
from schema.system_user.users import SystemUserRole
from service.common.pagination import Page, paginate_statement


logger = get_logger(__name__)

_PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
_PASSWORD_HASH_ITERATIONS = 390_000
_PASSWORD_SALT_BYTES = 16


@dataclass(frozen=True)
class DeleteSystemUserResult:
    deleted: bool
    not_found: bool = False
    message: str = ""


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(_PASSWORD_SALT_BYTES)
    digest = pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        _PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"{_PASSWORD_HASH_ALGORITHM}${_PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False

    if algorithm != _PASSWORD_HASH_ALGORITHM or iterations <= 0 or not salt or not expected_digest:
        return False

    actual_digest = pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    ).hex()
    return hmac.compare_digest(actual_digest, expected_digest)


async def create_system_user(
    username: str,
    password: str,
    email: str = "",
    role: SystemUserRole = SystemUserRole.USER,
) -> SystemUser:
    now = datetime.now()
    system_user = SystemUser(
        role=role,
        email=email,
        username=username,
        password=_hash_password(password),
        created_at=now,
        updated_at=now,
    )

    async with get_async_session() as session:
        session.add(system_user)
        await session.commit()
        await session.refresh(system_user)

    logger.info("system user created: %s", system_user.id)
    return system_user


async def delete_system_user(id: int) -> DeleteSystemUserResult:
    async with get_async_session() as session:
        system_user = await session.get(SystemUser, id)
        if system_user is None:
            return DeleteSystemUserResult(deleted=False, not_found=True, message="system user not found")

        result = await session.exec(select(SandboxContainer.id).where(SandboxContainer.owner_id == id).limit(1))
        if result.first() is not None:
            return DeleteSystemUserResult(
                deleted=False,
                message="system user owns sandbox containers",
            )

        await session.delete(system_user)
        await session.commit()

    logger.info("system user deleted: %s", id)
    return DeleteSystemUserResult(deleted=True)


async def update_system_user(
    id: int,
    username: str | None = None,
    password: str | None = None,
    email: str | None = None,
    role: SystemUserRole | None = None,
) -> SystemUser | None:
    async with get_async_session() as session:
        system_user = await session.get(SystemUser, id)
        if system_user is None:
            return None

        if role is not None:
            system_user.role = role
        if email is not None:
            system_user.email = email
        if username is not None:
            system_user.username = username
        if password is not None:
            system_user.password = _hash_password(password)

        system_user.updated_at = datetime.now()
        session.add(system_user)
        await session.commit()
        await session.refresh(system_user)

    logger.info("system user updated: %s", system_user.id)
    return system_user


async def query_system_user_by_username(username: str) -> SystemUser | None:
    async with get_async_session() as session:
        result = await session.exec(select(SystemUser).where(SystemUser.username == username))
        return result.first()


async def query_system_user_by_id(user_id: int) -> SystemUser | None:
    async with get_async_session() as session:
        return await session.get(SystemUser, user_id)


async def query_system_users(page: int = 1, size: int = 100, keyword: str = "") -> Page[SystemUser]:
    statement = select(SystemUser).order_by(SystemUser.id)

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                SystemUser.email.ilike(pattern),
                SystemUser.username.ilike(pattern),
            )
        )

    return await paginate_statement(statement, page=page, size=size)


async def system_user_login(email: str, password: str) -> str | None:
    cfg = get_config()

    async with get_async_session() as session:
        result = await session.exec(select(SystemUser).where(SystemUser.email == email))
        system_user = result.first()
        if system_user is None:
            return None

        if not _verify_password(password, system_user.password):
            return None

        token = jwt.encode(
            payload={
                "id": system_user.id,
                "role": system_user.role,
                "email": system_user.email,
                "username": system_user.username,
                "sub": "xuanmu",
                "exp": datetime.now() + timedelta(days=30),
            },
            key=cfg.system.encrypt_key,
            algorithm="HS256",
        )
        return token
