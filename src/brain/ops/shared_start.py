"""Whether this install shares the start of a model request, and which tools that start may name.

`brain.gate.shared_start` says what the shared start may hold (needs-rupash 175, option A, decided
2026-10-12). This is the half that reads the install's switch, because a run that changes the bytes
every agent run sends to a model is a genuinely new behaviour and ships switched off: with the
switch off a run sends the one system message it always did.

**Never fatal and never wider.** A process with no database, or whose switch cannot be read,
shares nothing, which is the behaviour before this existed; the switch can only narrow what the
first message holds, and the person is shown every tool they were shown before, in the same words.

Task ids: M3.7.2
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.shared_start import universal_tools
from brain.ops.features import SHARED_TOOL_START, is_on
from brain.tools.registry import ToolRegistry


async def universal_when_on(
    sessions: async_sessionmaker[AsyncSession] | None, registry: ToolRegistry
) -> frozenset[str]:
    """The tools the shared start may name on this install, or none while the switch is off."""
    if sessions is None:
        return frozenset()
    async with sessions() as session:
        if not await is_on(session, SHARED_TOOL_START):
            return frozenset()
    return universal_tools(registry)
