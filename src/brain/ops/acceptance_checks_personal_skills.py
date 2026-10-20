"""Install acceptance check for a person's own skills (M40.3.2.1, M40.3.2.2, M40.3.2.3).

A member writes a skill, signed in through the install's own gate, and the check asks **the three
things that must not happen** beside the act that works: that a skill nobody offered is seen by
anybody else, that it is in the library before it is offered, and that offering it is refused to
anyone but its owner. It is asked as the routes My workspace calls, so a skill that is right in a
unit test and wrong on this install's schema, grants and policies fails here.

**The switch is asked both ways.** With `personal_skills` off the add is refused in the switch's own
words and nothing is written; with it on the same press adds. The switch is set on the check's
application state, which is where the routes look first, so the check never turns a real switch on
or off on the install it runs against.

**What is not claimed.** M40.3.2.4 (usable only by this person's own agents until approved) is not
named by this check: nothing a person adds can be pinned to any agent until a named person has
approved the exact bytes, so the half that is proved here is that it reaches nobody, and the half
that lets a person run it on their own agent first is the owner's question. Naming the leaf would
let a green run close it on the refusal alone.

Every name the check writes is the run's: the skill is `acceptance_<run>_personal`, written by
reserved people of acceptance_a, and all of it rolls back with the check.

Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3
"""

from __future__ import annotations

from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1950

A, B = RESERVED_DEPARTMENTS


async def _refusal(call: Any) -> str | None:
    """What a route refused with, in its own words, or None when it answered."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent as refused:
        return str(refused.public_message)
    return None


@check(
    leaves=("M40.3.2.1", "M40.3.2.2", "M40.3.2.3"),
    sentence=(
        "A member writes a skill of their own and sees it listed with where it came from and "
        "what a reader has said; no colleague, no reviewer and no reading of the library finds "
        "it; a colleague cannot offer it; the member offers it and it is then in the library "
        "waiting for a named person; and with the switch off the same press adds nothing."
    ),
)
async def a_member_writes_a_skill_and_nobody_sees_it_until_they_offer_it(h: Harness) -> None:
    from brain.listing import ListAsked
    from brain.member_skill_routes import (
        PERSONAL_SKILLS_ARE_SWITCHED_OFF,
        add_my_skill,
        my_personal_skills,
        offer_my_skill,
    )
    from brain.ops.acceptance_checks_skills import _administrator, _named, _skill_md
    from brain.ops.skill_store import StoredSkills
    from brain.skill_routes import SkillPackageAsked, skill_library

    await h.found_departments()
    c = await console(h)
    maker, colleague = (h.principal(A, role) for role in ("skill_maker", "skill_friend"))
    await h.person(maker, department=A)
    await h.person(colleague, department=A)
    reviewer = await _administrator(h, "personal_skill_review")
    name = _named(h, "personal")
    text = _skill_md(name).decode("utf-8")
    body = SkillPackageAsked(file_name="SKILL.md", content=text, encoding="text")

    async def adding(who: str) -> Any:
        with c.as_route():
            return await add_my_skill(c.request("POST"), body, await c.asked(who, strong=False))

    async def listed(who: str) -> list[Any]:
        with c.as_route():
            page = await my_personal_skills(c.request(), await c.asked(who, strong=False))
        return [one for one in page.skills if one.name == name]

    async def offering(who: str, digest: str) -> Any:
        with c.as_route():
            return await offer_my_skill(c.request("POST"), digest, await c.asked(who, strong=False))

    async def reviewers_page() -> dict[str, Any]:
        from brain.ops.acceptance_skill_console import _asking, _request

        page = await skill_library(_request(c.app), await _asking(h, reviewer), ListAsked())
        return {one.digest: one for one in page.items}

    c.app.state.personal_skills_on = False
    if await _refusal(adding(maker)) != PERSONAL_SKILLS_ARE_SWITCHED_OFF:
        raise CheckFailedError("a skill was added, or refused in other words, with the switch off")
    if await listed(maker):
        raise CheckFailedError("a skill was kept though the switch was off")

    c.app.state.personal_skills_on = True
    made = await adding(maker)
    if getattr(made, "status_code", 0) != 201:
        raise CheckFailedError("a member could not add a skill they wrote")
    mine = await listed(maker)
    if len(mine) != 1:
        raise CheckFailedError("a skill a member added was not on their own list")
    [one] = mine
    if (one.origin, one.review, one.offered) != ("studio", "pending", False):
        raise CheckFailedError("a new skill did not read as written here, unread and not offered")

    if await listed(colleague):
        raise CheckFailedError("a colleague's list showed a skill the member had not offered")
    store = StoredSkills(h.sessions)
    if await store.skill(one.digest) is not None or any(
        found.name == name for found in await store.library()
    ):
        raise CheckFailedError("a skill nobody offered was in the library")
    if one.digest in await reviewers_page():
        raise CheckFailedError("a reviewer was shown a skill nobody had offered")
    refused_for_theirs = await _refusal(offering(colleague, one.digest))
    refused_for_nothing = await _refusal(offering(colleague, "0" * 64))
    if refused_for_theirs is None or refused_for_theirs != refused_for_nothing:
        raise CheckFailedError(
            "a colleague could offer a skill that was not theirs, or tell it apart"
        )

    offered = await offering(maker, one.digest)
    if not offered.offered:
        raise CheckFailedError("a member's own skill was not marked offered when they offered it")
    if (await store.skill(one.digest)) is None:
        raise CheckFailedError("an offered skill was not in the library")
    shown = (await reviewers_page()).get(one.digest)
    if shown is None or shown.review != "pending":
        raise CheckFailedError("an offered skill did not wait for a reviewer, undecided")
    if await _refusal(offering(maker, one.digest)) is None:
        raise CheckFailedError("a skill could be offered twice")
