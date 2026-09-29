"""The install acceptance checks for the connector framework: the interface, the key, the calls.

`brain.ops.acceptance_checks_connectors` proves what a connector may keep. This proves the frame
every connector runs inside: what a connectable source declares, where its key lives and how a run
borrows it, what a read may be sent to, what sits in front of every call, and what a person is told
when a read fails, and what the calls a source was sent come to on its page. Nine checks, split
where the leaves split, and each one drives the functions the
product runs rather than a restatement of them: `brain.ops.connector_sync_run.attempt` for the
worker, `brain.ops.live_read_run.ConnectedSources` under `brain.connectors.live_read.read_live`
for a question, `brain.ops.live_records.SourceRecords` for the lane's refresh, the connect route's
own `connection_problems` and `StoredConnections.connect`, and `brain.gate.answer._unreached` for
the notice.

**No check calls a source, reads the vault or holds a real key.** Every answer is written in the
check in the envelope Xero documents, and the caller hands it back without opening a socket. The
key is minted by the check and dropped with it, and the vault is `_Vault`: the two protocols the
product asks a vault through (`brain.ops.credentials.CredentialVault` for the connect route's
write, `brain.ops.connector_sync_run.RunTokenVault` for a run's token) answered from a dictionary
the check owns, so the product's own `Credentials` and `WorkerConnectorKeys` run unchanged in front
of it. See `brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`, which this
module shares with that one, along with its resolver, its clock and its canary search.

**The source is Xero, for the reason the connector checks give, and every connectable source is
held where the leaf is about all of them.** The interface and the scope at connect are questions
about every source the console connects, so those checks fill each source's form with identifiers
made up for the run (`FORMS`) and a source added to the console without a row there fails the
first check rather than being skipped. See `A_CHECK_FILLS_EACH_FORM_WITH_IDENTIFIERS_OF_ITS_OWN`.

**Two checks write to the database and six do not.** The worker's read and the health it leaves,
and the connect route's key, need the connection and attempt tables, and the notice needs two
reserved people and their reach. Everything else is a function of declarations and recorded
answers, so it runs on any install whatever its database holds, and `tests/unit/
test_acceptance_connector_framework.py` runs those six with no database at all.

**The retry is shown at two budgets, because at the live budget Xero's is never taken.** Xero states
its wait in whole seconds, and a question's reads end by 1.6 seconds, so a stated second plus a
timeout never fits and `read_live` refuses to wait for it: a person is not kept waiting on a source
that asked for time. The same executor at the task lane's budget, which holds the wait, retries once
after the stated wait lengthened by jitter. Both halves are the executor's own rule, and the check
says which budget each was asked at. See `A_WAIT_THE_BUDGET_CANNOT_HOLD_IS_NOT_TAKEN`.

Rejected: checking the throttle, the breaker and the lease by calling their pure functions. Each is
already unit tested that way; what an install has to show is that the executor it runs puts them in
front of a real read, which only a read shows.

Task ids: M38.5.1, M11.1.1, M11.1.3, M11.2.1, M11.2.2, M11.2.3, M11.2.5, M11.2.6, M11.3.1
Task ids: M11.3.2, M11.3.3, M11.3.5, M11.5.1, M11.5.4, M11.5.5, M11.3.4
"""

from __future__ import annotations

import asyncio
import json
import math
import secrets
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

from brain.connectors.contract import FetchRequest, HealthState, identity_mode_default
from brain.connectors.declaration import shipped
from brain.connectors.federation import CONNECTOR_TIMEOUT_MS, FEDERATION_TIMEOUT_MS, FailureReason
from brain.connectors.live_read import (
    LIVE_READ_BUDGET_MS,
    LIVE_READ_TIMEOUT_MS,
    RECORD_ID_FILTER,
    LiveCall,
    LiveFlights,
    LiveRead,
    LiveSources,
    LiveThrottle,
    read_live,
)
from brain.connectors.manifest import manifest_digest
from brain.connectors.xero import ENTITY_INVOICE
from brain.core.envelope import IdentityMode, SideEffect
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check

# The department grants the other checks write, and the Xero helpers the connector checks wrote,
# imported rather than copied.
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_checks_connectors import (
    SOURCE,
    STAND_IN_ADDRESS,
    _clock,
    _no_wait,
    _Resolver,
    _search,
    _settings,
)
from brain.ops.acceptance_run import SET_UP_REACH, Harness
from brain.ops.connectable import CONNECTABLE, given, key_reference, manifest_for
from brain.ops.connector_lease import RUN_LEASE_TTL, RUN_POLICY, LeaseOutcome
from brain.ops.connector_store import Connection, StoredConnections, live
from brain.ops.connector_sync import (
    ADDRESS_REFUSED,
    KEY_DECLINED,
    NO_READING,
    NO_VERIFIED_CEILING,
    READ_TO_THE_END,
    READINGS,
    VAULT_REFUSED,
    SyncOutcome,
    SyncState,
    plan_for,
    sync_in_words,
)
from brain.ops.connector_sync_run import (
    SourceAnswer,
    WorkerConnectorKeys,
    attempt,
    authorization,
)
from brain.ops.connector_sync_store import LiveConnection
from brain.ops.credentials import KEY_FIELD
from brain.ops.limits import MINUTE_SECONDS, LimitScope, connector_ceiling
from brain.ops.live_read_run import ConnectedSources
from brain.ops.secrets import MAX_LEASE

if TYPE_CHECKING:
    from brain.connectors.manifest import ConnectorManifest
    from brain.ops.connector_sync import Attempt
    from brain.ops.connector_sync_run import ConnectorKeys, SourceCaller
    from brain.ops.openbao import RoleToken, StaticVersion
    from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Why each connectable source is connected with identifiers the check made up.
A_CHECK_FILLS_EACH_FORM_WITH_IDENTIFIERS_OF_ITS_OWN: Final = (
    "The interface and the scope at connect are about every source the console connects, so the "
    "check fills each source's form as a person would, with an organisation, account, helpdesk, "
    "folder or database made up for the run in the shape the source's own connection class "
    "accepts, and a credential in the shape the source takes. Nothing is "
    "connected by filling a form, and a source the console gains without a row here fails the "
    "check rather than passing it unexamined."
)

#: Why the retry is asked at two budgets.
A_WAIT_THE_BUDGET_CANNOT_HOLD_IS_NOT_TAKEN: Final = (
    "The executor retries a refusal once, after the wait the source stated lengthened by jitter, "
    "and only when that wait and another timeout fit inside what is left of the question's "
    "budget. Xero states whole seconds and a question's live reads end by 1.6 seconds, so there a "
    "stated second is not waited for; at the task lane's budget the same executor takes it. The "
    "check asks both, so neither half is mistaken for the other."
)

#: Why the check that connects a source grants its steward nothing.
A_CHECK_GRANTS_NOBODY_OUTSIDE_ITS_DEPARTMENTS: Final = (
    "The connect route grants the data steward what a source declares, in the same transaction. "
    "The steward is a real person, and a check writes grants only in its reserved departments, so "
    "the check connects the source as the route does and declares nothing for a steward to be "
    "granted."
)

#: What the connecting check says when the install has the source connected already. Its own
#: words, for the connector checks' reason: connecting it again is refused, and moving the real
#: connection aside would hold its lock while the check runs.
CONNECTED_ALREADY: Final = (
    "this install has the source the check connects connected already, so the check does not "
    "connect it again"
)

# ------------------------------------------------------------------------ the figures
#: How each source the console connects is filled in, by name. See
#: `A_CHECK_FILLS_EACH_FORM_WITH_IDENTIFIERS_OF_ITS_OWN`.
FORMS: Final[Mapping[str, Callable[[], dict[str, str]]]] = MappingProxyType(
    {
        "freshdesk": lambda: {
            "domain": f"acceptance-{secrets.token_hex(4)}.freshdesk.com",
            "department": RESERVED_DEPARTMENTS[0],
        },
        "hubspot": lambda: {"portal_id": str(10**8 + secrets.randbelow(9 * 10**8))},
        SOURCE: _settings,
        "google_drive": lambda: {
            "folder": f"acceptance{secrets.token_hex(8)}",
            "domain": f"acceptance-{secrets.token_hex(4)}.example",
            "department": RESERVED_DEPARTMENTS[0],
            "steward": f"acceptance-steward-{secrets.token_hex(4)}",
        },
        "google_analytics": lambda: {
            "property": str(10**8 + secrets.randbelow(9 * 10**8)),
            "department": RESERVED_DEPARTMENTS[0],
        },
        "search_console": lambda: {
            "site": f"sc-domain:acceptance-{secrets.token_hex(4)}.example",
            "department": RESERVED_DEPARTMENTS[0],
        },
        "laravel": lambda: {
            "schema": f"acceptance_{secrets.token_hex(4)}",
            "client_rule": f"department = {RESERVED_DEPARTMENTS[0]}",
            "user_rule": f"department in {', '.join(RESERVED_DEPARTMENTS)}",
            "max_rows": "500",
            "timeout_seconds": "10",
        },
    }
)

#: Selectors meaning everything, as the leaf means them, written here rather than read from the
#: product's own list so a word dropped from that list is still tried.
EVERYTHING: Final = ("*", "**", "all", "everything")

#: An address that means inside this network on every network: a unique local address, RFC 4193.
#: Not an IPv4 literal, for the client-independence sweep's reason.
INSIDE_ADDRESS: Final = "fd00::1"

#: The timeout M11.5.1 names, in milliseconds. Held against the executor's, which is not compared
#: with itself.
LEAF_TIMEOUT_MS: Final = 800

#: How early a timeout may be measured to fire and still count as that timeout. An event loop's
#: clock may fire a timer a tick early; a tenth of the timeout is far above a tick and far below
#: an executor that did not wait at all.
EARLIEST_FRACTION: Final = 0.9

#: How long a silent source holds its call before the check releases it. Well past the budget, so
#: only the executor's timeout can end the read on time.
HOLD_SECONDS: Final = 5.0

#: How many askers ask for one record at once. The leaf's twenty.
HERD: Final = 20

#: How long the one read the herd shares takes, so the nineteen who follow find it in flight.
HERD_HOLD_SECONDS: Final = 0.05

#: The jitter the retry check hands the executor, so the wait it slept can be read back.
STATED_JITTER: Final = 0.05

#: A wait the source states that fits the task lane's budget and not the live read's, in seconds,
#: as Xero writes it in `Retry-After`; and one that fits neither.
SHORT_WAIT: Final = "1"
LONG_WAIT: Final = "60"

#: The most questions the breaker check asks before deciding the breaker never opened.
MOST_READS: Final = 10

#: Run tokens the vault could mint wider than the connector-run role: renewable, carrying another
#: policy, or living longer than asked.
WIDER: Final = (
    (True, (RUN_POLICY,), timedelta()),
    (False, (RUN_POLICY, "default"), timedelta()),
    (False, (RUN_POLICY,), timedelta(minutes=1)),
)


# ------------------------------------------------------------------------ the helpers
@dataclass
class _Vault:
    """The vault as both halves of the product ask it, over slots the check wrote.

    `brain.ops.credentials.CredentialVault` for the connect route's write, and
    `brain.ops.connector_sync_run.RunTokenVault` with its reader for a run's token. `renewable`,
    `policies` and `longer` shape the token it mints, so a vault configured wider than the
    connector-run role can be asked for. Reads and revocations are counted under a lock, because
    a live read borrows its key from a thread.
    """

    slots: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    renewable: bool = False
    policies: tuple[str, ...] = (RUN_POLICY,)
    longer: timedelta = field(default_factory=timedelta)
    minted: list[tuple[timedelta, dict[str, str]]] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    revoked: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        with self._lock:
            self.slots[path] = dict(fields)
        return _clock()

    def static_kv_version(self, path: str) -> StaticVersion | None:
        from brain.ops.openbao import StaticVersion

        return StaticVersion(written_at=None) if path in self.slots else None

    def read_static_kv(self, path: str) -> dict[str, Any]:
        from brain.ops.openbao import VaultRefusedError

        with self._lock:
            self.reads.append(path)
            held = self.slots.get(path)
        if held is None:
            raise VaultRefusedError("the check's vault holds nothing at that slot", status=404)
        return dict(held)

    def mint_role_token(self, role: str, *, ttl: timedelta, meta: Mapping[str, str]) -> RoleToken:
        from brain.ops.leases import SealedSecret
        from brain.ops.openbao import RoleToken

        del role
        with self._lock:
            self.minted.append((ttl, dict(meta)))
        return RoleToken(
            token=SealedSecret(secrets.token_hex(16)),
            accessor=secrets.token_hex(8),
            lease_seconds=int((ttl + self.longer).total_seconds()),
            renewable=self.renewable,
            policies=self.policies,
        )

    def holding(self, token: RoleToken) -> _Vault:
        del token
        return self

    def revoke_self(self) -> None:
        with self._lock:
            self.revoked += 1


@dataclass
class _Answering:
    """`SourceCaller` answering each call with what `answer` gives for its address. No socket."""

    answer: Callable[[str], SourceAnswer]
    asked: list[tuple[str, dict[str, str]]] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        with self._lock:
            self.asked.append((url, dict(headers)))
        return self.answer(url)

    def authorisations(self) -> set[str]:
        """Every Authorization header this caller was sent, which is where a key travels."""
        return {headers.get("Authorization", "") for _, headers in self.asked}


class _Inside:
    """Every name answers an address inside this network. See `INSIDE_ADDRESS`."""

    def resolve(self, host: str) -> list[str]:
        del host
        return [INSIDE_ADDRESS]


def _listed(url: str, *records: Mapping[str, str]) -> SourceAnswer:
    """A 200 in Xero's envelope for whichever list the address asks for, holding `records`."""
    key = "Contacts" if "/Contacts" in url else "Invoices"
    body = json.dumps({key: list(records)}).encode("utf-8")
    return SourceAnswer(status=200, headers={}, body=body)


def _refusing(
    status: int, headers: Mapping[str, str] | None = None
) -> Callable[[str], SourceAnswer]:
    """An answer of this status to every call, with these headers."""

    def answer(url: str) -> SourceAnswer:
        del url
        return SourceAnswer(status=status, headers=dict(headers or {}), body=b"{}")

    return answer


def _invoice(record_id: str, number: str) -> dict[str, str]:
    """One invoice as Xero's Invoices endpoint writes it."""
    return {"InvoiceID": record_id, "InvoiceNumber": number, "Status": "AUTHORISED"}


def _no_jitter() -> float:
    return 0.0


def _form(name: str) -> dict[str, str]:
    """The settings the check connects this source with. See `FORMS`."""
    fill = FORMS.get(name)
    if fill is None:
        raise CheckFailedError("a source the console can connect has no form this check fills")
    return fill()


def _credential(name: str) -> str:
    """A credential made up for the check in the shape this source takes it (M11.7.7).

    A key, a service account key file or a database user's name and password, each random and
    good for nothing: the check judges it as the connect route would and keeps it nowhere real.
    """
    from brain.connectors.declaration import CredentialShape
    from brain.ops.credentials import SERVICE_ACCOUNT

    match CONNECTABLE[name].credential_shape:
        case CredentialShape.KEY:
            return secrets.token_hex(24)
        case CredentialShape.KEY_FILE:
            return json.dumps(
                {
                    "type": SERVICE_ACCOUNT,
                    "client_email": f"acceptance-{secrets.token_hex(4)}@acceptance.example",
                    "private_key": secrets.token_hex(32),
                }
            )
        case CredentialShape.DATABASE_USER:
            return json.dumps(
                {"user": f"acceptance_{secrets.token_hex(4)}", "password": secrets.token_hex(16)}
            )


@dataclass
class _Rig:
    """A Xero tenant made up for one check: its settings, manifest, connection, vault and key."""

    settings: dict[str, str]
    manifest: ConnectorManifest
    connection: Connection
    vault: _Vault
    key: str = field(repr=False)

    def sources(self, caller: SourceCaller) -> ConnectedSources:
        """The sources a question reads, as `live_read_run.live_records_for` builds them."""
        return ConnectedSources(
            {SOURCE: self.connection},
            keys=WorkerConnectorKeys(self.vault),
            caller=caller,
            resolver=_Resolver(),
            clock=_clock,
        )


def _rig(
    h: Harness,
    *,
    renewable: bool = False,
    policies: tuple[str, ...] = (RUN_POLICY,),
    longer: timedelta | None = None,
) -> _Rig:
    settings = _settings()
    manifest = manifest_for(SOURCE, settings)
    key = secrets.token_hex(24)
    vault = _Vault(
        slots={manifest.credential.ref.path: {KEY_FIELD: key}},
        renewable=renewable,
        policies=policies,
        longer=longer or timedelta(),
    )
    connection = Connection(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(manifest),
        connected_by=h.actor,
        connected_at=h.now,
    )
    return _Rig(settings=settings, manifest=manifest, connection=connection, vault=vault, key=key)


async def _read(
    h: Harness,
    rig: _Rig,
    caller: SourceCaller,
    *,
    previous: SyncState | None = None,
    keys: ConnectorKeys | None = None,
    resolver: Resolver | None = None,
) -> Attempt:
    """One worker read of the rig's connection, as `connector_sync_run.sync_on` makes it."""
    plan = plan_for(rig.connection, last=None, now=h.now)
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read a source connected as declared")
    return await attempt(
        LiveConnection(id=uuid.uuid4(), connection=rig.connection),
        plan,
        previous=previous,
        sessions=h.sessions,
        keys=keys or WorkerConnectorKeys(rig.vault),
        caller=caller,
        resolver=resolver or _Resolver(),
        clock=_clock,
        sleep=_no_wait,
    )


def _call(
    index: int,
    record_id: str,
    *,
    connector: str = SOURCE,
    mode: IdentityMode = IdentityMode.SERVICE,
) -> LiveCall:
    """One live read of one record, as `live_records.SourceRecords.refresh` plans it."""
    return LiveCall(
        call_id=f"record-{index}",
        connector=connector,
        request=FetchRequest(
            entity=ENTITY_INVOICE, filters=((RECORD_ID_FILTER, record_id),), limit=1
        ),
        identity_mode=mode,
    )


async def _ask(
    sources: LiveSources,
    calls: Sequence[LiveCall],
    *,
    throttle: LiveThrottle | None = None,
    budget_ms: int = LIVE_READ_BUDGET_MS,
    jitter: Callable[[], float] = _no_jitter,
    sleep: Callable[[float], Awaitable[object]] = _no_wait,
) -> LiveRead:
    """One question's live reads through the executor, with its own flights."""
    return await read_live(
        calls,
        sources=sources,
        asker=f"{RESERVED_DEPARTMENTS[0]}.asker",
        throttle=throttle or LiveThrottle(),
        flights=LiveFlights(),
        clock=_clock,
        budget_ms=budget_ms,
        jitter=jitter,
        sleep=sleep,
    )


# -------------------------------------------- 1. the interface, the health, the key's home
@check(
    leaves=("M11.1.1", "M11.2.1"),
    sentence=(
        "Every source the console connects declares read-only tools, read capabilities, one scope "
        "and its key as a vault reference. A Xero tenant connected in the check with a key minted "
        "for it is read by the worker's sync, shown healthy, then shown down with the key declined "
        "after a recorded 401, and the index audit finds the key in no table."
    ),
)
async def a_source_is_read_by_its_declaration_and_its_key_is_in_no_table(
    h: Harness,
) -> None:
    from brain.identity.data_steward import declared_capabilities
    from brain.ops.connector_admin import connection_problems
    from brain.ops.connector_sync_store import StoredSyncStates, attempt_row
    from brain.ops.connector_sync_store import read_live as live_rows
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials, connector_key_slot
    from brain.ops.openbao import CONNECTOR_KEY_PREFIX

    # M11.1.1: what every source the console connects declares about itself.
    for name, kind in CONNECTABLE.items():
        declared = manifest_for(name, _form(name))
        binding = declared.credential
        if binding.ref != key_reference(name) or not binding.ref.path.startswith(
            CONNECTOR_KEY_PREFIX
        ):
            raise CheckFailedError("a source's key is not bound by a reference to its own slot")
        if binding.write_granted_by or not binding.permits(SideEffect.NONE):
            raise CheckFailedError("a source the console connects is bound to write")
        if not declared.tools or not declared.scope.selectors or not kind.settings:
            raise CheckFailedError("a source the console connects declares no tool or no scope")
        for tool in declared.tools:
            if tool.side_effect is not SideEffect.NONE or not tool.name.startswith(f"{name}."):
                raise CheckFailedError("a source declares a tool that is not a read of its own")
        capabilities = declared_capabilities(declared)
        if any(not one.startswith("read:") for one in capabilities) or not {
            f"read:{tool.entity}" for tool in declared.tools
        } <= set(capabilities):
            raise CheckFailedError(
                "a source's declared capabilities are not the reads its tools make"
            )

    if (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckNotRunError(CONNECTED_ALREADY)

    # M11.2.1: connected as the route connects it, with the key kept by the product's own keeper.
    kind = CONNECTABLE[SOURCE]
    settings = given(kind, _settings())
    key = secrets.token_hex(24)
    if connection_problems(SOURCE, settings, key):
        raise CheckFailedError("the connect route refused a source connected as its form asks")
    manifest = kind.build(settings, key_reference(SOURCE))
    slot = connector_key_slot(SOURCE)
    vault = _Vault()
    credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))

    async def keep_key() -> datetime | None:
        kept = await credentials.keep(
            slot, key, actor=h.actor, trace_id=h.trace_id, ent_hash=SET_UP_REACH
        )
        return kept.set_at

    # No steward is declared for: see A_CHECK_GRANTS_NOBODY_OUTSIDE_ITS_DEPARTMENTS.
    await StoredConnections(h.sessions).connect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(manifest),
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=keep_key,
    )
    if slot.path != manifest.credential.ref.path or vault.slots.get(slot.path) != {KEY_FIELD: key}:
        raise CheckFailedError("the key was not kept at the slot the source's declaration names")

    # M11.1.1: the worker reads the connection through its declaration, and health shows it.
    async with h.sessions() as session, session.begin():
        found = [one for one in await live_rows(session) if one.connection.connector == SOURCE]
    if len(found) != 1 or dict(found[0].connection.settings) != settings:
        raise CheckFailedError("the worker did not read back the connection as it was typed")
    connected = found[0]
    plan = plan_for(connected.connection, last=None, now=h.now)
    if plan.refused or not plan.due or plan.reading is None:
        raise CheckFailedError("the worker's plan would not read a source connected as declared")
    answered = _Answering(_listed)
    read = await attempt(
        connected,
        plan,
        previous=None,
        sessions=h.sessions,
        keys=WorkerConnectorKeys(vault),
        caller=answered,
        resolver=_Resolver(),
        clock=_clock,
        sleep=_no_wait,
    )
    if read.outcome is not SyncOutcome.SYNCED or not answered.asked:
        raise CheckFailedError("the worker did not read the connected source to the end")
    if answered.authorisations() != {authorization(plan.reading.key_scheme(), key)}:
        raise CheckFailedError("the worker did not send the key the connection kept")
    await h.execute(attempt_row(connected.id, read))
    healthy = (await StoredSyncStates(h.sessions).states()).get(SOURCE)
    if healthy is None or healthy.health is not HealthState.OK:
        raise CheckFailedError("the Connectors screen did not show a source read to the end as ok")
    if sync_in_words(plan, healthy) != READ_TO_THE_END:
        raise CheckFailedError("the Connectors screen did not say the source was read to the end")

    declined = await attempt(
        connected,
        plan,
        previous=healthy,
        sessions=h.sessions,
        keys=WorkerConnectorKeys(vault),
        caller=_Answering(_refusing(401)),
        resolver=_Resolver(),
        clock=_clock,
        sleep=_no_wait,
    )
    await h.execute(attempt_row(connected.id, declined))
    down = (await StoredSyncStates(h.sessions).states()).get(SOURCE)
    if down is None or down.health is not HealthState.DOWN or down.detail != KEY_DECLINED:
        raise CheckFailedError("a key the source declined did not leave the source down")
    if not sync_in_words(plan, down).startswith(KEY_DECLINED):
        raise CheckFailedError("the Connectors screen did not say the source declined the key")

    # M11.2.1: the search saw what the connection wrote, and the key is in none of it.
    if not {"ops.connector_connection", "ops.credential_write"} <= set(await _search(h, h.actor)):
        raise CheckFailedError("the index audit could not see the rows the connection wrote")
    if await _search(h, key):
        raise CheckFailedError("the key the check connected with was found in a table")


# ------------------------------------------------ 2. a REST read is a spec and a mapping
@check(
    leaves=("M11.1.3",),
    sentence=(
        "Xero's reads are built from its OpenAPI document and a field mapping: an address "
        "resolving inside the network is refused before any call, by the operation and by the "
        "worker's read; "
        "an argument the document does not define is refused while a defined one is prepared; and "
        "a field the mapping does not name never arrives."
    ),
)
async def a_rest_read_is_built_from_a_spec_and_refused_before_a_call(
    h: Harness,
) -> None:
    from brain.connectors.rest import RestSpecError
    from brain.tools.fetch import UnsafeAddressError

    rig = _rig(h)
    reading = READINGS[SOURCE]
    for entity in reading.entities():
        try:
            reading.operation(entity, settings=rig.settings, resolver=_Inside())
        except UnsafeAddressError:
            continue
        raise CheckFailedError("a specification whose server resolves inside the network loaded")
    inside = _Answering(_listed)
    refused = await _read(h, rig, inside, resolver=_Inside())
    if refused.outcome is not SyncOutcome.FAILED or refused.detail != ADDRESS_REFUSED:
        raise CheckFailedError("the worker's read of an address inside the network was not refused")
    if inside.asked:
        raise CheckFailedError("the worker called a source whose address resolved inside")

    operation = reading.operation(ENTITY_INVOICE, settings=rig.settings, resolver=_Resolver())
    first = reading.first_page(ENTITY_INVOICE)
    try:
        operation.prepare({**first, h.word().lower(): "1"}, resolver=_Resolver())
    except RestSpecError:
        pass
    else:
        raise CheckFailedError("an argument the specification does not define was prepared")
    prepared = operation.prepare(first, resolver=_Resolver())
    parts = urlsplit(prepared.url)
    if (
        prepared.address != STAND_IN_ADDRESS
        or parts.scheme != "https"
        or parts.path != operation.operation.path
        or parse_qs(parts.query) != {name: [value] for name, value in first.items()}
    ):
        raise CheckFailedError("a defined argument was not prepared where the specification says")
    try:
        operation.prepare(first, resolver=_Inside())
    except UnsafeAddressError:
        pass
    else:
        raise CheckFailedError("a prepared read was not refused when its address resolved inside")

    record_id, number, unmapped = str(uuid.uuid4()), h.word(), h.word()
    rows = operation.project({"Invoices": [{**_invoice(record_id, number), "Reference": unmapped}]})
    mapped = {one.target for one in operation.transport.fields}
    if len(rows) != 1 or not set(rows[0]) <= mapped:
        raise CheckFailedError("the field mapping let through a field it does not name")
    values = set(map(str, rows[0].values()))
    if not {record_id, number} <= values or unmapped in values:
        raise CheckFailedError("the field mapping lost a field it names or kept one it does not")


# ------------------------------------------------------ 3. one named thing, never everything
@check(
    leaves=("M11.2.3",),
    sentence=(
        "Each source the console connects is connected to the one organisation, account, "
        "helpdesk, folder or database typed and admits no other, and the connect route refuses a "
        "selector of *, **, all or everything for it in that source's own words before any "
        "manifest is built."
    ),
)
async def a_source_is_connected_to_one_named_thing_and_never_to_everything(h: Harness) -> None:
    from brain.connectors.contract import ConnectorContractError
    from brain.ops.connector_admin import connection_problems

    for name, kind in CONNECTABLE.items():
        settings = _form(name)
        key = _credential(name)
        if connection_problems(name, settings, key):
            raise CheckFailedError("the connect route refused a source connected as its form asks")
        scope = manifest_for(name, settings).scope
        # The one thing typed is the setting every selector is, or is inside: a database's views
        # are named within it (`schema.v_client`), everything else is the one selector itself.
        named = [
            one
            for one in kind.settings
            if all(
                selector in (settings[one.name],) or selector.startswith(f"{settings[one.name]}.")
                for selector in scope.selectors
            )
        ]
        if not scope.selectors or len(named) != 1:
            raise CheckFailedError(
                "a connected source's scope names other than the one thing typed"
            )
        setting = named[0]
        for selector in scope.selectors:
            if not scope.admits(selector) or any(
                scope.admits(one) for one in (*EVERYTHING, f"{selector}0")
            ):
                raise CheckFailedError("a connected source's scope admits other than what it names")
        for wide in EVERYTHING:
            everything = {**settings, setting.name: wide}
            told = [
                (one.field, one.code, one.message)
                for one in connection_problems(name, everything, key)
            ]
            if told != [(setting.name, "refused", setting.refused)]:
                raise CheckFailedError("the connect route did not refuse a scope of everything")
            try:
                manifest_for(name, everything)
            except ConnectorContractError:
                continue
            raise CheckFailedError("a manifest was built for a source connected to everything")
    del h


# ---------------------------------------------------- 4. a lease per run, and rotation
@check(
    leaves=("M11.2.2", "M11.2.6"),
    sentence=(
        "Each worker read of a Xero tenant made up for the check mints its own run token with the "
        "run TTL, reads the key through it and revokes it when the read ends; a token the vault "
        "made renewable, gave another policy or a longer life is revoked unread; a key replaced in "
        "the vault between two reads is sent by the next read, nothing restarted."
    ),
)
async def a_run_leases_its_key_and_the_next_run_reads_a_replaced_one(h: Harness) -> None:
    rig = _rig(h)
    keys = WorkerConnectorKeys(rig.vault)
    before = _Answering(_listed)
    first = await _read(h, rig, before, keys=keys)
    if first.outcome is not SyncOutcome.SYNCED or first.lease is not LeaseOutcome.REVOKED:
        raise CheckFailedError("a read did not give its run token back when it ended")
    if rig.vault.minted != [(RUN_LEASE_TTL, {"connector": SOURCE})] or rig.vault.revoked != 1:
        raise CheckFailedError("a read did not mint one run token for its own source")
    if not timedelta() < RUN_LEASE_TTL <= MAX_LEASE:
        raise CheckFailedError("a run token lives longer than the longest lease the vault grants")

    # M11.2.6: the key replaced in the vault, and the same process reading again.
    replaced = secrets.token_hex(24)
    rig.vault.slots[rig.manifest.credential.ref.path] = {KEY_FIELD: replaced}
    after = _Answering(_listed)
    second = await _read(h, rig, after, keys=keys)
    sent_before, sent_after = before.authorisations(), after.authorisations()
    if second.outcome is not SyncOutcome.SYNCED or len(sent_before) != 1 or len(sent_after) != 1:
        raise CheckFailedError("a read did not send one key to the source")
    if (
        sent_before == sent_after
        or not all(rig.key in one for one in sent_before)
        or not all(replaced in one for one in sent_after)
    ):
        raise CheckFailedError("the next read did not send the key that replaced the last one")
    if len(rig.vault.minted) != 2 or rig.vault.revoked != 2:
        raise CheckFailedError("a read did not lease the key for itself")
    if manifest_digest(manifest_for(SOURCE, rig.settings)) != rig.connection.digest:
        raise CheckFailedError("replacing a source's key moved what its connection agreed to")

    # M11.2.2: a token wider than the run role is given back unread.
    for renewable, policies, longer in WIDER:
        wide = _rig(h, renewable=renewable, policies=policies, longer=longer)
        called = _Answering(_listed)
        done = await _read(h, wide, called)
        if done.outcome is not SyncOutcome.FAILED or done.detail != VAULT_REFUSED:
            raise CheckFailedError("a run token wider than the run role was not refused")
        if done.lease is not LeaseOutcome.REVOKED or wide.vault.revoked != 1:
            raise CheckFailedError("a run token wider than the run role was not revoked")
        if wide.vault.reads or called.asked:
            raise CheckFailedError("a run token wider than the run role was read with")


# ------------------------------------------ 5. whose key, how long, and once for many
@check(
    leaves=("M11.2.5", "M11.5.1", "M11.5.4"),
    sentence=(
        "A live read of a Xero record runs only under the service key the source declares: one "
        "asked under the asker's own credentials borrows no key and makes no call. A source that "
        "does not answer is cut off at 800 ms and left out while another answers, inside the live "
        "read budget, and twenty askers of one record at once make one call to it."
    ),
)
async def a_live_read_uses_the_service_key_ends_on_time_and_is_made_once(
    h: Harness,
) -> None:
    from brain.core.envelope import TypedResult
    from brain.knowledge.rows import ENTITY_KEY, ID_KEY, RowRecord
    from brain.ops.live_records import SourceRecords

    # M11.2.5: the asker's own credentials by default, the service's only where declared.
    rig = _rig(h)
    record_id = str(uuid.uuid4())
    number = h.word()
    answered = _Answering(lambda url: _listed(url, _invoice(record_id, number)))
    sources = rig.sources(answered)
    declared = sources.reads(SOURCE, ENTITY_INVOICE)
    if identity_mode_default() is not IdentityMode.DELEGATED:
        raise CheckFailedError("a read declaring no identity does not run as the asker")
    if declared is not IdentityMode.SERVICE or any(
        tool.identity_mode is not declared for tool in rig.manifest.tools
    ):
        raise CheckFailedError("the source's service reads are not the ones it declares")
    own = await _ask(sources, (_call(0, record_id, mode=identity_mode_default()),))
    if own.rows or answered.asked or rig.vault.minted:
        raise CheckFailedError("a read under the asker's own credentials used the service key")
    if [one.reason for one in own.partial.failed] != [FailureReason.NOT_SERVING]:
        raise CheckFailedError("a read under the asker's own credentials was not said unserved")
    served = await _ask(sources, (_call(0, record_id, mode=declared),))
    if list(served.rows) != ["record-0"] or len(answered.asked) != 1:
        raise CheckFailedError("a read under the service key the source declares was not made")

    # M11.5.1: a silent source is cut off at the timeout, and another is answered meanwhile.
    if not LIVE_READ_TIMEOUT_MS == FEDERATION_TIMEOUT_MS == LEAF_TIMEOUT_MS < LIVE_READ_BUDGET_MS:
        raise CheckFailedError("the live read timeout is not the 800 ms the leaf names")
    quiet = str(uuid.uuid4())
    release = threading.Event()

    def silent_for_one(url: str) -> SourceAnswer:
        if quiet in url:
            release.wait(HOLD_SECONDS)
            return SourceAnswer(timed_out=True)
        return _listed(url, _invoice(record_id, number))

    started = time.monotonic()
    try:
        timed = await _ask(
            rig.sources(_Answering(silent_for_one)), (_call(0, record_id), _call(1, quiet))
        )
    finally:
        release.set()
    elapsed_ms = (time.monotonic() - started) * 1000
    if list(timed.rows) != ["record-0"]:
        raise CheckFailedError("a source that answered was not read beside one that did not")
    if [one.reason for one in timed.partial.failed] != [FailureReason.TIMEOUT]:
        raise CheckFailedError("a source that did not answer was not cut off at its timeout")
    if not LIVE_READ_TIMEOUT_MS * EARLIEST_FRACTION <= elapsed_ms < LIVE_READ_BUDGET_MS:
        raise CheckFailedError("a read of a silent source did not end at its timeout in budget")

    # M11.5.4: twenty askers of one record at once, and one call.
    def held(url: str) -> SourceAnswer:
        time.sleep(HERD_HOLD_SECONDS)
        return _listed(url, _invoice(record_id, number))

    herd = _Answering(held)
    herd_sources = rig.sources(herd)

    async def connected() -> LiveSources:
        return herd_sources

    records = SourceRecords(connected=connected, clock=_clock)
    tenant = rig.settings["tenant_id"]
    index = TypedResult[RowRecord](
        records=(
            RowRecord.model_validate(
                {ENTITY_KEY: ENTITY_INVOICE, ID_KEY: record_id, "tenant_id": tenant}
            ),
        ),
        source=SOURCE,
    )
    got = await asyncio.gather(
        *(
            records.refresh(index, source=SOURCE, entity=ENTITY_INVOICE, asker=f"{h.actor}.{one}")
            for one in range(HERD)
        )
    )
    if len(herd.asked) != 1:
        raise CheckFailedError("twenty askers of one record at once made other than one call")
    for one in got:
        if one is None or one.result is None:
            raise CheckFailedError("an asker of a record read once was not answered with it")
        if [row.id for row in one.result.records] != [record_id]:
            raise CheckFailedError("an asker of a record read once was answered with another")


# ------------------------------------------------------ 6. the bucket and the ceiling
@check(
    leaves=("M11.3.1", "M11.3.5"),
    sentence=(
        "Every connectable source's plan and live-read bucket follow its documented row in "
        "brain.ops.limits, and Xero's row states its daily figure in its own note; live reads past "
        "the bucket's burst are refused as quota with no call, and a source with no documented "
        "row, HubSpot, Google Drive and Laravel today, is not read at all."
    ),
)
async def a_burst_is_paced_by_the_source_s_documented_ceiling(h: Harness) -> None:
    from brain.connectors.federation import DEFAULT_PER_SOURCE_CALLS
    from brain.ops.token_bucket import bucket_for

    for name in CONNECTABLE:
        settings = _form(name)
        manifest = manifest_for(name, settings)
        connection = Connection(
            connector=name,
            settings=settings,
            digest=manifest_digest(manifest),
            connected_by=h.actor,
            connected_at=h.now,
        )
        plan = plan_for(connection, last=None, now=h.now)
        row = connector_ceiling(manifest.ceiling)
        if row is None:
            # Refused for its missing ceiling, or before that for having no reading at all, which
            # is Google Drive's and Laravel's case: either way it is not read.
            if plan.refused not in (NO_VERIFIED_CEILING, NO_READING):
                raise CheckFailedError(
                    "a source with no documented ceiling was planned for reading"
                )
            continue
        documented = {("minute", row.per_minute)}
        if row.per_day is not None:
            documented.add(("day", row.per_day))
            if f"{row.per_day:,} calls a day" not in row.note:
                raise CheckFailedError("a daily ceiling is not the figure its documentation states")
        windows = {
            (one.period, one.limit) for one in plan.limits if one.scope is LimitScope.CONNECTOR
        }
        if manifest.ceiling != name or windows != documented:
            raise CheckFailedError("the worker's plan reads a source against another ceiling")
        bucket = bucket_for(name, now=h.now)
        if (
            not math.isclose(bucket.refill_per_second * MINUTE_SECONDS, row.per_minute)
            or bucket.capacity > row.per_minute
        ):
            raise CheckFailedError("a live read bucket is paced other than by the documented row")

    rig = _rig(h)
    throttle = LiveThrottle()
    burst = int(bucket_for(SOURCE, now=h.now).capacity)
    number = h.word()
    answered = _Answering(lambda url: _listed(url, _invoice(str(uuid.uuid4()), number)))
    sources = rig.sources(answered)
    read_through = 0
    refused: list[FailureReason] = []
    for _ in range(burst + 1):
        calls = tuple(_call(one, str(uuid.uuid4())) for one in range(DEFAULT_PER_SOURCE_CALLS))
        asked = await _ask(sources, calls, throttle=throttle)
        read_through += len(asked.rows)
        refused.extend(one.reason for one in asked.partial.failed)
        if refused:
            break
    if read_through != burst or len(answered.asked) != burst:
        raise CheckFailedError("a burst of live reads was not the bucket's burst")
    if not refused or set(refused) != {FailureReason.QUOTA}:
        raise CheckFailedError("a live read past the bucket's burst was not refused as quota")


# ------------------------------------------------------ 7. the breaker and the retry
@check(
    leaves=("M11.3.2", "M11.3.3"),
    sentence=(
        "Recorded 503s open Xero's breaker and the next live read is refused as circuit open with "
        "no call, while as many 429s leave it closed. A 429 stating a one-second wait is retried "
        "once after that wait lengthened by jitter where the budget holds it and not waited for "
        "inside the 1.6 s live budget; a failing sync waits twice as long the second time."
    ),
)
async def failures_open_the_breaker_and_a_refusal_is_retried_in_budget(
    h: Harness,
) -> None:
    rig = _rig(h)

    # M11.3.2: ill health opens the breaker, and an open breaker makes no call.
    failing = _Answering(_refusing(503))
    throttle = LiveThrottle()
    sources = rig.sources(failing)
    opened_after = 0
    for asked in range(1, MOST_READS + 1):
        read = await _ask(sources, (_call(0, str(uuid.uuid4())),), throttle=throttle)
        reasons = [one.reason for one in read.partial.failed]
        if reasons == [FailureReason.CIRCUIT_OPEN]:
            opened_after = asked - 1
            break
        if reasons != [FailureReason.TRANSPORT] or len(failing.asked) != asked:
            raise CheckFailedError("a source answering 503 was not read once per question")
    if not opened_after or len(failing.asked) != opened_after:
        raise CheckFailedError("503s did not open the breaker, or it called through once open")
    busy = _Answering(_refusing(429, {"Retry-After": LONG_WAIT}))
    throttle = LiveThrottle()
    sources = rig.sources(busy)
    for _ in range(opened_after + 1):
        read = await _ask(sources, (_call(0, str(uuid.uuid4())),), throttle=throttle)
        if [one.reason for one in read.partial.failed] != [FailureReason.QUOTA]:
            raise CheckFailedError("a run of refusals for volume opened the breaker")
    if len(busy.asked) != opened_after + 1 or not throttle.breaker(SOURCE).admits(_clock()):
        raise CheckFailedError("a run of refusals for volume opened the breaker")

    # M11.3.3: a stated wait is retried once, lengthened by jitter, when the budget holds it.
    # See A_WAIT_THE_BUDGET_CANNOT_HOLD_IS_NOT_TAKEN.
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    def refused_then_answered() -> _Answering:
        answers = [
            SourceAnswer(status=429, headers={"Retry-After": SHORT_WAIT}, body=b"{}"),
            _listed("/Invoices", _invoice(str(uuid.uuid4()), h.word())),
        ]
        return _Answering(lambda url: answers.pop(0) if len(answers) > 1 else answers[0])

    retried = refused_then_answered()
    read = await _ask(
        rig.sources(retried),
        (_call(0, str(uuid.uuid4())),),
        budget_ms=CONNECTOR_TIMEOUT_MS,
        jitter=lambda: STATED_JITTER,
        sleep=sleep,
    )
    expected = float(SHORT_WAIT) * (1.0 + STATED_JITTER)
    if list(read.rows) != ["record-0"] or len(retried.asked) != 2:
        raise CheckFailedError("a refusal stating a wait the budget holds was not retried")
    if len(slept) != 1 or not math.isclose(slept[0], expected):
        raise CheckFailedError("a retry did not wait the stated time lengthened by jitter")
    slept.clear()
    hurried = refused_then_answered()
    read = await _ask(
        rig.sources(hurried),
        (_call(0, str(uuid.uuid4())),),
        jitter=lambda: STATED_JITTER,
        sleep=sleep,
    )
    if read.rows or len(hurried.asked) != 1 or slept:
        raise CheckFailedError("a person was kept waiting for a wait the live budget cannot hold")
    unstated = _Answering(_refusing(429))
    read = await _ask(
        rig.sources(unstated),
        (_call(0, str(uuid.uuid4())),),
        budget_ms=CONNECTOR_TIMEOUT_MS,
        sleep=sleep,
    )
    if read.rows or len(unstated.asked) != 1 or slept:
        raise CheckFailedError("a refusal that stated no wait was retried at once")

    # M11.3.3 in the worker: a source failing again waits twice as long.
    first = await _read(h, rig, _Answering(_refusing(503)))
    previous = SyncState(
        connector=SOURCE,
        finished_at=first.finished_at,
        outcome=first.outcome,
        health=first.health,
        consecutive_failures=first.consecutive_failures,
        next_attempt_at=first.next_attempt_at,
        detail=first.detail,
        last_synced_at=None,
    )
    second = await _read(h, rig, _Answering(_refusing(503)), previous=previous)
    once = first.next_attempt_at - first.finished_at
    twice = second.next_attempt_at - second.finished_at
    if once != READINGS[SOURCE].refresh_interval() or twice != 2 * once:
        raise CheckFailedError("a source failing twice in a row was not asked twice as late")


# ------------------------------------------------- 8. who is told a source was not read
@check(
    leaves=("M11.5.5",),
    sentence=(
        "A live read of Xero that failed beside a source nobody connected is told to a reserved "
        "person whose reach covers Xero as Xero not reached, and to one whose reach covers nothing "
        "as part of the answer being unavailable, naming neither source; the operator's line names "
        "both sources and why."
    ),
)
async def an_unreached_source_is_named_only_to_an_asker_who_could_see_it(h: Harness) -> None:
    from brain.api_routes import sources_at
    from brain.core.errors import Degraded
    from brain.gate.abstain import scope_of_reach
    from brain.gate.answer import _unreached
    from brain.gate.streaming import AnswerStream, Event, encode
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.rows import entity_capability
    from brain.tools.startup import build_registry

    # The registry the application builds for an install whose rows come from the source, which
    # is the install on which a question reads that source live at all.
    registry = build_registry(source=SOURCE, records=SessionRowSource(h.sessions))
    kinds = sorted(
        {one.entity for one in registry.definitions() if one.source == SOURCE and one.entity}
    )
    if not kinds:
        raise CheckFailedError("an install reading the source registers no row kind under it")
    a, b = RESERVED_DEPARTMENTS
    await h.found_departments()
    seer, other = h.principal(a, "seer"), h.principal(b, "other")
    await h.person(seer, department=a, grants=_in(a, entity_capability(kinds[0]).value))
    await h.person(other, department=b)
    sees = scope_of_reach(sources_at(registry, await h.reach(seer), h.now))
    blind = scope_of_reach(sources_at(registry, await h.reach(other), h.now))
    if SOURCE not in sees.covered or SOURCE in blind.covered:
        raise CheckFailedError("the sources an asker is told about did not follow their reach")

    rig = _rig(h)
    unconnected = next(name for name in sorted(shipped()) if name != SOURCE)
    read = await _ask(
        rig.sources(_Answering(_refusing(503))),
        (_call(0, str(uuid.uuid4())), _call(1, str(uuid.uuid4()), connector=unconnected)),
    )
    if read.rows or {one.connector for one in read.partial.failed} != {SOURCE, unconnected}:
        raise CheckFailedError("the live read did not report both sources it could not read")
    logged = read.partial.trace_lines()
    if {line.split(":", 1)[0] for line in logged} != {SOURCE, unconnected} or not all(
        ": " in line for line in logged
    ):
        raise CheckFailedError("the operator's line did not name every source and its reason")

    public = encode(Event.TEXT, Degraded.public_message)
    told = _unreached(AnswerStream(), [], (), read.partial, sees).frames
    untold = _unreached(AnswerStream(), [], (), read.partial, blind).frames
    if public not in untold or any(SOURCE in one or unconnected in one for one in untold):
        raise CheckFailedError(
            "an asker who could not see the source was told more than unavailable"
        )
    if public in told or not any(SOURCE in one for one in told):
        raise CheckFailedError("an asker who could see the source was not told it by name")
    if any(unconnected in one for one in told):
        raise CheckFailedError("an asker was told the name of a source their reach does not cover")


# ------------------------------------------------------------ 9. what the calls were (M11.3.4)
@check(
    leaves=("M11.3.4",),
    sentence=(
        "Questions read a Xero tenant made up for the check live through the answer path's own "
        "reader, one record served, one refused as over the source's limit and one failing: the "
        "source's page is sent the calls a second and a minute, those in flight, the refused and "
        "failed shares and the latency, and a reader who may see only their own usage none."
    ),
)
async def a_source_s_live_calls_are_measured_on_its_page(h: Harness) -> None:
    from types import SimpleNamespace

    from brain.console.workspace import Basis
    from brain.console_stats_routes import (
        CALLS_ARE_EVERYBODY_S,
        CALLS_ARE_THIS_PROCESS_S,
        connector_calls,
    )
    from brain.core.envelope import TypedResult
    from brain.knowledge.rows import ENTITY_KEY, ID_KEY, RowRecord
    from brain.ops.live_records import SourceRecords

    rig = _rig(h)
    served, over, failing = (str(uuid.uuid4()) for _ in range(3))
    number = h.word()

    def answer(url: str) -> SourceAnswer:
        if over in url:
            # A wait past the question's budget, so the refusal is counted once and not retried.
            return SourceAnswer(status=429, headers={"Retry-After": "60"}, body=b"{}")
        if failing in url:
            return SourceAnswer(status=503, headers={}, body=b"{}")
        return _listed(url, _invoice(served, number))

    sources = rig.sources(_Answering(answer))

    async def connected() -> LiveSources:
        return sources

    records = SourceRecords(connected=connected, clock=_clock)
    # The application's state as the stats route reads it: its live reader and nothing else.
    state = SimpleNamespace(live_records=records)
    before, _ = connector_calls(state, SOURCE, Basis.EVERYONE, _clock())
    if before is None:
        raise CheckFailedError("the source's page was not sent the calls questions made to it")
    if before.requests != 0 or not before.quiet:
        raise CheckFailedError("a source nobody asked about was shown calls")
    tenant = rig.settings["tenant_id"]
    for one in (served, over, failing):
        index = TypedResult[RowRecord](
            records=(
                RowRecord.model_validate(
                    {ENTITY_KEY: ENTITY_INVOICE, ID_KEY: one, "tenant_id": tenant}
                ),
            ),
            source=SOURCE,
        )
        await records.refresh(index, source=SOURCE, entity=ENTITY_INVOICE, asker=h.actor)
    now = _clock()
    calls, told = connector_calls(state, SOURCE, Basis.EVERYONE, now)
    if calls is None or told != CALLS_ARE_THIS_PROCESS_S:
        raise CheckFailedError("the source's page was not sent the calls questions made to it")
    if calls.requests != 3 or calls.concurrency != 0:
        raise CheckFailedError("the source's page did not count each call questions made once")
    if not math.isclose(calls.per_minute, calls.requests / calls.window_seconds * 60.0):
        raise CheckFailedError("the source's calls a minute were not its calls over the window")
    if not math.isclose(calls.per_second * 60.0, calls.per_minute):
        raise CheckFailedError("the source's calls a second and a minute disagree")
    if not (math.isclose(calls.quota_ratio, 1 / 3) and math.isclose(calls.error_ratio, 1 / 3)):
        raise CheckFailedError("the refused and failed shares of the source's calls were wrong")
    if not 0.0 <= calls.latency_p50_ms <= calls.latency_p95_ms:
        raise CheckFailedError("the source's call latency was not measured")
    hidden, why = connector_calls(state, SOURCE, Basis.OWN, now)
    if hidden is not None or why != CALLS_ARE_EVERYBODY_S:
        raise CheckFailedError("a reader of their own usage was shown everybody's calls")
