"""A person's own skills over HTTP: listing, adding, bringing in and offering.

The handlers are called with a stand-in store that keeps what it is given, because what is under
test is the route's decisions (the member grant first, the switch, the refusals in words, one answer
for a skill that is not yours and one that was never made); the store's own statements and the
tables' policies are run against a real PostgreSQL in `test_personal_skill_store.py`.

**Every refusal has a sibling proving the permitted case is answered**, which is CLAUDE.md's rule
about a guard tested only by its refusals.

Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3, M40.3.2.4
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.routing import APIRoute

from brain import member_skill_routes
from brain.console.skill_library import LibrarySkill, added, read_package
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.member_skill_routes import (
    ALREADY_HELD,
    ALREADY_OFFERED,
    CATEGORIES_ARE_THE_LIBRARYS,
    MOST_SHOWN,
    PERSONAL_SKILLS_ARE_SWITCHED_OFF,
    TOO_MANY,
    PersonalSkills,
    add_my_skill,
    import_my_skill,
    my_personal_skills,
    offer_my_skill,
    router,
)
from brain.ops.personal_skill_store import MOST_UNOFFERED, Claim, PersonalEntry
from brain.skill_routes import SkillImportAsked, SkillPackageAsked
from tests.fixtures.skill_sources import (
    COMMIT,
    FOLDER,
    OWNER,
    REPOSITORY,
    Resolved,
    github,
    raw_url,
)
from tests.unit.test_skill_library import SKILL_MD, text_with

#: Far from any wall clock, so no grant here can lapse while the suite runs.
NOW = datetime(2999, 1, 1, tzinfo=UTC)

ME = "u_member"
COLLEAGUE = "u_colleague"

MEMBER_GRANTS = tuple(
    Grant(capability=Capability(value=one), scope=Scope.unrestricted())
    for one in ("read:member.home", "read:member.content")
)


def reach(principal: str = ME, *, member: bool = True) -> EntitlementSet:
    return EntitlementSet(principal_id=principal, grants=MEMBER_GRANTS if member else ())


def asked(principal: str = ME, *, member: bool = True) -> Any:
    return SimpleNamespace(
        caller=SimpleNamespace(principal=SimpleNamespace(id=principal)),
        reach=reach(principal, member=member),
        now=NOW,
    )


class FakeStore:
    """A `PersonalSkills` over a dictionary, answering as the real one does."""

    def __init__(self) -> None:
        #: digest to (the skill, its owner, when it was offered).
        self.held: dict[str, tuple[LibrarySkill, str, datetime | None]] = {}

    async def mine(self, owner_id: str, limit: int = 200) -> tuple[PersonalEntry, ...]:
        return tuple(
            PersonalEntry(skill=one, made_at=NOW, offered_at=offered)
            for one, owner, offered in self.held.values()
            if owner == owner_id
        )[:limit]

    async def one_of_mine(self, owner_id: str, digest: str) -> PersonalEntry | None:
        found = self.held.get(digest)
        if found is None or found[1] != owner_id:
            return None
        return PersonalEntry(skill=found[0], made_at=NOW, offered_at=found[2])

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> Claim:
        del ent_hash, trace_id
        if one.digest in self.held:
            return (
                Claim.YOURS_ALREADY
                if self.held[one.digest][1] == one.submitted_by
                else Claim.HELD_ALREADY
            )
        unoffered = sum(
            1
            for _, owner, offered in self.held.values()
            if owner == one.submitted_by and not offered
        )
        if unoffered >= MOST_UNOFFERED:
            return Claim.TOO_MANY
        self.held[one.digest] = (one, one.submitted_by, None)
        return Claim.ADDED

    async def offer(self, owner_id: str, digest: str, at: datetime) -> bool:
        found = self.held.get(digest)
        if found is None or found[1] != owner_id or found[2] is not None:
            return False
        self.held[digest] = (found[0], found[1], at)
        return True


class EmptyLibrary:
    """The department's library as `library_of` answers it: nothing in it, unless told."""

    def __init__(self, skills: Sequence[LibrarySkill] = ()) -> None:
        self.skills = tuple(skills)

    async def library(self, limit: int = 500) -> tuple[LibrarySkill, ...]:
        return self.skills


def a_request(
    store: PersonalSkills, *, on: bool = True, library: EmptyLibrary | None = None, **state: Any
) -> Any:
    held = library or EmptyLibrary()
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                personal_skills=store, personal_skills_on=on, _library=held, **state
            )
        )
    )


@pytest.fixture(autouse=True)
def the_library_is_the_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """`library_of` read from the request, so a test names the library the offer is checked on."""
    monkeypatch.setattr(
        member_skill_routes, "library_of", lambda request: request.app.state._library
    )


def run(call: Callable[[], Any]) -> Any:
    return asyncio.run(call())


def package(text: str = SKILL_MD) -> SkillPackageAsked:
    return SkillPackageAsked(file_name="SKILL.md", content=text, encoding="text")


def add(request: Any, text: str = SKILL_MD, who: str = ME) -> Any:
    return run(lambda: add_my_skill(request, package(text), asked(who)))


def listed(request: Any, who: str = ME) -> Any:
    return run(lambda: my_personal_skills(request, asked(who)))


def digest_of(text: str = SKILL_MD) -> str:
    return added(read_package("SKILL.md", text.encode()), by=ME, at=NOW).digest


# ---------------------------------------------------------------------------------- listing
def test_a_person_sees_the_skills_they_added_and_nobody_elses() -> None:
    """Two people each hold a skill and each list shows one: their own. Delete this and a list
    that returned the whole table would pass every other test here, because each has one person."""
    store = FakeStore()
    request = a_request(store)
    add(request, text_with(name="mine-one"))
    add(request, text_with(name="theirs-one"), who=COLLEAGUE)

    mine = listed(request)
    theirs = listed(request, who=COLLEAGUE)

    assert [one.name for one in mine.skills] == ["mine-one"]
    assert [one.name for one in theirs.skills] == ["theirs-one"]


def test_a_new_skill_reads_as_private_pending_and_studio_written() -> None:
    """The row says where it came from, what a reader has said and what it can do now, and an
    unoffered skill says nothing runs it. Delete this and a list could show a skill as ready that
    nobody has read."""
    request = a_request(FakeStore())
    made = add(request)
    body = listed(request).skills[0]

    assert made.status_code == 201
    assert (body.origin, body.review, body.offered) == ("studio", "pending", False)
    assert body.name == "hosting-expiry"
    assert body.version == "1.0.0"
    assert "Only you can see this" in body.standing
    assert body.may_offer is True


def test_the_list_carries_no_count_of_what_the_reader_cannot_see() -> None:
    """Whatever the install holds for other people, the answer's fields are the person's own
    skills, whether there are more of them, and whether they may add. Delete this and a total beside
    the list is one field away from telling a person how many skills colleagues have written."""
    from brain.ops.jobs import hidden_count_fields

    request = a_request(FakeStore())
    for who in (ME, COLLEAGUE, "u_third"):
        add(request, text_with(name=f"skill-{who.split('_')[1]}"), who=who)
    from brain.member_skill_routes import MemberOwnSkillsView, MemberOwnSkillView

    assert set(MemberOwnSkillsView.model_fields) == {"skills", "more", "may_add", "unavailable"}
    assert hidden_count_fields([MemberOwnSkillsView, MemberOwnSkillView]) == ()
    assert len(listed(request).skills) == 1


def test_a_list_longer_than_one_answer_says_there_is_more_and_never_how_many() -> None:
    """The bound is a resource bound and the answer says only that it was reached. Delete this and
    a long list is either cut silently or carries its length."""
    store = FakeStore()
    request = a_request(store)
    for number in range(MOST_SHOWN + 3):
        one = added(read_package("SKILL.md", text_with(name=f"s-{number}").encode()), by=ME, at=NOW)
        store.held[one.digest] = (one, ME, None)

    body = listed(request)

    assert len(body.skills) == MOST_SHOWN
    assert body.more is True


# ------------------------------------------------------------------------------- the grant
@pytest.mark.parametrize("which", ["list", "add", "import", "offer"])
def test_a_caller_without_the_member_grant_is_refused_every_route_alike(which: str) -> None:
    """The member grant is asked first, before the switch, the store or the key, and the refusal is
    one sentence naming nothing. Delete this and a caller with no grant could tell a switched-off
    install from a switched-on one, or a real key from a made-up one."""
    request = a_request(FakeStore(), on=False)
    calls = {
        "list": lambda: my_personal_skills(request, asked(member=False)),
        "add": lambda: add_my_skill(request, package(), asked(member=False)),
        "import": lambda: import_my_skill(
            request,
            SkillImportAsked(kind="url", url="https://example.test/SKILL.md"),
            asked(member=False),
        ),
        "offer": lambda: offer_my_skill(request, "a" * 64, asked(member=False)),
    }

    with pytest.raises(Absent) as refused:
        run(calls[which])

    assert str(refused.value) == "your skills are not answerable for this caller"


def test_a_caller_with_the_member_grant_is_answered_on_every_route() -> None:
    """The permitted case beside the refusal above. Delete this and a guard that refused everybody
    would pass the test before it."""
    request = a_request(FakeStore())

    assert listed(request).skills == []
    assert add(request).status_code == 201
    done = run(lambda: offer_my_skill(request, digest_of(), asked()))
    assert done.offered is True


# -------------------------------------------------------------------------------- the switch
def test_adding_and_offering_wait_for_the_switch_and_listing_does_not() -> None:
    """With the switch off, a person can still read what they have and is told why they cannot add,
    and neither an add nor an offer writes. Delete this and a switch turned off would hide the
    person's own work, or let a write through."""
    store = FakeStore()
    on = a_request(store)
    add(on)
    off = a_request(store, on=False)

    body = listed(off)
    assert [one.name for one in body.skills] == ["hosting-expiry"]
    assert body.may_add is False
    assert body.unavailable == PERSONAL_SKILLS_ARE_SWITCHED_OFF
    assert body.skills[0].may_offer is False
    with pytest.raises(Absent) as refused:
        add(off, text_with(name="another"))
    assert str(refused.value) == PERSONAL_SKILLS_ARE_SWITCHED_OFF
    with pytest.raises(Absent) as offering:
        run(lambda: offer_my_skill(off, digest_of(), asked()))
    assert str(offering.value) == PERSONAL_SKILLS_ARE_SWITCHED_OFF
    assert len(store.held) == 1
    assert listed(on).may_add is True
    assert listed(on).unavailable == ""


def test_a_process_with_no_database_and_no_override_reads_the_switch_as_off() -> None:
    """With nothing on the application state and no database to ask, the switch is off: a feature
    ships off, and an absent row is off. Delete this and a process that cannot read its switch would
    let a member add skills, since every other test here sets the override."""
    bare = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    assert run(lambda: member_skill_routes.personal_skills_are_on(bare)) is False


def test_the_switch_is_the_one_the_feature_module_declares_and_its_reader_asks_for_it() -> None:
    """The route asks `PERSONAL_SKILLS` about the install's switch and the feature names this
    reader. Delete this and the switch could be renamed away from the function that reads it."""
    from brain.ops.features_declared.personal_skills import PERSONAL_SKILLS

    assert PERSONAL_SKILLS.read_by == ("brain.member_skill_routes:personal_skills_are_on",)
    assert inspect.iscoroutinefunction(member_skill_routes.personal_skills_are_on)


# ---------------------------------------------------------------------------------- adding
def test_the_same_words_added_twice_are_one_skill_and_the_second_answer_is_a_200() -> None:
    """A second press on the same bytes is answered with the skill that is already there. Delete
    this and a double press is either an error or a second copy."""
    store = FakeStore()
    request = a_request(store)

    first = add(request)
    again = add(request)

    assert (first.status_code, again.status_code) == (201, 200)
    assert len(store.held) == 1


def test_words_another_person_holds_are_refused_without_saying_who() -> None:
    """The refusal is one sentence whoever holds the bytes. Delete this and a person could learn
    that a colleague wrote the same procedure by being told so."""
    store = FakeStore()
    request = a_request(store)
    add(request, who=COLLEAGUE)

    with pytest.raises(Absent) as refused:
        add(request)

    assert str(refused.value) == ALREADY_HELD
    assert COLLEAGUE not in str(refused.value)


def test_a_person_may_hold_only_so_many_skills_they_have_not_offered() -> None:
    """The bound that stands in for deletion, which `0232` does not grant. Delete this and one
    person's pastes accumulate in a table nothing prunes. The sibling is the 26th, which is
    refused, beside the one before it, which is not; offering one makes room."""
    store = FakeStore()
    request = a_request(store)
    for number in range(MOST_UNOFFERED):
        assert add(request, text_with(name=f"skill-{number}")).status_code == 201

    with pytest.raises(Absent) as refused:
        add(request, text_with(name="one-too-many"))
    assert str(refused.value) == TOO_MANY

    first = digest_of(text_with(name="skill-0"))
    run(lambda: offer_my_skill(request, first, asked()))
    assert add(request, text_with(name="one-too-many")).status_code == 201


def test_categories_belong_to_the_library_and_a_paste_that_carries_them_is_refused() -> None:
    """A category is set by whoever looks after the library, once the skill is offered. Delete this
    and a member's skill could arrive filed under a category the department's people look in."""
    request = a_request(FakeStore())
    body = SkillPackageAsked(
        file_name="SKILL.md", content=SKILL_MD, encoding="text", categories=("finance",)
    )

    with pytest.raises(Absent) as refused:
        run(lambda: add_my_skill(request, body, asked()))

    assert str(refused.value) == CATEGORIES_ARE_THE_LIBRARYS


def test_a_file_that_is_not_a_skill_is_refused_saying_what_to_change() -> None:
    """A package that does not parse is the parser's refusal, in its words. Delete this and the
    route could store anything it was handed."""
    request = a_request(FakeStore())

    with pytest.raises(Absent) as refused:
        add(request, "no frontmatter here")

    assert "this skill was not added" in str(refused.value)


# --------------------------------------------------------------------------------- importing
def test_a_skill_from_an_address_is_the_persons_own_with_an_address_origin() -> None:
    """Fetched through the install's fetcher and listed with where it came from. Delete this and
    the import could file a fetched skill as one written here, which a reviewer would read
    wrongly."""
    store = FakeStore()
    request = a_request(store, skill_fetcher=github(), skill_resolver=Resolved())
    body = SkillImportAsked(kind="url", url=raw_url())

    made = run(lambda: import_my_skill(request, body, asked()))

    assert made.status_code == 201
    row = listed(request).skills[0]
    assert (row.origin, row.location) == ("url", raw_url())


def test_a_skill_from_a_repository_is_pinned_to_its_commit_and_listed_as_one() -> None:
    """The commit is the address, and the row says repository. Delete this and a pinned skill is
    listed as an upload."""
    store = FakeStore()
    request = a_request(store, skill_fetcher=github(), skill_resolver=Resolved())
    body = SkillImportAsked(
        kind="github", repository=f"{OWNER}/{REPOSITORY}", commit=COMMIT, path=FOLDER
    )

    made = run(lambda: import_my_skill(request, body, asked()))

    assert made.status_code == 201
    row = listed(request).skills[0]
    assert row.origin == "repository"
    assert row.location == f"{OWNER}/{REPOSITORY}"


def test_an_import_asks_the_switch_before_anything_is_fetched() -> None:
    """With the switch off nothing reaches the fetcher, so a member cannot use the server to reach
    an address. Delete this and the switch gates the form and not the fetch."""
    recorded = github()
    request = a_request(FakeStore(), on=False, skill_fetcher=recorded, skill_resolver=Resolved())
    body = SkillImportAsked(kind="url", url="https://example.test/SKILL.md")

    with pytest.raises(Absent) as refused:
        run(lambda: import_my_skill(request, body, asked()))

    assert str(refused.value) == PERSONAL_SKILLS_ARE_SWITCHED_OFF
    assert recorded.connected == []


# ---------------------------------------------------------------------------------- offering
def test_offering_marks_the_skill_offered_once_and_says_what_happens_next() -> None:
    """Offering is allowed once; the answer reads as waiting for a person, and a second offer is
    refused in words. Delete this and a second press moves the skill to the front of a queue it is
    already in."""
    store = FakeStore()
    request = a_request(store)
    add(request)

    done = run(lambda: offer_my_skill(request, digest_of(), asked()))

    assert done.offered is True
    assert done.offered_at == NOW
    assert "Offered to the department" in done.standing
    with pytest.raises(Absent) as refused:
        run(lambda: offer_my_skill(request, digest_of(), asked()))
    assert str(refused.value) == ALREADY_OFFERED


def test_a_skill_that_is_not_yours_and_one_never_made_are_one_answer() -> None:
    """The refusal for a colleague's key and for a key nobody made are the same sentence. Delete
    this and the route is a way to ask whether a colleague has written a particular file."""
    store = FakeStore()
    request = a_request(store)
    add(request, who=COLLEAGUE)

    with pytest.raises(Absent) as theirs:
        run(lambda: offer_my_skill(request, digest_of(), asked()))
    with pytest.raises(Absent) as never:
        run(lambda: offer_my_skill(request, "b" * 64, asked()))

    assert str(theirs.value) == str(never.value)
    assert store.held[digest_of()][2] is None


def test_a_name_the_library_already_spells_differently_is_not_offered() -> None:
    """The library folds a name to one reference and refuses a second spelling; the offer is held to
    the same rule so a reviewer is never asked to read the confusable twin. Delete this and a
    department could end up with `hosting_expiry` beside `hosting-expiry`."""
    store = FakeStore()
    rival = added(
        read_package("SKILL.md", text_with(name="hosting_expiry").encode()), by="u_admin", at=NOW
    )
    request = a_request(store, library=EmptyLibrary([rival]))
    add(request)

    with pytest.raises(Absent) as refused:
        run(lambda: offer_my_skill(request, digest_of(), asked()))

    assert "spelt differently" in str(refused.value)
    assert store.held[digest_of()][2] is None


def test_the_offer_names_no_colleague_no_approver_and_no_state() -> None:
    """Offering takes the skill's key in the path and nothing in a body, so there is nowhere to
    name a reviewer or a decision. Delete this and a body field could write an approval."""
    posts = {
        one.path: one
        for one in router.routes
        if isinstance(one, APIRoute) and "POST" in (one.methods or set())
    }
    offer = posts["/api/v1/me/skills/{digest}/offer"]
    parameters = set(inspect.signature(offer.endpoint).parameters)
    assert parameters == {"request", "digest", "asked"}


def test_every_route_here_is_under_me_and_none_decides() -> None:
    """The surface is four routes under `/me/skills`: no review, assignment or category route.
    Delete this and a route that approved a person's own skill could be added beside the others."""
    found = sorted(
        (method, one.path)
        for one in router.routes
        if isinstance(one, APIRoute)
        for method in (one.methods or set())
    )
    assert found == [
        ("GET", "/api/v1/me/skills"),
        ("POST", "/api/v1/me/skills"),
        ("POST", "/api/v1/me/skills/imports"),
        ("POST", "/api/v1/me/skills/{digest}/offer"),
    ]


def test_the_router_is_mounted_by_the_application() -> None:
    """Imported in `brain.routers`, so the application serves it. Delete this and a router nobody
    mounts is a screen that answers 404 while every test above passes."""
    from brain.routers import ROUTERS

    assert router in ROUTERS
