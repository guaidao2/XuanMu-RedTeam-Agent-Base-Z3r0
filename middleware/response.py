import json
from http import HTTPStatus

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from logger import get_logger
from schema.common.responses import CommonResponse


logger = get_logger(__name__)


class CommonResponseStatusMiddleware:
    """sync HTTP status with CommonResponse.code when handlers return wrapped data"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_api_scope(scope):
            await self.app(scope, receive, send)
            return

        response_start: Message | None = None
        body_parts: list[bytes] = []
        passthrough = False

        async def send_wrapper(message: Message) -> None:
            nonlocal passthrough, response_start

            if message["type"] == "http.response.start":
                response_start = message
                passthrough = not _is_json_response(message)
                if passthrough:
                    await send(message)
                return

            if message["type"] != "http.response.body" or response_start is None:
                await send(message)
                return

            if passthrough:
                await send(message)
                return

            body_parts.append(message.get("body", b""))
            if message.get("more_body", False):
                return

            body = b"".join(body_parts)
            response_start = _sync_common_response_status(response_start, body)
            await send(response_start)
            await send({**message, "body": body})

        await self.app(scope, receive, send_wrapper)


def _is_api_scope(scope: Scope) -> bool:
    path = str(scope.get("path") or "")
    return path == "/api" or path.startswith("/api/")


def _sync_common_response_status(response_start: Message, body: bytes) -> Message:
    if response_start.get("status") != 200:
        return response_start

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return response_start

    if not isinstance(payload, dict):
        return response_start

    code = payload.get("code")
    if not isinstance(code, int) or not 100 <= code <= 599:
        return response_start

    return {**response_start, "status": code}


def _is_json_response(response_start: Message) -> bool:
    for raw_key, raw_value in response_start.get("headers", []):
        if raw_key.lower() == b"content-type":
            return b"application/json" in raw_value.lower()
    return False


def _serialize_validation_errors(errors: list[dict]) -> list[dict]:
    serialized_errors: list[dict] = []
    for error in errors:
        serialized_error = dict(error)
        ctx = serialized_error.get("ctx")
        if isinstance(ctx, dict):
            serialized_error["ctx"] = {key: str(value) for key, value in ctx.items()}
        serialized_errors.append(serialized_error)
    return serialized_errors


async def request_validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """wrap request validation errors in CommonResponse"""
    return JSONResponse(
        status_code=422,
        content=CommonResponse(
            code=422,
            message="request validation failed",
            data=_serialize_validation_errors(exc.errors()),
        ).model_dump(),
    )


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """wrap framework HTTP errors in CommonResponse"""
    return JSONResponse(
        status_code=exc.status_code,
        content=CommonResponse(
            code=exc.status_code,
            message=str(exc.detail),
        ).model_dump(),
        headers=exc.headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """log unexpected API failures and return the public CommonResponse shape"""
    logger.error(
        "unhandled request failed: %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
        content=CommonResponse(
            code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
            message="internal server error",
        ).model_dump(),
    )
