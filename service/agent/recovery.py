from core.runtime.session import get_agent_pool
from logger import get_logger
from middleware.auth import AuthUser
from service.agent import sessions as agent_sessions
from service.system_user.users import query_system_user_by_id
from service.agent.runtime import build_runtime_context
from service.work_project.projects import can_run_work_project_session


logger = get_logger(__name__)


async def recover_pending_sessions() -> None:
    pending = await agent_sessions.list_running_sessions()
    if not pending:
        return
    for session in pending:
        if not await agent_sessions.has_outstanding_session_work(session.session_id):
            await agent_sessions.force_mark_session_stopped(
                session.session_id,
                error="Agent runtime was interrupted by backend restart.",
            )
            continue
        user = await query_system_user_by_id(session.owner_id)
        if user is None:
            await agent_sessions.force_mark_session_stopped(
                session.session_id,
                error="Agent session owner no longer exists.",
            )
            continue
        auth_user = AuthUser(id=user.id, role=user.role, email=user.email, username=user.username)
        if not await can_run_work_project_session(session.session_id, auth_user.id, auth_user.role):
            await agent_sessions.force_mark_session_stopped(
                session.session_id,
                error="WorkProject is canceled.",
            )
            continue
        agent_code = session.runtime_agent_code or session.agent_code
        runtime = await get_agent_pool().get_or_create(session.session_id)
        context = await build_runtime_context(
            session.session_id,
            auth_user,
            session.runtime_sandbox_container_id,
            agent_code,
        )
        await runtime.start_notification_recovery(context)
