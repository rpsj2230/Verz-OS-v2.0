"""A client leaving: everything they hold given back, then the install removed and shown to be.

M41.2.6 says a client who leaves must be able to take their data and leave nothing behind.
Both halves already have a per-person version in `brain.ops.erasure`, which assembles a
subject access request over every store and deletes with a certificate that does not lie
about backups. This is the same two acts at the other scale, and the difference in scale
changes exactly one thing, which is the whole reason this is a separate module rather than a
wider parameter on that one.

**A handover is not computed at a reach, and that is the permission surface.** The obvious
implementation is an export at somebody's entitlement: the departing administrator asks, and
the system gives them what they can see. That is wrong twice. It is too narrow, because
nobody's reach covers the audit ledger, so the client would leave without the record of who
asked what; and it is a disclosure, because a manifest computed at a reach is an inventory of
what exists as seen by one person, and the difference between two people's manifests is
precisely the set of things one of them may not see. An export is the one artefact never
re-checked, so that difference is permanent and portable.

So there is no principal here. No function in this module takes an `EntitlementSet`, no model
carries a reach, a principal id or an entitlement hash, and `handover_gaps` refuses any that
appear. What authorises a handover is not a person's grants: it is the installation's own
owner, named on a frozen request with a reason from a closed list and a reference to the
written instruction, the same shape `brain.ops.export.BulkExportRequest` uses and for the
same reason. See `A_HANDOVER_COMPUTED_AT_A_REACH_IS_AN_INVENTORY_OF_WHAT_SOMEBODY_CANNOT_SEE`.

**The return comes before the teardown, structurally.** `plan_teardown` will not construct a
plan from a return that did not reach every store, so there is no ordering a caller can get
wrong and no flag that skips the return. A deletion performed before the data was handed back
is not a handover: it is a deletion, and the client finds out which one it was afterwards.
See `A_TEARDOWN_BEFORE_A_RETURN_IS_A_DELETION_WITH_EXTRA_STEPS`.

**"Nothing behind" is bigger than the database.** `brain.ops.retention.Store` covers every
place a person's data comes to rest, and it is complete for what a deletion has to reach. It
is not complete for what an *install* leaves behind: a realm in the identity provider, a
bucket in the object store, secrets in the vault, a scheduled job, a proxy entry, an
environment file on the host. None of those is a store and all of them survive a database
being dropped. `Residue` is that list, iterated the same way `Store` is, so a certificate
cannot be issued while one is outstanding.

**Nothing here reaches anything.** Same split as `brain.ops.erasure`, and for the same
reason: the case that matters is the store that could not be reached, and a module holding a
database session could not be made to fail that way in a test. Every function takes what was
observed and returns what is wrong with it.

Task ids: M41.2.6
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Final

from brain.ops.erasure import (
    StoreHolding,
    backup_horizon,
    deletion_order,
)
from brain.ops.retention import DataClass, Store, data_class_of, facts_for


class HandoverError(Exception):
    """Raised when a handover would hand back less than everything, or delete before it did."""


# ------------------------------------------------------------------ written-down reasons
#: Why a handover has no principal on it anywhere.
A_HANDOVER_COMPUTED_AT_A_REACH_IS_AN_INVENTORY_OF_WHAT_SOMEBODY_CANNOT_SEE: Final = (
    "An export computed at somebody's entitlement is a list of what exists as seen by them, "
    "and two such lists differ by exactly the set one of them may not see. An export is also "
    "the one artefact this system never re-checks, so that difference leaves the building "
    "and stays true forever. A handover therefore has no reach at all: it is an act on the "
    "installation, authorised by whoever owns the installation, and the per-person question "
    "already has an answer in brain.ops.erasure.assemble, where it is asked about the person "
    "asking it."
)

#: Why the return has to have happened before the teardown can be planned.
A_TEARDOWN_BEFORE_A_RETURN_IS_A_DELETION_WITH_EXTRA_STEPS: Final = (
    "The order is the entire content of the promise. Data returned and then removed is a "
    "handover; data removed and then returned is a deletion followed by an apology, and the "
    "client discovers which one happened only afterwards. So the plan will not construct "
    "from an incomplete return, rather than the order being a step in a runbook somebody "
    "follows under time pressure on the last day of a contract."
)

#: Why the database is not the whole install.
A_DROPPED_DATABASE_IS_NOT_AN_UNINSTALL: Final = (
    "brain.ops.retention.Store is complete for where a person's data rests and is not "
    "complete for what an install leaves on somebody's infrastructure. A realm in the "
    "identity provider still authenticates, a bucket still holds objects, a vault still "
    "holds secrets that still open things, a scheduled job still fires, a proxy still routes "
    "a hostname. Every one of those survives dropping the database and none of them is a "
    "store, so a certificate that counted only stores would be true and would not mean what "
    "it is read to mean."
)

#: Why a certificate carries no claim of completeness.
A_CERTIFICATE_STATES_A_DATE_AND_NEVER_A_PROMISE: Final = (
    "The same argument brain.ops.erasure.Certificate makes: a boolean stamped at issue time "
    "is read as a promise about the future, and no deletion reaches inside a backup already "
    "written. So the certificate carries the date after which no surviving backup can "
    "contain the data, and there is no field on it that says complete."
)


class Reason(enum.StrEnum):
    """Why the installation is being handed over. A closed list, like `LawfulBasis`.

    Free text is where the name of a person, a dispute or a commercial term ends up, in a
    document that is filed and kept longer than the install was.
    """

    #: The contract ran to its end.
    CONTRACT_ENDED = "contract_ended"
    #: The client asked, inside the contract.
    CLIENT_REQUEST = "client_request"
    #: The same client, moving the install somewhere else.
    MIGRATION = "migration"


@dataclass(frozen=True)
class Handover:
    """One instruction to hand an installation back and remove it.

    Every field is required and none has a default, which is the structural version of the
    argument `brain.ops.export` makes about its own request object: validating a reason
    leaves a function that can be called without one, and a function that can be called
    without one will be.

    **There is deliberately no principal, no entitlement and no reach on this.** See
    `A_HANDOVER_COMPUTED_AT_A_REACH_IS_AN_INVENTORY_OF_WHAT_SOMEBODY_CANNOT_SEE`.
    """

    handover_id: str
    reason: Reason
    #: Who at the client instructed it, as the contract names them. An organisational role,
    #: not a login: this is the authority for the act, not a principal whose grants are read.
    instructed_by: str
    #: Where the written instruction is. A handover with no paper is one nobody can review.
    instruction_reference: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for name in ("handover_id", "instructed_by", "instruction_reference"):
            if not str(getattr(self, name)).strip():
                msg = f"a handover with no {name} cannot be reviewed after the fact"
                raise HandoverError(msg)
        if self.requested_at.tzinfo is None:
            msg = "a naive request time compares wrongly against an aware completion"
            raise HandoverError(msg)


@dataclass(frozen=True)
class Return:
    """Everything the installation holds, store by store, ready to be handed over.

    Built over every member of `Store`, with no predicate that could drop one, for the reason
    `brain.ops.erasure.SubjectAccess` gives about itself: a document that says "this is
    everything" and omits a store is false and looks complete.

    The sections are `brain.ops.erasure.StoreHolding` rather than a second model of the same
    shape. A store that could not be searched is named as not searched, which is an
    operational fact rather than a disclosure: there is no narrower principal here for it to
    disclose anything to. The disclosure rule is satisfied by this object having no reach at
    all, not by blurring "empty" into "unreachable".
    """

    handover: Handover
    at: datetime
    holdings: tuple[StoreHolding, ...]

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            msg = "a naive assembly time compares wrongly against an aware one"
            raise HandoverError(msg)
        covered = {one.store for one in self.holdings}
        if covered != set(Store):
            missing = sorted(store.value for store in set(Store) - covered)
            msg = (
                f"a return that omits {missing} says it is everything and is not; the client "
                "leaves without whatever those hold and nothing about the document looks wrong"
            )
            raise HandoverError(msg)

    @property
    def complete(self) -> bool:
        """Whether every store was actually read. Not whether anything was in them."""
        return all(one.reached for one in self.holdings)

    def unreached(self) -> tuple[Store, ...]:
        return tuple(one.store for one in self.holdings if not one.reached)

    @property
    def items(self) -> int:
        return sum(one.items for one in self.holdings)


def assemble_return(
    *,
    handover: Handover,
    at: datetime,
    found: Mapping[Store, int],
    unreachable: Iterable[Store] = (),
) -> Return:
    """Assemble the return over every store there is.

    Built by iterating `Store` rather than by iterating `found`, which is the difference
    between a document about the stores that exist and a document about the stores somebody
    remembered. A store in neither argument reported nothing, which is a legitimate answer and
    is recorded as zero.
    """
    if unknown := sorted(str(store) for store in set(found) - set(Store)):
        msg = f"a count was reported for {unknown}, which is not a store"
        raise HandoverError(msg)
    could_not = set(unreachable)
    holdings = tuple(
        StoreHolding(
            store=store,
            data_class=data_class_of(store),
            items=0 if store in could_not else found.get(store, 0),
            reached=store not in could_not,
            holds=facts_for(store).holds,
        )
        for store in Store
    )
    return Return(handover=handover, at=at, holdings=holdings)


class Residue(enum.StrEnum):
    """What an install leaves on somebody's infrastructure that is not a store.

    See `A_DROPPED_DATABASE_IS_NOT_AN_UNINSTALL`. Each member is here because it survives the
    database being dropped and goes on doing something: authenticating somebody, holding
    objects, opening a door, firing on a schedule, routing a hostname.
    """

    #: The realm, its clients and its users in the identity provider.
    IDENTITY_REALM = "identity_realm"
    #: The bucket or prefix in the object store, and the lifecycle rules on it.
    OBJECT_STORE = "object_store"
    #: Everything in the vault: connector credentials, signing keys, provider keys.
    VAULT_SECRETS = "vault_secrets"
    #: Scheduled jobs, timers and automations that still fire.
    SCHEDULED_WORK = "scheduled_work"
    #: The hostname, its DNS record, its certificate and the proxy route to it.
    NETWORK_ROUTE = "network_route"
    #: Containers, images and volumes on the host.
    RUNTIME = "runtime"
    #: The per-install environment file, which is the one artefact holding every value above.
    INSTALL_CONFIGURATION = "install_configuration"


def teardown_order() -> tuple[Store, ...]:
    """The order stores are removed in: sources before the copies made from them.

    `brain.ops.erasure.deletion_order` returned, not reimplemented. The rule is the same rule
    and a second copy of an ordering is a second place for it to be subtly wrong, which is
    the argument this repository makes about its central invariant and is no weaker here: the
    failure of getting it wrong is a cache repopulated from rows that were about to go.
    """
    return deletion_order()


@dataclass(frozen=True)
class TeardownPlan:
    """What removing this installation will do, in the order it will do it.

    Constructed only through `plan_teardown`, which is what enforces the ordering rule. The
    plan is a value rather than an executor, so the interesting case, a step that could not
    be completed, is expressible and testable.
    """

    handover: Handover
    stores: tuple[Store, ...]
    residue: tuple[Residue, ...]

    def __post_init__(self) -> None:
        if set(self.stores) != set(Store):
            missing = sorted(store.value for store in set(Store) - set(self.stores))
            msg = f"a teardown that never reaches {missing} leaves data behind"
            raise HandoverError(msg)
        if set(self.residue) != set(Residue):
            missing = sorted(one.value for one in set(Residue) - set(self.residue))
            msg = (
                f"a teardown that never reaches {missing} leaves the install behind. "
                f"{A_DROPPED_DATABASE_IS_NOT_AN_UNINSTALL}"
            )
            raise HandoverError(msg)


def plan_teardown(returned: Return) -> TeardownPlan:
    """The removal, planned from a return that actually happened.

    **Takes the return rather than the handover**, and that is the ordering rule expressed as
    a signature: there is no call that plans a teardown without a return in hand, and no
    argument that stands in for one. See
    `A_TEARDOWN_BEFORE_A_RETURN_IS_A_DELETION_WITH_EXTRA_STEPS`.
    """
    if not returned.complete:
        names = ", ".join(store.value for store in returned.unreached())
        msg = (
            f"{names} could not be read, so the client has not been given everything and a "
            f"teardown now would remove what they never received. "
            f"{A_TEARDOWN_BEFORE_A_RETURN_IS_A_DELETION_WITH_EXTRA_STEPS}"
        )
        raise HandoverError(msg)
    return TeardownPlan(handover=returned.handover, stores=teardown_order(), residue=tuple(Residue))


@dataclass(frozen=True)
class Removed:
    """One store or one residue, and what removing it did. A count, never the content."""

    #: The store, or the residue. One field rather than two, so a certificate cannot cover
    #: one list and quietly not the other.
    what: Store | Residue
    items: int
    #: False when the executor could not reach it. A certificate cannot be issued while any
    #: of these is False, which is why the field exists at all.
    completed: bool

    def __post_init__(self) -> None:
        if self.items < 0:
            msg = f"{self.what} reported a negative count"
            raise HandoverError(msg)
        if not self.completed and self.items:
            msg = (
                f"{self.what} was not completed and reports {self.items} item(s); one of "
                "those is not true and the count is the one that would be believed"
            )
            raise HandoverError(msg)

    @property
    def data_class(self) -> DataClass | None:
        """The class governing this, for a store. None for residue, which holds no rows."""
        return data_class_of(self.what) if isinstance(self.what, Store) else None


@dataclass(frozen=True)
class Certificate:
    """What was returned, what was removed, and the one date the client has to know.

    Read the field list as the argument. There is a handover, two timestamps, a count per
    store and per residue, and a date. There is no field for a value, a row, an excerpt or a
    sample, and there is no field that says "complete": see
    `A_CERTIFICATE_STATES_A_DATE_AND_NEVER_A_PROMISE`.

    `returned_items` is the number handed back and is not a count of anything withheld.
    Nothing was withheld: a handover has no reach, so there is no such quantity to report.
    """

    handover: Handover
    returned_at: datetime
    completed_at: datetime
    returned_items: int
    removed: tuple[Removed, ...]
    #: After this date no surviving backup can contain the data. A date, not a claim.
    recoverable_from_backup_until: datetime

    def __post_init__(self) -> None:
        covered = {one.what for one in self.removed}
        if covered != set(Store) | set(Residue):
            missing = sorted(str(one) for one in (set(Store) | set(Residue)) - covered)
            msg = f"a certificate that does not account for {missing} is not a certificate"
            raise HandoverError(msg)
        if self.completed_at < self.returned_at:
            msg = "this certificate says the install was removed before the data was returned"
            raise HandoverError(msg)

    def is_beyond_backup_reach(self, now: datetime) -> bool:
        """Whether every backup that could hold this data has rotated out, as of `now`."""
        return now >= self.recoverable_from_backup_until


def certify(returned: Return, *, removed: Sequence[Removed], completed_at: datetime) -> Certificate:
    """Issue a certificate for a handover that actually finished.

    **Refused while anything is outstanding**, which is the whole reason this is a function
    rather than a constructor call. A certificate is produced to be relied on, and one issued
    over a teardown that reached everything but the identity realm reads as saying the install
    is gone. The partial case already has a representation, which is the list of `Removed`
    itself; what must not exist is a certificate for it.
    """
    if not returned.complete:
        msg = "a certificate cannot be issued for a return that did not reach every store"
        raise HandoverError(msg)
    if outstanding := [one.what for one in removed if not one.completed]:
        names = ", ".join(sorted(str(one) for one in outstanding))
        msg = (
            f"{names} could not be removed, so this handover has not finished and a "
            "certificate for it would say it had"
        )
        raise HandoverError(msg)
    return Certificate(
        handover=returned.handover,
        returned_at=returned.at,
        completed_at=completed_at,
        returned_items=returned.items,
        removed=tuple(removed),
        recoverable_from_backup_until=backup_horizon(completed_at),
    )


# ------------------------------------------------------------------ the structural checks
#: Field names that would turn a certificate into a copy of what it handed over.
_CONTENT_NAMES: Final[frozenset[str]] = frozenset(
    {"value", "values", "content", "text", "body", "rows", "payload", "sample", "excerpt"}
)

#: Field and parameter names that would make a handover a view computed for one person.
#:
#: `principal_id` and `reach` are the two obvious ones. `ent_hash` is here because it is how
#: an entitlement is recorded everywhere else in this system, so it is the spelling somebody
#: reaches for when adding "which reach was this taken at" to a document.
_REACH_NAMES: Final[frozenset[str]] = frozenset(
    {"principal", "principal_id", "reach", "entitlement", "ent_hash", "caller", "as_principal"}
)

#: Words that would make a count into a report of what was withheld. There is nothing to
#: withhold here, so a field named for it would be a field somebody fills in from somewhere.
_WITHHELD_NAMES: Final[frozenset[str]] = frozenset(
    {"withheld", "hidden", "denied", "redacted", "omitted", "locked", "lock_count", "skipped"}
)

#: The models a handover could grow one of the above on.
HANDOVER_MODELS: Final[tuple[type, ...]] = (Handover, Return, TeardownPlan, Removed, Certificate)

#: The functions a reach could arrive through.
HANDOVER_SURFACE: Final[tuple[Any, ...]] = (
    assemble_return,
    plan_teardown,
    certify,
    teardown_order,
)


def handover_gaps(
    models: Sequence[type] = HANDOVER_MODELS,
    surface: Sequence[Any] = HANDOVER_SURFACE,
) -> tuple[str, ...]:
    """Everything about these types that would make a handover a permission decision.

    Three rules, scanned rather than trusted, because each of them dies the same way: one
    field or one argument added during a handover that was going badly, and never removed.
    """
    findings: list[str] = []
    for model in models:
        # `fields` wants a dataclass and mypy cannot see that every entry is one: the
        # parameter is a sequence of plain types so a test can pass a careless class in.
        for one in fields(model):
            lowered = one.name.lower()
            if lowered in _CONTENT_NAMES:
                findings.append(f"{model.__name__}.{one.name} could hold what was handed over")
            if lowered in _REACH_NAMES:
                findings.append(
                    f"{model.__name__}.{one.name} makes this a view computed for one person. "
                    f"{A_HANDOVER_COMPUTED_AT_A_REACH_IS_AN_INVENTORY_OF_WHAT_SOMEBODY_CANNOT_SEE}"
                )
            if lowered in _WITHHELD_NAMES:
                findings.append(
                    f"{model.__name__}.{one.name} counts what was not handed over, and a "
                    "count of what somebody did not receive is the disclosure this platform "
                    "refuses everywhere else"
                )
    for function in surface:
        signature = inspect.signature(function)
        for name, parameter in signature.parameters.items():
            annotation = str(parameter.annotation)
            if name.lower() in _REACH_NAMES or "EntitlementSet" in annotation:
                findings.append(
                    f"{function.__name__}({name}) takes a reach, so a handover would differ "
                    "by who asked for it"
                )
    return tuple(findings)
