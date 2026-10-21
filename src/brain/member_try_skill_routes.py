"""Whether an approved skill can be tried from Ask, and what it is called (M40.7.2).

One read for the page a skill's card opens: `GET /me/skills/{digest}/try`, gated on the member
grant. The question that carries the skill is `POST /answer` with `try_skill` (see
`brain.api_routes.with_tried_skill`); this only tells the page, before the person types, whether
the install lets them try it, so Ask can say what it is doing in words rather than carry a digest
it cannot explain.

**One answer for every reason a skill cannot be tried.** The switch being off, a digest nobody
holds, a skill nobody approved, one that changed after it was approved and one retired are all
`available: false` with the same sentence and no name, so the route cannot be used to ask which
skills exist or what is being reviewed. The name is given only for a skill the library holds
approved and unchanged, which is a skill whose card any agent running it already shows its model.

Task ids: M40.7.2
"""

from __future__ import annotations

from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, trying_a_skill_is_on
from brain.console.reads import permitted
from brain.console.skill_library import retired_digests
from brain.core.errors import Absent
from brain.member.shell import member_screen
from brain.mine_routes import MEMBER_HOME
from brain.skill_routes import DIGEST_PATTERN, library_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

TRY_PATH: Final = "/me/skills/{digest}/try"

CANNOT_BE_TRIED: Final = (
    "This skill cannot be tried here. Ask an administrator what is switched on."
)

Digest = Annotated[str, Path(pattern=DIGEST_PATTERN)]


class MemberTrySkillView(BaseModel):
    """Whether the skill can be tried, and its name only when it can."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    name: str = ""
    told: str = ""


@router.get(TRY_PATH, response_model=MemberTrySkillView, responses=COMMON_RESPONSES)
async def can_try_a_skill(request: Request, digest: Digest, asked: Asked) -> MemberTrySkillView:
    """Whether this approved skill may be tried from Ask now, in one answer for every no."""
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("trying a skill not answerable", principal=asked.caller.principal.id)
        raise Absent("trying a skill is not answerable for this caller")
    no = MemberTrySkillView(available=False, told=CANNOT_BE_TRIED)
    if not await trying_a_skill_is_on(request.app.state):
        return no
    store = library_of(request)
    one = await store.skill(digest)
    if one is None or one.moved or not one.imported.is_executable():
        return no
    if digest in retired_digests(await store.retirements([digest])):
        return no
    return MemberTrySkillView(available=True, name=one.name)
