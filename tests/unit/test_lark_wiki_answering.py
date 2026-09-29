"""A switched-on Lark Wiki on Ask: what is switched on, a declared space, the words, the reach.

The live walk runs over the install check's own recorded wiki
(`brain.ops.acceptance_checks_lark_wiki`), so the bodies these tests read are the bodies the check
reads; the database half is that check's own test. Dates are pinned far from any wall clock.

Task ids: M11.6.4
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.acceptance_checks_connectors import _Resolver
from brain.ops.acceptance_checks_lark_base import HOST, _AppKeys, _Issuer
from brain.ops.acceptance_checks_lark_wiki import _NoLibrary, _Page, _RecordedWiki
from brain.ops.lark_wiki_live import (
    COMPANY,
    DEPARTMENT,
    LARK_WIKI_USE,
    MAX_WORDS,
    SPACES_NAMESPACE,
    WikiPassages,
    WithWiki,
    declaration_of,
    space_key,
    space_value,
    told_to,
    wiki_host,
    words_of,
)
from brain.ops.setting_store import SettingState

LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
SPACE = "7034502641455497244"
STEWARD = "u_steward"


def state(value: Any) -> SettingState:
    return SettingState(
        key=space_key(SPACE),
        value_type="json",
        value=value,
        updated_by=STEWARD,
        updated_at=LONG_AGO,
    )


def reader(*grants: tuple[str, Scope]) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(Grant(capability=Capability(value=c), scope=s) for c, s in grants),
    )


def test_the_wiki_is_read_only_with_knowledge_from_wiki_chosen_on_a_known_platform() -> None:
    """Delete this and a Wiki switched off in Connect Lark can still be walked on every question."""
    on = {
        "INSTALL_LARK_USES": f"staff_list,{LARK_WIKI_USE}",
        "INSTALL_LARK_PLATFORM": "larksuite.com",
    }
    assert wiki_host(lambda name: on.get(name, "")) == HOST
    assert wiki_host(lambda name: {**on, "INSTALL_LARK_USES": "staff_list"}.get(name, "")) is None
    assert wiki_host(lambda name: {**on, "INSTALL_LARK_PLATFORM": "x"}.get(name, "")) is None


def test_the_use_read_is_the_one_connect_lark_saves() -> None:
    """Held against `brain.ops.lark_connect.Use.WIKI`, which this module restates. Delete this and
    a renamed use leaves every Wiki switched on and read by nothing."""
    from brain.ops.lark_connect import Use

    assert Use.WIKI.value == LARK_WIKI_USE


def test_a_space_is_declared_at_a_reach_and_its_writer_is_its_steward() -> None:
    """`A_SPACE_IS_READ_ONLY_WHERE_SOMEBODY_DECLARED_ITS_REACH`. Delete this and a space can be read
    at a reach nobody chose, or with nobody answerable for its pages."""
    company = declaration_of(state(space_value(SPACE, COMPANY)))
    assert company is not None
    assert (company.space_id, company.owner_id, company.level.value) == (SPACE, STEWARD, "company")
    web = declaration_of(state(space_value(SPACE, DEPARTMENT, "web")))
    assert web is not None and web.visibility.department == "web"
    assert space_key(SPACE).startswith(f"{SPACES_NAMESPACE}.")


@pytest.mark.parametrize(
    "value",
    [
        space_value(SPACE, DEPARTMENT, ""),
        space_value(SPACE, "everyone"),
        space_value("", COMPANY),
        "company",
        {},
    ],
)
def test_a_row_that_declares_no_readable_space_is_no_space(value: Any) -> None:
    """Delete this and a row edited by hand into nonsense can be read as a space at the widest
    reach, which is the default `lark_wiki.SpaceDeclaration` refuses."""
    assert declaration_of(state(value)) is None


def test_declaring_a_space_refuses_what_would_read_back_as_none() -> None:
    """Delete this and Connect Lark can save a space that is then silently never read."""
    from brain.ops.lark_wiki_live import declare_space

    with pytest.raises(ValueError, match="declares nothing"):
        asyncio.run(declare_space(None, SPACE, reach=DEPARTMENT, updated_by=STEWARD))  # type: ignore[arg-type]


def test_a_title_is_matched_on_the_question_s_longer_words_in_any_script() -> None:
    """`A_TITLE_IS_MATCHED_ON_THE_QUESTION_S_LONGER_WORDS`. Delete this and "what is the" walks
    every page title in the wiki, spending the tenant's minute on pages nobody asked about."""
    assert words_of("What is the renewal policy?") == ("what", "renewal", "policy")
    assert words_of("SLA 条款 of it") == ("条款",)
    assert len(words_of(" ".join(f"word{n}" for n in range(20)))) == MAX_WORDS


def recorded() -> _RecordedWiki:
    return _RecordedWiki(
        space_id=SPACE,
        pages=(
            _Page("wikcnOpen0001", "doccnOpen0001", "Renewal handbook", "renewal text", False),
            _Page("wikcnLock0001", "doccnLock0001", "Renewal salaries", "locked text", True),
        ),
    )


def search_over(wiki: _RecordedWiki, declared: tuple[Any, ...]) -> WikiPassages:
    async def spaces() -> tuple[Any, ...]:
        return declared

    return WikiPassages(
        HOST, spaces, keys=_AppKeys(), caller=wiki, resolver=_Resolver(), issuer=_Issuer()
    )


def department_space() -> Any:
    found = declaration_of(state(space_value(SPACE, DEPARTMENT, "web")))
    assert found is not None
    return found


def test_a_page_is_told_to_a_reader_its_reach_admits_and_a_locked_one_is_never_read() -> None:
    """`A_WIKI_PAGE_IS_TOLD_ONLY_TO_A_READER_ITS_REACH_ADMITS`, over the recorded wiki. Delete this
    and a page can be told outside its department, or a page restricted in Lark read at all."""
    wiki = recorded()
    search = WithWiki(_NoLibrary(), search_over(wiki, (department_space(),)))
    web = reader(("read:knowledge", Scope.department("web")))
    told = asyncio.run(search.passages("the renewal handbook", entitlement=web, now=LONG_AGO))
    assert [one.document for one in told.records] == ["renewal text"]
    assert not any("doccnLock0001" in url for url in wiki.asked)
    ops = reader(("read:knowledge", Scope.department("ops")))
    assert (
        asyncio.run(search.passages("the renewal handbook", entitlement=ops, now=LONG_AGO)).records
        == ()
    )


def test_a_reader_with_no_knowledge_read_or_no_declared_space_costs_no_call() -> None:
    """Delete this and every question from anybody walks the wiki, whatever they may read."""
    wiki = recorded()
    nobody = reader()
    asyncio.run(
        search_over(wiki, (department_space(),)).passages(
            "renewal handbook", entitlement=nobody, now=LONG_AGO
        )
    )
    web = reader(("read:knowledge", Scope.department("web")))
    asyncio.run(search_over(wiki, ()).passages("renewal handbook", entitlement=web, now=LONG_AGO))
    assert wiki.asked == []


def test_a_company_page_is_told_to_every_reader_of_the_knowledge_plane() -> None:
    """The positive case beside the department one. Delete this and a company page, the staff
    handbook, can be hidden from every reader whose grant is departmental."""
    wiki = recorded()
    company = declaration_of(state(space_value(SPACE, COMPANY)))
    assert company is not None
    ops = reader(("read:knowledge", Scope.department("ops")))
    told = asyncio.run(
        search_over(wiki, (company,)).passages("renewal handbook", entitlement=ops, now=LONG_AGO)
    )
    assert [one.document for one in told.records] == ["renewal text"]


def test_the_reach_evaluator_is_the_library_search_s_own() -> None:
    """Delete this and the Wiki can grow an evaluator of its own that disagrees with the library's
    about who may read a department's documents."""
    import inspect

    import brain.ops.lark_wiki_live as live

    source = inspect.getsource(told_to)
    assert "reach_for(" in source and "reach.admits(" in source
    from brain.knowledge.search import reach_for

    assert vars(live)["reach_for"] is reach_for


def test_the_model_lane_reads_the_wiki_only_when_it_is_switched_on(monkeypatch: Any) -> None:
    """Delete this and a Wiki switched on in Connect Lark is never searched by the answer lane,
    or one switched off is."""
    from types import SimpleNamespace

    import brain.api_routes as api_routes

    models = SimpleNamespace(calls=object())
    monkeypatch.setattr(api_routes, "ModelService", SimpleNamespace)
    state = SimpleNamespace(models=models, passage_search=_NoLibrary(), db_sessions=None)
    monkeypatch.setattr(api_routes, "wiki_passages_for", lambda sessions, vault: None)
    lane = api_routes.model_lane_of(state)
    assert lane is not None and isinstance(lane.search, _NoLibrary)
    monkeypatch.setattr(
        api_routes, "wiki_passages_for", lambda sessions, vault: search_over(recorded(), ())
    )
    lane = api_routes.model_lane_of(state)
    assert lane is not None and isinstance(lane.search, WithWiki)
