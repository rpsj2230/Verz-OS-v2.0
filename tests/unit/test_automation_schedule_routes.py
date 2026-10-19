"""An agent's installed automations on its Automations tab, and the confirmed start and stop.

`brain.console.automation_schedule` decides who may start or stop an automation and what a
confirmation is over, and `brain.automation_schedule_routes` asks those questions in order over
stores handed in on `app.state`. The first half here holds the decisions over values; the second
drives the routes through the application's own authentication, as
`tests/unit/test_automation_gallery_routes.py` drives the gallery. What the store writes, and the
ledger entry its row appends, are `tests/unit/test_automation_run_store.py`'s.

Task ids: M39.6.1.4, M39.6.1.5, M39.6.2.2, M38.2.2.5, M39.9.2.3
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import automation_schedule_routes as routes
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.agent_automations import SCHEDULE_CAPABILITY, Automation, SchedulerChange
from brain.console.automation_gallery import AUTOMATION_AUTHORITY, BUILT_IN
from brain.console.automation_schedule import (
    A_START_IS_APPROVED_BY_SOMEBODY_IT_DOES_NOT_RUN_AS,
    NotConfirmedError,
    ScheduleControlError,
    ScheduleShown,
    cannot_start_because,
    changed,
    may_start,
    may_stop,
    shown_start,
    shown_stop,
)
from brain.console.automations import LEAVES_NO_NEXT_RUN, ChangeKind
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.identity.bearer import TokenAuthority
from brain.knowledge.visibility import Visibility
from brain.ops.automation_run import PausedBecause, RunOutcome, RunRecord, run_id
from brain.ops.automation_run_store import Listed
from brain.tables.automation_run import STARTED
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SUBJECTS,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)

AGENT = "quote_helper"
QUESTIONS = next(one for one in BUILT_IN if one.task == "automation.unanswered_questions")
SUMMARY = next(one for one in BUILT_IN if one.task == "automation.work_summary")

LIST = f"{API_PREFIX}/agents/{{agent}}/automations"
START = f"{API_PREFIX}/agents/{{agent}}/automations/{{automation}}/start"
STOP = f"{API_PREFIX}/agents/{{agent}}/automations/{{automation}}/stop"

EVERYWHERE = Scope.unrestricted()
TAB_READ = tab(Tab.AUTOMATIONS).read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)


def grant(capability: Capability | str, scope: Scope = EVERYWHERE) -> Grant:
    value = capability if isinstance(capability, Capability) else Capability(value=capability)
    return Grant(capability=value, scope=scope)


def on_agent(agent_id: str) -> Scope:
    return Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value=agent_id),))


#: The owner opens the tab, whose read is the queue screen's; the approver holds the authority and
#: the queue screen's read; a colleague holds the queue read and no authority; a fourth opens the
#: tab and may see nobody else's scheduled work; the authority over another agent covers nothing
#: here.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_narrow": (grant(TAB_READ), grant(CONFIGURATION)),
    "u_admin": (
        grant(TAB_READ),
        grant(CONFIGURATION),
        grant(AUTOMATION_AUTHORITY),
        grant(SCHEDULE_CAPABILITY),
    ),
    "u_elsewhere": (grant(TAB_READ), grant(CONFIGURATION), grant(SCHEDULE_CAPABILITY)),
    # The tab's read is the queue screen's, so a reader who may open the tab and see nobody
    # else's scheduled work holds it in a scope naming only themselves.
    "u_wide": (
        grant(TAB_READ, Scope(clauses=(Clause(field="principal_id", op=Op.EQ, value="u_wide"),))),
        grant(CONFIGURATION),
    ),
    "u_prefix": (
        grant(TAB_READ),
        grant(CONFIGURATION),
        grant(SCHEDULE_CAPABILITY),
        grant(AUTOMATION_AUTHORITY, on_agent("some_other_agent")),
    ),
    "u_none": (),
}


def person(pid: str) -> Principal:
    return Principal(
        id=pid, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name=f"Person {pid}"
    )


def reach(pid: str) -> EntitlementSet:
    return EntitlementSet(principal_id=pid, grants=GRANTS[pid])


def an_agent(*capabilities: str) -> AgentRecord:
    return AgentRecord(
        agent_id=AGENT,
        display_name="Quote helper",
        persona="Answers briefly.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by="u_builder",
    )


READING_AGENT = an_agent("read:question", "read:client.name")


def an_automation(
    automation_id: str = "auto_one",
    *,
    owner: str = "u_narrow",
    template: Any = QUESTIONS,
    next_run_at: datetime | None = None,
) -> Automation:
    return Automation(
        automation_id=automation_id,
        agent_id=AGENT,
        name=template.name,
        runs_as=person(owner),
        task=template.task,
        next_run_at=next_run_at,
    )


# ------------------------------------------------------------------ the decisions
def test_a_start_needs_the_authority_over_the_automation_held_by_somebody_it_does_not_run_as() -> (
    None
):
    """The approver may start; the owner may not start their own even holding the authority; a
    colleague with no authority and an authority over another agent may not.

    Delete this and an automation's own principal could approve its own start, which is the gated
    change `A_START_IS_APPROVED_BY_SOMEBODY_IT_DOES_NOT_RUN_AS` exists to refuse."""
    one = an_automation()
    becomes = NOW + timedelta(days=1)
    assert may_start(one, reach("u_admin"), agent=READING_AGENT, becomes=becomes, now=NOW)
    assert not may_start(one, reach("u_elsewhere"), agent=READING_AGENT, becomes=becomes, now=NOW)
    assert not may_start(one, reach("u_prefix"), agent=READING_AGENT, becomes=becomes, now=NOW)
    own = an_automation(owner="u_admin")
    assert not may_start(own, reach("u_admin"), agent=READING_AGENT, becomes=becomes, now=NOW)
    assert "approving itself" in A_START_IS_APPROVED_BY_SOMEBODY_IT_DOES_NOT_RUN_AS


def test_a_running_automation_cannot_be_started_and_a_paused_one_cannot_be_stopped() -> None:
    """Delete this and a second start would move a running automation's next run, which is a
    schedule change nobody was shown."""
    running = an_automation(next_run_at=NOW + timedelta(hours=1))
    assert not may_start(
        running, reach("u_admin"), agent=READING_AGENT, becomes=NOW + timedelta(days=1), now=NOW
    )
    assert not may_stop(an_automation(), reach("u_narrow"), now=NOW)


def test_a_stop_is_the_owners_to_make_and_the_authoritys_and_nobody_elses() -> None:
    """Delete this and a stop would need an approver, or a colleague who may only see an automation
    could stop it."""
    running = an_automation(next_run_at=NOW + timedelta(hours=1))
    assert may_stop(running, reach("u_narrow"), now=NOW)
    assert may_stop(running, reach("u_admin"), now=NOW)
    assert not may_stop(running, reach("u_elsewhere"), now=NOW)
    assert not may_stop(running, reach("u_prefix"), now=NOW)


def test_a_task_the_install_cannot_perform_or_the_agent_cannot_read_cannot_be_started() -> None:
    """The work summary says what it needs, and an agent whose ceiling names no question read
    names the read it is missing. The positive case is the approver above.

    Delete this and a start would be offered that the first run refuses and pauses."""
    summary = an_automation(template=SUMMARY)
    said = cannot_start_because(summary, READING_AGENT, NOW)
    assert said is not None and "which agent each question was asked of" in said
    assert not may_start(
        summary, reach("u_admin"), agent=READING_AGENT, becomes=NOW + timedelta(days=1), now=NOW
    )
    blind = an_agent("read:client.name")
    said = cannot_start_because(an_automation(), blind, NOW)
    assert said is not None and said.endswith("read:question.")
    assert cannot_start_because(an_automation(), READING_AGENT, NOW) is None
    assert not may_start(
        an_automation(), reach("u_admin"), agent=blind, becomes=NOW + timedelta(days=1), now=NOW
    )


def test_a_confirmation_is_over_what_would_change_and_moves_when_any_of_it_does() -> None:
    """Delete this and a start confirmed before the cadence's hour went by would be written at a
    next run nobody saw, or a stop confirmed for one automation could stop another."""
    one = an_automation()
    start = shown_start(one, QUESTIONS.cadence, now=NOW)
    assert start.becomes is not None
    later = shown_start(one, QUESTIONS.cadence, now=start.becomes)
    assert later.confirmation != start.confirmation
    assert shown_start(
        replace(one, automation_id="auto_two"), QUESTIONS.cadence, now=NOW
    ).confirmation != (start.confirmation)
    running = an_automation(next_run_at=start.becomes)
    assert shown_stop(running, QUESTIONS.cadence).confirmation != start.confirmation
    with pytest.raises(ScheduleControlError, match="a start leaves"):
        ScheduleShown(
            direction=start.direction, automation=one, cadence=QUESTIONS.cadence, becomes=None
        )


def test_a_confirmed_change_is_the_domains_resume_or_pause_and_a_stale_one_is_refused() -> None:
    """Delete this and a change could be written with a registry entry that disagrees with it, or
    without the person having confirmed it."""
    one = an_automation()
    start = shown_start(one, QUESTIONS.cadence, now=NOW)
    made = changed(start, confirmation=start.confirmation, guards=QUESTIONS.guards)
    assert made.after is not None and made.after.next_run_at == start.becomes
    assert made.entry is not None and made.entry.next_run_at == start.becomes
    with pytest.raises(NotConfirmedError):
        changed(start, confirmation="0" * 64, guards=QUESTIONS.guards)
    running = made.after
    stop = shown_stop(running, QUESTIONS.cadence)
    stopped = changed(stop, confirmation=stop.confirmation, guards=QUESTIONS.guards)
    assert stopped.after is not None and stopped.after.paused


# ------------------------------------------------------------------ the routes
class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


class Directory:
    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return person(pid)
        return None


@dataclass
class Agents:
    held: dict[str, AgentRecord] = field(default_factory=lambda: {AGENT: READING_AGENT})

    async def agent(self, agent_id: str) -> AgentRecord | None:
        return self.held.get(agent_id)


@dataclass
class Schedules:
    """`routes.AutomationSchedules` in memory, keeping the store's one condition and no other."""

    rows: dict[str, Listed] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    lose_the_race: bool = False

    async def listed(self, agent_id: str) -> tuple[Listed, ...]:
        return tuple(one for one in self.rows.values() if one.automation.agent_id == agent_id)

    async def change(
        self,
        change: SchedulerChange,
        *,
        reason: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> bool:
        self.calls.append({"change": change, "reason": reason, "actor": actor, "at": at})
        held = self.rows[change.before.automation_id]
        if self.lose_the_race or held.automation.next_run_at != change.before.next_run_at:
            return False
        assert change.after is not None
        self.rows[change.before.automation_id] = replace(
            held, automation=change.after, stopped_because=reason
        )
        return True


def a_run(automation_id: str, principal_id: str) -> RunRecord:
    due = datetime(2998, 12, 30, 8, tzinfo=UTC)
    return RunRecord(
        run_id=run_id(automation_id, due),
        automation_id=automation_id,
        agent_id=AGENT,
        principal_id=principal_id,
        due_at=due,
        started_at=due,
        finished_at=due,
        outcome=RunOutcome.SUCCEEDED,
        result=("3 asked in web that crm would have answered",),
    )


def listed(one: Automation, *, template: Any = QUESTIONS, stopped: str | None = None) -> Listed:
    return Listed(
        automation=one,
        template_id=template.template_id,
        guards=template.guards,
        stopped_because=stopped,
        runs=(a_run(one.automation_id, one.runs_as.id),),
    )


@pytest.fixture
def schedules() -> Schedules:
    return Schedules(
        rows={
            "auto_one": listed(an_automation()),
            "auto_summary": listed(an_automation("auto_summary", template=SUMMARY)),
        }
    )


@pytest.fixture
def client(schedules: Schedules) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.agent_records = Agents()
        app.state.automation_schedules = schedules
        app.state.automation_events_on = False
        yield c


SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


def auth(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'sid': 'sess-1', **SECOND_FACTOR})}"}


def listing(c: TestClient, pid: str, agent: str = AGENT) -> Response:
    answer: Response = c.get(LIST.format(agent=agent), headers=auth(pid))
    return answer


def items(c: TestClient, pid: str) -> dict[str, dict[str, Any]]:
    answer = listing(c, pid)
    assert answer.status_code == 200, answer.text
    return {one["automation_id"]: one for one in answer.json()["items"]}


def change(c: TestClient, pid: str, path: str, automation: str, confirmation: str) -> Response:
    answer: Response = c.post(
        path.format(agent=AGENT, automation=automation),
        json={"confirmation": confirmation},
        headers=auth(pid),
    )
    return answer


def refusal(answer: Response) -> dict[str, Any]:
    assert answer.status_code == 404, answer.text
    body = dict(answer.json())
    body["trace_id"] = "<per request>"
    return body


def test_the_listing_shows_a_person_their_own_and_what_their_queue_grant_covers_and_no_more(
    client: TestClient,
) -> None:
    """The owner and a queue reader see both automations; a reader who may open the tab and holds
    no queue read sees none, as an empty list and not a refusal; nobody is told how many.

    Delete this and the tab could list every person's scheduled work to anybody who opens it."""
    assert set(items(client, "u_narrow")) == {"auto_one", "auto_summary"}
    assert set(items(client, "u_elsewhere")) == {"auto_one", "auto_summary"}
    body = listing(client, "u_wide").json()
    assert body["items"] == []
    assert set(body) == {"items", "result_rule"}


def test_a_reader_who_may_not_open_the_tab_and_an_agent_that_is_not_there_are_one_answer(
    client: TestClient,
) -> None:
    """Delete this and the listing says which agents exist to somebody trying ids."""
    missing = refusal(listing(client, "u_admin", "no_such_agent"))
    assert refusal(listing(client, "u_none")) == missing


def test_what_a_run_found_is_shown_to_whom_it_ran_as_and_to_nobody_else(client: TestClient) -> None:
    """Delete this and a colleague holding the queue read would be shown lines computed at somebody
    else's reach."""
    own = items(client, "u_narrow")["auto_one"]["last_run"]
    theirs = items(client, "u_elsewhere")["auto_one"]["last_run"]
    assert own["result"] == ["3 asked in web that crm would have answered"]
    assert theirs["result"] == []
    assert {k: v for k, v in own.items() if k != "result"} == {
        k: v for k, v in theirs.items() if k != "result"
    }


def test_the_controls_are_offered_only_where_the_decision_says_and_an_unbuilt_task_says_why(
    client: TestClient,
) -> None:
    """Delete this and a start button would be drawn for the automation's own principal or for an
    outcome the install cannot perform."""
    admin = items(client, "u_admin")
    assert admin["auto_one"]["start_confirmation"] is not None
    assert admin["auto_one"]["cannot_start"] is None
    assert admin["auto_one"]["paused_because"] == routes.NEVER_STARTED
    assert admin["auto_summary"]["start_confirmation"] is None
    assert "which agent each question was asked of" in admin["auto_summary"]["cannot_start"]
    owner = items(client, "u_narrow")["auto_one"]
    assert (owner["start_confirmation"], owner["stop_confirmation"]) == (None, None)


def test_a_confirmed_start_is_written_as_the_approver_and_a_stale_one_writes_nothing(
    client: TestClient, schedules: Schedules
) -> None:
    """Delete this and a start could be written without the digest that was shown, or attributed to
    somebody other than who pressed it."""
    shown = items(client, "u_admin")["auto_one"]

    stale = change(client, "u_admin", START, "auto_one", "0" * 64)
    assert stale.status_code == 409
    # The sentence a failure carries is the document's own, and its reference is the header's:
    # see `brain.api.A_DOCUMENT_A_ROUTE_WROTE_STILL_CARRIES_THE_TWO_FIELDS_EVERY_FAILURE_DOES`.
    assert stale.json() == {
        "outcome": routes.UNCONFIRMED,
        "sentence": routes.LOOK_AGAIN,
        "message": routes.LOOK_AGAIN,
        "trace_id": stale.headers["x-trace-id"],
    }
    assert schedules.calls == []

    done = change(client, "u_admin", START, "auto_one", shown["start_confirmation"])
    assert done.status_code == 200, done.text
    [call] = schedules.calls
    assert (call["reason"], call["actor"]) == (STARTED, "u_admin")
    assert call["change"].after.next_run_at.isoformat() == shown["start_becomes"].replace(
        "Z", "+00:00"
    )
    assert done.json()["next_run_at"] is not None
    assert done.json()["paused_because"] is None


def test_the_owner_stops_their_own_without_approval_and_a_bystander_cannot(
    client: TestClient, schedules: Schedules
) -> None:
    """Delete this and the fail-safe direction would need paperwork, or a reader of the queue could
    stop somebody else's automation."""
    running = an_automation(next_run_at=NOW + timedelta(days=1))
    schedules.rows["auto_one"] = listed(running, stopped=STARTED)

    shown = items(client, "u_narrow")["auto_one"]
    assert shown["stop_confirmation"] is not None
    assert items(client, "u_elsewhere")["auto_one"]["stop_confirmation"] is None
    assert (
        change(client, "u_elsewhere", STOP, "auto_one", shown["stop_confirmation"]).status_code
        == 404
    )
    assert schedules.calls == []

    done = change(client, "u_narrow", STOP, "auto_one", shown["stop_confirmation"])
    assert done.status_code == 200, done.text
    [call] = schedules.calls
    assert (call["reason"], call["actor"]) == (PausedBecause.STOPPED.value, "u_narrow")
    assert done.json()["paused_because"] == routes.STOPPED_BECAUSE[PausedBecause.STOPPED.value]


def test_a_change_that_lost_a_race_writes_nothing_and_says_to_look_again(
    client: TestClient, schedules: Schedules
) -> None:
    """Delete this and a start racing a run, or a second approver, would report success over a
    write the store declined."""
    schedules.lose_the_race = True
    shown = items(client, "u_admin")["auto_one"]
    moved = change(client, "u_admin", START, "auto_one", shown["start_confirmation"])
    assert moved.status_code == 409
    assert moved.json() == {
        "outcome": routes.MOVED,
        "sentence": routes.IT_MOVED,
        "message": routes.IT_MOVED,
        "trace_id": moved.headers["x-trace-id"],
    }


def test_a_control_on_an_automation_the_reader_cannot_see_is_the_same_404_as_none(
    client: TestClient,
) -> None:
    """Delete this and trying a start on an id says whether somebody has an automation there."""
    none = refusal(change(client, "u_admin", START, "auto_nobody", "0" * 64))
    assert refusal(change(client, "u_wide", START, "auto_one", "0" * 64)) == none
    assert refusal(change(client, "u_narrow", START, "auto_one", "0" * 64)) == none


def test_a_paused_automation_says_why_in_words_for_every_reason() -> None:
    """Every runner's reason and every change that leaves no next run has words, and nothing else
    does. Delete this and a pause reason added to the domain would reach the tab as nothing."""
    stops = {ChangeKind.PAUSED, ChangeKind.ADOPTED, ChangeKind.REMOVED}
    assert stops == set(LEAVES_NO_NEXT_RUN)
    assert set(routes.STOPPED_BECAUSE) == {one.value for one in PausedBecause} | {
        one.value for one in stops
    }


# ------------------------------------------------------------------ one a person wrote (M39.9.2.2)
def written(
    trigger: Any,
    *,
    task: str,
    condition: Any = None,
    tools: tuple[str, ...] = ("search_tickets",),
) -> Any:
    from brain.console.automation_authoring import Authored

    return Authored(
        name="I check each morning whether any ticket is overdue",
        instruction="Look at the tickets and tell me which are overdue by more than a week.",
        guards="Without it an overdue ticket is found when the client chases, not by us.",
        trigger=trigger,
        tools=tools,
        condition=condition,
        task=task,
    )


def listed_authored(one: Automation, authored: Any, *, cadence: Any = None) -> Listed:
    from brain.console.automation_authoring import AUTHORED_TEMPLATE

    return Listed(
        automation=one,
        template_id=AUTHORED_TEMPLATE,
        guards=authored.guards,
        stopped_because=None,
        runs=(),
        cadence=cadence,
        authored=authored,
    )


def test_an_automation_a_person_wrote_is_listed_with_its_trigger_condition_and_tools_in_words(
    client: TestClient, schedules: Schedules
) -> None:
    """The leaf's card: the trigger and the condition said in words, what it is told, what it may
    use, and that writes wait. Its cadence is its own, so a start is offered with the next run
    that cadence gives. Delete this and an automation a person wrote is dropped from the list
    because no template names it, or drawn without what they asked for."""
    from brain.console.automation_authoring import (
        SKILLS_ARE_THE_AGENTS_TO_CHANGE,
        WRITES_WAIT_FOR_A_PERSON,
        Condition,
        ConditionOp,
        TriggerChoice,
    )
    from brain.console.automation_gallery import Cadence, Every
    from brain.orchestration.unattended import TriggerKind

    cadence = Cadence(every=Every.DAY, hour_utc=5)
    one = written(
        TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=cadence),
        task=QUESTIONS.task,
        condition=Condition(field="freshdesk.ticket.due_by", op=ConditionOp.IS_OVER, value="7"),
    )
    schedules.rows["auto_written"] = listed_authored(
        an_automation("auto_written", template=QUESTIONS), one, cadence=cadence
    )

    shown = items(client, "u_admin")["auto_written"]

    assert shown["schedule"] == "every day at 05:00 UTC"
    assert shown["authored"] == {
        "trigger": "Runs every day at 05:00 UTC",
        "fires": True,
        "condition": "only when the ticket due by (freshdesk) is more than 7 days ago",
        "instruction": one.instruction_text,
        "tools": ["search_tickets"],
        "skills": [],
        "from_template": None,
        "writes_wait": WRITES_WAIT_FOR_A_PERSON,
        "skills_rule": SKILLS_ARE_THE_AGENTS_TO_CHANGE,
    }
    assert shown["start_confirmation"] is not None
    assert items(client, "u_admin")["auto_one"]["authored"] is None


class OfferedSkills:
    """`brain.automation_skills.AutomationSkills` in memory, noting whose reach it was asked at."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def offered(self, agent: Any, *, reach: Any, now: Any) -> tuple[Any, ...]:
        from brain.tools.skills import SkillCard

        self.asked.append(reach.principal_id)
        return (SkillCard(name="overdue_chase", description="Chase an overdue", version="1.0.0"),)


def test_the_card_names_the_skills_to_the_automations_owner_and_asks_no_other_reach(
    client: TestClient, schedules: Schedules
) -> None:
    """The skills a run would be offered are read at a reach, and the only reach a card can read
    them at is its reader's own, so they are named on an automation that runs as the reader and
    nowhere else, and nobody's reach is asked on behalf of somebody else's automation. A person
    who owns none of the automations asks nothing at all. Delete this and one person is shown
    skills read at another's reach, or every list costs a skill read nobody could use."""
    from brain.console.automation_authoring import SKILLS_ARE_THE_AGENTS_TO_CHANGE, TriggerChoice
    from brain.console.automation_gallery import Cadence, Every
    from brain.orchestration.unattended import TriggerKind

    skills = OfferedSkills()
    client.app.state.automation_skills = skills  # type: ignore[attr-defined]
    cadence = Cadence(every=Every.DAY, hour_utc=5)
    one = written(TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=cadence), task=QUESTIONS.task)
    schedules.rows["auto_written"] = listed_authored(
        an_automation("auto_written", template=QUESTIONS), one, cadence=cadence
    )

    other = items(client, "u_admin")["auto_written"]["authored"]
    assert skills.asked == []
    owner = items(client, "u_narrow")["auto_written"]["authored"]

    assert other["skills"] == []
    assert owner["skills"] == ["overdue_chase"]
    assert skills.asked == ["u_narrow"]
    # One list holding the reader's own automation and somebody else's: the skills, read at the
    # reader's reach, are named on theirs and on no other card in the same answer.
    schedules.rows["auto_theirs"] = listed_authored(
        an_automation("auto_theirs", owner="u_admin", template=QUESTIONS), one, cadence=cadence
    )
    mixed = items(client, "u_narrow")
    assert mixed["auto_written"]["authored"]["skills"] == ["overdue_chase"]
    assert mixed["auto_theirs"]["authored"]["skills"] == []
    assert owner["skills_rule"] == other["skills_rule"] == SKILLS_ARE_THE_AGENTS_TO_CHANGE


def test_a_trigger_nothing_fires_is_listed_saying_so_and_cannot_be_started(
    client: TestClient, schedules: Schedules
) -> None:
    """A webhook is saved and shown and its start is not offered, the sentence says why, and a
    start pressed anyway is the one 404. Delete this and a control that reaches nothing is drawn
    for a trigger no install fires."""
    from brain.console.automation_authoring import NOTHING_FIRES_THIS_YET, TriggerChoice
    from brain.orchestration.unattended import TriggerKind

    one = written(
        TriggerChoice(kind=TriggerKind.WEBHOOK, source="ticket_closed"), task=QUESTIONS.task
    )
    schedules.rows["auto_hook"] = listed_authored(
        an_automation("auto_hook", template=QUESTIONS), one
    )

    shown = items(client, "u_admin")["auto_hook"]

    assert shown["schedule"] == "Runs when ticket closed is called from outside"
    assert shown["authored"]["fires"] is False
    assert shown["start_confirmation"] is None
    assert shown["cannot_start"] == NOTHING_FIRES_THIS_YET
    missing = refusal(listing(client, "u_admin", "no_such_agent"))
    pressed = change(client, "u_admin", START, "auto_hook", "0" * 64)
    assert pressed.status_code == 404
    assert pressed.json()["message"] == missing["message"]
    assert schedules.calls == []


def a_change_trigger(*, armed: bool = False) -> tuple[Automation, Any]:
    from brain.console.automation_authoring import TriggerChoice
    from brain.orchestration.unattended import TriggerKind

    armed_at = datetime(2998, 12, 31, 8, tzinfo=UTC) if armed else None
    one = written(
        TriggerChoice(kind=TriggerKind.CONNECTOR_EVENT, source="ticket_source"),
        task=QUESTIONS.task,
    )
    return an_automation("auto_change", next_run_at=armed_at), one


def test_a_change_trigger_is_offered_a_start_only_while_changes_are_switched_on(
    client: TestClient, schedules: Schedules
) -> None:
    """Off, the card says why and a start pressed anyway is the one 404; on, the start is offered
    with a digest that does not move between two requests, because the instant it arms at is the
    write's, and the confirmed start arms it. Delete this and a control that reaches nothing is
    drawn on an install that has not switched changes on, or every start of a listener is refused
    as stale."""
    from brain.console.automation_authoring import EVENTS_ARE_OFF

    one, authored = a_change_trigger()
    schedules.rows["auto_change"] = listed_authored(one, authored)

    off = items(client, "u_admin")["auto_change"]
    assert off["start_confirmation"] is None
    assert off["cannot_start"] == EVENTS_ARE_OFF
    assert off["schedule"] == "Runs when something changes in ticket source"
    assert change(client, "u_admin", START, "auto_change", "0" * 64).status_code == 404

    client.app.state.automation_events_on = True  # type: ignore[attr-defined]
    first = items(client, "u_admin")["auto_change"]
    second = items(client, "u_admin")["auto_change"]
    assert first["start_confirmation"] is not None
    assert first["start_confirmation"] == second["start_confirmation"]
    assert first["cannot_start"] is None

    done = change(client, "u_admin", START, "auto_change", first["start_confirmation"])
    assert done.status_code == 200, done.text
    [call] = schedules.calls
    assert (call["reason"], call["actor"]) == (STARTED, "u_admin")
    assert call["change"].after.next_run_at is not None
    assert done.json()["next_run_at"] is not None


def test_an_armed_change_trigger_is_stopped_with_the_switch_off_as_with_it_on(
    client: TestClient, schedules: Schedules
) -> None:
    """The switch gates the door and never traps what it opened. Delete this and turning changes off
    leaves a listener running that nobody can stop from its own page."""
    one, authored = a_change_trigger(armed=True)
    schedules.rows["auto_change"] = listed_authored(one, authored)

    shown = items(client, "u_narrow")["auto_change"]
    assert shown["stop_confirmation"] is not None
    assert shown["start_confirmation"] is None

    done = change(client, "u_narrow", STOP, "auto_change", shown["stop_confirmation"])
    assert done.status_code == 200, done.text
    [call] = schedules.calls
    assert call["change"].after.next_run_at is None


def test_an_instruction_is_listed_and_says_what_it_still_needs_before_it_can_be_started(
    client: TestClient, schedules: Schedules
) -> None:
    """The instruction task has no performer yet, so its start is refused in words, not scheduled
    to fail. Delete this and a start is offered for an automation whose first run is refused."""
    from brain.console.automation_authoring import AUTHORED_TASK, TriggerChoice
    from brain.console.automation_gallery import Cadence, Every
    from brain.orchestration.unattended import TriggerKind

    cadence = Cadence(every=Every.DAY, hour_utc=5)
    one = written(TriggerChoice(kind=TriggerKind.SCHEDULE, cadence=cadence), task=AUTHORED_TASK)
    base = an_automation("auto_words", template=QUESTIONS)
    schedules.rows["auto_words"] = listed_authored(
        replace(base, task=AUTHORED_TASK), one, cadence=cadence
    )

    shown = items(client, "u_admin")["auto_words"]

    assert shown["start_confirmation"] is None
    assert "an agent run with nobody present" in shown["cannot_start"]
