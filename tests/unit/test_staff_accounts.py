"""Who the staff sync gives a sign-in account, links, closes and opens, with no connection.

`brain.identity.staff_accounts.account_plan` over rosters and accounts written here. The calls that
carry the plan out are `tests/unit/test_sign_in_accounts.py`'s, against a stand-in Keycloak.

Task ids: M1.6.16, M1.6.17
"""

from __future__ import annotations

import pytest

from brain.identity.staff_accounts import (
    DEFAULT_ALLOWED,
    NO_ACCOUNTS_FROM_AN_OPEN_LIST,
    YOUR_ACCOUNT_IS_READY,
    AccountRefusal,
    HeldAccount,
    account_plan,
    allowed_types,
    may_have_an_account,
    setting_value,
)
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    Asserts,
    EmploymentStatus,
    EmploymentType,
    Roster,
    StaffRecord,
)

TRUSTED = frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT})


def person(
    name: str,
    *,
    status: EmploymentStatus = EmploymentStatus.ACTIVE,
    kind: EmploymentType | None = EmploymentType.REGULAR,
) -> StaffRecord:
    return StaffRecord(
        f"{name}@example.test",
        name.title(),
        active=status is EmploymentStatus.ACTIVE,
        status=status,
        employment_type=kind,
    )


def roster(*people: StaffRecord, complete: bool = True) -> Roster:
    return Roster(source="lark", people=people, complete=complete, asserts=TRUSTED)


def account(
    name: str, *, enabled: bool = True, made: bool = True, stable: str = "", source: str = "lark"
) -> HeldAccount:
    return HeldAccount(
        account_id=f"kc-{name}",
        email=f"{name}@example.test",
        enabled=enabled,
        source=source if made or stable else "",
        stable_id=stable or (f"on_{name}" if made else ""),
        made_by_sync=made,
    )


STABLE = {f"{n}@example.test": f"on_{n}" for n in ("ada", "bo", "cy", "di", "ed", "fay")}


def test_the_active_and_allowed_are_given_accounts_and_nobody_else_is() -> None:
    """Suspended, gone and never-activated people get none, outsourced people get none by default,
    and somebody whose type the source does not record gets one. Delete this and the sync gives a
    suspended contractor a way in, or gives a whole LDAP company none."""
    plan = account_plan(
        roster(
            person("ada"),
            person("bo", status=EmploymentStatus.SUSPENDED),
            person("cy", status=EmploymentStatus.LEFT),
            person("di", status=EmploymentStatus.NOT_ACTIVATED),
            person("ed", kind=EmploymentType.OUTSOURCED),
            person("fay", kind=None),
        ),
        stable_ids=STABLE,
        accounts=(),
        allowed=DEFAULT_ALLOWED,
        absent_is_gone=False,
    )

    assert [one.person.work_address for one in plan.to_make] == [
        "ada@example.test",
        "fay@example.test",
    ]
    assert [one.stable_id for one in plan.to_make] == ["on_ada", "on_fay"]
    assert plan.refused == {AccountRefusal.NOT_ACTIVE: 3, AccountRefusal.TYPE_NOT_ALLOWED: 1}
    assert plan.to_link == ()
    assert plan.to_enable == plan.to_disable == ()


def test_an_account_is_found_by_the_source_s_identifier_then_by_address_and_never_made_twice() -> (
    None
):
    """Ada's account moved address and is found by her identifier; Bo's was made by hand and is
    found by address and linked, marked, and not made again; Cy's is already the sync's. Delete this
    and every run makes a second account for anybody whose address changed or whose account an
    administrator made first."""
    plan = account_plan(
        roster(person("ada"), person("bo"), person("cy")),
        stable_ids=STABLE,
        accounts=(
            HeldAccount("kc-ada", "ada.old@example.test", True, "lark", "on_ada", True),
            account("bo", made=False),
            account("cy"),
        ),
        allowed=DEFAULT_ALLOWED,
        absent_is_gone=True,
    )

    assert plan.to_make == ()
    assert {one.account.account_id: one.needs_marking for one in plan.to_link} == {
        "kc-ada": False,
        "kc-bo": True,
        "kc-cy": False,
    }
    assert plan.to_disable == plan.to_enable == ()


def test_the_sync_closes_only_accounts_it_made_and_opens_them_again_when_its_person_returns() -> (
    None
):
    """Bo is suspended and his account is the sync's, so it is closed; Cy is suspended and his was
    made by hand, so it is left; Di's closed account is the sync's and she is active again, so it is
    opened. Delete this and the first administrator's account is closed on a directory's word, or
    a returning person stays locked out."""
    plan = account_plan(
        roster(
            person("bo", status=EmploymentStatus.SUSPENDED),
            person("cy", status=EmploymentStatus.SUSPENDED),
            person("di"),
        ),
        stable_ids=STABLE,
        accounts=(account("bo"), account("cy", made=False), account("di", enabled=False)),
        allowed=DEFAULT_ALLOWED,
        absent_is_gone=True,
    )

    assert [one.account_id for one in plan.to_disable] == ["kc-bo"]
    assert [one.account_id for one in plan.to_enable] == ["kc-di"]


def test_an_account_whose_type_is_no_longer_allowed_is_closed() -> None:
    """Delete this and switching outsourced off leaves every outsourced account open."""
    plan = account_plan(
        roster(person("ed", kind=EmploymentType.OUTSOURCED)),
        stable_ids=STABLE,
        accounts=(account("ed"),),
        allowed=DEFAULT_ALLOWED,
        absent_is_gone=False,
    )
    assert [one.account_id for one in plan.to_disable] == ["kc-ed"]
    assert plan.refused == {AccountRefusal.TYPE_NOT_ALLOWED: 1}


@pytest.mark.parametrize(("gone", "closed"), [(True, ["kc-fay"]), (False, [])])
def test_somebody_a_list_no_longer_names_is_closed_only_when_the_list_is_whole(
    gone: bool, closed: list[str]
) -> None:
    """Absence is not departure unless the list promised completeness and was applied before. An
    account of another source is never closed for absence from this one. Delete this and a partial
    read closes everybody it did not reach."""
    plan = account_plan(
        roster(person("ada"), complete=gone),
        stable_ids=STABLE,
        accounts=(
            account("ada"),
            account("fay"),
            account("gil", source="google_workspace"),
        ),
        allowed=DEFAULT_ALLOWED,
        absent_is_gone=gone,
    )
    assert [one.account_id for one in plan.to_disable] == closed
    assert bool(plan.withheld) is not gone


def test_the_plan_reports_counts_and_names_nobody() -> None:
    """Delete this and the report can grow a list of who was refused an account."""
    plan = account_plan(
        roster(person("ada"), person("bo", status=EmploymentStatus.LEFT)),
        stable_ids=STABLE,
        accounts=(account("bo"),),
        allowed=DEFAULT_ALLOWED,
        absent_is_gone=True,
    )
    said = " ".join(plan.sentences())
    assert said == (
        "Sign-in accounts: 1 made, 0 opened again, 1 closed. "
        "No account for 1 suspended, gone or never activated."
    )
    for name in ("ada", "bo", "Ada", "Bo", "kc-bo", "on_ada"):
        assert name not in said


def test_the_setting_names_types_and_says_nothing_for_the_default() -> None:
    """Every type but outsourced by default, held against a list written here. Delete this and the
    default lets outsourced people in, or refuses a type nobody refused."""
    assert allowed_types("") == frozenset(
        {
            EmploymentType.REGULAR,
            EmploymentType.INTERN,
            EmploymentType.LABOUR_DISPATCH,
            EmploymentType.CONSULTANT,
            EmploymentType.CONTRACTOR,
            EmploymentType.OTHER,
        }
    )
    assert allowed_types("regular, outsourced ,nonsense") == frozenset(
        {EmploymentType.REGULAR, EmploymentType.OUTSOURCED}
    )
    assert setting_value([EmploymentType.OUTSOURCED, EmploymentType.REGULAR]) == (
        "regular,outsourced"
    )
    outsourced = person("ed", kind=EmploymentType.OUTSOURCED)
    assert not may_have_an_account(outsourced, allowed_types(""))
    assert may_have_an_account(outsourced, allowed_types("regular,outsourced"))


def test_none_alone_allows_nobody_and_closes_what_the_sync_made() -> None:
    """The install's way to say it wants no accounts made: `none`, which allows no type, so nobody
    is given an account and every account the sync made is closed, while an account a person made
    by hand is left alone. Delete this and `none` can read as blank, which is the default, and let
    everybody in on the install that asked for nobody."""
    assert allowed_types("none") == allowed_types(" NONE ") == frozenset()
    plan = account_plan(
        roster(person("ada"), person("bo")),
        stable_ids=STABLE,
        accounts=[account("ada"), account("bo", made=False)],
        allowed=allowed_types("none"),
        absent_is_gone=False,
    )
    assert plan.to_make == ()
    assert [one.account_id for one in plan.to_disable] == ["kc-ada"]
    assert plan.refused == {AccountRefusal.TYPE_NOT_ALLOWED: 2}


def test_the_sentence_an_administrator_passes_on_says_where_and_what_to_press() -> None:
    """Delete this and the sentence can drift from the flow the owner chose."""
    assert YOUR_ACCOUNT_IS_READY == (
        "Your account is ready. Go to the sign-in page, press Forgot password and enter your "
        "work email."
    )


@pytest.mark.parametrize("source", ["spreadsheet", "google_sheet", "a_source_nobody_listed"])
def test_a_list_anybody_with_the_link_can_edit_makes_closes_and_links_nothing(source: str) -> None:
    """A spreadsheet or a Google Sheet, at the trust it ships with, plans nothing at all: a row
    somebody adds is not an account. Delete this and whoever holds a sheet's link can give an
    address they read a way into the Brain."""
    listed = Roster(
        source=source,
        people=(person("ada"), person("bo", status=EmploymentStatus.LEFT)),
        complete=True,
        asserts=DEFAULT_TRUST.get(source, frozenset({Asserts.EXISTENCE})),
    )
    plan = account_plan(
        listed,
        stable_ids=STABLE,
        accounts=[account("bo", source=source)],
        allowed=DEFAULT_ALLOWED,
        absent_is_gone=True,
    )
    assert (plan.to_make, plan.to_link, plan.to_enable, plan.to_disable) == ((), (), (), ())
    assert plan.withheld == (NO_ACCOUNTS_FROM_AN_OPEN_LIST,)


@pytest.mark.parametrize("source", ["lark", "google_workspace", "microsoft_entra", "ldap"])
def test_every_company_directory_at_its_shipped_trust_gives_accounts(source: str) -> None:
    """The sibling: each directory at the trust it ships with plans an account for an active
    person. Delete this and the guard above can refuse every source with every test green."""
    listed = Roster(
        source=source, people=(person("ada"),), complete=True, asserts=DEFAULT_TRUST[source]
    )
    plan = account_plan(
        listed, stable_ids=STABLE, accounts=[], allowed=DEFAULT_ALLOWED, absent_is_gone=False
    )
    assert [one.stable_id for one in plan.to_make] == ["on_ada"]
    assert plan.withheld == ()
