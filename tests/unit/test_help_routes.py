"""The help pages over HTTP: a runbook per screen, per alert, the playbook, and what it can see.

Driven through the real application as `tests/unit/test_install_routes.py` drives the install
screens, with its people, its token machinery and its wiring. What is under test is who may read
a page and what it is, so the same six people sign in the same way and only what they hold differs.

**Every refusal here has a sibling that reads.** A guard tested only by its refusals is satisfied
by routes that refuse everybody, so each page is asked by a reader who may open its screen and
answered, and by one who may not and refused with the one refusal, the same one a screen that does
not exist gets.

Task ids: M34.4.1, M34.3.2.1, M34.3.1.1, M34.3.1.2, M34.3.1.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.console.reads import Plane, plane_capability
from brain.console.screens import SCREENS, screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.help_routes import RUNBOOKS, runbook_text, title_of
from brain.ops.controls import CONTROLS, Missed
from brain.ops.reliability import MATRIX
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, verifier
from tests.unit.test_install_routes import SECOND_FACTOR, _app, get

WHOLE = Scope.unrestricted()
THE_CONSOLE_PLANE = Grant(capability=plane_capability(Plane.CONTENT), scope=WHOLE)


def _reads(*keys: str) -> tuple[Grant, ...]:
    return tuple(Grant(capability=screen(one).read.requires, scope=WHOLE) for one in keys)


GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (THE_CONSOLE_PLANE,),
    "u_admin": (THE_CONSOLE_PLANE, *_reads("overview", "queue", "incidents")),
    "u_narrow": (
        THE_CONSOLE_PLANE,
        Grant(
            capability=Capability(value="read:knowledge"),
            scope=Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),)),
        ),
    ),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real application with the department list fixed: the query is the acceptance check's."""
    from brain import help_routes

    async def two(request: object) -> tuple[str, ...]:
        return ("finance", "sales")

    monkeypatch.setattr(help_routes, "live_slugs", two)
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    app = _app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer="https://id.verz.example/realms/brain",
                audience="brain-api",
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        yield c


def _get(c: TestClient, who: str, path: str) -> Any:
    return get(c, who, f"{API_PREFIX}{path}")


def test_every_screen_has_a_runbook_this_image_ships_and_a_page_for_it() -> None:
    """The route serves the files the sweep holds to the registry. Delete this and a screen can
    gain or lose a runbook with the help route answering for fewer of them than the sweep says."""
    assert all(runbook_text(one.key) is not None for one in SCREENS)
    assert RUNBOOKS.is_dir()
    assert all(title_of(runbook_text(one.key) or "") == one.title for one in SCREENS)


def test_a_reader_of_a_screen_is_given_its_runbook_and_the_index_names_only_theirs(
    client: TestClient,
) -> None:
    """The overview reader reads the overview runbook and the index lists it and not the screens
    they cannot open. Delete this and a runbook is either not served or served for a screen the
    reader may not open."""
    page = _get(client, "u_admin", "/help/runbooks/overview")
    assert page.status_code == 200
    assert page.json()["markdown"].startswith(f"# {screen('overview').title}")
    index = _get(client, "u_admin", "/help/runbooks").json()["runbooks"]
    keys = {one["key"] for one in index}
    assert {"overview", "queue", "incidents"} <= keys
    assert "retention" not in keys
    assert _get(client, "u_none", "/help/runbooks").json() == {"runbooks": []}


def test_a_screen_that_is_not_theirs_or_not_there_is_one_refusal(client: TestClient) -> None:
    """A runbook for a screen the reader may not open, one for a screen that does not exist and
    one whose name is not a name are all the same 404. Delete this and the help pages say which
    screens an install has and which a person is kept from."""
    refusals = [
        _get(client, "u_none", "/help/runbooks/overview"),
        _get(client, "u_admin", "/help/runbooks/retention"),
        _get(client, "u_admin", "/help/runbooks/no_such_screen"),
    ]
    assert {one.status_code for one in refusals} == {404}
    assert len({one.json()["message"] for one in refusals}) == 1


def test_an_alert_runbook_is_every_reason_a_control_can_be_missed(client: TestClient) -> None:
    """One control's runbook carries a step list for each of the four reasons, from the same
    function the handover pack uses. Delete this and an alert reaches somebody with no next step
    for one of the ways it can be raised."""
    named = CONTROLS[0].name
    page = _get(client, "u_admin", f"/help/alerts/{named}")
    assert page.status_code == 200
    reasons = [one["reason"] for one in page.json()["steps"]]
    assert reasons == [one.value for one in Missed]
    assert all(one["first_check"] and one["then_do"] for one in page.json()["steps"])
    assert [one["who"] for one in page.json()["escalation"]] == ["installation owner", "supplier"]
    listed = _get(client, "u_admin", "/help/alerts").json()["alerts"]
    assert [one["control"] for one in listed] == [one.name for one in CONTROLS]
    assert _get(client, "u_none", f"/help/alerts/{named}").status_code == 404
    assert _get(client, "u_admin", "/help/alerts/no_such_control").status_code == 404


def test_the_playbook_is_every_failure_mode_and_only_for_a_reader_of_incidents(
    client: TestClient,
) -> None:
    """Each declared failure mode is rendered and a person without the Incidents screen is
    refused. Delete this and the playbook stays a Python table nobody reads."""
    page = _get(client, "u_admin", "/help/playbook")
    assert page.status_code == 200
    assert [one["component"] for one in page.json()["failures"]] == [
        one.component for one in MATRIX
    ]
    assert _get(client, "u_none", "/help/playbook").status_code == 404


def test_what_it_sees_names_the_readers_own_departments_and_the_install_s_posture(
    client: TestClient,
) -> None:
    """A reader of finance is told finance and not sales, everybody is told the install's
    privacy posture, and a reader of nothing is told no sentence about reach. Delete this and the
    page lists departments beyond the reader's reach, or shows a stranger an empty summary."""
    narrow = _get(client, "u_narrow", "/help/what-it-sees").json()
    said = " ".join(one["text"] for one in narrow["can_ask_about"])
    assert "finance" in said and "sales" not in said
    assert {one["key"] for one in narrow["privacy"]} >= {"posture.entitled"}
    none = _get(client, "u_none", "/help/what-it-sees").json()
    assert none["can_ask_about"] == []
    assert none["privacy"] == narrow["privacy"]
    assert SECOND_FACTOR


def test_every_signed_in_person_is_served_the_asking_guide_with_the_sentence_for_nothing_indexed(
    client: TestClient,
) -> None:
    """The guide is addressed to everybody who asks, so a person who may open no screen is served
    it, and with questions built from data off, or nothing indexed, the table says so. It carries
    none of the demo company's departments and none of the shipped page's own working.

    Delete this and the guide is served only to administrators, or to staff with the demo company's
    tables in it."""
    from brain.ops.guide_docs import NO_EXAMPLES_YET, YOUR_DEPARTMENT

    client.app.state.starter_questions_from_data_on = False  # type: ignore[attr-defined]
    for who in ("u_none", "u_admin", "u_narrow"):
        page = _get(client, who, "/help/asking-well")
        assert page.status_code == 200
        body = page.json()
        assert body["title"] == "How to ask well"
        assert body["markdown"].startswith("# How to ask well")
        assert YOUR_DEPARTMENT in body["markdown"] and NO_EXAMPLES_YET in body["markdown"]
        assert "checked: examples from" not in body["markdown"]
        assert "## Task ids" not in body["markdown"]


def test_a_guide_this_install_cannot_cut_is_not_served(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A shipped page that lost the headings it is cut at, and an image carrying no page, are both
    refused as a server fault rather than served as the demo company's page or as nothing. Delete
    this and an edit to the guide serves staff something the check never looked at."""
    from brain import help_routes

    client.app.state.starter_questions_from_data_on = False  # type: ignore[attr-defined]
    broken = tmp_path / "asking-well.md"
    broken.write_text("# How to ask well\n\nNo examples here.\n", encoding="utf-8")
    for path in (broken, tmp_path / "missing.md"):
        monkeypatch.setattr(help_routes, "ASKING_GUIDE", path)
        refused = _get(client, "u_none", "/help/asking-well")
        # Failed is the server's fault and says so in the log only, with the generic body.
        assert refused.status_code == 500
        assert refused.json()["message"] == "Something went wrong."
        assert "markdown" not in refused.json()
