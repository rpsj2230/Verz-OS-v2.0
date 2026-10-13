"""The Sign in with Lark check: registered, stepping aside, passing, and failing where it proves.

The database half runs the check as the worker runs it. It writes nothing, so what is asserted
about the database is that nothing moved, and the product is then broken in two places the check
reads: the person the bridge names, and the router the application mounts.

Task ids: M1.1.8
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_lark_sign_in"
NAME = "the_lark_bridge_names_the_person_lark_names_and_nobody_else"

LARK = {
    "INSTALL_BROKERED_DIRECTORY": "lark",
    "INSTALL_BROKERED_CLIENT_ID": "cli_acceptance0001",
    "INSTALL_STAFF_SOURCE": "lark",
    "INSTALL_STAFF_SOURCE_LOCATION": "larksuite.com",
    "INSTALL_OIDC_REDIRECT_URIS": "https://brain.example.invalid/callback",
}


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def brokering_lark(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in LARK.items():
        monkeypatch.setenv(name, value)


def test_the_check_is_registered_with_the_leaf_it_proves_and_listed_in_its_page_order() -> None:
    """Delete this and the check can close a leaf it does not exercise, name an id no task has,
    or drop out of the module with the page listing one fewer row."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M1.1.8",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_an_install_that_does_not_broker_lark_the_check_says_there_is_nothing_to_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every install is in this state until its owner sets Lark up. Delete this and the check can
    pass on a bridge it never reached, which closes the leaf on nothing."""
    from brain.ops.acceptance_checks_lark_sign_in import (
        THIS_INSTALL_DOES_NOT_BROKER_SIGN_IN_TO_LARK,
    )

    for name in LARK:
        monkeypatch.delenv(name, raising=False)
    with at_head("brain_acceptance_lark_off") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome == {NAME: (NOT_RUN, THIS_INSTALL_DOES_NOT_BROKER_SIGN_IN_TO_LARK)}


@pytest.mark.needs_db
def test_on_an_install_that_brokers_lark_the_bridge_is_asked_and_nothing_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes and the tables
    hold what they held before. Delete this and the bridge can break with nothing on the owner's
    install saying so."""
    brokering_lark(monkeypatch)
    with at_head("brain_acceptance_lark_on") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, (mine()[NAME],))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("another_person", "the bridge did not name the person Lark named"),
        (
            "unmounted",
            "the Lark sign-in bridge is not one of the routers the application mounts",
        ),
    ],
)
def test_the_check_fails_where_the_bridge_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Two breaks: a bridge that names somebody other than the person Lark named, and a bridge the
    application does not mount. Each fails with its own sentence. Delete this and the check can
    pass with either gone."""
    import brain.lark_sign_in_routes as routes
    import brain.routers as routers
    from brain.identity.lark_sign_in import Claims

    brokering_lark(monkeypatch)
    if broken == "another_person":
        monkeypatch.setattr(
            routes,
            "claims_from",
            lambda answer: Claims(sub="on_somebody_else", email="else@example.invalid", name="x"),
        )
    else:
        monkeypatch.setattr(routers, "ROUTERS", ())
    with at_head(f"brain_acceptance_lark_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
