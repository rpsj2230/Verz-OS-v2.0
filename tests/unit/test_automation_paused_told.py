"""A steward whose agent's automation was paused for failing is told once, by the web process.

The pure half holds the sentence, the key, the cadence and the switch, and drives
`brain.automation_paused_told.tell_paused_stewards` with its sender replaced by one that keeps a
ledger, so a second pass over the same pause is seen to send nothing. The server half fails a real
automation twice through the worker's own tick, so the pause row is the one `run_one` writes, and
reads it back as the application role.

Task ids: M39.6.2.3
"""

from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain import automation_paused_told
from brain.automation_paused_told import (
    INTENT_PREFIX,
    LOOKBACK,
    TELL_EVERY,
    Paused,
    intent_ref_for,
    paused_between,
    paused_text,
    tell_paused_stewards,
)
from brain.console.agent_automations import FAILURES_BEFORE_PAUSE
from brain.ops import automation_run_store as store
from brain.ops.automation_run_store import RUN_EVERY
from brain.ops.notices import NoticeKind, notice
from brain.session import make_session_factory
from brain.tables.channel import DeliveryOutcome
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_automation_run_store import (
    AGENT,
    NOW,
    OWNER,
    next_run,
    seeded,
    through_0067,
    tick,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"
AT = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
ONE = Paused(
    pause_id="p1",
    automation_id="auto_one",
    agent_id="quote_helper",
    steward_id="u_steward",
    paused_at=AT,
)


# ------------------------------------------------------------------------ the pieces
def test_the_steward_is_told_what_stopped_and_never_why_it_failed() -> None:
    """The sentence is `OwnerNotice.render` for the threshold that paused it: the automation, the
    agent and the count. Delete this and a later message can carry a run's failure text, which
    can quote the data the run read, to wherever the steward last wrote."""
    said = paused_text(ONE)

    assert "auto_one" in said and "quote_helper" in said
    assert f"{FAILURES_BEFORE_PAUSE} consecutive failed runs" in said
    assert "{" not in said


def test_each_pause_has_its_own_key_so_a_second_pause_is_a_second_message() -> None:
    """The key is the pause row's id. Delete this and an automation paused, resumed and paused
    again tells its steward once, the second time being taken for the first."""
    assert intent_ref_for(ONE) == f"{INTENT_PREFIX}.p1"
    assert intent_ref_for(replace(ONE, pause_id="p2")) != intent_ref_for(ONE)


def test_the_loop_runs_as_often_as_the_worker_and_looks_back_further() -> None:
    """Asked as often as the worker runs automations, and looking back many runs, so a pause made
    while this process was down is still told. Delete this and a cadence edit leaves stewards told
    late, or a lookback shorter than the gap leaves some never told."""
    assert TELL_EVERY == RUN_EVERY
    assert LOOKBACK >= TELL_EVERY * 60


def test_the_notice_row_names_this_sender_and_keeps_no_switch() -> None:
    """The notices page says the pause is sent, by this function, and has no switch. Delete this
    and the page keeps saying no channel sends it, or somebody gives it a switch the misuse rule
    says it must not have."""
    row = notice(NoticeKind.AUTOMATION_PAUSED.value)

    assert row.sent_by == "brain.automation_paused_told:tell_paused_stewards"
    assert not row.switchable


@dataclass
class Session:
    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


@dataclass
class Sent:
    outcome: DeliveryOutcome
    issued: bool


@dataclass
class Teller:
    """`brain.tell_later.tell` in memory, with the operation ledger's rule: a key already sent is
    handed back its first record and issues nothing."""

    told: list[tuple[str, str, str]] = field(default_factory=list)
    keys: set[tuple[str, str]] = field(default_factory=set)

    async def __call__(
        self, request: Any, person: str, said: str, *, intent_ref: str, now: datetime
    ) -> Sent:
        first = (person, intent_ref) not in self.keys
        self.keys.add((person, intent_ref))
        if first:
            self.told.append((person, said, intent_ref))
        return Sent(DeliveryOutcome.SENT, issued=first)


def telling(monkeypatch: pytest.MonkeyPatch, *, on: bool) -> Teller:
    teller = Teller()

    async def switched(session: Any, kind: NoticeKind) -> bool:
        assert kind is NoticeKind.AUTOMATION_PAUSED
        return on

    monkeypatch.setattr(automation_paused_told, "notice_is_on", switched)
    monkeypatch.setattr(automation_paused_told, "tell", teller)
    return teller


def test_the_steward_is_told_once_however_often_the_loop_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The positive case, and once.** Each pause is handed to the sender with its steward, its
    sentence and its own key; the next pass over the same pauses issues nothing and counts
    nothing. Delete this and the loop can tell nobody while it reads on, or tell a steward every
    minute for a day."""
    teller = telling(monkeypatch, on=True)
    two = replace(ONE, pause_id="p2", automation_id="auto_two")

    first = asyncio.run(tell_paused_stewards(None, Session, now=AT, paused=(ONE, two)))  # type: ignore[arg-type]
    second = asyncio.run(tell_paused_stewards(None, Session, now=AT, paused=(ONE, two)))  # type: ignore[arg-type]

    assert (first, second) == (2, 0)
    assert teller.told == [
        ("u_steward", paused_text(ONE), "automation_paused.p1"),
        ("u_steward", paused_text(two), "automation_paused.p2"),
    ]


def test_with_the_notice_reading_off_nobody_is_told(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sender asks `notice_is_on` before each pass, as every sender does. The notice has no
    switch today, so this is the day somebody gives it one. Delete this and that switch would stop
    nothing."""
    teller = telling(monkeypatch, on=False)

    sent = asyncio.run(tell_paused_stewards(None, Session, now=AT, paused=(ONE,)))  # type: ignore[arg-type]

    assert (sent, teller.told) == (0, [])


def test_the_sender_is_the_one_later_sender_and_the_worker_sends_nothing() -> None:
    """`THE_WORKER_MARKS_AND_THE_WEB_PROCESS_TELLS`: this module sends through
    `brain.tell_later.tell` alone, and the worker's run store imports neither it nor that sender.
    Delete this and a second path to a chat appears beside the one that re-checks reach, or the
    worker starts needing the channels' tokens."""
    told = ast.parse((SRC / "automation_paused_told.py").read_text(encoding="utf-8"))
    imported = {
        (node.module, alias.name)
        for node in ast.walk(told)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("brain.tell_later", "tell") in imported
    assert not any(module == "brain.channels.outbound" for module, _ in imported)
    worker = (SRC / "ops" / "automation_run_store.py").read_text(encoding="utf-8")
    assert "tell_later" not in worker and "automation_paused_told" not in worker


# ------------------------------------------------------------------------ on a server
def _failed_twice(monkeypatch: pytest.MonkeyPatch, url: str) -> datetime:
    """The seeded automation failed at two slots through the worker's own tick, so the pause row
    is the one `run_one` writes. Returns the instant of the second, pausing, run."""

    async def broken(*_: object, **__: object) -> tuple[str, ...]:
        msg = "the read quoted somebody's data"
        raise RuntimeError(msg)

    monkeypatch.setattr(store, "perform", broken)
    seeded(url)
    tick(url)
    again = next_run(url)
    assert again is not None
    tick(url, again)
    return again


def _read(url: str, *, after: datetime, until: datetime) -> tuple[Paused, ...]:
    async def go() -> tuple[Paused, ...]:
        built = app_engine(url)
        try:
            return await paused_between(make_session_factory(built), after=after, until=until)
        finally:
            await built.dispose()

    return run(go)


@pytest.mark.needs_db
def test_a_real_pause_is_read_for_the_agents_steward_and_a_window_before_it_reads_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The worker's mark is what the web process reads.** An automation failed twice through
    the tick is read back, as the application role, as one pause addressed to the agent's steward,
    as `run_one` addresses its notice; a window ending before the pause reads nothing. Delete this
    and the loop can read a reason or an actor the runner never writes, and tell nobody."""
    with through_0067("brain_paused_told_steward") as url:
        paused_at = _failed_twice(monkeypatch, url)
        found = _read(
            url, after=paused_at - timedelta(hours=1), until=paused_at + timedelta(hours=1)
        )
        before = _read(
            url, after=paused_at - timedelta(hours=1), until=paused_at - timedelta(seconds=1)
        )

    assert [(one.automation_id, one.agent_id, one.steward_id) for one in found] == [
        ("auto_one", AGENT, "u_steward")
    ]
    assert before == ()


@pytest.mark.needs_db
def test_a_stop_a_person_made_is_not_read_and_a_gone_agent_falls_back_to_the_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop a person made is not a pause for failing and is not told, and neither is a row
    claiming the runner's reason in a person's name; with the agent's row gone the pause is
    addressed to the automation's own owner, as `run_one` falls back. Delete this and a steward is
    told their automation failed when somebody stopped it or wrote that it had, or a pause on an
    agent since removed is told to nobody."""
    with through_0067("brain_paused_told_fallback") as url:
        paused_at = _failed_twice(monkeypatch, url)
        sql(
            url,
            "INSERT INTO agent.automation_schedule (automation_id, agent_id, next_run_at, reason,"
            " changed_by, at) VALUES ('auto_one', %s, NULL, 'stopped', %s, %s)",
            AGENT,
            OWNER,
            paused_at + timedelta(minutes=1),
        )
        sql(
            url,
            "INSERT INTO agent.automation_schedule (automation_id, agent_id, next_run_at, reason,"
            " changed_by, at) VALUES ('auto_one', %s, NULL, 'failed_repeatedly', %s, %s)",
            AGENT,
            OWNER,
            paused_at + timedelta(minutes=2),
        )
        sql(
            url,
            "UPDATE agent.automation SET agent_id = 'gone_agent' WHERE automation_id = 'auto_one'",
        )
        sql(url, "UPDATE agent.automation_schedule SET agent_id = 'gone_agent'")
        found = _read(url, after=NOW - timedelta(days=30), until=paused_at + timedelta(hours=1))

    assert [(one.steward_id, one.agent_id) for one in found] == [(OWNER, "gone_agent")]


def test_the_notice_ends_with_the_agents_automations_tab_when_the_install_has_an_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**M39.1.2.4's alert.** With an address of its own, the notice ends with the agent's
    Automations tab on this install's console, made by `workspace.deep_link` on the address the
    chat's Ask link is made from; with none, it carries no link rather than half of one. Delete
    this and the alert says what stopped and leaves the steward to find where."""
    from brain import chat_answer
    from brain.automation_paused_told import OPEN_IT

    monkeypatch.setattr(chat_answer, "ask_link", lambda: "https://brain.example.test/ask")
    linked = paused_text(ONE)
    monkeypatch.setattr(chat_answer, "ask_link", lambda: "")
    plain = paused_text(ONE)

    assert linked.endswith(f"{OPEN_IT} https://brain.example.test/agents/quote_helper/automations")
    assert linked.startswith(plain)
    assert OPEN_IT not in plain and "https://" not in plain


def test_the_approvals_link_and_an_agents_link_share_one_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`approval_cards.approvals_link` and the agent link are both `chat_answer.console_link`
    over the same Ask address, so two links in two messages cannot disagree about where this
    install is. Delete this and a second derivation of the address drifts from the first."""
    from brain import approval_cards, chat_answer

    monkeypatch.setattr(chat_answer, "ask_link", lambda: "https://brain.example.test/ask")

    assert approval_cards.approvals_link() == "https://brain.example.test/approvals"
    assert chat_answer.console_link("/agents/x/memory") == (
        "https://brain.example.test/agents/x/memory"
    )
