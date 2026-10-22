"""The member self-service install checks, each passing on PostgreSQL at head and each failing.

The database half runs the module as the worker does, with the install's issuer set: every check
passes and leaves nothing behind. Then each is shown failing with the product broken the way it
would plausibly break: a menu that lists the console to a member, a governance route that answers
a member, a workspace line written by hand, an agent's runs counted for the wrong person.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M40.1.1.1, M40.1.1.5, M40.1.2.1, M40.1.2.2, M40.1.2.4, M40.2.2.1
Task ids: M40.3.1.1, M40.3.1.5, M40.5.1.2, M40.6.1.1
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check

MODULE = "brain.ops.acceptance_checks_member_self"
SIGN_IN = "a_person_known_in_chat_signs_in_on_the_web_as_that_one_person"
MENU = "a_member_is_given_no_governance_menu_and_no_governance_route"
SAYS = "the_workspace_line_follows_grants_and_connecting_widens_nothing"
AGENTS = "each_agent_shows_where_it_runs_and_how_often_the_person_used_it"
DOCUMENTS = "a_member_s_documents_show_their_review_and_no_colleague_s"
APPROVALS = "an_approval_says_what_will_happen_before_it_is_decided"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_flow_and_names_every_leaf() -> None:
    """Six checks, each closing the leaves its flow exercises. Delete this and a check can lose a
    leaf with the page showing the same rows, so the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (SIGN_IN, ("M40.1.1.1", "M40.1.1.5")),
        (MENU, ("M40.1.2.1", "M40.1.2.2")),
        (SAYS, ("M40.1.2.4", "M40.5.1.2")),
        (AGENTS, ("M40.2.2.1",)),
        (DOCUMENTS, ("M40.3.1.1", "M40.3.1.5")),
        (APPROVALS, ("M40.6.1.1",)),
    ]


def test_the_member_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [SIGN_IN, MENU, SAYS, AGENTS, DOCUMENTS, APPROVALS]


def test_the_module_places_itself_inside_its_range() -> None:
    """The order key is one of this module's own. Delete this and two modules can share a key,
    which the Install page then breaks by name and nobody chose."""
    from brain.ops import acceptance_checks_member_self as module

    assert 1900 <= module.CHECK_ORDER <= 1999


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_member_self") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run(url: str, *names: str) -> dict[str, tuple[str, str]]:
    return run_check(url, [one for one in registered((MODULE,)) if not names or one.name in names])


def failed(url: str, name: str) -> str:
    [(outcome, reason)] = run(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_member_check_passes_on_an_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """**The module as the worker runs it.** Every check passes and nothing a check wrote is
    left. Delete this and a check that can never pass on a real schema, or one that commits a
    person, reaches the owner's server first."""
    before = counts(install)
    outcomes = run(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 6
    assert counts(install) == before


def _break(monkeypatch: pytest.MonkeyPatch, target: Any, name: str, value: Any) -> None:
    monkeypatch.setattr(target, name, value)


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_web_sign_in_naming_somebody_else_fails_the_sign_in_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`GET /me` answering as another person than the token's. Delete this and M40.1.1.1 closes on
    a check a sign-in that names the wrong person passes."""
    from brain import api_routes

    real = api_routes.me

    async def somebody_else(asked: Any) -> Any:
        return (await real(asked)).model_copy(update={"principal_id": "somebody_else"})

    _break(monkeypatch, api_routes, "me", somebody_else)
    assert "one person" in _failed(install, SIGN_IN)


@pytest.mark.needs_db
def test_a_menu_given_to_a_member_or_a_route_open_to_one_fails_the_menu_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Stop control drawn for a member, then the feature switch answering anybody. Delete this
    and M40.1.2.1 and M40.1.2.2 close on a menu that governs everything and an unguarded route."""
    from brain import feature_routes, navigation_routes

    with monkeypatch.context() as patched:
        patched.setattr(navigation_routes, "stop_offered", lambda *args: "everything")
        assert "governance menu" in _failed(install, MENU)
    monkeypatch.setattr(feature_routes, "may_switch", lambda reach, now: True)
    assert "not refused a governance route" in _failed(install, MENU)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("module_name", "attribute", "sentence"),
    [
        ("brain.navigation_routes", "console_navigation", "DB_MENU_READ"),
        ("brain.jobs_routes", "pause_job", "DB_MENU_REFUSALS"),
        ("brain.feature_routes", "switch_feature", "DB_MENU_SWITCH"),
    ],
)
def test_a_step_the_database_refuses_in_the_menu_check_is_named_by_the_step_and_quotes_nothing(
    install: str,
    issuer: None,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    attribute: str,
    sentence: str,
) -> None:
    """The install stopped this check on an OperationalError and the page could only say the type.
    A refused step must fail with the sentence naming it, and the administrator's switch must be
    told apart from the member's refused one. Delete this and a database error on an install is
    again a type name, and the next run cannot say which statement it was."""
    import importlib

    from sqlalchemy.exc import OperationalError

    from brain.ops import acceptance_checks_member_self as module

    target = importlib.import_module(module_name)
    real = getattr(target, attribute)

    async def refuses(*args: Any, **kwargs: Any) -> Any:
        asked = args[-1]
        # The member's press on the switch is one of the refusals; only the administrator's is
        # the step this case is about.
        if attribute == "switch_feature" and not asked.caller.principal.id.endswith(".admin"):
            return await real(*args, **kwargs)
        raise OperationalError("statement", {}, Exception("a value that must not be quoted"))

    monkeypatch.setattr(target, attribute, refuses)
    reason = _failed(install, MENU)
    assert reason == getattr(module, sentence)
    assert "must not be quoted" not in reason


@pytest.mark.needs_db
def test_a_line_written_by_hand_fails_the_workspace_line_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disclosure line the same for everybody. Delete this and M40.1.2.4 closes on a line that
    was never drawn from anybody's grants."""
    from brain import mine_routes

    monkeypatch.setattr(mine_routes, "disclosure_line", lambda reach, now: "You may ask anything.")
    assert "same line" in _failed(install, SAYS)


@pytest.mark.needs_db
def test_runs_counted_for_nobody_fail_the_agents_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every agent listed as never used. Delete this and M40.2.2.1 closes on a list that cannot
    say how often anybody ran what."""
    from dataclasses import replace

    from brain import member_activity, mine_routes

    real = member_activity.my_agents

    def never_used(*args: Any, **kwargs: Any) -> Any:
        return tuple(replace(one, uses=0) for one in real(*args, **kwargs))

    monkeypatch.setattr(mine_routes, "my_agents", never_used)
    assert "how often" in _failed(install, AGENTS)


@pytest.mark.needs_db
def test_a_document_listed_without_its_review_fails_the_documents_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review date dropped from every row. Delete this and M40.3.1.1 closes on a list that
    cannot say when anything is next to be looked at."""
    from brain import knowledge_lifecycle_routes as routes

    real = routes.document_view

    def undated(*args: Any, **kwargs: Any) -> Any:
        return real(*args, **kwargs).model_copy(update={"review_by": None})

    monkeypatch.setattr(routes, "document_view", undated)
    assert "review date" in _failed(install, DOCUMENTS)


@pytest.mark.needs_db
def test_a_list_that_shows_everybody_every_document_fails_the_documents_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Authority to act on a document given to every reader. Delete this and M40.3.1.5 closes on a
    list that shows a colleague's own documents."""
    from brain.knowledge import lifecycle

    monkeypatch.setattr(lifecycle.Authority, "may_act", lambda self, item: True)
    assert "colleague's document" in _failed(install, DOCUMENTS)


@pytest.mark.needs_db
def test_a_card_that_says_nothing_fails_the_approvals_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request's words left off every card. Delete this and M40.6.1.1 closes on an approval
    that asks somebody to decide what they are not told."""
    from brain import approval_routes

    real = approval_routes.card_view

    def silent(shown: Any) -> Any:
        return real(shown).model_copy(update={"request": ""})

    monkeypatch.setattr(approval_routes, "card_view", silent)
    assert "did not say what it was" in _failed(install, APPROVALS)
