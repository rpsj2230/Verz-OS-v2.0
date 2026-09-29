"""The install acceptance check for audit and tracing: each audited act, its entry and its chain.

M24.3.4 asks that a grant, a leash change, a merge, a publish, a sensitive read and a browser
session each be seen in the audit view, that the chain verifies and a removed newest entry is
detected, that a run's trace holds only masked content, and that the compliance export holds no
deployment history.
This check performs every act the install can record, inside its rolled-back transaction, and reads
back what the ledger, the audit view and the chain verifier make of them. It is a module of its own,
named in `brain.ops.acceptance.CHECK_MODULES`, beside the checks that reach a model.

**Every act is the product's own write, attributed as a console request attributes it.** A grant is
the row the Govern screen inserts; a publish is the template version an install writes
(`brain.ops.acceptance_checks_skills._an_agent`); a sensitive read is a finished request handed to
`brain.ops.sensitive_read_store.SensitiveReadRecorder`, which is how every read reaches the ledger.
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

**The leaf cannot be proved whole on any install yet, and the check says so rather than passing.**
A browser session writes nothing to the ledger (`brain.browsing` keeps its envelope in
`ops.browser_envelope` with no trigger, and its recording has no backend wired), and there is no
trace store: `brain.ops.trace_sink.CountingTraceSink` drops every payload by design. So once every
part that exists has been seen working, the check ends as not run with
`A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT`, and a part that exists and does not work fails
it first. The compliance export is not read either: it walks the whole ledger into one document at
an auditor's reach, and the deployment history is kept out of it by construction, which
`tests/unit/test_deployment_history.py` holds.

Task ids: M38.5.1, M24.3.4
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from typing import Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check

# Imported first so the suite's own checks are registered ahead of this one.
from brain.ops.acceptance_checks_skills import _an_agent
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the audit check ends as not run on every install today.
A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT: Final = (
    "every act this install records reached the ledger, the audit view and a chain that caught "
    "its newest entry missing, but a browser session writes no entry and there is no trace "
    "store, so the leaf cannot be proved whole"
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
)

#: The leash rung the check loosens its own agent to. `brain.gate.injection.AutonomyTier`'s top.
LOOSENED: Final = 2

#: Who a verification checkpoint is recorded by. `brain.audit.verify.Checkpoint` needs a name.
CHECKPOINT_BY: Final = "acceptance_check"


#: The acts the check attributes to a trace of their own; the publish is the install's, under the
#: run's trace, because `_an_agent` writes it as the check's set-up.
ACTED_UNDER_THEIR_OWN_TRACE: Final = frozenset(
    {"grant", "leash_change", "entity_merge", "record_read"}
)


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


@check(
    leaves=("M24.3.4",),
    sentence=(
        "A grant, a publish, a leash change, a merge and a sensitive read made by a reserved "
        "administrator each reach the ledger with that actor and the act's trace, and the audit "
        "view shows them; the ledger verifies from its first entry, and a missing newest entry "
        "is caught by the published head."
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
    # 5. A read of the subject's personnel record, finished as every request finishes.
    reader = await StoredPrincipals(h.sessions).live_principal(admin)
    if reader is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    record = {"@entity": "personnel", "principal_id": subject, "name": "Acceptance check"}
    await finish(
        (TelemetryRecorder(h.sessions), SensitiveReadRecorder(h.sessions)),
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

    raise CheckNotRunError(A_BROWSER_SESSION_AND_A_TRACE_STORE_ARE_NOT_BUILT)
