"""Furnishing an install with the starter skills: eight submissions waiting for a person's review.

`brain.tools.starter_skills` declares the eight skills, and this is the half that owns a session.
It adds each one to the library the way any package is added, as an undecided submission by the
first-run identity, through `brain.ops.skill_store.StoredSkills.add`, so the row, its ledger entry
and its digest are the ones a pasted file would have. **Nothing it writes is approved**: the
deciding row is a person's, and `brain.console.skill_library.decided` refuses the importer
deciding their own, which first run is, so even a mistake here could not approve one. See
`THE_PRODUCT_NEVER_APPROVES_ITS_OWN_STARTER_SKILLS`.

**Behind a switch that ships off, because furnishing is the owner's question** (needs-rupash 185:
whether they arrive for review, which is the recommended answer, or approved by the product, which
this module cannot do). With the switch off nothing is written and the library is exactly what an
administrator added. Turning it on writes the eight at the next start, once: a name the library
already holds, at any version and in any state, is left alone, so a skill an administrator edited,
retired or rejected is never put back, for
`brain.ops.starter_store.WHAT_FURNISHING_WROTE_IS_THE_COMPANYS_AND_IS_NEVER_PUT_BACK`'s reason.

**Never fatal.** The caller (`brain.app.lifespan`) logs what it could not do and serves anyway: a
library that is missing eight starter skills is a library an administrator can still fill.

Task ids: M12.4.7
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.console.skill_library import added, read_package
from brain.ops.features import STARTER_SKILLS_SWITCH, is_on
from brain.ops.skill_store import StoredSkills
from brain.tools.starter_skills import STARTER_SKILLS

#: Why the starter skills are never approved by the product.
THE_PRODUCT_NEVER_APPROVES_ITS_OWN_STARTER_SKILLS: Final = (
    "A skill is the one part of an agent that arrives from outside the company, and an approval is "
    "a named person's statement about exact words. So the starter skills are furnished as "
    "undecided submissions of first run, and the person who reads one, rehearses its examples and "
    "approves it is the name the library records. A skill approved by the product would be a "
    "skill with no approver on every install."
)


async def furnish_skills(
    sessions: async_sessionmaker[AsyncSession], *, actor: str, trace_id: str, now: datetime
) -> tuple[str, ...]:
    """Add every starter skill whose name the library does not hold, and say which were written.

    A name already held, at any version and in any state, is left alone: see the module docstring.
    Idempotent on the digest as well, so two starts together write each once.
    """
    store = StoredSkills(sessions)
    held = {one.name for one in await store.library()}
    wrote: list[str] = []
    for starter in STARTER_SKILLS:
        if starter.name in held:
            continue
        one = added(read_package("SKILL.md", starter.markdown.encode("utf-8")), by=actor, at=now)
        if await store.add(one, ent_hash="", trace_id=trace_id):
            wrote.append(starter.name)
    return tuple(wrote)


async def furnish_skills_when_on(
    sessions: async_sessionmaker[AsyncSession], *, actor: str, trace_id: str, now: datetime
) -> tuple[str, ...]:
    """`furnish_skills`, when the install has switched starter skills on, and nothing when not."""
    async with sessions() as session:
        if not await is_on(session, STARTER_SKILLS_SWITCH):
            return ()
    return await furnish_skills(sessions, actor=actor, trace_id=trace_id, now=now)
