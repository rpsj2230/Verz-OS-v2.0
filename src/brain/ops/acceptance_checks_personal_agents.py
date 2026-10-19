"""The install acceptance checks for oversight of personal agents and a person's own Google account.

Two properties of the owner's direction on needs item 173 (2026-10-12), asked of the product's own
route functions as reserved people of acceptance_a.

**Oversight tells an auditor that a personal agent exists and offers it to nobody**
(`brain.agents.oversight`, M39.10.3). The agent is made by its owner through the builder; a reader
holding the audit capability for agents is told of it, by name and owner, and the owner, a colleague
and an administrator holding the install authority are not; the auditor's roster does not list it
and its workspace is refused to them as one never made is; and with the switch off nobody is told.

**A person's own Google account is attached to their own personal agent, and read for them alone**
(`brain.agent_own_workspace_routes`, M39.10.4). A Google Workspace made up for the check, with one
made-up account per person, is connected and the owner consents for theirs, as
`brain.ops.acceptance_checks_workspace_ready` does. The owner's agent reads nothing until the
account is attached, reads the owner's own account when it is, and Google is called with the
owner's access and nobody's else; a colleague's and an administrator's presses are refused as for
an agent never made and write nothing; a department's agent that names Workspace and holds its read
is handed nothing, and a press to attach on it is refused in the one sentence; detaching takes it
off; and each press is one ledger entry naming who, which way and why.

**It claims M39.10.4 and not M39.10.5.** A department's agent that names Workspace and is handed
nothing is the half of M39.10.5 that holds under every answer to needs item 189, and is asserted
here because it is the same read. The rest of that leaf (a shared mailbox an administrator connects,
and a person's own mail inside their private conversation only) is the owner's decision on item 189
and is not built, so this check does not close it.

**What it does not prove, and cannot.** A real person signing in at Google, and Google answering for
a real mailbox. The Google here is recorded answers for made-up people, and **an install that has
Google Workspace connected already is not run**, because the check would be standing a second
connection up beside the real one. The owner's own steps on needs item 173 are the rest, and the
install check `a_persons_own_workspace_is_read_with_their_token_for_them_alone` is run after them.

Task ids: M39.10.3, M39.10.4
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.core.entitlement import EntitlementSet
    from brain.ops.connector_store import Connection

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1560

# What the oversight check says, one sentence for each way the property can fail.
NOT_TOLD_TO_THE_AUDITOR: Final = (
    "a reader holding the audit capability for agents was not told a personal agent exists"
)
TOLD_TO_ANOTHER: Final = "a personal agent was told to somebody who holds no audit capability"
TOLD_TO_ITS_OWNER: Final = "a person was told of their own personal agent under oversight"
OVERSEEN_IS_LISTED: Final = "an agent told for oversight was listed on the auditor's roster"
OVERSEEN_IS_OPENED: Final = "an agent told for oversight was opened by the auditor"
OVERSEEN_IS_TOLD_APART: Final = "an overseen agent was refused differently from one never made"
OVERSIGHT_IGNORES_THE_SWITCH: Final = "oversight was shown with its switch off"
THE_OWNER_LOST_IT: Final = "a person's own personal agent was no longer theirs to open"
AN_ANSWER_TOLD_APART: Final = "readers who may not be told were answered in different shapes"

# What the own-account check says.
NOT_RUN_WITH_A_REAL_WORKSPACE: Final = (
    "this install has Google Workspace connected already, so the check does not stand a second "
    "connection up beside the real one, and a real person's own sign-in at Google is the one thing "
    "it cannot do for them"
)
WORKSPACE_NOT_CONNECTED: Final = "a made-up Google Workspace was not connected from its form"
CONSENT_NOT_KEPT: Final = "a person's own consent to Google Workspace was not kept"
AGENT_NOT_MADE: Final = "a person's own personal agent was not made"
READ_BEFORE_ATTACHING: Final = "a personal agent read an account that was never attached to it"
ATTACH_REFUSED: Final = "the owner was refused attaching their own account to their own agent"
NOT_READ_ONCE_ATTACHED: Final = "an agent with its owner's account attached read nothing of it"
READ_SOMEBODY_ELSES: Final = "Google was asked for an account that was not the asker's own"
ANOTHER_ATTACHED_IT: Final = "somebody other than the owner attached an account to a personal agent"
ANOTHER_TOLD_APART: Final = "a personal agent was refused differently from one never made"
TEAM_AGENT_READ: Final = "a department's agent naming Workspace was handed a person's own mail"
TEAM_AGENT_ATTACHED: Final = "a department's agent was given a person's own account"
TEAM_REFUSAL_NOT_SAID: Final = "a refused team agent was not refused in its own sentence"
STILL_READ_AFTER_DETACHING: Final = "an agent still read an account its owner took off it"
SWITCH_IGNORED: Final = "an account was attached to an agent with the switch off"
NOT_ON_THE_LEDGER: Final = "a press did not reach the ledger naming who, which way and why"


async def _member(h: Harness, role: str, *grants: tuple[str, Scope]) -> str:
    """A reserved person of acceptance_a holding exactly these grants."""
    made = h.principal(A, role)
    await h.person(made, department=A, grants=grants)
    return made


# ----------------------------------------------------------------- M39.10.3 oversight
@check(
    leaves=("M39.10.3",),
    sentence=(
        "A person's own personal agent is told, by name and owner, to a reader who holds the audit "
        "capability for agents, and to nobody else; it is not on that reader's roster and its "
        "workspace is refused to them as one never made is; every other reader is answered in the "
        "same shape; and with the switch off the auditor is told of none."
    ),
)
async def an_auditor_is_told_of_a_personal_agent_and_may_not_use_it(
    h: Harness,
) -> None:
    from brain.agent_oversight_routes import agent_oversight
    from brain.agent_routes import agent_workspace, agents
    from brain.audit.view import CAPABILITY_BY_KIND
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_agent_kinds import _made
    from brain.ops.acceptance_checks_agents import _refusal
    from brain.ops.acceptance_checks_builder import _builder
    from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
    from brain.ops.acceptance_switch import switched
    from brain.ops.features import PERSONAL_AGENTS
    from brain.ops.features_declared.personal_agent_oversight import PERSONAL_AGENT_OVERSIGHT

    app = _gallery(h, secrets.token_hex(32))
    owner = await _member(h, "overseen_owner")
    # A reader who holds the audit capability for agents over somebody else's people only: told of
    # their agents and of nobody's beside them.
    over_others = Scope(clauses=(Clause(field="actor_id", op=Op.IN, value=("u_nobody_here",)),))
    colleague = await _member(
        h, "overseen_colleague", (CAPABILITY_BY_KIND["agent"].value, over_others)
    )
    auditor = await _member(
        h, "overseen_auditor", (CAPABILITY_BY_KIND["agent"].value, Scope.unrestricted())
    )
    administrator = await _builder(h, "overseen_administrator")
    await switched(h, PERSONAL_AGENTS, on=True)
    await switched(h, PERSONAL_AGENT_OVERSIGHT, on=True)

    status, _, mine = await _made(h, app, owner, "personal")
    if status != 201:
        raise CheckFailedError(AGENT_NOT_MADE)

    async def told(reader: str) -> tuple[set[str], list[str], bool]:
        page = await agent_oversight(_request(app), await _asking(h, reader))
        return {one.agent_id for one in page.items}, sorted(page.model_dump()), page.truncated

    seen, shape, _more = await told(auditor)
    if mine not in seen:
        raise CheckFailedError(NOT_TOLD_TO_THE_AUDITOR)
    shapes = []
    for other in (owner, colleague, administrator):
        found, said, _ = await told(other)
        if mine in found and other == owner:
            raise CheckFailedError(TOLD_TO_ITS_OWNER)
        if mine in found:
            raise CheckFailedError(TOLD_TO_ANOTHER)
        shapes.append(said)
    if any(one != shape for one in shapes):
        raise CheckFailedError(AN_ANSWER_TOLD_APART)

    # Told, and offered nothing: not on the auditor's roster, and its workspace is the 404.
    async def listed(reader: str) -> set[str]:
        page = await agents(
            _request(app), await _asking(h, reader), ListAsked(search="Acceptance check", limit=50)
        )
        return {one.agent_id for one in page.items}

    if mine in await listed(auditor):
        raise CheckFailedError(OVERSEEN_IS_LISTED)
    if mine not in await listed(owner):
        raise CheckFailedError(THE_OWNER_LOST_IT)

    async def opened(reader: str, agent_id: str) -> tuple[type[BaseException], str, str] | None:
        return await _refusal(agent_workspace(_request(app), agent_id, await _asking(h, reader)))

    refused = await opened(auditor, mine)
    if refused is None:
        raise CheckFailedError(OVERSEEN_IS_OPENED)
    if refused != await opened(auditor, f"acceptance_{h.run}_never_made"):
        raise CheckFailedError(OVERSEEN_IS_TOLD_APART)
    if await opened(owner, mine) is not None:
        raise CheckFailedError(THE_OWNER_LOST_IT)

    await switched(h, PERSONAL_AGENT_OVERSIGHT, on=False)
    if mine in (await told(auditor))[0]:
        raise CheckFailedError(OVERSIGHT_IGNORES_THE_SWITCH)


# ------------------------------------------------------- M39.10.4 a person's own account
async def _a_made_up_workspace(h: Harness, ada: str, bea: str, canary: dict[str, str]) -> Any:
    """Google Workspace connected from its form with the client secret kept, and `ada` having
    consented for her own account, as `brain.ops.acceptance_checks_workspace_ready` does. Returns
    the recorded Google, the vault, and the connection."""
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
    from brain.ops.acceptance_checks_connector_framework import _credential
    from brain.ops.acceptance_checks_connectors import _Resolver
    from brain.ops.acceptance_checks_google_workspace import CONSOLE_RETURN, _Google
    from brain.ops.acceptance_checks_oauth import _RoleVault
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connectable import CONNECTABLE, given, manifest_for
    from brain.ops.connector_admin import connection_problems, people_problems
    from brain.ops.connector_consent import StoredConsentHealth, StoredConsents
    from brain.ops.connector_store import Connection, StoredConnections
    from brain.ops.connector_sync_run import WorkerConnectorKeys
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials, connector_key_slot

    source = gws.CONNECTOR_NAME
    declared = shipped()[source]
    kind = CONNECTABLE.get(source)
    example = gws.CONSOLE.example
    if kind is None or example is None:
        raise CheckFailedError(WORKSPACE_NOT_CONNECTED)
    google = _Google(
        client_secret=secrets.token_urlsafe(32),
        mail={ada: canary["ada-mail"], bea: canary["bea-mail"]},
        events={ada: canary["ada-event"], bea: canary["bea-mail"]},
    )
    vault = _RoleVault()
    credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    form = given(kind, {**example.fresh((A,)), gws.SERVICES_SETTING: "mail, calendar"})
    people = StoredPrincipals(h.sessions)

    async def is_live(principal_id: str) -> bool:
        return await people.live_principal(principal_id) is not None

    if connection_problems(source, form, _credential(source)) or await people_problems(
        kind, form, is_live=is_live
    ):
        raise CheckFailedError(WORKSPACE_NOT_CONNECTED)
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
    reach = await _console(h, ada, second_factor=False)
    if not may_consent_for_themselves(reach, declared, connection, h.now):
        raise CheckFailedError(CONSENT_NOT_KEPT)
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
            reach, one, live_one, h.now
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
        raise CheckFailedError(CONSENT_NOT_KEPT)
    return google, vault


@check(
    leaves=("M39.10.4",),
    sentence=(
        "A made-up Google Workspace and a person's own consent to it: their personal agent reads "
        "nothing until they attach the account, then reads their own account with their own "
        "access and nobody's; a colleague and an administrator cannot attach it; a department's "
        "agent naming it is handed nothing and cannot be given it; detaching ends the read."
    ),
)
async def a_persons_own_google_account_is_on_their_agent_for_them_alone(
    h: Harness,
) -> None:
    from sqlalchemy import text, update

    from brain.agent_own_workspace_routes import OwnWorkspaceAsked, attach_own_workspace
    from brain.agents.own_workspace import (
        A_TEAM_AGENT_CARRIES_NO_ONES_OWN_ACCOUNT,
        ATTACHED_REASON,
        DETACHED_REASON,
    )
    from brain.connectors import google_workspace as gws
    from brain.ops.acceptance_checks_agent_kinds import _made
    from brain.ops.acceptance_checks_agents import _refusal
    from brain.ops.acceptance_checks_builder import _body, _builder
    from brain.ops.acceptance_checks_connectable import _run_reaches
    from brain.ops.acceptance_checks_connectors import _Resolver
    from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
    from brain.ops.acceptance_switch import switched
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync_run import WorkerConnectorKeys
    from brain.ops.features import PERSONAL_AGENTS
    from brain.ops.features_declared.personal_agent_own_workspace import (
        PERSONAL_AGENT_OWN_WORKSPACE,
    )
    from brain.ops.google_workspace_live import WorkspacePassages
    from brain.tables.agent import AgentRow

    source = gws.CONNECTOR_NAME
    if (await h.execute(live(source))).scalar_one_or_none() is not None:
        raise CheckNotRunError(NOT_RUN_WITH_A_REAL_WORKSPACE)
    await h.found_departments()
    reads = ((gws.READER, Scope.department(A)),)
    ada = await _member(h, "own_ada", *reads)
    bea = await _member(h, "own_bea", *reads)
    administrator = await _builder(h, "own_administrator")
    canary = {one: f"{h.word()} retainer" for one in ("ada-mail", "ada-event", "bea-mail")}
    google, vault = await _a_made_up_workspace(h, ada, bea, canary)
    await switched(h, PERSONAL_AGENTS, on=True)
    await switched(h, PERSONAL_AGENT_OWN_WORKSPACE, on=True)
    app = _gallery(h, secrets.token_hex(32))

    status, _, mine = await _made(h, app, ada, "personal")
    if status != 201:
        raise CheckFailedError(AGENT_NOT_MADE)
    status, _, shared = await _made(h, app, administrator, "team")
    if status != 201:
        raise CheckFailedError(AGENT_NOT_MADE)
    # Both are switched on, as an administrator's enable would, so a question can be asked of them,
    # and the department's names Workspace and holds its read as an administrator's mistake or a
    # hand edit would write it, since the product's own routes refuse to.
    await h.execute(
        *h.attributed(ada), update(AgentRow).where(AgentRow.id == mine).values(disabled_at=None)
    )
    await h.execute(
        *h.attributed(administrator),
        update(AgentRow)
        .where(AgentRow.id == shared)
        .values(disabled_at=None, connectors=[source], capabilities=[gws.READER]),
    )

    async def the_connection() -> Any:
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

    async def handed(reach: EntitlementSet) -> str:
        found = await passages.passages(
            "What did we agree about the retainer?", entitlement=reach, now=h.now
        )
        return " ".join(one.document for one in found.records)

    async def runs(person: str, *agents: str) -> tuple[EntitlementSet, ...]:
        return (await _run_reaches(h, person, *agents))[1:]

    async def press(person: str, agent_id: str, *, attached: bool) -> tuple[int, dict[str, Any]]:
        answered = await attach_own_workspace(
            _request(app), agent_id, OwnWorkspaceAsked(attached=attached), await _asking(h, person)
        )
        return int(answered.status_code), _body(answered)

    # 1. Nothing attached: the agent reads nothing, though its owner holds the read and consented.
    (before,) = await runs(ada, mine)
    if canary["ada-mail"] in await handed(before):
        raise CheckFailedError(READ_BEFORE_ATTACHING)

    # 2. Nobody but the owner attaches it, and each is told what an agent never made is told.
    never = f"acceptance_{h.run}_never_made"
    for other in (bea, administrator):
        refused = await _refusal(press(other, mine, attached=True))
        unknown = await _refusal(press(other, never, attached=True))
        if refused is None:
            raise CheckFailedError(ANOTHER_ATTACHED_IT)
        if refused != unknown:
            raise CheckFailedError(ANOTHER_TOLD_APART)

    # 3. The owner attaches it, and the agent reads their own account with their own access.
    done, said = await press(ada, mine, attached=True)
    if done != 200 or said.get("attached") is not True:
        raise CheckFailedError(ATTACH_REFUSED)
    (after,) = await runs(ada, mine)
    told = await handed(after)
    if canary["ada-mail"] not in told or canary["ada-event"] not in told:
        raise CheckFailedError(NOT_READ_ONCE_ATTACHED)
    if {account for _, account in google.called} - {ada}:
        raise CheckFailedError(READ_SOMEBODY_ELSES)

    # 4. A department's agent, naming Workspace and holding its read, is handed nothing, and a press
    # to give it an account is refused in the one sentence.
    (team,) = await runs(ada, shared)
    if await handed(team):
        raise CheckFailedError(TEAM_AGENT_READ)
    refused_team, said_team = await press(ada, shared, attached=True)
    if refused_team == 200:
        raise CheckFailedError(TEAM_AGENT_ATTACHED)
    if said_team.get("message") != A_TEAM_AGENT_CARRIES_NO_ONES_OWN_ACCOUNT:
        raise CheckFailedError(TEAM_REFUSAL_NOT_SAID)

    # 5. Detaching ends the read, and a press with the switch off is refused, in that order.
    done, said = await press(ada, mine, attached=False)
    if done != 200:
        raise CheckFailedError(ATTACH_REFUSED)
    (taken,) = await runs(ada, mine)
    if canary["ada-mail"] in await handed(taken):
        raise CheckFailedError(STILL_READ_AFTER_DETACHING)
    await switched(h, PERSONAL_AGENT_OWN_WORKSPACE, on=False)
    off, _ = await press(ada, mine, attached=True)
    if off == 200:
        raise CheckFailedError(SWITCH_IGNORED)

    # 6. Every press on the ledger: who, which way and why. A refused one left no entry.
    rows = (
        await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry WHERE action = 'compose_change'"
                " AND subject = :subject ORDER BY seq"
            ).bindparams(subject=f"agent:{mine}")
        )
    ).all()
    said_on_the_ledger = [
        (
            str(actor),
            dict(details).get("part"),
            dict(details)["direction"],
            dict(details)["reason_code"],
        )
        for actor, details in rows
        if dict(details).get("part") == "connector"
    ]
    if said_on_the_ledger != [
        (ada, "connector", "attached", ATTACHED_REASON),
        (ada, "connector", "detached", DETACHED_REASON),
    ]:
        raise CheckFailedError(NOT_ON_THE_LEDGER)
