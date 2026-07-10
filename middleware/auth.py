from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response as StarletteResponse

from config import get_config
from schema.common.responses import CommonResponse
from schema.system_user.users import SystemUserRole


ACCESS_TOKEN_HEADER = "X-XM-Access-Token"
_API_PATH_PREFIX = "/api"


@dataclass(frozen=True)
class AuthUser:
    id: int
    role: SystemUserRole
    email: str
    username: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AuthUser":
        return cls(
            id=payload["id"],
            role=SystemUserRole(payload["role"]),
            email=payload["email"],
            username=payload["username"],
        )


class JwtAuthMiddleware(BaseHTTPMiddleware):
    """decode the application JWT on /api/* requests if present.

    a missing token passes through (public endpoints rely on this); a
    malformed/expired token is rejected up front so dependencies see a clean
    state."""

    async def dispatch(self, request: Request, call_next) -> StarletteResponse:
        if request.method == "OPTIONS" or not _is_api_request(request):
            return await call_next(request)

        token = request.headers.get(ACCESS_TOKEN_HEADER, "").strip()
        if not token:
            return await call_next(request)

        try:
            user = decode_access_token(token)
        except jwt.ExpiredSignatureError:
            return _error_response(HTTPStatus.UNAUTHORIZED, "token expired")
        except jwt.InvalidTokenError:
            return _error_response(HTTPStatus.UNAUTHORIZED, "invalid token")
        if user is None:
            return _error_response(HTTPStatus.UNAUTHORIZED, "invalid token payload")

        request.state.system_user = user
        return await call_next(request)


def decode_access_token(token: str) -> AuthUser | None:
    if not token:
        return None

    cfg = get_config()
    payload = jwt.decode(
        token,
        key=cfg.system.encrypt_key,
        algorithms=["HS256"],
        options={"require": ["exp", "id", "role", "email", "username", "sub"]},
    )
    if not _is_valid_payload(payload):
        return None
    try:
        return AuthUser.from_payload(payload)
    except (KeyError, TypeError, ValueError):
        return None


def require_user(request: Request) -> AuthUser:
    user = getattr(request.state, "system_user", None)
    if not isinstance(user, AuthUser):
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED.value, detail="missing access token")
    return user


def require_admin(user: AuthUser = Depends(require_user)) -> AuthUser:
    if user.role != SystemUserRole.ADMIN:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN.value, detail="admin role required")
    return user


def _error_response(status_code: HTTPStatus, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code.value,
        content=CommonResponse(code=status_code.value, message=message).model_dump(),
    )


def _is_api_request(request: Request) -> bool:
    path = request.url.path
    return path == _API_PATH_PREFIX or path.startswith(f"{_API_PATH_PREFIX}/")


def _is_valid_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        isinstance(payload.get("id"), int)
        and payload.get("role") in {SystemUserRole.ADMIN.value, SystemUserRole.USER.value}
        and isinstance(payload.get("email"), str)
        and isinstance(payload.get("username"), str)
        and payload.get("sub") == "xuanmu"
    )
