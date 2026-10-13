"""The one address Keycloak is pointed at to sign a person in with Lark, and nothing else.

`brain.identity.lark_sign_in` says how Lark's answers become what Keycloak's OpenID Connect broker
reads; this is the request it is said in. Keycloak, having sent the person to Lark's own sign-in
page and been returned a code, posts the code here with the application's secret, and gets back
what a standard token endpoint would have answered. That is the whole of it (M1.1.8).

**It answers nothing unless the install brokers sign-in to Lark.** `brain.ops.realm_import.brokered`
is the one reader of the settings that decide that, and is asked on every request, so an install
whose directory is anything else answers this address with the same "nothing here" as an address
that does not exist, and ships with the feature off. See
`AN_INSTALL_THAT_DOES_NOT_BROKER_LARK_HAS_NOTHING_AT_THIS_ADDRESS`.

**It is outside the API prefix and takes no sign-in, and what it takes instead is the secret.**
Every route under the prefix authenticates its caller but two written exceptions
(`tests/unit/test_api_routes.py`), and this is a third kind of caller: Keycloak, which has no
session and no bearer token. It is not under the prefix so that the rule stays as written, and it
is left out of the public schema. What proves the caller is that Lark accepts the code with the
secret the caller sent: a request without the application's secret, or with a wrong one, is refused
by Lark and this answers a fixed word. The bridge cannot be used to ask Lark anything but this one
exchange and the one read of the person it bought. See
`THE_BRIDGE_ASKS_LARK_ONLY_THE_ONE_EXCHANGE`.

**A cap on how often it is asked, because anybody can post to it.** Each request that gets past
the shape check costs Lark a call, and a flood of them is a flood at Lark in this install's name.
`MAX_EXCHANGES_PER_MINUTE` is a backstop held in the process, not a limit a company tunes; the real
limit is Lark's refusal of a code nobody holds. Rejected: the sliding-window store the API's
callers go through, whose scopes are people, channels and agents and which this caller is none of.

**What it logs is that it was asked and how it ended, never what was said.** Not the code, not the
secret, not Lark's answer and not the person: a sign-in is a person, and a log is read by people
who may not be them.

Task ids: M1.1.8
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Final
from urllib.parse import parse_qsl

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from brain.connectors.staff_directories import DirectorySignInError
from brain.identity.lark_sign_in import (
    ALIAS,
    BRIDGE_PATH,
    INVALID_REQUEST,
    TOKEN_PATH,
    LarkSignInError,
    claims_from,
    exchange_request,
    grant_from,
    id_token_for,
    profile_request,
)
from brain.install import InstallError, value_of
from brain.ops.realm_import import STAFF_LOCATION_SETTING, brokered
from brain.setup_staff_routes import fetch_of

log = structlog.get_logger(__name__)

router = APIRouter(tags=["lark-sign-in"])

# ------------------------------------------------------------------ written-down reasons
#: Why an install not brokering to Lark answers nothing here.
AN_INSTALL_THAT_DOES_NOT_BROKER_LARK_HAS_NOTHING_AT_THIS_ADDRESS: Final = (
    "The address answers a person's sign-in only on an install whose settings broker sign-in to "
    "Lark, and answers anybody else with one 404 and one body, the same as an address that does "
    "not exist, so posting to it cannot tell a stranger which sign-in services this install uses."
)

#: Why the bridge makes exactly two calls to Lark and no others.
THE_BRIDGE_ASKS_LARK_ONLY_THE_ONE_EXCHANGE: Final = (
    "The addresses it calls are built from Lark's two platforms by `brain.identity.lark_sign_in`, "
    "never from anything the request said; the body of the one call is the five values of a "
    "standard exchange, and the one read is of the person that exchange's own token belongs to. "
    "A caller can choose a code and a secret and nothing else."
)

# ------------------------------------------------------------------------ the figures
#: The most a sign-in service asks in a minute. A company's people do not sign in faster than this.
MAX_EXCHANGES_PER_MINUTE: Final = 60

#: The longest request taken: a form of five short values.
MAX_BODY_BYTES: Final = 8192

NOT_HERE: Final = {"error": "not_found"}
TOO_MANY: Final = {"error": "temporarily_unavailable"}
UNREACHABLE: Final = {"error": "temporarily_unavailable"}

#: When each recent request was made, newest last. Process-held, for the reason in the module
#: docstring: a backstop and not a policy.
_RECENT: deque[float] = deque(maxlen=MAX_EXCHANGES_PER_MINUTE)

NO_STORE: Final = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _may_ask(now: float) -> bool:
    """Whether this request is inside the minute's cap, and counted if so."""
    if len(_RECENT) == _RECENT.maxlen and now - _RECENT[0] < 60:
        return False
    _RECENT.append(now)
    return True


def forget_recent_requests() -> None:
    """Empty the cap's memory. For a test, which asks more often than a company's people do."""
    _RECENT.clear()


def _refused(word: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": word}, headers=NO_STORE)


@router.post(TOKEN_PATH, include_in_schema=False)
async def exchange(request: Request) -> JSONResponse:
    """Keycloak's code exchange, answered as Lark's sign-in would have if it were standard."""
    try:
        broker = brokered()
        location = value_of(STAFF_LOCATION_SETTING)
    except InstallError:
        return JSONResponse(status_code=404, content=NOT_HERE)
    if not broker.provider or broker.provider.get("alias") != ALIAS:
        return JSONResponse(status_code=404, content=NOT_HERE)
    config = broker.provider["config"]
    client_id = str(config["clientId"])
    issuer = str(config["tokenUrl"]).removesuffix(TOKEN_PATH) + BRIDGE_PATH

    moment = datetime.now(UTC)
    if not _may_ask(moment.timestamp()):
        return JSONResponse(status_code=503, content=TOO_MANY, headers=NO_STORE)
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return _refused(INVALID_REQUEST)
    try:
        form = dict(parse_qsl(raw.decode("ascii"), keep_blank_values=True, max_num_fields=20))
    except (UnicodeDecodeError, ValueError):
        return _refused(INVALID_REQUEST)

    fetch = fetch_of(request)
    try:
        sent = exchange_request(location, form=form, client_id=client_id)
        grant = grant_from(await fetch(sent))
        claims = claims_from(await fetch(profile_request(location, grant.access_token)))
    except LarkSignInError as refused:
        log.info("lark_sign_in.refused", word=refused.word)
        return _refused(refused.word)
    except DirectorySignInError:
        log.info("lark_sign_in.unreachable")
        return JSONResponse(status_code=502, content=UNREACHABLE, headers=NO_STORE)
    log.info("lark_sign_in.exchanged")
    answer = id_token_for(
        claims, grant, client_id=client_id, issuer=issuer, now_seconds=int(moment.timestamp())
    )
    return JSONResponse(content=answer, headers=NO_STORE)
