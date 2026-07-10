from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from agents import set_tracing_disabled
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import ROOT_PATH, get_config

# ── 兼容补丁：新版 openai InputTokensDetails 字段变更 ──
try:
    from agents import usage as _agents_usage
    import openai.types.completion_usage as _openai_usage
    _agents_usage.InputTokensDetails = _openai_usage.InputTokensDetails
except Exception:
    pass

from core.delegation.subagents import start_subagent_runtime, stop_subagent_runtime
from core.runtime.session import get_agent_pool
from database import close_engine, create_all_tables, init_engine
from logger import get_logger
from middleware.auth import JwtAuthMiddleware
from middleware.response import (
    CommonResponseStatusMiddleware,
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from router.agent.agents import router as agent_router
from router.agent.sessions import router as agent_session_router
from router.common.fallback import api_not_found_router
from router.egress_proxy.proxies import router as egress_proxy_router
from router.host.hosts import router as host_router
from router.sandbox.containers import router as sandbox_container_router
from router.sandbox.images import router as sandbox_image_router
from router.system_config.config import router as system_config_router
from router.system_user.users import router as system_user_router
from router.work_project.projects import router as work_project_router
from schema.system_user.users import SystemUserRole
from service.agent.recovery import recover_pending_sessions
from service.system_user.users import create_system_user, query_system_user_by_username
from utils.urllib3_compat import install_urllib3_closed_file_close_patch


logger = get_logger(__name__)

install_urllib3_closed_file_close_patch()

WEB_DIST_PATH = ROOT_PATH / "web" / "dist-app"
API_PREFIX = "/api"


async def _bootstrap_admin_user() -> None:
    bootstrap = get_config().system.bootstrap_admin
    if not bootstrap.enabled:
        logger.debug("bootstrap admin user skipped")
        return

    if await query_system_user_by_username(bootstrap.username) is not None:
        logger.debug("bootstrap admin user already exists: %s", bootstrap.username)
        return

    await create_system_user(
        username=bootstrap.username,
        password=bootstrap.password,
        email=bootstrap.email,
        role=SystemUserRole.ADMIN,
    )
    logger.info("bootstrap admin user created: %s", bootstrap.username)





def _mount_frontend(app: FastAPI) -> None:
    """serve built frontend assets when web/dist-app exists"""
    index_path = WEB_DIST_PATH / "index.html"
    if not index_path.is_file():
        logger.debug("frontend static route skipped: %s not found", index_path)
        return

    assets_path = WEB_DIST_PATH / "assets"
    if assets_path.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_path), name="web-assets")

    async def serve_frontend(path: str = "") -> FileResponse:
        return FileResponse(index_path)

    app.add_api_route("/", serve_frontend, methods=["GET"], include_in_schema=False)
    app.add_api_route("/{path:path}", serve_frontend, methods=["GET"], include_in_schema=False)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    try:
        init_engine()
        await create_all_tables()
        await _bootstrap_admin_user()

        set_tracing_disabled(True)
        await start_subagent_runtime()
        await recover_pending_sessions()
        await get_agent_pool().start()

        yield
    except Exception:
        # surface startup failures; the finally block below would otherwise hide them
        logger.exception("lifespan startup failed")
        raise
    finally:
        await stop_subagent_runtime()
        await get_agent_pool().stop()
        await close_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="XuanMu RedTeam Agent - 开源红队多智能体协作平台，用于授权安全评估、代码审计、渗透测试与安全研究。",
        version="0.2.1",
        lifespan=lifespan,
    )

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    logger.debug("exception handlers added")

    app.add_middleware(CommonResponseStatusMiddleware)
    app.add_middleware(JwtAuthMiddleware)
    logger.debug("middleware added")

    app.include_router(system_user_router, prefix=API_PREFIX)
    app.include_router(host_router, prefix=API_PREFIX)
    app.include_router(egress_proxy_router, prefix=API_PREFIX)
    app.include_router(sandbox_image_router, prefix=API_PREFIX)
    app.include_router(sandbox_container_router, prefix=API_PREFIX)
    app.include_router(work_project_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(agent_session_router, prefix=API_PREFIX)
    app.include_router(system_config_router, prefix=API_PREFIX)
    app.include_router(api_not_found_router, prefix=API_PREFIX)
    logger.debug("api router added")

    _mount_frontend(app)
    return app
