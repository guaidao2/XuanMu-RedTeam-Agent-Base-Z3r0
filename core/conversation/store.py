"""SDK Session backend that keeps SDK tables untouched and stores owner /
nested-call attribution in `agent_message_meta` (1:1 FK to agent_messages.id)."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agents.extensions.memory import SQLAlchemySession
from agents.items import TResponseInputItem
from sqlalchemy import insert, select, text as sql_text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from config import AgentConfig
from core.conversation.compaction import (
    CompactionScope,
    compact_if_needed as compact_session_context_if_needed,
    get_latest_compaction,
)
from core.conversation.projection import ContextProjection, project_context
from model.agent.message_meta import AgentMessageMeta
from utils.sdk_tables import agent_messages


@dataclass(frozen=True, slots=True)
class StoredItem:
    message_id: int
    created_at: datetime
    owner_code: str
    item: dict[str, Any]
    nested_for: str = ""
    nested_call_id: str = ""


class XuanMuSession(SQLAlchemySession):
    def __init__(
        self,
        *,
        session_id: str,
        engine: AsyncEngine,
        viewing_agent_code: str,
        agent_code_to_name: dict[str, str],
        nested_for_agent_code: str = "",
        nested_call_id: str = "",
    ) -> None:
        super().__init__(session_id=session_id, engine=engine)
        self._viewing_agent_code = viewing_agent_code
        self._agent_code_to_name = agent_code_to_name
        self._nested_for = nested_for_agent_code
        self._nested_call_id = nested_call_id if nested_for_agent_code else ""

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        if not items:
            return
        await self._ensure_tables()

        message_payload = [
            {"session_id": self.session_id, "message_data": json.dumps(item, separators=(",", ":"))}
            for item in items
        ]
        owner = self._viewing_agent_code
        nested_for = self._nested_for
        nested_call_id = self._nested_call_id
        meta_table = AgentMessageMeta.__table__

        async def _write() -> None:
            async with self._session_factory() as sess:
                async with sess.begin():
                    await self._ensure_session_row(sess)

                    # bulk insert messages and capture the assigned ids in payload order
                    result = await sess.execute(
                        insert(self._messages).returning(self._messages.c.id),
                        message_payload,
                    )
                    inserted_ids = [row[0] for row in result]

                    if inserted_ids:
                        await sess.execute(insert(meta_table), [
                            {
                                "message_id": mid,
                                "owner_code": owner,
                                "nested_for": nested_for,
                                "nested_call_id": nested_call_id,
                            }
                            for mid in inserted_ids
                        ])

                    await sess.execute(
                        update(self._sessions)
                        .where(self._sessions.c.session_id == self.session_id)
                        .values(updated_at=sql_text("CURRENT_TIMESTAMP"))
                    )

        await self._run_sqlite_write_with_retry(_write)

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        await self._ensure_tables()
        projected = await self._projected_items()
        return projected if limit is None else projected[-limit:]

    async def compact_if_needed(
        self,
        *,
        agent_config: AgentConfig,
        incoming_items: list[TResponseInputItem],
    ) -> None:
        await self._ensure_tables()
        projection = await self._context_projection()
        await compact_session_context_if_needed(
            session_factory=self._session_factory,
            scope=self._compaction_scope(),
            agent_config=agent_config,
            projection=projection,
            incoming_items=incoming_items,
        )

    async def _projected_items(self) -> list[TResponseInputItem]:
        return (await self._context_projection()).items

    async def _context_projection(self) -> ContextProjection:
        async with self._session_factory() as sess:
            stored = await fetch_stored_items(sess, self.session_id)
            compaction = await get_latest_compaction(sess, self._compaction_scope())
        return project_context(
            stored,
            viewing_agent_code=self._viewing_agent_code,
            agent_code_to_name=self._agent_code_to_name,
            nested_for=self._nested_for,
            nested_call_id=self._nested_call_id,
            compaction=compaction,
        )

    async def _ensure_session_row(self, sess: AsyncSession) -> None:
        existing = await sess.execute(
            select(self._sessions.c.session_id).where(self._sessions.c.session_id == self.session_id)
        )
        if existing.scalar_one_or_none() is not None:
            return
        try:
            async with sess.begin_nested():
                await sess.execute(insert(self._sessions).values({"session_id": self.session_id}))
        except IntegrityError:
            # raced with another writer that created the parent row first
            pass

    def _compaction_scope(self) -> CompactionScope:
        return CompactionScope(
            session_id=self.session_id,
            viewer_agent_code=self._viewing_agent_code,
            nested_for=self._nested_for,
            nested_call_id=self._nested_call_id,
        )


async def fetch_stored_items(
    sess: AsyncSession,
    session_id: str,
    *,
    before_id: int | None = None,
    limit: int | None = None,
) -> list[StoredItem]:
    """Load messages + owner attribution for one conversation, in ascending order."""
    meta_table = AgentMessageMeta.__table__
    stmt = (
        select(
            agent_messages.c.id,
            agent_messages.c.created_at,
            agent_messages.c.message_data,
            meta_table.c.owner_code,
            meta_table.c.nested_for,
            meta_table.c.nested_call_id,
        )
        .select_from(
            agent_messages.outerjoin(meta_table, agent_messages.c.id == meta_table.c.message_id)
        )
        .where(agent_messages.c.session_id == session_id)
    )
    if before_id is not None:
        stmt = stmt.where(agent_messages.c.id < before_id)
    if limit is None:
        stmt = stmt.order_by(agent_messages.c.created_at.asc(), agent_messages.c.id.asc())
    else:
        stmt = stmt.order_by(agent_messages.c.created_at.desc(), agent_messages.c.id.desc()).limit(limit)
    result = await sess.execute(stmt)

    items: list[StoredItem] = []
    for row in result.all():
        try:
            item = json.loads(row.message_data)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        items.append(StoredItem(
            message_id=row.id,
            created_at=row.created_at,
            owner_code=row.owner_code or "",
            item=item,
            nested_for=row.nested_for or "",
            nested_call_id=row.nested_call_id or "",
        ))
    return items if limit is None else list(reversed(items))
