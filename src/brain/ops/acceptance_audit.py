"""The install acceptance check for audit and tracing: each act, its chain, its trace, the export.

M24.3.4 asks that a grant, a leash change, a merge, a publish, a sensitive read and a browser
session each be seen in the audit view with a recording where one applies, that the chain verifies
and a removed newest entry is detected, that a run's trace graph and payload hold only masked
content readable under the separate role, and that the compliance export holds no deployment
history. This check performs every act, inside its rolled-back transaction, and reads back what the
ledger, the audit view, the chain verifier, the trace store and the export make of them. It is a
module of its own, found by `brain.ops.acceptance.check_modules`, beside the checks that reach a
model.

**Every act is the product's own write, attributed as a console request attributes it.** A grant is
the row the Govern screen inserts; a publish is the template version an install writes
(`brain.ops.acceptance_checks_skills._an_agent`); a sensitive read is a finished request handed to
`brain.ops.sensitive_read_store.SensitiveReadRecorder`, which is how every read reaches the ledger;
a browser session is a sealed envelope stored by `brain.browsing.envelope_store` and a session
opened and closed on it by `brain.browsing.session_store`, whose table's trigger is the entry.
Two acts have no writer in the product at all: nothing under `src` moves a leash, which the seal on
`guardrails.leash` refuses, and nothing writes a merge, because `brain.resolution.merge` is pure. So
each is the one statement the ledger's trigger watches for (`0104`), run as the application role,
which is what an operator's statement would be and what the trigger was written to catch. Each act
carries its own trace, as each console request does, and the entry is read back by that trace.

**The chain is walked before anything is written, and the check's own entries after.** The whole
ledger is verified from its first entry against its own newest entry as the published head, with
no write in flight, so the walk holds none of the locks an audited write takes. Once the acts are
in, the entries after that head are verified from the head the walk computed, and verified again
with the newest of them left out, which the published head has to catch as missing. Nothing real is
pretended removed: the entry left out is the check's own.

**The sensitive read's run is traced by the recorder the application installs, and read back as
an operator would read it.** `brain.ops.trace_store.TraceRecorder` is handed the finished request
beside the two recorders it already had; the record it disclosed carries a word nothing on the
install holds, and that word has to be absent from every stored step. The application's own role
has to hold no SELECT on the steps and the reader role has to, a read whose sign-in carries every
other realm role and not the payload one has to be refused with no row written (M32.1.2.4, see
`ONLY_ITS_OWN_ROLE_READS_A_TRACE`), and a read with it has to leave its row and return the graph:
the request, and the tool call hanging from it, every payload one of the four shapes `mask` leaves
and every attribute a value `mask` would leave as it is.

**The compliance export is the one the Import and export screen produces**, over the window the
acts wrote, as the check's auditor, who reads the whole ledger and so takes the chain. It has to
carry exactly the ledger's entries of that window, verify, and hold none of the values the install's
deployment history records: a commit, an image, a fingerprint or a link of that chain. **A history
with nothing in it proves nothing about keeping one out**, so an install whose deploys were never
recorded ends as not run with `NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT`, after every other part has
been seen working and a part that does not work has failed it first.

Task ids: M38.5.1, M24.3.4, M32.1.2.4
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check

# Imported first so the suite's own checks are registered ahead of this one.
from brain.ops.acceptance_checks_skills import _an_agent
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.audit.ledger import AuditEntry
    from brain.core.entitlement import EntitlementSet
    from brain.identity.oidc import VerifiedClaims

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 70

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the audit check ends as not run on an install whose deploys were never recorded.
NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT: Final = (
    "every act reached the ledger, the audit view, a verified chain and a masked trace, but this "
    "install has recorded no deployment, so the export cannot be shown to keep one out"
)

# ------------------------------------------------------------------------ the figures
#: The reach digest an act is attributed at. The ledger requires the shape; no reach is claimed.
ACT_REACH: Final = "0" * 32

#: The acts and the subject kind each entry is filed under, in the order the check makes them.
ACTS: Final = (
    ("grant", "grant"),
    ("publish", "artifact"),
    ("leash_change", "agent"),
    ("entity_merge", "entity"),
    ("entity_merge", "entity"),
    ("record_read", "principal"),
    ("browser_session", "session"),
    ("browser_session", "session"),
)

#: The leash rung the check loosens its own agent to. `brain.gate.injection.AutonomyTier`'s top.
LOOSENED: Final = 2

#: Who a verification checkpoint is recorded by. `brain.audit.verify.Checkpoint` needs a name.
CHECKPOINT_BY: Final = "acceptance_check"

#: The acts the check attributes to a trace of their own; the publish is the install's, under the
#: run's trace, because `_an_agent` writes it as the check's set-up.
ACTED_UNDER_THEIR_OWN_TRACE: Final = frozenset(
    {"grant", "leash_change", "entity_merge", "record_read", "browser_session"}
)

#: The origin the check's browsing target declares. `.invalid` is reserved and never resolves.
BROWSED_ORIGIN: Final = "https://acceptance.invalid"

#: Why the check reads a trace, as `brain.ops.tracing.PayloadRead` requires a reason.
READ_REASON: Final = "An install acceptance check reading its own run's trace"

#: Why the trace is read off two sign-ins, one carrying every other realm role and one the
#: payload role besides.
ONLY_ITS_OWN_ROLE_READS_A_TRACE: Final = (
    "A run's stored trace is read under a Keycloak realm role of its own, held for an incident and "
    "taken away after, and under no capability and no other role. The check reads the roles off "
    "a sign-in as the trace route does: one carrying the realm's administrative and default roles "
    "is refused and leaves no row, and the same person with the payload role besides reads it."
)

#: The realm roles a sign-in may carry that must not read a trace: Keycloak's defaults and an
#: administrator's.
OTHER_REALM_ROLES: Final = ("offline_access", "uma_authorization", "admin", "realm-admin")

#: A deployment value shorter than this is not looked for: `unknown` and a short commit could
#: occur in an export by chance, and every value that identifies a deploy is longer.
DEPLOYMENT_VALUE_MIN_CHARS: Final = 12


def kind_of(subject: str) -> str:
    """The subject kind an entry is filed under: the part of its subject before the colon."""
    return subject.partition(":")[0]


def _trace(h: Harness, n: int) -> str:
    return f"{h.trace_id}-act{n}"


async def _as(h: Harness, actor: str, n: int, *statements: Any) -> None:
    """Statements run as a console request by `actor` runs them: attributed, under its trace."""
    from brain.tables.audit import attributed_to

    await h.execute(
        *attributed_to(actor_id=actor, ent_hash=ACT_REACH, trace_id=_trace(h, n)), *statements
    )


async def _entries(h: Harness, actor: str) -> list[tuple[str, str, str]]:
    """Every entry `actor` is the actor of, in order: action, subject, trace."""
    rows = (
        await h.execute(
            text(
                "SELECT action, subject, trace_id FROM obs.audit_entry"
                " WHERE actor_id = :actor ORDER BY seq"
            ).bindparams(actor=actor)
        )
    ).all()
    return [(str(action), str(subject), str(trace)) for action, subject, trace in rows]


async def _a_browser_session(h: Harness, asker: str, agent: str) -> tuple[str, str]:
    """A sealed read-only envelope for the check's agent, a browser opened on it and closed with a
    full recording: the run id, and the digest the session's end names.

    Each through the product's own writer. The asker is granted the browsing capability over the
    check's own target first, because compiling the envelope keeps only the steps its reach holds.
    """
    from brain.browsing.envelope import compile_envelope
    from brain.browsing.envelope_store import put_envelope
    from brain.browsing.planning import Goal, PlanRequest, plan
    from brain.browsing.recording import Direction, record, recording_gaps
    from brain.browsing.session_store import end, start
    from brain.browsing.sessions import BROWSE_SURFACE, surface_scope
    from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
    from brain.browsing.wire import Kind, encode, start_fields
    from brain.gate.injection import AutonomyTier
    from brain.gate.suspension_store import PRINCIPAL_SETTING

    target = Target(
        name=f"acceptance_{h.run}",
        origins=frozenset({BROWSED_ORIGIN}),
        surfaces=(
            Surface(
                name="status",
                origin=BROWSED_ORIGIN,
                path="/",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=BROWSE_SURFACE,
                reads=("status",),
            ),
        ),
    )
    await h.grant(asker, BROWSE_SURFACE.value, surface_scope(target))
    run_id = f"acceptance_{h.run}_browse"
    envelope = compile_envelope(
        plan(
            PlanRequest(
                goal=Goal(text="Read the acceptance check's status page", asked_by=asker),
                target=target.name,
                surfaces=("status",),
            ),
            TargetRegistry(targets=(target,)),
        ),
        target,
        run_id=run_id,
        reach=await h.reach(asker),
        ceiling=AutonomyTier.AUTONOMOUS,
    )
    recording = record(
        run_id,
        h.now,
        (
            (
                Direction.TO_RUNNER,
                encode(Kind.START, **start_fields(envelope, target, approved=True)),
            ),
            (Direction.FROM_RUNNER, encode(Kind.ENDED, reason="finished")),
        ),
        (),
        keep_pictures=frozenset(),
    )
    if recording_gaps(recording):
        raise CheckFailedError("the check's own browser recording was not a whole run")
    async with h.sessions() as session:
        await session.execute(
            text("SELECT set_config(:name, :value, true)").bindparams(
                name=PRINCIPAL_SETTING, value=asker
            )
        )
        await put_envelope(session, envelope, agent_id=agent)
        await start(session, run_id=run_id, trace_id=_trace(h, 6), at=h.now)
        digest = await end(session, run_id=run_id, at=h.now, recording=recording)
        await session.commit()
    if digest is None:
        raise CheckFailedError("a browser session that kept a recording named none")
    return run_id, digest


def _signed_in(h: Harness, subject: str, roles: Sequence[str]) -> VerifiedClaims:
    """The claims a sign-in carrying these realm roles would leave, as the trace route reads them.

    Built rather than verified, because what is proved is which role the route reads off a token,
    and a signature over made-up claims would prove nothing more about that.
    """
    from types import MappingProxyType

    from brain.identity.oidc import VerifiedClaims
    from brain.trace_routes import REALM_ACCESS_CLAIM

    return VerifiedClaims(
        issuer="acceptance",
        subject=subject,
        audience=(),
        issued_at=h.now,
        expires_at=h.now,
        session_id=None,
        key_id="acceptance",
        algorithm="RS256",
        verified_at=h.now,
        claims=MappingProxyType({REALM_ACCESS_CLAIM: {"roles": list(roles)}}),
    )


async def _the_trace_is_masked_and_held_apart(
    h: Harness, reader: str, trace_id: str, canary: str
) -> None:
    """The run's graph is stored, masked, readable only under the reader role and after its row."""
    from brain.ops.trace_store import (
        TRACE_READER_ROLE,
        StoredTraces,
        TraceStoreError,
    )
    from brain.ops.tracing import MASKED_PAYLOADS, PAYLOAD_ROLE, Span, StepKind, mask, mask_value
    from brain.session import APPLICATION_ROLE
    from brain.trace_routes import payload_roles_of

    held = (
        await h.execute(
            text(
                "SELECT has_table_privilege(:app, 'obs.trace_step', 'SELECT'),"
                " has_table_privilege(:reader, 'obs.trace_step', 'SELECT')"
            ).bindparams(app=APPLICATION_ROLE, reader=TRACE_READER_ROLE)
        )
    ).one()
    if held[0] or not held[1]:
        raise CheckFailedError("a stored trace is readable by the application's own role")

    async def reads() -> int:
        return int(
            (
                await h.execute(
                    text(
                        "SELECT count(*) FROM obs.trace_read WHERE trace_id = :t AND actor = :a"
                    ).bindparams(t=trace_id, a=reader)
                )
            ).scalar_one()
        )

    # M32.1.2.4: the roles are read off a sign-in as the trace route reads them, so every other
    # realm role is carried and only the separate one admits. See `ONLY_ITS_OWN_ROLE_READS_A_TRACE`.
    without = payload_roles_of(_signed_in(h, reader, OTHER_REALM_ROLES))
    holding = payload_roles_of(_signed_in(h, reader, (*OTHER_REALM_ROLES, PAYLOAD_ROLE)))
    store = StoredTraces(h.sessions)
    try:
        await store.read(
            realm_roles=without, at=h.now, actor=reader, trace_id=trace_id, reason=READ_REASON
        )
    except TraceStoreError:
        pass
    else:
        raise CheckFailedError("a trace was read without the separate role")
    if await reads():
        raise CheckFailedError("a refused trace read left a row saying it was read")
    steps = await store.read(
        realm_roles=holding, at=h.now, actor=reader, trace_id=trace_id, reason=READ_REASON
    )
    if await reads() != 1:
        raise CheckFailedError("a trace was read without a row saying who read it")
    kinds = [(one.kind, one.parent) for one in steps]
    if not steps or kinds[0] != (StepKind.REQUEST, None) or (StepKind.TOOL_CALL, 0) not in kinds:
        raise CheckFailedError("a run's trace graph was not stored under its trace")
    if steps[0].payload_out == mask_value(""):
        raise CheckFailedError("a run's payload was not stored with its trace")
    for one in steps:
        again = mask(Span(name=one.name, environment=h.settings.env, attributes=one.attributes))
        if (
            one.payload_in not in MASKED_PAYLOADS
            or one.payload_out not in MASKED_PAYLOADS
            or dict(again.attributes) != dict(one.attributes)
            or canary in json.dumps(one.attributes)
        ):
            raise CheckFailedError("a stored trace held content that was not masked")


async def _the_export_holds_no_deployment_history(
    h: Harness, auditor: EntitlementSet, walked: Sequence[AuditEntry]
) -> None:
    """The export of the acts' window carries the ledger's entries and nothing a deploy recorded."""
    from brain.ops.data_transfer import produce_audit_export
    from brain.ops.deployment_history import chain_from_rows, recorded
    from brain.ops.export import ExportReason

    produced = produce_audit_export(
        walked,
        reader=auditor,
        reason=ExportReason.REGULATORY_REQUEST,
        trace_id=_trace(h, 7),
        at=h.now,
        since=walked[0].at,
        until=h.now + timedelta(seconds=1),
    )
    if produced.entries != len(walked) or produced.verified is not True:
        raise CheckFailedError("the compliance export did not carry exactly the ledger's entries")
    history = chain_from_rows((await h.execute(recorded())).all()).entries
    recorded_values = {
        value
        for link in history
        for value in (
            link.deployment.commit,
            link.deployment.image,
            link.deployment.previous,
            link.deployment.fingerprint(),
            link.entry_hash,
        )
        if len(value) >= DEPLOYMENT_VALUE_MIN_CHARS
    }
    if any(value in produced.document for value in recorded_values):
        raise CheckFailedError("the compliance export held the deployment history")
    if not recorded_values:
        raise CheckNotRunError(NO_DEPLOYMENT_IS_RECORDED_TO_KEEP_OUT)


@check(
    leaves=("M24.3.4", "M32.1.2.4"),
    sentence=(
        "A grant, a publish, a leash change, a merge, a sensitive read and a browser session each "
        "reach the ledger with their actor and trace, and the audit view shows them and the "
        "session's recording; the ledger verifies and catches a missing newest entry; the read's "
        "trace is stored masked and read only under its own role; and the compliance export "
        "holds no deployment history."
    ),
)
async def each_audited_act_is_in_the_ledger_and_a_missing_entry_is_caught(h: Harness) -> None:
    from brain.audit.chain_check import (
        StoredLedgerSequence,
        check_ledger,
        entry_of,
        published_anchor,
    )
    from brain.audit.reads import READ_LOG_CAPABILITY
    from brain.audit.verify import Checkpoint, Completeness, verify_window
    from brain.audit.view import MAX_PAGE_SIZE, AuditFilter, AuditView
    from brain.audit_routes import StoredLedger, read_page
    from brain.core.lane import Lane
    from brain.core.redaction import ChannelPayload
    from brain.gate.context import Channel
    from brain.gate.finish import Finished, Origin, ToolCallOutcome, finish
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.sensitive_read_store import SensitiveReadRecorder
    from brain.ops.telemetry_store import TelemetryRecorder
    from brain.ops.trace_store import TraceRecorder
    from brain.resolution.canonical import EntityType
    from brain.tables.gate import CapabilityGrantRow

    # The whole ledger first, with nothing written, so the walk holds no lock.
    ledger = StoredLedgerSequence(h.sessions)
    # The newest entry as the published head, read as the anchor route reads it; the route
    # itself is the audit_anchor control's, which a cron outside the tree calls.
    newest_before = await ledger.newest()
    whole = await check_ledger(
        ledger,
        at=h.now,
        anchor=None
        if newest_before is None
        else published_anchor(
            seq=newest_before.seq, head=newest_before.entry_hash, recorded_at=h.now
        ),
    )
    if not whole.continuous:
        raise CheckFailedError("the install's ledger did not verify from its first entry")
    if newest_before is not None and whole.completeness is not Completeness.ANCHORED:
        raise CheckFailedError("the install's ledger did not hold its newest entry as its head")

    await h.found_departments()
    admin, subject, auditor = (h.principal(A, role) for role in ("admin", "subject", "auditor"))
    for one in (admin, subject):
        await h.person(one, department=A)
    await h.person(
        auditor,
        department=A,
        grants=(
            ("read:audit.*", Scope.unrestricted()),
            (READ_LOG_CAPABILITY.value, Scope.unrestricted()),
        ),
    )

    # 1. A grant, as the Govern screen writes one.
    await _as(
        h,
        admin,
        1,
        insert(CapabilityGrantRow).values(
            principal_id=subject,
            capability="read:knowledge",
            scope=Scope.department(A).model_dump(mode="json"),
            granted_by=admin,
            reason="Granted by an install acceptance check for the length of the check",
            not_after=h.now + timedelta(hours=1),
        ),
    )
    # 2. A publish: the template version an install of the check's own agent writes.
    agent = await _an_agent(h, admin)
    # 3. The agent's leash loosened for one target of the check's own.
    before = (
        await h.execute(
            text(
                "SELECT effective_document -> 'guardrails.leash' FROM agent.template_instance"
                " WHERE id = :agent"
            ).bindparams(agent=agent)
        )
    ).scalar_one_or_none()
    rungs = [
        *(before if isinstance(before, list) else []),
        {"target": f"acceptance_{h.run}", "scope": Scope().model_dump(mode="json"), "rung": 2},
    ]
    await _as(
        h,
        admin,
        3,
        text(
            "UPDATE agent.template_instance SET effective_document ="
            " jsonb_set(effective_document, '{guardrails.leash}', CAST(:rungs AS jsonb))"
            " WHERE id = :agent"
        ).bindparams(rungs=json.dumps(rungs), agent=agent),
    )
    # 4. Two entities of the check's own, one merged into the other.
    kept, gone = f"acceptance_{h.run}_kept", f"acceptance_{h.run}_gone"
    kind = next(iter(EntityType)).value
    await _as(
        h,
        admin,
        4,
        *(
            text(
                "INSERT INTO er.canonical (entity_id, entity_type, created_by,"
                " created_from_source, created_from_entity, created_from_source_id)"
                " VALUES (:entity, :kind, :by, 'acceptance', 'acceptance', :entity)"
            ).bindparams(entity=entity, kind=kind, by=admin)
            for entity in (kept, gone)
        ),
        text(
            "UPDATE er.canonical SET merged_into = :kept, merged_at = now() WHERE entity_id = :gone"
        ).bindparams(kept=kept, gone=gone),
    )
    # 5. A read of the subject's personnel record, finished as every request finishes, and traced
    # by the recorder the application installs. The name is a word nothing on the install holds.
    reader = await StoredPrincipals(h.sessions).live_principal(admin)
    if reader is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    canary = h.word()
    record = {"@entity": "personnel", "principal_id": subject, "name": canary}
    await finish(
        (
            TelemetryRecorder(h.sessions),
            SensitiveReadRecorder(h.sessions),
            TraceRecorder(h.sessions, environment=h.settings.env),
        ),
        Finished(
            Origin(trace_id=_trace(h, 5), principal=reader, channel=Channel.CONSOLE),
            h.now,
            ToolCallOutcome(refused=False, disclosed=ChannelPayload(records=(record,))),
            completed_at=h.now,
            entitlement_hash=(await h.reach(admin)).ent_hash(),
            lane=Lane.TASK,
            tool_calls=1,
        ),
    )
    # 6. The check's agent opens a browser on a sealed envelope and closes it with a recording.
    run_id, recording = await _a_browser_session(h, admin, agent)

    # Installing the agent writes entries of its own as well, so the acts are looked for among
    # the actor's entries rather than held equal to them.
    entries = await _entries(h, admin)
    if Counter(ACTS) - Counter((action, kind_of(subject)) for action, subject, _ in entries):
        raise CheckFailedError("an act did not reach the ledger with the actor who made it")
    for action, _, trace in entries:
        if action in ACTED_UNDER_THEIR_OWN_TRACE and not trace.startswith(f"{h.trace_id}-act"):
            raise CheckFailedError("an act's entry did not carry the trace of the act")
    read_trace = next(trace for action, _, trace in entries if action == "record_read")
    requested = (
        await h.execute(
            text("SELECT count(*) FROM obs.request_telemetry WHERE trace_id = :t").bindparams(
                t=read_trace
            )
        )
    ).scalar_one()
    if read_trace != _trace(h, 5) or requested != 1:
        raise CheckFailedError("a sensitive read's entry could not be followed to its request")

    reach = await h.reach(auditor)
    page = await read_page(
        StoredLedger(h.sessions),
        lambda loaded: AuditView(loaded, reader=reach, now=h.now),
        AuditFilter(actors=frozenset({admin})),
        limit=MAX_PAGE_SIZE,
        cursor=None,
        newest_first=True,
    )
    if Counter(ACTS) - Counter((one.action.value, one.subject_kind) for one in page.rows):
        raise CheckFailedError("the audit view did not show an auditor every act that was made")
    ends = [
        one.details
        for one in page.rows
        if one.action.value == "browser_session" and one.subject_id == run_id
    ]
    if {"change": "ended", "recording": recording} not in ends:
        raise CheckFailedError("the audit view did not show a browser session's recording")

    tail = [entry_of(row) for row in await ledger.after(whole.last_seq, limit=500)]
    if not tail or any(one is None for one in tail):
        raise CheckFailedError("the entries the acts appended could not be read back as a chain")
    walked = [one for one in tail if one is not None]
    newest = walked[-1]
    anchor = published_anchor(seq=newest.seq, head=newest.entry_hash, recorded_at=h.now)
    checkpoint = (
        None
        if whole.last_seq is None
        else Checkpoint(
            through_seq=whole.last_seq,
            entry_hash=whole.head,
            recorded_at=h.now,
            recorded_by=CHECKPOINT_BY,
        )
    )
    held = verify_window(walked, at=h.now, checkpoint=checkpoint, anchors=(anchor,))
    if not held.continuous or held.completeness is not Completeness.ANCHORED:
        raise CheckFailedError("the entries the acts appended did not chain onto the ledger")
    cut = verify_window(walked[:-1], at=h.now, checkpoint=checkpoint, anchors=(anchor,))
    if cut.completeness is not Completeness.ANCHOR_MISSING:
        raise CheckFailedError("a ledger missing its newest entry was not caught by its head")

    await _the_trace_is_masked_and_held_apart(h, auditor, read_trace, canary)
    await _the_export_holds_no_deployment_history(h, reach, walked)
