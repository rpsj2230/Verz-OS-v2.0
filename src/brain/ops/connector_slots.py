"""A slot in the vault for every source this build has a connector for, with the scopes it needs.

`ops/openbao/credential-slots.md` argued each source's scopes in a table, and that table named
`connectors/creds/<source>`, a leased path nothing reads: since the console began connecting sources
the key is kept at `connector_keys/<source>` (`brain.ops.credentials.connector_key_slot`). The
document had drifted from the code, and the slots it called "defined in OpenBao" were defined
nowhere but in prose. This is the catalogue both now come from.

**Defined in the vault, empty until go-live, and the difference is visible.** The installer writes
each slot's metadata with its scopes as custom metadata (`kv metadata put`), which creates the slot
with no version, so the vault itself says what a source's key must be allowed to do before anybody
issues one. `OpenBaoVault.static_kv_defined` tells a defined slot from one that does not exist, and
`static_kv_version` tells an empty one from a filled one, so the Secrets vault screen can say
"defined, empty" rather than one word for three states. See `A_SLOT_IS_DEFINED_BEFORE_IT_IS_FILLED`.

**Every source has a row, connectable or not.** A source the console cannot connect today still has
a connector in this build, and its scopes are cheapest to argue before the day it becomes
connectable. `slot_gaps` holds the catalogue to `brain.ops.connectable`'s two lists in both
directions, and to the scopes each connectable source's hint tells a person to ask for.

**The words go into a shell command, so their alphabet is closed.** `SAFE_SCOPE` admits letters,
digits, spaces and `._:*,-`, and no quote, so the installer can single-quote a value without
escaping anything. A scope that needs another character is a reason to change this constant and
the installer's quoting together, deliberately.

Task ids: M38.4.1.3
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.ops.connectable import CONNECTABLE, NOT_FROM_THE_CONSOLE
from brain.ops.credentials import connector_key_slot

# ------------------------------------------------------------------ written-down reasons

#: Why a slot exists in the vault before a key does.
A_SLOT_IS_DEFINED_BEFORE_IT_IS_FILLED: Final = (
    "A slot defined with its scopes and holding no key says, on the vault itself, what the key a "
    "vendor issues must be allowed to do, before anybody is in the hour of making a connector "
    "work, which is the hour a write scope gets granted to save a round trip. So the installer "
    "creates every source's slot as metadata with its scopes and no version, and the console tells "
    "a defined, empty slot from a missing one and from a filled one."
)

#: What a scope may be spelled with. See the module docstring.
SAFE_SCOPE: Final = r"^[A-Za-z0-9 ._:*,-]{1,120}$"
_SAFE_SCOPE_RE: Final = re.compile(SAFE_SCOPE)

#: The custom metadata keys the installer writes on a slot.
REQUEST_KEY: Final = "scopes"
REFUSE_KEY: Final = "not_requested"


@dataclass(frozen=True)
class SlotScopes:
    """One source's slot: where its key goes, what to ask its vendor for, and what never to."""

    connector: str
    request: tuple[str, ...]
    refuse: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.request or not self.refuse:
            msg = f"{self.connector} needs at least one scope to ask for and one never to"
            raise ValueError(msg)
        for one in (*self.request, *self.refuse):
            if not _SAFE_SCOPE_RE.fullmatch(one):
                msg = f"{one!r} is not a scope the installer can write without escaping"
                raise ValueError(msg)

    @property
    def path(self) -> str:
        return connector_key_slot(self.connector).path


#: Every source's slot, by the source's name. The scopes are `credential-slots.md`'s, moved here.
SLOT_SCOPES: Final[Mapping[str, SlotScopes]] = MappingProxyType(
    {
        one.connector: one
        for one in (
            SlotScopes(
                "freshdesk",
                request=("an agent API key with read access",),
                refuse=("an admin key, which can change SLAs and delete tickets",),
            ),
            SlotScopes(
                "google_drive",
                request=("read on the named shared drive only",),
                refuse=("domain-wide delegation",),
            ),
            SlotScopes(
                "hubspot",
                request=("crm.objects.contacts.read", "crm.objects.deals.read"),
                refuse=("crm.objects.*.write", "anything touching settings"),
            ),
            SlotScopes(
                "laravel",
                request=("SELECT on the allowlisted views only",),
                refuse=("SELECT on tables", "any write"),
            ),
            SlotScopes(
                "lark_base",
                request=("bitable:app:readonly", "base:record:read"),
                refuse=("base:record:write", "drive:drive"),
            ),
            SlotScopes(
                "lark_wiki",
                request=("wiki:wiki:readonly",),
                refuse=("docs:document edit scopes",),
            ),
            SlotScopes(
                "xero",
                request=("accounting.transactions.read", "accounting.contacts.read"),
                refuse=("any .write scope",),
            ),
        )
    }
)


def slot_gaps() -> tuple[str, ...]:
    """Every disagreement between the catalogue, the sources this build has, and the hints.

    A source with no slot, a slot for no source, and a connectable source whose hint does not name
    a scope its slot asks for, each as a sentence. Empty is the only acceptable answer.
    """
    known = set(CONNECTABLE) | set(NOT_FROM_THE_CONSOLE)
    found = [
        f"{name} has a connector and no credential slot"
        for name in sorted(known - set(SLOT_SCOPES))
    ]
    found += [
        f"{name} has a credential slot and no connector"
        for name in sorted(set(SLOT_SCOPES) - known)
    ]
    for name, kind in sorted(CONNECTABLE.items()):
        slot = SLOT_SCOPES.get(name)
        if slot is None:
            continue
        found += [
            f"{name}'s hint does not ask for {scope}"
            for scope in slot.request
            if scope not in kind.credential_hint
        ]
    return tuple(found)


def metadata_arguments(slot: SlotScopes) -> str:
    """The `kv metadata put` flags that define `slot` with its scopes, single-quoted."""
    return (
        f"-custom-metadata='{REQUEST_KEY}={'; '.join(slot.request)}' "
        f"-custom-metadata='{REFUSE_KEY}={'; '.join(slot.refuse)}'"
    )
