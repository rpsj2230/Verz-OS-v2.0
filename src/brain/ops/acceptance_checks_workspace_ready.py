"""The install acceptance check that Google Workspace, connected from the console, is ready to use.

M11.9.12 asks of Google Workspace what M11.9.3 to M11.9.14 ask of every other source: once it is
connected from the console, with no server step, **a permitted person's question is answered from
it and an agent bound to it can use it**. The neighbouring check (M11.7.6,
`brain.ops.acceptance_checks_google_workspace`) proves the reading: a person's own consent, their
own token, nobody else's mail. It never asked through an agent, never asked whether the Connectors
screen offers the source at all, and never showed a source one step short of ready: so a
Workspace could pass every reading rule and still be invisible on the console, or need an agent
configured at the server before anybody could use it.

**Workspace is the one source whose readiness has two halves, and the walk takes both.** An
administrator connects it once on the Connectors screen (the form, the client secret kept in the
vault), and then each person connects their own account from My workspace (their consent). Neither
is a server step, and neither alone makes a question answerable, so the walk does both through the
routes' own functions in the routes' order and asks only afterwards.

**The agent bound to Workspace is the person's own personal agent**, since the owner's direction on
needs item 173 (2026-10-12): a person's own mail belongs to an agent only they can ask. Until
2026-10-14 this check bound a department's agent and watched it read one person's mailbox, which
passed because the read named an entity no connector provided and so was in every ceiling that
listed it (`brain.connectors.google_workspace.READER_ENTITY`). A department's agent naming Workspace
and holding the read is asked the same question and is handed nothing, which is the half of the
property that was missing.

**Bound is shown against unbound, because an agent that answers is only half of it.** A second
agent of the same department, naming no source and holding no read of Workspace, is asked the same
question by the same person and is handed what a person with nothing connected is handed. Without
it, an agent that answered at its caller's own reach and ignored its ceiling would pass. See
`brain.ops.acceptance_checks_connectable.AN_AGENT_NOT_BOUND_TO_A_SOURCE_IS_TOLD_WHAT_ABSENCE_TELLS`.

**No socket is opened and no real key is held.** Google is `_Google` of the reading check: a
recorded consent page, token endpoint and API holding one made-up account per person, and the vault
is the oauth check's role vault. Recorded answers are never a call. See
`brain.ops.acceptance_checks_connectors.A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

**What it does not prove, said once.** The question is asked of the passage reader the answer lane
is handed (`brain.ops.google_workspace_live.WorkspacePassages`), at the person's reach and at each
agent's run reach, rather than of a model, because a passage is what the model step is given. An
install with Workspace connected already is not run, since the check would be connecting over a
real connection.

Task ids: M11.9.12
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.ops.connector_store import Connection

#: Where this module's check stands on the Install page, within the range assigned to it. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1200

A = RESERVED_DEPARTMENTS[0]

# ------------------------------------------------------------------ written-down reasons
#: Said where the install has Workspace connected already. Held here and not imported, because a
#: reason is held to a literal in the file that raises it (`tests/unit/test_acceptance.py`).
WORKSPACE_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Google Workspace connected already, so the check does not stand a second "
    "connection up beside the real one"
)

#: What "ready" is held to for a source whose reading is each person's own.
READY_FOR_WORKSPACE_MEANS_BOTH_HALVES_AND_NO_SERVER_STEP: Final = (
    "Google Workspace is ready when an administrator's connection on the Connectors screen and a "
    "person's own consent from My workspace are the only steps taken: the very next question is "
    "answered from that person's account and the very next personal agent of theirs naming "
    "Workspace is handed the same, with nothing set at the server and nothing restarted."
)


@check(
    leaves=("M11.9.12",),
    sentence=(
        "A Google Workspace made up for the check is connected from its form and consented to by a "
        "person from My workspace, nothing else set: their question and their own personal agent "
        "are handed their own mail and calendar, and an agent not bound to it, or a department's "
        "agent naming it, is handed what a person with nothing connected is handed."
    ),
)
async def workspace_is_ready_for_a_person_and_an_agent_once_connected(
    h: Harness,
) -> None:
    from brain.agents.model import AgentAudience
    from brain.connector_routes import (
        ConsentExchange,
        finish_consent,
        may_consent_for_themselves,
        start_consent,
    )
    from brain.connectors import google_workspace as gws
    from brain.connectors.declaration import shipped
    from brain.connectors.manifest import manifest_digest
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_checks_connectable import _run_reaches, _served
    from brain.ops.acceptance_checks_connector_framework import _credential
    from brain.ops.acceptance_checks_connectors import _Resolver, _search
    from brain.ops.acceptance_checks_google_workspace import (
        CONSOLE_RETURN,
        _Google,
    )
    from brain.ops.acceptance_checks_oauth import _RoleVault
    from brain.ops.acceptance_checks_skills import _an_agent
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connectable import CONNECTABLE, given, manifest_for
    from brain.ops.connector_admin import connection_problems, people_problems
    from brain.ops.connector_consent import StoredConsentHealth, StoredConsents
    from brain.ops.connector_store import Connection, StoredConnections, live
    from brain.ops.connector_sync_run import WorkerConnectorKeys
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials, connector_key_slot
    from brain.ops.google_workspace_live import WorkspacePassages
    from brain.tools.startup import build_registry

    source = gws.CONNECTOR_NAME
    declared = shipped()[source]
    if (await h.execute(live(source))).scalar_one_or_none() is not None:
        raise CheckNotRunError(WORKSPACE_IS_CONNECTED_HERE_ALREADY)
    kind = CONNECTABLE.get(source)
    if kind is None:
        raise CheckFailedError("Google Workspace is not offered on the Connectors screen")
    await h.found_departments()

    ada, bea = h.principal(A, "ada"), h.principal(A, "bea")
    canary = {one: f"{h.word()} retainer" for one in ("ada-mail", "ada-event", "bea-mail")}
    google = _Google(
        client_secret=secrets.token_urlsafe(32),
        mail={ada: canary["ada-mail"], bea: canary["bea-mail"]},
        events={ada: canary["ada-event"], bea: canary["bea-mail"]},
    )
    vault = _RoleVault()
    credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    example = gws.CONSOLE.example
    assert example is not None  # the connector declares one
    form = given(kind, {**example.fresh((A,)), gws.SERVICES_SETTING: "mail, calendar"})
    people = StoredPrincipals(h.sessions)

    async def is_live(principal_id: str) -> bool:
        return await people.live_principal(principal_id) is not None

    if connection_problems(source, form, _credential(source)) or await people_problems(
        kind, form, is_live=is_live
    ):
        raise CheckFailedError("the Connectors screen refused Workspace connected as its form asks")
    settings = dict(form)
    connection = Connection(
        connector=source,
        settings=settings,
        digest=manifest_digest(manifest_for(source, settings)),
        connected_by=h.actor,
        connected_at=h.now,
    )

    async def keep_secret() -> object:
        kept = await credentials.keep(
            connector_key_slot(source), google.client_secret, actor=h.actor, trace_id=h.trace_id
        )
        return kept.set_at

    await StoredConnections(h.sessions).connect(
        connector=source,
        settings=settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=keep_secret,  # type: ignore[arg-type]
    )

    reads = (gws.READER,)
    scope = Scope.department(A)
    for person in (ada, bea):
        await h.person(person, department=A, grants=tuple((one, scope) for one in reads))
    reaches = {one: await _console(h, one, second_factor=False) for one in (ada, bea)}

    # Ada connects her own account from My workspace, as the route does: the only other step.
    if not may_consent_for_themselves(reaches[ada], declared, connection, h.now):
        raise CheckFailedError("a person holding the reader grant may not connect their account")
    consents = StoredConsents(h.sessions)
    address = await start_consent(
        declared,
        connection,
        consents=consents,
        principal_id=ada,
        return_address=CONSOLE_RETURN,
        now=h.now,
    )
    state, code = google.consent(address, ada)

    async def connected(name: str) -> Connection | None:
        return connection if name == source else None

    done = await finish_consent(
        state=state,
        code=code,
        vendor_refused=False,
        principal_id=ada,
        may_connect=lambda name: False,
        may_consent_personally=lambda one, live_one: may_consent_for_themselves(
            reaches[ada], one, live_one, h.now
        ),
        declarations={source: declared},
        connected=connected,
        consents=consents,
        exchange=ConsentExchange(
            keys=WorkerConnectorKeys(vault),
            poster=google,
            resolver=_Resolver(),
            health=StoredConsentHealth(h.sessions),
        ),
        credentials=credentials,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        now=h.now,
    )
    if not done.kept or not done.personal:
        raise CheckFailedError("a person's own consent to Google Workspace was not kept")

    async def the_connection() -> Connection | None:
        return next(
            (
                one
                for one in await StoredConnections(h.sessions).connected()
                if one.connector == source
            ),
            None,
        )

    passages = WorkspacePassages(
        the_connection,
        keys=WorkerConnectorKeys(vault),
        caller=google,
        poster=google,
        resolver=_Resolver(),
        clock=lambda: h.now,
    )
    question = "What did we agree about the retainer?"

    async def handed(reach: EntitlementSet) -> str:
        found = await passages.passages(question, entitlement=reach, now=h.now)
        return " ".join(one.document for one in found.records)

    tools = build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions))
    served = await _served(h)
    builder = h.principal(A, "builder")
    await h.person(builder, department=A)
    # The agent bound to Workspace is Ada's own personal agent, since 2026-10-14: a person's own
    # account belongs to an agent only they can ask. A department's agent naming it is beside it.
    bound = await _an_agent(
        h,
        ada,
        capabilities=reads,
        named="_bound",
        scope=scope,
        connectors=(source,),
        settled=(served, tools),
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=ada),
    )
    unbound = await _an_agent(h, builder, named="_unbound", scope=scope, settled=(served, tools))
    shared = await _an_agent(
        h,
        builder,
        capabilities=reads,
        named="_team",
        scope=scope,
        connectors=(source,),
        settled=(served, tools),
    )
    own, through, beside, team = await _run_reaches(h, ada, bound, unbound, shared)

    told = await handed(own)
    if canary["ada-mail"] not in told or canary["ada-event"] not in told:
        raise CheckFailedError("a permitted person's question was not answered from Workspace")
    via_agent = await handed(through)
    if canary["ada-mail"] not in via_agent or canary["ada-event"] not in via_agent:
        raise CheckFailedError("an agent bound to a connected Workspace could not use it")
    refused = await handed(beside)
    if canary["ada-mail"] in refused or canary["ada-event"] in refused:
        raise CheckFailedError("an agent not bound to Workspace was answered from it")
    if await handed(team):
        raise CheckFailedError("a department's agent naming Workspace was handed a person's mail")
    if await handed(reaches[bea]):
        raise CheckFailedError("a person who has not connected their account was read something")

    # Nothing read, and no token or secret, is in any table.
    for needle in (*canary.values(), google.client_secret, *google.refresh, *google.access, state):
        if await _search(h, needle):
            raise CheckFailedError("a message, a token or a secret was found in a table")
