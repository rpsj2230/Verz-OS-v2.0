"""A person's own skills: add one, see where it stands, and offer it to the department.

Four routes for the person asking, none taking a parameter that names whose list it is, each gated
on the member grant (`brain.member.shell`) and nothing administrative: **list** your skills,
**add** one by pasting or writing it, **bring** one from a repository at a commit or an address, and
**offer** one to the department's library. `brain.member_library` decided all of it (`my_skills`,
`add_skill`, `submit_for_review`) and had no caller; `brain.ops.personal_skill_store` keeps it.

**A skill added here is the person's alone until they offer it, and then it is in the review queue
like any other, undecided.** The skill is stored where every skill is, so the bytes a reviewer later
approves are the bytes this person wrote and the digest is the same; what makes it theirs is one row
(`0232`), and `brain.ops.skill_store.library_of` leaves a skill with that row and no offer out of
every reading of the library. A colleague, a reviewer and an administrator therefore find nothing:
not a row, not a name, not a count, and a request for it by key is answered as for a key that was
never made (`DENIED_AND_ABSENT_ARE_ONE_ANSWER`). The one thing that is not hidden is a collision: a
person adding bytes that anyone already holds is told "already held", never by whom.

**Nothing here approves anything and nothing here makes a skill run.** Adding stores undecided
bytes (`added` has no parameter for a state or a reviewer), and a skill is pinned to an agent only
once a named person has approved exactly those bytes (`pin_skill`), which no route here can do. So
"usable only by this person's own agents until approved" (M40.3.2.4) holds by being usable by no
agent at all, which is stronger than the leaf and narrower than it reads: whether a person may run
their own skill on their own agent before a reviewer has read it is the owner's question, reported
beside the leaf and not decided here.

**The import fetches through the install's own fetcher and host list**, the same `fetched_package`
the administrator's import uses, so the address rule and the host list apply to every hop and a
member cannot reach an address an administrator could not. It is behind the `personal_skills` switch
(off), because opening the fetcher to every member is a decision an install makes.

**A person holds at most `MOST_UNOFFERED` skills they have not offered**, because a skill is never
deleted (`0232` grants no DELETE): without a bound one person's pastes would accumulate for ever.

**The switch gates adding and offering and never reading.** A person's skills stay listed with the
switch off, as does the sentence saying why they cannot add another.

Rejected: letting a member's skill into the library at once and marking it. Every reader of the
library would then have to remember to look at the mark, which is how an unfinished skill ends up
assigned.

Rejected: a route to withdraw an offer. A skill in the review queue is read by a person the moment
it is offered, and taking it back would be the one act that makes the queue unreliable for them.

Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3, M40.3.2.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import trace_of_request
from brain.console.reads import permitted
from brain.console.skill_library import (
    LibrarySkill,
    Package,
    SkillLibraryError,
    added,
    another_spelling,
    read_package,
    runnable_here,
)
from brain.core.errors import Absent, Failed
from brain.member.shell import member_screen
from brain.member_library import (
    LibraryError,
    Origin,
    PersonalSkill,
    add_skill,
    my_skills,
    standing_of,
    submit_for_review,
)
from brain.mine_routes import MEMBER_HOME
from brain.ops.features import is_on
from brain.ops.features_declared.personal_skills import PERSONAL_SKILLS
from brain.ops.personal_skill_store import (
    MOST_UNOFFERED,
    Claim,
    PersonalEntry,
    StoredPersonalSkills,
)
from brain.ops.skill_store import MAX_LIBRARY
from brain.routing_routes import sessions_of
from brain.skill_routes import (
    Digest,
    SkillImportAsked,
    SkillPackageAsked,
    fetched_package,
    library_of,
    package_bytes,
    sandbox_of,
)

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

MY_SKILLS_PATH: Final = "/me/skills"
IMPORT_PATH: Final = "/me/skills/imports"
OFFER_PATH: Final = "/me/skills/{digest}/offer"

#: How many of a person's own skills one answer carries. Past it the answer says there are more and
#: never how many.
MOST_SHOWN: Final = 100

PERSONAL_SKILLS_ARE_SWITCHED_OFF: Final = (
    "Adding and offering your own skills is switched off on this install. The skills you already "
    "added stay yours and stay listed here."
)

DENIED_AND_ABSENT_ARE_ONE_ANSWER: Final = (
    "a skill that is not yours, one that was never made and one whose key was typed wrong are "
    "answered alike, so this route cannot be used to ask what other people have written"
)

ALREADY_HELD: Final = (
    "this skill was not added: these exact words are already held. If you wrote them yourself, "
    "change something in them first; if you need the skill that holds them, ask the person who "
    "looks after the department's skills."
)

TOO_MANY: Final = (
    f"this skill was not added: you hold {MOST_UNOFFERED} skills you have not offered yet, which "
    "is as many as one person keeps. Offer one to the department to make room."
)

CATEGORIES_ARE_THE_LIBRARYS: Final = (
    "this skill was not added: categories are set by the person who looks after the department's "
    "library, once it is offered"
)

ALREADY_OFFERED: Final = "this skill was already offered to the department"


@runtime_checkable
class PersonalSkills(Protocol):
    """What these routes need of the store, so a test can stand in for the database."""

    async def mine(self, owner_id: str, limit: int = ...) -> tuple[PersonalEntry, ...]: ...

    async def one_of_mine(self, owner_id: str, digest: str) -> PersonalEntry | None: ...

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> Claim: ...

    async def offer(self, owner_id: str, digest: str, at: datetime) -> bool: ...


def store_of(request: Request) -> PersonalSkills:
    """`app.state.personal_skills` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "personal_skills", None)
    if isinstance(found, PersonalSkills):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredPersonalSkills(factory)


async def personal_skills_are_on(request: Request) -> bool:
    """Whether adding and offering a skill of one's own is switched on. Off until turned on.

    Asked before an add and an offer, and never before a reading: see
    `brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.
    """
    found = getattr(request.app.state, "personal_skills_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        return False
    async with factory() as session:
        return await is_on(session, PERSONAL_SKILLS)


def _not_answerable() -> Absent:
    return Absent("your skills are not answerable for this caller")


def _refused(reason: str) -> Absent:
    """A refusal for somebody who asked to do something, saying what to change."""
    return Absent(reason, public_message=reason)


def _guard(asked: Asked) -> None:
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own skills not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()


class MemberOwnSkillView(BaseModel):
    """One skill this person holds: what it is, where it came from and what it can do now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    digest: str
    name: str
    version: str
    #: `studio`, `repository` or `url`.
    origin: str
    #: Where it came from in the source's own spelling, so two forks of one skill can be told apart.
    location: str
    #: `approved`, `pending`, `rejected` or `changed`.
    review: str
    offered: bool
    offered_at: datetime | None = None
    made_at: datetime
    #: What it can do now, in a sentence.
    standing: str
    may_offer: bool


class MemberOwnSkillsView(BaseModel):
    """This person's own skills, and whether they may add or offer one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skills: list[MemberOwnSkillView]
    more: bool = False
    may_add: bool
    #: Why they cannot add or offer, in a sentence; empty when they can.
    unavailable: str = ""


def _view(entry: PersonalEntry, owner_id: str, *, on: bool) -> MemberOwnSkillView:
    one = entry.skill
    row = my_skills(
        [PersonalSkill(owner_id=owner_id, imported=one.imported, digest=one.digest)],
        principal_id=owner_id,
    )[0]
    return MemberOwnSkillView(
        digest=row.digest,
        name=row.name,
        version=row.version,
        origin=row.origin.value,
        location=row.location,
        review=row.review.value,
        offered=entry.offered,
        offered_at=entry.offered_at,
        made_at=entry.made_at,
        standing=standing_of(row.review, offered=entry.offered),
        may_offer=on and not entry.offered,
    )


@router.get(MY_SKILLS_PATH, response_model=MemberOwnSkillsView, responses=COMMON_RESPONSES)
async def my_personal_skills(request: Request, asked: Asked) -> MemberOwnSkillsView:
    """This person's own skills, offered or not, newest first."""
    _guard(asked)
    me = asked.caller.principal.id
    on = await personal_skills_are_on(request)
    found = await store_of(request).mine(me, MOST_SHOWN + 1)
    return MemberOwnSkillsView(
        skills=[_view(one, me, on=on) for one in found[:MOST_SHOWN]],
        more=len(found) > MOST_SHOWN,
        may_add=on,
        unavailable="" if on else PERSONAL_SKILLS_ARE_SWITCHED_OFF,
    )


async def _kept(request: Request, asked: Asked, package: Package, origin: Origin) -> JSONResponse:
    """Store one package as this person's own, or refuse saying why. Shared by both ways in."""
    me = asked.caller.principal.id
    try:
        one = added(package, by=me, at=asked.now)
        add_skill(owner_id=me, imported=one.imported, origin=origin)
    except (SkillLibraryError, LibraryError) as refused:
        raise _refused(str(refused)) from None
    store = store_of(request)
    claim = await store.add(one, ent_hash=asked.reach.ent_hash(), trace_id=trace_of_request())
    if claim is Claim.HELD_ALREADY:
        raise _refused(ALREADY_HELD)
    if claim is Claim.TOO_MANY:
        raise _refused(TOO_MANY)
    entry = await store.one_of_mine(me, one.digest)
    if entry is None:
        # Written a moment ago by this person and not found: the database is not answering.
        raise Failed("a skill just stored could not be read back")
    log.info("own skill added", origin=origin.value, principal=me)
    status = 200 if claim is Claim.YOURS_ALREADY else 201
    return JSONResponse(
        status_code=status, content=_view(entry, me, on=True).model_dump(mode="json")
    )


@router.post(
    MY_SKILLS_PATH, status_code=201, response_model=MemberOwnSkillView, responses=COMMON_RESPONSES
)
async def add_my_skill(request: Request, body: SkillPackageAsked, asked: Asked) -> JSONResponse:
    """Keep a pasted or written skill as this person's own, undecided."""
    _guard(asked)
    if not await personal_skills_are_on(request):
        raise _refused(PERSONAL_SKILLS_ARE_SWITCHED_OFF)
    if body.categories:
        raise _refused(CATEGORIES_ARE_THE_LIBRARYS)
    try:
        package = runnable_here(
            read_package(body.file_name, package_bytes(body)), sandbox=sandbox_of(request)
        )
    except SkillLibraryError as refused:
        raise _refused(str(refused)) from None
    return await _kept(request, asked, package, Origin.STUDIO)


@router.post(
    IMPORT_PATH, status_code=201, response_model=MemberOwnSkillView, responses=COMMON_RESPONSES
)
async def import_my_skill(request: Request, body: SkillImportAsked, asked: Asked) -> JSONResponse:
    """Bring a skill from a repository at a commit or from an address, as this person's own.

    The switch is asked before anything is fetched, so a person who may not add cannot use this
    server to reach an address.
    """
    _guard(asked)
    if not await personal_skills_are_on(request):
        raise _refused(PERSONAL_SKILLS_ARE_SWITCHED_OFF)
    if body.categories:
        raise _refused(CATEGORIES_ARE_THE_LIBRARYS)
    package = await fetched_package(request, body)
    try:
        runnable_here(package, sandbox=sandbox_of(request))
    except SkillLibraryError as refused:
        raise _refused(str(refused)) from None
    return await _kept(
        request, asked, package, Origin.REPOSITORY if body.kind == "github" else Origin.URL
    )


@router.post(OFFER_PATH, response_model=MemberOwnSkillView, responses=COMMON_RESPONSES)
async def offer_my_skill(request: Request, digest: Digest, asked: Asked) -> MemberOwnSkillView:
    """Offer one of this person's own skills to the department's library for a person to read."""
    _guard(asked)
    me = asked.caller.principal.id
    store = store_of(request)
    entry = await store.one_of_mine(me, digest)
    if entry is None:
        log.info("own skill not offerable", principal=me)
        raise _not_answerable()
    if not await personal_skills_are_on(request):
        raise _refused(PERSONAL_SKILLS_ARE_SWITCHED_OFF)
    if entry.offered:
        raise _refused(ALREADY_OFFERED)
    one = entry.skill
    try:
        submit_for_review(
            PersonalSkill(owner_id=me, imported=one.imported, digest=one.digest), at=asked.now
        )
    except LibraryError as refused:
        raise _refused(str(refused)) from None
    held = await library_of(request).library(MAX_LIBRARY)
    if another_spelling(one.imported.skill, held) is not None:
        raise _refused(
            "this skill was not offered: the library already holds a skill whose name is this "
            "one spelt differently. Name yours the same way if it is a new version of it."
        )
    if not await store.offer(me, digest, asked.now):
        raise _refused(ALREADY_OFFERED)
    log.info("own skill offered", principal=me)
    return _view(PersonalEntry(skill=one, made_at=entry.made_at, offered_at=asked.now), me, on=True)
