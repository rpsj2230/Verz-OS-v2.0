"""The setup wizard's staff list screen over HTTP: what to register, where to sign in, and one read.

`brain.setup_wizard` asks which staff list a company keeps and, since M42.5.7, where it is, and
`POST /setup/appointment` writes both answers as `INSTALL_STAFF_SOURCE` and
`INSTALL_STAFF_SOURCE_LOCATION` through `brain.ops.install_settings` in the appointment's own
transaction. What the screen could not do was the rest of the leaf: sign in to the directory and
pull the list, so the person sees who it names before anything is written. These three routes
are that, and none of them writes anything anywhere.

**Every route but the first asks for the setup code before it does anything, and refuses in the
appointment's one way.** A wrong code, a closed wizard and an install with no code are one 404,
for `brain.setup_routes.EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER`'s reason, and they are
asked before a single outbound request is built: a route that contacted a directory for whoever
found the address would be a way to make this server send a stranger's client secret anywhere
Google, Microsoft or Lark will accept it. See `NOTHING_LEAVES_THIS_SERVER_BEFORE_THE_CODE`.

**The first route is ungated because it says nothing about this install.** What a company
registers at each vendor, and the path its return address ends in, are the product's own
documentation and the same on every server; they are served rather than copied into the
console, so the screen and `docs/install/authentication.md` read one text.

**The trial is `brain.console.staff_source_view.rehearse`, the same three steps the console's
trial runs.** The chosen source and its location are handed in as the two settings they will
become, `selected_source` judges them exactly as it will after install, `roster_from` checks
the answer against the choice, and `brain.identity.staff_sync.dry_run` says what a first run
would change. `known` is empty and `last_applied` is none, and neither is a shortcut: at first
run this system holds nobody and has never applied a list, so a plan that proposes adding
everybody and removing nobody is the true one. The answer is the console trial's own
`TrialView`, so one screen draws both.

**A spreadsheet is read from the file the person chose, and nobody signs in to one.** The
console reads the file in the browser and posts its text; the server parses it with `csv` and
hands the rows to `SpreadsheetSource`. That is
`staff_source.A_SPREADSHEET_CANNOT_BE_AUTHENTICATED_AGAINST` taken at its word.

**A directory is signed in to in a second window, and the client secret is used once.** The
console opens the vendor's page in a pop-up, because the setup code lives in the wizard tab's
memory and a navigation would lose it, and the pop-up hands the returned code back to that tab.
The tab then posts the code, its PKCE verifier and the application's client id and secret here;
the secret is judged by `brain.ops.credentials.problems_with`, sent once in the token exchange,
and kept nowhere. See `A_CLIENT_CREDENTIAL_USED_FOR_ONE_READ_IS_NOT_KEPT`.

**Keeping that secret for the scheduled sync is not built, and the reason is a reader rather
than a writer.** `brain.ops.credentials` writes provider slots only, the application's vault
policy grants no path a directory credential could live at, and nothing in this repository
reads a directory on a schedule. A secret written for a sync nobody runs is a standing
credential with no reader, which is the shape this repository refuses elsewhere. The second
slot kind that module's own docstring anticipates for connector credentials is the place it
belongs, once a sync exists to read it.

**Nothing a refusal says was sent by the person.** Every body is carried by `NoEchoRoute`, and a
refusal from a directory is the vendor's words, shortened, from
`brain.connectors.staff_directories.A_REFUSAL_REPEATS_THE_VENDOR_AND_NEVER_THE_REQUEST`.

Task ids: M42.5.7
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final, cast

import httpx
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import COMMON_RESPONSES, NoEchoRoute
from brain.connectors.staff_directories import (
    REGISTRATION,
    RETURN_PATH,
    Answer,
    DirectorySignInError,
    Fetch,
    Outbound,
    authorisation_address,
    exchange,
    pull,
)
from brain.console.staff_source_view import Trial, rehearse
from brain.core.errors import Absent, Failed
from brain.identity.staff_adapters import SPREADSHEET, RosterUnavailableError, SpreadsheetSource
from brain.identity.staff_source import (
    STAFF_SOURCE_LOCATION_SETTING,
    STAFF_SOURCE_SETTING,
    StaffSource,
)
from brain.ops.credentials import MAX_CREDENTIAL_CHARS, problems_with
from brain.setup_routes import appointer_of
from brain.setup_wizard import (
    MAX_ANSWER_CHARS,
    WizardClosedError,
    WizardLockedError,
    assert_open,
    assert_unlocked,
)
from brain.sign_in_routes import enrolment_of
from brain.staff_source_routes import TrialView, run_view

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons
#: Why the code is asked before any request to a directory is built.
NOTHING_LEAVES_THIS_SERVER_BEFORE_THE_CODE: Final = (
    "A trial signs in to a directory with a client secret the request carries. Asked for by "
    "anybody who found the address, it would make this server send a stranger's secret to a "
    "vendor on their behalf, from this server's address. So the setup code is asked first, "
    "refused in the appointment's one way, and nothing is built or sent until it is accepted."
)

#: Why the secret a trial signs in with is not kept.
A_CLIENT_CREDENTIAL_USED_FOR_ONE_READ_IS_NOT_KEPT: Final = (
    "The client secret reaches this server to read the list once, while the person watches. "
    "No sync reads a directory on a schedule yet and no vault path is granted for a directory "
    "credential, so keeping it would be a standing secret with no reader. It is judged, sent "
    "once in the token exchange, and dropped with the request."
)

# --------------------------------------------------------------------- the figures
REGISTRATION_PATH: Final = "/setup/staff-source/registration"
SIGN_IN_PATH: Final = "/setup/staff-source/sign-in"
TRIAL_PATH: Final = "/setup/staff-source/trial"

#: The largest staff list file this reads, as text. A ceiling on an upload rather than a
#: statement about any company's size: two megabytes of CSV is tens of thousands of rows.
MAX_SHEET_CHARS: Final = 2_000_000

#: The longest authorisation code, verifier or return address accepted.
MAX_RETURNED_CHARS: Final = 2000

#: How long one request to a directory may take, and the largest answer read from one.
FETCH_TIMEOUT_SECONDS: Final = 30.0
MAX_ANSWER_BYTES: Final = 32 * 1024 * 1024


# ------------------------------------------------------------------------ the shapes
class RegistrationView(BaseModel):
    """What a company registers at one vendor before anybody can sign in to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    where: str
    grant: str
    location: str


class RegistrationsView(BaseModel):
    """Every directory a person signs in to, and the path their return address ends in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: tuple[RegistrationView, ...]
    return_path: str


class DirectorySignInAsked(BaseModel):
    """Where to send the person: the code, the source, where it is, and the browser's half."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_code: str = Field(max_length=MAX_ANSWER_CHARS)
    staff_source: str = Field(max_length=MAX_ANSWER_CHARS)
    location: str = Field(max_length=MAX_ANSWER_CHARS)
    client_id: str = Field(max_length=MAX_ANSWER_CHARS)
    redirect_uri: str = Field(max_length=MAX_RETURNED_CHARS)
    state: str = Field(max_length=MAX_ANSWER_CHARS)
    challenge: str = Field(max_length=MAX_ANSWER_CHARS)


class DirectorySignInView(BaseModel):
    """The vendor page to open, or the one thing wrong with what was given."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str = ""
    problem: str = ""


class StaffTrialAsked(BaseModel):
    """One read of a staff list: the code, the source, and a file or a returned sign-in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_code: str = Field(max_length=MAX_ANSWER_CHARS)
    staff_source: str = Field(max_length=MAX_ANSWER_CHARS)
    location: str = Field(default="", max_length=MAX_ANSWER_CHARS)
    sheet: str = Field(default="", max_length=MAX_SHEET_CHARS)
    client_id: str = Field(default="", max_length=MAX_ANSWER_CHARS)
    client_secret: str = Field(default="", max_length=MAX_CREDENTIAL_CHARS)
    code: str = Field(default="", max_length=MAX_RETURNED_CHARS)
    verifier: str = Field(default="", max_length=MAX_ANSWER_CHARS)
    redirect_uri: str = Field(default="", max_length=MAX_RETURNED_CHARS)


# ------------------------------------------------------------------------ the decisions
def _nothing_here() -> Absent:
    """The appointment's one refusal, in the same words."""
    return Absent("no setup appointment is answerable here")


async def assert_setup_open(request: Request, setup_code: str, now: datetime) -> None:
    """Refuse unless this install's wizard is open and the code is its code.

    The appointment's own order: the store, the enrolment, the count, the code. See
    `NOTHING_LEAVES_THIS_SERVER_BEFORE_THE_CODE`.
    """
    appointer = appointer_of(request)
    if appointer is None:
        raise Failed("no first administrator store on this process")
    enrolment = enrolment_of(request)
    if enrolment is None:
        log.info("staff list trial refused", reason="no_setup_code")
        raise _nothing_here()
    administrators = await appointer.administrators(now)
    try:
        assert_open(administrators)
        assert_unlocked(enrolment, setup_code, now=now)
    except (WizardClosedError, WizardLockedError) as refused:
        log.info("staff list trial refused", reason=type(refused).__name__)
        raise _nothing_here() from refused


def secret_problem(secret: str) -> str:
    """Why this client secret cannot be sent, in words, or the empty string.

    `brain.ops.credentials.problems_with` judges it, because it is the one answer here to what a
    credential pasted from a browser may be. Its sentences name a provider key, so the codes are
    kept and the words are this screen's.
    """
    codes = {one.code for one in problems_with(secret)}
    if "blank" in codes:
        return "Paste your application's client secret."
    if codes:
        return (
            "The client secret has a space, a line break or a character a secret cannot hold "
            "inside it. Copy it again from where you created it."
        )
    return ""


async def source_for(asked: StaffTrialAsked, fetch: Fetch) -> StaffSource:
    """The source a trial reads: the file's rows, or the directory signed in to and walked."""
    if asked.staff_source == SPREADSHEET:
        if not asked.sheet.strip():
            msg = "Choose the file your staff list is saved in. Save it as CSV first."
            raise DirectorySignInError(msg)
        rows = tuple(tuple(row) for row in csv.reader(io.StringIO(asked.sheet)))
        return SpreadsheetSource(rows=rows)
    if asked.staff_source not in REGISTRATION:
        msg = "That is not a staff list this screen can read."
        raise DirectorySignInError(msg)
    problem = secret_problem(asked.client_secret)
    if problem:
        raise DirectorySignInError(problem)
    token = await exchange(
        fetch,
        asked.staff_source,
        location=asked.location,
        client_id=asked.client_id,
        client_secret=asked.client_secret,
        code=asked.code,
        verifier=asked.verifier,
        redirect_uri=asked.redirect_uri,
    )
    return await pull(fetch, asked.staff_source, token=token, location=asked.location)


async def trial_for(asked: StaffTrialAsked, fetch: Fetch) -> Trial:
    """One read and the plan it makes, or the refusal that stopped it, in words.

    Every failure a person can meet here becomes a `Trial` carrying one refusal rather than an
    error, because this screen is where a person finds out whether their source is wired, and
    the tool for finding a mistake must survive every mistake. That is
    `brain.console.staff_source_view.trial`'s argument, one step earlier.
    """
    settings = {
        STAFF_SOURCE_SETTING: asked.staff_source,
        STAFF_SOURCE_LOCATION_SETTING: asked.location,
    }
    named = asked.staff_source.strip() or "none"
    try:
        source = await source_for(asked, fetch)
        return rehearse(source, known={}, last_applied=None, env=settings)
    except (DirectorySignInError, RosterUnavailableError, ValueError, csv.Error) as why:
        return Trial(source=named, plan=None, refusals=(str(why),))


# ------------------------------------------------------------------------- the wiring
async def http_fetch(outbound: Outbound) -> Answer:
    """Send one request to a directory. The one socket in the staff list screen.

    No redirects are followed, because every address here is a vendor's own and a redirect is
    the one way a request carrying a token or a secret could land somewhere else.
    """
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            response = await client.request(
                outbound.method,
                outbound.url,
                headers=dict(outbound.headers),
                data=dict(outbound.form) if outbound.form is not None else None,
                json=dict(outbound.json_body) if outbound.json_body is not None else None,
            )
    except httpx.HTTPError as failed:
        host = httpx.URL(outbound.url).host
        msg = f"This server could not reach {host}. Check that it can reach the internet."
        raise DirectorySignInError(msg) from failed
    if len(response.content) > MAX_ANSWER_BYTES:
        return Answer(status=502, body={"error": "the answer was larger than a directory sends"})
    try:
        body = response.json()
    except ValueError:
        body = {}
    return Answer(status=response.status_code, body=body if isinstance(body, Mapping) else {})


def fetch_of(request: Request) -> Fetch:
    """The directory client this process was built with, or the real one.

    A `cast` after a `callable` check, for `brain.staff_source_routes.trial_source_of`'s reason:
    a protocol whose only member is `__call__` admits every function, so the check would be a
    callable check with more words, and the attribute's name is what discriminates.
    """
    found = getattr(request.app.state, "staff_directory_fetch", None)
    return cast(Fetch, found) if callable(found) else http_fetch


router = APIRouter(tags=["setup"], route_class=NoEchoRoute)

_TOLD: Final[dict[int | str, dict[str, object]]] = {**COMMON_RESPONSES}


@router.get(REGISTRATION_PATH, response_model=RegistrationsView, responses=_TOLD)
async def staff_source_registration() -> RegistrationsView:
    """What a company registers at each directory, and the path its return address ends in."""
    return RegistrationsView(
        sources=tuple(
            RegistrationView(source=source, where=one.where, grant=one.grant, location=one.location)
            for source, one in REGISTRATION.items()
        ),
        return_path=RETURN_PATH,
    )


@router.post(SIGN_IN_PATH, response_model=DirectorySignInView, responses=_TOLD)
async def staff_source_sign_in(request: Request, body: DirectorySignInAsked) -> JSONResponse:
    """The vendor page the person signs in on, once the code is accepted."""
    await assert_setup_open(request, body.setup_code, datetime.now(UTC))
    try:
        address = authorisation_address(
            body.staff_source,
            location=body.location,
            client_id=body.client_id,
            redirect_uri=body.redirect_uri,
            state=body.state,
            challenge=body.challenge,
        )
    except DirectorySignInError as why:
        told = DirectorySignInView(problem=str(why))
        return JSONResponse(status_code=422, content=told.model_dump(mode="json"))
    return JSONResponse(status_code=200, content=DirectorySignInView(address=address).model_dump())


@router.post(TRIAL_PATH, response_model=TrialView, responses=_TOLD)
async def staff_source_trial(request: Request, body: StaffTrialAsked) -> TrialView:
    """Read the chosen list once and say who a first run would add. Writes nothing."""
    await assert_setup_open(request, body.setup_code, datetime.now(UTC))
    found = await trial_for(body, fetch_of(request))
    log.info(
        "staff list trial",
        source=found.source,
        read=found.plan is not None,
    )
    return TrialView(trial=run_view(found))
