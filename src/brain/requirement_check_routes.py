"""The Requirement checks screen over HTTP: every requirement in the register, and what was seen.

Four leaves ask each area's requirements to be "demonstrated on an install by a person, and each
check is recorded against the requirement it proves": permissions (M1.8.8), departments
(M2.3.2), models (M5.6.5) and observability (M24.3.6). The register is
`docs/requirements/register.json`, shipped in the image, and a check is a row in
`ops.requirement_check`. This screen puts the two side by side: pick an area, read each
requirement in the owner's words, and record passed or failed with a sentence about what was done.

**One authority, `admin:requirement_check`, over everything, for reading and for recording.** The
register is the same in every install and says nothing about this company, but the checks are a
record of what this install was seen to do, including what failed, which is a map of where it is
weak. So the screen is not a read every administrator's screen list carries; it is granted with the
other administration capabilities, and `brain.identity.administration_reconciliation` grants it to
an administrator appointed before it existed.

**Every area can be checked, and four are named.** `CHECKED_BY` maps an area to the leaf that asks
for its checks, so the screen can say which task a row's check proves; an area with no leaf is
still checkable, because M24.3.4 asks for its audit and tracing checks to be "recorded" in the same
sense and a mechanism that refused an area would be a narrowing nobody asked for.

**Counts are fine here, and that is said because nearly nowhere else they are.** The register is
product-wide and every reader of this screen sees all of it, so "twelve of eighty passed" hides
nothing from anybody; the rule against counts is about entries a reader may not see.

**A check is refused, in words and before anything is written, when it names an id the register
does not carry**, because a check against nothing is a check nobody can read back. A check that
names an id a later release retired stays in the table, for `brain.tables.requirement_check`'s
reason, and drops off this screen, which lists the register's rows and has no row to show it by.

Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.requirements import REGISTER_IN_DOCS, Register, Requirement, load_register
from brain.routing_routes import sessions_of
from brain.tables.requirement_check import (
    NOTE_CHARS,
    REQUIREMENT_ID_CHARS,
    REQUIREMENT_ID_PATTERN,
    CheckOutcome,
    RequirementCheckRow,
)

log = structlog.get_logger()

# ------------------------------------------------------------------------ the figures

#: Reading the screen and recording a check. An `admin:` verb, over everything.
REQUIREMENT_CHECK_AUTHORITY: Final = Capability(value="admin:requirement_check")

#: Where the screen is read and a check recorded.
CHECKS_PATH: Final = "/requirements/checks"

#: The leaf that asks for each area's checks, by the area's name in the register.
CHECKED_BY: Final[Mapping[str, str]] = {
    "Permissions": "M1.8.8",
    "Departments": "M2.3.2",
    "Models": "M5.6.5",
    "Observability": "M24.3.6",
}

#: Where the register lives in the image, and in a checkout: `docs/` beside `src/`.
DOCS: Final = Path(__file__).resolve().parents[2] / "docs"

#: What the screen says, once, about what a check is.
A_CHECK_IS_WHAT_A_PERSON_SAW_ON_THIS_INSTALL: Final = (
    "A check is what a person saw this install do, on the release it was running, recorded by "
    "them. A later check supersedes an earlier one and never edits it, so a requirement that "
    "passed and then failed shows both. Record what you did and what you saw, never a value "
    "from the company's data."
)

NO_REGISTER: Final = (
    "This release carries no requirements register, so there is nothing to check against."
)

# ------------------------------------------------------------------------ the shapes


class RequirementCheckView(BaseModel):
    """One recorded check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    outcome: CheckOutcome
    checked_by: str
    checked_at: datetime
    release_commit: str | None
    note: str


class RequirementView(BaseModel):
    """One requirement in the owner's words, and the newest check against it, if any."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    requirement: str
    source: str
    latest: RequirementCheckView | None


class RequirementAreaView(BaseModel):
    """One area of the register and where its checks stand. Counts: see the module docstring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    area: str
    #: The leaf that asks for this area's checks, or None when none does.
    proves: str | None
    requirements: int
    passed: int
    failed: int
    unchecked: int


class RequirementChecksView(BaseModel):
    """The screen: every area, and one area's requirements with their newest checks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    areas: list[RequirementAreaView]
    area: str | None
    requirements: list[RequirementView]
    #: The commit this process runs, which a check recorded now is recorded against.
    release_commit: str | None
    told: str


class RequirementCheckAsked(BaseModel):
    """A check to record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str = Field(max_length=REQUIREMENT_ID_CHARS, pattern=REQUIREMENT_ID_PATTERN)
    outcome: CheckOutcome
    note: str = Field(min_length=1, max_length=NOTE_CHARS)


# ------------------------------------------------------------------------ the decisions


def may_check(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds `REQUIREMENT_CHECK_AUTHORITY` over everything, at this instant."""
    scope = reach.scope_for(REQUIREMENT_CHECK_AUTHORITY, now)
    return scope is not None and scope.is_unrestricted()


def areas_of(
    register: Register, latest: Mapping[str, RequirementCheckView]
) -> list[RequirementAreaView]:
    """Every area in the register, in the order its first row appears, with where it stands."""
    order: dict[str, list[Requirement]] = {}
    for row in register.requirements:
        order.setdefault(row.area, []).append(row)
    views: list[RequirementAreaView] = []
    for area, rows in order.items():
        outcomes = [latest[row.id].outcome for row in rows if row.id in latest]
        passed = sum(1 for one in outcomes if one is CheckOutcome.PASSED)
        failed = sum(1 for one in outcomes if one is CheckOutcome.FAILED)
        views.append(
            RequirementAreaView(
                area=area,
                proves=CHECKED_BY.get(area),
                requirements=len(rows),
                passed=passed,
                failed=failed,
                unchecked=len(rows) - passed - failed,
            )
        )
    return views


def chosen_area(register: Register, asked: str | None) -> str | None:
    """The area asked for when the register has it, else the first area a leaf asks checks of."""
    present = {row.area for row in register.requirements}
    if asked is not None and asked in present:
        return asked
    for area in CHECKED_BY:
        if area in present:
            return area
    return register.requirements[0].area if register.requirements else None


# ------------------------------------------------------------------------ the register


@functools.cache
def _register_at(path: Path) -> Register | None:
    return load_register(path) if path.exists() else None


def register_of(request: Request) -> Register | None:
    """`app.state.requirement_register` when a test put one there, the shipped file otherwise."""
    found = getattr(request.app.state, "requirement_register", None)
    if isinstance(found, Register):
        return found
    return _register_at(DOCS / REGISTER_IN_DOCS)


def release_commit_of(request: Request) -> str | None:
    """The commit this image was built from, or None in a checkout with no manifest."""
    found = getattr(request.app.state, "release_commit", None)
    if isinstance(found, str):
        return found or None
    from brain.ops.release_manifest import read_manifest

    manifest = read_manifest()
    return None if manifest is None else manifest.commit


# ------------------------------------------------------------------------ the store


@dataclass(frozen=True)
class NewCheck:
    """What a recorded check is made of, before the database gives it an instant."""

    requirement_id: str
    outcome: CheckOutcome
    checked_by: str
    release_commit: str | None
    note: str


@runtime_checkable
class RequirementChecks(Protocol):
    """Where checks are kept. `StoredRequirementChecks` over a database."""

    async def latest(self) -> Mapping[str, RequirementCheckView]:
        """The newest check per requirement id, for every id ever checked."""
        ...

    async def record(self, check: NewCheck) -> RequirementCheckView:
        """Append one check and answer with it as kept."""
        ...


def view_of(row: RequirementCheckRow) -> RequirementCheckView:
    return RequirementCheckView(
        requirement_id=row.requirement_id,
        outcome=CheckOutcome(row.outcome),
        checked_by=row.checked_by,
        checked_at=row.checked_at,
        release_commit=row.release_commit,
        note=row.note,
    )


class StoredRequirementChecks:
    """`ops.requirement_check`, read and appended as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def latest(self) -> Mapping[str, RequirementCheckView]:
        newest = (
            select(
                RequirementCheckRow.requirement_id,
                func.max(RequirementCheckRow.checked_at).label("at"),
            )
            .group_by(RequirementCheckRow.requirement_id)
            .subquery()
        )
        statement = select(RequirementCheckRow).join(
            newest,
            (RequirementCheckRow.requirement_id == newest.c.requirement_id)
            & (RequirementCheckRow.checked_at == newest.c.at),
        )
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(statement)).scalars().all()
        return {row.requirement_id: view_of(row) for row in rows}

    async def record(self, check: NewCheck) -> RequirementCheckView:
        statement = (
            insert(RequirementCheckRow)
            .values(
                requirement_id=check.requirement_id,
                outcome=check.outcome.value,
                checked_by=check.checked_by,
                release_commit=check.release_commit,
                note=check.note,
            )
            .returning(RequirementCheckRow)
        )
        async with self._sessions() as session, session.begin():
            row = (await session.execute(statement)).scalar_one()
            return view_of(row)


def checks_of(request: Request) -> RequirementChecks:
    """`app.state.requirement_checks` when a test put one there, the database otherwise."""
    found = getattr(request.app.state, "requirement_checks", None)
    if isinstance(found, RequirementChecks):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredRequirementChecks(sessions)


# ------------------------------------------------------------------------ the routes


def _not_answerable() -> Absent:
    return Absent("the requirement checks screen is not answerable for this caller")


def _refused(field: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": "value_error", "loc": ("body", field), "msg": message, "input": None}]
    )


router = APIRouter(prefix=API_PREFIX, tags=["requirements"])


@router.get(CHECKS_PATH, response_model=RequirementChecksView, responses=COMMON_RESPONSES)
async def requirement_checks(
    request: Request,
    asked: Asked,
    area: Annotated[str | None, Query(max_length=80)] = None,
) -> RequirementChecksView:
    """Every area of the register with where its checks stand, and one area's requirements."""
    if not may_check(asked.reach, asked.now):
        log.info("requirement checks not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    register = register_of(request)
    commit = release_commit_of(request)
    if register is None:
        return RequirementChecksView(
            areas=[], area=None, requirements=[], release_commit=commit, told=NO_REGISTER
        )
    latest = await checks_of(request).latest()
    chosen = chosen_area(register, area)
    rows: Sequence[Requirement] = [one for one in register.requirements if one.area == chosen]
    return RequirementChecksView(
        areas=areas_of(register, latest),
        area=chosen,
        requirements=[
            RequirementView(
                id=one.id, requirement=one.requirement, source=one.source, latest=latest.get(one.id)
            )
            for one in rows
        ],
        release_commit=commit,
        told=A_CHECK_IS_WHAT_A_PERSON_SAW_ON_THIS_INSTALL,
    )


@router.post(
    CHECKS_PATH, status_code=201, response_model=RequirementCheckView, responses=COMMON_RESPONSES
)
async def record_check(
    request: Request, asked: Asked, check: RequirementCheckAsked
) -> RequirementCheckView:
    """Record one check against one requirement the register carries, as the person asking."""
    if not may_check(asked.reach, asked.now):
        log.info("requirement check refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    register = register_of(request)
    if register is None or check.requirement_id not in {one.id for one in register.requirements}:
        raise _refused("requirement_id", "the register carries no requirement with this id")
    note = check.note.strip()
    if not note:
        raise _refused("note", "a check says what was done and what was seen")
    new = NewCheck(
        requirement_id=check.requirement_id,
        outcome=check.outcome,
        checked_by=asked.caller.principal.id,
        release_commit=release_commit_of(request),
        note=note,
    )
    return await checks_of(request).record(new)
