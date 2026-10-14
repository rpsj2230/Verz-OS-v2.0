"""`GET /install` as it carries how long approvals wait: what a reader is told and what it is not.

`tests/unit/test_approval_wait.py` holds the pure half and the check. What was missing was the
route: the one place where a reader's capability, a database that may be absent or broken, and the
two facts about approvals meet. Driven through the real application, with the token machinery of
`tests/unit/test_install_routes.py`, and a session that records the statement it was asked and
answers a fixed set of rows, so the SQL the route sends is itself under test.

**What is asserted is the disclosure, not only the figure.** The wait is a median, so the body must
not change with how many approvals were decided; a refusal must be the one refusal whatever this
process can read, and must leave the database unasked; and the statement may name two columns of
one view and no person. Every refusal here has a sibling that reads, because a guard tested only
by its refusals is satisfied by a route that refuses everybody.

Task ids: M35.4.5, M35.3.2.2
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fixtures.setting_rows import Result
from tests.unit.test_install_routes import INSTALL_PATH, _app, _wiring, facts_of, get

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock. The
#: route's own `now` is the real one and the session below ignores it, so only the differences
#: between the two instants of a row matter.
DECIDED = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)

WAIT = "typical approval wait"
PUSH = "push notifications for approvals"


def waits(*hours: float) -> list[tuple[datetime, datetime]]:
    """One decided approval per figure: raised that many hours before it was decided."""
    return [(DECIDED - timedelta(hours=one), DECIDED) for one in hours]


class Asked:
    """Every statement the route sent to the database, in order."""

    def __init__(self) -> None:
        self.statements: list[Any] = []


def sessions_answering(
    rows: Sequence[tuple[datetime, datetime]], *, broken: bool = False
) -> tuple[async_sessionmaker[AsyncSession], Asked]:
    """A session factory answering these rows, or failing as an un-upgraded database does."""
    asked = Asked()

    class WaitSession(AsyncSession):
        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            asked.statements.append(statement)
            if broken:
                raise OperationalError("SELECT", {}, Exception("relation does not exist"))
            return Result(rows)

        async def close(self) -> None:
            return None

    return async_sessionmaker(class_=WaitSession), asked


def read_install(
    pid: str,
    *,
    rows: Sequence[tuple[datetime, datetime]] = (),
    broken: bool = False,
    database: bool = True,
) -> tuple[Any, Asked]:
    """`GET /install` as this person, against a process wired as the arguments say."""
    sessions, asked = sessions_answering(rows, broken=broken)
    app = _app()
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = _wiring()
        app.state.db_sessions = sessions if database else None
        return get(client, pid, INSTALL_PATH), asked


def test_the_install_screen_gives_the_typical_wait_and_says_push_is_now_worth_building() -> None:
    """Six, five and one hours: the median of five is past the stated four, so push is reported due.

    Delete this and the figure the owner asked for can stop reaching the screen, or its verdict can
    be computed and never shown, while every pure test goes on passing."""
    response, _ = read_install("u_narrow", rows=waits(6, 5, 1))

    assert response.status_code == 200
    facts = facts_of(response.json())
    assert facts[WAIT]["source"] == "measured" and facts[WAIT]["value"] == "5 hours"
    assert facts[PUSH]["source"] == "measured"
    assert facts[PUSH]["value"].startswith("now worth building")


def test_a_quick_install_is_told_that_push_is_not_needed_yet() -> None:
    """The other side of the line, beside the one above. Delete this and a route that always
    reports push as due would pass, and a quiet install would be told to build a feature."""
    response, _ = read_install("u_narrow", rows=waits(1, 1, 2))

    facts = facts_of(response.json())
    assert facts[WAIT]["value"] == "1 hour"
    assert facts[PUSH]["value"].startswith("not needed yet")


def test_the_body_is_the_same_whether_three_approvals_were_decided_or_thirty_one() -> None:
    """**No count of anything.** Three decisions and thirty-one, both with a median of two hours,
    answer one body, whole: a figure that moved with how many people were asked is a count read off
    the page. The keys are checked too, because a `total` added beside the facts is the usual way a
    count arrives.

    Delete this and a fact such as 'based on 31 decisions' can be added to the wait, which tells a
    reader how many approvals the install's people were asked for."""
    few, _ = read_install("u_narrow", rows=waits(2, 2, 2))
    many, _ = read_install("u_narrow", rows=waits(*([2.0] * 31)))

    assert few.status_code == many.status_code == 200
    assert few.json() == many.json()
    for body in (few.json(), many.json()):
        assert {"total", "count", "truncated", "hidden", "withheld", "omitted"}.isdisjoint(
            set(body) | {key for one in body["facts"] for key in one}
        )


def test_a_reader_who_may_not_open_the_screen_is_answered_as_if_it_were_absent() -> None:
    """**DENIED and ABSENT leave as one answer, whatever this process can read.** A caller holding
    nothing is refused with the same status and message on a process with rows, on one whose
    database fails and on one with no database, and the wait is mentioned by none of them. Compared
    with each other rather than to a literal, because the literal is the thing under test.

    Delete this and a refusal can differ with how the deployment is wired, which tells anybody who
    can reach the port whether approvals have ever been decided here."""
    answers = [
        read_install("u_none", rows=waits(6, 5, 1))[0],
        read_install("u_none", broken=True)[0],
        read_install("u_none", database=False)[0],
    ]

    assert {one.status_code for one in answers} == {404}
    assert len({one.json()["message"] for one in answers}) == 1
    for one in answers:
        assert WAIT not in one.text and PUSH not in one.text


def test_a_refused_reader_leaves_the_database_unasked_and_an_entitled_one_does_not() -> None:
    """The capability is checked before the view is read. The refused reader's session is asked
    nothing, and the entitled reader's is asked, which is the sibling that stops this passing for a
    route that never reads at all.

    Delete this and the read can move above the check, which makes a refusal cost a query and lets
    the timing of a 404 say whether this install has decided any approvals."""
    _, refused = read_install("u_none", rows=waits(6, 5, 1))
    _, entitled = read_install("u_narrow", rows=waits(6, 5, 1))

    assert refused.statements == []
    assert len(entitled.statements) == 1


def test_an_install_with_nothing_decided_is_told_unknown_with_the_reason_and_no_wait() -> None:
    """No approval decided: the fact is unknown, carries a reason and no value, and there is no
    sentence about push. A wait of nothing would read as 'answered at once'.

    Delete this and an install nobody has approved anything on is shown a figure of zero, which
    keeps push deferred on no evidence and looks like good news."""
    response, _ = read_install("u_narrow", rows=())

    facts = facts_of(response.json())
    assert facts[WAIT]["source"] == "unknown"
    assert facts[WAIT]["value"] == ""
    assert "no approval has been decided" in facts[WAIT]["because"]
    assert PUSH not in facts


def test_a_database_that_cannot_be_asked_is_unknown_and_the_screen_still_answers() -> None:
    """A view the database lacks (an install not yet upgraded) fails the read. The screen answers
    200 with its other facts, and the wait is unknown with a reason that says the database could
    not be asked, which is a different sentence from the empty case.

    Delete this and one missing view turns the whole This install screen into an error, or the
    failure is shown as a wait of nothing."""
    broken, _ = read_install("u_narrow", broken=True)
    empty, _ = read_install("u_narrow", rows=())

    assert broken.status_code == 200
    facts = facts_of(broken.json())
    assert facts[WAIT]["source"] == "unknown" and facts[WAIT]["value"] == ""
    assert "could not be asked" in facts[WAIT]["because"]
    assert facts[WAIT]["because"] != facts_of(empty.json())[WAIT]["because"]
    assert PUSH not in facts
    assert any(name not in {WAIT, PUSH} for name in facts)


def test_a_process_with_no_database_answers_the_other_facts_and_says_nothing_of_the_wait() -> None:
    """No session factory at all, as in a process started without a database. The screen answers
    and mentions no wait, rather than failing or inventing one.

    Delete this and a process without a database cannot open the Install screen."""
    response, asked = read_install("u_narrow", database=False)

    assert response.status_code == 200
    facts = facts_of(response.json())
    assert WAIT not in facts and PUSH not in facts and facts
    assert asked.statements == []


def test_the_statement_reads_two_columns_of_one_view_and_binds_no_person() -> None:
    """**What the route asks the database, taken from the statement it sent.** The select list is
    exactly the two times, the table is the view, and the only bound values are a start and a
    bound on rows, so no reader and no approval is named. The start is about a quarter back.

    Delete this and the read can be widened to the suspension table or can carry the caller's id,
    which turns an aggregate of two times into a look at who was asked what."""
    _, asked = read_install("u_narrow", rows=waits(1))
    before = datetime.now(UTC)
    [statement] = asked.statements
    sql = " ".join(str(statement).split())
    shape = re.fullmatch(r"SELECT (.+?) FROM (\S+)( WHERE .*)?", sql, flags=re.IGNORECASE)

    assert shape is not None
    assert {column.strip() for column in shape.group(1).split(",")} == {"raised_at", "decided_at"}
    assert shape.group(2) == "gate.approval_wait"
    params = statement.compile().params
    assert set(params) == {"since", "most"}
    assert timedelta(days=89) < before - params["since"] < timedelta(days=91)
    assert isinstance(params["most"], int) and params["most"] > 0
