"""Telling a transaction who is writing, at what reach, in which request, from the request itself.

`brain.tables.audit.attributed_to` builds the three transaction-local settings a ledgering trigger
reads, and every route that writes a ledgered row has to execute them before the write. The routes
that did it each rebuilt the same three arguments from the request, and four that wrote grants,
legal holds, releases and switches did not do it at all, so their entries carried `0003`'s
placeholders (`brain.ops.write_attribution`). This is the one place the arguments are taken from
the request: the actor is the caller the gate resolved, the reach digest is the caller's live
reach, and the trace is the id the middleware vouched for, read from the log context as
`brain.api_routes.answer` reads it rather than from a header the caller proposed.

Rejected: an argument for the actor. A route that could pass one could pass the subject of the
write instead, which is the defect `tests/unit/test_govern_routes.py` records a mutation finding
in the removal route; the caller is the only actor a request has.

Task ids: M24.3.1
"""

from __future__ import annotations

import structlog
from sqlalchemy import TextClause
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api_routes import Asking
from brain.tables.audit import attributed_to


def trace_of_request() -> str:
    """The trace id the middleware vouched for or minted, or empty outside a request."""
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def of_request(asked: Asking) -> tuple[TextClause, ...]:
    """The three settings for a write this request makes, as `attributed_to` builds them."""
    return attributed_to(
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )


async def attribute(session: AsyncSession, asked: Asking) -> None:
    """Execute them in this session's transaction, before the write they attribute."""
    for statement in of_request(asked):
        await session.execute(statement)
