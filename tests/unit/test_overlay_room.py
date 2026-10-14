"""A save of the optional services is checked against the room the server last measured.

`brain.ops.overlays.plan` decides on the server, from facts the deploy step gathers, which
switched-on services fit. That answer is read in a deploy's journal, which is a release after the
person typed the setting, so the planner also keeps the room it measured (`ROOM_KEY`) and the
Settings screen asks the same costing, `plan_in_room`, whether a value would fit before it is
saved. These tests hold that the two are one costing, that the room is kept whether or not
anything is switched on, that a save with no measurement is allowed, and that a refusal over HTTP
writes nothing.

Every figure is a fixture of a host that does not exist: an 8,192 MiB machine, never anybody's.

Task ids: M32.2.1.1, M32.1.1.1, M32.1.1.2
"""

from __future__ import annotations

import asyncio
import io
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.ops import overlays, setting_store
from brain.ops.overlays import (
    BY_NAME,
    NO_SERVICES,
    OVERLAYS,
    ROOM_KEY,
    Host,
    main,
    memory_problem,
    plan,
    plan_in_room,
    planned,
    read_host,
    room_in,
    room_observation,
)
from brain.ops.wiring import HOST_RESERVE_MIB
from tests.fixtures.console_http import Stub, console_client
from tests.fixtures.setting_rows import SettingRows
from tests.unit.test_overlays import FACTS
from tests.unit.test_settings_routes import InstallRows, put

PRESIDIO = BY_NAME["presidio"]
LANGFUSE = BY_NAME["langfuse"]
#: What the overlay the product always runs costs, taken first of everything.
FLOOR = sum(one.cost_mib for one in OVERLAYS if one.always)
BOTH = PRESIDIO.cost_mib + LANGFUSE.cost_mib


class _Row:
    def __init__(self, value: object) -> None:
        self.value = value


def _ask(monkeypatch: pytest.MonkeyPatch, value: str, row: object | None) -> str:
    """`memory_problem` over a namespace holding `row` as the room, or holding nothing."""

    async def held(session: object, namespace: str) -> dict[str, object]:
        del session
        assert namespace == "overlay"
        return {} if row is None else {ROOM_KEY: _Row(row)}

    monkeypatch.setattr(setting_store, "read_namespace", held)
    return asyncio.run(memory_problem(object(), value))  # type: ignore[arg-type]


def test_the_save_check_and_the_deploy_plan_are_one_costing_so_they_refuse_the_same_service() -> (
    None
):
    """`plan` is `plan_in_room` over a measured host, whatever the host, and the save sentence is
    the plan's own sentence for the service the deploy would leave out.

    Delete this and the screen can refuse a value the deploy would start, or accept one the deploy
    drops, because the two sums have drifted apart."""
    for room in (0, FLOOR, FLOOR + PRESIDIO.cost_mib, FLOOR + BOTH - 1, FLOOR + BOTH):
        host = Host(total_mib=room + HOST_RESERVE_MIB, reserved_mib=0, unlimited_used_mib=0)
        both = planned((PRESIDIO, LANGFUSE))
        assert plan(both, host) == plan_in_room(both, host.available_mib, host.runtimes)


def test_a_save_that_would_not_all_start_in_the_measured_room_is_refused_in_the_plan_s_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One mebibyte short of both is refused naming the service the deploy would drop, with its
    cost and what is left after the detector took its share and the always-on pools took theirs.

    Delete this and the owner switches on a service the next release silently does not start."""
    said = _ask(monkeypatch, "presidio,langfuse", {"available_mib": FLOOR + BOTH - 1})

    assert said.startswith(overlays.NOT_ALL_OF_THESE_FIT_ON_THIS_SERVER)
    assert (
        f"the trace ledger and its file store (langfuse) needs {LANGFUSE.cost_mib} MiB and this "
        f"server has {LANGFUSE.cost_mib - 1} MiB left for it" in said
    )
    assert said.endswith(overlays.WHAT_TO_DO_ABOUT_A_SERVICE_THAT_DOES_NOT_FIT)
    assert "presidio" not in said
    assert "connection pools" not in said
    assert "so it is not started" not in said, "a save is not a start, so the plan's tail goes"


def test_the_first_service_the_deploy_would_leave_out_is_the_one_named_and_never_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In a room too small for the always-on pools and everything else, the person is told about
    the first service they chose, in the order the room is given, and not about the pools they
    never asked for. And with the pools paid for and room for neither choice, it is the detector,
    which comes first, that is named, not the ledger behind it.

    Delete this and a save is refused with a sentence about something nobody chose, or about the
    second of two services when the first is what the owner would fix first."""
    nothing = _ask(monkeypatch, "presidio,langfuse", {"available_mib": 0})
    assert "(presidio) needs" in nothing
    assert "(langfuse)" not in nothing
    assert "connection pools" not in nothing

    tight = _ask(monkeypatch, "presidio,langfuse", {"available_mib": FLOOR + 100})
    assert "(presidio) needs" in tight
    assert "(langfuse)" not in tight


@pytest.mark.parametrize(
    ("value", "room"),
    [
        ("presidio,langfuse", FLOOR + BOTH),
        ("presidio", FLOOR + PRESIDIO.cost_mib),
        ("langfuse", FLOOR + LANGFUSE.cost_mib),
        (NO_SERVICES, 0),
    ],
)
def test_a_save_that_fits_the_measured_room_exactly_is_allowed(
    monkeypatch: pytest.MonkeyPatch, value: str, room: int
) -> None:
    """The positive sibling, at the boundary: exactly the cost is room enough, and naming nothing
    is never refused however little room there is. Delete this and the guard is satisfied by a
    function that refuses everything."""
    assert _ask(monkeypatch, value, {"available_mib": room}) == ""


@pytest.mark.parametrize(
    "row",
    [None, {}, {"available_mib": "a lot"}, {"available_mib": -1}, {"available_mib": True}, "nope"],
    ids=["no row", "no field", "text", "negative", "a boolean", "not an object"],
)
def test_with_no_usable_measurement_a_save_is_allowed_and_the_deploy_decides(
    monkeypatch: pytest.MonkeyPatch, row: object | None
) -> None:
    """The first switch-on of every install has no measurement yet, and a row somebody typed at a
    database prompt is no measurement. Delete this and a missing or garbled row blocks the very save
    that would have started the service."""
    assert _ask(monkeypatch, "presidio,langfuse", row) == ""


def test_a_measured_room_is_a_whole_non_negative_number_and_nothing_else() -> None:
    """`True` is an `int` to Python and must not read as a room of one. Delete this and a boolean
    written into the row is a one mebibyte server that refuses every save."""
    assert room_in({"available_mib": 4096, "total_mib": 8192}) == 4096
    assert room_in({"available_mib": 0}) == 0
    for wrong in ({"available_mib": True}, {"available_mib": 1.5}, {"available_mib": -2}, 7, None):
        assert room_in(wrong) is None


def test_a_service_that_needs_a_runtime_the_server_lacks_is_not_also_refused_for_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sandbox's refusal is `runtime_problem`'s. In a room big enough for it, this check says
    nothing, so a person is never told two reasons for one service. Delete this and a server
    without gVisor is refused by a memory sentence that is not the reason."""
    sandbox = BY_NAME["sandbox"]
    assert _ask(monkeypatch, "sandbox", {"available_mib": FLOOR + sandbox.cost_mib}) == ""


def test_the_room_the_planner_kept_is_the_room_it_planned_with() -> None:
    """The row's number is the host's `available_mib`, the figure the plan costs against. Delete
    this and the screen checks a save against a different sum than the deploy makes."""
    host = read_host(FACTS.splitlines(), project="u-overlays")
    assert room_observation(host) == {
        "available_mib": host.available_mib,
        "total_mib": host.total_mib,
    }


def _plan_with(monkeypatch: pytest.MonkeyPatch, kept: list[dict[str, Any]], *, fails: bool) -> None:
    def record(value: dict[str, object], **named: Any) -> None:
        if fails:
            msg = "no database"
            raise overlays.OverlayError(msg)
        kept.append({"value": value, **named})

    monkeypatch.setattr(overlays, "_record", record)
    monkeypatch.setattr(overlays, "_saved_from_database", lambda: {})
    monkeypatch.setattr(sys, "stdin", io.StringIO(FACTS))


def test_the_planner_keeps_the_room_when_nothing_at_all_is_switched_on(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The report the step writes after starting services is written only when one started, so on
    an install that has switched nothing on the room would never be kept, and the first save would
    have nothing to be checked against. Delete this and the check works on every install except
    the one about to switch its first service on."""
    kept: list[dict[str, Any]] = []
    _plan_with(monkeypatch, kept, fails=False)

    assert main(["plan", "--project", "u-overlays"]) == 0

    host = read_host(FACTS.splitlines(), project="u-overlays")
    assert [one["key"] for one in kept] == [ROOM_KEY]
    assert kept[0]["value"] == room_observation(host)
    assert kept[0]["description"] == overlays.ROOM_DESCRIPTION
    started = [line for line in capsys.readouterr().out.splitlines() if line.startswith("START ")]
    assert started == ["START class-pools"], "only the overlay the product always runs"


def test_a_room_that_cannot_be_kept_is_said_and_the_plan_still_stands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The deploy is the authority, so a measurement that cannot be written must not stop a plan
    that was made. Delete this and a database that is restarting stops the detector."""
    _plan_with(monkeypatch, [], fails=True)

    assert main(["plan", "--project", "u-overlays"]) == 0

    said = capsys.readouterr().out
    assert "SAY this server has 8192 MiB" in said
    assert "SAY the room measured on this server was not kept: " in said


# ------------------------------------------------------------------ over HTTP
@pytest.fixture
def served(
    installed: InstallRows, furnishing: SettingRows
) -> Iterator[tuple[TestClient, Stub, SettingRows]]:
    from tests.unit.test_settings_routes import GRANTS

    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([installed.answer, furnishing.answer])
        yield client, stub, furnishing


@pytest.fixture
def installed() -> InstallRows:
    return InstallRows()


@pytest.fixture
def furnishing() -> SettingRows:
    from brain.ops.starter_store import FURNISHED_KEY

    rows = SettingRows()
    rows.hold(FURNISHED_KEY, True, value_type="boolean", by="first_run")
    return rows


@pytest.fixture(autouse=True)
def nothing_saved() -> Iterator[None]:
    from brain.install import hold_saved

    before = hold_saved({})
    yield
    hold_saved(before)


def test_saving_more_services_than_the_server_has_room_for_is_refused_and_nothing_is_written(
    served: tuple[TestClient, Stub, SettingRows], installed: InstallRows
) -> None:
    """End to end through the real route: 422 with the sentence, no row written, nothing committed.
    Delete this and the guard exists in `overlays` and the screen never calls it."""
    client, stub, rooms = served
    rooms.hold(ROOM_KEY, {"available_mib": FLOOR + BOTH - 1}, value_type="json")

    answer = put(client, "u_admin", "INSTALL_SERVICES", "presidio,langfuse")

    assert answer.status_code == 422, answer.text
    assert answer.json()["message"].startswith(overlays.NOT_ALL_OF_THESE_FIT_ON_THIS_SERVER)
    assert installed.writes == []
    assert stub.commits == 0


@pytest.mark.parametrize("room", [FLOOR + BOTH, None], ids=["room enough", "no measurement"])
def test_the_same_save_goes_through_where_the_room_is_enough_or_has_not_been_measured(
    served: tuple[TestClient, Stub, SettingRows], installed: InstallRows, room: int | None
) -> None:
    """The positive sibling of the refusal above: the same value is written, once, by the person
    who saved it. Delete this and the route refuses every save of the setting."""
    client, stub, rooms = served
    if room is not None:
        rooms.hold(ROOM_KEY, {"available_mib": room}, value_type="json")

    answer = put(client, "u_admin", "INSTALL_SERVICES", "presidio,langfuse")

    assert answer.status_code == 200, answer.text
    assert [(one["key"], one["updated_by"]) for one in installed.writes] == [
        ("install.services", "u_admin")
    ]
    assert stub.commits == 1
