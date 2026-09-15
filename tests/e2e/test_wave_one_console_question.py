"""The wave-1 milestone: a person asks in the console and is answered from the seeded company.

`docs/wbs` states what must be live after wave one as "a person asks in the console and gets a
permission-correct answer from seeded data", and every clause of it is load-bearing. This drives
the whole path over HTTP. `brain.seed.install` writes the demo company through its own `Executor`
protocol and what it wrote is read back, so the people, grants, records and rules are the rows an
install holds rather than `brain.demo`'s objects. The real application from
`brain.app.create_app` serves them: a bearer token from a console session is verified, its
subject is mapped to a seeded principal, that person's seeded grants are resolved and narrowed by
`brain.gate.admission`, a question goes to `POST /api/v1/answer` and the records screen to
`GET /api/v1/records/{entity}`, and whatever comes back came through the row plane and the
redactor.

**"The same question" is still the test.** One question, asked in the console by two people from
one department, must produce two answers, because every module on the path is correct on its own
and only the composition can fail. `tests/e2e/test_wave_two_lark_question.py` is the precedent,
and this is its shape with the transport changed to the console and the data changed from a
cassette to the seed.

**The worked examples are the demo's own, and the company fixture is the wrong case here.** Seeded
data is `brain.demo`, and `tests/unit/test_demo.py` holds the demo and the fixture apart on people
and on departments, so a fixture person asking about the seeded company would be refused for a
reason unrelated to the property. The demo carries its own pair. `demo_projects_lead` is Owen
Marsh, "Department admin, Projects", holding `read:client.*` there. `demo_projects_coord` is Sanne
Vos, whose role reads "Sees which clients, never what they are worth": Wei Ling, restated for a
demo. `demo_ops_lead` asks from another department, and `demo_ops_scheduler` holds nothing over
clients at all.

**There are no canaries in seeded data, so the leak instrument is the seeded value itself.** The
demo refuses canary-shaped strings by construction (`brain.demo.CANARY_SHAPED`, asserted in
`tests/unit/test_demo.py`), because a client's first screen reading `CANARY-CONTRACT-7Q4XZ` looks
like a corrupted database. So what must not leak is the contract value the seed wrote for the
record the two people share, and a guard below asserts that string occurs exactly once in
everything the seed wrote, which is what makes its appearance anywhere else a leak rather than a
coincidence.

**What this found, and what closed it.** Measured on 2026-09-14, the product as it shipped could
not answer anybody's question about the seeded company in the console, and each of three defects
was enough on its own to stop it. Each is pinned by a test below that fails for that reason.

1. **Nothing classified a seeded entity.** `brain.tools.startup.BUILT_IN_ROW_ENTITIES` held the
   price list alone, so no row tool existed for `client`, `job` or `invoice`. The demo now
   classifies its own columns (`brain.demo.row_classifications`), and `brain.tools.startup`
   registers them for an install that reads the demo's source and for no other, rather than
   widening the built-ins: those columns are an invented company's schema, and built in they
   would govern every install's `client`. See
   `test_the_entity_the_worked_examples_ask_about_is_classified_by_the_application`.
2. **A seeded record did not carry the field its readers' grants are scoped on.** Every demo
   grant is a department scope, and `brain.demo.record_rows` never wrote the department into
   `fields`, so the compiled WHERE clause and the redactor both tested a key no seeded record
   had. It writes it now, derived from the scope rather than spelled twice. See
   `test_every_seeded_record_carries_the_fields_its_readers_grants_are_scoped_on`.
3. **The seed and the application named different sources, and the mismatch was a 500.** The
   seed files everything under `brain.demo.DEMO_SOURCE` and the application reads rows under
   `Settings.tool_source`. Which system an install reads is configuration, so an install showing
   the seeded company is configured to read the demo's source, and `showing_the_seeded_company`
   below is that configuration. The 500 was its own defect: `fast_lane.entities_served` keyed on
   the entity alone, so a rule for a pair nothing served matched and `respond` raised. It keys on
   the pair now. See `test_the_seed_writes_under_the_source_the_application_reads_rows_from` and
   `test_a_rule_filed_under_a_source_the_console_does_not_read_abstains_rather_than_failing`.

The constraint the first fix had to meet lives in `brain.demo`: the department column requires
`read:client` and not `read:client.department`. The redactor evaluates a department scope
against the record `read_rows` builds from the projection, so a coordinator who may reach the row
and not select that column had her row dropped whole. See
`brain.demo.THE_COLUMN_A_SCOPE_TESTS_IS_READ_BY_WHOEVER_REACHES_THE_ROW` and
`test_she_sees_the_seeded_client_and_never_what_it_is_worth`.

**Each defect was a strict xfail while it stood, and the markers came off with the fixes.** A
finding with no test goes stale in a commit message, and a test asserting the broken behaviour
would have gone red on the fix and read as a regression. So each property was asserted, marked
`xfail(strict=True)` and restricted to `AssertionError`, and so were the three tests that are the
leaf itself: a fix could not land without its marker coming off, because strictness turns an
unexpected pass into a failure. None is left.

**What this does not do.** No model is called: the answer lane is the fast lane, a rule and a row.
No PostgreSQL: the row source is a double over the rows the seed wrote. It applies the tool's own
pin, because that is wiring a real source applies too, and ignores the caller's scope and the
asker's filter, deliberately, so anything missing from a response was removed by the projection
or the redactor and never by the double being polite. The seed's writes are read back from its
`Executor` rather than from a database, so no trigger, constraint or conflict clause runs. The
console's browser half is not here; what is here is the API the console calls, with a token that
carries a session and is therefore held to the console's channel ceiling. And the configuration
is set here rather than read from an install: nothing in this repository sets
`BRAIN_TOOL_SOURCE=demo` on an install that loads the demo, which is a setup step and not a
composition a test can show.

Task ids: M38.2.2.2
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import demo, seed
from brain.api import API_PREFIX
from brain.api_routes import GateWiring, row_readers
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.abstain import NOT_FOUND_TEXT
from brain.gate.context import Channel
from brain.gate.fast_lane import FastPathRule, rules_from_rows
from brain.identity.bearer import TokenAuthority
from brain.knowledge.rows import ID_KEY, RowQuery, row_scope_for
from brain.tools.startup import build_registry, classification_for
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    KID,
    Keys,
    NoCache,
    Versions,
    marker_for,
    verifier,
)
from tests.unit.test_streaming import decode

# ------------------------------------------------------------------ the install
#: Why the console here reads the demo's source rather than the application's default.
AN_INSTALL_SHOWS_THE_SEEDED_COMPANY_BY_READING_ITS_SOURCE: Final = (
    "The seed files everything it writes under brain.demo.DEMO_SOURCE, because those rows came "
    "from nobody, and Settings.tool_source is which system an install reads rows from. So an "
    "install showing the seeded company is configured to read the demo's source, the way an "
    "install is configured to read any system, and an install configured the default way reads "
    "its own system and registers none of the demo."
)


def showing_the_seeded_company() -> Settings:
    """The application's settings on an install that shows the seeded company.

    See `AN_INSTALL_SHOWS_THE_SEEDED_COMPANY_BY_READING_ITS_SOURCE`. A function rather than a
    module constant, because `Settings` reads the environment when it is built and a constant
    would read it once, at collection, for every test after.
    """
    return Settings(env="development", tool_source=demo.DEMO_SOURCE)


def reading_its_own_system() -> Settings:
    """The application's settings on an install configured the default way."""
    return Settings(env="development")


# ------------------------------------------------------------------ the worked examples
#: "Department admin, Projects": every client column, in Projects.
SEES_THE_VALUE: Final = f"{demo.DEMO_PREFIX}projects_lead"

#: "Sees which clients, never what they are worth": the client's name, in Projects.
SEES_THE_CLIENT_NOT_ITS_VALUE: Final = f"{demo.DEMO_PREFIX}projects_coord"

#: Every client column, in Operations, which is not where the shared record lives.
IN_ANOTHER_DEPARTMENT: Final = f"{demo.DEMO_PREFIX}ops_lead"

#: Jobs and nothing else. Holds no grant over clients anywhere.
HOLDS_NOTHING_OVER_CLIENTS: Final = f"{demo.DEMO_PREFIX}ops_scheduler"

#: The column the two worked examples differ by.
VALUE_FIELD: Final = "contract_value"

#: What a console session signed in with a password alone may exercise. Written in words rather
#: than read from `brain.gate.admission`, so a change to the ceiling there is compared against
#: this sentence and not against itself: a password-only session reads, writes and invokes, and
#: approves and administers nothing.
A_PASSWORD_ONLY_CONSOLE_SESSION_MAY: Final = frozenset({"read", "write", "invoke"})

#: A client the seeded company does not have, in the words `tests/unit/test_demo.py` uses for one.
NOBODY: Final = "Nobody At All"


# ------------------------------------------------------------------ what the seed wrote
#: The table an insert names, as `brain.seed.insert_statement` spells it.
INSERT_INTO: Final = re.compile(r'^INSERT INTO "([a-z_]+)"\."([a-z_]+)"')


class RecordingExecutor:
    """A `brain.seed.Executor` that keeps what the seed wrote instead of sending it anywhere.

    Refuses anything that is not an insert, because the one thing this file relies on is that
    the rows read back are the rows a load would have written, and a statement it did not
    understand is a row it would silently have missed.
    """

    def __init__(self) -> None:
        self.written: dict[str, list[dict[str, Any]]] = {}

    def execute(self, statement: Any, parameters: Any = None, /) -> None:
        found = INSERT_INTO.match(str(statement))
        assert found is not None, f"the seed ran something that is not an insert: {statement}"
        assert isinstance(parameters, list), "the seed inserts every table as one batch"
        table = f"{found.group(1)}.{found.group(2)}"
        self.written.setdefault(table, []).extend(dict(one) for one in parameters)


@dataclass(frozen=True)
class Seeded:
    """The demo company as the seed wrote it, decoded the way a database would hand it back."""

    principals: Mapping[str, Principal]
    grants: Mapping[str, tuple[Grant, ...]]
    records: tuple[Mapping[str, Any], ...]
    rules: tuple[FastPathRule, ...]
    written: Mapping[str, list[dict[str, Any]]]

    def reach(self, pid: str) -> EntitlementSet:
        """Everything this seeded person holds, as `gate.capability_grant` records it."""
        return EntitlementSet(
            principal_id=pid,
            grants=self.grants.get(pid, ()),
            not_after=self.principals[pid].not_after,
        )

    def record(self, source_id: str) -> Mapping[str, Any]:
        return next(one for one in self.records if one["source_id"] == source_id)


def read_back_the_seed() -> Seeded:
    """Run `brain.seed.install` and decode every row it wrote."""
    executor = RecordingExecutor()
    seed.install(executor)
    written = executor.written

    principals = {
        str(row["id"]): Principal(
            id=str(row["id"]),
            kind=PrincipalKind(row["kind"]),
            employment=Employment(row["employment"]),
            display_name=str(row["display_name"]),
            primary_department=row["primary_department"],
            not_after=row["not_after"],
        )
        for row in written["auth.principal"]
    }
    grants: dict[str, list[Grant]] = {}
    for row in written["gate.capability_grant"]:
        grants.setdefault(str(row["principal_id"]), []).append(
            Grant(
                capability=Capability(value=str(row["capability"])),
                scope=Scope.model_validate_json(str(row["scope"])),
            )
        )
    records = tuple(
        {**row, "fields": json.loads(str(row["fields"]))} for row in written["proj.record"]
    )
    return Seeded(
        principals=principals,
        grants={pid: tuple(held) for pid, held in grants.items()},
        records=records,
        rules=rules_from_rows(written["gate.fast_path_rule"]),
        written=written,
    )


@pytest.fixture(scope="module")
def seeded() -> Seeded:
    return read_back_the_seed()


def shared_record(seeded: Seeded) -> Mapping[str, Any]:
    """The client both worked examples may see, in the department they both sit in.

    Found through `brain.demo.build_records`, which declares the department, rather than through
    the department the seed stores. Every fixture here calls this, so reading the stored field
    would turn a seed that stopped writing it into every test erroring at setup, and the one
    test written to fail for that reason would be lost in the noise.
    """
    department = seeded.principals[SEES_THE_VALUE].primary_department
    declared = next(
        one
        for one in demo.build_records()
        if one.entity == "client" and one.department == department
    )
    return seeded.record(declared.source_id)


def client_rule(seeded: Seeded) -> FastPathRule:
    """The seeded rule that answers a question about a client by name."""
    return next(one for one in seeded.rules if one.entity == "client" and one.match_field == "name")


def question_about(seeded: Seeded, name: str) -> str:
    rule = client_rule(seeded)
    return rule.template.format(**{rule.slot: name})


# ------------------------------------------------------------------ the application
def subject_of(pid: str) -> str:
    """The subject a person's token carries. Opaque, as an identity provider's `sub` is."""
    return f"subject-{pid}"


@dataclass(frozen=True)
class SeededDirectory:
    """A `PrincipalDirectory` over the principals the seed wrote. The real one reads that table."""

    seeded: Seeded

    def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        if issuer != ISSUER:
            return None
        return next(
            (one for pid, one in self.seeded.principals.items() if subject_of(pid) == subject),
            None,
        )


@dataclass(frozen=True)
class SeededStore:
    """An `EntitlementStore` over the grants the seed wrote. The real one reads that table."""

    seeded: Seeded

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return self.seeded.reach(principal_id)


class SeededRecords:
    """A `RowSource` over the records the seed wrote.

    It applies the tool's own pin, a source and an entity, because that is a fact about wiring
    that `brain.knowledge.row_store.SessionRowSource` applies by running the statement, and
    leaving it out would make this double answer for a tool the real one reads nothing for.

    It ignores the caller's scope and the asker's filter, deliberately, and hands back every
    column including the value. Anything absent from a response was therefore removed by the
    projection or the redactor rather than never fetched, which is the argument
    `tests/unit/test_api_routes.UnfilteredRows` makes about its own double.

    `only` narrows it to one named record, because the fast lane falls through when two records
    answer to one name. That is `tests/unit/test_answer_route.OneRow`'s precedent: still
    unfiltered in the way that matters, since the one record carries every column.
    """

    def __init__(self, seeded: Seeded, *, only: str | None = None) -> None:
        self.seeded = seeded
        self.only = only

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        return [
            {ID_KEY: one["source_id"], **one["fields"]}
            for one in self.seeded.records
            if one["source"] == query.source
            and one["entity"] == query.entity
            and (self.only is None or one["source_id"] == self.only)
        ]


def console_token(pid: str) -> str:
    """A compact JWS for one seeded person, from a console session signed in with a password.

    Carries `sid`, which is what `brain.api_routes.channel_for` reads as a browser session and
    therefore the console. Carries no `amr`, so `brain.identity.bearer` reads the sign-in as
    authenticated and not strong.

    Minted against the wall clock rather than a fixed instant, for the reason
    `tests/unit/test_api_routes.token_for` gives: the route reads `datetime.now`, and a token
    stamped with a fixed hour is an expired token on every run after that hour.
    """
    now = datetime.now(UTC)
    header = {"alg": "RS256", "typ": "JWT", "kid": KID}
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": subject_of(pid),
        "typ": "Bearer",
        "sid": f"console-session-{pid}",
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int(now.timestamp()),
    }

    def segment(blob: bytes) -> str:
        return base64.urlsafe_b64encode(blob).decode().rstrip("=")

    return ".".join(
        (
            segment(json.dumps(header).encode()),
            segment(json.dumps(payload).encode()),
            segment(marker_for(KID)),
        )
    )


def console(
    seeded: Seeded,
    *,
    only: str | None = None,
    rules: Sequence[FastPathRule] | None = None,
) -> Iterator[TestClient]:
    """The real application, holding the seeded company exactly as it would hold it from a database.

    Configured by `showing_the_seeded_company`. The registry is built by
    `brain.tools.startup.build_registry` with that configuration's `tool_source`, which is what
    `brain.app.lifespan` does with a database; the rules are the seeded rows through
    `rules_from_rows`, which is what `brain.gate.rule_store.load_rules` does. Nothing here
    registers a tool or classifies an entity the application so configured would not.

    `rules` replaces the seeded rules, for the one test about a rule filed under a source this
    install does not read.
    """
    settings = showing_the_seeded_company()
    app: FastAPI = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=SeededDirectory(seeded),
            ),
            versions=Versions(),
            store=SeededStore(seeded),
            cache=NoCache(),
        )
        app.state.tools = build_registry(
            source=settings.tool_source, records=SeededRecords(seeded, only=only)
        )
        app.state.fast_path_rules = seeded.rules if rules is None else tuple(rules)
        yield client


@pytest.fixture
def browsing(seeded: Seeded) -> Iterator[TestClient]:
    """The console over every seeded record."""
    yield from console(seeded)


@pytest.fixture
def asking(seeded: Seeded) -> Iterator[TestClient]:
    """The console over the one record the question names."""
    yield from console(seeded, only=str(shared_record(seeded)["source_id"]))


@pytest.fixture
def nothing_there(seeded: Seeded) -> Iterator[TestClient]:
    """The console over no record at all, which is what a question about an absent client finds."""
    yield from console(seeded, only="no_record_has_this_id")


@pytest.fixture
def asking_under_another_source(seeded: Seeded) -> Iterator[TestClient]:
    """The console over the one record the question names, holding the seeded rules refiled
    under the source an install configured the default way reads, which this one does not."""
    elsewhere = reading_its_own_system().tool_source
    refiled = tuple(rule.model_copy(update={"source": elsewhere}) for rule in seeded.rules)
    yield from console(seeded, only=str(shared_record(seeded)["source_id"]), rules=refiled)


def ask(client: TestClient, pid: str, question: str) -> Response:
    answered: Response = client.post(
        f"{API_PREFIX}/answer",
        headers={"authorization": f"Bearer {console_token(pid)}"},
        json={"question": question},
    )
    return answered


def browse(client: TestClient, pid: str, entity: str) -> Response:
    page: Response = client.get(
        f"{API_PREFIX}/records/{entity}",
        headers={"authorization": f"Bearer {console_token(pid)}"},
    )
    return page


def said(answered: Response) -> list[str]:
    """The text frames of an answer, which is what a person reads."""
    return [one.data for one in decode(answered.text) if one.event == "text"]


# ================================================================== the person in the console
def test_every_seeded_person_is_known_to_the_console_as_themselves(
    seeded: Seeded, browsing: TestClient
) -> None:
    """**"A person asks in the console", which is the half of the leaf that held first.** Every
    seeded person presenting a console session is resolved from the seeded principal table as
    themselves, on the console's channel, at the reach their seeded grants give a password-only
    session there.

    The reach is compared by digest against the seeded grants narrowed to
    `A_PASSWORD_ONLY_CONSOLE_SESSION_MAY`, which is written in words here rather than read from
    `brain.gate.admission`, so a ceiling that stopped narrowing is compared against a sentence
    and not against itself.

    Delete this and the console can answer a seeded person at somebody else's reach, or at their
    nominal reach with the approve verb in it, and every other test here still passes."""
    people = [pid for pid, one in seeded.principals.items() if one.kind is PrincipalKind.HUMAN]
    assert len(people) >= 4, "the seed wrote fewer people than the worked examples need"

    for pid in people:
        me = browsing.get(
            f"{API_PREFIX}/me", headers={"authorization": f"Bearer {console_token(pid)}"}
        )
        assert me.status_code == 200, (pid, me.text)
        body = me.json()
        exercisable = tuple(
            grant
            for grant in seeded.grants.get(pid, ())
            if grant.capability.verb in A_PASSWORD_ONLY_CONSOLE_SESSION_MAY
        )

        assert body["principal_id"] == pid
        assert body["channel"] == str(Channel.CONSOLE)
        assert body["ent_hash"] == EntitlementSet(principal_id=pid, grants=exercisable).ent_hash()


def test_the_worked_examples_differ_by_the_value_and_by_nothing_else(seeded: Seeded) -> None:
    """The two people the leaf is asked of are what this file says they are, read from the
    grants the seed wrote rather than from `brain.demo`: both reach client rows in the same place
    and read the client's name, and only one reads its value.

    Delete this and a change to the seed can turn the pair into two people who differ by
    department, and the answers below would differ for a reason unrelated to the value."""
    lead = seeded.reach(SEES_THE_VALUE)
    coordinator = seeded.reach(SEES_THE_CLIENT_NOT_ITS_VALUE)
    name = Capability(value="read:client.name")
    value = Capability(value=f"read:client.{VALUE_FIELD}")

    assert row_scope_for("client", lead) is not None
    assert row_scope_for("client", lead) == row_scope_for("client", coordinator)
    assert lead.holds(name) and coordinator.holds(name)
    assert lead.holds(value)
    assert not coordinator.holds(value)
    assert row_scope_for("client", seeded.reach(HOLDS_NOTHING_OVER_CLIENTS)) is None


def test_the_value_that_would_leak_occurs_once_in_everything_the_seed_wrote(
    seeded: Seeded,
) -> None:
    """The guard on every leak check here. Seeded data carries no canary, so a leak is detected
    by the seeded value itself, and that only works if the value appears nowhere else: not in
    another record, a rule, a name or an address. Counted as a substring across every string the
    seed wrote, including inside a record's fields.

    Delete this and a seed that wrote the same figure twice turns every absence check here into
    a check that could be satisfied or failed by the wrong row."""
    value = str(shared_record(seeded)["fields"][VALUE_FIELD])
    strings: list[str] = []
    for rows in seeded.written.values():
        for row in rows:
            strings.extend(str(cell) for cell in row.values())

    assert sum(one.count(value) for one in strings) == 1, value


# ================================================================ the three defects, one at a time
def test_the_entity_the_worked_examples_ask_about_is_classified_by_the_application(
    seeded: Seeded,
) -> None:
    """Defect 1 on its own: the application classifies the entity the seeded rule and the shared
    record are about, and an install showing the seeded company registers one row tool for it.

    Both halves, because the records route asks both: an entity with a classification and no
    tool is a 404 there, and a tool with no classification is refused a policy by the answer
    lane.

    Delete this and the reason the leaf tests below fail is one of three nobody can tell apart."""
    entity = str(shared_record(seeded)["entity"])
    registry = build_registry(
        source=showing_the_seeded_company().tool_source, records=SeededRecords(seeded)
    )

    assert classification_for(entity) is not None
    assert [one.entity for one in registry.definitions()].count(entity) == 1


def test_every_seeded_record_carries_the_fields_its_readers_grants_are_scoped_on(
    seeded: Seeded,
) -> None:
    """Defect 2 on its own: for every seeded person and every entity they reach, every field their
    row scope tests is present on every stored record of that entity.

    Read from the stored rows, which is the test `tests/unit/test_demo.py` did not make until
    this one found the gap: it checked that the scope resolves and never that a record could
    satisfy it.

    Delete this and a seed can go on writing records no scoped reader can ever reach."""
    for pid in seeded.principals:
        reach = seeded.reach(pid)
        for entity in sorted({str(one["entity"]) for one in seeded.records}):
            scope = row_scope_for(entity, reach)
            if scope is None:
                continue
            tested = {clause.field for clause in scope.clauses}
            for record in seeded.records:
                if record["entity"] == entity:
                    missing = sorted(tested - set(record["fields"]))
                    assert not missing, (pid, record["source_id"], missing)


def test_the_seed_writes_under_the_source_the_application_reads_rows_from(seeded: Seeded) -> None:
    """Defect 3 on its own: every source and entity a seeded rule or record names is a pair the
    answer lane has a reader for on an install showing the seeded company, and on an install
    configured the default way it has a reader for none of them.

    Read from `row_readers`, which is the mapping the answer route hands the lane, rather than
    from the setting, because a source name compared with the setting it was copied into is a
    constant compared with itself. The last assertion is the demo staying out of an install
    that did not ask for it: were the demo's source ever the default, every other assertion here
    would move with it and only that one would notice.

    Delete this and the seed and the application can drift onto different sources again, and
    every seeded question abstains with nothing saying why."""

    def served(settings: Settings) -> set[tuple[str, str]]:
        registry = build_registry(source=settings.tool_source, records=SeededRecords(seeded))
        return set(row_readers(registry))

    by_rules = {(rule.source, rule.entity) for rule in seeded.rules}
    by_records = {(str(one["source"]), str(one["entity"])) for one in seeded.records}

    assert by_rules and by_records
    assert by_rules <= served(showing_the_seeded_company())
    assert by_records <= served(showing_the_seeded_company())
    assert not (by_rules | by_records) & served(reading_its_own_system())


def test_a_rule_filed_under_a_source_the_console_does_not_read_abstains_rather_than_failing(
    seeded: Seeded, asking_under_another_source: TestClient, nothing_there: TestClient
) -> None:
    """**A rule for a pair nothing serves is told what an absence is told, and until 2026-09-14
    it was a 500.** The Projects lead, who is answered when the seeded rule names the source the
    console reads, asks the same question through the seeded rules refiled under a source it does
    not read, and hears word for word what a question about a client that does not exist hears.

    `fast_lane.entities_served` keyed on the entity alone, so the refiled rule matched because a
    client tool existed, `respond` found no reader for its pair and raised, and the route answered
    500. A server error for one question and an abstention for another is also a difference a
    person can read.

    Delete this and the lane can go back to matching on the entity, and the first install whose
    rules and tools name different sources answers every such question with a server error."""
    assert reading_its_own_system().tool_source != showing_the_seeded_company().tool_source
    record = shared_record(seeded)

    refiled = ask(
        asking_under_another_source,
        SEES_THE_VALUE,
        question_about(seeded, str(record["fields"]["name"])),
    )
    absent = ask(nothing_there, SEES_THE_VALUE, question_about(seeded, NOBODY))

    assert refiled.status_code == 200, refiled.text
    assert said(refiled) == said(absent)
    assert any(NOT_FOUND_TEXT in text for text in said(refiled)), said(refiled)


# ================================================================== the leaf
def test_the_person_who_may_see_it_is_answered_from_the_seeded_record(
    seeded: Seeded, asking: TestClient
) -> None:
    """**The sentence the wave-1 milestone is written as, in the direction nobody reports.** The
    Projects lead asks the seeded rule's question about the seeded client in Projects and is
    told the seeded answer.

    Delete this and the console can refuse every seeded question from everybody, which every
    refusal test in this file reads as the permission model working."""
    record = shared_record(seeded)
    rule = client_rule(seeded)

    answered = ask(asking, SEES_THE_VALUE, question_about(seeded, str(record["fields"]["name"])))

    assert answered.status_code == 200, answered.text
    texts = said(answered)
    assert any(str(record["fields"][rule.answer_field]) in text for text in texts), texts
    assert not any(NOT_FOUND_TEXT in text for text in texts), texts


@pytest.mark.parametrize("pid", [SEES_THE_CLIENT_NOT_ITS_VALUE, IN_ANOTHER_DEPARTMENT])
def test_somebody_who_may_not_be_told_it_hears_what_an_absence_is_told(
    pid: str, seeded: Seeded, asking: TestClient, nothing_there: TestClient
) -> None:
    """DENIED and ABSENT must be one answer, asked in the console about seeded data. The
    coordinator may not read the answer field and the Operations lead may not reach the record,
    and each is told, word for word, what they are told about a client that does not exist.

    Until 2026-09-14 both sides were the abstention the three defects produced, so this passed
    for a reason unrelated to its property. The refused side now reaches the row plane and the
    redactor, which is where a refusal could become a sentence of its own.

    Delete this and the console can tell a person which seeded clients exist by answering a
    refusal differently from an absence."""
    record = shared_record(seeded)

    refused = said(ask(asking, pid, question_about(seeded, str(record["fields"]["name"]))))
    absent = said(ask(nothing_there, pid, question_about(seeded, NOBODY)))

    assert refused == absent
    assert any(NOT_FOUND_TEXT in text for text in refused), refused


def test_the_person_entitled_to_the_value_sees_it_on_the_records_screen(
    seeded: Seeded, browsing: TestClient
) -> None:
    """**Screen 3, from seeded data.** The Projects lead opens the client records in the console
    and the shared client is there with its value.

    Delete this and the value can be withheld from the one person entitled to it, which is the
    same defect as a leak and the one nobody reports."""
    record = shared_record(seeded)

    page = browse(browsing, SEES_THE_VALUE, str(record["entity"]))

    assert page.status_code == 200, page.text
    assert str(record["fields"][VALUE_FIELD]) in page.text


def test_she_sees_the_seeded_client_and_never_what_it_is_worth(
    seeded: Seeded, browsing: TestClient
) -> None:
    """**The other half of the same screen.** The coordinator opens the same records and sees the
    shared client by name, and its value is nowhere in what she receives.

    Delete this and the records screen can withhold the client from her altogether, which passes
    every leak check and is the page she was given the grant to read."""
    record = shared_record(seeded)

    page = browse(browsing, SEES_THE_CLIENT_NOT_ITS_VALUE, str(record["entity"]))

    assert page.status_code == 200, page.text
    names = [item.get("name") for item in page.json()["items"]]
    assert record["fields"]["name"] in names, names
    assert str(record["fields"][VALUE_FIELD]) not in page.text


@pytest.mark.parametrize(
    "pid", [SEES_THE_CLIENT_NOT_ITS_VALUE, IN_ANOTHER_DEPARTMENT, HOLDS_NOTHING_OVER_CLIENTS]
)
def test_the_seeded_value_reaches_nobody_who_may_not_read_it(
    pid: str, seeded: Seeded, asking: TestClient, browsing: TestClient
) -> None:
    """The leak direction, over both surfaces the console has: the answer to the question about
    the shared client, and the client records screen. Checked on the whole body rather than on a
    field, because a value can be absent from a record and present in a label.

    Its positive siblings are the two tests above that show the value to the lead, which is why
    this is not satisfied by a console that shows nobody anything.

    Delete this and the seeded value can reach the coordinator, another department or somebody
    holding nothing over clients, and no other test here reads a body for it."""
    record = shared_record(seeded)
    value = str(record["fields"][VALUE_FIELD])

    answered = ask(asking, pid, question_about(seeded, str(record["fields"]["name"])))
    page = browse(browsing, pid, str(record["entity"]))

    assert value not in answered.text
    assert value not in page.text


def test_an_entity_somebody_holds_nothing_over_answers_exactly_as_one_that_does_not_exist(
    seeded: Seeded, browsing: TestClient
) -> None:
    """The records screen, asked by a seeded person who holds nothing over clients, answers the
    client entity with the status and bytes an entity that does not exist gets. The entity is
    classified and has a tool on this install, so this is a refusal answering like an absence
    rather than two absences agreeing, which is what it was until 2026-09-14.

    Compared as whole bodies with one exclusion, the trace id, for the reason
    `tests/unit/test_api_routes.py` gives about the same comparison: it is minted per request
    before anything is known about the question, so it differs between any two requests and
    says nothing about either. The lengths are compared too, because two refusals of different
    lengths are distinguishable without being read.

    Delete this and the console tells a person which kinds of record the seeded company keeps by
    answering a refusal differently from an absence."""
    record = shared_record(seeded)

    refused = browse(browsing, HOLDS_NOTHING_OVER_CLIENTS, str(record["entity"]))
    absent = browse(browsing, HOLDS_NOTHING_OVER_CLIENTS, "no_such_entity")

    assert refused.status_code == absent.status_code == 404
    assert {k: v for k, v in refused.json().items() if k != "trace_id"} == {
        k: v for k, v in absent.json().items() if k != "trace_id"
    }
    assert refused.json()["trace_id"] and absent.json()["trace_id"]
    assert refused.headers.get("content-length") == absent.headers.get("content-length")
