"""The questions a new person is offered on their first visit to Ask, for their own department.

`brain.identity.lifecycle.welcome_questions` was written for the joiner's first day and nothing
served it: the Ask page said it suggested no question. This is the route, and it holds no
judgement of its own. **The questions are a function of the caller's admitted reach and their own
department, and of nothing else**: a question is offered only when the caller holds every
capability it names in that department, so one they would be refused is never shown, and the
function takes one department name, so a list of the company's departments cannot be built from
it. No count of what was left out is sent, because that count is the number of things the person
may not ask.

**The three templates are unchanged and still always offered.** If a department has indexed nothing,
the answer to a suggested question is the ordinary nothing-found one, which is what any question
about nothing gets.

**Questions built from what is indexed are a second, separate read, behind a switch (M34.1.1.2).**
This module first rejected generating questions from what a department has indexed, on the argument
that a suggestion built from a kind of record a person cannot reach discloses it. That argument
holds for a suggestion built without the reader's reach, and the owner's leaf asks for suggestions
from what actually indexed, so the second read keeps the argument and changes the construction: a
kind of record is a candidate only when `row_scope_for` admits the reader to it in their own
department, and the choice of three is made among those alone
(`brain.console.adoption_coverage.starter_for_reader`). It is a route of its own so that the
templates' answer stays what it was and so that `GET /welcome` never waits on the database. The
same Ask component draws both lists, so there is one welcome and not two.

Task ids: M26.1.4, M34.1.1.2, M34.1.1.3
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.connector_routes import manifest_or_none, records_of, sync_records_of
from brain.console.adoption_coverage import starter_for_reader
from brain.core.department import SLUG_RE
from brain.core.errors import Failed
from brain.identity.lifecycle import LifecycleError, welcome_questions
from brain.locale import default_locale, text
from brain.ops.connector_catalogue import declarations
from brain.ops.connector_sync import SyncState
from brain.ops.coverage_store import record_counts
from brain.ops.features import is_on
from brain.ops.features_declared.starter_questions_from_data import STARTER_QUESTIONS_FROM_DATA
from brain.reviewed_connectors import current as reviewed_now
from brain.routing_routes import sessions_of

#: Where the questions are read from.
WELCOME_PATH: Final = "/welcome"

#: Where the questions built from what is indexed are read from.
WELCOME_FROM_DATA_PATH: Final = "/welcome/from-your-data"

router = APIRouter(prefix=API_PREFIX, tags=["welcome"])


class WelcomeView(BaseModel):
    """At most three questions, in the order they are offered, and nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    questions: list[str]


@router.get(WELCOME_PATH, response_model=WelcomeView, responses=COMMON_RESPONSES)
async def welcome(asked: Asked) -> WelcomeView:
    """The starter questions this person may ask in their own department.

    A person with no department, or whose department is not a slug the questions can name, is
    offered none, which is the same answer as one who may ask none of them.
    """
    department = asked.caller.principal.primary_department
    if not department:
        return WelcomeView(questions=[])
    try:
        found = welcome_questions(asked.reach, department, now=asked.now)
    except LifecycleError:
        return WelcomeView(questions=[])
    return WelcomeView(questions=list(found))


class StarterFromDataView(BaseModel):
    """One question built from what is indexed, and the system to check its answer in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    #: The system a person opens to see the same figure, as its screen names it.
    check_in: str


class WelcomeFromDataView(BaseModel):
    """At most three questions built from the caller's own department's data. No count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    questions: list[StarterFromDataView]


async def starter_from_data_is_on(request: Request) -> bool:
    """Whether questions built from what is indexed are switched on. Off until turned on.

    Asked before the data is read and never before the fixed templates, which are not behind it.
    """
    found = getattr(request.app.state, "starter_questions_from_data_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        return await is_on(session, STARTER_QUESTIONS_FROM_DATA)


@router.get(WELCOME_FROM_DATA_PATH, response_model=WelcomeFromDataView, responses=COMMON_RESPONSES)
async def welcome_from_data(request: Request, asked: Asked) -> WelcomeFromDataView:
    """Up to three questions about what the caller's own department has indexed (M34.1.1.2).

    The department is the caller's own and nothing a request carries sets it. A person with none,
    or one that is not a slug, and a caller reaching no kind of record that is indexed there, are
    all answered with an empty list: the ordinary answer, which says nothing about what exists.
    """
    empty = WelcomeFromDataView(questions=[])
    department = asked.caller.principal.primary_department
    if not department or not SLUG_RE.match(department):
        return empty
    if not await starter_from_data_is_on(request):
        return empty
    await reviewed_now(request.app.state)
    factory = sessions_of(request)
    records = records_of(request)
    if factory is None or records is None:
        raise Failed("no database on this process")
    sync = sync_records_of(request)
    connections = await records.connected()
    synced: dict[str, SyncState] = dict(await sync.states()) if sync is not None else {}
    manifests = {
        one.connector: built for one in connections if (built := manifest_or_none(one)) is not None
    }
    async with factory() as session:
        counts = await record_counts(session, [department])
    declared = declarations()
    found = starter_for_reader(
        department=department,
        entitlement=asked.reach,
        now=asked.now,
        connections=connections,
        manifests=manifests,
        synced=synced,
        counts=counts,
        declared=declared,
    )
    rules = default_locale()
    return WelcomeFromDataView(
        questions=[
            StarterFromDataView(
                question=text(one.shape, rules).replace("{entity}", one.entity),
                check_in=declared[one.check_in].label if one.check_in in declared else one.check_in,
            )
            for one in found
        ]
    )
