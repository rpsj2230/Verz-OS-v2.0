"""Install acceptance checks for connector safety: a key shown nowhere, a changed declaration shown.

M11.8.9 is the composite leaf that says connector safety is proved on an install. Most of its
clauses already had a check, each written for the leaf it was built under and none for this one:
the run's lease and its revocation, the throttle and the breaker, a replaced key, a field a source
renamed. What no check showed is the two clauses that are about **what a person can see**: that a
key written in the console is shown back by no screen, no response and no log, and that a changed
tool manifest is shown on the Connectors screen and not answered quietly. So this module holds
those two checks and nothing else, and the leaf is named on the checks that prove its other
clauses in `brain.ops.acceptance_checks_connector_framework` and
`brain.ops.acceptance_schema_drift`.

**The key check runs the whole path rather than a screen at a time.** A key is written through the
Connectors screen's own connect route, a run of the worker reads the source with it, the screens
are read as a person would read them, the key is replaced through the replace route, the next run
reads, and the screens are read again. Every body a route returned is searched for both keys, every
log event and standard library record written while it ran is searched for both, and so is every
row of every table. A screen that said which key was held, or a log line that repeated the key a
person typed into a refused request, is found by that search and by nothing short of it: the
tables are searched by `brain.ops.acceptance_checks_connectors._search` and the screens and the
log are searched here. The key is made for the check and good for nothing, and the vault is the
framework check's `_Vault`, which keeps nothing past the check. See
`A_KEY_IS_SEARCHED_FOR_WHEREVER_IT_COULD_BE_SHOWN`.

**The log is listened to without being taken over.** The listener is one structlog processor placed
before every other one, which sees each event before the install's own capture redacts it and
hands it on unchanged, so the install's log keeps what it would have kept and the check sees what
the capture would have been handed. A listener that replaced the processors, as
`structlog.testing.capture_logs` does, would silence the worker's own log for the length of the
check. It also proves it heard: a check whose listener heard nothing says so rather than passing.

**A changed declaration is shown on every surface that shows a source, and read on none.** The
source is connected under a declaration whose one tool description differs from this release's,
which is the silent redefinition the pin is for. The Connectors list says the declaration is not
what was agreed and why nothing reads it, the sources list marks it changed, the drift view names
the tool that changed, the worker's plan refuses it, and a question's live read of it is refused
without a call; connected under this release's declaration, the same read reaches the source. The
renamed field half of the clause is `brain.ops.acceptance_schema_drift`'s, which reads the
sentence the Connectors screen shows. See `A_CHANGED_DECLARATION_IS_SHOWN_AND_NEVER_ANSWERED`.

**No source is called and no real key is held.** Every answer is recorded in the check, in the
envelope Xero documents, and the caller returns it without opening a socket. See
`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

**Both checks connect Xero, so both step aside where the install has it connected.** Connecting a
source that is connected is refused, and moving the owner's aside would hold its lock. See
`A_SOURCE_IS_CONNECTED_HERE_ALREADY`.

Rejected: a third check pushing a source past its ceiling and watching its circuit open. The
framework's burst check and breaker check already do each half, and a composite would restate both
in one transaction. What they show, and what the leaf's wording may not mean, is said in the
commit that added this module: a source refusing on volume is throttled and never opens its circuit
(`brain.connectors.throttle.A_QUOTA_REFUSAL_IS_NOT_ILL_HEALTH`), and one answering with failures
opens it.

Task ids: M11.8.9
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import secrets
import uuid
from typing import TYPE_CHECKING, Any, Final

import structlog

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from collections.abc import Iterator

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 740

# ------------------------------------------------------------------ written-down reasons
#: What both checks say where the install has the source they connect connected already.
A_SOURCE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Xero connected already, so the check does not connect a tenant of its own "
    "beside it and does not ask about it"
)

#: Why the key is looked for in more than the tables.
A_KEY_IS_SEARCHED_FOR_WHEREVER_IT_COULD_BE_SHOWN: Final = (
    "A key is shown to somebody by a screen, by a response, by a log line or by a stored row, and "
    "each is a different code path with its own way of repeating what it was handed. So the check "
    "writes a key through the screen's own route, reads the screens as a person would, and then "
    "searches every body the routes returned, every log event heard while it ran and every row of "
    "every table, for each key it used. A search of one of them is not evidence about the others."
)

#: Why a changed declaration is checked on every surface and not on the one that refuses it.
A_CHANGED_DECLARATION_IS_SHOWN_AND_NEVER_ANSWERED: Final = (
    "A declaration the release changed is refused by the worker's plan and by a question's live "
    "read, and each refusal alone would leave a person looking at a source that reads as "
    "connected and answers nothing. So the check asks each place a person is told about a source, "
    "and the two places something reads it, and holds them together."
)

#: Said when the key check's listener heard nothing, which would make its search worth nothing.
THE_LISTENER_HEARD_NOTHING: Final = (
    "the check's listener on the log heard no event while the Connectors routes ran, so a search "
    "of it could not have found a key"
)

# ------------------------------------------------------------------------ the figures
#: The authorities the checks' people hold. Restated rather than imported, so a change to a
#: route's authority fails its check instead of moving with it.
CONNECTS_SOURCES: Final = "admin:connector"

#: What a refused connect is typed with: a tenant that is not an identifier, and so not Xero's.
NOT_A_TENANT: Final = "not an identifier"


# ------------------------------------------------------------------------ the helpers
@contextlib.contextmanager
def _listening() -> Iterator[list[str]]:
    """Every log event and library log record written inside the block, as text.

    One structlog processor placed first, which records the event and returns it unchanged, and one
    handler on the root of the standard library's loggers. Both are taken out again whatever
    happens, and neither changes what the install's own processors do. See the module docstring.
    """
    heard: list[str] = []

    def watch(logger: Any, method: str, event: Any) -> Any:
        del logger, method
        heard.append(repr(event))
        return event

    class Tap(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            heard.append(self.format(record))

    tap = Tap(level=logging.DEBUG)
    root = logging.getLogger()
    structlog.configure(processors=[watch, *structlog.get_config()["processors"]])
    root.addHandler(tap)
    try:
        yield heard
    finally:
        root.removeHandler(tap)
        structlog.configure(
            processors=[one for one in structlog.get_config()["processors"] if one is not watch]
        )


def _said(shown: list[str], body: Any) -> None:
    """Keep what a route answered, as text, to be searched for a key."""
    shown.append(body.decode("utf-8") if isinstance(body, bytes) else body.model_dump_json())


def _hid(keys: tuple[str, ...], where: list[str]) -> bool:
    """Whether none of the keys is in any of the texts."""
    return not any(key in text for key in keys for text in where)


# ------------------------------------------------ 1. a key is shown back nowhere
@check(
    leaves=("M11.8.9",),
    sentence=(
        "A Xero key written through the Connectors route is used by one worker read under a run "
        "token given back when it ends; the key replaced through the route is the one the next "
        "read sends, nothing restarted. No response or screen the routes gave, no log event and "
        "no table holds either key, and a refused connect repeats none."
    ),
)
async def a_key_written_through_connectors_is_shown_back_nowhere(h: Harness) -> None:
    from brain.connector_routes import (
        ConnectAsked,
        ConnectorKeyAsked,
        connect,
        connector_probe,
        connector_source,
        connector_sources,
        connectors,
        declaration_drift,
        export_connector,
        replace_key,
    )
    from brain.connectors.contract import HealthState
    from brain.console.connector_detail import SourceStatus
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_connector_framework import _Answering, _listed, _Vault
    from brain.ops.acceptance_checks_connectors import (
        SOURCE,
        _clock,
        _no_wait,
        _Resolver,
        _search,
        _settings,
    )
    from brain.ops.acceptance_operations_console import asking_as, console_for, screen_grants
    from brain.ops.connector_lease import RUN_LEASE_TTL, LeaseOutcome
    from brain.ops.connector_store import live
    from brain.ops.connector_sync import READ_TO_THE_END, SyncOutcome, plan_for, sync_in_words
    from brain.ops.connector_sync_run import WorkerConnectorKeys, attempt, authorization
    from brain.ops.connector_sync_store import StoredSyncStates, attempt_row, read_live
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials

    if (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckNotRunError(A_SOURCE_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    admin = h.principal(A, "keys")
    await h.person(
        admin,
        department=A,
        grants=((CONNECTS_SOURCES, Scope.unrestricted()), *screen_grants("connectors")),
    )
    vault = _Vault()
    console = console_for(h)
    console.app.state.credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    first, second = secrets.token_hex(24), secrets.token_hex(24)
    shown: list[str] = []

    async def read_screens() -> None:
        """Every screen and response this source has, asked as the person who connected it."""
        asked = await asking_as(h, admin, strong=True)
        view = await connectors(console.request(), asked)
        _said(shown, view)
        ours = [one for one in view.connectors or [] if one.name == SOURCE]
        if len(ours) != 1 or ours[0].key_held is not True or not ours[0].pinned:
            raise CheckFailedError("Connectors did not say a key is held for a source it pins")
        listed = await connector_sources(console.request(), asked, ListAsked(limit=200))
        _said(shown, listed)
        row = next((one for one in listed.items if one.name == SOURCE), None)
        if row is None or row.status is SourceStatus.NOT_CONNECTED or row.declaration_changed:
            raise CheckFailedError("the sources list did not show the source as connected")
        for one in (
            await connector_source(console.request(), SOURCE, asked),
            await export_connector(console.request(), SOURCE, asked),
            await declaration_drift(console.request(), SOURCE, asked),
            await connector_probe(console.request(), SOURCE, asked),
        ):
            _said(shown, one)

    async def read_once(sent: _Answering) -> Any:
        """One scheduled read of the stored connection, recorded as the worker records it."""
        async with h.sessions() as session, session.begin():
            [stored] = [
                one for one in await read_live(session) if one.connection.connector == SOURCE
            ]
        plan = plan_for(stored.connection, last=None, now=h.now)
        if plan.refused or not plan.due or plan.reading is None:
            raise CheckFailedError("the worker's plan would not read a source connected as typed")
        done = await attempt(
            stored,
            plan,
            previous=None,
            sessions=h.sessions,
            keys=WorkerConnectorKeys(vault),
            caller=sent,
            resolver=_Resolver(),
            clock=_clock,
            sleep=_no_wait,
        )
        await h.execute(attempt_row(stored.id, done))
        return done, plan

    with _listening() as heard:
        # A connect the route refuses, typed with the key: no body repeats it.
        refused = await connect(
            console.request("POST"),
            ConnectAsked(connector=SOURCE, settings={"tenant_id": NOT_A_TENANT}, credential=first),
            await asking_as(h, admin, strong=True),
        )
        _said(shown, refused.body)
        if refused.status_code != 422 or (await h.execute(live(SOURCE))).first() is not None:
            raise CheckFailedError("a connect with a tenant that is not one was not refused whole")

        connected = await connect(
            console.request("POST"),
            ConnectAsked(connector=SOURCE, settings=_settings(), credential=first),
            await asking_as(h, admin, strong=True),
        )
        _said(shown, connected.body)
        if connected.status_code != 200 or not any(
            first in held.values() for held in vault.slots.values()
        ):
            raise CheckFailedError("a key typed into the connect route was not kept in the vault")

        # The first run: a token minted for it, used once, and given back when it ended.
        before = _Answering(_listed)
        done, plan = await read_once(before)
        if done.outcome is not SyncOutcome.SYNCED or done.lease is not LeaseOutcome.REVOKED:
            raise CheckFailedError("a read did not give its run token back when it ended")
        if plan.reading is None or before.authorisations() != {
            authorization(plan.reading.key_scheme(), first)
        }:
            raise CheckFailedError("the worker did not send the key the route kept")
        if vault.minted != [(RUN_LEASE_TTL, {"connector": SOURCE})] or vault.revoked != 1:
            raise CheckFailedError("a read did not lease its key for the one run")
        healthy = (await StoredSyncStates(h.sessions).states()).get(SOURCE)
        if healthy is None or healthy.health is not HealthState.OK:
            raise CheckFailedError("a source read to the end was not shown healthy")
        if sync_in_words(plan, healthy) != READ_TO_THE_END:
            raise CheckFailedError("Connectors did not say the source was read to the end")
        await read_screens()

        # Replaced through the route, and the next run, in the same process, sends the new key.
        replaced = await replace_key(
            console.request("POST"),
            SOURCE,
            ConnectorKeyAsked(credential=second),
            await asking_as(h, admin, strong=True),
        )
        _said(shown, replaced.body)
        held = [one for one in vault.slots.values() if second in one.values()]
        if replaced.status_code != 200 or len(held) != 1 or first in held[0].values():
            raise CheckFailedError(
                "a key replaced through the route was not the one the vault held"
            )
        after = _Answering(_listed)
        again, replan = await read_once(after)
        if again.outcome is not SyncOutcome.SYNCED or replan.reading is None:
            raise CheckFailedError("a source was not read after its key was replaced")
        if after.authorisations() != {authorization(replan.reading.key_scheme(), second)}:
            raise CheckFailedError("the next read did not send the key that replaced the last one")
        if len(vault.minted) != 2 or vault.revoked != 2 or again.lease is not LeaseOutcome.REVOKED:
            raise CheckFailedError("a second read did not lease its key for itself")
        await read_screens()

    if not heard:
        raise CheckFailedError(THE_LISTENER_HEARD_NOTHING)
    keys = (first, second)
    if not _hid(keys, shown):
        raise CheckFailedError("a key was shown back in a response the Connectors routes gave")
    if not _hid(keys, heard):
        raise CheckFailedError("a key was written to a log")
    for key in keys:
        if await _search(h, key):
            raise CheckFailedError("a key written through the console was found in a table")


# ------------------------------------------------ 2. a changed declaration is shown, not answered
@check(
    leaves=("M11.8.9",),
    sentence=(
        "A Xero tenant connected under a declaration whose one tool description differs from this "
        "release's is shown on Connectors as not what was agreed and not read, marked changed on "
        "the sources list, its drift names the tool, the worker's plan refuses it and a live read "
        "of it is refused with no call; connected under this release's it is read."
    ),
)
async def a_changed_declaration_is_shown_on_connector_health_not_read(h: Harness) -> None:
    from brain.connector_routes import (
        connector_sources,
        connectors,
        declaration_drift,
    )
    from brain.connectors.contract import FetchRequest
    from brain.connectors.live_read import RECORD_ID_FILTER
    from brain.connectors.manifest import digest_input, manifest_digest
    from brain.connectors.xero import ENTITY_INVOICE
    from brain.console.connector_detail import SourceStatus
    from brain.console.connector_trust import DECLARATION_AGREED
    from brain.console.connector_trust import DECLARATION_CHANGED as SHOWN_AS_CHANGED
    from brain.core.envelope import IdentityMode
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_connector_framework import _Answering, _invoice, _listed
    from brain.ops.acceptance_checks_connectors import (
        SOURCE,
        _clock,
        _Keys,
        _nothing_kept,
        _Resolver,
        _settings,
    )
    from brain.ops.acceptance_operations_console import asking_as, console_for, screen_grants
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync import DECLARATION_NOT_AGREED, plan_for
    from brain.ops.connector_sync_store import read_live
    from brain.ops.live_read_run import ConnectedSources

    if (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckNotRunError(A_SOURCE_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    admin = h.principal(A, "declares")
    await h.person(
        admin,
        department=A,
        grants=((CONNECTS_SOURCES, Scope.unrestricted()), *screen_grants("connectors")),
    )
    settings = _settings()
    declared = manifest_for(SOURCE, settings)
    if not declared.tools:
        raise CheckFailedError("the source the check connects declares no tool to redefine")
    tool = declared.tools[0]
    redefined = dataclasses.replace(
        declared,
        tools=(
            dataclasses.replace(tool, description=f"{tool.description} {h.word()}"),
            *declared.tools[1:],
        ),
    )
    store = StoredConnections(h.sessions)
    said: dict[str, Any] = {"actor": h.actor, "trace_id": h.trace_id, "ent_hash": SET_UP_REACH}
    await store.connect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(redefined),
        agreed=digest_input(redefined),
        keep_key=_nothing_kept,
        **said,
    )
    console = console_for(h)

    async def stored() -> Any:
        async with h.sessions() as session, session.begin():
            [one] = [
                each for each in await read_live(session) if each.connection.connector == SOURCE
            ]
        return one

    async def live_read(caller: _Answering) -> Any:
        """One question's live read of the stored connection, as the answer path makes it."""
        sources = ConnectedSources(
            {SOURCE: (await stored()).connection},
            keys=_Keys(),
            caller=caller,
            resolver=_Resolver(),
            clock=_clock,
        )
        source = sources.source_for(SOURCE, mode=IdentityMode.SERVICE, asker=admin)
        if source is None or sources.reads(SOURCE, ENTITY_INVOICE) is None:
            raise CheckFailedError("a connected source was not one a question reads live")
        request = FetchRequest(
            entity=ENTITY_INVOICE, filters=((RECORD_ID_FILTER, str(uuid.uuid4())),), limit=1
        )
        return await source(request)

    # Connected under a declaration this release no longer makes: shown, and read by nobody.
    asked = await asking_as(h, admin, strong=True)
    view = await connectors(console.request(), asked)
    ours = [one for one in view.connectors or [] if one.name == SOURCE]
    if len(ours) != 1 or ours[0].pinned or ours[0].declaration != SHOWN_AS_CHANGED:
        raise CheckFailedError("Connectors did not show a changed declaration as not agreed")
    if ours[0].sync != DECLARATION_NOT_AGREED:
        raise CheckFailedError("Connectors did not say why a changed declaration is not read")
    listed = await connector_sources(console.request(), asked, ListAsked(limit=200))
    row = next((one for one in listed.items if one.name == SOURCE), None)
    if row is None or row.status is SourceStatus.NOT_CONNECTED or not row.declaration_changed:
        raise CheckFailedError("the sources list did not mark a changed declaration")
    drift = await declaration_drift(console.request(), SOURCE, asked)
    if (
        not drift.changed
        or not drift.known
        or not any(one.kind == "changed" for one in drift.lines)
    ):
        raise CheckFailedError("the drift view did not name what the declaration changed")
    if (
        plan_for((await stored()).connection, last=None, now=h.now).refused
        != DECLARATION_NOT_AGREED
    ):
        raise CheckFailedError("the worker planned a read under a declaration nobody agreed to")
    silent = _Answering(_listed)
    refused = await live_read(silent)
    if silent.asked or refused.rows is not None:
        raise CheckFailedError("a question's live read answered under a changed declaration")

    # Connected under this release's declaration: pinned, said so, and read. The sibling that
    # stops the refusals above being satisfied by a source nothing can read.
    await store.reconnect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(declared),
        agreed=digest_input(declared),
        **said,
    )
    view = await connectors(console.request(), await asking_as(h, admin, strong=True))
    ours = [one for one in view.connectors or [] if one.name == SOURCE]
    if len(ours) != 1 or not ours[0].pinned or ours[0].declaration != DECLARATION_AGREED:
        raise CheckFailedError("Connectors did not show a source under this release's declaration")
    answered = _Answering(lambda url: _listed(url, _invoice(str(uuid.uuid4()), h.word())))
    await live_read(answered)
    if len(answered.asked) != 1:
        raise CheckFailedError("a source under this release's declaration was not read live")
