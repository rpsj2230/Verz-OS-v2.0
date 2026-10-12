"""The install acceptance check for Sign in with Lark: what the bridge tells the sign-in service.

M1.1.8 is a person on a Lark staff list signing in with Lark and no password, as the account the
staff sync made for them. Two services make that happen, and **this check can ask only this
install's half of it**: the bridge in the application that turns Lark's answers into what Keycloak
reads (`brain.lark_sign_in_routes`). Keycloak's half, which is linking the person to their account
by their address and refusing a person with none, is not asked here and the sentence says so:
asking it would mean signing a person in at the owner's real sign-in service with a real Lark
account, which no check of this kind does. That half is the owner's own sign-in, recorded on the
Requirement checks screen (needs-rupash 197).

**What it asks is the bridge as the install runs it.** The install's own settings decide whether it
answers at all (`brain.ops.realm_import.brokered`), the router the application mounts is the one
asked, and the request is the one Keycloak sends. What stands in is Lark: a recorded answer for a
made-up person on a reserved documentation domain, so no address is resolved and no request leaves
the process. The check steps aside, and says why, on an install whose sign-in is not brokered to
Lark, which is every install until its owner sets it up. See
`AN_INSTALL_NOT_BROKERING_LARK_HAS_NO_BRIDGE_TO_ASK`.

**It writes nothing.** No row, no account, no email: the bridge holds nothing and the check makes
nobody. The application's secret and the code it posts are made for the check, and the check looks
for both in what the bridge answers.

Task ids: M1.1.8
"""

from __future__ import annotations

import base64
import json
from typing import Any, Final
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI

from brain.connectors.staff_directories import Answer, Fetch, Outbound
from brain.identity.lark_sign_in import ALIAS, BROKER_RETURN_SUFFIX, TOKEN_PATH, platform_of
from brain.install import InstallError, value_of
from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, inside the range assigned to it. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1210

# ------------------------------------------------------------------ written-down reasons
#: Why the check stands aside on an install not brokering to Lark.
AN_INSTALL_NOT_BROKERING_LARK_HAS_NO_BRIDGE_TO_ASK: Final = (
    "The bridge answers only on an install whose settings broker sign-in to Lark, so on any other "
    "there is nothing at its address to ask, and the check says so rather than passing on a "
    "bridge it never reached."
)

#: Said when the install does not broker sign-in to Lark.
THIS_INSTALL_DOES_NOT_BROKER_SIGN_IN_TO_LARK: Final = (
    "this install does not broker sign-in to Lark, so the sign-in service is not pointed at the "
    "bridge and there is nothing to ask; it is asked once the owner has set Sign in with Lark up"
)

#: Said when the bridge's own per-minute cap was reached before the check could ask.
THE_BRIDGE_WAS_BUSY: Final = (
    "the bridge's per-minute cap was reached, so the check did not ask it; it is asked again at "
    "the next run"
)

#: Why the Keycloak half is not asked.
KEYCLOAK_S_HALF_IS_THE_OWNER_S_OWN_SIGN_IN: Final = (
    "Linking a person to their account by address is Keycloak's. Asking it takes a real sign-in at "
    "the owner's real sign-in service, so it is shown by the owner signing in once and recording "
    "it, and not by a check."
)

#: The Lark platform the made-up person is on, as the install's own setting names one.
LOCATION_SETTING: Final = "INSTALL_STAFF_SOURCE_LOCATION"


class _Lark:
    """Lark's two answers for one made-up person, and what the bridge asked of it."""

    def __init__(self, *, host: str, person: dict[str, Any]) -> None:
        self.host = host
        self.person = person
        self.asked: list[tuple[str, str]] = []
        self.secrets_seen: list[str] = []

    async def __call__(self, outbound: Outbound) -> Answer:
        self.asked.append((outbound.method, outbound.url))
        if outbound.url == f"https://{self.host}/open-apis/authen/v2/oauth/token":
            body = outbound.json_body or {}
            self.secrets_seen.append(str(body.get("client_secret", "")))
            return Answer(
                status=200, body={"code": 0, "access_token": "u-acceptance", "expires_in": 7200}
            )
        if outbound.url == f"https://{self.host}/open-apis/authen/v1/user_info":
            return Answer(status=200, body={"code": 0, "data": self.person})
        raise CheckFailedError("the bridge asked an address that is not Lark's")


def _claims(token: str) -> dict[str, Any]:
    segment = token.split(".")[1]
    padded = segment + "=" * (-len(segment) % 4)
    claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    return claims


@check(
    leaves=("M1.1.8",),
    sentence=(
        "On an install brokering sign-in to Lark, the mounted bridge answers a made-up person on a "
        "recorded Lark with their identifier and work address alone, refuses a person with no "
        "address and an exchange Lark refuses by one fixed word, and echoes neither code nor "
        "secret. Linking the person to their account is the sign-in service's, and not asked."
    ),
)
async def the_lark_bridge_names_the_person_lark_names_and_nobody_else(h: Harness) -> None:
    from brain.lark_sign_in_routes import router
    from brain.ops.realm_import import brokered
    from brain.routers import ROUTERS

    broker = brokered()
    if broker.provider.get("alias") != ALIAS:
        raise CheckNotRunError(THIS_INSTALL_DOES_NOT_BROKER_SIGN_IN_TO_LARK)
    if router not in ROUTERS:
        raise CheckFailedError(
            "the Lark sign-in bridge is not one of the routers the application mounts"
        )
    try:
        location = value_of(LOCATION_SETTING)
    except InstallError as unset:
        raise CheckNotRunError(THIS_INSTALL_DOES_NOT_BROKER_SIGN_IN_TO_LARK) from unset
    _, host = platform_of(location)
    config = broker.provider["config"]
    client_id = str(config["clientId"])
    address = f"{h.word().lower()}@acceptance.invalid"
    union_id = f"on_{h.word().lower()}"
    secret, code = f"CANARY-{h.word()}", f"CANARY-{h.word()}"
    return_to = f"https://id.acceptance.invalid/realms/brain{BROKER_RETURN_SUFFIX}"
    person = {"name": "Acceptance Person", "union_id": union_id, "enterprise_email": address}

    async def asked(fetch: Fetch) -> httpx.Response:
        app = FastAPI()
        app.include_router(router)
        app.state.staff_directory_fetch = fetch
        form = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": secret,
            "code": code,
            "redirect_uri": return_to,
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://bridge.acceptance.invalid"
        ) as client:
            return await client.post(
                TOKEN_PATH,
                content=urlencode(form),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

    lark = _Lark(host=host, person=person)
    answered = await asked(lark)
    if answered.status_code == 503:
        raise CheckNotRunError(THE_BRIDGE_WAS_BUSY)
    if answered.status_code != 200:
        raise CheckFailedError("the bridge refused an exchange Lark accepted")
    body = answered.json()
    claims = _claims(str(body["id_token"]))
    if claims.get("email") != address or claims.get("sub") != union_id:
        raise CheckFailedError("the bridge did not name the person Lark named")
    if claims.get("aud") != client_id or not str(body.get("access_token")):
        raise CheckFailedError("the bridge's answer was not for the application it was asked for")
    if len(lark.asked) != 2 or lark.secrets_seen != [secret]:
        raise CheckFailedError("the bridge asked Lark for more, or less, than the one exchange")
    if secret in answered.text or code in answered.text:
        raise CheckFailedError("the bridge's answer carried the secret or the code")

    # A person Lark gives no address for is refused, and what Lark said is not passed on.
    nobody = await asked(_Lark(host=host, person={"union_id": union_id, "name": "No Address"}))
    if nobody.status_code != 400 or nobody.json() != {"error": "access_denied"}:
        raise CheckFailedError("a person Lark gave no address for was not refused by one word")

    # An exchange Lark refuses is one word too, and says nothing Lark said.
    async def refuses(outbound: Outbound) -> Answer:
        return Answer(status=400, body={"code": 20024, "msg": f"{address} {secret}"})

    refused = await asked(refuses)
    if refused.status_code != 400 or refused.json() != {"error": "invalid_grant"}:
        raise CheckFailedError("an exchange Lark refused was not answered by one fixed word")
    if address in refused.text or secret in refused.text:
        raise CheckFailedError("a refusal carried what Lark said")
