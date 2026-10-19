"""Who an agent is offered to beside its level, over HTTP: who is told, who may change it, and what
a change writes.

Driven through the real application with signed-in people and a stub where the pool is. The
lifecycle authority is asked of an in-memory `AgentLifecycles` put where
`brain.agent_lifecycle_routes.lifecycles_of` looks first, the offers are held by a store that
records every write it was asked for, and the switch is the boolean `app.state` carries. That the
rows reach PostgreSQL under their row policies is the install check
`a_steward_offers_an_agent_to_more_than_one_department_and_to_named_people`, which
`tests/unit/test_acceptance.py` runs over a migrated database.

Task ids: M27.11.13
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

import brain.agent_audience_routes as audience_routes
from brain.agent_audience_routes import (
    A_COMPANY_AGENT_IS_FOUND_BY_EVERYBODY,
    A_PERSONAL_AGENT_IS_FOUND_BY_ITS_OWNER,
    ADDITIONS_PATH,
    AUDIENCE_PATH,
    MAX_OFFERS,
    NOT_A_DEPARTMENT_HERE,
    NOT_SWITCHED_ON,
    NOTHING_TO_WITHDRAW,
    REMOVALS_PATH,
    TOO_MANY_OFFERS,
    AudienceView,
    router,
)
from brain.agent_lifecycle_routes import FoundAgent
from brain.agent_routes import record_of
from brain.agents.audience_store import Extras
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.api import API_PREFIX
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.tables.agent import AgentRow
from brain.tables.audience_extra import ExtraKind
from tests.fixtures.console_http import Stub, console_client, get, headers, no_audience_extras
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import agent_row

WEB = "web_desk"
MINE = "my_desk"
PRIVATE = "private_desk"
ADMINS_OWN = "admins_own_desk"
EVERYONE = "company_desk"
FINANCE = "finance_desk"

#: `u_admin` (web) holds the lifecycle authority everywhere; `u_prefix` (web) holds it in sales
#: alone, so over a web agent it holds nothing; `u_narrow` (web) is the steward of two agents and
#: holds nothing; `u_wide` (sales) and `u_none` (no department) hold nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=Scope.unrestricted()),),
    "u_prefix": (Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=Scope.department("sales")),),
    "u_narrow": (),
    "u_wide": (),
    "u_none": (),
    "u_elsewhere": (),
}

ROWS: Mapping[str, AgentRow] = {
    WEB: agent_row(WEB, level=Visibility.DEPARTMENT, department="web", owner_id="u_steward"),
    MINE: agent_row(MINE, level=Visibility.DEPARTMENT, department="web", owner_id="u_narrow"),
    PRIVATE: agent_row(PRIVATE, level=Visibility.PERSONAL, owner_id="u_narrow"),
    ADMINS_OWN: agent_row(ADMINS_OWN, level=Visibility.PERSONAL, owner_id="u_admin"),
    EVERYONE: agent_row(EVERYONE, level=Visibility.COMPANY, owner_id="u_steward"),
    FINANCE: agent_row(FINANCE, level=Visibility.DEPARTMENT, department="finance"),
}

#: The departments this install has, which an offer to a department has to name one of.
DEPARTMENTS = ("web", "sales", "finance")


def answer(statement: Any) -> Result | None:
    """The one agent row a request asked for, which is the audience's read."""
    if not isinstance(statement, Select):
        return None
    described = statement.column_descriptions
    if described[0].get("entity") is AgentRow and len(described) == 1:
        wanted = str(statement.whereclause.right.value)  # type: ignore[union-attr]
        return Result([ROWS[wanted]] if wanted in ROWS else [])
    return None


class Lifecycles:
    """The lifecycle authority's read of an agent, over the same rows, and nothing else.

    The other members of `AgentLifecycles` exist because `lifecycles_of` accepts only an object
    that has all of them, and none is called: these routes write offers, never an agent's row.
    """

    async def agent(self, agent_id: str) -> FoundAgent | None:
        row = ROWS.get(agent_id)
        record = None if row is None else record_of(row)
        return (
            None if record is None else FoundAgent(record=record, install=None, effective_hash=None)
        )

    async def version(self, *_: Any, **__: Any) -> None:
        raise AssertionError("an offer reads no template version")

    async def live_principal(self, *_: Any, **__: Any) -> None:
        raise AssertionError("an offer checks no person")

    async def change(self, *_: Any, **__: Any) -> bool:
        raise AssertionError("an offer changes no agent row")

    async def widen(self, *_: Any, **__: Any) -> bool:
        raise AssertionError("an offer changes no agent row")

    async def create(self, *_: Any, **__: Any) -> None:
        raise AssertionError("an offer makes no agent")

    async def change_channels(self, *_: Any, **__: Any) -> bool:
        raise AssertionError("an offer changes no channel")


@dataclass
class Kept:
    """`AudienceExtras` in memory: what each agent is offered to, and every write asked of it."""

    held: dict[str, Extras] = field(default_factory=dict)
    writes: list[tuple[str, str, str, str, str]] = field(default_factory=list)

    async def of(self, agent_id: str) -> Extras:
        return self.held.get(agent_id, Extras())

    async def add(self, *, agent_id: str, kind: ExtraKind, value: str, by: str) -> None:
        self.writes.append(("add", agent_id, kind.value, value, by))
        now = await self.of(agent_id)
        self.held[agent_id] = (
            Extras(tuple(sorted({*now.departments, value})), now.people)
            if kind is ExtraKind.DEPARTMENT
            else Extras(now.departments, tuple(sorted({*now.people, value})))
        )

    async def remove(self, *, agent_id: str, kind: ExtraKind, value: str, by: str) -> bool:
        now = await self.of(agent_id)
        present = value in (now.departments if kind is ExtraKind.DEPARTMENT else now.people)
        if not present:
            return False
        self.writes.append(("remove", agent_id, kind.value, value, by))
        self.held[agent_id] = (
            Extras(tuple(one for one in now.departments if one != value), now.people)
            if kind is ExtraKind.DEPARTMENT
            else Extras(now.departments, tuple(one for one in now.people if one != value))
        )
        return True


@dataclass
class Served:
    client: TestClient
    stub: Stub
    kept: Kept

    def view(self, pid: str, agent_id: str) -> Any:
        return get(self.client, pid, f"{API_PREFIX}{AUDIENCE_PATH.format(agent_id=agent_id)}")

    def offer(
        self, pid: str, agent_id: str, kind: str, value: str, *, withdraw: bool = False
    ) -> Any:
        path = REMOVALS_PATH if withdraw else ADDITIONS_PATH
        return self.client.post(
            f"{API_PREFIX}{path.format(agent_id=agent_id)}",
            json={"kind": kind, "value": value},
            headers=headers(pid),
        )


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[Served]:
    async def departments(_factory: Any) -> tuple[str, ...]:
        return DEPARTMENTS

    monkeypatch.setattr(audience_routes, "live_departments", departments)
    with console_client(GRANTS, routers=(router,)) as (client, stub):
        stub.answerers.append(no_audience_extras)
        stub.answerers.append(answer)
        kept = Kept()
        state = client.app.state  # type: ignore[attr-defined]
        state.agent_lifecycles = Lifecycles()
        state.audience_extras = kept
        state.agent_audience_extras_on = True
        yield Served(client, stub, kept)


def switched(served: Served, *, on: bool) -> None:
    served.client.app.state.agent_audience_extras_on = on  # type: ignore[attr-defined]


def refusal(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["message"]


def told(response: Any) -> tuple[int, str, str]:
    body = response.json()
    return response.status_code, body["outcome"], body["sentence"]


# ---------------------------------------------------------------------------- who is told
def test_a_steward_and_a_holder_of_the_authority_are_told_who_an_agent_is_offered_to(
    served: Served,
) -> None:
    """The names beside the level go to the agent's steward and to whoever holds the lifecycle
    authority over its row, and both are told whether they may change them.

    Delete this and the card never shows the people an agent was offered to, so an administrator
    cannot see what they are asked to add to or withdraw."""
    served.kept.held[MINE] = Extras(("sales",), ("u_wide",))
    steward = AudienceView.model_validate(served.view("u_narrow", MINE).json())
    holder = AudienceView.model_validate(served.view("u_admin", MINE).json())
    assert (steward.names_shown, steward.departments, steward.people) == (
        True,
        ["sales"],
        ["u_wide"],
    )
    assert (holder.names_shown, holder.departments, holder.people) == (True, ["sales"], ["u_wide"])
    assert (steward.may_change, holder.may_change) == (False, True)
    assert holder.department_choices == sorted(DEPARTMENTS)
    assert steward.department_choices == []


def test_anybody_else_is_told_the_same_whether_an_agent_is_offered_to_nobody_or_to_many(
    served: Served,
) -> None:
    """A reader who answers for the agent in no way is sent no name and no sentence that says
    names exist, so an agent offered to nobody and one offered to a hundred read identically.

    Delete this and a colleague learns which people were offered a department's agent, which is
    a fact about people they may never have met."""
    bare = served.view("u_prefix", WEB).json()
    served.kept.held[WEB] = Extras(("sales", "finance"), ("u_none", "u_wide"))
    offered = served.view("u_prefix", WEB).json()
    assert bare == offered
    assert (offered["names_shown"], offered["departments"], offered["people"]) == (False, [], [])
    assert offered["refusal"] is None


def test_an_agent_the_caller_may_not_see_is_the_404_an_agent_that_does_not_exist_gets(
    served: Served,
) -> None:
    """The read is a loop over slugs like every agent address. Delete this and the card tells a
    caller outside an agent's audience that the agent exists."""
    hidden = served.view("u_narrow", FINANCE)
    missing = served.view("u_narrow", "no_such_agent")
    assert refusal(hidden) == refusal(missing)
    assert hidden.status_code == 404


# ------------------------------------------------------------------------ changing it
def test_an_offer_is_added_and_withdrawn_in_the_callers_name_when_the_switch_is_on(
    served: Served,
) -> None:
    """The positive case: a holder of the authority offers a web agent to one department and one
    person, the answer lists both, and withdrawing each writes one removal, all in their name.

    Delete this and every refusal below is satisfied by a route that refuses everybody."""
    department = served.offer("u_admin", WEB, "department", "sales")
    person = served.offer("u_admin", WEB, "person", "u_wide")
    assert (department.status_code, person.status_code) == (200, 200), person.text
    body = AudienceView.model_validate(person.json())
    assert (body.departments, body.people) == (["sales"], ["u_wide"])
    assert served.kept.writes == [
        ("add", WEB, "department", "sales", "u_admin"),
        ("add", WEB, "person", "u_wide", "u_admin"),
    ]
    gone = served.offer("u_admin", WEB, "department", "sales", withdraw=True)
    assert gone.status_code == 200
    assert (gone.json()["departments"], gone.json()["people"]) == ([], ["u_wide"])
    assert served.kept.writes[-1] == ("remove", WEB, "department", "sales", "u_admin")


def test_with_the_switch_off_nothing_is_written_and_a_holder_is_told_why(served: Served) -> None:
    """The switch ships off. Delete this and the add and withdraw routes work on an install where
    nobody has answered whether an agent may be offered to several, which is the question the
    switch holds back."""
    switched(served, on=False)
    added = served.offer("u_admin", WEB, "department", "sales")
    removed = served.offer("u_admin", WEB, "department", "sales", withdraw=True)
    assert told(added) == (409, "refused", NOT_SWITCHED_ON) == told(removed)
    assert served.kept.writes == []
    read = AudienceView.model_validate(served.view("u_admin", WEB).json())
    assert (read.may_change, read.refusal) == (False, NOT_SWITCHED_ON)


def test_what_is_stored_is_shown_whether_or_not_the_switch_is_on(served: Served) -> None:
    """Switching it off hides nothing and deletes nothing. Delete this and an install that turned
    the switch off would show an agent as offered to nobody that the roster still offers to
    several, which is a card contradicting the roster."""
    served.kept.held[WEB] = Extras(("sales",), ())
    switched(served, on=False)
    read = AudienceView.model_validate(served.view("u_admin", WEB).json())
    assert read.departments == ["sales"]


def test_a_personal_agent_and_a_company_agent_take_no_offer_whatever_the_switch_says(
    served: Served,
) -> None:
    """A personal agent is found by its owner and nobody else, and a company agent is already
    found by everybody. The one person who can be told so about a personal agent is its owner
    who also holds the authority; everybody else, an administrator included, cannot open it.

    Delete this and a personal agent can be offered to a colleague, which is exactly the leak
    M39.10.3 exists to close."""
    own = served.offer("u_admin", ADMINS_OWN, "person", "u_wide")
    company = served.offer("u_admin", EVERYONE, "department", "sales")
    others = served.offer("u_admin", PRIVATE, "person", "u_wide")
    assert told(own) == (409, "refused", A_PERSONAL_AGENT_IS_FOUND_BY_ITS_OWNER)
    assert told(company) == (409, "refused", A_COMPANY_AGENT_IS_FOUND_BY_EVERYBODY)
    assert refusal(others) == refusal(served.offer("u_admin", "no_such_agent", "person", "u_wide"))
    assert served.kept.writes == []


def test_a_department_the_install_does_not_have_is_refused_and_a_person_is_not_checked(
    served: Served,
) -> None:
    """A word that is nobody's department would be an offer to nobody that looks like one, so it
    is refused; a person is accepted as named, because answering that a principal does not exist
    would tell the asker which ids do.

    Delete this and a typed department is stored and nothing ever matches it, or a refusal
    names which people exist."""
    typed = served.offer("u_admin", WEB, "department", "salse")
    unknown_person = served.offer("u_admin", WEB, "person", "nobody_by_that_name")
    assert told(typed) == (409, "refused", NOT_A_DEPARTMENT_HERE)
    assert unknown_person.status_code == 200
    assert [one[3] for one in served.kept.writes] == ["nobody_by_that_name"]


def test_a_department_that_has_since_gone_can_still_be_withdrawn(served: Served) -> None:
    """Withdrawal checks nothing about the department, only that it was offered. Delete this and
    an offer to a retired department can never be taken back."""
    served.kept.held[WEB] = Extras(("retired",), ())
    gone = served.offer("u_admin", WEB, "department", "retired", withdraw=True)
    assert gone.status_code == 200
    assert gone.json()["departments"] == []


def test_withdrawing_what_was_never_offered_says_so_and_writes_nothing(served: Served) -> None:
    """Delete this and a withdrawal of nothing answers as though it had done something, which is
    how a person comes to believe they have taken an agent away from somebody."""
    again = served.offer("u_admin", WEB, "person", "u_wide", withdraw=True)
    assert told(again) == (409, "refused", NOTHING_TO_WITHDRAW)
    assert served.kept.writes == []


def test_an_agent_is_offered_to_no_more_than_the_bound(served: Served) -> None:
    """Delete this and one agent's offers grow without bound, and the roster's one read of every
    agent's offers grows with them."""
    served.kept.held[WEB] = Extras((), tuple(f"u_{n:03d}" for n in range(MAX_OFFERS)))
    over = served.offer("u_admin", WEB, "person", "u_one_more")
    assert told(over) == (409, "refused", TOO_MANY_OFFERS)
    assert served.kept.writes == []


def test_whoever_may_not_change_an_agent_is_the_one_404_a_missing_agent_gets(
    served: Served,
) -> None:
    """A steward holds no authority, a holder in another department holds none over this row, a
    person with no grant holds none, and the agent may be one nobody can see: all are the answer a
    missing agent gets, and none writes.

    Delete this and the add route tells a stranger which agents exist and lets a steward widen
    their own agent's audience alone, which the owner decided is an administrator's act."""
    missing = refusal(served.offer("u_admin", "no_such_agent", "person", "u_wide"))
    for pid, agent_id in (
        ("u_narrow", MINE),
        ("u_prefix", WEB),
        ("u_none", WEB),
        ("u_wide", FINANCE),
        ("u_admin", FINANCE),
    ):
        got = served.offer(pid, agent_id, "person", "u_wide")
        assert refusal(got) == missing, (pid, agent_id)
    assert missing[0] == 404
    assert served.kept.writes == []


def test_a_malformed_name_is_refused_before_anything_is_read(served: Served) -> None:
    """A name is one word with no spaces. Delete this and a name with a space is stored, and the
    roster's audience predicate matches nobody."""
    spaced = served.offer("u_admin", WEB, "person", "two words")
    empty = served.offer("u_admin", WEB, "person", "")
    assert (spaced.status_code, empty.status_code) == (422, 422)
    assert served.kept.writes == []


def test_the_view_tells_no_name_and_no_refusal_to_a_reader_who_does_not_answer_for_the_agent() -> (
    None
):
    """The view itself, handed names for a reader who answers for nothing, sends none of them and no
    reason the offers cannot be changed. The route reads the names only for a reader they may be
    told to, so over HTTP this is true twice over, and this is the second lock: a caller of
    `audience_view` that read the names for everybody would still send them to nobody.

    Delete this and the guard inside the view is covered only by the route's own, so removing the
    second leaves the first as the one thing between a colleague and the names."""
    from types import SimpleNamespace
    from typing import cast

    record = record_of(ROWS[WEB])
    assert record is not None

    def asking(pid: str) -> Any:
        # A cast at the route's boundary: the view reads these three, and a `Caller` is minted only
        # from a verified token.
        return cast(
            Any,
            SimpleNamespace(
                caller=SimpleNamespace(principal=SimpleNamespace(id=pid)),
                reach=EntitlementSet(principal_id=pid, grants=()),
                now=datetime(2019, 3, 4, tzinfo=UTC),
            ),
        )

    stranger, steward = asking("u_nobody"), asking("u_steward")
    names = Extras(("sales",), ("u_wide",))
    told = audience_routes.audience_view(
        record,
        names,
        stranger,
        switched_on=False,
        departments=DEPARTMENTS,
    )
    assert (told.names_shown, told.departments, told.people, told.refusal) == (False, [], [], None)
    assert (told.may_change, told.department_choices) == (False, [])
    # The sibling: the agent's own steward, handed the same, is told the names, and still not why a
    # change is refused, because they hold no authority to make one.
    own = audience_routes.audience_view(
        record,
        names,
        steward,
        switched_on=False,
        departments=DEPARTMENTS,
    )
    assert (own.names_shown, own.departments, own.people, own.refusal) == (
        True,
        ["sales"],
        ["u_wide"],
        None,
    )


def test_a_reader_who_may_not_change_the_offers_is_not_told_why_they_cannot_be_changed(
    served: Served,
) -> None:
    """With the switch off, the holder of the authority is told it is not switched on and a member
    of the department is told nothing about it, so the sentence cannot reach somebody who has no
    use for it and learns from it that the install has such a switch.

    Delete this and the refusal is sent to every reader of the agent."""
    switched(served, on=False)
    holder = AudienceView.model_validate(served.view("u_admin", WEB).json())
    member = AudienceView.model_validate(served.view("u_narrow", WEB).json())
    assert holder.refusal == NOT_SWITCHED_ON
    assert member.refusal is None
    assert member.may_change is False
