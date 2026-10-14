"""The model server over HTTP: what the page says, and a save of its settings refused in words.

Driven through the real application with `ops.setting` and the peak ring held in memory, the way
`tests/unit/test_settings_routes.py` drives the Settings screen. Three things are held here.

**The page tells the truth about what it knows.** With nothing measured it shows the product's own
reckoning and says so; with measurements it shows the largest per part and the limit they suggest,
which is a number and never applied.

**A save is judged by the one costing.** The same setting is accepted in a room that holds the
result and refused, in the plan's own sentence, in one that does not, and a refusal writes nothing.

**A person without the authority is refused before anything is read.**

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.install import hold_saved
from brain.ops import overlays
from brain.ops.model_server import config_from, effective_limit_mib
from brain.ops.overlays import ROOM_KEY
from brain.settings_routes import INSTALL_SETTING_AUTHORITY, SETTINGS_PATH
from tests.fixtures.console_http import console_client, get, headers
from tests.fixtures.setting_rows import SettingRows
from tests.unit.test_settings_routes import InstallRows

PAGE = f"{API_PREFIX}/install/model-server"
SCREEN = f"{API_PREFIX}{SETTINGS_PATH}"

GRANTS = {
    "u_admin": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.unrestricted()),),
    "u_narrow": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}

#: Far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

#: What the overlay the product always runs costs, which is taken first of everything.
ALWAYS_ON = sum(one.cost_mib for one in overlays.OVERLAYS if one.always)


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class Ring:
    """`ops.model_server_peak` held in memory: answers the one select that reads the whole ring."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def hold(self, part: str, batch_no: int, anon: int, cache: int) -> None:
        self.rows.append(
            {
                "part": part,
                "slot": batch_no % 50,
                "batch_no": batch_no,
                "at": LONG_AGO,
                "model": "m",
                "items": 1,
                "request_bytes": 1,
                "duration_ms": 1,
                "anon_peak_mib": anon,
                "cache_peak_mib": cache,
                "cgroup_limit_mib": None,
            }
        )

    def answer(self, statement: Any) -> _Mappings | None:
        if isinstance(statement, Select):
            names = [one["name"] for one in statement.column_descriptions]
            if "batch_no" in names and "anon_peak_mib" in names:
                return _Mappings(list(self.rows))
        return None


@pytest.fixture(autouse=True)
def nothing_saved() -> Iterator[None]:
    before = hold_saved({})
    yield
    hold_saved(before)


@pytest.fixture
def held() -> tuple[InstallRows, SettingRows, Ring]:
    return InstallRows(), SettingRows(), Ring()


@pytest.fixture
def served(held: tuple[InstallRows, SettingRows, Ring]) -> Iterator[TestClient]:
    installed, settings, ring = held
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([installed.answer, settings.answer, ring.answer])
        yield client


def put(client: TestClient, name: str, value: str) -> Any:
    return client.put(f"{SCREEN}/{name}", json={"value": value}, headers=headers("u_admin"))


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
def test_a_caller_without_the_authority_over_everything_is_refused_before_anything_is_read(
    pid: str,
) -> None:
    """The authority is asked first, over everything, with a database and without. Delete this and
    a department-scoped administrator reads the whole install's memory and what its server holds."""
    for database in (True, False):
        with console_client(GRANTS, database=database) as (client, stub):
            assert get(client, pid, PAGE).status_code == 404
            assert stub.statements == []


def test_a_fresh_install_sees_the_default_choice_costed_and_nothing_measured(
    served: TestClient,
) -> None:
    """The positive case, and the honest one: the default is the embedding part, the limit is
    worked out and is the budget's row, the switch is off, nothing is measured and so nothing is
    suggested, and the note says every figure is a judgement.

    Delete this and the page invents a measurement, or shows nothing for an install that has not
    chosen."""
    page = get(served, "u_admin", PAGE).json()

    assert page["parts"] == ["embedding"] and page["switched_on"] is False
    assert page["limit_mib"] == page["worked_out_limit_mib"] == effective_limit_mib(config_from())
    assert page["worked_out"] is True and page["problem"] == ""
    assert page["measured"] == [] and page["suggested_limit_mib"] is None
    assert "judgements" in page["note"]


def test_what_was_chosen_and_what_was_measured_are_shown_and_the_suggestion_is_the_largest(
    served: TestClient, held: tuple[InstallRows, SettingRows, Ring]
) -> None:
    """Both halves in one page: the choice read through the one installation reader, and the ring
    summarised by its largest batch per part. A hand-set limit is shown as hand-set and the
    worked-out one beside it. The suggestion is the largest part's, not a sum.

    Delete this and the screen shows what the install did not choose, or an average a large batch
    kills."""
    _, _, ring = held
    ring.hold("embedding", 1, 300, 600)
    ring.hold("embedding", 2, 410, 640)
    ring.hold("layout", 1, 1100, 0)
    needed = effective_limit_mib(config_from(parts="layout"))
    hold_saved(
        {"INSTALL_MODEL_PARTS": "layout,embedding", "INSTALL_MODEL_MEMORY_MIB": str(needed + 256)}
    )

    page = get(served, "u_admin", PAGE).json()

    assert page["parts"] == ["layout", "embedding"]
    assert page["limit_mib"] == needed + 256 and page["worked_out"] is False
    assert page["worked_out_limit_mib"] == needed
    by_part = {one["part"]: one for one in page["measured"]}
    assert by_part["embedding"]["batches"] == 2
    assert by_part["embedding"]["largest_anonymous_mib"] == 410
    assert by_part["embedding"]["largest_total_mib"] == 1050
    assert page["suggested_limit_mib"] == max(
        one["suggested_limit_mib"] for one in page["measured"]
    )


def test_settings_that_are_not_a_configuration_give_a_page_that_says_so_and_not_an_error(
    served: TestClient,
) -> None:
    """The person is here to fix it, so the page opens, names the problem in words, and shows the
    product's defaults rather than a half-read choice.

    Delete this and a mistyped part makes the one page that explains it a 500."""
    hold_saved({"INSTALL_MODEL_PARTS": "translation"})

    page = get(served, "u_admin", PAGE).json()

    assert "translation" in page["problem"]
    assert page["parts"] == ["embedding"]


# ------------------------------------------------------------------ a save is judged
def test_a_part_that_does_not_fit_the_room_the_server_last_measured_is_refused_and_writes_nothing(
    served: TestClient, held: tuple[InstallRows, SettingRows, Ring]
) -> None:
    """The same costing the deploy uses, asked with the setting as it would then stand: a room that
    holds the default does not hold the layout part, the refusal is the plan's sentence naming the
    model server, and nothing is written. The default is accepted in the same room.

    Delete this and a person chooses a part the next release then leaves out, which is a setting
    that looks saved and a server that does not run."""
    installed, settings, _ = held
    installed.rows["install.services"] = "modelserver"
    settings.hold(
        ROOM_KEY,
        {"available_mib": ALWAYS_ON + effective_limit_mib(config_from()), "total_mib": 8192},
        value_type="json",
    )

    ok = put(served, "INSTALL_MODEL_PARTS", "embedding")
    assert ok.status_code == 200, ok.text
    installed.writes.clear()

    refused = put(served, "INSTALL_MODEL_PARTS", "layout")

    assert refused.status_code == 422
    assert "(modelserver)" in refused.json()["message"]
    assert "cannot hold all of these services" in refused.json()["message"]
    assert installed.writes == []


def test_a_limit_under_what_the_chosen_parts_need_is_refused_by_the_configuration_itself(
    served: TestClient, held: tuple[InstallRows, SettingRows, Ring]
) -> None:
    """Before any room is asked: a limit too small for the parts chosen is not a configuration, so
    the refusal does not depend on what the server last measured, and says what would do.

    Delete this and a limit that cannot hold the part is saved on an install nobody has measured."""
    installed, _, _ = held
    hold_saved({"INSTALL_MODEL_PARTS": "layout"})

    refused = put(served, "INSTALL_MODEL_MEMORY_MIB", "100")

    assert refused.status_code == 422 and "layout" in refused.json()["message"]
    assert installed.writes == []


def test_with_no_measurement_a_model_setting_is_saved_and_the_deploy_decides(
    served: TestClient, held: tuple[InstallRows, SettingRows, Ring]
) -> None:
    """Refusing on a guess would block the first choice of every install. The positive case beside
    the refusals, so a check that refuses everything is caught.

    Delete this and the first install to choose a part cannot save the choice."""
    installed, _, _ = held
    installed.rows["install.services"] = "modelserver"

    saved = put(served, "INSTALL_MODEL_PARTS", "embedding,layout")

    assert saved.status_code == 200, saved.text
    assert [one["key"] for one in installed.writes] == ["install.model_parts"]
