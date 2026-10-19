"""Whether a person may start an agent's draft from a description (M20.5.3).

One question, asked in one place, by the two routes that need it: the one that does the describing
and the drafts page, which says whether to offer it. **A page that offered a control its route would
refuse is the shape `brain.console.role_surfaces` rejected**, so the page asks the same question the
route does and not a second one.

Task ids: M20.5.3
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.features import is_on
from brain.ops.features_declared.agent_describe import DESCRIBE_AN_AGENT


async def describe_is_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether describing is switched on now. Off until an administrator turns it on."""
    async with sessions() as session:
        return await is_on(session, DESCRIBE_AN_AGENT)
