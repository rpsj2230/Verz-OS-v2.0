"""The install acceptance check that every shipped source is connected from the console.

M11.7.7 asks that no source has to be connected at the server: each is connected, configured and
switched off on the Connectors screen, including the visibility rule and the department it needs.
Until 2026-09-30 Google Drive and the Laravel database could not be, because the screen took one
pasted key and neither a key file nor a database user, and had nowhere to write a view's rule.

**One check walks every source through the three things a person does on the screen**, with the
parts the connect, edit and disconnect routes call and in that order: the form's settings and
credential judged by `brain.ops.connector_admin.connection_problems`, the manifest built by the
source's own form, the connection written by `StoredConnections.connect`, edited by `reconnect`
with a setting changed, and switched off by `disconnect`. Each inside the check's transaction, so
nothing is left, and **no credential reaches the vault**: the key the route would keep is the
check's own made-up one, judged in the shape the source takes it and then handed to
`_nothing_kept`, which keeps nothing, as every connector check here does.

**A source the install has connected already is not connected again.** A connection of that source
is the proof that it connects, and connecting it a second time is refused by the store. Its form is
still judged, so a source whose form broke is still found. See `A_CONNECTED_SOURCE_IS_JUDGED_ONLY`.

**The Lark sources are connected on Connect Lark, which is on the same screen.** They are named by
the declaration's own sentence and walked by Connect Lark's own checks, and anything else found not
connectable here fails this one.

Task ids: M11.7.7
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Mapping
from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_connector_framework import _credential, _form
from brain.ops.acceptance_checks_connectors import _nothing_kept
from brain.ops.acceptance_run import SET_UP_REACH, Harness

A, _ = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: What the check does with a source the install has connected already.
A_CONNECTED_SOURCE_IS_JUDGED_ONLY: Final = (
    "A source this install has connected is connected from the console already, and the store "
    "refuses a second connection of it, so the check judges its form and credential and does not "
    "connect, edit or switch it off: the install's own connection is never touched."
)

#: What each source's edit changes, by name: a setting a person would change, and its new value.
#: Made up for the run, in the shape the source's own connection accepts.
EDITS: Final[Mapping[str, tuple[str, Callable[[], str]]]] = {
    "xero": ("tenant_id", lambda: "22222222-3333-4444-5555-" + secrets.token_hex(6)),
    "hubspot": ("portal_id", lambda: str(10**8 + secrets.randbelow(9 * 10**8))),
    "freshdesk": ("domain", lambda: f"acceptance-{secrets.token_hex(4)}.freshdesk.com"),
    "google_drive": ("folder", lambda: f"acceptance{secrets.token_hex(8)}"),
    "laravel": ("client_rule", lambda: "status in active, pending"),
}

#: A credential in the wrong shape for each kind, which the connect route must refuse.
WRONG_SHAPE: Final = {
    "key": "two words",
    "key_file": json.dumps({"type": "authorized_user"}),
    "database_user": json.dumps({"user": "reader"}),
}


@check(
    leaves=("M11.7.7",),
    sentence=(
        "Every shipped source but Lark's two, which Connect Lark connects, is connected on the "
        "Connectors screen from settings and a credential in its own shape, a key, a key file or "
        "a database user, edited with a setting changed, rules and departments included, and "
        "switched off, all inside the check's transaction, and none has to be connected at the "
        "server."
    ),
)
async def each_source_is_connected_edited_and_switched_off_in_the_console(
    h: Harness,
) -> None:
    from brain.connectors.declaration import shipped
    from brain.connectors.manifest import digest_input, manifest_digest
    from brain.identity.data_steward import declared_capabilities
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.connectable import CONNECTABLE, NOT_FROM_THE_CONSOLE, given, key_reference
    from brain.ops.connector_admin import connection_problems, people_problems
    from brain.ops.connector_store import StoredConnections, live

    # Nothing is left for the server: what the console cannot connect is Connect Lark's.
    if set(CONNECTABLE) | set(NOT_FROM_THE_CONSOLE) != set(shipped()):
        raise CheckFailedError("a shipped source is neither connectable here nor explained")
    if any(not name.startswith("lark_") for name in NOT_FROM_THE_CONSOLE):
        raise CheckFailedError("a source other than Lark's can only be connected at the server")
    if set(EDITS) != set(CONNECTABLE):
        raise CheckFailedError("a source the console connects has no edit this check makes")

    store = StoredConnections(h.sessions)
    said = {"actor": h.actor, "trace_id": h.trace_id, "ent_hash": SET_UP_REACH}
    # A setting naming a person names a reserved person made for the run, and a made-up id is
    # refused, by the lookup the routes make of the principal store.
    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=())
    people = StoredPrincipals(h.sessions)

    async def is_live(principal_id: str) -> bool:
        return await people.live_principal(principal_id) is not None

    for name, kind in CONNECTABLE.items():
        persons = {one.name: steward for one in kind.settings if one.names_a_person}
        settings = given(kind, {**_form(name), **persons})
        credential = _credential(name)
        if connection_problems(name, settings, credential) or await people_problems(
            kind, settings, is_live=is_live
        ):
            raise CheckFailedError("the connect route refused a source connected as its form asks")
        nobody = {**settings, **dict.fromkeys(persons, f"{steward}-nobody")}
        if persons and not await people_problems(kind, nobody, is_live=is_live):
            raise CheckFailedError("a setting naming nobody here was not refused")
        wrong = [
            (one.field, one.code)
            for one in connection_problems(name, settings, WRONG_SHAPE[kind.credential_shape.value])
        ]
        if not wrong or {field for field, _ in wrong} != {"credential"}:
            raise CheckFailedError("a credential in the wrong shape was not refused as the key")
        if (await h.execute(live(name))).scalar_one_or_none() is not None:
            continue  # See A_CONNECTED_SOURCE_IS_JUDGED_ONLY.

        manifest = kind.build(settings, key_reference(name))
        await store.connect(
            connector=name,
            settings=settings,
            digest=manifest_digest(manifest),
            keep_key=_nothing_kept,
            declared=declared_capabilities(manifest),
            agreed=digest_input(manifest),
            **said,
        )
        if (await h.execute(live(name))).scalar_one_or_none() is None:
            raise CheckFailedError("a source connected from its form was not live afterwards")

        setting, value = EDITS[name]
        edited = {**settings, setting: value()}
        if connection_problems(name, edited, credential):
            raise CheckFailedError("an edit a person would make was refused")
        rebuilt = kind.build(given(kind, edited), key_reference(name))
        await store.reconnect(
            connector=name,
            settings=given(kind, edited),
            digest=manifest_digest(rebuilt),
            declared=declared_capabilities(rebuilt),
            agreed=digest_input(rebuilt),
            **said,
        )
        now = {one.connector: one for one in await store.connected()}.get(name)
        if now is None or dict(now.settings) != given(kind, edited):
            raise CheckFailedError("an edited source was not live with the settings it was given")
        if manifest_digest(rebuilt) == manifest_digest(manifest) or now.digest != manifest_digest(
            rebuilt
        ):
            raise CheckFailedError("an edit did not change what the source declares")

        await store.disconnect(name, **said)
        if (await h.execute(live(name))).scalar_one_or_none() is not None:
            raise CheckFailedError("a source switched off was still live")
