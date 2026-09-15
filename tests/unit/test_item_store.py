"""The re-verification nag: who is asked, where the rest go, and what is never said.

The first half is decisions and runs anywhere. The second builds `know.item`, the outbox and the
grant tables through the migrations that ship and runs the sweep against them; it skips when
there is no server, as every file using `tests.fixtures.scratch_postgres` does.

The clock is 2999, for the reason CLAUDE.md records.

Task ids: M34.2.1.3
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import psycopg
import pytest

from brain.core.department import department_scope
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.item import (
    KnowledgeError,
    KnowledgeItem,
    KnowledgeState,
    ReverificationTask,
)
from brain.knowledge.item_store import (
    NOTHING_SENDS_A_NAG_YET,
    ItemUnderReview,
    NagRun,
    Route,
    items_for_review,
    nag_event,
    nag_event_id,
    reach_from,
    route_for,
    row_values,
    run_reverification_now,
)
from brain.knowledge.search import KNOWLEDGE_READ, Reach
from brain.knowledge.verification import open_reverification_tasks
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.ops.outbox import MAX_IDENTIFIER_CHARS, EventKind, serialise
from brain.ops.worker import _loop_factory
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.knowledge_items import (
    a_person,
    a_reader,
    a_reader_of_everything,
    knowledge_items,
    nags,
    predecessor,
    put,
)
from tests.fixtures.scratch_postgres import migrate, modelled, present, run, secured, shape, sql

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)

#: A review date that has arrived.
LAPSED = NOW - DAY

#: What a nag must never carry. Chosen to be unmistakable in a byte search.
TITLE = "Renewal pricing for the northern accounts"

TABLES: tuple[str, ...] = ("know.item",)

#: The department registry every reach below is computed against.
DEPARTMENTS: tuple[str, ...] = ("ops", "web")


def reach_of(principal_id: str, department: str) -> Reach | None:
    """What somebody holding `read:knowledge` in one department reaches."""
    return reach_from(
        EntitlementSet(
            principal_id=principal_id,
            grants=(Grant(capability=KNOWLEDGE_READ, scope=department_scope(department)),),
        ),
        departments=DEPARTMENTS,
        now=NOW,
    )


def due(
    item_id: str = "kb.renewals",
    *,
    visibility: Visibility = Visibility.DEPARTMENT,
    state: KnowledgeState = KnowledgeState.PUBLISHED,
) -> ItemUnderReview:
    return ItemUnderReview(
        item_id=item_id,
        owner_id="u_owner",
        title=TITLE,
        state=state,
        visibility=visibility,
        department="web" if visibility is Visibility.DEPARTMENT else "",
        review_by=LAPSED,
    )


def task_for(item: ItemUnderReview) -> ReverificationTask:
    return ReverificationTask(
        item_id=item.item_id, owner_id=item.owner_id, title=item.title, review_by=LAPSED
    )


def an_item(
    item_id: str,
    *,
    owner: str = "u_owner",
    visibility: KnowledgeVisibility | None = None,
    state: KnowledgeState = KnowledgeState.PUBLISHED,
    review_by: datetime | None = LAPSED,
) -> KnowledgeItem:
    item = KnowledgeItem(
        item_id=item_id,
        content="What the document says.",
        title=TITLE,
        visibility=visibility or KnowledgeVisibility.of_department("web", owner_id=owner),
        owner_id=owner,
        state=state,
    )
    if review_by is None:
        return item
    return item.verified(by="u_verifier", at=review_by - 365 * DAY, review_by=review_by)


def sweep(url: str, *, at: datetime = NOW) -> NagRun:
    return run_reverification_now(url, now=at, loop_factory=_loop_factory())


def read_for_review(url: str, *, by: datetime) -> tuple[ItemUnderReview, ...]:
    async def read() -> tuple[ItemUnderReview, ...]:
        made = make_app_engine(url)
        try:
            async with make_session_factory(made)() as session:
                return await items_for_review(session, by=by)
        finally:
            await made.dispose()

    return run(read)


# ------------------------------------------------------------------ who is asked
def test_an_owner_who_still_reaches_the_item_is_the_one_asked() -> None:
    """The positive half of every refusal below: an owner whose grant admits the item's
    department is asked.

    Delete this and a route that never asked anybody would pass every test of where a nag goes
    instead."""
    assert route_for(due(), reach_of("u_owner", "web")) is Route.OWNER


def test_an_owner_who_has_left_the_department_is_not_asked_and_the_department_is() -> None:
    """The finding this leaf was held back for. The owner's grant now names another department,
    or they reach nothing at all, and the published department item goes to its department.

    Delete this and a nag names a document to somebody the gate would refuse it to."""
    assert route_for(due(), reach_of("u_owner", "ops")) is Route.DEPARTMENT
    assert route_for(due(), None) is Route.DEPARTMENT


def test_a_company_item_whose_owner_reads_nothing_goes_to_the_company() -> None:
    """A company item reaches every reader of the plane, so any read of it at all is enough for
    the owner to be asked, and no read sends it to the company.

    Delete this and a company item whose steward left is either asked of nobody or of them."""
    company = due(visibility=Visibility.COMPANY)

    assert route_for(company, None) is Route.COMPANY
    assert route_for(company, reach_of("u_owner", "ops")) is Route.OWNER


def test_what_only_the_owner_may_reach_is_held_rather_than_routed() -> None:
    """A personal item and a draft are their owner's alone, so an owner who cannot reach one
    holds it and nobody else is told. The siblings: the same owner who can reach it is asked.

    Delete this and a draft or a personal note goes to a department that was never meant to
    know it exists."""
    personal = due(visibility=Visibility.PERSONAL)
    draft = due(state=KnowledgeState.DRAFT)

    assert route_for(personal, None) is Route.HELD
    assert route_for(personal, reach_of("u_owner", "ops")) is Route.OWNER
    assert route_for(draft, reach_of("u_owner", "ops")) is Route.HELD
    assert route_for(draft, reach_of("u_owner", "web")) is Route.OWNER


def test_a_reach_that_belongs_to_somebody_else_is_refused() -> None:
    """Another person's reach cannot decide whether this owner is asked.

    Delete this and a caller holding the wrong variable routes an item to its owner on the
    strength of a colleague's grant."""
    with pytest.raises(KnowledgeError, match="offered to route"):
        route_for(due(), reach_of("u_somebody_else", "web"))


def test_a_grant_the_document_plane_cannot_reduce_reaches_nothing_here() -> None:
    """A `read:knowledge` grant scoped on something other than a department is refused by
    `reach_for`, and the sweep reads that as no reach rather than stopping. A department grant
    still reaches its department.

    Delete this and one oddly written grant stops every owner being asked."""
    by_owner = EntitlementSet(
        principal_id="u_owner",
        grants=(
            Grant(
                capability=KNOWLEDGE_READ,
                scope=Scope(clauses=(Clause(field="owner_id", op=Op.EQ, value="u_owner"),)),
            ),
        ),
    )
    found = reach_of("u_owner", "web")

    assert reach_from(by_owner, departments=DEPARTMENTS, now=NOW) is None
    assert found is not None
    assert found.departments == ("web",)


# ------------------------------------------------------------------ what is recorded
def test_a_nag_carries_no_title_and_names_the_owner_only_when_the_owner_is_asked() -> None:
    """The three routed events, byte for byte: identifiers, a route and a date. The owner is
    named only on the owner's route, the department only on the department's, and a held item
    has no event at all.

    Delete this and the title, or the name of an owner who has left, travels in an event read
    by whoever holds a webhook endpoint."""
    item = due()
    task = task_for(item)
    stamp = LAPSED.isoformat()
    asked = nag_event(task, Route.OWNER, department="web", now=NOW)
    routed = nag_event(task, Route.DEPARTMENT, department="web", now=NOW)
    company = nag_event(task, Route.COMPANY, department="", now=NOW)

    assert dict(asked.attributes) == {"route": "owner", "review_by": stamp, "recipient": "u_owner"}
    assert dict(routed.attributes) == {
        "route": "department",
        "review_by": stamp,
        "department": "web",
    }
    assert dict(company.attributes) == {"route": "company", "review_by": stamp}
    for one in (asked, routed, company):
        assert one.kind is EventKind.APPROVAL_REQUESTED
        assert one.entity == "knowledge_item"
        assert one.record_id == "kb.renewals"
        assert TITLE.encode() not in serialise(one)
    assert b"u_owner" not in serialise(routed)
    with pytest.raises(KnowledgeError, match="held"):
        nag_event(task, Route.HELD, department="web", now=NOW)


def test_a_nag_is_named_by_its_item_and_review_date_and_by_nothing_else() -> None:
    """One id for one item and review date, whatever offset the date arrived in and whenever the
    nag was recorded, and a different id for another date or another item, inside the outbox's
    identifier limit for the longest item id the grammar admits.

    Delete this and the log that stops a second nag stops matching the nag it recorded."""
    key = ("kb.renewals", LAPSED)
    elsewhere = LAPSED.astimezone(timezone(timedelta(hours=8)))
    longest = "k" * 128
    task = task_for(due())

    assert nag_event_id(key) == nag_event_id(("kb.renewals", elsewhere))
    assert nag_event_id(key) != nag_event_id(("kb.renewals", LAPSED + DAY))
    assert nag_event_id(key) != nag_event_id(("kb.pricing", LAPSED))
    assert nag_event_id((longest, LAPSED)).startswith("reverification.")
    assert len(nag_event_id((longest, LAPSED))) <= MAX_IDENTIFIER_CHARS
    assert (
        nag_event(task, Route.OWNER, department="web", now=NOW + DAY).event_id
        == nag_event(task, Route.OWNER, department="web", now=NOW).event_id
    )


def test_a_personal_item_whose_visibility_names_somebody_else_is_refused_before_it_is_written() -> (
    None
):
    """One owner column serves as the steward and as the only reader of a personal item, so an
    item personal to one person and stewarded by another is refused. The siblings: a matching
    personal item, and a department item, are stored as they are.

    Delete this and a personal note is stored readable by its steward and not by its writer."""
    stray = KnowledgeItem(
        item_id="kb.notes",
        content="x",
        title=TITLE,
        visibility=KnowledgeVisibility.personal("u_writer"),
        owner_id="u_steward",
    )
    mine = stray.model_copy(update={"owner_id": "u_writer"})
    stored = row_values(an_item("kb.renewals"))

    with pytest.raises(KnowledgeError, match="one owner column"):
        row_values(stray)
    assert row_values(mine)["owner_id"] == "u_writer"
    assert row_values(mine)["department"] is None
    assert row_values(mine)["visibility"] == "personal"
    assert (stored["department"], stored["state"], stored["verified_by"]) == (
        "web",
        "published",
        "u_verifier",
    )
    assert (stored["review_by"], stored["supersedes"]) == (LAPSED, None)


def test_the_run_summary_is_three_answers_and_says_that_nothing_is_sent() -> None:
    """Each flag reads as yes or no in its own place, and every summary says nothing is sent.

    Delete this and a control run recorded as ok reads as owners having been told."""
    busy = NagRun(recorded=True, held=False, more_waiting=True).summary(NOW)
    quiet = NagRun(held=True).summary(NOW)

    assert "a nag was recorded: yes;" in busy
    assert "was held: no;" in busy
    assert "one run asks about: yes." in busy
    assert "a nag was recorded: no;" in quiet
    assert "was held: yes;" in quiet
    assert "one run asks about: no." in quiet
    assert NOTHING_SENDS_A_NAG_YET in busy and NOTHING_SENDS_A_NAG_YET in quiet


def test_the_sweep_decides_over_rows_that_hold_no_text() -> None:
    """`open_reverification_tasks` takes a row with no content, a replaced one is not due, and a
    row is judged by reach in the shape a chunk row has.

    Delete this and the sweep needs the corpus it has no reach over."""
    kept = due("kb.kept")
    replaced = due("kb.replaced", state=KnowledgeState.SUPERSEDED)
    company = due(visibility=Visibility.COMPANY)

    assert [one.item_id for one in open_reverification_tasks((kept, replaced), now=NOW).tasks] == [
        "kb.kept"
    ]
    assert kept.reach_row() == {
        "deleted_at": None,
        "state": "published",
        "owner_id": "u_owner",
        "visibility": "department",
        "department": "web",
    }
    assert company.reach_row()["department"] is None


# ------------------------------------------------------------------ against the database
def test_the_items_for_review_are_the_retrievable_ones_whose_date_has_arrived() -> None:
    """A lapsed published item and a lapsed draft are read, oldest date first, with every
    column; a later date, a replaced item and an undated one are not.

    Delete this and the sweep can read superseded documents, or none."""
    with knowledge_items("brain_kr_items_for_review") as url:
        put(
            url,
            an_item("kb.a_lapsed"),
            an_item("kb.b_draft", state=KnowledgeState.DRAFT),
            an_item("kb.c_later", review_by=NOW + 30 * DAY),
            an_item("kb.d_replaced", state=KnowledgeState.SUPERSEDED),
            an_item("kb.e_undated", review_by=None),
        )
        now_due = read_for_review(url, by=NOW)
        later = read_for_review(url, by=NOW + 31 * DAY)

    assert [one.item_id for one in now_due] == ["kb.a_lapsed", "kb.b_draft"]
    assert [one.item_id for one in later] == ["kb.a_lapsed", "kb.b_draft", "kb.c_later"]
    first = now_due[0]
    assert (first.owner_id, first.title, first.state, first.visibility) == (
        "u_owner",
        TITLE,
        KnowledgeState.PUBLISHED,
        Visibility.DEPARTMENT,
    )
    assert (first.department, first.review_by) == ("web", LAPSED)


def test_the_application_role_reads_a_department_item_only_with_its_department() -> None:
    """As `brain_app` with no settings a department item is invisible, the sweep's function
    still returns it, and with the department set the item is visible.

    Delete this and the table's policy can be dropped, or the function stop reading past it,
    with every superuser test still green."""
    with knowledge_items("brain_kr_policy") as url:
        put(url, an_item("kb.renewals"))
        with psycopg.connect(url) as conn:
            conn.execute("SET ROLE brain_app")
            unset = conn.execute("SELECT count(*) FROM know.item").fetchone()
            swept = conn.execute(
                "SELECT count(*) FROM know.items_for_review(%s)", (NOW,)
            ).fetchone()
            conn.execute("SELECT set_config('app.departments', 'web', true)")
            set_ = conn.execute("SELECT count(*) FROM know.item").fetchone()
            conn.rollback()

    assert unset == (0,)
    assert swept == (1,)
    assert set_ == (1,)


def test_a_run_asks_the_owner_who_reaches_the_item_and_routes_the_one_who_left() -> None:
    """Three owners, end to end through the store: one still reads the department and is asked,
    one's grant moved to another department and their item goes to its department without their
    name, and one reads nothing and owns a personal item, which is held. Nothing stored names the
    title, the owner who left or the held item.

    Delete this and the store can route on a reach it never resolved."""
    stamp = LAPSED.isoformat()
    with knowledge_items("brain_kr_run") as url:
        a_person(url, "u_stays")
        a_reader(url, "u_stays", "web")
        a_person(url, "u_moved")
        a_reader(url, "u_moved", "ops")
        a_person(url, "u_private")
        put(
            url,
            an_item("kb.kept", owner="u_stays"),
            an_item("kb.moved", owner="u_moved"),
            an_item(
                "kb.notes", owner="u_private", visibility=KnowledgeVisibility.personal("u_private")
            ),
        )
        said = sweep(url)
        found = nags(url)
        stored = json.dumps(sql(url, "SELECT * FROM ops.outbox_event"), default=str)

    assert said == NagRun(recorded=True, held=True, more_waiting=False)
    assert found == [
        ("kb.kept", {"route": "owner", "recipient": "u_stays", "review_by": stamp}),
        ("kb.moved", {"route": "department", "department": "web", "review_by": stamp}),
    ]
    assert TITLE not in stored
    assert "u_moved" not in stored
    assert "kb.notes" not in stored


def test_a_second_run_asks_nothing_and_a_new_review_date_asks_again() -> None:
    """The log is the outbox: the same lapsed date is asked once however often the sweep runs,
    and re-verifying with a new date that has also lapsed asks again.

    Delete this and every owner is asked about the same document every morning."""
    with knowledge_items("brain_kr_second_run") as url:
        a_person(url, "u_owner")
        a_reader(url, "u_owner", "web")
        put(url, an_item("kb.renewals"))

        first = sweep(url)
        second = sweep(url)
        after_second = len(nags(url))
        put(url, an_item("kb.renewals", review_by=NOW - timedelta(hours=1)))
        third = sweep(url)
        after_third = len(nags(url))

    assert first.recorded is True
    assert second == NagRun()
    assert after_second == 1
    assert third.recorded is True
    assert after_third == 2


def test_a_held_item_is_asked_about_once_its_owner_can_reach_it_again() -> None:
    """Held is deferred and not dropped: nothing is recorded while the owner reads nothing, and
    the first run after they are granted a read asks them.

    Delete this and a held item is lost the day it is held."""
    with knowledge_items("brain_kr_held") as url:
        a_person(url, "u_private")
        put(
            url,
            an_item(
                "kb.notes", owner="u_private", visibility=KnowledgeVisibility.personal("u_private")
            ),
        )
        held = sweep(url)
        while_held = nags(url)
        a_reader(url, "u_private", "web")
        asked = sweep(url)
        found = nags(url)

    assert held == NagRun(held=True)
    assert while_held == []
    assert asked == NagRun(recorded=True)
    assert found == [
        ("kb.notes", {"route": "owner", "recipient": "u_private", "review_by": LAPSED.isoformat()})
    ]


def test_an_owner_is_asked_about_five_at_a_time_and_the_rest_wait_for_the_next_run() -> None:
    """The per-owner bound reaches the store and defers rather than drops: six lapsed items for
    one owner are five nags and a run that says more are waiting, and the next run asks about
    the sixth.

    Delete this and the store can drop what the bound defers, or stop saying the sweep is
    behind."""
    with knowledge_items("brain_kr_bound") as url:
        a_person(url, "u_owner")
        a_reader(url, "u_owner", "web")
        put(url, *(an_item(f"kb.item_{number}") for number in range(6)))
        first = sweep(url)
        after_first = len(nags(url))
        second = sweep(url)
        after_second = len(nags(url))

    assert first == NagRun(recorded=True, more_waiting=True)
    assert after_first == 5
    assert second == NagRun(recorded=True)
    assert after_second == 6


def test_an_item_is_asked_about_a_working_week_before_its_review_date() -> None:
    """The lead time reaches the read: an item due in three days is asked about now, and one
    due in a fortnight is not.

    Delete this and every nag arrives on or after the day the review has already lapsed."""
    with knowledge_items("brain_kr_lead") as url:
        a_person(url, "u_owner")
        a_reader(url, "u_owner", "web")
        put(
            url,
            an_item("kb.soon", review_by=NOW + 3 * DAY),
            an_item("kb.later", review_by=NOW + 14 * DAY),
        )
        said = sweep(url)
        found = [record for record, _ in nags(url)]

    assert said == NagRun(recorded=True)
    assert found == ["kb.soon"]


def test_an_owner_who_reads_everything_is_asked_about_a_company_item() -> None:
    """A company item has no department, so no department is judged: an owner holding an
    unrestricted read is asked about it rather than having it routed to the company.

    Delete this and an item with no department can be judged against an empty department name,
    which the reach refuses, so every company item's owner stops being asked."""
    with knowledge_items("brain_kr_everything") as url:
        a_person(url, "u_owner")
        a_reader_of_everything(url, "u_owner")
        # Built verified in one step: a published company item nobody has verified is refused.
        handbook = KnowledgeItem(
            item_id="kb.handbook",
            content="What the document says.",
            title=TITLE,
            visibility=KnowledgeVisibility.company(owner_id="u_owner"),
            owner_id="u_owner",
            state=KnowledgeState.PUBLISHED,
            verified_by="u_verifier",
            verified_at=LAPSED - 365 * DAY,
            review_by=LAPSED,
        )
        put(url, handbook)
        said = sweep(url)
        found = nags(url)

    assert said == NagRun(recorded=True)
    assert found == [
        ("kb.handbook", {"route": "owner", "recipient": "u_owner", "review_by": LAPSED.isoformat()})
    ]


def test_an_owner_who_was_disabled_and_one_who_never_existed_are_routed_alike() -> None:
    """DENIED and ABSENT as one answer: a disabled owner still holding a grant, and an owner id
    no principal has, produce identical nags that differ only in the item they name.

    Delete this and the routing of a nag tells a subscriber which owners are real."""
    with knowledge_items("brain_kr_alike") as url:
        a_person(url, "u_gone", disabled_at=NOW - 30 * DAY)
        a_reader(url, "u_gone", "web")
        put(url, an_item("kb.gone", owner="u_gone"), an_item("kb.ghost", owner="u_nobody"))
        sweep(url)
        routes = dict(nags(url))

    expected = {"route": "department", "department": "web", "review_by": LAPSED.isoformat()}
    assert routes == {"kb.ghost": expected, "kb.gone": expected}


def test_the_table_refuses_a_department_it_could_not_split_or_one_it_does_not_name() -> None:
    """The two constraints the policy rests on, and half a verification, refused by the
    database; a well-formed department item is accepted.

    Delete this and a comma in a department splits into a department nobody granted."""
    insert = (
        "INSERT INTO know.item (item_id, owner_id, visibility, department, state, verified_by) "
        "VALUES (%s, 'u_owner', 'department', %s, 'published', %s)"
    )
    with knowledge_items("brain_kr_constraints") as url:
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "kb.comma", "web,ops", None)
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "kb.nowhere", None, None)
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "kb.half", "web", "u_verifier")
        sql(url, insert, "kb.fine", "web", None)
        stored = sql(url, "SELECT item_id FROM know.item")

    assert stored == [("kb.fine",)]


def test_the_migration_builds_exactly_what_the_model_declares() -> None:
    """Every constraint, index and column of `know.item`, compared between `0040` and the model.

    Delete this and the migration and the model can disagree about a constraint's name, which
    is the one thing a later migration dropping it has to get right."""
    with (
        knowledge_items("brain_kr_shape") as url,
        modelled("brain_kr_shape_modelled", TABLES) as from_models,
    ):
        assert shape(url, TABLES) == shape(from_models, TABLES)
        assert secured(url, TABLES) == dict.fromkeys(TABLES, True)


def test_the_migration_comes_down_and_goes_back_up() -> None:
    """Upgrade, downgrade and upgrade again: the table and its function go and come back.

    Delete this and a downgrade that leaves the function behind is found when the table it
    names is gone."""
    function = "SELECT to_regprocedure('know.items_for_review(timestamptz)')::text"
    with knowledge_items("brain_kr_round_trip") as url:
        migrate("brain_kr_round_trip", "downgrade", predecessor())
        gone = (present(url, TABLES), sql(url, function))
        migrate("brain_kr_round_trip", "upgrade", "0040")
        back = (present(url, TABLES), sql(url, function))

    assert gone == (set(), [(None,)])
    assert back == (set(TABLES), [("know.items_for_review(timestamp with time zone)",)])
