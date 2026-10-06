"""The roster `/answer` selects from, the reach a selected agent answers at, and the answer store.

Pure: `brain.gate.roster` over hand-built agent records, and `brain.gate.front.remember` over the
chain's own output. The route-level proofs are in `tests/unit/test_answer_route_gate.py`.

Task ids: M3.9.8, M3.5.2, M13.2.5
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.agents.template import EffectiveAgent, LeashRung, SignedManifest, SkillRef, materialise
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.cache_key import CachedAnswer, key_for
from brain.gate.catalogue import AgentCeiling
from brain.gate.context import Channel, GateStep, open_trace
from brain.gate.front import AgentSetup, Caching, Choosing, FrontHalf, remember, run_front_half
from brain.gate.injection import AutonomyTier
from brain.gate.roster import answer_roster, run_entitlement, setup_of, viewer_for
from brain.knowledge.visibility import Visibility
from tests.unit.test_agent_template import (
    AUDIENCE,
    SKILL_DIGEST,
    _installed,
    _manifest,
    _signed,
)

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
    channels: tuple[str, ...] = ("console",),
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name=agent_id.title(),
        persona=persona,
        audience=AgentAudience(level=level, owner_id=owner_id),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by=owner_id,
        disabled_at=LONG_AGO if disabled else None,
        channels=channels,
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
        channel=Channel.CONSOLE,
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
    roster = answer_roster(
        (mine, ours, theirs), VIEWER, channel=Channel.CONSOLE, default=DEFAULT, tool_names=TOOLS
    )
    assert roster.visible == {"brain", "mine", "ours"}


def test_an_agent_not_enabled_on_the_requests_channel_is_not_in_its_roster() -> None:
    """**M13.7.4.** An agent switched on for Lark alone is in a Lark question's roster and not in a
    console question's, and an agent switched on for nothing is in neither, so a name for it on the
    wrong channel finds what a name nobody created finds.

    Delete this and an agent answers on a channel nobody enabled it on, which is the leaf's whole
    refusal gone with every other test still green."""
    agents = (
        an_agent("lark_only", channels=("lark",)),
        an_agent("both", channels=("console", "lark")),
        an_agent("mute", channels=()),
    )

    def roster_on(channel: Channel) -> frozenset[str]:
        return answer_roster(
            agents, VIEWER, channel=channel, default=DEFAULT, tool_names=TOOLS
        ).visible

    assert roster_on(Channel.LARK) == {"brain", "lark_only", "both"}
    assert roster_on(Channel.CONSOLE) == {"brain", "both"}
    assert roster_on(Channel.SLACK) == {"brain"}


def test_an_agent_enabled_on_a_channel_is_still_held_to_its_audience_there() -> None:
    """Being switched on for a channel admits nobody: somebody else's personal agent enabled on the
    console is still not in this person's console roster. Delete this and enabling a channel could
    be read as publishing the agent to everybody who asks there."""
    secret = an_agent("secret", level=Visibility.PERSONAL, owner_id="u_other")
    roster = answer_roster(
        (secret,), VIEWER, channel=Channel.CONSOLE, default=DEFAULT, tool_names=TOOLS
    )
    assert roster.visible == {"brain"}


def test_one_agents_cache_key_does_not_depend_on_the_order_its_channels_arrived_in() -> None:
    """Two records built from the same channels in different orders, with a repeat, are one value
    and one `setup_of` hash. Delete this and a set of channels dumped in iteration order gives one
    agent a different cache key on every replica, so an answer computed on one is never served on
    another."""
    one = an_agent(channels=("teams", "console", "lark"))
    other = an_agent(channels=("lark", "teams", "console", "lark"))
    assert one == other
    assert one.channels == ("console", "lark", "teams")
    assert setup_of(one, TOOLS).config_hash == setup_of(other, TOOLS).config_hash
    assert setup_of(an_agent(channels=("console",)), TOOLS).config_hash != (
        setup_of(one, TOOLS).config_hash
    )


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


# --------------------------------------------- M13.2.5 the install's stored hash is the key
def _manifest_with(
    *,
    leash: tuple[LeashRung, ...] = (),
    skills: tuple[SkillRef, ...] | None = None,
    connectors: tuple[str, ...] | None = None,
) -> SignedManifest:
    """The template tests' own manifest, signed, with only the named part changed."""
    base = _manifest(leash=leash)
    changes: dict[str, object] = {}
    if skills is not None:
        changes["skills"] = skills
    if connectors is not None:
        changes["connectors"] = connectors
    return _signed(base.model_copy(update=changes))


def _effective_of(signed: SignedManifest) -> EffectiveAgent:
    return materialise(signed, _installed(signed), audience=AUDIENCE)


def _key_through(effective: EffectiveAgent, *, with_install_hash: bool = True) -> str:
    """The cache key `/answer` computes for one question through one materialised install.

    The record and the stored hash go through `setup_of` exactly as the roster reads them, and
    the key is the real one.
    """
    setup = setup_of(effective.record, TOOLS, effective.config_hash if with_install_hash else None)
    return key_for("what is the retainer", "e" * 32, setup.config_hash, 4, {"laravel": 7})


RAISED = (LeashRung(target="client.read_summary", scope=Scope(), rung=AutonomyTier.ASSISTED),)
OTHER_SKILL = (SkillRef(name="other_playbook", digest=SKILL_DIGEST),)


def test_a_changed_leash_or_skill_or_connector_moves_the_answer_cache_key() -> None:
    """Each of the three changes, made on a manifest, gives a different key, and the unchanged
    install gives the same one twice. The leash and the pinned skills are not on the agent
    record at all, so only the install's stored hash can move the key for them.

    Delete this and `/answer` can serve an answer cached before an agent's leash was raised, a
    skill was assigned or a connector was switched, through the agent as it is now."""
    base = _key_through(_effective_of(_manifest_with()))
    assert _key_through(_effective_of(_manifest_with())) == base
    assert _key_through(_effective_of(_manifest_with(leash=RAISED))) != base
    assert _key_through(_effective_of(_manifest_with(skills=OTHER_SKILL))) != base
    assert _key_through(_effective_of(_manifest_with(connectors=("hubspot",)))) != base


def test_the_record_alone_does_not_see_a_leash_or_a_skill_so_the_install_hash_is_what_moves() -> (
    None
):
    """Without the install's hash two agents whose leashes, or whose skills, differ hash the
    same, which is the defect this leaf closes; with it they do not.

    Delete this and the test above can pass on a fixture whose change is also visible on the
    record, which would leave the install hash decorative."""
    plain = _effective_of(_manifest_with())
    for other in (
        _effective_of(_manifest_with(leash=RAISED)),
        _effective_of(_manifest_with(skills=OTHER_SKILL)),
    ):
        assert _key_through(plain, with_install_hash=False) == _key_through(
            other, with_install_hash=False
        )
        assert _key_through(plain) != _key_through(other)


def test_the_roster_keys_each_agent_on_its_own_install_hash_and_one_without_still_answers() -> None:
    """Each agent's roster hash is `setup_of` over its own record and its own install hash, an
    agent with no install row is in the roster hashed on its record alone, and the install hash
    does change the roster's hash.

    Delete this and the hashes are applied to the wrong agent, left off, or an agent without an
    install drops out of the roster."""
    one, two, bare = an_agent("one"), an_agent("two"), an_agent("bare")
    roster = answer_roster(
        (one, two, bare),
        VIEWER,
        channel=Channel.CONSOLE,
        default=DEFAULT,
        tool_names=TOOLS,
        install_hashes={"one": "a" * 64, "two": "b" * 64},
    )
    assert roster.visible == {"brain", "one", "two", "bare"}
    assert roster.agents["one"].config_hash == setup_of(one, TOOLS, "a" * 64).config_hash
    assert roster.agents["two"].config_hash == setup_of(two, TOOLS, "b" * 64).config_hash
    assert roster.agents["bare"].config_hash == setup_of(bare, TOOLS).config_hash
    assert roster.agents["one"].config_hash != setup_of(one, TOOLS).config_hash
