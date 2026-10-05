"""Who the staff list keeps out of the Brain and lets back in, with no database.

`brain.identity.standing` decides; `tests/unit/test_standing_run.py` is the same against a real
PostgreSQL. Every refusal here has a sibling showing the thing still works.

Task ids: M1.6.14
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.identity.staff_accounts import DEFAULT_ALLOWED
from brain.identity.staff_roster import LeftBecause, MemberWrite, StoredMember, Write, digest_of
from brain.identity.staff_source import EmploymentStatus, EmploymentType, StaffRecord
from brain.identity.standing import (
    WHY_KEPT_OUT,
    Held,
    KeptOut,
    Standing,
    kept_out_because,
    standing_plan,
    standings,
)

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
LONG_AGO = datetime(2019, 3, 1, tzinfo=UTC)

ACTIVE, REGULAR = EmploymentStatus.ACTIVE, EmploymentType.REGULAR


def digest(name: str) -> str:
    return digest_of(f"{name}@example.test")


def held(pid: str, *, disabled: bool = False, by_list: bool = False) -> Held:
    return Held(principal_id=pid, disabled=disabled, changed_by_the_list=by_list)


@pytest.mark.parametrize(
    ("status", "kind", "why"),
    [
        (EmploymentStatus.SUSPENDED, REGULAR, KeptOut.SUSPENDED),
        (EmploymentStatus.LEFT, REGULAR, KeptOut.LEFT),
        (EmploymentStatus.NOT_ACTIVATED, REGULAR, KeptOut.NOT_ACTIVATED),
        (ACTIVE, EmploymentType.OUTSOURCED, KeptOut.TYPE_NOT_ALLOWED),
        (ACTIVE, REGULAR, None),
        (ACTIVE, None, None),
    ],
)
def test_suspended_gone_never_activated_and_a_disallowed_type_are_kept_out_and_nobody_else(
    status: EmploymentStatus, kind: EmploymentType | None, why: KeptOut | None
) -> None:
    """The owner's rule, item by item, and its sibling: an active person of an allowed or unrecorded
    type is let in. Delete this and one word can stop keeping anybody out, or keep everybody out."""
    assert kept_out_because(Standing(status, kind), DEFAULT_ALLOWED) is why


def test_the_reading_speaks_over_the_roster_and_the_roster_over_nothing() -> None:
    """A person marked left before and listed as active today is active; a person no longer listed
    keeps the mark the roster holds; an inactive newcomer the roster never held is judged by the
    reading. Delete this and a returning person stays kept out, or a hand-made account for somebody
    the source never activated is let in."""
    found = standings(
        members=[
            StoredMember(digest("back"), "Back", left_at=LONG_AGO),
            StoredMember(digest("gone"), "Gone", left_at=LONG_AGO),
            StoredMember(digest("here"), "Here"),
        ],
        writes=[
            MemberWrite(
                Write.MARK_LEFT,
                digest("absent"),
                "Absent",
                left_because=LeftBecause.ABSENT_FROM_COMPLETE_ROSTER,
            )
        ],
        people=[
            StaffRecord("back@example.test", "Back", active=True, status=ACTIVE),
            StaffRecord(
                "new@example.test", "New", active=False, status=EmploymentStatus.NOT_ACTIVATED
            ),
        ],
    )
    assert found == {
        digest("back"): Standing(ACTIVE),
        digest("gone"): Standing(EmploymentStatus.LEFT),
        digest("absent"): Standing(EmploymentStatus.LEFT),
        digest("new"): Standing(EmploymentStatus.NOT_ACTIVATED),
    }


def test_a_person_the_list_keeps_out_is_disabled_and_one_it_kept_out_is_let_back_in() -> None:
    """Delete this and the plan can disable nobody, or never let anybody back."""
    plan = standing_plan(
        {
            digest("ada"): Standing(EmploymentStatus.SUSPENDED),
            digest("bo"): Standing(ACTIVE, REGULAR),
            digest("ed"): Standing(ACTIVE, EmploymentType.OUTSOURCED),
        },
        bound={digest("ada"): "u_ada", digest("bo"): "u_bo", digest("ed"): "u_ed"},
        held={
            "u_ada": held("u_ada"),
            "u_bo": held("u_bo", disabled=True, by_list=True),
            "u_ed": held("u_ed"),
        },
        administrators=frozenset({"u_admin"}),
        allowed=DEFAULT_ALLOWED,
    )
    assert plan.to_disable == (("u_ada", KeptOut.SUSPENDED), ("u_ed", KeptOut.TYPE_NOT_ALLOWED))
    assert plan.to_enable == ("u_bo",)
    assert plan.kept_in == ()
    assert plan.sentences() == (
        "Kept out of the Brain: 1 suspended, 1 of a type that may not use the Brain; "
        "1 let back in.",
    )


def test_a_person_an_administrator_disabled_is_not_let_back_in_by_the_list() -> None:
    """`THE_LIST_LETS_BACK_IN_ONLY_WHOM_IT_KEPT_OUT`. Delete this and a nightly run undoes a
    person's decision to disable somebody."""
    plan = standing_plan(
        {digest("bo"): Standing(ACTIVE, REGULAR)},
        bound={digest("bo"): "u_bo"},
        held={"u_bo": held("u_bo", disabled=True, by_list=False)},
        administrators=frozenset(),
        allowed=DEFAULT_ALLOWED,
    )
    assert (plan.to_disable, plan.to_enable, plan.sentences()) == ((), (), ())


def test_the_last_administrator_is_kept_in_and_one_of_two_is_not() -> None:
    """`THE_LAST_ADMINISTRATOR_IS_NEVER_KEPT_OUT`, and its sibling: with another administrator
    still able to sign in, a suspended administrator is kept out like anybody else. Delete this
    and a directory can lock a company out of its install, or shield every administrator for ever.
    """
    where = {digest("ada"): Standing(EmploymentStatus.SUSPENDED)}
    alone = standing_plan(
        where,
        bound={digest("ada"): "u_ada"},
        held={"u_ada": held("u_ada")},
        administrators=frozenset({"u_ada"}),
        allowed=DEFAULT_ALLOWED,
    )
    assert (alone.to_disable, alone.kept_in) == ((), ("u_ada",))
    assert alone.sentences() == (
        "1 kept able to sign in, because keeping them out would leave no administrator.",
    )

    paired = standing_plan(
        where,
        bound={digest("ada"): "u_ada"},
        held={"u_ada": held("u_ada")},
        administrators=frozenset({"u_ada", "u_other"}),
        allowed=DEFAULT_ALLOWED,
    )
    assert (paired.to_disable, paired.kept_in) == ((("u_ada", KeptOut.SUSPENDED),), ())

    # A second administrator who is already disabled cannot sign in either.
    disabled_other = standing_plan(
        where,
        bound={digest("ada"): "u_ada", digest("bo"): "u_other"},
        held={"u_ada": held("u_ada"), "u_other": held("u_other", disabled=True)},
        administrators=frozenset({"u_ada", "u_other"}),
        allowed=DEFAULT_ALLOWED,
    )
    assert disabled_other.kept_in == ("u_ada",)


def test_somebody_with_no_brain_person_and_somebody_already_right_are_left_alone() -> None:
    """Delete this and the plan disables a principal twice, or names somebody nobody can sign in
    as."""
    plan = standing_plan(
        {
            digest("ghost"): Standing(EmploymentStatus.LEFT),
            digest("done"): Standing(EmploymentStatus.LEFT),
            digest("fine"): Standing(ACTIVE, REGULAR),
        },
        bound={digest("done"): "u_done", digest("fine"): "u_fine"},
        held={"u_done": held("u_done", disabled=True, by_list=True), "u_fine": held("u_fine")},
        administrators=frozenset(),
        allowed=DEFAULT_ALLOWED,
    )
    assert (plan.to_disable, plan.to_enable, plan.kept_in) == ((), (), ())


def test_every_reason_a_person_is_kept_out_has_a_sentence_their_page_shows() -> None:
    """Delete this and a new reason reaches the People screen as a blank."""
    assert set(WHY_KEPT_OUT) == set(KeptOut)
    assert all("cannot sign in or ask" in one for one in WHY_KEPT_OUT.values())
