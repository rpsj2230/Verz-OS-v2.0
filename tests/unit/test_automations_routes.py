"""The Automations module's routes: the list across agents, one automation's page and figures, and
the five confirmed changes, driven through the application's own authentication.

The decisions are `tests/unit/test_automations.py`'s and what the store writes is
`tests/unit/test_automation_change_store.py`'s. What is here is the order the routes ask in, what
they tell whom, and that a refusal says nothing about what exists. The personas and the gate wiring
are `tests/unit/test_automation_schedule_routes.py`'s, so the two automation surfaces are held to
one set of people.

Task ids: M27.12.3, M27.15.37, M39.6.1.4, M39.6.1.5
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import automation_schedule_routes as schedule_routes
from brain import automations_routes as routes
from brain.agents.model import AgentAudience, AgentRecord
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.automation_gallery import Cadence, Every
from brain.console.automations import Change, folded, shown
from brain.identity.bearer import TokenAuthority
from brain.knowledge.visibility import Visibility
from brain.ops.automation_run import PausedBecause, RunOutcome, RunRecord, run_id
from brain.ops.automation_run_store import RUNS_ON_ITS_PAGE, Detailed, Listed
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import AUDIENCE, ISSUER, Keys, NoCache, Versions, verifier
from tests.unit.test_automation_schedule_routes import (
    AGENT,
    NOW,
    QUESTIONS,
    READING_AGENT,
    Directory,
    Store,
    an_automation,
    auth,
    person,
)

HIDDEN = "private_helper"
LIST = f"{API_PREFIX}/console/automations"
ONE = f"{API_PREFIX}/console/automations/{{automation}}"
STATS = f"{API_PREFIX}/console/automations/{{automation}}/stats"
ACT = f"{API_PREFIX}/automations/{{automation}}/{{act}}"
RUNNING = NOW + timedelta(hours=1)
MONDAYS = Cadence(every=Every.WEEK, hour_utc=7, weekday=0)


@dataclass
class Agents:
    """Two agents: one the whole company sees, and one only its steward does."""

    held: dict[str, AgentRecord] = field(
        default_factory=lambda: {
            AGENT: READING_AGENT,
            HIDDEN: READING_AGENT.model_copy(
                update={
                    "agent_id": HIDDEN,
                    "audience": AgentAudience(level=Visibility.PERSONAL, owner_id="u_steward"),
                }
            ),
        }
    )

    async def agent(self, agent_id: str) -> AgentRecord | None:
        return self.held.get(agent_id)


def a_run(automation_id: str, principal_id: str, at: datetime, outcome: RunOutcome) -> RunRecord:
    return RunRecord(
        run_id=run_id(automation_id, at),
        automation_id=automation_id,
        agent_id=AGENT,
        principal_id=principal_id,
        due_at=at,
        started_at=at,
        finished_at=at,
        outcome=outcome,
        reason=PausedBecause.OWNER_GONE if outcome is RunOutcome.REFUSED else None,
        result=("3 asked in web",) if outcome is RunOutcome.SUCCEEDED else (),
    )


def detailed(
    automation_id: str,
    *,
    owner: str,
    next_run_at: datetime | None,
    agent: str = AGENT,
    gone: bool = False,
    runs: tuple[RunRecord, ...] = (),
) -> Detailed:
    one = replace(
        an_automation(automation_id, owner=owner, next_run_at=next_run_at), agent_id=agent
    )
    return Detailed(
        listed=Listed(
            automation=one,
            template_id=QUESTIONS.template_id,
            guards=QUESTIONS.guards,
            stopped_because=PausedBecause.OWNER_GONE.value if gone else None,
            runs=runs,
            cadence=QUESTIONS.cadence,
            owner_name=f"Person {owner}",
            owner_gone=gone,
            installed_by=owner,
            installed_as=owner,
            installed_at=NOW - timedelta(days=40),
        ),
        schedule=(),
        names={owner: f"Person {owner}"},
    )


@dataclass
class Book:
    """`routes.AutomationDirectory` in memory, folding each change as the store does."""

    rows: dict[str, Detailed]
    applied: list[Change] = field(default_factory=list)
    lose_the_race: bool = False

    async def every(self) -> tuple[Listed, ...]:
        return tuple(one.listed for one in self.rows.values())

    async def one(self, automation_id: str) -> Detailed | None:
        return self.rows.get(automation_id)

    async def apply(
        self, automation_id: str, change: Change, *, expect: str, ent_hash: str, trace_id: str
    ) -> bool:
        held = self.rows[automation_id]
        was = held.listed
        if self.lose_the_race or expect != shown(
            was.automation, cadence=was.cadence, removed=was.removed
        ):
            return False
        self.applied.append(change)
        now_is = folded(
            installed_as=was.installed_as,
            template_cadence=QUESTIONS.cadence,
            changes=(*was.changes, change),
        )
        moved = replace(
            was.automation, runs_as=person(now_is.owner_id), next_run_at=change.next_run_at
        )
        adopted = now_is.owner_id != was.automation.runs_as.id
        self.rows[automation_id] = replace(
            held,
            listed=replace(
                was,
                automation=moved,
                cadence=now_is.cadence,
                removed=now_is.removed,
                changes=now_is.changes,
                owner_gone=was.owner_gone and not adopted,
                owner_name=f"Person {now_is.owner_id}",
                stopped_because=change.kind.value,
            ),
        )
        return True


@pytest.fixture
def book() -> Book:
    # Relative to the wall clock, because the periods are counted back from the request's own
    # instant, which the gate reads; nothing here is a fixed date that could go off.
    today = datetime.now(UTC)
    ran = (
        a_run("auto_one", "u_narrow", today - timedelta(days=1), RunOutcome.SUCCEEDED),
        a_run("auto_one", "u_narrow", today - timedelta(days=10), RunOutcome.FAILED),
    )
    return Book(
        rows={
            "auto_one": detailed("auto_one", owner="u_narrow", next_run_at=RUNNING, runs=ran),
            "auto_gone": detailed("auto_gone", owner="u_gone", next_run_at=None, gone=True),
            "auto_hidden": detailed(
                "auto_hidden", owner="u_narrow", next_run_at=RUNNING, agent=HIDDEN
            ),
        }
    )


@pytest.fixture
def client(book: Book) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
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
        app.state.automation_directory = book
        yield c


def listing(c: TestClient, pid: str, query: str = "") -> Response:
    answer: Response = c.get(f"{LIST}{query}", headers=auth(pid))
    return answer


def rows(c: TestClient, pid: str, query: str = "") -> dict[str, dict[str, Any]]:
    answer = listing(c, pid, query)
    assert answer.status_code == 200, answer.text
    return {one["automation_id"]: one for one in answer.json()["items"]}


def page(c: TestClient, pid: str, automation: str) -> Response:
    answer: Response = c.get(ONE.format(automation=automation), headers=auth(pid))
    return answer


def act(
    c: TestClient, pid: str, automation: str, what: str, body: dict[str, Any] | None = None
) -> Response:
    confirmation = body.pop("confirmation") if body and "confirmation" in body else None
    if confirmation is None:
        seen = page(c, "u_admin", automation)
        confirmation = seen.json()["confirmation"] if seen.status_code == 200 else "0" * 64
    answer: Response = c.post(
        ACT.format(automation=automation, act=what),
        json={"confirmation": confirmation, **(body or {})},
        headers=auth(pid),
    )
    return answer


def refusal(answer: Response) -> dict[str, Any]:
    assert answer.status_code == 404, answer.text
    body = dict(answer.json())
    body["trace_id"] = "<per request>"
    return body


def test_the_list_is_every_automation_on_the_agents_a_reader_may_see_and_no_count(
    client: TestClient,
) -> None:
    """An automation on an agent the reader cannot see is absent as if it did not exist, the rows
    carry names rather than principal ids, and nothing says how many were withheld. A reader who
    may open the module and see nobody's scheduled work gets an empty list, not a refusal.

    Delete this and the module would be the global pile of every scheduled thing in the company,
    which `agent_automations.automations_for` exists to refuse."""
    seen = rows(client, "u_admin")
    assert set(seen) == {"auto_one", "auto_gone"}
    assert seen["auto_one"]["state"] == "running"
    assert seen["auto_gone"]["state"] == "ownerless"
    assert seen["auto_one"]["owner_name"] == "Person u_narrow"
    assert seen["auto_one"]["last_outcome"] == "succeeded"
    assert "owner_id" not in seen["auto_one"]
    assert set(listing(client, "u_admin").json()) == {"items", "next_cursor"}
    assert listing(client, "u_wide").json()["items"] == []
    assert set(rows(client, "u_admin", "?filter=state:ownerless")) == {"auto_gone"}


def test_no_module_read_a_hidden_automation_and_a_missing_one_are_one_answer(
    client: TestClient,
) -> None:
    """Delete this and trying ids would tell somebody which automations exist on agents they may
    not see, or that the module exists at all."""
    missing = refusal(page(client, "u_admin", "auto_nobody"))
    assert refusal(page(client, "u_admin", "auto_hidden")) == missing
    assert refusal(listing(client, "u_none")) == missing
    assert refusal(act(client, "u_admin", "auto_hidden", "pause")) == missing
    assert refusal(act(client, "u_elsewhere", "auto_one", "pause")) == missing


def test_the_page_offers_only_the_changes_this_reader_may_make(client: TestClient) -> None:
    """The authority may pause, reschedule and remove a running automation and adopt an ownerless
    one; the owner may pause and remove their own and do nothing gated; nobody may resume an
    automation whose person has gone.

    Delete this and the page would offer a button the route then refuses."""
    admin = page(client, "u_admin", "auto_one").json()
    assert (admin["may_pause"], admin["may_resume"], admin["may_reschedule"]) == (True, False, True)
    assert (admin["may_remove"], admin["may_adopt"]) == (True, False)
    owner = page(client, "u_narrow", "auto_one").json()
    assert (owner["may_pause"], owner["may_reschedule"], owner["may_remove"]) == (True, False, True)
    gone = page(client, "u_admin", "auto_gone").json()
    assert (gone["may_adopt"], gone["may_resume"]) == (True, False)
    assert (
        gone["stopped_because"] == schedule_routes.STOPPED_BECAUSE[PausedBecause.OWNER_GONE.value]
    )
    assert admin["schedule_accepts"] == routes.SCHEDULE_ACCEPTS
    assert "u_narrow" not in (admin["automation"]["owner_name"], admin["installed_by_name"])


def test_a_pause_is_written_confirmed_and_a_stale_or_raced_one_writes_nothing(
    client: TestClient, book: Book
) -> None:
    """Delete this and a pause confirmed over an automation somebody else had since changed would
    be written anyway, or a lost race would read as done."""
    stale = act(client, "u_narrow", "auto_one", "pause", {"confirmation": "0" * 64})
    assert stale.status_code == 409 and stale.json()["outcome"] == schedule_routes.UNCONFIRMED
    book.lose_the_race = True
    raced = act(client, "u_narrow", "auto_one", "pause")
    assert raced.status_code == 409 and raced.json()["outcome"] == schedule_routes.MOVED
    book.lose_the_race = False
    done = act(client, "u_narrow", "auto_one", "pause")
    assert done.status_code == 200, done.text
    assert done.json()["automation"]["state"] == "paused"
    assert [(one.kind.value, one.changed_by) for one in book.applied] == [("paused", "u_narrow")]


def test_an_ownerless_automation_is_adopted_in_the_adopters_name_and_stays_paused(
    client: TestClient, book: Book
) -> None:
    """Adopted by the authority: it runs as them, it is still paused, and they cannot resume their
    own adoption, which is somebody else's approval.

    Delete this and adopting an automation would restart it at the adopter's reach with nobody
    else having looked."""
    done = act(client, "u_admin", "auto_gone", "adopt")
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["automation"]["state"] == "paused"
    assert body["owner_id"] == "u_admin"
    assert body["may_resume"] is False
    assert book.applied[-1].runs_as_id == "u_admin"
    assert act(client, "u_admin", "auto_gone", "resume").status_code == 404


def test_a_schedule_says_what_it_accepts_and_a_weekly_one_names_its_day(
    client: TestClient,
) -> None:
    """Delete this and a weekly schedule with no day could be written, or a schedule change would
    not move the next run of a running automation."""
    refused = act(client, "u_admin", "auto_one", "reschedule", {"every": "week", "hour_utc": 7})
    assert refused.status_code == 422
    done = act(
        client, "u_admin", "auto_one", "reschedule", {"every": "week", "hour_utc": 7, "weekday": 0}
    )
    assert done.status_code == 200, done.text
    assert done.json()["automation"]["schedule"] == MONDAYS.words()
    assert done.json()["automation"]["next_run_at"] is not None


def test_a_removed_automation_keeps_its_page_and_offers_nothing(client: TestClient) -> None:
    """Delete this and a removed automation could be resumed from its own page."""
    assert act(client, "u_narrow", "auto_one", "remove").status_code == 200
    body = page(client, "u_admin", "auto_one").json()
    assert body["automation"]["state"] == "removed"
    assert not any(body[one] for one in ("may_pause", "may_resume", "may_reschedule", "may_remove"))
    assert act(client, "u_admin", "auto_one", "resume").status_code == 404


def test_the_figures_are_runs_by_outcome_and_the_cost_is_said_to_be_unrecorded(
    client: TestClient,
) -> None:
    """Seven and thirty days over the runs the reader may be shown; a run's result only to whom it
    ran as; cost named as unrecorded rather than nought.

    Delete this and a figure nothing records could reach the page as a zero."""
    answer = client.get(STATS.format(automation="auto_one"), headers=auth("u_admin"))
    assert answer.status_code == 200, answer.text
    body = answer.json()
    periods = {one["range"]: one for one in body["periods"]}
    assert (periods["7d"]["runs"], periods["7d"]["succeeded"]) == (1, 1)
    assert (periods["30d"]["runs"], periods["30d"]["failed"]) == (2, 1)
    assert [one["figure"] for one in body["unrecorded"]] == ["run_cost"]
    admin_runs = page(client, "u_admin", "auto_one").json()["runs"]
    owner_runs = page(client, "u_narrow", "auto_one").json()["runs"]
    assert admin_runs[0]["result"] == []
    assert owner_runs[0]["result"] == ["3 asked in web"]
    assert [one["reach"] for one in owner_runs] == [routes.REACH_NONE, routes.REACH_NONE]


def test_the_page_reads_every_run_the_longest_period_can_hold() -> None:
    """The most frequent cadence is once a day and the page reads more runs than the longest period
    can hold, so the figures are never cut off and never need to say "at least".

    Delete this and a cadence added at an hourly rate, or a smaller bound, would make the thirty-day
    figures a count of the newest sixty runs presented as the month's."""
    assert {one.value for one in Every} == {"day", "weekday", "week"}
    longest = max(span for _, span in routes.PERIODS)
    assert longest.days + 1 < RUNS_ON_ITS_PAGE
    assert "once a day" in routes.EVERY_RUN_IN_THE_LONGEST_PERIOD_IS_READ
