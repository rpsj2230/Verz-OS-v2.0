"""The install acceptance checks that a source connected from the console is ready to use at once.

M11.9.3 to M11.9.14 ask the same three things of each source the owner named: once it is connected
from the console, with no server step, **a permitted person's question is answered from it on the
install, and an agent bound to it can use it**. The neighbouring checks each prove a piece: every
source's form connects on the Connectors screen (M11.7.7), and each source answers a reader on Ask
(M11.6.x, M11.7.x). None of them asked through an agent, and none showed the three in one walk, so
a source could pass each piece and still need a restart, a hand-written setting or an agent
configured at the server before anybody could use it. One check per source walks all three.

**Each walk is the routes' own functions in the routes' order.** The form is judged by the connect
route's own `brain.ops.connector_admin.connection_problems` and `people_problems`, the connection
written by `StoredConnections.connect`, the source read by the worker's own `attempt`, and every
question asked through `/answer`'s own `brain.api_routes.answered_for`, which reads the sources
connected now on each question. The agent is a template naming the source, finished by
`brain.agents.install.settle` against the install's connections as `connectors_of` reads them on a
request, stored, and picked on `/answer` by its id as the web's picker sends it. See
`READY_MEANS_THE_NEXT_QUESTION_AND_THE_NEXT_INSTALL`.

**Bound is shown against unbound, because an agent that answers is only half of it.** A second
agent of the same department, naming no source and holding no read of it, is asked the same
question by the same person and is told what a record that does not exist tells it. Without it an
agent that answered at the caller's own reach, ignoring its ceiling, would pass. See
`AN_AGENT_NOT_BOUND_TO_A_SOURCE_IS_TOLD_WHAT_ABSENCE_TELLS`.

**No socket is opened and no real key is held.** Each source is answered by the recorded caller its
own check already holds, in the vendor's documented envelopes, and every key is minted for the
check (`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`). A Lark Base
switched on for the install is read by none of these checks: the answer route's Base lane is handed
a schema reader that answers nothing, so the install's own Lark is never asked.

**A source the install has connected already is not connected again**, for
`brain.ops.acceptance_checks_connectors.A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`'s reason: the
store refuses a second connection, and the install's own connection is the proof that it connects.

**The CRM is HubSpot.** HubSpot's own module calls itself a CRM, and the Laravel connector calls its
database the portal, which is the maintenance portal (M11.9.9) and not on this module.

**What the Drive, Slack and Lark checks stop short of, said once.** A Drive file's words and a
Slack message are each handed to the model step as a passage, so those walks ask the application's
own passage reader, at the person's reach and at each agent's run reach, rather than a model.
Slack's reader is handed the connection the store holds on each question, as
`brain.ops.live_read_run.slack_passages_for` reads it, and matches the person to their Slack account
by the digest of their work address, which the walk binds with the People page's own statement
(`brain.identity.work_email.binding`): a step on the console, never one at the server. Lark is
connected on Connect Lark, which keeps which Base is switched on as installation settings the whole
process reads, so the Lark walk writes those settings in its transaction through the save's own
store and reads them back through `brain.install.value_of` with what it saved, and does not hold
them for the running process.

Task ids: M11.9.3, M11.9.4, M11.9.5, M11.9.6, M11.9.7, M11.9.8
Task ids: M11.9.10, M11.9.11, M11.9.13, M11.9.14
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_connectors import (
    DUE_DATE,
    _Keys,
    _no_wait,
    _nothing_kept,
    _Recorded,
    _Resolver,
)
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from fastapi import FastAPI

    from brain.connectors.registry import ConnectorRegistry, RegisteredConnector
    from brain.core.entitlement import EntitlementSet
    from brain.gate.answer import Answered
    from brain.ops.connector_store import Connection
    from brain.tools.registry import ToolRegistry

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 420

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: What "ready to use with no server step" is held to.
READY_MEANS_THE_NEXT_QUESTION_AND_THE_NEXT_INSTALL: Final = (
    "A source connected from the console is ready when the very next question is answered from "
    "it and the very next agent naming it installs ready, with nothing set at the server and "
    "nothing restarted. So the walk asks before connecting that no question shape is the "
    "source's, connects it through the route's own store, and then asks and installs through the "
    "route's own functions, which read the connections on each request."
)

#: Why an unbound agent is asked beside the bound one.
AN_AGENT_NOT_BOUND_TO_A_SOURCE_IS_TOLD_WHAT_ABSENCE_TELLS: Final = (
    "An agent answers at its caller's reach narrowed by its own ceiling, so binding is what lets "
    "it read a source. An agent of the same department naming no source and holding none of its "
    "reads, asked the same question by the same person, must be told what a record that does "
    "not exist tells it, or the bound agent's answer proves nothing about binding."
)

#: What a walk says where the install has the source connected already.
THIS_SOURCE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has this source connected already, so the check does not connect it again and "
    "does not ask about it"
)

#: The helpdesk address the Freshdesk walk connects. Reserved, and answered by the recorded caller.
HELPDESK: Final = "acceptance-ready.freshdesk.com"

#: The platform the Lark walk's Base is switched on for, as Connect Lark's form names it. Its host
#: is checked against the recorded Base's own, so a name the form does not know fails the walk.
LARK_PLATFORM: Final = "larksuite.com"


# ------------------------------------------------------------------------ the helpers
@dataclass(frozen=True)
class _Source:
    """A source connected from its form and read by the worker, and what answers it."""

    connection: Connection
    caller: Any
    keys: Any
    poster: Any = None


@dataclass(frozen=True)
class _Asking:
    """What the walk asks: a question naming the record, one naming nothing, and what to hear."""

    present: str
    absent: str
    told: str


class _NoBase:
    """`LarkCaller` and `TokenIssuer` answering nothing, so no Lark Base is read by these checks."""

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> Any:
        from brain.ops.connector_sync_run import SourceAnswer

        del url, address, headers, max_bytes
        return SourceAnswer(status=404, headers={}, body=b"{}")

    def issue(self, host: str, *, app_id: str, app_secret: str) -> str | None:
        del host, app_id, app_secret
        return None


def _prose(answered: Answered) -> str:
    """What the person was told, read from the frames as the web draws them."""
    from brain.ops.acceptance_checks_chat import heard

    return heard(answered.frames).prose


def _asked(field_name: str, slot: str) -> str:
    """The first question shape every connected record is asked in."""
    from brain.knowledge.classified_rows import QUESTION_SHAPES, label_of

    return QUESTION_SHAPES[0].format(label=label_of(field_name), slot=slot)


async def _shapes_of(h: Harness, name: str) -> bool:
    """Whether Ask holds a question shape of this source, read as the answer route reads it."""
    from brain.api_routes import connected_questions_of

    rules = await connected_questions_of(SimpleNamespace(db_sessions=h.sessions))
    return name in {rule.source for rule in rules}


async def _from_the_console(
    h: Harness,
    name: str,
    settings: Mapping[str, str],
    caller: Any,
    *,
    keys: Any = None,
    poster: Any = None,
) -> _Source:
    """Judge the form as the connect route does, connect it, and read it as the worker does.

    Asks first that no question on Ask is the source's, so what the walk proves afterwards was made
    by the connection alone. See `READY_MEANS_THE_NEXT_QUESTION_AND_THE_NEXT_INSTALL`.
    """
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_checks_connector_framework import _credential
    from brain.ops.acceptance_checks_sources import _connection
    from brain.ops.connectable import CONNECTABLE, given
    from brain.ops.connector_admin import connection_problems, people_problems
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync import SyncOutcome, plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import LiveConnection

    if (await h.execute(live(name))).scalar_one_or_none() is not None:
        raise CheckNotRunError(THIS_SOURCE_IS_CONNECTED_HERE_ALREADY)
    kind = CONNECTABLE.get(name)
    if kind is None:
        raise CheckFailedError("a source the owner named is not offered on the Connectors screen")
    if await _shapes_of(h, name):
        raise CheckFailedError("a source nobody connected contributed a question to Ask")
    form = given(kind, settings)
    people = StoredPrincipals(h.sessions)

    async def is_live(principal_id: str) -> bool:
        return await people.live_principal(principal_id) is not None

    if connection_problems(name, form, _credential(name)) or await people_problems(
        kind, form, is_live=is_live
    ):
        raise CheckFailedError("the Connectors screen refused a source connected as its form asks")
    connection = _connection(h, name, form)
    await StoredConnections(h.sessions).connect(
        connector=name,
        settings=connection.settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=_nothing_kept,
    )
    plan = plan_for(connection, last=None, now=h.now)
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read a source connected as declared")
    keys = _Keys() if keys is None else keys
    done = await attempt(
        LiveConnection(id=uuid.uuid4(), connection=connection),
        plan,
        previous=None,
        sessions=h.sessions,
        keys=keys,
        caller=caller,
        resolver=_Resolver(),
        clock=lambda: h.now,
        sleep=_no_wait,
        poster=poster,
    )
    if done.outcome is not SyncOutcome.SYNCED or done.records < 1:
        raise CheckFailedError("the worker did not read a source connected from the console")
    return _Source(connection=connection, caller=caller, keys=keys, poster=poster)


async def _answering(h: Harness, source: _Source) -> FastAPI:
    """The state `/answer` reads, over the check's transaction: the registry, no model, the live
    reader over the one connection, the stored agents, and a Base lane that reads nothing."""
    from fastapi import FastAPI

    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_routing import roster_over
    from brain.ops.lark_base_live import BaseSchema
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tools.startup import build_registry

    async def connected() -> Any:
        return ConnectedSources(
            {source.connection.connector: source.connection},
            keys=source.keys,
            caller=source.caller,
            resolver=_Resolver(),
            clock=lambda: h.now,
            poster=source.poster,
        )

    app = FastAPI()
    state = app.state
    state.settings = h.settings
    state.db_sessions = h.sessions
    state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    state.fast_path_rules = ()
    state.trace_sink = CountingTraceSink()
    state.live_records = SourceRecords(connected=connected, clock=lambda: h.now)
    state.agent_roster = roster_over(h)
    nothing = _NoBase()
    state.lark_base_schema = BaseSchema(
        keys=_Keys(), caller=nothing, resolver=_Resolver(), issuer=nothing, clock=lambda: h.now
    )
    return app


async def _served(h: Harness, *also: RegisteredConnector) -> ConnectorRegistry:
    """The install's connections as `connectors_of` reads them on a request, with `also` beside.

    `connectors_of`'s own body less its reading of a switched-on Lark Base, which reads the
    process's held settings: the Lark walk hands its Base in `also`, built as
    `_switched_on_base` builds it.
    """
    from brain.agent_lifecycle_routes import _registered
    from brain.connectors.registry import ConnectorRegistry
    from brain.ops.connector_store import StoredConnections

    connected = await StoredConnections(h.sessions).connected()
    entries = [one for one in (_registered(c) for c in connected) if one is not None]
    return ConnectorRegistry.of_connected((*entries, *also))


async def _two_agents(
    h: Harness,
    name: str,
    reads: Sequence[str],
    scope: Scope,
    *,
    served: ConnectorRegistry,
    tools: ToolRegistry,
) -> tuple[str, str]:
    """An agent of acceptance_a naming the source and holding its reads, finished against the
    install's connections, and one beside it naming nothing. See
    `AN_AGENT_NOT_BOUND_TO_A_SOURCE_IS_TOLD_WHAT_ABSENCE_TELLS`."""
    from brain.ops.acceptance_checks_skills import _an_agent

    owner = h.principal(A, "builder")
    await h.person(owner, department=A)
    bound = await _an_agent(
        h,
        owner,
        capabilities=reads,
        named="_bound",
        scope=scope,
        connectors=(name,),
        settled=(served, tools),
    )
    unbound = await _an_agent(h, owner, named="_unbound", scope=scope, settled=(served, tools))
    return bound, unbound


async def _run_reaches(h: Harness, principal_id: str, *agents: str) -> tuple[EntitlementSet, ...]:
    """The person's reach on Ask, then each agent's run reach for them, as `/answer` computes it:
    the roster the route reads (`brain.api_routes.roster_of`) and `run_entitlement` over it."""
    from brain.api_routes import Answering, roster_of
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.gate.roster import run_entitlement
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_routing import roster_over
    from brain.tools.startup import build_registry

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    roster = await roster_of(
        SimpleNamespace(agent_roster=roster_over(h)),
        Answering(principal=person, reach=reach, channel=Channel.CONSOLE, now=h.now),
        build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions)),
    )
    found = [roster.records.get(one) for one in agents]
    if any(one is None for one in found):
        raise CheckFailedError("an agent of the person's department was not theirs to ask")
    return reach, *(run_entitlement(reach, one) for one in found)


async def _on_ask(
    h: Harness, app: FastAPI, principal_id: str, question: str, *, agent: str | None = None
) -> Answered:
    """One question through `/answer`'s own function, as the person, through `agent` if named."""
    from brain.api_routes import Answering, Question, answered_for
    from brain.gate.admission import Assurance, admit
    from brain.gate.answer import Answered
    from brain.gate.context import Channel, open_trace
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_threads import _request

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    answering = Answering(principal=person, reach=reach, channel=Channel.CONSOLE, now=h.now)
    trace = open_trace(f"{h.trace_id}-{secrets.token_hex(4)}", h.now, Channel.CONSOLE)
    outcome = await answered_for(
        _request(app), trace, answering, Question(question=question, agent=agent)
    )
    if not isinstance(outcome, Answered):
        raise CheckFailedError("a question was refused by a window the check never installs")
    return outcome


async def _ready_on_ask(
    h: Harness,
    source: _Source,
    asking: _Asking,
    *,
    reads: Sequence[str],
    scope: Scope,
) -> None:
    """The walk after the connection: a permitted person answered, then the bound agent, then the
    unbound one told what absence tells. See the module docstring."""
    if not await _shapes_of(h, source.connection.connector):
        raise CheckFailedError("a source connected from the console contributed no question to Ask")
    app = await _answering(h, source)
    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=tuple((one, scope) for one in reads))
    bound, unbound = await _two_agents(
        h,
        source.connection.connector,
        reads,
        scope,
        served=await _served(h),
        tools=app.state.tools,
    )

    told = await _on_ask(h, app, reader, asking.present)
    if told.composed is None or asking.told not in _prose(told):
        raise CheckFailedError("a permitted person's question was not answered from the source")
    through = await _on_ask(h, app, reader, asking.present, agent=bound)
    if through.composed is None or asking.told not in _prose(through):
        raise CheckFailedError("an agent bound to a connected source could not use it")
    refused = await _on_ask(h, app, reader, asking.present, agent=unbound)
    nothing = await _on_ask(h, app, reader, asking.absent, agent=unbound)
    if asking.told in _prose(refused) or _prose(refused) != _prose(nothing):
        raise CheckFailedError("an agent not bound to a source was answered from it")


# ------------------------------------------------------------- M11.9.3: Google Drive
@check(
    leaves=("M11.9.3",),
    sentence=(
        "A Google Drive folder made up for the check is connected from its form with a key file "
        "and walked by the worker, nothing else set: a permitted person's question is handed the "
        "Doc's words read from Drive, an agent naming Drive installs ready and is handed them too, "
        "and an agent not bound to it is handed what a missing file hands it."
    ),
)
async def google_drive_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.connectors import google_drive
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_drive import DOC_MIME, _Drive, _DriveFile
    from brain.ops.acceptance_checks_google import _KeyFiles, a_key_file
    from brain.ops.drive_passages import DrivePassages, indexed_files
    from brain.tools.startup import build_registry

    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(steward, department=A)
    folder_id, words = f"acceptance{secrets.token_hex(8)}", h.word()
    doc = _DriveFile(
        file_id=f"doc{secrets.token_hex(8)}",
        name=h.word(),
        mime_type=DOC_MIME,
        parent=folder_id,
        words=f"The words of the document are {words}.",
    )
    drive, keys = _Drive(folder_id=folder_id, files=(doc,)), _KeyFiles(a_key_file())
    source = await _from_the_console(
        h,
        google_drive.GOOGLE_DRIVE,
        {
            google_drive.FOLDER_SETTING: folder_id,
            google_drive.DOMAIN_SETTING: f"{h.word().lower()}.example",
            google_drive.DEPARTMENT_SETTING: A,
            google_drive.STEWARD_SETTING: steward,
        },
        drive,
        keys=keys,
        poster=drive,
    )

    async def connected() -> Connection | None:
        return source.connection

    async def indexed() -> Any:
        return await indexed_files(h.sessions)

    passages = DrivePassages(
        connected,
        indexed,
        keys=keys,
        caller=drive,
        poster=drive,
        resolver=_Resolver(),
        clock=lambda: h.now,
    )

    async def handed(reach: EntitlementSet, name: str) -> tuple[str, ...]:
        found = await passages.passages(f"What does {name} say?", entitlement=reach, now=h.now)
        return tuple(one.document for one in found.records)

    reads = (f"read:{google_drive.FILE}",)
    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=tuple((one, Scope.department(A)) for one in reads))
    tools = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    bound, unbound = await _two_agents(
        h,
        google_drive.GOOGLE_DRIVE,
        reads,
        Scope.department(A),
        served=await _served(h),
        tools=tools,
    )
    own, through, beside = await _run_reaches(h, reader, bound, unbound)

    if not any(words in one for one in await handed(own, doc.name)):
        raise CheckFailedError("a permitted person's question was not answered from the source")
    if not any(words in one for one in await handed(through, doc.name)):
        raise CheckFailedError("an agent bound to a connected source could not use it")
    refused, nothing = await handed(beside, doc.name), await handed(beside, h.word())
    if any(words in one for one in refused) or refused != nothing:
        raise CheckFailedError("an agent not bound to a source was answered from it")


# --------------------------------------------------------------------- M11.9.4: Lark
@check(
    leaves=("M11.9.4",),
    sentence=(
        "A Lark Base made up for the check is switched on with Connect Lark's own settings, read "
        "back through the one reader of installation values, and indexed by the worker, nothing "
        "else set: a permitted person's question is answered from Lark, an agent naming the Base "
        "installs ready and answers too, and one not bound to it is told what absence tells."
    ),
)
async def lark_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.api_routes import base_lane_for, covered_at, field_policies, source_field_policies
    from brain.connectors.lark_base import LARK_BASE, fair_share_budget
    from brain.connectors.manifest import manifest_digest
    from brain.connectors.minimal_index import fresh_canary
    from brain.connectors.registry import ConnectorState, RegisteredConnector
    from brain.gate.answer import answer_lane
    from brain.gate.context import Channel
    from brain.gate.finish import Origin
    from brain.identity.principal_store import StoredPrincipals
    from brain.install import value_of
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_lark_base import (
        HOST,
        MODIFIED_TIME,
        TEXT,
        _AppKeys,
        _field,
        _Issuer,
        _made_up,
        _RecordedBase,
    )
    from brain.ops.install_settings import load, save
    from brain.ops.lark_base_index import LARK_BASE_USE, index_base, opened, switched_on
    from brain.ops.lark_base_live import BaseSchema, with_base
    from brain.ops.lark_connect import Use, settings_for
    from brain.ops.live_read_run import ConnectedSources
    from brain.ops.live_records import SourceRecords
    from brain.ops.trace_sink import CountingTraceSink
    from brain.tables.audit import attributed_to
    from brain.tools.startup import build_registry

    await h.found_departments()
    base_id, table_id = _made_up("", 20), _made_up("tbl", 12)
    name, canary, record_id = h.word(), fresh_canary("ACCEPTANCE"), _made_up("rec", 10)
    base = _RecordedBase(
        base_id=base_id,
        table_id=table_id,
        title=f"Accounts {h.word()}",
        fields=(
            _field("fldPrim00001", "Client", TEXT, primary=True),
            _field("fldValu00003", "Contract Value", TEXT),
            _field("fldEdit00004", "Last modified", MODIFIED_TIME),
        ),
        record={
            "record_id": record_id,
            "fields": {"Client": name, "Contract Value": canary, "Last modified": 1552000000000},
        },
    )
    keys, issuer = _AppKeys(), _Issuer()

    # Connect Lark's save: the settings it writes, kept in the check's transaction and read back
    # through the one reader of installation values with what was kept, as the next question reads.
    values = settings_for((Use.BASE,), platform=LARK_PLATFORM, base_link=base_id)
    async with h.sessions() as session:
        # Attributed as the save route's session is, so the ledger entry names the run's reach.
        for one in attributed_to(actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id):
            await session.execute(one)
        await save(session, values, updated_by=h.actor)
        await session.commit()
    async with h.sessions() as session:
        kept = await load(session)
    use = switched_on(lambda setting: value_of(setting, saved=kept))
    if use is None or use.base_id != base_id or use.host != HOST:
        raise CheckFailedError(
            "the Base Connect Lark saved was not switched on for the next question"
        )
    if LARK_BASE_USE not in kept.get("INSTALL_LARK_USES", ""):
        raise CheckFailedError("Connect Lark's save did not switch knowledge from Base on")

    # The worker's index, under a key leased and a token exchanged for the run.
    with opened(
        use, keys=keys, caller=base, resolver=_Resolver(), issuer=issuer, now=h.now
    ) as reading:
        if isinstance(reading, str):
            raise CheckFailedError("the worker could not open the made-up Base with its key")
        run = await index_base(use, reading, h.sessions, now=h.now, budget=fair_share_budget())
    if (run.tables, run.kept) != (1, 1):
        raise CheckFailedError("the worker did not index the switched-on Base's table and record")

    schema = BaseSchema(
        keys=keys, caller=base, resolver=_Resolver(), issuer=issuer, clock=lambda: h.now
    )
    lane = await base_lane_for(use, schema, h.sessions)
    tables = await schema.tables(use)
    if not lane.rules or not tables:
        raise CheckFailedError("a switched-on Base contributed no question to Ask")

    async def connected() -> Any:
        nothing = ConnectedSources(
            {}, keys=keys, caller=base, resolver=_Resolver(), clock=lambda: h.now
        )
        return with_base(
            nothing,
            use,
            tables,
            keys=keys,
            caller=base,
            resolver=_Resolver(),
            issuer=issuer,
            clock=lambda: h.now,
        )

    live = SourceRecords(connected=connected, clock=lambda: h.now)
    registry = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    entity = f"lark_{table_id.lower()}"
    reads = (f"read:{entity}", f"read:{entity}.*")
    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=tuple((one, Scope.unrestricted()) for one in reads))
    manifest = use.manifest(tables[0].table)
    served = await _served(
        h,
        RegisteredConnector(
            manifest=manifest, digest=manifest_digest(manifest), state=ConnectorState.ENABLED
        ),
    )
    bound, unbound = await _two_agents(
        h, LARK_BASE, reads, Scope.unrestricted(), served=served, tools=registry
    )
    own, through, beside = await _run_reaches(h, reader, bound, unbound)
    person = await StoredPrincipals(h.sessions).live_principal(reader)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")

    async def ask(reach: EntitlementSet, slot: str) -> Answered:
        return await answer_lane(
            _asked("contract_value", slot),
            origin=Origin(trace_id=h.trace_id, principal=person, channel=Channel.CONSOLE),
            recorders=(),
            rules=lane.rules,
            readers=dict(lane.readers),
            entitlement=reach,
            policies={**field_policies(registry), **lane.policies},
            reachable_sources=covered_at(registry, reach, h.now),
            sink=CountingTraceSink(),
            now=h.now,
            clock=lambda: h.now,
            live=live,
            source_policies={**source_field_policies(registry), **lane.source_policies},
        )

    told = await ask(own, name)
    if told.composed is None or canary not in _prose(told):
        raise CheckFailedError("a permitted person's question was not answered from the source")
    used = await ask(through, name)
    if used.composed is None or canary not in _prose(used):
        raise CheckFailedError("an agent bound to a connected source could not use it")
    refused, nothing = await ask(beside, name), await ask(beside, h.word())
    if canary in _prose(refused) or _prose(refused) != _prose(nothing):
        raise CheckFailedError("an agent not bound to a source was answered from it")


# -------------------------------------------------------------------- M11.9.5: Slack
@check(
    leaves=("M11.9.5",),
    sentence=(
        "A Slack workspace made up for the check is connected from its form and indexed by the "
        "worker, nothing else set: a permitted person in a channel is handed its message read "
        "from Slack on the next question, an agent naming Slack installs ready and is handed it "
        "too, and an agent not bound to it is handed what a subject Slack never mentions hands it."
    ),
)
async def slack_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.connectors import slack_messages as slack
    from brain.connectors.minimal_index import fresh_canary
    from brain.identity.staff_roster import digest_of
    from brain.identity.work_email import binding
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_slack import _RecordedSlack, _slack_id
    from brain.ops.connector_store import StoredConnections
    from brain.ops.slack_messages_live import READ_MESSAGE, SlackPassages
    from brain.tools.startup import build_registry

    await h.found_departments()
    word, channel, member = h.word(), _slack_id("C"), _slack_id("U")
    address, said = f"{h.word().lower()}@acceptance.invalid", fresh_canary("ACCEPTANCE")
    workspace = _RecordedSlack(
        channels={channel: ("general", False)},
        members={member: (address, (channel,))},
        histories={channel: (("1600000000.000100", f"{said} {word}"),)},
    )
    await _from_the_console(
        h,
        slack.CONNECTOR_NAME,
        {slack.WORKSPACE_SETTING: _slack_id("T"), slack.DEPARTMENT_SETTING: A},
        workspace,
    )

    # The person's work address, bound by the People page's own statement: what matches them to
    # their Slack account, and a step taken on the console rather than at the server.
    reads = (READ_MESSAGE.value,)
    reader = h.principal(A, "reader")
    await h.person(reader, department=A, grants=tuple((one, Scope.department(A)) for one in reads))
    await h.execute(*h.attributed(), binding(reader, digest_of(address)))
    stored = StoredConnections(h.sessions)

    # The connection read from the store on each question, as `slack_passages_for` reads it, so
    # what is handed over came from what the Connectors screen wrote and from nothing held.
    async def connected() -> Connection | None:
        return next(
            (one for one in await stored.connected() if one.connector == slack.CONNECTOR_NAME),
            None,
        )

    passages = SlackPassages(
        connected,
        sessions=h.sessions,
        keys=_Keys(),
        caller=workspace,
        resolver=_Resolver(),
        clock=lambda: h.now,
    )

    async def handed(reach: EntitlementSet, subject: str) -> tuple[str, ...]:
        found = await passages.passages(
            f"What was said about {subject}?", entitlement=reach, now=h.now
        )
        return tuple(one.document for one in found.records)

    tools = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    bound, unbound = await _two_agents(
        h, slack.CONNECTOR_NAME, reads, Scope.department(A), served=await _served(h), tools=tools
    )
    own, through, beside = await _run_reaches(h, reader, bound, unbound)

    if not any(said in one for one in await handed(own, word)):
        raise CheckFailedError("a permitted person's question was not answered from the source")
    if not any(said in one for one in await handed(through, word)):
        raise CheckFailedError("an agent bound to a connected source could not use it")
    refused, nothing = await handed(beside, word), await handed(beside, h.word())
    if any(said in one for one in refused) or refused != nothing:
        raise CheckFailedError("an agent not bound to a source was answered from it")


# ---------------------------------------------------------------- M11.9.6: Freshdesk
@check(
    leaves=("M11.9.6",),
    sentence=(
        "A Freshdesk helpdesk made up for the check is connected from its form and read by the "
        "worker, nothing else set: a permitted person's question about a ticket is answered with "
        "its body read from Freshdesk, an agent naming Freshdesk installs ready and answers it "
        "too, and an agent not bound to it is told what a missing ticket tells it."
    ),
)
async def freshdesk_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.connectors import freshdesk
    from brain.connectors.minimal_index import fresh_canary
    from brain.ops.acceptance_checks_sources import OPEN, _Helpdesk

    await h.found_departments()
    subject, body = h.word(), fresh_canary("ACCEPTANCE")
    ticket = {
        "id": 900_000 + uuid.uuid4().int % 99_999,
        "subject": subject,
        "status": OPEN,
        "priority": 1,
        "company_id": 1,
        "requester_id": 1,
        "group_id": 1,
        "created_at": "2019-03-01T10:00:00Z",
        "updated_at": "2019-03-02T10:00:00Z",
        "due_by": "2019-03-08T10:00:00Z",
    }
    source = await _from_the_console(
        h,
        freshdesk.FRESHDESK,
        {freshdesk.DOMAIN_SETTING: HELPDESK, freshdesk.DEPARTMENT_SETTING: A},
        _Helpdesk(ticket, body=body),
    )
    await _ready_on_ask(
        h,
        source,
        _Asking(
            present=_asked(freshdesk.LIVE_BODY_FIELD, subject),
            absent=_asked(freshdesk.LIVE_BODY_FIELD, h.word()),
            told=body,
        ),
        reads=(
            f"read:{freshdesk.TICKET}",
            f"read:{freshdesk.TICKET}.subject",
            f"read:{freshdesk.TICKET}.{freshdesk.LIVE_BODY_FIELD}",
        ),
        scope=Scope.department(A),
    )


# --------------------------------------------------------------------- M11.9.7: Xero
@check(
    leaves=("M11.9.7",),
    sentence=(
        "A Xero organisation made up for the check is connected from its form and read by the "
        "worker, nothing else set: a permitted person's question about an invoice is answered "
        "with its amount read from Xero, an agent naming Xero installs ready and answers it too, "
        "and an agent not bound to it is told what a missing invoice tells it."
    ),
)
async def xero_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.connectors import xero
    from brain.connectors.minimal_index import fresh_canary

    await h.found_departments()
    amount, number = fresh_canary("ACCEPTANCE"), h.word()
    invoices = {
        "Invoices": [
            {
                "InvoiceID": str(uuid.uuid4()),
                "InvoiceNumber": number,
                "Contact": {"ContactID": str(uuid.uuid4())},
                "AmountDue": amount,
                "DueDate": DUE_DATE,
                "Status": "AUTHORISED",
            }
        ]
    }
    ledger = _Recorded(
        invoices=json.dumps(invoices).encode("utf-8"),
        contacts=json.dumps({"Contacts": []}).encode("utf-8"),
    )
    source = await _from_the_console(
        h, xero.CONNECTOR_NAME, {"tenant_id": str(uuid.uuid4())}, ledger
    )
    entity = xero.ENTITY_INVOICE
    await _ready_on_ask(
        h,
        source,
        _Asking(
            present=_asked("amount_due", number),
            absent=_asked("amount_due", h.word()),
            told=amount,
        ),
        reads=(f"read:{entity}", f"read:{entity}.invoice_number", f"read:{entity}.amount_due"),
        scope=Scope.unrestricted(),
    )


# ------------------------------------------------------------------ M11.9.8: the CRM
@check(
    leaves=("M11.9.8",),
    sentence=(
        "A HubSpot account, the CRM, made up for the check is connected from its form and read by "
        "the worker, nothing else set: a permitted person's question about a company is answered "
        "from HubSpot, an agent naming HubSpot installs ready and answers it too, and an agent "
        "not bound to it is told what a missing company tells it."
    ),
)
async def the_crm_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.connectors import hubspot
    from brain.ops.acceptance_checks_hubspot import _RecordedAccount

    await h.found_departments()
    company = h.word()
    account = _RecordedAccount(
        company={
            "id": str(10**6 + secrets.randbelow(9 * 10**6)),
            "properties": {
                "name": company,
                "lifecyclestage": "customer",
                "hs_lastmodifieddate": "2019-03-02T10:00:00.000Z",
            },
        },
        deal={
            "id": str(10**6 + secrets.randbelow(9 * 10**6)),
            "properties": {"dealname": h.word(), "amount": "1", "dealstage": "contractsent"},
        },
    )
    portal = str(10**8 + secrets.randbelow(9 * 10**8))
    source = await _from_the_console(h, hubspot.CONNECTOR_NAME, {"portal_id": portal}, account)
    entity = hubspot.ENTITY_CLIENT
    await _ready_on_ask(
        h,
        source,
        _Asking(
            present=_asked("lifecycle_stage", company),
            absent=_asked("lifecycle_stage", h.word()),
            told="customer",
        ),
        reads=(f"read:{entity}", f"read:{entity}.name", f"read:{entity}.lifecycle_stage"),
        scope=Scope.unrestricted(),
    )


# ------------------------------------------------------- M11.9.10: domains and hosting
@check(
    leaves=("M11.9.10",),
    sentence=(
        "A domains connection made up for the check is connected from its form and read from "
        "recorded registries by the worker, nothing else set: a permitted person's question about "
        "a domain's expiry is answered from its registry, an agent naming the connector installs "
        "ready and answers it too, and one not bound to it is told what an unlisted domain tells."
    ),
)
async def domains_are_ready_for_a_person_and_their_agent_once_connected(h: Harness) -> None:
    from brain.connectors import domains
    from brain.ops.acceptance_checks_domains import EXPIRY, _Registries

    await h.found_departments()
    listed = f"acceptance-{secrets.token_hex(4)}.com"
    unlisted = f"acceptance-{secrets.token_hex(4)}.com"
    source = await _from_the_console(
        h,
        domains.CONNECTOR_NAME,
        {"domains": listed, "department": A},
        _Registries(registrar=h.word()),
    )
    await _ready_on_ask(
        h,
        source,
        _Asking(
            present=_asked("expiry", listed),
            absent=_asked("expiry", unlisted),
            told=EXPIRY[:10],
        ),
        reads=("read:domain", "read:domain.name", "read:domain.expiry"),
        scope=Scope.department(A),
    )


# ---------------------------------------------------------------- M11.9.11: Cloudflare
@check(
    leaves=("M11.9.11",),
    sentence=(
        "A Cloudflare account made up for the check is connected from its form and its DNS records "
        "indexed by the worker, nothing else set: a permitted person's question about a record's "
        "content is answered from Cloudflare, an agent naming Cloudflare installs ready and "
        "answers it too, and one not bound to it is told what a missing record tells it."
    ),
)
async def cloudflare_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.connectors import cloudflare
    from brain.connectors.minimal_index import fresh_canary
    from brain.ops.acceptance_checks_cloudflare import READS, _Account, _Leases

    await h.found_departments()
    content = fresh_canary("ACCEPTANCE")
    account = _Account(
        account=secrets.token_hex(16),
        zone=secrets.token_hex(16),
        record=secrets.token_hex(16),
        name=f"{h.word().lower()}.example.com",
        content=content,
    )
    source = await _from_the_console(
        h,
        cloudflare.CLOUDFLARE,
        {cloudflare.ACCOUNT_SETTING: account.account, cloudflare.DEPARTMENT_SETTING: A},
        account,
        keys=_Leases(allows=False),
    )
    await _ready_on_ask(
        h,
        source,
        _Asking(
            present=_asked("content", account.name),
            absent=_asked("content", f"{h.word().lower()}.example.com"),
            told=content,
        ),
        reads=(*READS, f"read:{cloudflare.DNS_RECORD}.content"),
        scope=Scope.department(A),
    )


# ---------------------------------------------------------- M11.9.13: Google Analytics
@check(
    leaves=("M11.9.13",),
    sentence=(
        "A Google Analytics property made up for the check is connected from its form with a key "
        "file and read by the worker, nothing else set: a permitted person's question about its "
        "sessions is answered from a report read when asked, an agent naming Analytics installs "
        "ready and answers it too, and one not bound to it is told what absence tells."
    ),
)
async def analytics_is_ready_for_a_person_and_its_agent_once_connected(h: Harness) -> None:
    from brain.connectors import google_analytics
    from brain.ops.acceptance_checks_google import ASKED_FIGURE, _Google, _KeyFiles, a_key_file

    await h.found_departments()
    property_id, name = str(10**8 + secrets.randbelow(9 * 10**8)), h.word()
    figure = str(10**14 + secrets.randbelow(9 * 10**14))
    google = _Google(property_id=property_id, display_name=name, figures={ASKED_FIGURE: figure})
    source = await _from_the_console(
        h,
        google_analytics.GOOGLE_ANALYTICS,
        {
            google_analytics.PROPERTY_SETTING: property_id,
            google_analytics.DEPARTMENT_SETTING: A,
        },
        google,
        keys=_KeyFiles(a_key_file()),
        poster=google,
    )
    entity = google_analytics.ENTITY_PROPERTY
    await _ready_on_ask(
        h,
        source,
        _Asking(
            present=_asked(ASKED_FIGURE, name),
            absent=_asked(ASKED_FIGURE, h.word()),
            told=figure,
        ),
        reads=(
            f"read:{entity}",
            f"read:{entity}.{google_analytics.LABEL_FIELD}",
            f"read:{entity}.{ASKED_FIGURE}",
        ),
        scope=Scope.department(A),
    )


# ------------------------------------------------------------ M11.9.14: Search Console
@check(
    leaves=("M11.9.14",),
    sentence=(
        "A Search Console site made up for the check is connected from its form with a key file "
        "and read by the worker, nothing else set: a permitted person's question about its clicks "
        "is answered from Search Console when asked, an agent naming it installs ready and "
        "answers it too, and an agent not bound to it is told what a missing site tells it."
    ),
)
async def search_console_is_ready_for_a_person_and_an_agent_once_connected(
    h: Harness,
) -> None:
    from brain.connectors import search_console
    from brain.ops.acceptance_checks_google import _KeyFiles, a_key_file
    from brain.ops.acceptance_checks_search_console import ASKED_SEARCH_FIGURE, _SearchConsole

    await h.found_departments()
    name = f"{h.word().lower()}.example"
    site = f"{search_console.DOMAIN_PROPERTY_PREFIX}{name}"
    clicks = 10**14 + secrets.randbelow(9 * 10**14)
    google = _SearchConsole(
        site=site,
        other_site=f"{search_console.DOMAIN_PROPERTY_PREFIX}{h.word().lower()}.example",
        clicks_on=(h.now.date() - timedelta(days=2)).isoformat(),
        clicks=clicks,
    )
    source = await _from_the_console(
        h,
        search_console.SEARCH_CONSOLE,
        {search_console.SITE_SETTING: site, search_console.DEPARTMENT_SETTING: A},
        google,
        keys=_KeyFiles(a_key_file()),
        poster=google,
    )
    entity = search_console.ENTITY_SITE
    await _ready_on_ask(
        h,
        source,
        _Asking(
            present=_asked(ASKED_SEARCH_FIGURE, name),
            absent=_asked(ASKED_SEARCH_FIGURE, f"{h.word().lower()}.example"),
            told=str(clicks),
        ),
        reads=(
            f"read:{entity}",
            f"read:{entity}.{search_console.LABEL_FIELD}",
            f"read:{entity}.{ASKED_SEARCH_FIGURE}",
        ),
        scope=Scope.department(A),
    )
