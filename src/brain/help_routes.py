"""The install's own help pages: what it can see, a runbook per screen and alert, the playbook.

Everything here was written, checked and shipped in the image and served nowhere. A runbook for
each of the console's screens sat in `docs/console/runbooks` with a sweep that held it to the
screen registry (`launch.screen_runbook_gaps`, `guide_docs.runbook_gaps`), the alert runbooks were
assembled by `brain.ops.controls.runbook_for` for a handover pack nobody opened, the incident
playbook was a Python table (`brain.ops.reliability.MATRIX`) nothing rendered, and the plain
statements of what the system can see and what it does with what is typed
(`brain.adoption.visibility_summary`, `privacy_posture`) had no caller. The leaves ask that a
person at the install can read them from the install (M34.4.1, M34.3.2.1, M34.3.1.1, M34.3.1.2).

**Who may read a page is the question of who may open what it is about.** A runbook for a screen is
served to a reader who may open that screen and answered with the one refusal to everybody else,
whether the screen exists or not, so the help pages cannot be used to learn which screens an
install has or which a person is kept from. The alert runbooks are the Jobs screen's reader's and
the playbook is the Incidents screen's. A list names only what this reader may open and carries no
count of the rest. See `A_HELP_PAGE_IS_AS_OPEN_AS_THE_SCREEN_IT_IS_ABOUT`.

**The runbooks are read from the shipped files and nothing is generated from them.** A runbook is
prose a person wrote and the sweep checks it against the registry, so this serves the file as it
stands. Rejected: building the page from the registry alone, which would pass the sweep and say
nothing a person had thought to write down.

**The statements of what the system sees come from the reader's own reach and the install's own
configuration.** The departments named are the ones the reader holds a read of knowledge in,
as `brain.console.spend_view.may_read_spend` asks of spend, and nothing is said about any other.
A reader who can reach nothing is sent no sentence rather than an empty one, which would tell them
there is something to reach and that it is not theirs.

Task ids: M34.4.1, M34.3.2.1, M34.3.1.1, M34.3.1.2, M34.3.1.3
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from fastapi import Path as RoutePath
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from brain.adoption import Sentence, privacy_posture, visibility_summary
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.reads import permitted
from brain.console.screens import SCREENS
from brain.console.spend_view import PLACE_FIELD
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.locale import MESSAGES, default_locale
from brain.ops.controls import CONTROLS, Missed, runbook_for
from brain.ops.reliability import MATRIX
from brain.routing_routes import sessions_of
from brain.tables.gate import DepartmentRow

log = structlog.get_logger()

#: Where the runbooks ship. The image copies `docs` to the application's own root.
RUNBOOKS: Final = Path(__file__).resolve().parents[2] / "docs" / "console" / "runbooks"

#: Where the guide for everybody who asks ships, beside the runbooks.
ASKING_GUIDE: Final = Path(__file__).resolve().parents[2] / "docs" / "guides" / "asking-well.md"

#: Said when the image carries no asking guide, or one `served_asking_guide` cannot cut.
THE_GUIDE_IS_NOT_HERE: Final = "the asking guide is not shipped whole with this install"

#: The screens the alert runbooks and the playbook are the readers' of. The Scheduled jobs page
#: is read with the queue screen's grant, as `brain.jobs_routes` reads it.
ALERTS_ARE_THE_JOBS_SCREENS: Final = "queue"
THE_PLAYBOOK_IS_THE_INCIDENTS_SCREENS: Final = "incidents"

#: What a person reads knowledge with, so which departments they may ask about is a fact about
#: their own grants.
READS_KNOWLEDGE: Final = Capability(value="read:knowledge")

#: A screen's key, which is also a runbook's file name.
KEY_PATTERN: Final = r"^[a-z][a-z0-9_]{0,63}$"

#: How many departments the plain statement of what a person can ask about may name.
MAX_DEPARTMENTS: Final = 500

# ------------------------------------------------------------------ written-down reasons
#: Why a help page is as open as the screen it is about and no wider.
A_HELP_PAGE_IS_AS_OPEN_AS_THE_SCREEN_IT_IS_ABOUT: Final = (
    "A runbook describes a screen, who may see it and when it refuses, so a page served to "
    "somebody who may not open the screen is a description of a screen they were not given. It is "
    "answered with the one refusal, the same one for a screen that does not exist."
)


# ------------------------------------------------------------------------ the shapes
class SentenceView(BaseModel):
    """One plain sentence, in the install's language, and the catalogue key it came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    text: str


class WhatItSeesView(BaseModel):
    """What this person may ask about, and what the install does with what is typed.

    `can_ask_about` is empty for a reader who reaches nothing, and that is all it says.
    `privacy` is read off the install's configuration and needs no grant.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    can_ask_about: list[SentenceView]
    privacy: list[SentenceView]


class RunbookLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    title: str


class RunbookIndexView(BaseModel):
    """The runbooks for the screens this reader may open. No count of the rest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runbooks: list[RunbookLink]


class AskingGuideView(BaseModel):
    """How to ask well, with the reader's own department's examples and nobody else's."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    markdown: str


class RunbookView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    title: str
    markdown: str


class AlertStepsView(BaseModel):
    """What to check and what to do when one control is reported as missed in one way."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str
    first_check: list[str]
    then_do: list[str]
    escalate_after_minutes: int


class AlertRunbookView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    guards: str
    steps: list[AlertStepsView]


class AlertLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    guards: str


class AlertIndexView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alerts: list[AlertLink]


class FailureModeView(BaseModel):
    """One way a component fails, as the incident playbook states it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component: str
    fails: str
    presents_as: str
    blocks: list[str]
    retry: str
    response: str


class PlaybookView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failures: list[FailureModeView]


# ------------------------------------------------------------------------ the helpers
def _not_answerable() -> Absent:
    """The one refusal, which names no page, no screen and no reader."""
    return Absent("that help page is not answerable for this caller")


def _may_open(key: str, reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may open the screen of this key, false for a key no screen has."""
    known = next((one for one in SCREENS if one.key == key), None)
    return known is not None and permitted(known.read, reach, now)


def rendered(sentence: Sentence) -> SentenceView:
    """A sentence in the install's default language, its placeholders filled."""
    entries = MESSAGES[sentence.key]
    tag = default_locale().tag
    return SentenceView(key=sentence.key, text=entries[tag].format(**sentence.fills))


def statement(key: str) -> SentenceView:
    """A fixed statement from the catalogue in the install's default language."""
    return rendered(Sentence(key, {}))


def title_of(markdown: str) -> str:
    """A runbook's first line without its heading mark, which the sweep holds to the screen."""
    first = markdown.strip().splitlines()[0] if markdown.strip() else ""
    return re.sub(r"^#+\s*", "", first)


def runbook_text(key: str) -> str | None:
    """The shipped runbook for a screen, or None where this image carries none."""
    path = RUNBOOKS / f"{key}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


async def live_slugs(request: Request) -> tuple[str, ...]:
    """Every live department's slug, in slug order."""
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        return tuple(
            (
                await session.execute(
                    select(DepartmentRow.slug)
                    .where(DepartmentRow.deleted_at.is_(None))
                    .order_by(DepartmentRow.slug)
                    .limit(MAX_DEPARTMENTS)
                )
            )
            .scalars()
            .all()
        )


def reachable_departments(slugs: Sequence[str], reach: EntitlementSet, now: datetime) -> list[str]:
    """The departments among these this reach may read knowledge in."""
    scope = reach.scope_for(READS_KNOWLEDGE, now)
    if scope is None:
        return []
    return [one for one in slugs if scope.matches({PLACE_FIELD: one})]


router = APIRouter(prefix=API_PREFIX, tags=["help"])


# ------------------------------------------------------------------------- the routes
@router.get("/help/what-it-sees", response_model=WhatItSeesView, responses=COMMON_RESPONSES)
async def what_it_sees(request: Request, asked: Asked) -> WhatItSeesView:
    """What this person may ask about and what the install does with what they type (M34.3.1.1).

    The departments are the reader's own reach and the privacy statements are read off the
    install's configuration, so the page is never confidently wrong about either. Nobody is
    refused: a reader who reaches nothing is sent no sentence about reach.
    """
    reached = reachable_departments(await live_slugs(request), asked.reach, asked.now)
    return WhatItSeesView(
        can_ask_about=[rendered(one) for one in visibility_summary(reached)] if reached else [],
        privacy=[statement(one) for one in privacy_posture()],
    )


@router.get("/help/asking-well", response_model=AskingGuideView, responses=COMMON_RESPONSES)
async def asking_well(request: Request, asked: Asked) -> AskingGuideView:
    """The guide to asking well, with the questions the caller's own department can ask (M34.3.1.3).

    Open to every signed-in person, because it is addressed to everybody who asks and describes no
    screen. The examples are `GET /welcome/from-your-data`'s own answer, called rather than
    restated: the caller's own department, the kinds of record they may read there, at most three,
    each saying where to check it, and none while the switch for them is off. A reader with nothing
    to be offered is served the sentence the shipped page uses for a department with nothing
    indexed, which is the same sentence for the three reasons there might be nothing.
    """
    from brain.ops.guide_docs import GuideShapeError, served_asking_guide
    from brain.welcome_routes import welcome_from_data

    if not ASKING_GUIDE.is_file():
        raise Failed(THE_GUIDE_IS_NOT_HERE)
    offered = await welcome_from_data(request, asked)
    try:
        markdown = served_asking_guide(
            ASKING_GUIDE.read_text(encoding="utf-8"),
            examples=[(one.question, one.check_in) for one in offered.questions],
        )
    except GuideShapeError:
        raise Failed(THE_GUIDE_IS_NOT_HERE) from None
    return AskingGuideView(title=title_of(markdown), markdown=markdown)


@router.get("/help/runbooks", response_model=RunbookIndexView, responses=COMMON_RESPONSES)
async def runbook_index(asked: Asked) -> RunbookIndexView:
    """The runbooks for the screens this reader may open, in the registry's order (M34.3.2.1)."""
    found: list[RunbookLink] = []
    for one in SCREENS:
        text = runbook_text(one.key)
        if text is not None and permitted(one.read, asked.reach, asked.now):
            found.append(RunbookLink(key=one.key, title=title_of(text)))
    return RunbookIndexView(runbooks=found)


@router.get("/help/runbooks/{key}", response_model=RunbookView, responses=COMMON_RESPONSES)
async def runbook(key: Annotated[str, RoutePath(pattern=KEY_PATTERN)], asked: Asked) -> RunbookView:
    """One screen's runbook, to a reader who may open that screen (M34.3.2.1).

    One refusal for a key no screen has, a screen the reader may not open and a screen that has no
    runbook in this image, so none of the three can be told from another.
    """
    text = runbook_text(key) if _may_open(key, asked.reach, asked.now) else None
    if text is None:
        log.info("runbook not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    return RunbookView(key=key, title=title_of(text), markdown=text)


@router.get("/help/alerts", response_model=AlertIndexView, responses=COMMON_RESPONSES)
async def alert_index(asked: Asked) -> AlertIndexView:
    """Every alert this install can raise, to a reader of the Jobs screen (M34.4.1)."""
    if not _may_open(ALERTS_ARE_THE_JOBS_SCREENS, asked.reach, asked.now):
        raise _not_answerable()
    return AlertIndexView(
        alerts=[AlertLink(control=one.name, guards=one.guards) for one in CONTROLS]
    )


@router.get("/help/alerts/{control}", response_model=AlertRunbookView, responses=COMMON_RESPONSES)
async def alert_runbook(
    control: Annotated[str, RoutePath(pattern=KEY_PATTERN)], asked: Asked
) -> AlertRunbookView:
    """What to check and do for each way one control can be reported as missed (M34.4.1)."""
    named = next((one for one in CONTROLS if one.name == control), None)
    if named is None or not _may_open(ALERTS_ARE_THE_JOBS_SCREENS, asked.reach, asked.now):
        raise _not_answerable()
    steps = []
    for missed in Missed:
        book = runbook_for(named, missed)
        steps.append(
            AlertStepsView(
                reason=missed.value,
                first_check=list(book.first_check),
                then_do=list(book.then_do),
                escalate_after_minutes=int(book.escalate_after.total_seconds() // 60),
            )
        )
    return AlertRunbookView(control=named.name, guards=named.guards, steps=steps)


@router.get("/help/playbook", response_model=PlaybookView, responses=COMMON_RESPONSES)
async def playbook(asked: Asked) -> PlaybookView:
    """The incident playbook, every way a component fails, to a reader of Incidents (M34.4.1)."""
    if not _may_open(THE_PLAYBOOK_IS_THE_INCIDENTS_SCREENS, asked.reach, asked.now):
        raise _not_answerable()
    return PlaybookView(
        failures=[
            FailureModeView(
                component=one.component,
                fails=one.fails,
                presents_as=one.presents_as,
                blocks=list(one.blocks),
                retry=one.retry.value,
                response=one.response,
            )
            for one in MATRIX
        ]
    )
