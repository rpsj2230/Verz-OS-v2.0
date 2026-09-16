"""Writing the first administrator: one principal and the grants that make them one, once.

`brain.setup_wizard.apply_install` appoints a first administrator by returning a Super Admin
`RoleGrant`, and nothing stored it, so on a real install no principal existed and nobody held
`admin:sign_in`. The finishing screen asks exactly that question before it binds a sign-in, so
it refused every install, and nobody could ever sign in to bind anybody. This module is the
write that was missing: **the principal the wizard named, live and human, holding every
administration capability over everything, written in one transaction that refuses the moment
any administrator exists.**

**What "administrator" means here is the finishing screen's own test, and it is one function.**
`holds_everywhere` asks whether a reach holds `SIGN_IN_AUTHORITY` with an unrestricted scope.
It lived in `brain.sign_in_routes` and moved here, where both the route and this store import
it, because two readings of "is there an administrator" are two places for the wizard to open
on an install the finishing screen thinks is finished. See `ONE_TEST_OF_AN_ADMINISTRATOR`.

**The grants are every `admin:` capability the source declares, and a test holds that.**
`brain.identity.roles` says no role implies a capability, Super Admin included, so the role on
the wizard's grant confers nothing on its own and the capabilities have to be written as
grants. Which ones is `ADMINISTRATION`, and `tests/unit/test_first_administrator.py` reads
every `Capability(value="admin:...")` under `src/brain` and requires the two sets to be equal,
so a new administrative capability added next month is a red test asking whether the first
administrator should hold it, rather than a screen nobody on the install can open. See
`AN_ADMINISTRATOR_GOVERNS_THE_SYSTEM_AND_READS_NO_DATA`.

**No grant over the company's data is written, deliberately, and since 2026-09-16 the reads of
how the system is run are.** An administrator decides how the system is run, and what a person
may read of the company's data comes from the grants its own departments and the directory sync
write. A first administrator created holding a data read over everything would be the widest
data reach in the system created by whoever held a setup code for an hour, which is exactly the
account the invariant exists to prevent. Until 2026-09-16 this paragraph said "no `read:` grant"
and meant that, and the result was a console that opened one screen: every screen's own read is
a `read:` capability, `brain.console.reads.permitted` asks for it and for a plane besides, and
the administrator held neither, so Sessions, Activity and thirty more refused the one person the
install had. `OVERSIGHT` is the line drawn instead, and it is drawn where the console already
draws it: every screen's read at the existence and configuration planes, the two plane
capabilities up to configuration and never `read:console.content`, and the audit entries about
governing the system. A screen at the content plane, Learning and Memory today, is what a
person or an agent was told, so it is not opened.

**One `approve:` capability is granted, `approve:grant`, and `approve:action` is not.** Letting a
reach into the system is how an install gets its second person: the People screen's grant write,
the Access review and elevation are all behind it, so a first administrator without it is an
install on which nobody can ever grant anybody anything from the console. Approving a suspended
action is different in kind: it lets an agent carry out an act over the company's data, whose
content the first administrator cannot read, and it belongs to whoever a department makes its
approver. See `GOVERNANCE` and `THE_FIRST_ADMINISTRATOR_LETS_THE_SECOND_PERSON_IN`.

`tests/unit/test_administration_reconciliation.py` derives the set from `brain.console.screens`
and opens every screen for a fresh first administrator, because this package must not import the
console. See `AN_ADMINISTRATOR_READS_HOW_THE_SYSTEM_IS_RUN_AND_NO_DATA`.

**An administrator appointed before a capability existed is granted it at the next start.**
`brain.identity.administration_reconciliation` is that write, and argues why it runs at startup
rather than in a migration.

**Single use is a count read under a lock, never a flag.** The transaction takes a
transaction-scoped advisory lock, counts administrators through `gate.resolve_entitlements`,
and refuses unless the count is zero. The lock is what makes two appointments racing each other
one appointment and one refusal: without it both read zero before either commits. The count is
`firstrun.is_open`'s argument, a fact about the system rather than a value somebody sets. The
refusal names nobody, not the administrator who exists and not the one asked for. See
`THE_DOOR_IS_COUNTED_UNDER_A_LOCK`.

**It counts through the one resolver, and the cost of that is stated.** Every live principal's
reach is resolved in one statement and judged by `holds_everywhere`. A query over
`gate.capability_grant` for `admin:sign_in` would be cheaper and would be a second resolver:
it would miss an administrator made through a pack, and `brain.gate.entitlement_store` records
why that copy is the one that goes wrong. It resolves every principal, which on an install the
directory sync has already filled is a statement over the whole staff list; it runs once per
install, and once more for every attempt somebody makes after that, each of which is refused.

**The audit entries are the grant trigger's, attributed to first run.** `0003`'s trigger
appends a `grant` entry for every row this writes. Its actor falls back to the row's
`granted_by` when `brain.actor_id` is unset, and records that as inferred, so this sets the
actor to `firstrun.GRANTED_BY` explicitly with the request's trace id. The entry then says the
same thing `firstrun.first_administrator` put on the role grant, and says it was told rather
than guessed.

**Where it runs, and why not the two obvious places.**

Rejected: the seed command. `python -m brain.deployment.database seed` loads the demo company,
refuses any database holding rows it did not write, and `brain.demo` argues at length that the
demo stops short of an administrator because an administrator arriving with a seed is an
account nobody created. An install that never loads the demo would also never get an
administrator.

Rejected: the finishing screen. It could write the principal and grants and bind the sign-in in
one request, and it would then satisfy its own check with its own write: the question it asks,
whether the named principal is an administrator, would be answered yes by the act of asking.
The finishing screen stays the one that verifies, and this stays the one that appoints.

So it runs at the appointment, where `apply_install` spends the enrolment and returns the grant:
the caller counts `administrators`, passes the count to `apply_install`, and calls `appoint`
last. Last because appointing closes the wizard, and a door closed before the settings are
written is an install that can neither be finished nor started again. See
`APPOINTING_IS_THE_LAST_WRITE`.

**The settings the same wizard produced are written here, in this transaction**, rather than by
the caller before it. That is the only arrangement where the door and the configuration cannot
come apart: a separate write can fail after the wizard has closed, and an appointment that
commits alone closes it over answers kept nowhere. `brain.ops.install_settings` decides what a
row looks like and this module holds the transaction it lands in, which is the same split
`brain.ops.limits` and `brain.ops.limit_store` make. See
`THE_SETTINGS_AND_THE_DOOR_CLOSE_IN_ONE_TRANSACTION`.

**A principal the directory already holds is appointed in place.** The id is inserted with ON
CONFLICT DO NOTHING and read back under a row lock, so a principal the sync created before the
wizard finished keeps its own record and gains the grants, and a disabled, deleted or ended one
is refused rather than resurrected. An existing live grant of one of these capabilities to that
principal is refused by the table's unique index and the whole appointment rolls back, which is
the right direction: `EntitlementSet.scope_for` intersects two grants of one capability, so
writing past it would leave the first administrator narrower than they appear. A read in
`OVERSIGHT` the principal already holds is the one exception, and is kept at its own scope; see
`AN_OVERSIGHT_READ_ALREADY_HELD_IS_KEPT`.

Task ids: M42.5.6, M41.2.4
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.firstrun import GRANT_REASON, GRANTED_BY
from brain.gate.entitlement_store import entitlements_from
from brain.identity.principal_store import COLUMNS, PRINCIPAL_SETTING, readable
from brain.identity.roles import IdentityError, Role, RoleGrant
from brain.ops.install_settings import save as save_settings
from brain.tables.audit import ACTOR_SETTING, TRACE_ID_SETTING
from brain.tables.gate import CapabilityGrantRow
from brain.tables.identity import PrincipalRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why "is there an administrator" has one answer.
ONE_TEST_OF_AN_ADMINISTRATOR: Final = (
    "The wizard closes when an administrator exists and the finishing screen binds a sign-in "
    "only to one. If those two asked different questions, an install could be closed to the "
    "wizard and have nobody the finishing screen accepts, or open to the wizard with an "
    "administrator already signing in. So both ask holds_everywhere, and it lives here."
)

#: Why the grants are administration and nothing else.
AN_ADMINISTRATOR_GOVERNS_THE_SYSTEM_AND_READS_NO_DATA: Final = (
    "A Super Admin runs the system: sign-ins, connectors, the stop button, budgets, routing. "
    "No role implies a capability, so each of those is written as a grant over everything. "
    "Reading the company's data is granted by its departments and its directory, and a first "
    "administrator created holding read over everything would be the widest data reach in the "
    "system, made by whoever held a setup code for an hour."
)

#: Why the first administrator reads how the system is run, and where that stops.
AN_ADMINISTRATOR_READS_HOW_THE_SYSTEM_IS_RUN_AND_NO_DATA: Final = (
    "Every console screen asks for its own read capability and for a plane, and a first "
    "administrator holding neither opened one screen of thirty-six. So the first administrator "
    "holds every screen's read at the existence and configuration planes and both of those "
    "planes, which says that a thing is there and how it is set up and never what is inside "
    "it. The content plane is withheld, so is every screen that needs it, and so is every "
    "approve verb, which decides somebody else's act rather than reading the system. The audit "
    "kinds that name a business record or an artefact are withheld too, for the reason "
    "brain.identity.staff_sync gives a department head: the ledger must not be the way round a "
    "scope over the data."
)

#: Why the first administrator holds the authority to grant, and not to approve an act.
THE_FIRST_ADMINISTRATOR_LETS_THE_SECOND_PERSON_IN: Final = (
    "approve:grant is the People screen's grant write, the Access review and elevation. Without "
    "it over everything nobody on a fresh install can grant anybody anything, and the only way "
    "to hand out a first reach is a statement at a database prompt, which is the thing the "
    "console exists to make unnecessary. A grant written with it is still bounded by what the "
    "writer holds and recorded by the grant trigger, and a grant somebody writes to themselves is "
    "a self-grant the console reports loudly. approve:action is not granted: it lets an agent "
    "act over data the first administrator cannot read, and approvals belong to whoever a "
    "department makes its approver."
)

#: Why a read the principal already holds does not refuse the appointment, when an administration
#: capability does.
AN_OVERSIGHT_READ_ALREADY_HELD_IS_KEPT: Final = (
    "A principal the directory sync made a department head already holds read:audit and three "
    "audit kinds at their department's scope. Refusing the appointment over that, as a held "
    "administration capability is refused, would make a head who finished the wizard after the "
    "first sync unappointable. So the read they hold is kept and theirs is not written: two "
    "grants of one capability intersect, so writing it would change nothing, and a read held "
    "narrower than everything is the conservative direction, where an administration capability "
    "held narrower is an administrator who is not one."
)

#: Why the count is taken under a lock.
THE_DOOR_IS_COUNTED_UNDER_A_LOCK: Final = (
    "Two appointments that each count administrators before either commits both count zero "
    "and both write, and the install has two first administrators, one of them a stranger's. "
    "The transaction-scoped advisory lock makes the second wait for the first to commit, and "
    "then its count sees the first administrator and it is refused."
)

#: Why the appointment is the last thing the wizard writes.
APPOINTING_IS_THE_LAST_WRITE: Final = (
    "Appointing an administrator closes the wizard on every screen. Written before the "
    "settings and the provider key, a failure between the two leaves an install the wizard "
    "refuses to reopen and nothing configured, so the caller writes everything apply_install "
    "returns first and appoints last."
)

#: Why the wizard's settings are written by this transaction and not beside it.
THE_SETTINGS_AND_THE_DOOR_CLOSE_IN_ONE_TRANSACTION: Final = (
    "Appointing closes the wizard on every screen, so settings written in a transaction of "
    "their own can fail after the door has shut, leaving an install that can neither be "
    "finished nor started again, and an appointment that commits alone closes the wizard over "
    "answers kept nowhere. Both halves of that are APPOINTING_IS_THE_LAST_WRITE, and one "
    "transaction is the only arrangement where neither can happen: the rows and the grants "
    "commit together or neither does."
)

#: Why a refusal names nobody.
AN_APPOINTMENT_REFUSED_NAMES_NOBODY: Final = (
    "Somebody holding an old setup code learns that the install has an administrator and "
    "never who it is, and a principal id that exists but is not live is refused in the same "
    "shape as every other refusal here, so the appointment is not a way to ask who is here."
)

# --------------------------------------------------------------------- the figures

#: The capability that binds a sign-in, and the one an administrator is recognised by.
SIGN_IN_AUTHORITY: Final = Capability(value="admin:sign_in")

#: Every administration capability the source declares, granted over everything. Held equal to
#: a scan of `src/brain` by a test. See `AN_ADMINISTRATOR_GOVERNS_THE_SYSTEM_AND_READS_NO_DATA`.
ADMINISTRATION: Final[tuple[str, ...]] = (
    "admin:agent_instructions",
    "admin:automation",
    "admin:budget",
    "admin:connector",
    "admin:credential",
    "admin:erasure",
    "admin:feature",
    "admin:export",
    "admin:field_classification",
    "admin:halt",
    "admin:learning",
    "admin:legal_hold",
    "admin:operations_alert",
    "admin:operations_incident",
    "admin:plugin",
    "admin:retention",
    "admin:routing_matrix",
    "admin:schedule",
    "admin:session",
    "admin:sign_in",
    "admin:skill",
    "admin:skill_review",
    "admin:storage",
    "admin:webhook_subscriber",
)

#: What a first administrator reads of how the system is run, granted over everything. Three
#: parts: every console screen's own read at the existence and configuration planes, the two plane
#: capabilities up to configuration, and the audit kinds not withheld in `AUDIT_KINDS_WITHHELD`.
#: Written out rather than derived, because this package must not import the console, and held
#: equal to `brain.console.screens` and `brain.audit.view` by a test. See
#: `AN_ADMINISTRATOR_READS_HOW_THE_SYSTEM_IS_RUN_AND_NO_DATA`.
OVERSIGHT: Final[tuple[str, ...]] = (
    "read:agent",
    "read:artifact",
    "read:audit",
    "read:audit.agent",
    "read:audit.connector",
    "read:audit.credential",
    "read:audit.erasure",
    "read:audit.grant",
    "read:audit.leash",
    "read:audit.legal_hold",
    "read:audit.principal",
    "read:audit.retention",
    "read:audit.routing",
    "read:audit.session",
    "read:audit.setting",
    "read:audit.skill",
    "read:audit.webhook",
    "read:backup",
    "read:budget",
    "read:capability",
    "read:connection_budget",
    "read:connector",
    "read:console.configuration",
    "read:console.existence",
    "read:denial_pattern",
    "read:document",
    "read:evaluation",
    "read:export",
    "read:grant",
    "read:incident",
    "read:knowledge_coverage",
    "read:model_route",
    "read:overview",
    "read:question",
    "read:queue",
    "read:rate_limit",
    "read:release",
    "read:retention_policy",
    "read:role",
    "read:run",
    "read:scope",
    "read:session",
    "read:skill",
    "read:staff_source",
    "read:usage",
)

#: The audit subject kinds a first administrator is not granted, and why. Every other kind in
#: `brain.audit.ledger.SUBJECT_KINDS` is in `OVERSIGHT`, and a test fails when a kind is in
#: neither, so a kind added to the ledger is decided about here rather than inherited.
AUDIT_KINDS_WITHHELD: Final[dict[str, str]] = {
    "entity": (
        "A merge entry names two business record ids, and the first administrator holds no scope "
        "over any business record, so this kind would be the id of every record in the company "
        "reached round the scope that decides who may see one."
    ),
    "artifact": (
        "A publish entry names an artefact id, and who may see an artefact is decided by "
        "brain.console.agent_output over what it was built from, which an audit grant never asks."
    ),
    "memory": (
        "A correction entry names a memory id, and who may know a memory exists is decided by "
        "brain.memory.formation.may_recall over the capabilities it was formed under, which an "
        "audit grant never asks."
    ),
}

#: The decisions over other people's reach a first administrator holds, over everything. One, on
#: purpose. See `THE_FIRST_ADMINISTRATOR_LETS_THE_SECOND_PERSON_IN`.
GOVERNANCE: Final[tuple[str, ...]] = ("approve:grant",)

#: Everything a first administrator is granted at appointment, and what reconciliation grants an
#: administrator appointed before part of it existed.
GRANTED_AT_APPOINTMENT: Final[tuple[str, ...]] = (*ADMINISTRATION, *GOVERNANCE, *OVERSIGHT)

#: The advisory lock every appointment takes. Its own number, not the ledger's.
FIRST_RUN_LOCK: Final = 8274419101

#: Every live principal's reach, from the one resolver. The policy hides deleted rows.
_EVERY_REACH: Final = text("SELECT gate.resolve_entitlements(p.id, :at) FROM auth.principal AS p")


class AppointmentRefusal(enum.StrEnum):
    """Why no first administrator was written. For the log, never for the person at the screen."""

    #: The grant handed in was not the one `firstrun.first_administrator` produces.
    NOT_FIRST_RUN = "not_first_run"
    #: An administrator already exists.
    ALREADY_ADMINISTERED = "already_administered"
    #: The principal id is held by somebody disabled, deleted or ended.
    NO_LIVE_PRINCIPAL = "no_live_principal"


class FirstAdministratorRefusedError(IdentityError):
    """No first administrator was written. The message names nobody."""

    def __init__(self, reason: AppointmentRefusal) -> None:
        self.reason = reason
        super().__init__(f"no first administrator was appointed: {reason.value}")


def holds_everywhere(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds `SIGN_IN_AUTHORITY` over everything, at this instant.

    Held in part of the company is not held. See `ONE_TEST_OF_AN_ADMINISTRATOR`.
    """
    scope = reach.scope_for(SIGN_IN_AUTHORITY, now)
    return scope is not None and scope.is_unrestricted()


def assert_bought_by_first_run(grant: RoleGrant) -> None:
    """Refuse a grant that is not the standing Super Admin grant first run produces.

    A guard against a caller passing the wrong grant, not against an adversary: anybody can
    construct a `RoleGrant`, and what stops a stranger is the setup code on the route and the
    count under the lock here.
    """
    if grant.granted_by != GRANTED_BY or grant.role is not Role.SUPER_ADMIN:
        raise FirstAdministratorRefusedError(AppointmentRefusal.NOT_FIRST_RUN)


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


@dataclass(frozen=True)
class FirstAdministrators:
    """`auth.principal` and `gate.capability_grant`, written once at first run."""

    sessions: async_sessionmaker[AsyncSession]

    async def _count(self, session: AsyncSession, now: datetime) -> int:
        payloads = (await session.execute(_EVERY_REACH, {"at": now})).scalars().all()
        return sum(1 for one in payloads if holds_everywhere(entitlements_from(one), now))

    async def administrators(self, now: datetime) -> int:
        """How many administrators this install has, for `apply_install` and never for a person."""
        async with self.sessions() as session, session.begin():
            return await self._count(session, now)

    async def appoint(
        self,
        grant: RoleGrant,
        *,
        display_name: str,
        trace_id: str = "",
        settings: Mapping[str, str] | None = None,
    ) -> None:
        """Write the first administrator the wizard's grant names, or raise why not.

        `grant` is `Applied.grant` from `apply_install`, and its `granted_at` is the instant the
        appointment is judged at. `display_name` is the name the administrator screen collected.
        See `APPOINTING_IS_THE_LAST_WRITE` for when to call it.

        `settings` are the installation values the same wizard produced, written into
        `ops.setting` inside this transaction so that the door and the configuration close
        together. See `THE_SETTINGS_AND_THE_DOOR_CLOSE_IN_ONE_TRANSACTION`. None means write
        none, which is what a caller with nothing to save passes and what every existing caller
        gets: the settings are the wizard's, and nothing else appoints.
        """
        assert_bought_by_first_run(grant)
        now = grant.granted_at
        principal_id = grant.principal_id
        # Constructed before any statement, so a name the type refuses writes nothing.
        Principal(
            id=principal_id,
            kind=PrincipalKind.HUMAN,
            employment=Employment.STAFF,
            display_name=display_name,
        )
        async with self.sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
            await session.execute(_set_config(ACTOR_SETTING, GRANTED_BY))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            # See THE_DOOR_IS_COUNTED_UNDER_A_LOCK.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": FIRST_RUN_LOCK}
            )
            if await self._count(session, now) != 0:
                raise FirstAdministratorRefusedError(AppointmentRefusal.ALREADY_ADMINISTERED)
            await session.execute(
                insert(PrincipalRow)
                .values(
                    id=principal_id,
                    kind=PrincipalKind.HUMAN.value,
                    employment=Employment.STAFF.value,
                    display_name=display_name,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            row = (
                (
                    await session.execute(
                        select(*COLUMNS).where(PrincipalRow.id == principal_id).with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            principal = None if row is None else readable(dict(row))
            if principal is None or not principal.is_active(now):
                raise FirstAdministratorRefusedError(AppointmentRefusal.NO_LIVE_PRINCIPAL)
            # After the last refusal and before the grants, so a refused appointment leaves no
            # configuration behind and an appointed one cannot be missing it.
            kept = await save_settings(session, settings or {}, updated_by=principal_id)
            everything = Scope.unrestricted().model_dump(mode="json")
            await session.execute(
                insert(CapabilityGrantRow).values(
                    [
                        {
                            "principal_id": principal_id,
                            "capability": capability,
                            "scope": everything,
                            "granted_by": GRANTED_BY,
                            "reason": GRANT_REASON,
                        }
                        for capability in (*ADMINISTRATION, *GOVERNANCE)
                    ]
                )
            )
            # A read the directory already granted this principal is kept at its own scope rather
            # than refusing the appointment. See `AN_OVERSIGHT_READ_ALREADY_HELD_IS_KEPT`.
            await session.execute(
                insert(CapabilityGrantRow)
                .values(
                    [
                        {
                            "principal_id": principal_id,
                            "capability": capability,
                            "scope": everything,
                            "granted_by": GRANTED_BY,
                            "reason": GRANT_REASON,
                        }
                        for capability in OVERSIGHT
                    ]
                )
                .on_conflict_do_nothing(
                    index_elements=["principal_id", "capability"],
                    index_where=text("deleted_at IS NULL"),
                )
            )
        log.info("first_administrator.appointed", principal=principal_id, settings=kept)
