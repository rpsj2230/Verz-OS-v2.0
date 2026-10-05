"""The install acceptance checks for connectors: review refusals, a sync, the pin, a life.

Four checks, split where the leaves split. The first holds test declarations to the install's own
manifest review, which is `brain.connectors.manifest`'s constructors and nothing else: the product
has no other door a projection comes through. The second is the worker's read of a source, driven
through `brain.ops.connector_sync_run.attempt` with the source's answers recorded in the check and a
canary planted in them, and the install's own index audit looking for the canary afterwards. The
third connects a source inside the check's transaction under a declaration this release no longer
makes, and asks the worker's plan whether the next sync may read it. The fourth takes a source
through its life as the Connectors screen's routes do (connected, switched off, connected again and
upgraded to a changed declaration), reading the worker's plan, the live reads and the ledger after
each step.

**No check calls a source, and no check holds a real key.** The recorded answers are written here
in the envelope Xero documents for its Invoices and Contacts endpoints, as the connector's own
recordings in the test corpus hold them, and the caller hands them back without opening a socket.
The key the lease gives is minted for the check and dropped with it. The resolver answers one fixed
public address for every name, which is what the address rule needs to see and what nothing ever
connects to. See `A_RECORDED_ANSWER_IS_NEVER_A_CALL`.

**The source is Xero because it is the one this release reads with a verified ceiling and no
department of its own.** The sync needs a reading, a manifest the stored settings build, a
visibility predicate a record can carry and a measured ceiling; `brain.ops.connector_sync.plan_for`
asks all four, and Xero passes each on every install. Its tenant is a fresh identifier per run, so
no row the checks write could be mistaken for one a real connection wrote. Rejected: a source of
the check's own, which would prove a connector nobody ships.

**The pin check connects the source, so it steps aside where the install has connected it.** A
live connection of the same source is a real one, `StoredConnections.connect` refuses a second, and
disconnecting the owner's source inside a check, even one that is rolled back, would hold his
connection's lock for the length of the check. See `A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`.

**The canary search reads every row, so it runs as the worker's login.** The harness's sessions
run as the application role, which row-level security binds, and `brain.ops.index_audit` refuses
to search as a role that cannot see a row, for its own reason. The worker runs the checks as the
schema's owner (`Settings.owner_database_url`), so the search resets the role to that login for its
own statements, inside the same transaction, which is the only place the check's rows exist. A run
by hand in the application's container logs in as the application role, and the check says it was
not run. See `A_SEARCH_THAT_CANNOT_SEE_EVERY_ROW_IS_NOT_RUN`. The search is the audit's own scan of
every row of every table, so what it costs grows with the install; each table is one statement,
bounded by the run's statement timeout, and nothing is locked by reading.

Task ids: M38.5.1, M11.1.6
"""

from __future__ import annotations

import dataclasses
import json
import secrets
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.connectors.manifest import ProjectedEntity, ProjectedField
    from brain.ops.connector_lease import LeaseOutcome
    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.secrets import SecretRef

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 80

# ------------------------------------------------------------------ written-down reasons
#: Why nothing the sync check does reaches a source.
A_RECORDED_ANSWER_IS_NEVER_A_CALL: Final = (
    "The sync check reads answers written in the check, in the source's documented envelope, "
    "through a caller that returns them and opens no connection. The key it leases is minted for "
    "the check and never leaves the process, and every name resolves to one fixed public address "
    "nothing connects to, so the product's address rule is asked and no source is."
)

#: Why the pin check is not run where the source is connected already.
A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN: Final = (
    "The pin check connects the source it reads inside its own transaction. Where this install "
    "has that source connected, connecting it again is refused, and moving the real connection "
    "aside would hold its lock while the check runs, so the check is not run."
)

#: Why the canary search is not run as the application role.
A_SEARCH_THAT_CANNOT_SEE_EVERY_ROW_IS_NOT_RUN: Final = (
    "The canary is looked for in every row of every table, and a login bound by row-level "
    "security reads only the rows its settings admit. The worker runs the checks as the schema's "
    "owner, which sees every row; a run by the application's login could not have looked, so it "
    "is recorded as not run rather than as clean."
)

#: What the pin check says when the install has the source connected already.
SOURCE_ALREADY_CONNECTED: Final = (
    "this install has the source the check connects connected already, so the check does not "
    "connect it again"
)

#: What the canary check says when the audit could not look.
AUDIT_COULD_NOT_LOOK: Final = (
    "this run's database login cannot read every row, so the index audit could not look for the "
    "canary; the worker's run can"
)

# ------------------------------------------------------------------------ the figures
#: The source every database check here reads. See the module docstring.
SOURCE: Final = "xero"

#: The one address every name resolves to. Global unicast, so the address rule admits it as
#: public, in a block no registry has handed to anybody, so it names nobody's machine; and never
#: connected to, because the caller below opens no socket. Not an IPv4 literal, which the
#: client-independence sweep refuses because one names a machine somewhere.
STAND_IN_ADDRESS: Final = "2000::1"

#: A due date in the source's own `/Date(...)/` form, far from any wall clock.
DUE_DATE: Final = "/Date(32503680000000+0000)/"

#: The twelve pointer fields the review check declares, one label among them.
POINTERS: Final = (
    ("record_id", "identifier", ("identify",)),
    ("parent_id", "join_key", ("join",)),
    ("company_ref", "join_key", ("join",)),
    ("status", "status", ("filter", "count")),
    ("stage", "status", ("filter",)),
    ("priority", "status", ("sort",)),
    ("created_at", "timestamp", ("sort",)),
    ("updated_at", "timestamp", ("sort",)),
    ("due_at", "timestamp", ("filter",)),
    ("closed_at", "timestamp", ("filter",)),
    ("reference", "identifier", ("identify",)),
    ("title", "label", ("identify",)),
)

#: Names the permanent denylist holds: an email, a phone, an address, an identity number, bank
#: details and a salary, each as the name itself and as a spelling of it.
PERSONAL_FIELDS: Final = (
    "email",
    "contact_email",
    "phone",
    "mobile_phone",
    "address",
    "billing_address",
    "nric",
    "passport",
    "bank_account",
    "iban",
    "salary",
    "employee_salary",
)

#: The five shapes a projected field may take, as the leaf lists them.
POINTER_SHAPES: Final = frozenset({"identifier", "join_key", "status", "timestamp", "label"})


# ------------------------------------------------------------------------ the helpers
def _field(name: str, shape: str, uses: Sequence[str]) -> ProjectedField:
    from brain.connectors.manifest import FieldShape, HotUse, ProjectedField

    return ProjectedField(name, FieldShape(shape), tuple(HotUse(one) for one in uses))


def _pointers() -> tuple[ProjectedField, ...]:
    return tuple(_field(name, shape, uses) for name, shape, uses in POINTERS)


def _entity(
    fields: Sequence[ProjectedField], *, signal: str = "webhook", visibility: Any = None
) -> ProjectedEntity:
    """One entity as a connector author declares it: review runs as it is constructed."""
    from brain.connectors.manifest import ChangeSignal, ProjectedEntity
    from brain.core.scope import Clause, Op, Scope

    return ProjectedEntity(
        entity="acceptance_record",
        fields=tuple(fields),
        change_signal=ChangeSignal(signal),
        visibility=(
            Scope(clauses=(Clause(field="tenant_id", op=Op.EQ, value="acceptance_tenant"),))
            if visibility is None
            else visibility
        ),
    )


def _refused(fields: Sequence[ProjectedField], **kwargs: Any) -> bool:
    """Whether manifest review refuses this declaration."""
    from brain.connectors.manifest import ManifestError

    try:
        _entity(fields, **kwargs)
    except ManifestError:
        return True
    return False


def _failing(one: ProjectedField, *, fields: Sequence[ProjectedField], signal: str) -> set[str]:
    """The clauses review names against one field, read from its verdicts rather than its text."""
    from brain.connectors.manifest import ChangeSignal, FieldShape, failed_clauses, projectability

    labels = sum(1 for each in fields if each.shape is FieldShape.LABEL)
    verdicts = projectability(
        one, signal=ChangeSignal(signal), label_count=labels, field_count=len(fields)
    )
    return {verdict.clause for verdict in failed_clauses(verdicts)}


def _settings() -> dict[str, str]:
    """A tenant identifier nothing else holds, which is all the source is connected with."""
    return {"tenant_id": str(uuid.uuid4())}


@dataclass
class _Lease:
    """`brain.ops.connector_sync_run.KeyLease` over a key minted for the check."""

    given: str = field(repr=False)

    user_name: str = ""

    def key(self) -> str:
        return self.given

    def user(self) -> str:
        from brain.ops.connector_sync import NO_KEY
        from brain.ops.connector_sync_run import ConnectorKeyAbsentError

        if not self.user_name:
            raise ConnectorKeyAbsentError(NO_KEY)
        return self.user_name

    def close(self, now: datetime) -> LeaseOutcome:
        from brain.ops.connector_lease import LeaseOutcome

        del now
        return LeaseOutcome.NONE


@dataclass
class _Keys:
    """`ConnectorKeys` leasing a key this check made. See `A_RECORDED_ANSWER_IS_NEVER_A_CALL`."""

    leased: int = 0

    def lease(self, ref: SecretRef, *, now: datetime) -> _Lease:
        del ref, now
        self.leased += 1
        return _Lease(secrets.token_hex(16))


class _Resolver:
    """Every name answers the stand-in address. See `A_RECORDED_ANSWER_IS_NEVER_A_CALL`."""

    def resolve(self, host: str) -> list[str]:
        del host
        return [STAND_IN_ADDRESS]


@dataclass
class _Recorded:
    """`SourceCaller` answering each endpoint with the body written for it, and nothing else."""

    invoices: bytes
    contacts: bytes
    asked: list[str] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        self.asked.append(url)
        if "/Invoices" in url:
            return SourceAnswer(status=200, headers={}, body=self.invoices)
        if "/Contacts" in url:
            return SourceAnswer(status=200, headers={}, body=self.contacts)
        return SourceAnswer(status=404, headers={}, body=b"{}")


async def _no_wait(seconds: float) -> None:
    del seconds


async def _nothing_kept() -> datetime | None:
    """The key the console would keep in the vault. The pin check keeps none."""
    return None


def _clock() -> datetime:
    return datetime.now(UTC)


async def _search(h: Harness, needle: str) -> tuple[str, ...]:
    """`brain.ops.index_audit.tables_holding` as the worker's login, inside the check's transaction.

    See `A_SEARCH_THAT_CANNOT_SEE_EVERY_ROW_IS_NOT_RUN`. The role is reset for these statements
    only: the next harness session sets the application role again when it begins.
    """
    from brain.ops.index_audit import AuditRefusedError, tables_holding

    async with AsyncSession(bind=h.connection, join_transaction_mode="create_savepoint") as session:
        await session.execute(text("RESET ROLE"))
        try:
            found = await tables_holding(session, needle)
        except AuditRefusedError:
            raise CheckNotRunError(AUDIT_COULD_NOT_LOOK) from None
        await session.commit()
    return found


# ------------------------------------------------------------ 1. manifest review refuses
@check(
    leaves=("M11.4.2", "M11.4.3", "M11.4.4", "M11.8.1", "M11.4.7"),
    sentence=(
        "The install's manifest review accepts a projection of twelve pointer fields and refuses a "
        "thirteenth, a field failing any one of the five projectability clauses, an email, phone, "
        "address, identity number, bank or salary field, a shape that is not an id, join key, "
        "status, timestamp or one label, and any field on a source with no change signal."
    ),
)
async def manifest_review_refuses_a_projection_that_is_more_than_a_pointer(h: Harness) -> None:
    from brain.connectors.manifest import CLAUSE_NAMES, FieldShape, ManifestError
    from brain.connectors.minimal_index import StoredRow, minimal_index_findings
    from brain.core.projection import MAX_LABEL_CHARS, MAX_PROJECTED_FIELDS, is_forbidden
    from brain.ops.connectable import manifest_for

    hot, signalled, permitted, pointer, within = CLAUSE_NAMES
    twelve = _pointers()
    if len(twelve) != MAX_PROJECTED_FIELDS:
        raise CheckFailedError("the install's projection cap is not the twelve fields it declares")
    try:
        accepted = _entity(twelve)
        # A whole manifest, reviewed as a connector declares it, with the twelve as its projection.
        base = manifest_for(SOURCE, _settings())
        dataclasses.replace(base, projections=(accepted,))
    except ManifestError:
        raise CheckFailedError("manifest review refused twelve pointer fields") from None

    # M11.4.2: the thirteenth field.
    thirteen = (*twelve, _field("archived_at", "timestamp", ("filter",)))
    if not _refused(thirteen):
        raise CheckFailedError("manifest review accepted a thirteenth projected field")
    if within not in _failing(thirteen[-1], fields=thirteen, signal="webhook"):
        raise CheckFailedError("a thirteenth field was not refused by the twelve-field cap")

    # M11.4.3: each clause refuses on its own, and names itself.
    plain = twelve[:3]
    clauses = {
        hot: (*plain, _field("summary_ref", "identifier", ())),
        permitted: (*plain, _field("contract_value", "status", ("filter",))),
        pointer: (*plain, twelve[-1], _field("subtitle", "label", ("identify",))),
    }
    for clause, fields in clauses.items():
        if not _refused(fields):
            raise CheckFailedError(
                "manifest review accepted a field failing a projectability clause"
            )
        if clause not in _failing(fields[-1], fields=fields, signal="webhook"):
            raise CheckFailedError("a refused field was not refused by the clause it fails")

    # M11.4.4: the denylist refuses each personal field by name and by spelling.
    for name in PERSONAL_FIELDS:
        one = _field(name, "identifier", ("identify",))
        if not is_forbidden(name) or not _refused((*plain, one)):
            raise CheckFailedError("manifest review accepted a projected personal field")
        if _failing(one, fields=(*plain, one), signal="webhook") != {permitted}:
            raise CheckFailedError("a personal field was not refused by the denylist alone")

    # M11.8.1: five shapes and no sixth, one label, and a kept row held to its declaration.
    if {one.value for one in FieldShape} != POINTER_SHAPES:
        raise CheckFailedError("manifest review admits a field shape that is not a pointer")
    for shape in ("body", "text", "note", "amount"):
        try:
            FieldShape(shape)
        except ValueError:
            continue
        raise CheckFailedError("manifest review admits a field shape that is not a pointer")
    manifest = dataclasses.replace(base, projections=(accepted,))
    tenant = "acceptance_tenant"
    row = {"record_id": "r1", "status": "open", "title": "a label", "tenant_id": tenant}
    held = StoredRow(source=manifest.name, entity=accepted.entity, source_id="r1", fields=row)
    if minimal_index_findings(manifest, (held,)):
        raise CheckFailedError("a kept row holding only declared pointer fields was refused")
    for extra in (
        {"amount_due": "1"},
        {"title": "x" * (MAX_LABEL_CHARS + 1)},
        {"tenant_id": "another_tenant"},
    ):
        wider = dataclasses.replace(held, fields={**row, **extra})
        if not minimal_index_findings(manifest, (wider,)):
            raise CheckFailedError(
                "a kept row holding a field that is not a declared pointer was accepted"
            )

    # M11.4.7: no change signal, no fields; and an empty projection is still allowed.
    if not _refused(plain, signal="none"):
        raise CheckFailedError("a source with no change signal was allowed to project a field")
    if any(signalled not in _failing(one, fields=plain, signal="none") for one in plain):
        raise CheckFailedError(
            "a field on a source with no change signal was refused for another reason"
        )
    if _refused((), signal="none"):
        raise CheckFailedError("a source with no change signal was refused an empty projection")
    del h


# ------------------------------------------------ 2. a sync keeps its index, and the canary
@check(
    leaves=("M11.4.1", "M11.4.5", "M11.8.2"),
    sentence=(
        "The worker's read of a Xero tenant made up for the check, from recorded answers with a "
        "canary planted in the amount and tax number, leaves proj.record holding source, entity, "
        "id and the declared fields with the tenant predicate and no list of people, and the "
        "install's index audit finds the canary in no table."
    ),
)
async def a_sync_keeps_its_minimal_index_and_the_canary_reaches_no_table(h: Harness) -> None:
    from brain.connectors.manifest import PRINCIPAL_FIELD_RE, RESOLVED_ACL_RE, manifest_digest
    from brain.connectors.minimal_index import StoredRow, fresh_canary, minimal_index_findings
    from brain.connectors.xero import ENTITY_CONTACT, ENTITY_INVOICE
    from brain.core.scope import Clause, Op, Scope
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import Connection
    from brain.ops.connector_sync import SyncOutcome, plan_for
    from brain.ops.connector_sync_run import attempt
    from brain.ops.connector_sync_store import LiveConnection
    from brain.tables.projection import ProjectedRecordRow

    settings = _settings()
    tenant = settings["tenant_id"]
    manifest = manifest_for(SOURCE, settings)
    connection = Connection(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(manifest),
        connected_by=h.actor,
        connected_at=h.now,
    )
    plan = plan_for(connection, last=None, now=h.now)
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read a source connected as declared")

    # M11.4.5 at review: the predicate is kept, and a resolved list in either shape is refused.
    predicate = Scope(clauses=(Clause(field="owner_id", op=Op.IN, value=("u_one", "u_two")),))
    for refused in (
        {"fields": (*_pointers()[:3], _field("shared_with_users", "identifier", ("filter",)))},
        {"fields": _pointers()[:3], "visibility": predicate},
        {"fields": _pointers()[:3], "visibility": Scope.unrestricted()},
    ):
        if not _refused(**refused):
            raise CheckFailedError("manifest review accepted a resolved list of people")

    canary = fresh_canary("ACCEPTANCE")
    invoice_id, contact_id, number = str(uuid.uuid4()), str(uuid.uuid4()), h.word()
    invoices = {
        "Invoices": [
            {
                "InvoiceID": invoice_id,
                "InvoiceNumber": number,
                "Contact": {"ContactID": contact_id},
                "AmountDue": canary,
                "DueDate": DUE_DATE,
                "Status": "AUTHORISED",
            }
        ]
    }
    contacts = {
        "Contacts": [
            {
                "ContactID": contact_id,
                "Name": "Acceptance check contact",
                "ContactStatus": "ACTIVE",
                "UpdatedDateUTC": DUE_DATE,
                "TaxNumber": canary,
                "EmailAddress": canary,
            }
        ]
    }
    caller = _Recorded(
        invoices=json.dumps(invoices).encode("utf-8"),
        contacts=json.dumps(contacts).encode("utf-8"),
    )
    keys = _Keys()
    done = await attempt(
        LiveConnection(id=uuid.uuid4(), connection=connection),
        plan,
        previous=None,
        sessions=h.sessions,
        keys=keys,
        caller=caller,
        resolver=_Resolver(),
        clock=_clock,
        sleep=_no_wait,
    )
    if done.outcome is not SyncOutcome.SYNCED or done.records != 2 or keys.leased != 1:
        raise CheckFailedError("the worker did not read the recorded answers to the end")

    # M11.4.1: the rows, read back through the application's own role.
    rows = (
        await h.execute(
            select(
                ProjectedRecordRow.source,
                ProjectedRecordRow.entity,
                ProjectedRecordRow.source_id,
                ProjectedRecordRow.fields,
                ProjectedRecordRow.last_seen_at,
            ).where(
                ProjectedRecordRow.source == SOURCE,
                ProjectedRecordRow.source_id.in_((invoice_id, contact_id)),
            )
        )
    ).all()
    kept = {str(entity): (str(source_id), dict(fields)) for _, entity, source_id, fields, _ in rows}
    if len(rows) != 2 or set(kept) != {ENTITY_INVOICE, ENTITY_CONTACT}:
        raise CheckFailedError("proj.record did not hold one row per record the source answered")
    if kept[ENTITY_INVOICE][0] != invoice_id or kept[ENTITY_CONTACT][0] != contact_id:
        raise CheckFailedError("proj.record did not keep the source's own identifier")
    for entity, (_, fields) in kept.items():
        projection = manifest.projection_for(entity)
        declared = set(() if projection is None else projection.field_names)
        if set(fields) != declared | {"tenant_id"}:
            raise CheckFailedError("proj.record kept other than the declared hot fields")
    invoice = kept[ENTITY_INVOICE][1]
    if (invoice.get("invoice_number"), invoice.get("contact_id"), invoice.get("status")) != (
        number,
        contact_id,
        "AUTHORISED",
    ):
        raise CheckFailedError("proj.record did not hold the hot fields the source answered")
    if any(one is None for *_, one in rows):
        raise CheckFailedError("proj.record did not say when the source last confirmed a row")

    # M11.4.5 on the rows: the predicate's value, and nothing that lists people.
    for _, fields in kept.values():
        if fields.get("tenant_id") != tenant:
            raise CheckFailedError(
                "a projected row did not store its source's visibility predicate"
            )
        for name, value in fields.items():
            listed = isinstance(value, list | dict)
            if listed or RESOLVED_ACL_RE.search(name) or PRINCIPAL_FIELD_RE.search(name):
                raise CheckFailedError("a projected row stored a resolved list of people")
    stored = tuple(
        StoredRow(source=SOURCE, entity=entity, source_id=source_id, fields=fields)
        for entity, (source_id, fields) in kept.items()
    )
    if minimal_index_findings(manifest, stored):
        raise CheckFailedError("the index audit's rule refused a row the sync kept")

    # M11.8.2: the audit looks everywhere; the tenant it must find proves it could see the rows.
    if "proj.record" not in await _search(h, tenant):
        raise CheckFailedError("the index audit could not see the rows the sync kept")
    if await _search(h, canary):
        raise CheckFailedError("the canary planted in a recorded answer was found in a table")


# ---------------------------------------------------------- 3. the pin fails closed
@check(
    leaves=("M11.1.7",),
    sentence=(
        "A Xero tenant connected in the check under a declaration whose one tool description "
        "differs from this release's is refused by the worker's next sync plan because the digest "
        "differs, and is read by it once reconnected under this release's declaration; rotating "
        "the key's reference leaves the digest where it was."
    ),
)
async def a_changed_declaration_makes_the_next_sync_refuse(h: Harness) -> None:
    from brain.connectors.manifest import manifest_digest
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync import (
        DECLARATION_NOT_AGREED,
        plan_for,
        sync_in_words,
    )
    from brain.ops.connector_sync_store import read_live

    settings = _settings()
    declared = manifest_for(SOURCE, settings)
    if not declared.tools:
        raise CheckFailedError("the source the check connects declares no tool to redefine")
    first = declared.tools[0]
    redefined = dataclasses.replace(
        declared,
        tools=(
            dataclasses.replace(first, description=f"{first.description} {h.word()}"),
            *declared.tools[1:],
        ),
    )
    if manifest_digest(redefined) == manifest_digest(declared):
        raise CheckFailedError("a tool's description changed and the manifest's digest did not")
    rotated = dataclasses.replace(
        declared,
        credential=dataclasses.replace(
            declared.credential,
            ref=dataclasses.replace(declared.credential.ref, path=h.word().lower()),
        ),
    )
    if manifest_digest(rotated) != manifest_digest(declared):
        raise CheckFailedError("a rotated key reference moved the manifest's digest")

    if (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckNotRunError(SOURCE_ALREADY_CONNECTED)
    store = StoredConnections(h.sessions)
    await store.connect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(redefined),
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=_nothing_kept,
    )

    async def planned() -> Any:
        async with h.sessions() as session, session.begin():
            found = [one for one in await read_live(session) if one.connection.connector == SOURCE]
        if len(found) != 1:
            raise CheckFailedError("the worker's statement did not read back the connected source")
        return plan_for(found[0].connection, last=None, now=h.now)

    refused = await planned()
    if refused.refused != DECLARATION_NOT_AGREED or refused.manifest is not None:
        raise CheckFailedError("a sync was planned under a declaration nobody agreed to")
    if sync_in_words(refused, None) != DECLARATION_NOT_AGREED:
        raise CheckFailedError("the Connectors screen did not say why the source is not read")

    await store.reconnect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(declared),
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
    )
    agreed = await planned()
    if agreed.refused or not agreed.due or agreed.manifest != declared:
        raise CheckFailedError("a source reconnected under this release's declaration was not read")


# ------------------------------------------------ 4. connected, switched off, upgraded
@check(
    leaves=("M11.1.6",),
    sentence=(
        "A Xero tenant is connected, switched off and connected again inside the check through "
        "the store the Connectors screen's routes call, then upgraded to a changed declaration "
        "the way its edit route re-pins one: the worker's plan and the live reads follow each "
        "step, and every step is an entry in the audit ledger under who took it."
    ),
)
async def a_source_is_connected_switched_off_and_upgraded_from_the_console(h: Harness) -> None:
    from brain.connectors.declaration import shipped
    from brain.connectors.manifest import manifest_digest
    from brain.connectors.xero import ENTITY_INVOICE
    from brain.ops.connectable import CONNECTABLE, manifest_for
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync import plan_for
    from brain.ops.connector_sync_store import read_live
    from brain.ops.live_read_run import ConnectedSources

    if SOURCE not in shipped() or SOURCE not in CONNECTABLE:
        raise CheckFailedError("the source is not registered as one the console connects")
    if (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckNotRunError(SOURCE_ALREADY_CONNECTED)

    settings = _settings()
    declared = manifest_for(SOURCE, settings)
    store = StoredConnections(h.sessions)
    said = {"actor": h.actor, "trace_id": h.trace_id, "ent_hash": SET_UP_REACH}

    async def reading() -> tuple[Any, ...]:
        async with h.sessions() as session, session.begin():
            return tuple(
                one for one in await read_live(session) if one.connection.connector == SOURCE
            )

    def reads_live(connections: Sequence[Any]) -> bool:
        """Whether a question would read the source live, asked as the answer path asks."""
        sources = ConnectedSources(
            {one.connection.connector: one.connection for one in connections},
            keys=_Keys(),
            caller=_Recorded(invoices=b"{}", contacts=b"{}"),
            resolver=_Resolver(),
            clock=_clock,
        )
        return sources.reads(SOURCE, ENTITY_INVOICE) is not None

    # Registered and enabled: connected, read by the worker's plan.
    await store.connect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(declared),
        keep_key=_nothing_kept,
        **said,
    )
    first = await reading()
    if len(first) != 1 or not plan_for(first[0].connection, last=None, now=h.now).due:
        raise CheckFailedError("a source connected from the console was not read by the worker")
    if not reads_live(first):
        raise CheckFailedError("a source connected from the console was not read live")

    # Switched off: the worker reads it no more, and nothing is left connected.
    await store.disconnect(SOURCE, **said)
    off = await reading()
    if off or reads_live(off) or (await h.execute(live(SOURCE))).scalar_one_or_none() is not None:
        raise CheckFailedError("a source switched off from the console was still read")

    # Switched on again, then upgraded: a declaration this release changed is re-pinned by the
    # edit route's own call, and the next plan reads under it.
    first_tool = declared.tools[0]
    older = dataclasses.replace(
        declared,
        tools=(
            dataclasses.replace(first_tool, description=f"{first_tool.description} {h.word()}"),
            *declared.tools[1:],
        ),
    )
    await store.connect(
        connector=SOURCE,
        settings=settings,
        digest=manifest_digest(older),
        keep_key=_nothing_kept,
        **said,
    )
    stale = await reading()
    if len(stale) != 1 or plan_for(stale[0].connection, last=None, now=h.now).due:
        raise CheckFailedError("a source pinned to an older declaration was read before upgrade")
    await store.reconnect(
        connector=SOURCE, settings=settings, digest=manifest_digest(declared), **said
    )
    upgraded = await reading()
    if len(upgraded) != 1:
        raise CheckFailedError("an upgraded source was not left connected once")
    plan = plan_for(upgraded[0].connection, last=None, now=h.now)
    if not plan.due or plan.manifest != declared:
        raise CheckFailedError("an upgraded source was not read under this release's declaration")

    changes = [
        (str(actor), details if isinstance(details, dict) else json.loads(details))
        for actor, details in (
            await h.execute(
                text(
                    "SELECT actor_id, details FROM obs.audit_entry"
                    " WHERE subject = :subject AND trace_id = :trace ORDER BY seq"
                ).bindparams(subject=f"connector:{SOURCE}", trace=h.trace_id)
            )
        ).all()
    ]
    steps = [details.get("change") for _, details in changes]
    if steps != ["connected", "disconnected", "connected", "disconnected", "connected"]:
        raise CheckFailedError("a step in the source's life is missing from the audit ledger")
    if any(actor != h.actor for actor, _ in changes):
        raise CheckFailedError("a step in the source's life was recorded under somebody else")
