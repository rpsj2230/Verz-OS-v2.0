"""What the Secrets vault screen may say about the vault: open or not, and which slots hold a key.

`brain.credential_routes` lists the provider slots and whether each holds a key, and says the vault
is absent, refused or silent in one word for the whole list. That was enough for a screen that
writes a key and not for the question an operator asks first after a restart, which is whether the
vault is sealed. A sealed vault answers every authenticated call with a 503, which the credentials
list reads as "did not answer", and three people are then sent to look for a network fault when
what the vault needs is three of them to open it.

**The seal is asked first, and asked without the token.** `sys/seal-status` answers for anybody, so
this can say uninitialised, sealed or open even when the application's token has lapsed. Slots are
asked only of an open vault: a sealed one has no answer for them and a list of "unknown" rows under
a sentence saying it is sealed is the true picture. See `THE_SEAL_IS_ASKED_BEFORE_ANY_SLOT`.

**A connector's slot has three states and a provider's two, and the difference is real.** The
installer defines every source's slot with its scopes and no key (`brain.ops.connector_slots`), so
a source's slot is held, defined and empty, or missing, which means the installer's step did not
run. Nothing defines a provider slot ahead of its key, so a provider's is held or empty.

**Never a value.** Every call here reads `sys/seal-status` or a slot's metadata, which carries
version times and custom metadata and no field of the secret, and `SlotReport` has nowhere to put
one.

**Which policies this process's token carries is said, because a policy per role is only a policy
per role while each process holds its own.** Three policy files and an installer that mints the
application's token against `application` say nothing about the token actually in this process's
environment: a root token pasted in during a repair carries every capability and every screen
works. `auth/token/lookup-self` names the token's policies, so the screen says whether it carries
its own role's policy alone (with the vault's `default`, which the installer does not strip). See
`A_ROLES_POLICY_HOLDS_ONLY_WHILE_ITS_PROCESS_CARRIES_IT_ALONE`.

Task ids: M31.3.2.1, M31.3.2.2, M38.4.1.3
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

from brain.ops.connector_slots import SLOT_SCOPES, SlotScopes
from brain.ops.credentials import SLOTS
from brain.ops.openbao import SealStatus, StaticVersion, TokenStanding, VaultRefusedError
from brain.ops.secrets import VaultRole, policy_of

# ------------------------------------------------------------------ written-down reasons

#: Why the seal comes before the slots.
THE_SEAL_IS_ASKED_BEFORE_ANY_SLOT: Final = (
    "A sealed vault answers every authenticated call as unavailable, so a slot list asked of it "
    "reads as a vault that did not answer, and the person reading it looks for a network fault. "
    "The seal status answers for anybody, so it is asked first, and slots are asked only of a "
    "vault that is open."
)


#: Why a token carrying more than its role's policy is reported rather than accepted.
A_ROLES_POLICY_HOLDS_ONLY_WHILE_ITS_PROCESS_CARRIES_IT_ALONE: Final = (
    "Each process's vault token is minted against its own role's policy, so the application cannot "
    "read a connector's key and the browser runner reaches no database. A token carrying root or "
    "another role's policy works on every screen and is wider than the process holding it, so the "
    "screen says so rather than calling the vault healthy."
)

#: The one policy a token may carry beside its role's: the vault attaches it unless told not to,
#: and it grants a token's view of itself.
BESIDE_ITS_OWN: Final = frozenset({"default"})


class Seal(enum.StrEnum):
    """What the vault is, as this process can tell."""

    #: This install names no vault.
    ABSENT = "absent"
    #: A vault is named and did not answer.
    UNREACHABLE = "unreachable"
    #: The vault answered and has never been initialised.
    UNINITIALISED = "uninitialised"
    #: Initialised and sealed: it opens with three of its five pieces.
    SEALED = "sealed"
    #: Initialised and open.
    OPEN = "open"


SEAL_SAYS: Final[Mapping[Seal, str]] = MappingProxyType(
    {
        Seal.ABSENT: (
            "This install names no secrets vault, so no credential can be kept. The installer runs "
            "one on every profile unless it was declined; ops/openbao/UNSEAL.md has the steps."
        ),
        Seal.UNREACHABLE: (
            "A secrets vault is named and did not answer. Check that its container is running "
            "and on the brain-vault network."
        ),
        Seal.UNINITIALISED: (
            "The secrets vault is running and has never been initialised. The installer's vault "
            "steps did not finish: ops/openbao/UNSEAL.md, under Finishing what the installer began."
        ),
        Seal.SEALED: (
            "The secrets vault is sealed, so nothing can read or keep a credential until three "
            "holders of its unseal pieces open it: ops/openbao/UNSEAL.md, under After a restart."
        ),
        Seal.OPEN: "The secrets vault is open.",
    }
)


class SlotState(enum.StrEnum):
    """What a slot holds, as its metadata says."""

    HELD = "held"
    #: Defined with its scopes and holding no key: a connector's slot before go-live.
    DEFINED = "defined"
    #: A provider's slot holding no key, or a connector's the installer never defined.
    EMPTY = "empty"
    #: Not asked, or not answered: see the report's sentence.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SlotReport:
    """One slot: its path, what it is for, what it holds and when that was written."""

    slot: str
    description: str
    state: SlotState
    set_at: datetime | None = None
    #: A connector slot's scopes; empty for a provider's.
    request: tuple[str, ...] = ()
    refuse: tuple[str, ...] = ()


class TokenPolicy(enum.StrEnum):
    """Whether this process's token carries its own role's policy and nothing wider."""

    #: Its role's policy, and at most the vault's `default` beside it.
    OWN = "own"
    #: Anything else: root, another role's policy, or its own missing.
    OTHER = "other"
    #: Not asked, or the vault did not say.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TokenReport:
    """The policies this process's token carries, as the vault named them, and a sentence."""

    state: TokenPolicy
    policies: tuple[str, ...]
    told: str


POLICIES_UNKNOWN: Final = (
    "The vault was not asked, or did not say, which policies this token carries."
)


def token_says(state: TokenPolicy, role: VaultRole) -> str:
    """The sentence beside a token's policies."""
    own = policy_of(role)
    if state is TokenPolicy.OWN:
        return (
            f"This process's token carries the {own} policy and no other, so it can do what "
            f"ops/openbao/policies/{own}.hcl grants and nothing more."
        )
    if state is TokenPolicy.OTHER:
        return (
            f"This process's token does not carry the {own} policy alone, so it is wider or "
            f"narrower than this process should be. Mint one with bao token create -orphan "
            f"-policy={own} -period=768h and replace BRAIN_VAULT_TOKEN: "
            "ops/openbao/credential-slots.md."
        )
    return POLICIES_UNKNOWN


def token_policy_of(policies: tuple[str, ...], role: VaultRole) -> TokenPolicy:
    """OWN only when the role's policy is present and nothing but `default` is beside it."""
    if not policies:
        return TokenPolicy.UNKNOWN
    own = policy_of(role)
    if own in policies and set(policies) <= {own} | BESIDE_ITS_OWN:
        return TokenPolicy.OWN
    return TokenPolicy.OTHER


@runtime_checkable
class TokenLookup(Protocol):
    """A reader that can also say what its own token carries. `OpenBaoVault` is one."""

    def token_standing(self) -> TokenStanding:
        """The token's standing, policies included."""
        ...


def token_report(reader: object, role: VaultRole) -> TokenReport:
    """What this process's token carries. Never raises for the vault."""
    if not isinstance(reader, TokenLookup):
        return TokenReport(TokenPolicy.UNKNOWN, (), POLICIES_UNKNOWN)
    try:
        policies = tuple(sorted(reader.token_standing().policies))
    except Exception:
        # Broad for `report`'s reason: whatever stopped the answer, the vault did not say.
        return TokenReport(TokenPolicy.UNKNOWN, (), POLICIES_UNKNOWN)
    state = token_policy_of(policies, role)
    return TokenReport(state, policies, token_says(state, role))


@dataclass(frozen=True)
class VaultReport:
    """The vault's seal, a sentence about it, and every slot."""

    seal: Seal
    told: str
    providers: tuple[SlotReport, ...]
    connectors: tuple[SlotReport, ...]
    #: Why the slots are unknown when the vault is open and they are, or empty.
    slots_unread: str = ""
    #: What this process's own token carries; unknown unless the vault is open.
    token: TokenReport = TokenReport(TokenPolicy.UNKNOWN, (), POLICIES_UNKNOWN)


class VaultStatusReader(Protocol):
    """What this needs of the vault. `brain.ops.openbao.OpenBaoVault` is one."""

    def seal_status(self) -> SealStatus:
        """Whether the vault is initialised and sealed."""
        ...

    def static_kv_version(self, path: str) -> StaticVersion | None:
        """A slot's current version, or None."""
        ...

    def static_kv_defined(self, path: str) -> bool:
        """Whether a slot's metadata exists at all."""
        ...


SLOTS_REFUSED: Final = (
    "The vault refused this process's token when asked which slots hold a key. The application's "
    "token may have lapsed or its policy may not be loaded: ops/openbao/credential-slots.md."
)
SLOTS_SILENT: Final = "The vault stopped answering while its slots were being read."


def _connector_description(one: SlotScopes) -> str:
    return f"The key {one.connector} issues for this company's connection."


def _unknown(
    providers: Sequence[tuple[str, str]], connectors: Sequence[SlotScopes]
) -> tuple[tuple[SlotReport, ...], tuple[SlotReport, ...]]:
    return (
        tuple(SlotReport(slot=p, description=d, state=SlotState.UNKNOWN) for p, d in providers),
        tuple(
            SlotReport(
                slot=one.path,
                description=_connector_description(one),
                state=SlotState.UNKNOWN,
                request=one.request,
                refuse=one.refuse,
            )
            for one in connectors
        ),
    )


def report(
    reader: VaultStatusReader | None, role: VaultRole = VaultRole.APPLICATION
) -> VaultReport:
    """The vault as this process can see it. Never raises for the vault; see the module doc."""
    providers = [(path, SLOTS[path].description) for path in sorted(SLOTS)]
    connectors = [SLOT_SCOPES[name] for name in sorted(SLOT_SCOPES)]
    unknown_providers, unknown_connectors = _unknown(providers, connectors)
    if reader is None:
        seal = Seal.ABSENT
    else:
        try:
            status = reader.seal_status()
        except Exception:
            # Broad, and the type alone decides nothing: whatever stopped the answer, the vault
            # did not say whether it is sealed, and that is the one thing this reports.
            seal = Seal.UNREACHABLE
        else:
            if not status.initialized:
                seal = Seal.UNINITIALISED
            elif status.sealed:
                seal = Seal.SEALED
            else:
                seal = Seal.OPEN
    if reader is None or seal is not Seal.OPEN:
        return VaultReport(seal, SEAL_SAYS[seal], unknown_providers, unknown_connectors)
    token = token_report(reader, role)
    try:
        held_providers = tuple(
            _provider(reader, path, description) for path, description in providers
        )
        held_connectors = tuple(_connector(reader, one) for one in connectors)
    except VaultRefusedError:
        return VaultReport(
            seal, SEAL_SAYS[seal], unknown_providers, unknown_connectors, SLOTS_REFUSED, token
        )
    except Exception:
        return VaultReport(
            seal, SEAL_SAYS[seal], unknown_providers, unknown_connectors, SLOTS_SILENT, token
        )
    return VaultReport(seal, SEAL_SAYS[seal], held_providers, held_connectors, token=token)


def _provider(reader: VaultStatusReader, path: str, description: str) -> SlotReport:
    version = reader.static_kv_version(path)
    if version is None:
        return SlotReport(slot=path, description=description, state=SlotState.EMPTY)
    return SlotReport(
        slot=path, description=description, state=SlotState.HELD, set_at=version.written_at
    )


def _connector(reader: VaultStatusReader, one: SlotScopes) -> SlotReport:
    version = reader.static_kv_version(one.path)
    if version is not None:
        state, set_at = SlotState.HELD, version.written_at
    elif reader.static_kv_defined(one.path):
        state, set_at = SlotState.DEFINED, None
    else:
        state, set_at = SlotState.EMPTY, None
    return SlotReport(
        slot=one.path,
        description=_connector_description(one),
        state=state,
        set_at=set_at,
        request=one.request,
        refuse=one.refuse,
    )
