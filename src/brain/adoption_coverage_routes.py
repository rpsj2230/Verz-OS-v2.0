"""The coverage statement and the first-connector suggestion over HTTP.

`brain.adoption` built `coverage_report`, `shopping_list` and `first_connector` and nothing called
them. Two reads:

**`GET /report/coverage`**, for the Adoption page. For each department the reader's usage grant
admits, what is connected for it, how many records that holds and when it was last read, or an
explicit statement that nothing is connected; and the shopping list of what to do next.
`brain.console.adoption_coverage` decides who is told what and this module reads the rows it is
given and copies the result field by field. It is behind the `adoption_coverage` switch, because a
per-department statement of what is indexed is new, and a switch turned off removes a read and
leaves nothing stranded.

**`GET /console/connector-start`**, for the Connectors screen. The source to connect first, chosen
by `brain.adoption.first_connector` over the sources the console can connect, so a real question is
answerable before any document is uploaded. It is read behind the Connectors screen's own grant and
is not switched: it is a recommendation drawn from the list of sources this release ships, which is
the same on every install and tells a reader nothing about this one. The path is not under
`/console/connectors/` because `/console/connectors/{connector}` would answer it as a source named
`start`.

**Both reads state, in `ORGANISATION_NOTE`, what they leave out.** A source pinned to the whole
organisation belongs to no department's line. Saying so is the difference between a narrowing and a
silence.

Rejected: a coverage view that fetches record counts from each source when it is opened. A
connector keeps a small index and reads values live; a live count would spend the call ceiling every
question shares on a page view. The counts are the index's own.

Task ids: M34.1.1.1, M34.1.2.1, M34.1.2.2, M34.1.2.3
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.adoption import COVERAGE_MESSAGE, NEED_MESSAGE
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.connector_routes import manifest_or_none, records_of, sync_records_of
from brain.console.adoption_coverage import (
    CoverageStatement,
    coverage_for_reader,
    offers_of,
    start_with,
)
from brain.console.adoption_view import reachable_departments
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent, Failed
from brain.locale import default_locale, text
from brain.ops.connector_catalogue import declarations
from brain.ops.connector_sync import SyncState
from brain.ops.coverage_store import record_counts
from brain.ops.features import is_on
from brain.ops.features_declared.adoption_coverage import ADOPTION_COVERAGE
from brain.ops.question_gap_store import gaps_between
from brain.report_routes import live_departments
from brain.reviewed_connectors import current as reviewed_now
from brain.routing_routes import sessions_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["report"])

#: Where the coverage statement is read.
COVERAGE_PATH: Final = "/report/coverage"
#: Where the first connector is suggested.
START_PATH: Final = "/console/connector-start"

#: How far back the gaps that order the shopping list reach, in days.
GAP_WINDOW_DAYS: Final = 30

#: What the coverage view says it leaves out, so the narrowing is stated and not discovered.
ORGANISATION_NOTE: Final = (
    "Sources that answer to the whole organisation rather than to one department are listed on "
    "the Connectors screen and are not counted in a department's line."
)

#: What the view says when the switch is off.
SWITCHED_OFF: Final = "Coverage by department is switched off on this install."


class CoverageLineView(BaseModel):
    """One department's statement about one source, with no figure that adds lines together."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    #: The source's name, or None for a department with nothing connected and nothing to suggest.
    source: str | None
    #: What the screen calls it. The merged line's label names no connector.
    source_label: str | None
    state: str
    state_words: str
    records: int | None
    last_sync: datetime | None


class ActionView(BaseModel):
    """One thing the champion could do next."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    source: str
    source_label: str
    need: str
    words: str


class CoverageView(BaseModel):
    """The coverage statement for one reader. `lines` is empty when the switch is off."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    switched_on: bool
    lines: list[CoverageLineView]
    shopping: list[ActionView]
    note: str


class StartView(BaseModel):
    """The source to connect first, or neither field when nothing can answer before an upload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str | None
    label: str | None


def _label_of(name: str) -> str:
    one = declarations().get(name)
    return name if one is None else one.label


async def coverage_is_on(request: Request) -> bool:
    """Whether the coverage statement is switched on. Off until turned on.

    Asked before the statement is built. Nothing is stored by it, so turning it off strands nothing:
    see `brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.
    """
    found = getattr(request.app.state, "adoption_coverage_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        return await is_on(session, ADOPTION_COVERAGE)


def view_of(statement: CoverageStatement) -> CoverageView:
    """The statement copied field by field, with the words in the install's language."""
    rules = default_locale()
    return CoverageView(
        switched_on=True,
        lines=[
            CoverageLineView(
                department=one.department,
                source=one.source,
                source_label=None if one.source is None else _label_of(one.source),
                state=one.state.value,
                state_words=text(COVERAGE_MESSAGE[one.state], rules),
                records=one.records,
                last_sync=one.last_sync,
            )
            for one in statement.lines
        ],
        shopping=[
            ActionView(
                department=one.department,
                source=one.source,
                source_label=_label_of(one.source),
                need=one.need.value,
                words=text(NEED_MESSAGE[one.need], rules),
            )
            for one in statement.shopping
        ],
        note=ORGANISATION_NOTE,
    )


@router.get(COVERAGE_PATH, response_model=CoverageView, responses=COMMON_RESPONSES)
async def coverage(request: Request, asked: Asked) -> CoverageView:
    """What is connected for each department this reader may read usage for, and what to do next.

    Every reader is answered, as the adoption page is: a reader the usage grant admits no department
    for gets an empty statement, because a refusal would tell them there is something to refuse.
    """
    if not await coverage_is_on(request):
        return CoverageView(switched_on=False, lines=[], shopping=[], note=SWITCHED_OFF)
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
        departments = list((await session.execute(live_departments())).scalars().all())
        reachable = _reachable(departments, asked)
        counts = await record_counts(session, reachable)
        gaps = await gaps_between(
            session, start=asked.now - timedelta(days=GAP_WINDOW_DAYS), end=asked.now
        )
    statement = coverage_for_reader(
        departments=departments,
        entitlement=asked.reach,
        now=asked.now,
        connections=connections,
        manifests=manifests,
        synced=synced,
        counts=counts,
        declared=declarations(),
        unanswered=[one.unanswered() for one in gaps],
    )
    return view_of(statement)


def _reachable(departments: list[str], asked: Asking) -> frozenset[str]:
    """The departments the counts are bounded to: the ones `coverage_for_reader` will admit.

    The same function it calls, so the statement the store runs and the lines the module builds
    cannot name different sets.
    """
    return reachable_departments(departments, asked.reach, now=asked.now)


@router.get(START_PATH, response_model=StartView, responses=COMMON_RESPONSES)
async def connector_start(request: Request, asked: Asked) -> StartView:
    """The source to connect first, for a reader of the Connectors screen.

    Refused with the screen's one refusal to everybody else. Departments here are the ones the
    reader's usage grant admits, as on the coverage statement, so the widest-reach criterion counts
    only people the reader may know about.
    """
    if not permitted(screen("connectors").read, asked.reach, asked.now):
        raise Absent("connectors are not answerable for this caller")
    await reviewed_now(request.app.state)
    factory = sessions_of(request)
    records = records_of(request)
    if factory is None or records is None:
        raise Failed("no database on this process")
    connections = await records.connected()
    async with factory() as session:
        departments = list((await session.execute(live_departments())).scalars().all())
    chosen = start_with(
        offers_of(
            declarations(),
            {one.connector for one in connections},
            _reachable(departments, asked),
        )
    )
    return StartView(
        source=None if chosen is None else chosen.name,
        label=None if chosen is None else _label_of(chosen.name),
    )
