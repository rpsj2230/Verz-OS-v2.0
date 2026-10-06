"""Install acceptance checks for the Credentials screen: every slot the install declares, the vault
it was read from, and a value written into each slot the screen offers, never read back.

Every check calls the route the console page calls, as the reader that page serves, in the shape
`brain.ops.acceptance_operations_console` sets out (`A_ROUTE_IS_ASKED_AS_THE_PAGE_ASKS_IT`).

**What is read is this install's vault, and what is written goes to a vault of the check's own.**
The list and each slot's page read the vault's metadata, which carries no value, through a client
built exactly as `brain.app.vault_at_start` builds the application's, so the state the check holds
the screen to is the install's real seal, token and slots. A write cannot be undone by the check's
rolled-back transaction, and a provider key written into a real slot would be in use by the next
question, so every write goes to `KeptHere`, an in-memory vault holding a version for every slot,
through the product's own `Credentials`. The record of each write is the product's
`StoredCredentialWrites` in the check's transaction, so the slot's history is read back exactly as
a real write leaves it. See `A_WRITE_GOES_TO_A_VAULT_OF_THE_CHECKS_OWN`.

**No key the check writes is put to use.** `Credentials.put_to_use` hands a provider key to this
process's SDK through the environment it was given, and the check gives it a dictionary of its own,
so the process running the check keeps the keys it had. See
`NO_KEY_THE_CHECK_WRITES_REACHES_THIS_PROCESS`.

Task ids: M27.11.10, M27.15.50
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_operations_console import (
    Console,
    asking_as,
    console_for,
    refused,
    traced,
)
from brain.ops.acceptance_run import Harness
from brain.ops.openbao import StaticVersion

if TYPE_CHECKING:
    from brain.credential_routes import CredentialRow, CredentialsPage
    from brain.ops.credentials import Credentials
    from brain.ops.openbao import OpenBaoVault

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 324

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the check's writes go to a vault of its own.
A_WRITE_GOES_TO_A_VAULT_OF_THE_CHECKS_OWN: Final = (
    "A value written into a real slot cannot be undone by the check's rolled-back transaction, "
    "and a provider key written there is used by the next question. So the list and the slot's "
    "page read the install's own vault, whose metadata carries no value, and every write goes "
    "through the product's Credentials to an in-memory vault holding a version of every slot."
)

#: Why the keys the check writes reach no process.
NO_KEY_THE_CHECK_WRITES_REACHES_THIS_PROCESS: Final = (
    "Keeping a provider key also hands it to this process's provider SDK through the environment "
    "the store was given. The check's store is given a dictionary of its own, so the process "
    "running the check keeps the keys it had."
)

#: Said when the screen offers no slot a value on this install.
THE_SCREEN_OFFERS_NO_WRITE_HERE: Final = (
    "the Credentials screen offers no slot a value on this install, which it does while the vault "
    "is absent, sealed or unread, and says so on every slot; once the vault answers, it can run"
)

# ------------------------------------------------------------------------ the figures
#: The authority the screen asks. Restated rather than imported, so a change to the route's
#: authority fails the check instead of moving with it.
MANAGES_CREDENTIALS: Final = "admin:credential"

#: The most rows one page of the list may carry, which the check asks for so it reads few pages.
PAGE: Final = 200


# ------------------------------------------------------------------------ the helpers
class KeptHere:
    """An in-memory vault holding a version of every slot it is asked about, and every write.

    See `A_WRITE_GOES_TO_A_VAULT_OF_THE_CHECKS_OWN`. Holding a version of every slot is what lets a
    slot whose first value goes in elsewhere be replaced here, as it is on an install where it was
    set up. `written` keeps the paths and never the values.
    """

    def __init__(self) -> None:
        self.written: list[str] = []

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        del fields
        self.written.append(path)
        return datetime.now(UTC)

    def static_kv_version(self, path: str) -> StaticVersion | None:
        del path
        return StaticVersion(written_at=datetime.now(UTC))

    def read_static_kv(self, path: str) -> dict[str, Any]:
        del path
        return {}


def installs_vault(h: Harness) -> OpenBaoVault | None:
    """The application's vault client as `brain.app.vault_at_start` builds it, which nothing under
    `src` may import: none without both settings, none for an address that is not a URL."""
    from brain.ops.openbao import OpenBaoVault
    from brain.ops.secrets import VaultRole

    address, token = h.settings.vault_address, h.settings.vault_token
    if not address or not token:
        return None
    try:
        return OpenBaoVault(address, token, role=VaultRole.APPLICATION)
    except ValueError:
        return None


def store_of_the_checks_own(
    h: Harness, kept: KeptHere, *, outranking: frozenset[str] = frozenset()
) -> Credentials:
    """The product's `Credentials` over `kept`, recording to the check's transaction."""
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials

    return Credentials(
        kept,
        outranking=outranking,
        environ={},
        writes=StoredCredentialWrites(h.sessions),
    )


def screen_over(h: Harness, store: Credentials, vault: OpenBaoVault | None) -> Console:
    """The console application with the install's vault to read and the check's store to write."""
    console = console_for(h)
    console.app.state.vault = vault
    console.app.state.credentials = store
    return console


async def every_row(h: Harness, console: Console, admin: str) -> list[CredentialRow]:
    """Every row of the list, page by page, as the screen pages it."""
    from brain.credential_routes import credentials
    from brain.listing import ListAsked

    rows: list[CredentialRow] = []
    cursor: str | None = None
    for _ in range(50):
        page: CredentialsPage = await credentials(
            console.request(),
            await asking_as(h, admin, strong=True),
            ListAsked(limit=PAGE, cursor=cursor),
        )
        rows.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            return rows
    raise CheckFailedError("the Credentials list did not come to an end")


def a_value(fields: tuple[str, ...]) -> dict[str, Any]:
    """A body for a slot: `value` for a slot of one field, `values` naming each field otherwise."""
    if len(fields) == 1:
        return {"value": secrets.token_urlsafe(32)}
    return {"values": {name: secrets.token_urlsafe(32) for name in fields}}


def is_a_sentence(said: str) -> bool:
    """Whether a reason is words a person reads rather than a code or a blank."""
    return len(said.split()) >= 4


# ------------------------------------------------------- 1. the Credentials screen (M27.11.10)
@check(
    leaves=("M27.11.10", "M27.15.50"),
    sentence=(
        "An administrator of credentials is shown every slot this install declares and its "
        "vault's state with no value, writes every slot the screen offers and is told it is held "
        "without being sent it back, sees the write in the slot's history, is told why any other "
        "slot is not offered and which variable outranks a slot; a department's administrator "
        "and a person without the authority are refused."
    ),
)
async def every_slot_is_listed_and_written_from_the_screen_never_read_back(
    h: Harness,
) -> None:
    from brain.credential_routes import CredentialAsked, credential, credentials, set_credential
    from brain.listing import ListAsked
    from brain.ops.credential_catalogue import declared_slots
    from brain.ops.credentials import KEY_FIELD

    await h.found_departments()
    admin, narrow, other = (
        h.principal(A, "credentials"),
        h.principal(A, "credentials-a"),
        h.principal(A, "other"),
    )
    await h.person(admin, department=A, grants=((MANAGES_CREDENTIALS, Scope.unrestricted()),))
    await h.person(narrow, department=A, grants=((MANAGES_CREDENTIALS, Scope.department(A)),))
    await h.person(other, department=A)
    vault = installs_vault(h)
    kept = KeptHere()
    store = store_of_the_checks_own(h, kept)
    console = screen_over(h, store, vault)
    for asker in (narrow, other):
        if not await refused(
            credentials(
                console.request(), await asking_as(h, asker, strong=True), ListAsked(limit=PAGE)
            )
        ):
            raise CheckFailedError("Credentials answered a person without the authority over all")

    from brain.install import value_of
    from brain.ops.object_store import BACKEND_SETTING

    declared = declared_slots(store, backend=value_of(BACKEND_SETTING))
    rows = await every_row(h, console, admin)
    if [one.slot for one in rows] != [one.path for one in declared]:
        raise CheckFailedError("Credentials did not list every slot this install declares")
    unexplained = [one for one in rows if not one.writable and not is_a_sentence(one.write_told)]
    if unexplained:
        raise CheckFailedError("a slot the screen does not offer did not say why in words")
    offered = [one for one in rows if one.writable]
    if not offered:
        raise CheckNotRunError(THE_SCREEN_OFFERS_NO_WRITE_HERE)

    by_path = {one.path: one for one in declared}
    for n, row in enumerate(offered, start=1):
        body = a_value(by_path[row.slot].fields)
        async with traced(h, n):
            answer = await set_credential(
                console.request("PUT"),
                row.family,
                row.name,
                CredentialAsked(**body),
                await asking_as(h, admin, strong=True),
            )
        sent = json.loads(bytes(answer.body))
        if answer.status_code != 200 or sent.get("held") is not True:
            raise CheckFailedError("a slot the screen offers was not written from it")
        given = [body["value"]] if "value" in body else list(body["values"].values())
        if any(one in json.dumps(sent) for one in given):
            raise CheckFailedError("writing a credential sent the value back")
    if sorted(kept.written) != sorted(row.slot for row in offered):
        raise CheckFailedError("the slots written were not the slots the screen offered")

    first = offered[0]
    detail = await credential(
        console.request(), first.family, first.name, await asking_as(h, admin, strong=True)
    )
    if detail.history is None or admin not in [one.by_id for one in detail.history]:
        raise CheckFailedError("a slot's history did not name who wrote it from the screen")

    providers = [one for one in declared if one.env_var and KEY_FIELD in one.fields]
    if providers:
        variable = providers[0].env_var
        outranks = store_of_the_checks_own(h, KeptHere(), outranking=frozenset({variable}))
        outranked = screen_over(h, outranks, vault)
        shown = {one.slot: one for one in await every_row(h, outranked, admin)}
        if shown[providers[0].path].outranked_by != variable:
            raise CheckFailedError(
                "a slot the environment outranks was not named with its variable"
            )
