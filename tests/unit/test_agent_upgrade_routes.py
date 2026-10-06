"""An agent's upgrade, read, accepted and declined over HTTP.

Driven through the real application, signed in with the token machinery
`tests/fixtures/console_http.py` shares, with an in-memory `AgentUpgrades` put where
`brain.agent_upgrade_routes.upgrades_of` looks first. So these tests prove the routes' decisions:
who is refused with the one 404, what a stale page is told, which versions cannot be accepted and
why, that a version which cannot be accepted can still be declined, and what an acceptance hands
the store. That the rows and the ledger entries reach PostgreSQL is
`tests/unit/test_agent_upgrade_store.py`.

Every agent is made by the product's own install flow from a signed manifest, and every version
on offer is signed with the install's key, so what the routes review is what the domain reviews.

Task ids: M13.4.2, M13.4.3, M13.4.4, M13.4.5
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.agent_lifecycle_routes import NO_SIGNING_KEY_HERE, FoundAgent
from brain.agent_upgrade_routes import (
    ACCEPT_PATH,
    DECLINE_PATH,
    DECLINED,
    IT_MOVED,
    MOVED,
    NO_INSTALL_TO_UPGRADE,
    NOTHING_TO_UPGRADE,
    REFUSED,
    THIS_RAISES_A_RUNG,
    UNAVAILABLE,
    UPGRADE_PATH,
    WRITTEN,
    AgentUpgrades,
    Reading,
)
from brain.agents.creation import AGENT_INSTALL_CAPABILITY
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY, ARCHIVE_IS_TERMINAL
from brain.agents.model import AgentRecord, AgentState
from brain.agents.template import SignedManifest, TemplateManifest, publish
from brain.agents.upgrade import Decline, Declines, Upgraded, VersionShelf
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.builder.agent_drafts import NOT_THE_AUTHOR, NOT_WITHIN_YOUR_REACH
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_agent_lifecycle_routes import (
    COMPANY,
    LOOSE,
    PRIVATE,
    RETIRED,
    SALES,
    VERSION,
    WEB,
    everybody,
    manifest,
    tools,
)
from tests.unit.test_agent_routes import KEY

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NEWER_AT = datetime(2019, 6, 1, 9, 0)

EVERYWHERE = Scope.unrestricted()
READS = tuple(
    Grant(capability=Capability(value=one), scope=EVERYWHERE)
    for one in ("read:invoice", "read:invoice.reference", "read:invoice.total")
)

#: `u_admin` holds the lifecycle authority everywhere and reads no invoice. `u_prefix` holds it
#: everywhere and reads invoices, so can approve a version that reaches further. `u_narrow` holds it
#: in web alone. `u_wide` and `u_none` hold nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (
        Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=EVERYWHERE),
        Grant(capability=AGENT_INSTALL_CAPABILITY, scope=EVERYWHERE),
    ),
    "u_prefix": (Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=EVERYWHERE), *READS),
    "u_narrow": (Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=Scope.department("web")),),
    "u_wide": (),
    "u_none": (),
    "u_elsewhere": (),
}

NEWER_PERSONA = "Answer in full sentences and name the invoice you read."
AT = datetime(2019, 6, 2, 9, 0)


def newer(
    *,
    version: int = VERSION + 1,
    rung: AutonomyTier = AutonomyTier.SHADOW,
    capabilities: tuple[str, ...] = ("read:invoice.reference",),
    published_by: str = "u_publisher",
) -> SignedManifest:
    """The next version of the template: another persona, and optionally a rung or a reach."""
    base: TemplateManifest = manifest(rung)
    wider = base.authority.model_copy(
        update={"capabilities": tuple(Capability(value=one) for one in capabilities)}
    )
    document = base.model_copy(
        update={
            "persona": NEWER_PERSONA,
            "authority": wider,
            "identity": base.identity.model_copy(
                update={"version": version, "published_by": published_by}
            ),
        }
    )
    from datetime import UTC

    return publish(document, key=KEY, signed_by=published_by, at=NEWER_AT.replace(tzinfo=UTC))


@dataclass
class Accepted:
    upgraded: Upgraded
    from_version: int
    expected_hash: str
    disabled_at: datetime | None
    actor_id: str
    ent_hash: str


@dataclass
class Memory:
    """`AgentUpgrades` in memory, and every write it was asked for."""

    agents: dict[str, FoundAgent] = field(default_factory=everybody)
    versions: dict[tuple[str, int], SignedManifest] = field(default_factory=dict)
    declines: Declines = field(default_factory=Declines)
    accepted: list[Accepted] = field(default_factory=list)
    declined: list[tuple[Decline, str]] = field(default_factory=list)
    #: When true, every acceptance loses a race to somebody else's.
    racing: bool = False

    async def read(self, agent_id: str) -> Reading | None:
        found = self.agents.get(agent_id)
        if found is None:
            return None
        shelf = VersionShelf()
        if found.install is not None:
            shelf.publish(found.install[0])
            pinned = found.install[0].manifest.identity.version
            later = [
                one
                for (template, version), one in self.versions.items()
                if template == found.install[0].manifest.identity.template_id and version > pinned
            ]
            for one in sorted(later, key=lambda signed: signed.manifest.identity.version)[-1:]:
                shelf.publish(one)
        return Reading(found=found, shelf=shelf, declines=self.declines)

    async def accept(
        self,
        upgraded: Upgraded,
        *,
        from_version: int,
        expected_hash: str,
        disabled_at: datetime | None,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        if self.racing:
            return False
        agent_id = upgraded.instance.instance_id
        held = self.agents[agent_id]
        moved_to = self.versions[
            (upgraded.instance.template_id, upgraded.instance.template_version)
        ]
        self.agents[agent_id] = FoundAgent(
            record=upgraded.record.model_copy(
                update={
                    "audience": held.record.audience,
                    "created_by": held.record.created_by,
                    "disabled_at": disabled_at,
                }
            ),
            install=(moved_to, upgraded.instance),
            effective_hash=upgraded.effective.config_hash,
        )
        self.accepted.append(
            Accepted(upgraded, from_version, expected_hash, disabled_at, actor_id, ent_hash)
        )
        return True

    async def decline(self, made: Decline, *, actor_id: str, ent_hash: str, trace_id: str) -> bool:
        self.declined.append((made, actor_id))
        return True


@dataclass
class Console:
    client: TestClient
    app: FastAPI
    memory: Memory

    def post(self, pid: str, path: str, body: Mapping[str, Any]) -> Any:
        return self.client.post(f"{API_PREFIX}{path}", json=dict(body), headers=headers(pid))

    def get(self, pid: str, path: str) -> Any:
        return self.client.get(f"{API_PREFIX}{path}", headers=headers(pid))


def on_offer(memory: Memory, *versions: SignedManifest) -> None:
    for one in versions:
        memory.versions[(one.manifest.identity.template_id, one.manifest.identity.version)] = one


@pytest.fixture
def console() -> Iterator[Console]:
    """The real application, with the memory holding version 3, a signing key and one source."""
    app = create_app(Settings(env="development"))
    memory = Memory()
    on_offer(memory, newer())
    assert isinstance(memory, AgentUpgrades)
    with TestClient(app) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = None
        app.state.agent_upgrades = memory
        app.state.template_key = KEY
        app.state.tools = tools("ledger")
        yield Console(client=client, app=app, memory=memory)


def at(template: str, **values: object) -> str:
    return template.format(**values)


def reviewed(console: Console, agent_id: str = COMPANY, pid: str = "u_admin") -> dict[str, Any]:
    response = console.get(pid, at(UPGRADE_PATH, agent_id=agent_id))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def accepting(review: Mapping[str, Any], **resolutions: str) -> dict[str, Any]:
    """The body a page sends: the version and the configuration it drew, and the answers."""
    return {
        "to_version": review["to_version"],
        "expected_hash": review["expected_hash"],
        "resolutions": {
            **{one["path"]: "take_template" for one in review["conflicts"]},
            **{path.replace("__", "."): how for path, how in resolutions.items()},
        },
    }


def not_changed(response: Any) -> tuple[int, str, str]:
    body = response.json()
    return response.status_code, body["outcome"], body["sentence"]


def record_of_agent(console: Console, agent_id: str = COMPANY) -> AgentRecord:
    return console.memory.agents[agent_id].record


# ------------------------------------------------------------------------- the review
def test_a_review_names_the_version_on_offer_and_what_it_moves(console: Console) -> None:
    """The badge says a version is available, the review carries the version and the
    configuration it was drawn against, the persona this install had claimed is a conflict in three
    columns with its owner, and every other moved path is an update that nobody has to decide.

    Delete this and the page has nothing to draw an upgrade from, or draws a conflict as an update
    and takes the template's words over the installer's with nobody asked."""
    review = reviewed(console)

    assert (review["badge"], review["from_version"], review["to_version"]) == (
        "available",
        VERSION,
        VERSION + 1,
    )
    assert review["expected_hash"] == console.memory.agents[COMPANY].effective_hash
    [conflict] = review["conflicts"]
    assert conflict["path"] == "persona"
    assert conflict["now"] == NEWER_PERSONA
    assert conflict["was"] != conflict["local"] != conflict["now"]
    assert conflict["owner"]["set_by"]
    assert "persona" not in {one["path"] for one in review["updates"]}
    assert {"identity.version"} <= {one["path"] for one in review["updates"] if one["sealed"]}
    assert review["accept_unavailable"] is None


def test_an_agent_on_the_newest_version_has_nothing_to_review(console: Console) -> None:
    """With nothing newer shelved the badge is current, there is no version to name, and accepting
    is refused in words rather than moving the pin to itself.

    Delete this and an agent with no upgrade shows a badge, or accepting a non-upgrade writes."""
    console.memory.versions.clear()
    review = reviewed(console)

    assert (review["badge"], review["to_version"], review["conflicts"]) == ("current", None, [])
    refused = console.post(
        "u_admin", at(ACCEPT_PATH, agent_id=COMPANY), {"to_version": 3, "expected_hash": "0" * 64}
    )
    assert not_changed(refused) == (409, REFUSED, NOTHING_TO_UPGRADE)
    assert console.memory.accepted == []


def test_an_agent_with_no_install_says_there_is_nothing_to_upgrade(console: Console) -> None:
    """An agent never installed from a version has no pin to move: the review says so and
    accepting is refused in the same words.

    Delete this and the page renders an upgrade for an agent that has no lineage."""
    review = reviewed(console, LOOSE)
    assert review["nothing"] == NO_INSTALL_TO_UPGRADE and review["to_version"] is None
    refused = console.post(
        "u_admin", at(DECLINE_PATH, agent_id=LOOSE), {"to_version": 3, "expected_hash": "0" * 64}
    )
    assert not_changed(refused) == (409, REFUSED, NO_INSTALL_TO_UPGRADE)


@pytest.mark.parametrize(
    "pid, agent_id",
    [
        ("u_none", COMPANY),
        ("u_wide", COMPANY),
        ("u_narrow", SALES),
        ("u_narrow", COMPANY),
        ("u_admin", PRIVATE),
        ("u_admin", "no_such_agent"),
    ],
)
def test_who_may_not_act_on_an_agent_and_an_agent_that_is_not_there_are_one_answer(
    console: Console, pid: str, agent_id: str
) -> None:
    """A caller with no authority, one whose authority is another department's, one whose authority
    is a department's over an agent that is the whole company's, one whose audience does not cover
    the agent and a name that does not exist each get the same 404 on the review,
    on accepting and on declining, and nothing is written.

    Delete this and the upgrade routes tell a person which agents exist and what they are made
    from."""
    body = {"to_version": 3, "expected_hash": "0" * 64}
    answers = [
        console.get(pid, at(UPGRADE_PATH, agent_id=agent_id)),
        console.post(pid, at(ACCEPT_PATH, agent_id=agent_id), body),
        console.post(pid, at(DECLINE_PATH, agent_id=agent_id), body),
    ]
    missing = console.get("u_none", at(UPGRADE_PATH, agent_id="no_such_agent"))

    assert [one.status_code for one in answers] == [404, 404, 404]
    assert {one.json()["message"] for one in answers} == {missing.json()["message"]}
    assert console.memory.accepted == [] and console.memory.declined == []


def test_the_authority_over_one_departments_agents_reaches_exactly_those(console: Console) -> None:
    """The positive sibling: the web administrator reviews and declines the web agent, and is
    refused only the other department's.

    Delete this and the refusals above are satisfied by routes that refuse everybody."""
    assert reviewed(console, WEB, "u_narrow")["badge"] == "available"
    declined = console.post(
        "u_narrow",
        at(DECLINE_PATH, agent_id=WEB),
        {"to_version": 3, "expected_hash": console.memory.agents[WEB].effective_hash},
    )
    assert declined.status_code == 200


# ----------------------------------------------------------------------- accepting
def test_accepting_takes_the_versions_value_and_hands_the_store_what_it_must_compare(
    console: Console,
) -> None:
    """Resolving the persona to the template's words moves the pin, the agent's persona and the
    configuration hash; the store is handed the hash and version the page drew, the person who
    pressed and the request's reach digest, and the review afterwards is current.

    Delete this and the upgrade moves nothing, or moves it without naming who, or without the
    comparison that stops two people both winning."""
    review = reviewed(console)
    response = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "upgraded" and response.json()["sentence"] == WRITTEN
    [done] = console.memory.accepted
    assert (done.from_version, done.expected_hash, done.actor_id) == (
        VERSION,
        review["expected_hash"],
        "u_admin",
    )
    assert len(done.ent_hash) == 32
    moved = console.memory.agents[COMPANY]
    assert moved.install is not None
    assert moved.install[1].template_version == VERSION + 1
    assert record_of_agent(console).persona == NEWER_PERSONA
    assert moved.effective_hash != review["expected_hash"]
    assert reviewed(console)["badge"] == "current"


def test_keeping_the_local_value_keeps_the_installers_words(console: Console) -> None:
    """Resolving the persona to keep_local moves the pin and leaves the persona as it was.

    Delete this and every upgrade overwrites a local edit, whatever was chosen."""
    review = reviewed(console)
    before = record_of_agent(console).persona
    response = console.post(
        "u_admin",
        at(ACCEPT_PATH, agent_id=COMPANY),
        accepting(review, persona="keep_local"),
    )

    assert response.status_code == 200, response.text
    assert record_of_agent(console).persona == before != NEWER_PERSONA
    moved = console.memory.agents[COMPANY].install
    assert moved is not None and moved[1].template_version == VERSION + 1


def test_a_conflict_nobody_answered_is_refused_in_the_domains_words_and_writes_nothing(
    console: Console,
) -> None:
    """No resolution for the one conflict, and a resolution for a path that is not in conflict,
    are each refused with the domain's sentence, one path at a time.

    Delete this and an upgrade silently decides a conflict for the person, or a decision about
    something nobody was shown is accepted."""
    review = reviewed(console)
    unanswered = console.post(
        "u_admin",
        at(ACCEPT_PATH, agent_id=COMPANY),
        {"to_version": 3, "expected_hash": review["expected_hash"], "resolutions": {}},
    )
    unasked = console.post(
        "u_admin",
        at(ACCEPT_PATH, agent_id=COMPANY),
        accepting(review, tier="keep_local"),
    )

    for refused in (unanswered, unasked):
        assert refused.status_code == 409 and refused.json()["outcome"] == REFUSED
        assert "one conflicting path at a time" in refused.json()["sentence"]
    assert console.memory.accepted == []


def test_a_page_that_went_stale_is_told_so_and_nothing_is_written(console: Console) -> None:
    """The configuration moved since the page was drawn, a newer version replaced the one drawn,
    and the write lost a race: each is a 409 with one sentence and no change.

    Delete this and an acceptance acts on a diff the person never saw."""
    review = reviewed(console)
    body = accepting(review)

    moved = console.post(
        "u_admin", at(ACCEPT_PATH, agent_id=COMPANY), {**body, "expected_hash": "0" * 64}
    )
    other = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), {**body, "to_version": 9})
    console.memory.racing = True
    raced = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), body)

    for stale in (moved, other, raced):
        assert not_changed(stale) == (409, MOVED, IT_MOVED)
    assert console.memory.accepted == []


def test_an_archived_agent_is_not_upgraded(console: Console) -> None:
    """The review says why accepting is unavailable and accepting is refused with the domain's
    sentence about an archived agent.

    Delete this and an archived agent, which is terminal, is given a new configuration."""
    review = reviewed(console, RETIRED)
    assert review["accept_unavailable"] == ARCHIVE_IS_TERMINAL
    refused = console.post("u_admin", at(ACCEPT_PATH, agent_id=RETIRED), accepting(review))
    assert not_changed(refused) == (409, REFUSED, ARCHIVE_IS_TERMINAL)
    assert console.memory.accepted == []


def test_a_process_with_no_signing_key_says_so_and_still_lets_a_decline_through(
    console: Console,
) -> None:
    """Accepting becomes configuration only after the install's key has verified the version, so
    without one the review says accepting is unavailable and accepting says so; declining needs no
    key.

    Delete this and an unverified version is applied, or a person who cannot accept cannot say
    no."""
    console.app.state.template_key = None
    review = reviewed(console)
    assert review["accept_unavailable"] == NO_SIGNING_KEY_HERE
    refused = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))
    assert not_changed(refused) == (409, UNAVAILABLE, NO_SIGNING_KEY_HERE)
    declined = console.post(
        "u_admin",
        at(DECLINE_PATH, agent_id=COMPANY),
        {"to_version": review["to_version"], "expected_hash": review["expected_hash"]},
    )
    assert declined.status_code == 200 and console.memory.accepted == []


# -------------------------------------------------------------------- never a higher rung
def test_a_version_that_would_raise_a_rung_cannot_be_accepted_but_can_be_declined(
    console: Console,
) -> None:
    """**An upgrade never raises an autonomy rung.** A version holding the agent's tool at a
    higher rung is shown with the reason accepting is unavailable, accepting it is refused in the
    rule's words with nothing written, and declining it is allowed and recorded, after which the
    badge is declined. The positive sibling is the other tests here: the same agent accepts the
    same version at Shadow.

    Delete this and accepting a published version carries autonomy into every agent that takes
    it, which the agent never earned."""
    console.memory.versions.clear()
    on_offer(console.memory, newer(rung=AutonomyTier.ASSISTED))
    review = reviewed(console)
    assert review["accept_unavailable"] == THIS_RAISES_A_RUNG

    refused = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))
    assert not_changed(refused) == (409, REFUSED, THIS_RAISES_A_RUNG)
    assert console.memory.accepted == []

    declined = console.post(
        "u_admin",
        at(DECLINE_PATH, agent_id=COMPANY),
        {"to_version": review["to_version"], "expected_hash": review["expected_hash"]},
    )
    assert declined.status_code == 200
    assert declined.json()["outcome"] == "declined" and declined.json()["sentence"] == DECLINED
    [(made, who)] = console.memory.declined
    assert (made.version, who) == (VERSION + 1, "u_admin")
    assert reviewed(console)["badge"] == "declined"


# ------------------------------------------------------------------- reaching further
def test_a_version_that_reaches_further_waits_for_somebody_who_could_have_written_it(
    console: Console,
) -> None:
    """A version adding a capability the person accepting does not hold is refused in the builder's
    words, without naming what they lack; somebody holding all of it accepts it; and the person who
    published it may not be the one to accept it. The same version that reaches no further is
    accepted by anybody holding the authority.

    Delete this and an upgrade is a way to widen an agent past what anybody who accepts it could
    have written."""
    console.memory.versions.clear()
    on_offer(
        console.memory,
        newer(capabilities=("read:invoice.reference", "read:invoice.total")),
    )
    review = reviewed(console)

    short = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))
    assert not_changed(short) == (409, REFUSED, NOT_WITHIN_YOUR_REACH)
    assert console.memory.accepted == []

    holding = console.post("u_prefix", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))
    assert holding.status_code == 200, holding.text

    console.memory.agents = everybody()
    console.memory.versions.clear()
    on_offer(
        console.memory,
        newer(
            capabilities=("read:invoice.reference", "read:invoice.total"), published_by="u_prefix"
        ),
    )
    review = reviewed(console)
    own = console.post("u_prefix", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))
    assert not_changed(own) == (409, REFUSED, NOT_THE_AUTHOR)


# --------------------------------------------------------------------------- declining
def test_a_decline_is_recorded_for_the_version_and_a_second_press_is_the_same_answer(
    console: Console,
) -> None:
    """Declining names the person and the version, quiets the badge to declined, and pressing it
    again says the same thing and writes the one decline; the review still shows what was turned
    down, and a decline of a stale page is refused.

    Delete this and a no is forgotten, or recorded against the wrong version, or lost for the
    review."""
    review = reviewed(console)
    body = {"to_version": review["to_version"], "expected_hash": review["expected_hash"]}
    first = console.post("u_admin", at(DECLINE_PATH, agent_id=COMPANY), body)
    again = console.post("u_admin", at(DECLINE_PATH, agent_id=COMPANY), body)

    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert {(made.version, who) for made, who in console.memory.declined} == {
        (VERSION + 1, "u_admin")
    }
    after = reviewed(console)
    assert after["badge"] == "declined" and len(after["conflicts"]) == 1
    stale = console.post(
        "u_admin", at(DECLINE_PATH, agent_id=COMPANY), {**body, "expected_hash": "0" * 64}
    )
    assert not_changed(stale) == (409, MOVED, IT_MOVED)


def test_a_declined_version_can_still_be_accepted(console: Console) -> None:
    """A decline is a decision not to be nagged and not a decision never to look.

    Delete this and declining closes the door on a version somebody later wants."""
    review = reviewed(console)
    console.post(
        "u_admin",
        at(DECLINE_PATH, agent_id=COMPANY),
        {"to_version": review["to_version"], "expected_hash": review["expected_hash"]},
    )
    after = reviewed(console)
    assert after["badge"] == "declined"
    accepted = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), accepting(after))
    assert accepted.status_code == 200 and reviewed(console)["badge"] == "current"


def test_an_acceptance_that_leaves_the_agent_incomplete_switches_it_off(console: Console) -> None:
    """A version declaring a tool nothing on the install provides is accepted and the agent is
    switched off with the sentence saying so, as an install of it would be; one that stays
    complete leaves it as it was.

    Delete this and an upgraded agent that cannot run is left enabled."""
    review = reviewed(console)
    console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))
    assert record_of_agent(console).state is AgentState.ENABLED
    [done] = console.memory.accepted
    assert done.disabled_at is None

    console.memory.agents = everybody()
    console.memory.versions.clear()
    base = newer()
    declaring = base.manifest.model_copy(
        update={
            "authority": base.manifest.authority.model_copy(
                update={"allowed_tools": ("invoice.read", "no.such_tool")}
            )
        }
    )
    on_offer(
        console.memory, publish(declaring, key=KEY, signed_by="u_publisher", at=base.signed_at)
    )
    review = reviewed(console)
    response = console.post("u_admin", at(ACCEPT_PATH, agent_id=COMPANY), accepting(review))

    assert response.status_code == 200, response.text
    assert response.json()["switched_off"] is True
    assert record_of_agent(console).state is AgentState.DISABLED
