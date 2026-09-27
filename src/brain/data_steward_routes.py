"""The data steward over HTTP, for an install whose setup named nobody: who it is, and naming one.

Since 2026-09-17 the setup wizard names a data steward in the administrator's own transaction,
and `brain.identity.data_steward` argues why every read of the company's data begins with that
person. An install set up before then has no steward and nobody on it can ever be granted a data
read, and naming one must not need a shell on the server. **This is that route, and it appoints
only where nobody is appointed.** A second appointment is refused in a sentence and writes
nothing; see `brain.identity.data_steward.A_STEWARD_IS_APPOINTED_ONCE`.

**One authority for the read and the write, held over everything: `admin:data_steward`.** The
feature switch's argument in `brain.feature_routes`: an appointment is for the whole install, so
there is no department's version of it, and the only reader of who the steward is who needs to
know from this screen is somebody deciding whether to name one. It is an `admin:` verb, so
`brain.gate.admission` withholds it from a session without a second factor and from any channel
but the console before this module is asked, and a caller without it is refused identically on an
install with a database and one without, naming the screen and never the capability.
`brain.identity.first_administrator.ADMINISTRATION` holds it, so every first administrator is
granted it at appointment or at the next start. See
`NAMING_A_STEWARD_IS_ADMINISTRATION_OVER_EVERYTHING`.

**Who may be named: another person by name and work address, or the caller as well.** The body
never carries a principal id. Another person is a new principal the server mints an id for, as the
wizard's steward is, and is linked to their sign-in on the Sign-in links screen afterwards. The
caller is named only by saying so, and `brain.identity.data_steward.appoint_in` checks that choice
against the one test of an administrator. The name and address are judged by the wizard's own
steward screen, `brain.setup_wizard.problems_with`, so the two places a steward is named have one
rule; the rule that compares the address with the administrator's cannot run here, because an
administrator's address is kept nowhere. See `THE_WIZARD_S_SCREEN_JUDGES_WHAT_IS_TYPED_HERE`.

**The confirmations' words are served beside the answer**, for `brain.connector_routes`' reason:
the words a person agrees to before naming a steward are the words of the system that does it.

**What an administrator is told.** 200 with who the steward now is. 422 with each problem by field,
catalogue key and the key's English sentence, which is the language this console draws. 409 as
`ErrorBody`, the product's one error shape, with a sentence per refusal saying what to do, because
each is something the administrator acts on and none names anybody but the person they typed or
themselves. Rejected: a refusal view of its own carrying the store's code, which would be a fifth
route documenting its own 409 in `tests/unit/test_api.py` for a code no screen needs beside the
sentence. Everything is recorded:
each grant the appointment writes appends a `grant` entry naming the administrator as its actor,
with their reach's digest and the request's trace.

Task ids: M27.9.9
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.identity.data_steward import (
    DataStewards,
    NamedSteward,
    Steward,
    StewardRefusal,
    StewardRefusedError,
)
from brain.locale import rules_for, text
from brain.routing_routes import sessions_of
from brain.setup_routes import new_principal_id
from brain.setup_wizard import SAME_PERSON, StepId, problems_with, step_for

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the route asks an administration capability over everything.
NAMING_A_STEWARD_IS_ADMINISTRATION_OVER_EVERYTHING: Final = (
    "Naming the data steward hands one person the root of every data read on the install, for the "
    "whole install. It is decided by whoever governs the system, it has no department's version, "
    "and it needs a second factor, so it is an admin capability held over everything, asked "
    "before anything else, and refused in the same words whether or not this process has a "
    "database."
)

#: Why the console's appointment is judged by the wizard's screen.
THE_WIZARD_S_SCREEN_JUDGES_WHAT_IS_TYPED_HERE: Final = (
    "A steward is named in two places, the setup wizard and this screen, and two rules for what a "
    "name and a work address must be would come apart. So what is typed here is judged by the "
    "wizard's own steward screen. The one rule that cannot run here compares the address with the "
    "administrator's, which is kept nowhere after setup; naming yourself under a second account "
    "leaves an account the Sign-in links screen cannot link to the sign-in you already use."
)

# --------------------------------------------------------------------- the figures

#: Reads who the steward is and names one. Held over everything or not at all.
STEWARD_AUTHORITY: Final = Capability(value="admin:data_steward")

#: Where the screen reads and writes.
STEWARD_PATH: Final = "/govern/data-steward"

#: The screen's name in a refusal. The console's own words, identical on every install.
STEWARD_SCREEN: Final = "data steward"

#: The language the console draws, which is the one its problems are told in. See `brain.locale`.
CONSOLE_LANGUAGE: Final = "en"

#: What an administrator is told for each refusal the store can make. Every member has one.
TOLD: Final[Mapping[StewardRefusal, str]] = {
    StewardRefusal.ALREADY_APPOINTED: (
        "This install already has a data steward, or had one whose appointment was taken away. "
        "Replacing a data steward is not something the console does, so nothing was changed."
    ),
    StewardRefusal.NO_LIVE_PERSON: (
        "That person could not be named the data steward, because they are not a live person on "
        "this install. Nothing was changed."
    ),
    StewardRefusal.SAME_PERSON_UNSAID: (
        "That person administers this install, so naming them the data steward has to be chosen "
        "as naming the administrator as well. Nothing was changed."
    ),
    StewardRefusal.NOT_AN_ADMINISTRATOR: (
        "You do not administer this whole install, so you cannot be named the data steward as the "
        "administrator. Name another person instead. Nothing was changed."
    ),
    StewardRefusal.HOLDS_PART_ALREADY: (
        "That person already holds part of what a data steward holds, over less than everything. "
        "Remove those grants on the People screen and try again. Nothing was changed."
    ),
}

#: Said when nobody is appointed.
NOBODY_APPOINTED: Final = (
    "No data steward is appointed, so nobody on this install can be granted a read of the "
    "company's data. Name one person, or name yourself as the administrator and the data steward."
)


#: What naming another person does, in the words a person agrees to before it is done.
APPOINTING_ANOTHER: Final = (
    "They are granted the authority to grant and the content plane over everything, and the reads "
    "of every source connected now or later, and every grant is recorded against you. A data "
    "steward is named once, and the console does not replace one."
)

#: What naming yourself does, in the words a person agrees to before it is done.
APPOINTING_YOURSELF: Final = (
    "Your account then holds the widest governance and the widest reach over the company's data "
    "together: the authority to grant, the content plane and the reads of every connected source, "
    "over everything. It is recorded against you. A data steward is named once, and the console "
    "does not replace one."
)


def appointed_sentence(steward: Steward) -> str:
    """What the screen says about an appointed steward. Their name and nothing they hold."""
    return (
        f"{steward.display_name} is the data steward. Every read of the company's data is granted "
        "by them or by somebody they granted, and each source connected is granted to them."
    )


# ------------------------------------------------------------------------ the shapes


class StewardView(BaseModel):
    """Who the data steward is, or that nobody is, and a sentence saying what that means."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    appointed: bool
    principal_id: str | None
    display_name: str | None
    told: str
    #: What naming another person does, for the confirmation. See `APPOINTING_ANOTHER`.
    appointing_another: str = APPOINTING_ANOTHER
    #: What naming yourself does, for the confirmation. See `APPOINTING_YOURSELF`.
    appointing_yourself: str = APPOINTING_YOURSELF


class StewardAsked(BaseModel):
    """Another person by name and work address, or the caller by saying so. Never an id.

    No length on any field, for `brain.connector_routes.ConnectAsked`'s reason: the wizard's screen
    judges both in words, and a length on the model would be refused in a shape that names none.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    same_as_administrator: bool
    full_name: str = ""
    work_address: str = ""


class StewardProblemView(BaseModel):
    """One thing wrong with what was typed: the field, the catalogue key and its sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    key: str
    message: str


class StewardProblemsView(BaseModel):
    """Everything wrong with what was typed. Nothing was written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: list[StewardProblemView]


# ------------------------------------------------------------------------ the decisions


def may_name(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read and name the data steward: the authority, over everything."""
    return _in_reach(reach, STEWARD_AUTHORITY, NOWHERE, now)


def problems_in(asked: StewardAsked) -> tuple[StewardProblemView, ...]:
    """What the wizard's steward screen finds wrong with this body. See
    `THE_WIZARD_S_SCREEN_JUDGES_WHAT_IS_TYPED_HERE`."""
    values = {
        "steward_full_name": asked.full_name,
        "steward_work_address": asked.work_address,
        "steward_is_administrator": SAME_PERSON if asked.same_as_administrator else "no",
    }
    english = rules_for(CONSOLE_LANGUAGE)
    return tuple(
        StewardProblemView(field=one.field, key=one.key, message=text(one.key, english))
        for one in problems_with(step_for(StepId.DATA_STEWARD), values)
    )


def named_by(asked: StewardAsked, *, caller: str, minted: str) -> NamedSteward:
    """Who the body names: the caller when it says so, and otherwise a new person under `minted`."""
    if asked.same_as_administrator:
        return NamedSteward(principal_id=caller, display_name="", same_as_administrator=True)
    return NamedSteward(
        principal_id=minted, display_name=asked.full_name.strip(), same_as_administrator=False
    )


def steward_view(steward: Steward | None) -> StewardView:
    """The screen's answer about who is appointed."""
    if steward is None:
        return StewardView(
            appointed=False, principal_id=None, display_name=None, told=NOBODY_APPOINTED
        )
    return StewardView(
        appointed=True,
        principal_id=steward.principal_id,
        display_name=steward.display_name,
        told=appointed_sentence(steward),
    )


# ------------------------------------------------------------------------- the wiring


def _not_answerable() -> Absent:
    """The one refusal for a caller without the authority. Names the screen and nothing else."""
    return Absent(f"the {STEWARD_SCREEN} screen is not answerable for this caller")


def stewards_of(request: Request) -> DataStewards:
    """The store over this process's database, or one fault identical for every caller."""
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return DataStewards(sessions)


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.feature_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


router = APIRouter(prefix=API_PREFIX, tags=["govern"], route_class=NoEchoRoute)

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": ErrorBody, "description": "Nobody was named, and what to do about it."},
    422: {"model": StewardProblemsView, "description": "What is wrong with what was typed."},
}


@router.get(STEWARD_PATH, response_model=StewardView, responses=COMMON_RESPONSES)
async def data_steward(request: Request, asked: Asked) -> StewardView:
    """Who the data steward is, for a caller who may name one."""
    if not may_name(asked.reach, asked.now):
        log.info("data steward screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    return steward_view(await stewards_of(request).steward())


@router.post(STEWARD_PATH, response_model=StewardView, responses=_TOLD)
async def name_data_steward(request: Request, body: StewardAsked, asked: Asked) -> JSONResponse:
    """Name the data steward where nobody is appointed, or write nothing and say why.

    The authority first, then what was typed, then the store, and the order is the property: a
    caller without the authority learns nothing, and a caller with it is told about a blank box
    before anything is written.
    """
    if not may_name(asked.reach, asked.now):
        log.info("naming a data steward refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = problems_in(body)
    if found:
        problems = StewardProblemsView(problems=list(found))
        return JSONResponse(status_code=422, content=problems.model_dump(mode="json"))
    stewards = stewards_of(request)
    named = named_by(body, caller=asked.caller.principal.id, minted=new_principal_id())
    try:
        await stewards.appoint(
            named,
            actor=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
            now=asked.now,
        )
    except StewardRefusedError as refused:
        log.info("data steward not named", reason=refused.reason.value)
        refusal = ErrorBody(message=TOLD[refused.reason], trace_id=_trace_id())
        return JSONResponse(status_code=409, content=refusal.model_dump(mode="json"))
    except BrainError:
        raise
    except Exception as exc:
        # Broad for the reason `brain.api_routes.answer` gives, and the type name alone.
        raise Failed(f"naming a data steward: {type(exc).__name__}") from exc
    log.info("data steward named", principal=named.principal_id, by=asked.caller.principal.id)
    answered = steward_view(await stewards.steward())
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
