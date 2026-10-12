"""Turning one of the product's feature switches on inside an install acceptance check.

A feature ships switched off, so a check about one has to switch it on, and has to do it where
nothing of it survives: in the check's own transaction, with the attribution every settings write
carries, rolled back with the rest. The install's own switch is never touched. Several checks need
it, so it is written once.

Task ids: M38.5.1
"""

from __future__ import annotations

from brain.ops.acceptance_run import Harness
from brain.ops.features import Feature, switch


async def switched(h: Harness, feature: Feature, *, on: bool) -> None:
    """`feature`'s switch set in the check's transaction, and rolled back with the rest of it."""
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.tables.audit import attributed_to

    async with h.sessions() as session:
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        await switch(session, feature, on=on, by=h.actor)
        await session.commit()
