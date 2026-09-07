"""A fictitious company a new install can be shown working against on its first day.

M41.2.2 asks for a generic demo seed and then says the part that decides everything about
this module: **deliberately not the Verz test fixture.** The obvious implementation is to
point the seed at `tests/fixtures/company.py`, which already describes a company, already
loads, and is already trusted. It is the wrong artefact and the wrongness runs both ways.

**A demo built from the test fixture ships canaries to a client.** Every restricted field in
that fixture holds an improbable token, `CANARY-CONTRACT-7Q4XZ` and six more, because a test
asserts that none of them ever reaches somebody without the grant. Those tokens are the
fixture doing its job. In a demo they are a client's first screen reading like a corrupted
database, and worse, they are greppable strings whose absence a test depends on: a client who
edits one has quietly weakened the permission suite of the product they bought.

**And a test fixture built to demo well stops catching bugs.** The fixture is deliberately
untidy. It carries a contractor whose access has already lapsed, a person mid-transfer who
still holds grants in the department they left, and a persona whose whole reason to exist is
that she may see a client and may never see what it is worth. That is what makes the
permission tests sharp, and it is exactly what nobody wants on the screen they are shown to
decide whether to buy this. Sharing one artefact would mean each of them getting the half the
other needs, so there are two, and the differences are asserted rather than described:
`tests/unit/test_demo.py` holds the two apart on canaries, on identifiers and on departments.

**Nothing here is an administrator, and no grant here is unrestricted.** A demo that arrives
holding a super admin is an account nobody created, with the widest reach in the system, whose
credentials are whatever the seed decided. That is the failure `brain.firstrun` exists to
prevent, so the demo stops short of it: the widest thing in this file is a department admin,
and the first administrator is created by a person at first run. See
`A_DEMO_THAT_SHIPS_AN_ADMINISTRATOR_SHIPS_AN_ACCOUNT_NOBODY_CREATED`.

**Every identifier carries one prefix, so the demo can be removed.** A client who has finished
looking must be able to take it out, and "delete the demo" has to be a decidable question
rather than an archaeology exercise. Everything this module writes is prefixed, and
`demo_gaps` refuses an identifier that is not: see
`A_DEMO_NOBODY_CAN_REMOVE_BECOMES_PRODUCTION_DATA`.

**No values from anywhere real.** The addresses are on a domain reserved for documentation,
which is what makes `brain.ops.independence` able to pass over them, and the company, its
departments, its people and its records are invented. This module is read by
`brain.ops.independence` like every other file under `src`, which is the point: a demo is
product, so it is held to the product's rule about client values rather than exempted from it.

Task ids: M41.2.2
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from brain.core.entitlement import Capability, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope

# ------------------------------------------------------------------ written-down reasons
#: Why this is a second artefact rather than the test fixture under another name.
A_DEMO_AND_A_TEST_FIXTURE_WANT_OPPOSITE_THINGS: Final = (
    "A test fixture is built to be improbable: canary strings instead of values, a lapsed "
    "contractor, a person mid-transfer, and a persona defined by what she must never see. A "
    "demo is built to be ordinary, because it is what somebody is shown to decide whether "
    "the product works. Sharing one artefact gives each of them the half the other needs: "
    "the client sees canaries and the permission suite loses the personas that catch bugs."
)

#: Why the demo stops short of an administrator.
A_DEMO_THAT_SHIPS_AN_ADMINISTRATOR_SHIPS_AN_ACCOUNT_NOBODY_CREATED: Final = (
    "An administrator that arrives with the seed is an account with the widest reach in the "
    "system, created by nobody, whose credential is whatever the seed decided. That is the "
    "same object as a default password and it fails for the same reason. So the widest "
    "principal here is a department admin, and the first administrator is created by a "
    "person at first run, through brain.firstrun, against a token that cannot be replayed."
)

#: Why every identifier carries a prefix.
A_DEMO_NOBODY_CAN_REMOVE_BECOMES_PRODUCTION_DATA: Final = (
    "A client finishes looking at the demo in the first week and lives with the install for "
    "years. If removing it means deciding row by row which people were invented, nobody "
    "removes it, and a fictitious company sits inside a real one's data being counted, "
    "searched and answered from. So every identifier this module writes carries one prefix "
    "and removal is a predicate rather than an inventory."
)

#: Why no grant here is unrestricted.
AN_UNRESTRICTED_GRANT_IN_A_DEMO_IS_A_DEMO_OF_THE_WRONG_PRODUCT: Final = (
    "The thing worth showing on the first day is that two people asking one question get two "
    "answers. A demo whose people all hold unrestricted scope shows a system that answers "
    "everything to everybody, which is what every other product already does. Every grant "
    "here is bounded to a department for that reason, and demo_gaps refuses one that is not."
)

# ------------------------------------------------------------------ the company
#: The prefix on every identifier this module writes. One string, so removal is a predicate.
DEMO_PREFIX: Final = "demo_"

#: The domain the demo's people are reachable at. Reserved by RFC 2606 for documentation, so
#: it can never become a real company's and `brain.ops.independence` can pass over it.
DEMO_DOMAIN: Final = "northwind.example"

#: What the demo calls itself on screen. Not read from `brain.install`: this is the name of
#: the fictitious company inside the demo data, not the name of the client running the
#: install, and conflating the two would put the client's own name on invented invoices.
DEMO_COMPANY: Final = "Northwind Facilities"

#: The source name projected demo records are filed under. `demo` rather than a connector's
#: name, because these rows came from nobody: filing them under `freshdesk` would make a
#: staleness figure a claim about a system this install has never contacted.
DEMO_SOURCE: Final = "demo"

#: Fixed so the demo is byte-identical on every install. Everything dated is relative to it,
#: never to "now", for the reason the test fixture pins its own clock: a seed whose contents
#: depend on the hour it ran cannot be compared between two installs.
SEEDED_AT: Final = datetime(2026, 1, 6, 9, 0, tzinfo=UTC)

#: Four departments, none of them named after a real company's. Deliberately not the test
#: fixture's four, so a test asserting the two are different has something to compare.
DEPARTMENTS: Final[tuple[str, ...]] = ("operations", "projects", "accounts", "people")

#: The principal the demo's grants are recorded as coming from. A service principal that
#: exists in the seed rather than a name nobody can look up: `granted_by` is not nullable and
#: a grant attributed to a principal that does not exist is a ledger entry nobody can follow.
GRANTED_BY: Final = f"{DEMO_PREFIX}seed"

#: What the reason column says. Required and not nullable, so it says something true.
GRANT_REASON: Final = "seeded with the demo company; remove with the demo"

#: A canary is an improbable token in a value position. Recognised by shape rather than by
#: listing the seven the fixture happens to hold today, because the eighth is the one that
#: would reach a client. See `A_DEMO_AND_A_TEST_FIXTURE_WANT_OPPOSITE_THINGS`.
#:
#: **Three segments, and one of them mixing letters with digits.** The first version was
#: `[A-Z]{3,}-[A-Z0-9]{4,}` and it reported `INV-10233`, which is an invoice reference and
#: exactly the kind of ordinary value a demo is made of. What separates the two is not
#: capitals and a hyphen, which every reference number has: it is the third segment and the
#: deliberately unpronounceable tail, `CANARY-CONTRACT-7Q4XZ` against `INV-10233`.
CANARY_SHAPED = re.compile(r"\b[A-Z0-9]{2,}-[A-Z0-9]{2,}-[A-Z0-9]*(?:[A-Z]\d|\d[A-Z])[A-Z0-9]*\b")


@dataclass(frozen=True)
class DemoPerson:
    """One invented member of staff, their department, and what they may read.

    There is no `forbidden` field and that absence is the shape of the whole module. The
    fixture carries one because a test asserts against it; a demo carrying one would be a
    list, shipped to a client, of what their own screens are meant to withhold.
    """

    principal: Principal
    grants: tuple[Grant, ...]
    #: What this person does, for the tour. Shown beside them on the demo screen.
    role: str

    @property
    def address(self) -> str:
        """Where this person is reachable, derived rather than stored.

        Derived so that an address cannot disagree with an identifier, which is the way a
        seeded directory goes wrong: somebody edits one of the two and the other goes on
        being matched against.
        """
        local = self.principal.id.removeprefix(DEMO_PREFIX).replace("_", ".")
        return f"{local}@{DEMO_DOMAIN}"


@dataclass(frozen=True)
class DemoRecord:
    """One projected record: a client, a job or an invoice the demo can be asked about.

    `fields` is a plain mapping held to `brain.core.projection`'s rules by the same check
    every projected record is, rather than by being trusted for having been written here.
    """

    entity: str
    source_id: str
    department: str
    fields: Mapping[str, str]


@dataclass(frozen=True)
class DemoRule:
    """One fast-path rule, so the demo can answer a question with no model in the loop.

    This is what makes the demo an install that *works* rather than one that holds rows. The
    lane behind it reads `proj.record` under a role that reaches projected tables and nothing
    else, so a demo question is answered by the narrowest path the system has.
    """

    rule_id: str
    template: str
    slot: str
    entity: str
    match_field: str
    answer_field: str


def _person(identifier: str, name: str, department: str, role: str) -> Principal:
    return Principal(
        id=f"{DEMO_PREFIX}{identifier}",
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=name,
        primary_department=department,
    )


def _grant(capability: str, department: str) -> Grant:
    return Grant(capability=Capability(value=capability), scope=Scope.department(department))


def record_grants(held: Sequence[Grant]) -> tuple[Grant, ...]:
    """The `read:<entity>` grants implied by a set of `read:<entity>.<field>` grants.

    **Reaching a row and reading a column are two separate grants.**
    `brain.knowledge.rows.entity_capability` is explicit that `Capability.covers` deliberately
    does not let `read:client.*` confer `read:client`, and that separation is the design: the
    scope on the record grant becomes the WHERE clause while the field grants become the
    SELECT list.

    **This demo granted columns and never records, so nobody in it could reach a single row.**
    `row_scope_for` answered None for every person, `compile_row_query` short-circuited to a
    statement it already knew was empty, and the fast-path filter on `name` was refused as
    outside the projection. Measured on 2026-09-08 while writing
    `tests/invariants/test_wave_one_is_live.py`, which is the first test that ever put the
    demo's people and the row plane in one place.

    It went unnoticed because `brain.seed.ask` answers from the rules and records directly
    with no caller at all, so the install-from-empty job proved a question could be answered
    and never that a person could ask it. `tests/fixtures/company.py` had the identical bug
    and the identical cause a day earlier; that is two of two, which is an argument for this
    being derived rather than remembered.

    **One grant per entity, scopes intersected here rather than at read time.** The unique
    index `uq_capability_grant_principal_id_capability_live` is on principal and capability
    with no scope column, so a person may hold one live grant of a capability and no more.
    Emitting one record grant per field grant is correct in memory and unstorable.
    """
    scopes: dict[str, Scope] = {}
    order: list[str] = []
    for grant in held:
        verb, _, rest = grant.capability.value.partition(":")
        entity, dot, _field = rest.partition(".")
        if not dot or not entity:
            continue
        record = f"{verb}:{entity}"
        if record not in scopes:
            scopes[record] = grant.scope
            order.append(record)
        else:
            scopes[record] = scopes[record].intersect(grant.scope)
    return tuple(Grant(capability=Capability(value=one), scope=scopes[one]) for one in order)


def build_people() -> tuple[DemoPerson, ...]:
    """Eight invented people across four departments, and the service principal.

    Eight rather than the fixture's twelve, and the difference is not arithmetic: four of the
    fixture's twelve exist only to be edge cases, and an edge case is not what a demo is for.
    """
    people: list[DemoPerson] = [
        DemoPerson(
            principal=_person("ops_lead", "Iris Calder", "operations", "Operations lead"),
            grants=(
                _grant("read:client.*", "operations"),
                _grant("read:job.*", "operations"),
                _grant("approve:envelope", "operations"),
                _grant("invoke:agent", "operations"),
            ),
            role="Department admin, Operations",
        ),
        DemoPerson(
            principal=_person("ops_scheduler", "Tomas Berg", "operations", "Scheduler"),
            grants=(_grant("read:job.*", "operations"), _grant("invoke:agent", "operations")),
            role="Schedules the week's visits",
        ),
        DemoPerson(
            principal=_person("ops_engineer", "Nadia Faber", "operations", "Field engineer"),
            grants=(_grant("read:job.summary", "operations"),),
            role="On site, reads the job and nothing round it",
        ),
        DemoPerson(
            principal=_person("projects_lead", "Owen Marsh", "projects", "Projects lead"),
            grants=(
                _grant("read:client.*", "projects"),
                _grant("read:job.*", "projects"),
                _grant("approve:envelope", "projects"),
                _grant("invoke:agent", "projects"),
            ),
            role="Department admin, Projects",
        ),
        DemoPerson(
            principal=_person("projects_coord", "Sanne Vos", "projects", "Coordinator"),
            grants=(_grant("read:client.name", "projects"), _grant("invoke:agent", "projects")),
            role="Sees which clients, never what they are worth",
        ),
        DemoPerson(
            principal=_person("accounts_lead", "Priya Raman", "accounts", "Accounts lead"),
            grants=(
                _grant("read:client.*", "accounts"),
                _grant("read:invoice.*", "accounts"),
                _grant("invoke:agent", "accounts"),
            ),
            role="Department admin, Accounts",
        ),
        DemoPerson(
            principal=_person("accounts_clerk", "Hugo Lantz", "accounts", "Accounts clerk"),
            grants=(_grant("read:invoice.status", "accounts"), _grant("invoke:agent", "accounts")),
            role="Chases what is unpaid, sees no margin",
        ),
        DemoPerson(
            principal=_person("people_lead", "Ada Okonjo", "people", "People lead"),
            grants=(_grant("read:person.*", "people"), _grant("invoke:agent", "people")),
            role="Department admin, People",
        ),
    ]
    # The record grants their field grants imply, added here rather than written beside each
    # person. See `record_grants`: without them nobody in this demo could reach a single row,
    # which is what it was until 2026-09-08.
    return tuple(
        DemoPerson(
            principal=one.principal,
            grants=one.grants + record_grants(one.grants),
            role=one.role,
        )
        for one in people
    )


def build_service_principal() -> Principal:
    """The principal the demo's grants are attributed to.

    A service principal rather than a person, because nobody appointed these grants and a
    seed pretending a named person did would be the one false statement in the demo.
    """
    return Principal(
        id=GRANTED_BY,
        kind=PrincipalKind.SERVICE,
        employment=Employment.SERVICE,
        display_name="Demo seed",
        primary_department=None,
    )


def build_records() -> tuple[DemoRecord, ...]:
    """Clients, jobs and invoices, with ordinary values in every field.

    Ordinary is the requirement. A demo whose money column reads `CANARY-CONTRACT-7Q4XZ`
    demonstrates a broken import, and a demo whose money column is missing demonstrates
    nothing at all, because the field two people see differently is the product.
    """
    return (
        DemoRecord(
            entity="client",
            source_id=f"{DEMO_PREFIX}client_ashgrove",
            department="operations",
            fields={
                "name": "Ashgrove Retail Group",
                "status": "active",
                "since": "2021-03-01",
                "contract_value": "184000",
                "account_manager": "Iris Calder",
            },
        ),
        DemoRecord(
            entity="client",
            source_id=f"{DEMO_PREFIX}client_brightpier",
            department="projects",
            fields={
                "name": "Brightpier Hotels",
                "status": "active",
                "since": "2023-11-14",
                "contract_value": "97500",
                "account_manager": "Owen Marsh",
            },
        ),
        DemoRecord(
            entity="client",
            source_id=f"{DEMO_PREFIX}client_calderwood",
            department="accounts",
            fields={
                "name": "Calderwood Estates",
                "status": "dormant",
                "since": "2019-06-20",
                "contract_value": "42000",
                "account_manager": "Priya Raman",
            },
        ),
        DemoRecord(
            entity="job",
            source_id=f"{DEMO_PREFIX}job_2411",
            department="operations",
            fields={
                "summary": "Quarterly plant inspection, Ashgrove distribution centre",
                "status": "scheduled",
                "client": "Ashgrove Retail Group",
                "due": "2026-01-19",
            },
        ),
        DemoRecord(
            entity="job",
            source_id=f"{DEMO_PREFIX}job_2418",
            department="projects",
            fields={
                "summary": "Lobby refit, Brightpier waterfront",
                "status": "in_progress",
                "client": "Brightpier Hotels",
                "due": "2026-02-27",
            },
        ),
        DemoRecord(
            entity="invoice",
            source_id=f"{DEMO_PREFIX}invoice_10233",
            department="accounts",
            fields={
                "reference": "INV-10233",
                "status": "unpaid",
                "client": "Ashgrove Retail Group",
                "amount_due": "12400",
                "due": "2026-01-31",
            },
        ),
        DemoRecord(
            entity="invoice",
            source_id=f"{DEMO_PREFIX}invoice_10241",
            department="accounts",
            fields={
                "reference": "INV-10241",
                "status": "paid",
                "client": "Brightpier Hotels",
                "amount_due": "8150",
                "due": "2025-12-15",
            },
        ),
    )


def build_rules() -> tuple[DemoRule, ...]:
    """The questions the demo can answer with no model in the loop.

    Three, one per entity, so the first question somebody types on a fresh install is
    answered by the fast lane rather than by an inference server the install may not run.
    """
    return (
        DemoRule(
            rule_id=f"{DEMO_PREFIX}client_status",
            template="what is the status of {client}",
            slot="client",
            entity="client",
            match_field="name",
            answer_field="status",
        ),
        DemoRule(
            rule_id=f"{DEMO_PREFIX}job_status",
            template="what is the status of job {job}",
            slot="job",
            entity="job",
            match_field="client",
            answer_field="status",
        ),
        DemoRule(
            rule_id=f"{DEMO_PREFIX}invoice_status",
            template="is invoice {invoice} paid",
            slot="invoice",
            entity="invoice",
            match_field="reference",
            answer_field="status",
        ),
    )


# ------------------------------------------------------------------ rows
#: The tables the demo writes, in the order it writes them. Principals before grants because
#: a grant carries a foreign key to one; records and rules after both, because a rule names
#: an entity the records supply and a reader who finds neither sees an install that is empty
#: rather than one that is half seeded.
TABLES: Final[tuple[str, ...]] = (
    "auth.principal",
    "gate.capability_grant",
    "proj.record",
    "gate.fast_path_rule",
)


def principal_rows() -> tuple[dict[str, Any], ...]:
    """Every principal the demo writes, the service principal included."""
    principals = [one.principal for one in build_people()]
    principals.append(build_service_principal())
    return tuple(
        {
            "id": one.id,
            "kind": str(one.kind),
            "employment": str(one.employment),
            "display_name": one.display_name,
            "primary_department": one.primary_department,
            "not_after": one.not_after,
        }
        for one in principals
    )


def grant_rows() -> tuple[dict[str, Any], ...]:
    """Every grant, with the two columns the table will not accept null in.

    `granted_by` and `reason` are filled here rather than left to the writer, because a
    column that is not nullable and is supplied at the call site is a column that is supplied
    differently by the second call site.
    """
    return tuple(
        {
            "principal_id": person.principal.id,
            "capability": grant.capability.value,
            "scope": grant.scope.model_dump_json(),
            "granted_by": GRANTED_BY,
            "reason": GRANT_REASON,
            "not_after": None,
        }
        for person in build_people()
        for grant in person.grants
    )


def record_rows() -> tuple[dict[str, Any], ...]:
    """Every projected record, keyed the way `proj.record` is keyed."""
    return tuple(
        {
            "source": DEMO_SOURCE,
            "entity": one.entity,
            "source_id": one.source_id,
            "local_id": None,
            "fields": dict(one.fields),
            "last_seen_at": SEEDED_AT,
        }
        for one in build_records()
    )


def rule_rows() -> tuple[dict[str, Any], ...]:
    """Every fast-path rule, attributed to the seed rather than to a person."""
    return tuple(
        {
            "rule_id": one.rule_id,
            "template": one.template,
            "slot": one.slot,
            "source": DEMO_SOURCE,
            "entity": one.entity,
            "match_field": one.match_field,
            "answer_field": one.answer_field,
            "created_by": GRANTED_BY,
        }
        for one in build_rules()
    )


def demo_rows() -> dict[str, tuple[dict[str, Any], ...]]:
    """Every row the demo writes, by table, in insertion order.

    Keyed by the qualified table name and built from `TABLES` rather than from a literal
    dictionary, so a table added to one and not the other is a `KeyError` at import rather
    than a table that is silently never written.
    """
    builders = {
        "auth.principal": principal_rows,
        "gate.capability_grant": grant_rows,
        "proj.record": record_rows,
        "gate.fast_path_rule": rule_rows,
    }
    return {table: builders[table]() for table in TABLES}


def demo_identifiers() -> tuple[str, ...]:
    """Every identifier the demo writes, which is what removing it deletes.

    The removal predicate is this list rather than a `LIKE 'demo_%'` written at a call site:
    a prefix match also catches a real person a client happened to name that way, and the one
    time that matters is the time somebody runs the removal against production data.
    """
    found: list[str] = [one["id"] for one in principal_rows()]
    found.extend(one["source_id"] for one in record_rows())
    found.extend(one["rule_id"] for one in rule_rows())
    return tuple(found)


# ------------------------------------------------------------------ the checks
def _values(rows: tuple[dict[str, Any], ...]) -> Iterator[tuple[str, str]]:
    """Every string value in a set of rows, with the column it came from."""
    for row in rows:
        for column, value in row.items():
            if isinstance(value, str):
                yield column, value
            elif isinstance(value, dict):
                for inner, deep in value.items():
                    if isinstance(deep, str):
                        yield f"{column}.{inner}", deep


def demo_gaps() -> tuple[str, ...]:
    """Everything about this demo that would be wrong on a client's install.

    Written as findings rather than as assertions in a test, so the same rule can be run
    against the seed by whoever is about to load it. The four properties are the four
    arguments in the header, in the order they are made there.
    """
    findings: list[str] = []
    rows = demo_rows()

    for identifier in demo_identifiers():
        if not identifier.startswith(DEMO_PREFIX):
            findings.append(
                f"{identifier!r} does not start with {DEMO_PREFIX!r}, so removing the demo "
                f"cannot be a predicate. {A_DEMO_NOBODY_CAN_REMOVE_BECOMES_PRODUCTION_DATA}"
            )

    for table, table_rows in rows.items():
        for column, value in _values(table_rows):
            if CANARY_SHAPED.search(value):
                findings.append(
                    f"{table}.{column} holds {value!r}, which is canary-shaped. "
                    f"{A_DEMO_AND_A_TEST_FIXTURE_WANT_OPPOSITE_THINGS}"
                )

    for person in build_people():
        for grant in person.grants:
            if not grant.scope.clauses:
                findings.append(
                    f"{person.principal.id} holds {grant.capability.value} unrestricted. "
                    f"{AN_UNRESTRICTED_GRANT_IN_A_DEMO_IS_A_DEMO_OF_THE_WRONG_PRODUCT}"
                )
        if person.principal.primary_department not in DEPARTMENTS:
            findings.append(
                f"{person.principal.id} sits in "
                f"{person.principal.primary_department!r}, which is not a demo department"
            )

    for row in rows["gate.capability_grant"]:
        if str(row["capability"]).startswith("admin:"):
            findings.append(
                f"{row['principal_id']} holds {row['capability']}. "
                f"{A_DEMO_THAT_SHIPS_AN_ADMINISTRATOR_SHIPS_AN_ACCOUNT_NOBODY_CREATED}"
            )

    return tuple(findings)


#: What a question the demo cannot answer comes back as. One string for every reason, because
#: the reasons are "no rule matched", "no record by that name" and "two records answered to
#: it", and telling them apart on a fresh install would teach the first person to use the
#: system that the absence of an answer is a fact about what exists.
NO_ANSWER: Final = "no answer"


def answer(
    question: str,
    *,
    rules: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> str | None:
    """One question against the demo's own rules and records, with no model in the loop.

    **The rows are passed in rather than read here**, which is the split every policy module
    in this repository keeps: `brain.seed` owns the connection, this owns what an answer is.
    The reason is the case that matters, which is a question that matches a rule whose records
    are not there. That case is two lines of setup here and needs a database anywhere else.

    Returns None for every kind of nothing, deliberately: no rule matched, no record answered
    to the name, and two did. `brain.gate.fast_lane` gives the argument in full under
    `AN_EMPTY_ANSWER_IS_THE_SAME_ANSWER_FOR_A_DENIAL_AND_AN_ABSENCE`, and it is the same
    argument on the first day of an install as on any other.
    """
    from brain.gate.fast_lane import match_rule, rules_from_rows

    parsed = rules_from_rows(rules)
    entities = frozenset(str(one["entity"]) for one in records)
    match = match_rule(question, parsed, entities=entities)
    if match is None:
        return None
    hits = [
        one
        for one in records
        if str(one["entity"]) == match.rule.entity
        and str(dict(one["fields"]).get(match.rule.match_field, "")).casefold()
        == match.value.casefold()
    ]
    if len(hits) != 1:
        # Two records answering to one name is a fall-through rather than a first match, for
        # the reason the lane gives: there is nothing downstream able to notice the wrong one.
        return None
    found = dict(hits[0]["fields"]).get(match.rule.answer_field)
    return str(found) if found else None


def summary() -> str:
    """One line per table, for whoever ran the seed and wants to know what landed."""
    rows = demo_rows()
    counted = ", ".join(f"{len(rows[table])} {table}" for table in TABLES)
    return f"{DEMO_COMPANY}: {counted}"
