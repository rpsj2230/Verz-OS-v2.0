"""The demo company, and the properties that keep it a different artefact from the fixture.

M41.2.2 says "deliberately not the Verz test fixture", and that sentence is only worth
anything if something checks it. Every test here is one half of that: either the demo does
not contain what the fixture contains, or the demo contains what a demo needs and the fixture
deliberately does not.

The two artefacts are imported side by side in one file on purpose. Anywhere else, "they are
different" is a claim in a docstring; here it is a comparison that fails.

Task ids: M41.2.2
"""

from __future__ import annotations

import pytest

from brain import demo
from brain.gate.fast_lane import match_rule, rules_from_rows
from brain.ops.independence import is_reserved
from tests.fixtures.company import CANARIES, build_company, canary_tokens


def _every_demo_string() -> list[tuple[str, str]]:
    """Every string value the demo would write, with where it came from."""
    found: list[tuple[str, str]] = []
    for table, rows in demo.demo_rows().items():
        for row in rows:
            for column, value in row.items():
                if isinstance(value, str):
                    found.append((f"{table}.{column}", value))
                elif isinstance(value, dict):
                    found.extend(
                        (f"{table}.{column}.{inner}", deep)
                        for inner, deep in value.items()
                        if isinstance(deep, str)
                    )
    return found


# --------------------------------------------------- the demo is not the test fixture
def test_no_canary_the_permission_suite_depends_on_appears_anywhere_in_the_demo() -> None:
    """The reason there are two artefacts rather than one.

    The fixture's canaries are improbable tokens sitting where a value would be, and a test
    asserts they never reach somebody without the grant. Shipping them to a client puts
    `CANARY-CONTRACT-7Q4XZ` on their first screen and hands them a string whose absence the
    product's permission suite depends on.

    Deleting this test makes "point the seed at the fixture" a one-line change again, which
    is exactly the change that was there until 2026-09-07.
    """
    tokens = canary_tokens()
    assert tokens, "the fixture has no canaries, so this comparison proves nothing"
    for where, value in _every_demo_string():
        for token in tokens:
            assert token not in value, f"{where} carries the fixture canary {token}"


def test_the_demo_and_the_test_fixture_name_no_person_in_common() -> None:
    """Two companies, not one company written twice. A shared identifier would mean a demo
    row and a fixture row could collide in one database, and the collision would be silent:
    whichever landed second would be discarded by the conflict clause.

    Deleting this lets the demo drift back towards being the fixture one name at a time.
    """
    fixture = build_company()
    fixture_ids = set(fixture)
    fixture_names = {person.principal.display_name for person in fixture.values()}
    demo_ids = {row["id"] for row in demo.demo_rows()["auth.principal"]}
    demo_names = {row["display_name"] for row in demo.demo_rows()["auth.principal"]}

    assert not (fixture_ids & demo_ids)
    assert not (fixture_names & demo_names)


def test_the_demo_and_the_test_fixture_share_no_department() -> None:
    """The fixture's four departments are the ones Verz has. A demo repeating them is a Verz
    value in a client's database wearing a fictitious company's name.

    Deleting this lets the department list be copied across, which is the least visible way
    the two artefacts merge back into one.
    """
    from tests.fixtures.company import DEPARTMENTS as FIXTURE_DEPARTMENTS

    assert not (set(FIXTURE_DEPARTMENTS) & set(demo.DEPARTMENTS))
    assert len(demo.DEPARTMENTS) == len(set(demo.DEPARTMENTS))


def test_the_demo_carries_no_list_of_what_a_person_must_not_see() -> None:
    """The fixture's `Person` has a `forbidden` tuple because a canary test asserts against
    it. A demo carrying one would be a list, shipped to a client, of exactly what their own
    screens are meant to withhold, which is the disclosure the whole platform is arranged
    against.

    Deleting this lets `forbidden` be copied over with the rest of the shape, and it would
    look like completeness rather than like a leak.
    """
    fields = set(demo.DemoPerson.__dataclass_fields__)
    assert "forbidden" not in fields
    assert not any("forbid" in one or "denied" in one for one in fields), fields


# --------------------------------------------------- the demo is what a demo has to be
def test_the_demo_ships_no_administrator_and_no_unrestricted_grant() -> None:
    """The first administrator is created by a person at first run, against a token that
    cannot be replayed. A demo that arrives holding one has created an account nobody asked
    for, with the widest reach in the system and a provenance of "the seed".

    Deleting this makes `admin:grant` one line away, and the line reads like convenience.
    """
    for row in demo.demo_rows()["gate.capability_grant"]:
        assert not str(row["capability"]).startswith("admin:"), row
    for person in demo.build_people():
        for grant in person.grants:
            assert grant.scope.clauses, f"{person.principal.id} holds an unrestricted grant"


def test_every_identifier_the_demo_writes_carries_the_prefix_that_removes_it() -> None:
    """Removal has to be a predicate. A client who finishes with the demo and cannot tell
    which rows were invented keeps them, and a fictitious company is then counted, searched
    and answered from inside a real one's data.

    Deleting this lets one unprefixed identifier in, and the row it names is the row the
    removal misses.
    """
    identifiers = demo.demo_identifiers()
    assert identifiers
    assert all(one.startswith(demo.DEMO_PREFIX) for one in identifiers)


def test_every_demo_address_is_on_a_domain_reserved_for_documentation() -> None:
    """`brain.ops.independence` refuses a work address anywhere under `src`, and this module
    is under `src` because a demo is product. The addresses therefore have to be on a domain
    that can never become a real company's, and that is decided by the same function the
    sweep uses rather than by this test's own opinion.

    Deleting this lets an address on an ordinary domain in, and the first person to notice is
    whoever the demo emails.
    """
    people = demo.build_people()
    assert people
    for person in people:
        domain = person.address.partition("@")[2]
        assert is_reserved(domain), person.address


def test_a_demo_grant_names_a_department_the_demo_declares() -> None:
    """A grant scoped to a department nobody is in is a grant that reaches nothing, and a
    demo where half the people see nothing demonstrates a broken install.

    Deleting this lets a typo in a department name pass, and the symptom is an empty screen
    that looks like a permission model working correctly.
    """
    for person in demo.build_people():
        assert person.principal.primary_department in demo.DEPARTMENTS
        for grant in person.grants:
            values = [clause.value for clause in grant.scope.clauses]
            assert all(one in demo.DEPARTMENTS for one in values), (person.principal.id, values)


def test_the_demo_can_answer_a_question_about_its_own_records_with_no_model() -> None:
    """The half that makes this a demo rather than a data set: a question typed on a fresh
    install is matched by a rule the demo seeded, against a record the demo seeded, with no
    inference server in the loop.

    The rules and the records are compared through the real matcher rather than by reading
    both files, because the failure that matters is a rule whose template does not fit the
    values the records hold, and that is invisible in either file alone.

    Deleting this lets the rules and the records drift apart, and the install then holds rows
    and answers nothing.
    """
    rules = rules_from_rows(demo.rule_rows())
    entities = frozenset(one.entity for one in demo.build_records())
    client = next(one for one in demo.build_records() if one.entity == "client")

    match = match_rule(f"what is the status of {client.fields['name']}", rules, entities=entities)
    assert match is not None, "no demo rule matches a question about a demo record"
    assert match.value == client.fields["name"]
    assert client.fields[match.rule.match_field] == match.value
    assert match.rule.answer_field in client.fields


def test_every_table_the_demo_declares_produces_rows() -> None:
    """`demo_rows` is built from `TABLES`, so a table named there and not built is a
    `KeyError` rather than a table nobody writes. What this adds is the other direction: a
    table that builds an empty tuple is an install missing a whole plane and reporting
    success.

    Deleting this lets the records or the rules quietly become empty.
    """
    rows = demo.demo_rows()
    assert set(rows) == set(demo.TABLES)
    for table in demo.TABLES:
        assert rows[table], f"{table} produced no rows"


# --------------------------------------------------- the checks, driven rather than read
def test_a_canary_planted_in_a_demo_record_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`demo_gaps` is what `brain.seed` calls before the first insert, so it has to catch a
    canary rather than describe one. Driven by planting one, because a check tested only by
    a clean run passes with its body deleted.

    Deleting this leaves the canary rule asserted by nothing, and the rule is the reason the
    two artefacts stay apart.
    """
    planted = dict(demo.build_records()[0].fields)
    planted["status"] = CANARIES["client.contract_value"]
    monkeypatch.setattr(
        demo,
        "build_records",
        lambda: (
            demo.DemoRecord(
                entity="client",
                source_id=f"{demo.DEMO_PREFIX}client_planted",
                department="operations",
                fields=planted,
            ),
        ),
    )
    findings = demo.demo_gaps()
    assert any("canary-shaped" in one for one in findings), findings


def test_an_unrestricted_grant_in_the_demo_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other rule `brain.seed` relies on. A demo whose people all hold unrestricted scope
    demonstrates a system that answers everything to everybody, which is the opposite of what
    is being sold.

    Deleting this leaves the scope rule asserted only by a clean run, which a function that
    returns an empty tuple satisfies.
    """
    from brain.core.entitlement import Capability, Grant
    from brain.core.scope import Scope

    person = demo.build_people()[0]
    wide = demo.DemoPerson(
        principal=person.principal,
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
        ),
        role=person.role,
    )
    monkeypatch.setattr(demo, "build_people", lambda: (wide,))
    findings = demo.demo_gaps()
    assert any("unrestricted" in one for one in findings), findings


def test_an_administrator_in_the_demo_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """The third rule, and the one that ties this module to `brain.firstrun`: an
    administrator that arrives with the seed is the same object as a default password.

    Deleting this leaves `admin:grant` reachable through the demo with nothing objecting.
    """
    from brain.core.entitlement import Capability, Grant
    from brain.core.scope import Scope

    person = demo.build_people()[0]
    admin = demo.DemoPerson(
        principal=person.principal,
        grants=(
            Grant(capability=Capability(value="admin:grant"), scope=Scope.department("operations")),
        ),
        role=person.role,
    )
    monkeypatch.setattr(demo, "build_people", lambda: (admin,))
    findings = demo.demo_gaps()
    assert any("admin:grant" in one for one in findings), findings


def test_the_demo_as_written_reports_nothing() -> None:
    """The positive half. Three tests above prove the checks fire; this proves the demo
    shipped in this repository passes them, which is what `brain.seed` refuses on.

    Deleting this lets the demo be broken without the suite noticing, because every other
    check here is driven by a planted failure.
    """
    assert demo.demo_gaps() == ()


# --------------------------------------------------- one question, answered
def test_the_demo_answers_a_question_about_a_record_it_seeded() -> None:
    """The install is provable rather than describable only if something answers. A migrated,
    seeded install that has never been asked anything has not been shown to work, and every
    install bug this repository has had lived in exactly that gap.

    Deleting this leaves the CI install job asserting a string with nothing here explaining
    what the string is, and the job would go on passing with the answer path removed.
    """
    found = demo.answer(
        "what is the status of Ashgrove Retail Group",
        rules=demo.rule_rows(),
        records=demo.record_rows(),
    )
    assert found == "active"


@pytest.mark.parametrize(
    "question",
    [
        "what is the status of Nobody At All",  # a rule matches, no record answers
        "what colour is the sky",  # no rule matches at all
    ],
)
def test_every_kind_of_nothing_is_the_same_nothing(question: str) -> None:
    """A first install that answered "no such client" for one name and "I do not understand"
    for another has told its first user which clients exist. The reasons differ and the answer
    must not.

    Deleting this lets the two paths return different values, and the difference is a
    disclosure on the one screen where nobody is looking for one yet.
    """
    assert demo.answer(question, rules=demo.rule_rows(), records=demo.record_rows()) is None


def test_a_name_two_records_answer_to_produces_no_answer_rather_than_the_first() -> None:
    """`brain.gate.fast_lane` refuses an ambiguous record for the reason it refuses an
    ambiguous rule: there is nothing downstream able to notice the wrong one was chosen.

    Deleting this lets the lookup take `[0]`, which is right on the demo as shipped and wrong
    the first time a client adds a second record with the same name.
    """
    twice = [
        *demo.record_rows(),
        {
            "source": demo.DEMO_SOURCE,
            "entity": "client",
            "source_id": f"{demo.DEMO_PREFIX}client_twin",
            "local_id": None,
            "fields": {"name": "Ashgrove Retail Group", "status": "dormant"},
            "last_seen_at": demo.SEEDED_AT,
        },
    ]
    assert (
        demo.answer(
            "what is the status of Ashgrove Retail Group",
            rules=demo.rule_rows(),
            records=twice,
        )
        is None
    )


def test_every_seeded_row_is_identifiable_as_the_demo_and_can_be_removed() -> None:
    """**`DEMO_PREFIX` was compared against itself, so emptying it changed nothing.** Every
    id in this module is built as `f"{DEMO_PREFIX}{something}"` and every test that checked one
    rebuilt it the same way, so the constant could become `""` with the file green.

    An empty prefix is not cosmetic. `A_DEMO_NOBODY_CAN_REMOVE_BECOMES_PRODUCTION_DATA` is the
    whole argument for having one: a demo row indistinguishable from a real row is a row nobody
    dares delete, and a year later the company's own records sit beside four invented clients
    that look exactly like them.

    Asserted as a literal rather than through the constant, and over every row the seed
    actually produces rather than over one sample, because the failure is one builder that
    forgot the prefix rather than all of them.

    Delete this and the demo becomes data somebody has to identify by hand."""
    assert demo.DEMO_PREFIX == "demo_", "the prefix is what makes a demo row removable"

    for row in demo.principal_rows():
        assert str(row["id"]).startswith("demo_"), row

    for row in demo.grant_rows():
        assert str(row["granted_by"]).startswith("demo_"), row

    for row in demo.record_rows():
        assert str(row["source_id"]).startswith("demo_"), row
