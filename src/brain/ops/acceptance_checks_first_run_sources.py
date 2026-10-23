"""The install acceptance checks for connecting a source from first run and where its key lives.

Two leaves that rest on the same route. M42.5.9 is the wizard's connections step and the screens
that connect the sources it names; M42.6.5 is the claim that the key typed into those screens is
kept in the secrets vault and nowhere a person or a table could read it back. The step and the
screens are one request, `POST /connectors`, which first run's data sources step makes with the
administrator's own token after the finishing screen, so a check of the route is a check of both.

**The route is called as the console calls it, over the check's transaction.** The administrator
is a reserved person holding the connector grant, the Connectors list and the connect route are
asked as that person, and the key is kept by the product's own `Credentials` in front of a vault
that is a dictionary the check owns (`brain.ops.acceptance_checks_connector_framework._Vault`).
That is the same stand-in the connector framework's checks use and it says the same thing: the
product writes the key to the slot its declaration names, and not that a particular server's vault
accepted it. What a real vault does is the rehearsal's (`ops/openbao/REHEARSAL.md`) and the
provider-key check's (`brain.ops.acceptance_checks_first_run`).

**The source is whichever keyed one this install has not connected.** A live connection of the same
source is a real one, `StoredConnections.connect` refuses a second, and disconnecting an owner's
source inside a check would hold its lock. So the check takes Xero when it is free and the next
source the console connects with a key when it is not, filled in with identifiers made up for the
run, and says it was not run where every one of them is connected. See
`A_CHECK_STEPS_ASIDE_FROM_A_CONNECTED_SOURCE`.

**The key is looked for where it could be shown, and only where the check wrote.** The connect
response, the Connectors list, the stored connection's settings and the ledger entries of the
check's own trace. It does not search every table for it: that scan grows with the install, and the
connector framework's checks already make it once.

Rejected: driving the browser. The wizard's screens are the console's and the console's tests hold
them; what an install can add is that the route they call works on this install's schema.

Task ids: M42.5.9, M42.6.5
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import structlog
from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.acceptance_operations_console import Console

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1836

A, _B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the check does not connect a source an install already has.
A_CHECK_STEPS_ASIDE_FROM_A_CONNECTED_SOURCE: Final = (
    "A live connection of a source is a real one and a second is refused, and disconnecting an "
    "owner's source inside a check, even one that is rolled back, would hold its lock for the "
    "length of the check. So the check connects a source this install has not, and where it has "
    "connected every one the console offers with a key, it says it was not run."
)

#: Said where every keyed source is connected already.
EVERY_KEYED_SOURCE_IS_CONNECTED: Final = (
    "this install has connected every source the console connects with a key, so the check does "
    "not connect a tenant of its own beside any of them"
)

# ------------------------------------------------------------------------ the figures
#: What a person holds to connect a source. Restated rather than imported, so a change to a route's
#: authority fails its check instead of moving with it.
CONNECTS_SOURCES: Final = "admin:connector"

#: The source tried first, because its ceiling is measured and it names no department of its own.
PREFERRED: Final = "xero"

#: What the wizard's connections answer is when a person names two sources.
TWO_SOURCES: Final = "xero, hubspot"

#: A source name no connector could have: capital letters and a mark a name cannot hold.
NOT_A_SOURCE_NAME: Final = "Not A Source!"


# ------------------------------------------------------------------------ the helpers
def _keyed_candidates() -> list[str]:
    """The sources the console connects with one key, the preferred one first."""
    from brain.connectors.declaration import CredentialShape
    from brain.ops.acceptance_checks_connector_framework import FORMS
    from brain.ops.connectable import CONNECTABLE

    keyed = [
        name
        for name, kind in CONNECTABLE.items()
        if name in FORMS and kind.credential_shape is CredentialShape.KEY
    ]
    return sorted(keyed, key=lambda name: name != PREFERRED)


async def _unconnected(h: Harness) -> str:
    """The first keyed source this install has no live connection of."""
    from brain.ops.connector_store import live

    for name in _keyed_candidates():
        if (await h.execute(live(name))).scalar_one_or_none() is None:
            return name
    raise CheckNotRunError(EVERY_KEYED_SOURCE_IS_CONNECTED)


async def _administrator(h: Harness) -> tuple[str, Console]:
    """A reserved person who may connect a source, and the console's application over the run."""
    from brain.ops.acceptance_operations_console import console_for, screen_grants

    await h.found_departments()
    admin = h.principal(A, "connecting")
    await h.person(
        admin,
        department=A,
        grants=((CONNECTS_SOURCES, Scope.unrestricted()), *screen_grants("connectors")),
    )
    return admin, console_for(h)


# ------------------------------------------------ 1. the connections step and the screens
@check(
    leaves=("M42.5.9",),
    sentence=(
        "The wizard's connections step keeps the sources a person names and sets no installation "
        "value, refuses a name no source could have, and the Connectors screen it hands on to "
        "lists every source the console connects with its form and its steps, connects one in "
        "the console's own request, and then lists it as connected."
    ),
)
async def the_connections_step_hands_on_to_screens_that_connect_a_source(h: Harness) -> None:
    from brain.connector_routes import ConnectAsked, connect, connectors
    from brain.ops.acceptance_checks_connector_framework import _credential, _form, _Vault
    from brain.ops.acceptance_checks_first_run import _enrolment
    from brain.ops.acceptance_operations_console import asking_as
    from brain.ops.connectable import CONNECTABLE
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials
    from brain.setup_wizard import StepId, answer, new_draft, settings_from

    # The step: a list of source names is kept, commits nothing, and a name that is no name is
    # refused beside its own field.
    enrolment, code = _enrolment(h.now)
    kept, problems = answer(
        new_draft(),
        StepId.CONNECTIONS,
        {"connections": TWO_SOURCES},
        enrolment,
        code,
        administrators=0,
        now=h.now,
    )
    if problems or kept == new_draft():
        raise CheckFailedError("the connections step did not keep the sources a person named")

    if settings_from(kept) != settings_from(new_draft()):
        raise CheckFailedError("naming sources in the connections step set an installation value")
    unchanged, refused = answer(
        new_draft(),
        StepId.CONNECTIONS,
        {"connections": NOT_A_SOURCE_NAME},
        enrolment,
        code,
        administrators=0,
        now=h.now,
    )
    if {one.field for one in refused} != {"connections"} or unchanged != new_draft():
        raise CheckFailedError("a name no source could have was not refused beside its own field")

    skipped, none = answer(
        new_draft(),
        StepId.CONNECTIONS,
        {"connections": ""},
        enrolment,
        code,
        administrators=0,
        now=h.now,
    )
    if none or settings_from(skipped) != settings_from(new_draft()):
        raise CheckFailedError("skipping the connections step was refused or set a value")

    # The screen it hands on to: every source the console connects, with a form and its steps.
    name = await _unconnected(h)
    admin, console = await _administrator(h)
    console.app.state.credentials = Credentials(_Vault(), writes=StoredCredentialWrites(h.sessions))
    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        before = await connectors(console.request(), await asking_as(h, admin, strong=True))
        offered = {one.name: one for one in before.connectable}
        if not offered:
            raise CheckFailedError("Connectors listed no source the console connects")
        if set(offered) != set(CONNECTABLE):
            raise CheckFailedError("Connectors did not list every source the console connects")
        if any(not one.steps or not one.credential_label for one in offered.values()):
            raise CheckFailedError("a source was listed with no steps")
        if name not in offered or not offered[name].may_connect:
            raise CheckFailedError("the administrator was not offered the source to connect")

        # One connection, in the request first run's step makes with the administrator's token.
        done = await connect(
            console.request("POST"),
            ConnectAsked(connector=name, settings=_form(name), credential=_credential(name)),
            await asking_as(h, admin, strong=True),
        )
        if done.status_code != 200:
            raise CheckFailedError("the connect request first run makes was not accepted")
        after = await connectors(console.request(), await asking_as(h, admin, strong=True))
    shown = [one for one in after.connectors or [] if one.name == name]
    if len(shown) != 1 or not shown[0].pinned:
        raise CheckFailedError("a source connected from first run was not listed as connected")


# ------------------------------------------------ 2. the key lives in the vault
@check(
    leaves=("M42.6.5",),
    sentence=(
        "A key typed into the connect request is kept in the vault slot the source's declaration "
        "names and shown in no response, list, stored setting or ledger entry; the list says a key "
        "is held and what the source is trusted to read; a blank key and an install with no "
        "vault each write nothing and say why."
    ),
)
async def a_connector_key_is_kept_in_the_vault_and_shown_nowhere(h: Harness) -> None:
    from brain.connector_routes import ConnectAsked, connect, connectors
    from brain.ops.acceptance_checks_connector_framework import (
        _credential,
        _form,
        _Vault,
    )
    from brain.ops.acceptance_operations_console import asking_as
    from brain.ops.connectable import CONNECTABLE, key_reference
    from brain.ops.connector_store import live
    from brain.ops.connector_sync_store import read_live
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import KEY_FIELD, Credentials, connector_key_slot
    from brain.ops.openbao import CONNECTOR_KEY_PREFIX

    name = await _unconnected(h)
    admin, console = await _administrator(h)
    key = _credential(name)
    form = _form(name)
    slot = connector_key_slot(name)
    said: list[str] = []

    async def ask() -> Any:
        return await asking_as(h, admin, strong=True)

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        # An install with no vault is told so and writes nothing, for a source that takes a key.
        console.app.state.credentials = Credentials(None)
        shut = await connect(
            console.request("POST"),
            ConnectAsked(connector=name, settings=form, credential=key),
            await ask(),
        )
        said.append(bytes(shut.body).decode("utf-8"))
        if shut.status_code != 409 or (await h.execute(live(name))).first() is not None:
            raise CheckFailedError(
                "a source that takes a key was connected with no vault to hold it"
            )

        # A blank key is refused in words, and nothing is written for it either.
        vault = _Vault()
        console.app.state.credentials = Credentials(
            vault, writes=StoredCredentialWrites(h.sessions)
        )
        blank = await connect(
            console.request("POST"),
            ConnectAsked(connector=name, settings=form, credential=""),
            await ask(),
        )
        connected_blank = (await h.execute(live(name))).first() is not None
        if blank.status_code != 422 or vault.slots or connected_blank:
            raise CheckFailedError("a blank key was not refused before anything was kept")

        # The key typed is kept at the slot the declaration names, and only there.
        done = await connect(
            console.request("POST"),
            ConnectAsked(connector=name, settings=form, credential=key),
            await ask(),
        )
        said.append(bytes(done.body).decode("utf-8"))
        if done.status_code != 200:
            raise CheckFailedError("a source connected with a key and a form was not connected")
        listed = await connectors(console.request(), await ask())
    said.append(listed.model_dump_json())
    declared = CONNECTABLE[name].build(form, key_reference(name))
    if declared.credential.ref.path != slot.path or not slot.path.startswith(CONNECTOR_KEY_PREFIX):
        raise CheckFailedError("the declaration's key is not at the slot the route keeps it in")

    if list(vault.slots) != [slot.path] or vault.slots[slot.path] != {KEY_FIELD: key}:
        raise CheckFailedError("the key was not kept whole at the one slot of the source")

    # The list says a key is held and what the source reads, and carries neither the key nor a path.
    shown = [one for one in listed.connectors or [] if one.name == name]
    if len(shown) != 1:
        raise CheckFailedError("the list did not show the connected source once")
    if shown[0].key_held is not True:
        raise CheckFailedError("the list did not say a key is held")
    if shown[0].trust is None:
        raise CheckFailedError("the list did not say what the source may read")
    if slot.path in said[-1]:
        raise CheckFailedError("the list named the vault path of a key")

    # The key is in no response, no stored setting and no ledger entry the check's trace wrote.
    if any(key in one for one in said):
        raise CheckFailedError("a response the connect request or the list gave held the key")
    async with h.sessions() as session, session.begin():
        stored = [one for one in await read_live(session) if one.connection.connector == name]
    ledger = (
        await h.execute(
            text("SELECT details FROM obs.audit_entry WHERE trace_id = :trace").bindparams(
                trace=h.trace_id
            )
        )
    ).all()
    places = [json.dumps(dict(one.connection.settings)) for one in stored]
    places += [json.dumps(row[0], default=str) for row in ledger]
    if len(stored) != 1 or any(key in one for one in places):
        raise CheckFailedError("the stored connection was missing or the key was found in it")
