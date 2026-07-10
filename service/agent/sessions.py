from datetime import datetime
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import delete, exists, func, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.agent.constants import DEFAULT_AGENT_CODE
from core.delegation.subagents import cancel_session_subagent_runs
from core.runtime.session import get_agent_pool, get_agent_registry
from core.sandbox.command_jobs import cancel_session_async_sandbox_commands
from database import get_async_session
from logger import get_logger
from model.agent.sessions import AgentSessionMeta
from model.work_project.projects import WorkProject, WorkProjectOwner
from schema.agent.events import AgentContentEventSchema
from schema.agent.sessions import AgentSessionSummarySchema, SessionType
from schema.system_user.users import SystemUserRole
from service.agent import notifications as agent_notifications
from service.agent.event_log import fetch_timeline_page
from utils.sdk_tables import BOOTSTRAP_SESSION_ID, agent_messages, agent_sessions


logger = get_logger(__name__)

_TITLE_MAX_LEN = 80
DEFAULT_REPLAY_EVENT_PAGE_SIZE = 80

_content_event_adapter: TypeAdapter[AgentContentEventSchema] = TypeAdapter(AgentContentEventSchema)


async def create_session(user_id: int) -> str:
    session_id = str(uuid4())
    async with get_async_session() as session:
        await ensure_sdk_session_row(session, session_id)
        session.add(AgentSessionMeta(
            session_id=session_id,
            session_type=SessionType.CHAT,
            agent_code=DEFAULT_AGENT_CODE,
            owner_id=user_id,
        ))
        await session.commit()
    return session_id


async def update_session_title(
    session_id: str,
    title: str,
    user_id: int,
    user_role: SystemUserRole,
) -> AgentSessionSummarySchema | None:
    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None or not await _can_access_meta(session, meta, user_id, user_role):
            return None
        meta.title = title
        session.add(meta)
        await session.commit()
    return await session_summary(session_id, user_id=user_id, user_role=user_role)


async def ensure_chat_session_meta(
    session_id: str,
    user_text: str,
    requested_agent_code: str | None,
    user_id: int,
    user_role: SystemUserRole,
) -> str:
    # resolution: override > sticky > default
    valid = set(get_agent_registry().codes())
    override = requested_agent_code

    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None or not await _can_access_meta(session, meta, user_id, user_role):
            raise PermissionError("agent session not found")
        existing = meta.agent_code if meta and meta.agent_code in valid else None
        resolved = override or existing or DEFAULT_AGENT_CODE

        if meta.agent_code != resolved:
            meta.agent_code = resolved
            if not meta.title:
                meta.title = _truncate(user_text)
            session.add(meta)
        elif not meta.title:
            meta.title = _truncate(user_text)
            session.add(meta)
        await session.commit()

    return resolved


async def list_sessions(
    limit: int = 100,
    user_id: int = 0,
    user_role: SystemUserRole = SystemUserRole.USER,
    project_id: int | None = None,
) -> list[AgentSessionSummarySchema]:
    return await _list_sessions(
        limit=limit,
        user_id=user_id,
        user_role=user_role,
        project_id=project_id,
    )


async def session_summary(
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> AgentSessionSummarySchema | None:
    async with get_async_session() as session:
        if not await _can_access_session(session, session_id, user_id, user_role):
            return None
    return await _session_summary_by_id(session_id)


async def _list_sessions(
    limit: int,
    user_id: int,
    user_role: SystemUserRole,
    project_id: int | None = None,
) -> list[AgentSessionSummarySchema]:
    meta_table = AgentSessionMeta.__table__
    source = agent_sessions.join(
        meta_table,
        agent_sessions.c.session_id == meta_table.c.session_id,
    ).outerjoin(
        agent_messages,
        agent_sessions.c.session_id == agent_messages.c.session_id,
    )

    stmt = (
        select(
            agent_sessions.c.session_id,
            agent_sessions.c.created_at,
            agent_sessions.c.updated_at,
            func.count(agent_messages.c.id).label("message_count"),
        )
        .select_from(source)
        .where(agent_sessions.c.session_id != BOOTSTRAP_SESSION_ID)
        .group_by(
            agent_sessions.c.session_id,
            agent_sessions.c.created_at,
            agent_sessions.c.updated_at,
        )
        .order_by(agent_sessions.c.updated_at.desc())
        .limit(limit)
    )
    if project_id is None:
        stmt = stmt.where(
            meta_table.c.project_id.is_(None),
            meta_table.c.owner_id == user_id,
        )
    else:
        stmt = stmt.where(meta_table.c.project_id == project_id)
        if user_role != SystemUserRole.ADMIN:
            stmt = stmt.where(
                exists()
                .where(WorkProjectOwner.project_id == project_id)
                .where(WorkProjectOwner.user_id == user_id)
            )

    async with get_async_session() as session:
        rows = (await session.execute(stmt)).all()
        if not rows:
            return []

        session_ids = [row.session_id for row in rows]
        metas = {meta.session_id: meta for meta in (await session.exec(
            select(AgentSessionMeta).where(AgentSessionMeta.session_id.in_(session_ids))
        )).all()}

    return [_summary_from_row(row, metas.get(row.session_id)) for row in rows]


async def _session_summary_by_id(session_id: str) -> AgentSessionSummarySchema | None:
    meta_table = AgentSessionMeta.__table__
    source = agent_sessions.join(
        meta_table,
        agent_sessions.c.session_id == meta_table.c.session_id,
    ).outerjoin(
        agent_messages,
        agent_sessions.c.session_id == agent_messages.c.session_id,
    )
    stmt = (
        select(
            agent_sessions.c.session_id,
            agent_sessions.c.created_at,
            agent_sessions.c.updated_at,
            func.count(agent_messages.c.id).label("message_count"),
        )
        .select_from(source)
        .where(agent_sessions.c.session_id == session_id)
        .group_by(
            agent_sessions.c.session_id,
            agent_sessions.c.created_at,
            agent_sessions.c.updated_at,
        )
    )
    async with get_async_session() as session:
        row = (await session.execute(stmt)).first()
        if row is None:
            return None
        meta = await session.get(AgentSessionMeta, session_id)
    return _summary_from_row(row, meta)


def _summary_from_row(row, meta: AgentSessionMeta | None) -> AgentSessionSummarySchema:
    session_type = meta.session_type if meta else SessionType.CHAT
    return AgentSessionSummarySchema(
        session_id=row.session_id,
        session_type=session_type,
        title=_resolve_title(meta),
        agent_code=meta.agent_code if meta else "",
        owner_id=meta.owner_id if meta else 0,
        project_id=meta.project_id if meta else None,
        selected_sandbox_container_id=meta.selected_sandbox_container_id if meta else None,
        selected_sandbox_container_generation=meta.selected_sandbox_container_generation if meta else 0,
        is_running=meta.is_running if meta else False,
        runtime_agent_code=meta.runtime_agent_code if meta else "",
        runtime_sandbox_container_id=meta.runtime_sandbox_container_id if meta else None,
        runtime_sandbox_container_generation=meta.runtime_sandbox_container_generation if meta else 0,
        run_started_at=meta.run_started_at if meta else None,
        run_finished_at=meta.run_finished_at if meta else None,
        run_error=meta.run_error if meta else "",
        message_count=row.message_count or 0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_running_sessions() -> list[AgentSessionMeta]:
    async with get_async_session() as session:
        return list((await session.exec(
            select(AgentSessionMeta).where(AgentSessionMeta.is_running == True)  # noqa: E712
        )).all())


async def mark_session_running(
    session_id: str,
    *,
    agent_code: str,
    sandbox_container_id: int | None,
    sandbox_container_generation: int,
) -> None:
    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None:
            return
        meta.is_running = True
        meta.runtime_agent_code = agent_code
        meta.runtime_sandbox_container_id = sandbox_container_id
        meta.runtime_sandbox_container_generation = sandbox_container_generation
        meta.run_started_at = datetime.now()
        meta.run_finished_at = None
        meta.run_error = ""
        session.add(meta)
        await session.commit()


async def update_session_sandbox_container(
    session_id: str,
    *,
    sandbox_container_id: int | None,
    sandbox_container_generation: int,
    user_id: int,
    user_role: SystemUserRole,
) -> AgentSessionSummarySchema | None:
    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None or not await _can_access_meta(session, meta, user_id, user_role):
            return None
        meta.selected_sandbox_container_id = sandbox_container_id
        meta.selected_sandbox_container_generation = sandbox_container_generation
        session.add(meta)
        await session.commit()
    return await session_summary(session_id, user_id=user_id, user_role=user_role)


async def mark_session_stopped(session_id: str, *, error: str = "") -> None:
    if await has_outstanding_session_work(session_id):
        return
    await finish_session_run(session_id, error=error)


async def finish_session_run(session_id: str, *, error: str = "") -> None:
    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None:
            return
        meta.is_running = False
        meta.run_finished_at = datetime.now()
        meta.run_error = _truncate_error(error)
        session.add(meta)
        await session.commit()


async def mark_sessions_stopped(session_ids: list[str], *, error: str = "") -> None:
    if not session_ids:
        return
    active_session_ids = {
        session_id for session_id in session_ids
        if await has_outstanding_session_work(session_id)
    }
    async with get_async_session() as session:
        metas = (await session.exec(
            select(AgentSessionMeta).where(AgentSessionMeta.session_id.in_(session_ids))
        )).all()
        for meta in metas:
            if meta.session_id in active_session_ids:
                continue
            meta.is_running = False
            meta.run_finished_at = datetime.now()
            meta.run_error = _truncate_error(error)
            session.add(meta)
        await session.commit()


async def force_mark_session_stopped(session_id: str, *, error: str = "") -> None:
    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None:
            return
        meta.is_running = False
        meta.run_finished_at = datetime.now()
        meta.run_error = _truncate_error(error)
        session.add(meta)
        await session.commit()


async def has_outstanding_session_work(session_id: str) -> bool:
    # Single source of truth: every background task (sub-agent / async job)
    # registers an outstanding notification obligation for its whole lifetime,
    # so the notification table alone reflects session liveness.
    return await agent_notifications.has_active_session_notifications(session_id=session_id)


async def replay_session_events(
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> tuple[list[AgentContentEventSchema], bool, int | None] | None:
    return await replay_session_events_page(
        session_id=session_id,
        user_id=user_id,
        user_role=user_role,
        before_seq=None,
        limit=DEFAULT_REPLAY_EVENT_PAGE_SIZE,
    )


async def replay_session_events_page(
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
    *,
    before_seq: int | None,
    limit: int,
) -> tuple[list[AgentContentEventSchema], bool, int | None] | None:
    """Return one turn-aligned page of the persisted UI timeline, by seq cursor.

    The timeline log already stores the exact wire events (with stable identity
    and seq), so replay is a straight read + validate — no SDK-message
    derivation, identity remapping, or content-based de-duplication.
    """
    async with get_async_session() as session:
        if not await _can_access_session(session, session_id, user_id, user_role):
            return None

    await get_agent_pool().flush_timeline(session_id)

    items, has_more, next_before_seq = await fetch_timeline_page(
        session_id,
        before_seq=before_seq,
        limit=max(1, limit),
    )

    events: list[AgentContentEventSchema] = []
    for seq, payload in items:
        payload["seq"] = seq
        try:
            events.append(_content_event_adapter.validate_python(payload))
        except Exception:
            logger.debug("skipping malformed timeline payload session=%s seq=%s", session_id, seq)
    return events, has_more, next_before_seq


async def can_access_session(session_id: str, user_id: int, user_role: SystemUserRole) -> bool:
    async with get_async_session() as session:
        return await _can_access_session(session, session_id, user_id, user_role)


async def get_session_meta(session_id: str) -> AgentSessionMeta | None:
    async with get_async_session() as session:
        return await session.get(AgentSessionMeta, session_id)


async def project_id_for_session(session_id: str) -> int | None:
    meta = await get_session_meta(session_id)
    return meta.project_id if meta is not None else None


async def delete_session(
    session_id: str,
    user_id: int = 0,
    user_role: SystemUserRole = SystemUserRole.USER,
    *,
    allow_project_session: bool = False,
) -> bool:
    if not session_id:
        return False

    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None or not await _can_access_meta(session, meta, user_id, user_role):
            return False
        if meta.project_id is not None and not allow_project_session:
            return False

    await cancel_session_subagent_runs(session_id)
    await cancel_session_async_sandbox_commands(session_id)
    await get_agent_pool().discard(session_id)

    async with get_async_session() as session:
        records_deleted = await _delete_session_records_in_tx(session, session_id)
        await session.commit()

    if records_deleted:
        logger.info("agent session deleted: %s", session_id)
    return records_deleted


async def cancel_sessions(session_ids: list[str], reason: str) -> None:
    for session_id in session_ids:
        await get_agent_pool().cancel_all(session_id)
    await mark_sessions_stopped(session_ids, error=reason)


async def _delete_session_records_in_tx(session: AsyncSession, session_id: str) -> bool:
    # one DELETE drops the SDK session row and the FK CASCADE chain takes
    # care of agent_messages, agent_message_meta, and agent_session_meta
    result = await session.execute(
        delete(agent_sessions).where(agent_sessions.c.session_id == session_id)
    )
    return (result.rowcount or 0) > 0


async def ensure_sdk_session_row(session: AsyncSession, session_id: str) -> None:
    # placeholder row owned by the SDK; required so AgentSessionMeta's FK can
    # bind and so list_sessions can surface freshly-created empty conversations
    await session.execute(
        text(
            "INSERT INTO agent_sessions (session_id) VALUES (:sid) "
            "ON CONFLICT (session_id) DO NOTHING"
        ),
        {"sid": session_id},
    )


async def _can_access_session(
    session: AsyncSession,
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    meta = await session.get(AgentSessionMeta, session_id)
    return meta is not None and await _can_access_meta(session, meta, user_id, user_role)


async def _can_access_meta(
    session: AsyncSession,
    meta: AgentSessionMeta,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    if meta.project_id is None:
        return meta.owner_id == user_id
    if await session.get(WorkProject, meta.project_id) is None:
        return False
    if user_role == SystemUserRole.ADMIN:
        return True
    return await session.get(WorkProjectOwner, (meta.project_id, user_id)) is not None


def _resolve_title(meta: AgentSessionMeta | None) -> str:
    if meta is None:
        return ""
    return meta.title or ("Project session" if meta.session_type == SessionType.PROJECT else "Untitled session")


def _truncate(value: str) -> str:
    value = value.strip().replace("\n", " ")
    return value if len(value) <= _TITLE_MAX_LEN else value[: _TITLE_MAX_LEN - 1] + "..."


def _truncate_error(value: str) -> str:
    value = value.strip().replace("\n", " ")
    return value if len(value) <= 500 else value[:499] + "..."
