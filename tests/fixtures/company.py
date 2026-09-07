"""A synthetic company, built to break things.

Every permission test from here on runs against this. It is deliberately not a tidy org
chart: the interesting cases are the ones a real company produces and a clean fixture
never does — the contractor whose access expires, the person who sits in two departments,
the one mid-transfer who still holds grants in the department they left.

Three ideas make this fixture do real work.

**Canary values.** Every restricted field holds an improbable string, not a plausible
number. A contract value of 48000 leaking into an answer looks like data; a contract value
of ``CANARY-CONTRACT-7Q4XZ`` leaking is unmistakable, greppable, and cannot be confused
with something the model invented. A test can then assert on the absence of a token rather
than on the shape of an answer.

**Personas defined by what they must NOT see.** `sees_record_not_money` and `sees_neither`
exist because "can Aaron see this client" is the easy half. The half that catches bugs is
"Wei Ling can see the client and must never see its contract value", which is exactly the
locked field on screen 3.

**Nothing is granted twice.** Grants are listed once, per person, in one place. A fixture
that builds entitlements through a helper with defaults hides the thing under test.

Task ids: M0.6.1, M0.6.2, M0.6.3, M0.6.7
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope

#: Fixed so tests are deterministic. Everything relative to it, never to "now".
NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

DEPARTMENTS = ("maintenance", "web", "sales", "finance")

#: Improbable on purpose. If one of these appears in an answer it did not come from the
#: model's imagination and it did not come from a plausible-looking test row: it leaked.
CANARIES: dict[str, str] = {
    "client.contract_value": "CANARY-CONTRACT-7Q4XZ",
    "client.margin": "CANARY-MARGIN-J2WPL",
    "hr.salary": "CANARY-SALARY-M8VTK",
    "hr.performance_note": "CANARY-PERF-R3NDQ",
    "ticket.internal_note": "CANARY-TICKET-B6YHF",
    "invoice.amount_due": "CANARY-INVOICE-Z9KRT",
    "agent.system_prompt": "CANARY-PROMPT-D4LSW",
}


def canary_tokens() -> frozenset[str]:
    """Every canary. A test asserts none of these reach a principal without the grant."""
    return frozenset(CANARIES.values())


def cap(value: str) -> Capability:
    return Capability(value=value)


def dept(name: str) -> Scope:
    return Scope.department(name)


def dept_in(*names: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.IN, value=tuple(names)),))


@dataclass(frozen=True)
class Person:
    """A principal plus the grants they hold, and — the useful part — what they must not
    reach. `forbidden` is asserted directly by the canary tests."""

    principal: Principal
    grants: tuple[Grant, ...]
    note: str
    forbidden: tuple[str, ...] = field(default_factory=tuple)

    def entitlement(self) -> EntitlementSet:
        # not_after travels from the principal into the entitlement, which is where it is
        # enforced. Building the set without it is exactly the bug these canaries found.
        return EntitlementSet(
            principal_id=self.principal.id,
            grants=self.grants,
            not_after=self.principal.not_after,
        )


def _staff(pid: str, name: str, department: str) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=name,
        primary_department=department,
    )


def build_company() -> dict[str, Person]:
    """Twelve people across four departments. Keyed by id."""
    people: list[Person] = [
        # --- Super Admin ------------------------------------------------
        Person(
            principal=_staff("u_rupash", "Rupash Kumar", "maintenance"),
            grants=(
                Grant(capability=cap("admin:grant"), scope=Scope.unrestricted()),
                Grant(capability=cap("read:client.*"), scope=Scope.unrestricted()),
                Grant(capability=cap("read:ticket.*"), scope=Scope.unrestricted()),
                Grant(capability=cap("invoke:agent"), scope=Scope.unrestricted()),
            ),
            note="Super Admin. Wide, but still a grant set — there is no bypass flag.",
            # An admin who can grant themselves anything is still not born holding it.
            forbidden=("hr.salary",),
        ),
        # --- Department Admins ------------------------------------------
        Person(
            principal=_staff("u_aaron", "Aaron Lim", "maintenance"),
            grants=(
                Grant(capability=cap("read:client.*"), scope=dept("maintenance")),
                Grant(capability=cap("read:ticket.*"), scope=dept("maintenance")),
                Grant(capability=cap("approve:envelope"), scope=dept("maintenance")),
                Grant(capability=cap("invoke:agent"), scope=dept("maintenance")),
            ),
            note="Department Admin, Maintenance. Wide inside one department only.",
            forbidden=("hr.salary", "invoice.amount_due"),
        ),
        Person(
            principal=_staff("u_siti", "Siti Rahman", "web"),
            grants=(
                Grant(capability=cap("read:client.*"), scope=dept("web")),
                Grant(capability=cap("approve:envelope"), scope=dept("web")),
                Grant(capability=cap("invoke:agent"), scope=dept("web")),
            ),
            note="Department Admin, Web.",
            forbidden=("hr.salary", "ticket.internal_note"),
        ),
        # --- the personas that catch bugs -------------------------------
        Person(
            principal=_staff("u_weiling", "Wei Ling Tan", "maintenance"),
            grants=(
                Grant(capability=cap("read:client.name"), scope=dept("maintenance")),
                Grant(capability=cap("read:client.hosting_expiry"), scope=dept("maintenance")),
                Grant(capability=cap("read:client.hours_remaining"), scope=dept("maintenance")),
                Grant(capability=cap("read:ticket.status"), scope=dept("maintenance")),
                Grant(capability=cap("invoke:agent"), scope=dept("maintenance")),
            ),
            note="sees-record-not-money. The locked field on screen 3, as a fixture.",
            forbidden=("client.contract_value", "client.margin", "hr.salary"),
        ),
        Person(
            principal=_staff("u_jason", "Jason Ng", "web"),
            grants=(Grant(capability=cap("invoke:agent"), scope=dept("web")),),
            note="sees-neither. Can call an agent and reach almost nothing through it.",
            forbidden=(
                "client.contract_value",
                "client.margin",
                "hr.salary",
                "ticket.internal_note",
                "invoice.amount_due",
            ),
        ),
        # --- the awkward employment shapes ------------------------------
        Person(
            principal=Principal(
                id="u_contractor",
                kind=PrincipalKind.HUMAN,
                employment=Employment.CONTRACTOR,
                display_name="Marcus Devlin",
                primary_department="web",
                not_after=NOW + timedelta(days=30),
            ),
            grants=(
                Grant(capability=cap("read:client.name"), scope=dept("web")),
                Grant(capability=cap("invoke:agent"), scope=dept("web")),
            ),
            note="Contractor with a live expiry. Still inside it.",
            forbidden=("client.contract_value", "hr.salary"),
        ),
        Person(
            principal=Principal(
                id="u_expired",
                kind=PrincipalKind.HUMAN,
                employment=Employment.CONTRACTOR,
                display_name="Elena Farrow",
                primary_department="web",
                not_after=NOW - timedelta(days=1),
            ),
            grants=(
                # Grants still on file. Expiry must beat them, and it is checked when the
                # entitlement is built, not when the session opened.
                Grant(capability=cap("read:client.*"), scope=dept("web")),
                Grant(capability=cap("invoke:agent"), scope=dept("web")),
            ),
            note="Contractor whose expiry has passed. Grants intact, access must not be.",
            forbidden=("client.name", "client.contract_value"),
        ),
        Person(
            principal=Principal(
                id="u_partner",
                kind=PrincipalKind.HUMAN,
                employment=Employment.PARTNER,
                display_name="Priya Nair",
                primary_department="sales",
                not_after=NOW + timedelta(days=90),
            ),
            grants=(
                Grant(
                    capability=cap("read:client.name"),
                    scope=Scope(
                        clauses=(
                            Clause(field="department", op=Op.EQ, value="sales"),
                            Clause(field="partner_visible", op=Op.EQ, value="true"),
                        )
                    ),
                ),
            ),
            note="Partner. Two-clause scope: the second is what a single-clause bug drops.",
            forbidden=("client.contract_value", "hr.salary", "ticket.internal_note"),
        ),
        Person(
            principal=_staff("u_dual", "Daniel Ong", "sales"),
            grants=(
                Grant(capability=cap("read:client.name"), scope=dept_in("sales", "web")),
                Grant(capability=cap("read:client.contract_value"), scope=dept("sales")),
                Grant(capability=cap("invoke:agent"), scope=dept_in("sales", "web")),
            ),
            note=(
                "Two departments, unequal depth. Sees contract value in sales and not in "
                "web — a per-field, per-scope difference within one person."
            ),
            forbidden=("hr.salary",),
        ),
        Person(
            principal=_staff("u_transfer", "Grace Teo", "finance"),
            grants=(
                Grant(capability=cap("read:invoice.*"), scope=dept("finance")),
                # Residue from the department she left. Present on purpose: this is what
                # a joiners-movers-leavers report has to find.
                Grant(capability=cap("read:client.name"), scope=dept("web")),
                Grant(capability=cap("invoke:agent"), scope=dept("finance")),
            ),
            note="Mid-transfer. Holds a stale grant in her previous department.",
            forbidden=("hr.salary", "client.contract_value"),
        ),
        Person(
            principal=_staff("u_hr", "Meera Pillai", "finance"),
            grants=(
                Grant(
                    capability=cap("read:hr.*"),
                    scope=dept_in("maintenance", "web", "sales", "finance"),
                ),
                Grant(capability=cap("invoke:agent"), scope=dept("finance")),
            ),
            note="The only person who may read salary. Everyone else's forbidden list.",
            forbidden=("client.contract_value",),
        ),
        Person(
            principal=Principal(
                id="svc_sentinel",
                kind=PrincipalKind.SERVICE,
                employment=Employment.SERVICE,
                display_name="Site Health Sentinel (scheduled)",
                primary_department="maintenance",
            ),
            grants=(
                Grant(capability=cap("read:client.hosting_expiry"), scope=dept("maintenance")),
                Grant(capability=cap("read:client.domain_expiry"), scope=dept("maintenance")),
            ),
            note=(
                "Scheduled work runs as a principal like any other. Deliberately not "
                "called 'system': there is no principal that bypasses the gate."
            ),
            forbidden=("client.contract_value", "client.name", "hr.salary"),
        ),
    ]
    return {p.principal.id: p for p in reaching_their_own_rows(people)}


def record_grants(held: Sequence[Grant]) -> tuple[Grant, ...]:
    """The `read:<entity>` grants implied by a set of `read:<entity>.<field>` grants.

    **Reaching a row and reading a column are two separate grants**, and
    `brain.knowledge.rows.entity_capability` is explicit that `Capability.covers` deliberately
    does not let `read:client.*` confer `read:client`. That separation is what lets the scope
    on the row grant be the WHERE clause while the field grants are the SELECT list, and it is
    a good design.

    This fixture granted columns and never records, so `row_scope_for` answered None for every
    persona and `compile_row_query` short-circuited to a statement it already knew was empty.
    Nobody in the company could read anything. It went unnoticed because the tests of this
    corpus check the corpus's own shape, and every row-plane test builds its entitlement
    inline rather than taking a persona, so the fixture and the row plane were never in one
    test until `tests/invariants/test_golden_through_the_gate.py` on 2026-09-07. Measured
    afterwards: all twenty golden questions produced one identical answer stream, so the
    harness's canary check passed because no answer ever contained data.

    **Derived rather than written out**, so a persona given a new field grant reaches the rows
    it is about without anybody remembering this function exists. A field grant with no record
    grant is dead configuration: the column could never be selected, so the grant could never
    be exercised.

    **One record grant per field grant, at that field grant's own scope**, and the narrowing
    that produces is `EntitlementSet.scope_for`'s rather than this function's: several grants
    of one capability intersect there, deliberately, because holding a capability twice must
    never be wider than holding it once.

    That matters for the person this fixture exists to make awkward. `u_dual` holds
    `read:client.name` across sales and web and `read:client.contract_value` in sales alone.
    The intersection scopes their row grant to sales, and `compile_projection` then admits
    both columns, because a column grant narrower than the row grant would be a per-row column
    decision it refuses to make. Measured rather than reasoned: with the row grant at the
    wider scope the projection is `('name',)` and the contract value is absent everywhere,
    which is not the person the corpus describes.
    """
    implied: list[Grant] = []
    for grant in held:
        verb, _, rest = grant.capability.value.partition(":")
        entity, dot, _field = rest.partition(".")
        # No branch for a wildcard entity, and that is checked rather than assumed:
        # `Capability` refuses `read:*.name` outright, so `entity` can never be `*` here and a
        # guard for it would be a branch no mutation could reach. `read:*` has no dot and is
        # skipped by the first condition.
        if not dot or not entity:
            continue
        implied.append(Grant(capability=cap(f"{verb}:{entity}"), scope=grant.scope))
    return tuple(implied)


def reaching_their_own_rows(people: Sequence[Person]) -> list[Person]:
    """Every person, with the record grants their field grants imply.

    Applied here rather than inside `Person.entitlement`, so `Person.grants` and the
    entitlement built from it hold the same set. A derivation visible through only one of the
    two would be a fixture whose grants disagree with its own reach, which is a smaller
    version of the thing this function was written to remove.
    """
    return [
        Person(
            principal=one.principal,
            grants=(*one.grants, *record_grants(one.grants)),
            note=one.note,
            forbidden=one.forbidden,
        )
        for one in people
    ]


def everyone() -> dict[str, Person]:
    return build_company()


def person(pid: str) -> Person:
    return build_company()[pid]
