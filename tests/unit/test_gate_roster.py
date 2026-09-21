"""The roster `/answer` selects from, the reach a selected agent answers at, and the answer store.

Pure: `brain.gate.roster` over hand-built agent records, and `brain.gate.front.remember` over the
chain's own output. The route-level proofs are in `tests/unit/test_answer_route_gate.py`.

Task ids: M3.9.8, M3.5.2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.cache_key import CachedAnswer
from brain.gate.catalogue import AgentCeiling
from brain.gate.context import Channel, GateStep, open_trace
from brain.gate.front import AgentSetup, Caching, Choosing, FrontHalf, remember, run_front_half
from brain.gate.roster import answer_roster, run_entitlement, setup_of, viewer_for
from brain.knowledge.visibility import Visibility

#: Far from any wall clock, for the reason CLAUDE.md gives about fixtures with dates in them.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)

DEFAULT = {"brain": AgentSetup(AgentCeiling(agent_id="brain", allowed_tools=frozenset()), "cfg")}
TOOLS = ("crm.read_client",)


def an_agent(
    agent_id: str = "helper",
    *,
    level: Visibility = Visibility.COMPANY,
    owner_id: str = "u_steward",
    persona: str = "Answer briefly.",
    capabilities: tuple[str, ...] = ("read:client.name",),
    disabled: bool = False,
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name=agent_id.title(),
        persona=persona,
        audience=AgentAudience(level=level, owner_id=owner_id),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by=owner_id,
        disabled_at=LONG_AGO if disabled else None,
    )


def reach(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope()) for one in capabilities
        ),
    )


VIEWER = viewer_for(
    Principal(
        id="u_reader",
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="Reader",
        primary_department="web",
    )
)


def test_the_roster_holds_the_default_and_every_agent_the_person_may_run() -> None:
    """A company agent is offered beside the default; somebody else's personal agent and a
    disabled one are not in the roster at all, so a name for either finds nothing.

    Delete this and `/answer` can offer an agent the person may not use, which then answers."""
    roster = answer_roster(
        (
            an_agent("helper"),
            an_agent("secret", level=Visibility.PERSONAL, owner_id="u_other"),
            an_agent("resting", disabled=True),
        ),
        VIEWER,
        default=DEFAULT,
        tool_names=TOOLS,
    )
    assert roster.visible == {"brain", "helper"}
    assert set(roster.records) == {"helper"}


def test_a_personal_agent_is_in_its_owners_roster_and_a_department_agent_in_its_members() -> None:
    """The positive siblings: the owner of a personal agent may run it, and a member of the
    department a department agent serves may run that, because the viewer is their primary
    department; another department's agent is not offered."""
    mine = an_agent("mine", level=Visibility.PERSONAL, owner_id="u_reader")
    ours = an_agent("ours").model_copy(
        update={
            "audience": AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_s", department="web")
        }
    )
    theirs = an_agent("theirs").model_copy(
        update={
            "audience": AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_s", department="hr")
        }
    )
    roster = answer_roster((mine, ours, theirs), VIEWER, default=DEFAULT, tool_names=TOOLS)
    assert roster.visible == {"brain", "mine", "ours"}


def test_a_selected_agent_answers_at_the_callers_reach_intersected_with_its_ceiling() -> None:
    """The run reach keeps what both hold and nothing either lacks, and the default agent, which
    is the person, answers at their own reach unchanged.

    Delete this and a stored agent can answer at the caller's whole reach."""
    caller = reach("read:client.name", "read:client.contract_value")
    ran = run_entitlement(caller, an_agent(capabilities=("read:client.name",)))
    held = {grant.capability.value for grant in ran.grants}
    assert "read:client.name" in held
    assert "read:client.contract_value" not in held
    assert ran.principal_id == caller.principal_id
    assert run_entitlement(caller, None) is caller


def test_an_agents_cache_hash_moves_with_its_persona_and_with_the_registry() -> None:
    """A changed persona or a changed set of registered tools is a different key, and an
    unchanged agent is the same one.

    Delete this and an answer cached through yesterday's agent is served through today's."""
    base = setup_of(an_agent(), TOOLS).config_hash
    assert setup_of(an_agent(), TOOLS).config_hash == base
    assert setup_of(an_agent(persona="Answer at length."), TOOLS).config_hash != base
    assert setup_of(an_agent(), (*TOOLS, "crm.write_client")).config_hash != base


class Store:
    def __init__(self) -> None:
        self.data: dict[str, CachedAnswer] = {}

    def get(self, key: str) -> CachedAnswer | None:
        return self.data.get(key)

    def set(self, key: str, value: CachedAnswer, ttl_seconds: int) -> None:
        del ttl_seconds
        self.data[key] = value


def _front(question: str, caching: Caching, now: datetime, who: EntitlementSet) -> FrontHalf:
    recorder = open_trace("t-remember", now, Channel.CONSOLE)
    recorder.enter(GateStep.IDENTIFY)
    recorder.enter(GateStep.ENTITLE)
    return run_front_half(
        question,
        recorder=recorder,
        reach=who,
        channel=Channel.CONSOLE,
        agents=DEFAULT,
        choosing=Choosing(visible_agents=frozenset(DEFAULT), default_agent="brain"),
        registry=(),
        now=now,
        caching=caching,
    )


def test_an_answer_remembered_is_found_by_the_next_lookup_and_a_hit_is_not_stored_again() -> None:
    """`remember` stores under the parts the lookup used, so the next front half finds it; the
    hit it finds is not stored again, which would reset its age.

    Delete this and the store and the lookup can build their keys from different parts, and the
    cache fills with answers nobody ever finds."""
    store = Store()
    caching = Caching(store=store, policy_epoch=3)
    who = reach("read:client.name")
    first = _front("who owns Acme", caching, NOW, who)
    assert remember("who owns Acme", "Dana.", front=first, reach=who, caching=caching, now=NOW)

    later = NOW + timedelta(minutes=2)
    second = _front("who owns Acme", caching, later, who)
    assert second.cached is not None
    assert second.cached.payload == "Dana."
    assert (
        remember("who owns Acme", "x", front=second, reach=who, caching=caching, now=later) is None
    )
    assert next(iter(store.data.values())).stored_at == NOW


def test_nothing_is_remembered_without_a_store() -> None:
    """A process with no answer store keeps nothing and says so with None."""
    caching = Caching(store=Store(), policy_epoch=0)
    who = reach("read:client.name")
    front = _front("who owns Acme", caching, NOW, who)
    assert remember("who owns Acme", "Dana.", front=front, reach=who, caching=None, now=NOW) is None
