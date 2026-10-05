"""Connecting a source from the console: who may, what a connection must be, what it does not do.

`brain.ops.connectable` says which sources can be connected and what each asks for,
`brain.ops.credentials` keeps a key, and `brain.ops.connector_store` holds the rows. This module is
the judgement between them and the sentences a person is shown, and it holds no client: the vault
arrives as `brain.ops.credentials.Credentials` and the database as `ConnectorRecords`.

**Who may connect a source is `admin:connector` over that source, and nobody else.** The capability
is `brain.connectors.registry.INSTALL_AUTHORITY`, named once there, and the question is asked of its
scope against the source's name, the way `brain.console.connector_trust.connectors_reachable` asks
the screen's read: a grant narrowed to one source connects that source and no other, and a grant
narrowed by department connects nothing, because a source has no department and a missing field
never satisfies a clause. See `A_GRANT_NARROWED_TO_ONE_SOURCE_CONNECTS_THAT_SOURCE`. It is an
`admin:` verb, so `brain.gate.admission` already withholds it from a session with no second factor.

**Everything wrong with a connection is found before anything is written, and all of it at once.**
The settings by `connectable.settings_problems`, which ends in the connector's own refusal, and the
key by `brain.ops.credentials.problems_with`, told in a source key's words rather than a provider
key's. See `key_problems`.

**What connecting starts, and what it still does not, is said wherever connecting is offered.**
Since 2026-09-17 the worker reads a connected source on its own interval
(`brain.ops.connector_sync`) and keeps what it declares, with the source's visibility rule on every
record, and the table says when each source was last read and how that went. No question is answered
from what it keeps yet, because no row tool is registered for a connected source's records, and a
source with no verified call ceiling is not read at all. The screen and the confirmation carry
`WHAT_CONNECTING_A_SOURCE_STARTS` rather than a control that looks like it did more. And
disconnecting leaves the key in the vault, because the application may not delete one, which
`DISCONNECTING_A_SOURCE` tells the person to finish at the source.

**An edit and a key replacement are asked of the same authority as a connection**, and each says
what it leaves alone: an edit leaves the key, and a replaced key leaves the connection. See
`EDITING_A_SOURCE` and `REPLACING_A_KEY`.

Rejected: generating nothing and asking only for the key, with the source's identifiers filled in
by the first sync. A connection whose scope is decided by what the key happens to reach is exactly
the connector `brain.connectors.contract.ConnectorScope` refuses to build: narrowing later does not
un-fetch what was already read.

Task ids: M42.6.5, M27.11.9, M11.2.6, M11.7.7, M11.7.3
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final

from brain.connectors.declaration import CredentialShape
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.core.entitlement import EntitlementSet
from brain.ops.connectable import (
    CONNECTABLE,
    Connectable,
    SettingProblem,
    given,
    settings_problems,
)
from brain.ops.credentials import (
    CONNECTOR_NAME_PATTERN,
    VaultState,
    key_file_problems,
    problems_with,
    user_and_password,
)

# ------------------------------------------------------------ written-down reasons

#: Why the install authority is asked of its scope and not only whether it is held.
A_GRANT_NARROWED_TO_ONE_SOURCE_CONNECTS_THAT_SOURCE: Final = (
    "admin:connector can be granted over one source, and the screen's own read is narrowed the "
    "same way. Asking only whether the capability is held would let a grant written for one "
    "source connect every source, and write a key for a system its holder was never given. So the "
    "grant's scope is matched against the source's name, a scope with any other clause admits "
    "nothing, and a caller refused this way is refused exactly as one holding no grant at all."
)

#: What connecting starts and what it still does not, said on the screen and in the confirmation.
WHAT_CONNECTING_A_SOURCE_STARTS: Final = (
    "Connecting a source keeps its settings on this install and its key in the vault. The worker "
    "then reads it on its own interval, under its verified call ceiling, and keeps the few fields "
    "it declares, each record carrying the source's own rule about who may see it; the table shows "
    "when each source was last read and how that went. A source with no verified call ceiling, or "
    "whose declaration changed after it was connected, is not read, and its row says why. No "
    "question is answered from what is kept yet: nothing on this release registers a way to ask "
    "for a connected source's records. What it is trusted to read is shown from what it declared "
    "when it was connected, so it can be checked first."
)

#: The confirmation's consequence, in the words a person agrees to.
CONNECTING_A_SOURCE: Final = (
    "The key is written into the vault and never shown again, and the source is recorded as "
    "connected by you, now, with these settings. The ledger records both. "
    + WHAT_CONNECTING_A_SOURCE_STARTS
)

#: The confirmation's consequence for a disconnect.
DISCONNECTING_A_SOURCE: Final = (
    "The source is recorded as disconnected by you, now, and stops being listed as connected; the "
    "ledger records it. Its key stays in the vault, because this system may write a key and may "
    "not delete one, so revoke the key in the source's own settings as well. Connecting it again "
    "asks for a key again."
)

#: What a success says, per change.
CONNECTED: Final = (
    "The source is connected and its key is held in the vault. The worker reads it on its next run "
    "if it can be read, and the table shows when it was read and how that went."
)
DISCONNECTED: Final = (
    "The source is disconnected. Its key is still in the vault: revoke it in the source's own "
    "settings."
)

#: The confirmation's consequence for an edit, in the words a person agrees to.
EDITING_A_SOURCE: Final = (
    "The connection is recorded as disconnected by you and connected again with these settings, "
    "now, as one change; the ledger records both and its history keeps the old settings. What the "
    "source declares with these settings is what you agree to it reading. Its key stays as it is: "
    "replace the key separately if the new settings need another one."
)

#: What an edit's success says.
EDITED: Final = (
    "The source is connected with the new settings. The old connection is kept in its history, "
    "and its key was not changed. The worker reads it with these settings on its next run."
)

#: What an edit that would change nothing is told, against the source rather than a setting.
NOTHING_TO_EDIT: Final = (
    "These are the settings it is connected with, and what it declares is what was agreed to, so "
    "there is nothing to change."
)

#: The confirmation's consequence for replacing a key.
REPLACING_A_KEY: Final = (
    "The new key is written into the vault over the old one and never shown again, and the ledger "
    "records who wrote it. The connection, its settings and what it was agreed to read stay as "
    "they are. The worker uses the new key on its next attempt, so revoke the old key in the "
    "source's own settings once it has read."
)

#: What a replaced key's success says.
KEY_REPLACED: Final = (
    "The new key is held in the vault. The worker uses it on its next attempt; revoke the old key "
    "in the source's own settings."
)

#: What allowing a write agrees to, said before its key is sent (M11.7.3).
ALLOWING_A_WRITE: Final = (
    "The key is written into the vault in a slot of its own, apart from the read key, and never "
    "shown again; the ledger records who wrote it. From then on a change a person in the source's "
    "department approves is sent with it once and read back before it is reported done. Nothing "
    "is sent without that approval, and the connection and its read key stay as they are."
)

#: What a write grant's key being kept says (M11.7.3). The read key is untouched.
WRITE_ALLOWED: Final = (
    "The key for this write is held in the vault, in a slot of its own. From now on a change a "
    "person approves is sent with it, once, and read back with the read key before it is reported "
    "done. The read key is unchanged."
)

#: What asking for a write grant the source does not declare is told, by field.
NO_SUCH_WRITE: Final = "This source has no such write to allow."

#: What an exported connection record says about its key, in place of one.
NO_KEY_IS_EXPORTED: Final = (
    "No key is exported. A key is kept in the vault and never leaves it, so connecting from this "
    "record asks for the key again."
)

#: What a person is told for each vault state when a key is written or asked about.
TOLD: Final[Mapping[VaultState, str]] = MappingProxyType(
    {
        VaultState.ABSENT: (
            "This install runs no secrets vault, so no source's key can be kept and nothing was "
            "connected. Set BRAIN_VAULT_ADDRESS and BRAIN_VAULT_TOKEN in the server's environment "
            "file and restart the system."
        ),
        VaultState.UNREACHABLE: (
            "The secrets vault did not answer, so the key was not kept and nothing was connected. "
            "Check that it is running and unsealed and that the application can reach it, then try "
            "again."
        ),
        VaultState.REFUSED: (
            "The secrets vault answered and refused, so the key was not kept and nothing was "
            "connected. Its token may have expired, or the connector_keys engine or the "
            "application policy may not be loaded: ops/openbao/credential-slots.md has the steps. "
            "Then try again."
        ),
        VaultState.READY: "The secrets vault answered.",
    }
)

#: What the screen says about the vault beside the list, by its state. Nothing when it answered.
VAULT_SAYS: Final[Mapping[VaultState, str]] = MappingProxyType(
    {
        VaultState.ABSENT: (
            "This install runs no secrets vault, so no source can be connected: a source's key "
            "would have nowhere to be kept. Set BRAIN_VAULT_ADDRESS and BRAIN_VAULT_TOKEN in the "
            "server's environment file and restart the system."
        ),
        VaultState.UNREACHABLE: (
            "The secrets vault did not answer when it was asked about the connected sources' keys. "
            "Check that it is running and unsealed and that the application can reach it."
        ),
        VaultState.REFUSED: (
            "The secrets vault refused when it was asked about the connected sources' keys. Its "
            "token may have expired, or the connector_keys engine or the application policy may "
            "not be loaded: ops/openbao/credential-slots.md has the steps."
        ),
        VaultState.READY: "",
    }
)

#: What a person is told for each code `problems_with` gives, in a source key's words rather than
#: a provider key's. A code with no sentence here is told in `problems_with`'s own words.
KEY_SENTENCES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "blank": "Paste the key the source issued for this connection. It is never shown again.",
        "too_long": (
            "That is longer than a key. Check that only the key was copied, and paste it again."
        ),
        "not_one_piece": (
            "The key has a space, a line break or a character a key cannot hold inside it. Copy it "
            "again from the source's settings and paste it without them."
        ),
    }
)

#: The field a key's problems are told against.
KEY_FIELD: Final = "credential"

#: The field a problem with the choice of source is told against, and the field a grant over one
#: source is written against, which is `brain.console.screens.Axis.CONNECTOR`'s spelling.
SOURCE_FIELD: Final = "connector"

_SOURCE_NAME_RE: Final = re.compile(CONNECTOR_NAME_PATTERN)


# ------------------------------------------------------------------- the decisions


def may_connect_source(reach: EntitlementSet, connector: str, now: datetime) -> bool:
    """Whether this reach may connect or disconnect this source, at this instant.

    See `A_GRANT_NARROWED_TO_ONE_SOURCE_CONNECTS_THAT_SOURCE`. A name the slot grammar refuses is
    refused here too, so a route cannot be walked into a vault path by what it was sent.
    """
    if not _SOURCE_NAME_RE.fullmatch(connector):
        return False
    where = reach.scope_for(INSTALL_AUTHORITY, now)
    return where is not None and where.matches({SOURCE_FIELD: connector})


def key_problems(value: str) -> tuple[SettingProblem, ...]:
    """What is wrong with a pasted key: `problems_with`'s judgement, in a source key's words."""
    return tuple(
        SettingProblem(
            field=KEY_FIELD, code=one.code, message=KEY_SENTENCES.get(one.code, one.message)
        )
        for one in problems_with(value)
    )


def credential_problems(shape: CredentialShape, value: str) -> tuple[SettingProblem, ...]:
    """What is wrong with a credential in the shape its source takes it (M11.7.7).

    A key is judged as one, a key file by `key_file_problems` and a database user by
    `user_and_password`, each told against the one `credential` field the request has. See
    `brain.connectors.declaration.A_CREDENTIAL_IS_ASKED_FOR_IN_THE_SHAPE_THE_SOURCE_ISSUES_IT`.
    """
    match shape:
        case CredentialShape.KEY:
            return key_problems(value)
        case CredentialShape.KEY_FILE:
            found = key_file_problems(value)
        case CredentialShape.DATABASE_USER:
            _, found = user_and_password(value)
        case CredentialShape.NONE:
            # Nothing is asked, so nothing given is judged; a value sent anyway is not kept.
            return ()
    return tuple(
        SettingProblem(field=KEY_FIELD, code=one.code, message=one.message) for one in found
    )


async def people_problems(
    kind: Connectable,
    settings: Mapping[str, str],
    *,
    is_live: Callable[[str], Awaitable[bool]],
) -> tuple[SettingProblem, ...]:
    """Every setting naming a person that names nobody live here, in that setting's words (M11.7.7).

    A connector reads no table, so whether an id is somebody is asked here, of the caller's own
    lookup: the routes pass the principal store, and a check its own. See
    `brain.connectors.declaration.Setting.names_a_person`.
    """
    typed = given(kind, settings)
    found: list[SettingProblem] = []
    for one in kind.settings:
        if one.names_a_person and not await is_live(typed[one.name]):
            found.append(SettingProblem(field=one.name, code="refused", message=one.refused))
    return tuple(found)


def connection_problems(
    connector: str, settings: Mapping[str, str], credential: str
) -> tuple[SettingProblem, ...]:
    """Everything wrong with a connection, in field order: the source, its settings, its key.

    A source the console cannot connect is one problem and nothing else is judged, because there
    are no settings to judge it by. Otherwise the settings and the key are both judged, so a form
    with a bad identifier and a bad paste is corrected in one pass.
    """
    kind: Connectable | None = CONNECTABLE.get(connector)
    if kind is None:
        return (
            SettingProblem(
                field=SOURCE_FIELD,
                code="not_connectable",
                message="Choose one of the sources this screen can connect.",
            ),
        )
    return (
        *settings_problems(kind, settings),
        *credential_problems(kind.credential_shape, credential),
    )
