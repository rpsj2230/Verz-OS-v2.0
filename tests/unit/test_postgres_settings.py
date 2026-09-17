"""The database's memory settings per profile, read out of the compose files that run it.

Task ids: M0.3.6
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment import postgres_settings as ps
from brain.deployment.requirements import COMPOSE_FILES_FOR
from brain.ops.connections import database, demand_on
from brain.ops.wiring import PROFILES

REPO = Path(__file__).resolve().parents[2]


def _files(profile: str) -> dict[str, dict[str, Any]]:
    return {
        name: yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}
        for name in COMPOSE_FILES_FOR[profile]
    }


def _with_command(files: dict[str, dict[str, Any]], command: object) -> dict[str, Any]:
    edited = copy.deepcopy(files)
    for document in edited.values():
        body = (document.get("services") or {}).get("db")
        if isinstance(body, dict) and body:
            body["command"] = command
    return edited


@pytest.mark.parametrize("profile", PROFILES)
def test_every_profile_sets_each_memory_setting_to_its_sized_figure(profile: str) -> None:
    """The positive case, over the real compose files each profile composes: every one of the
    four settings is on the database's command line, equal to the profile's row, inside the
    container `brain.ops.connections` sizes.

    Delete this and `autovacuum_work_mem` can leave a profile's file again, which is how it was
    missing from one deployment while two others set it."""
    assert ps.settings_gaps(profile, _files(profile)) == ()


def test_a_setting_left_to_the_default_is_named() -> None:
    """The refusal half. A command without `autovacuum_work_mem` is exactly the staging install
    as measured on 2026-09-17, and it has to be a finding naming that setting and no other.

    Delete this and a check that reads nothing passes the test above."""
    files = _files("lite")
    command = "postgres -c shared_buffers=512MB -c work_mem=16MB -c maintenance_work_mem=256MB"
    found = ps.settings_gaps("lite", _with_command(files, command))

    assert len(found) == 1, found
    assert "autovacuum_work_mem" in found[0]
    assert "default" in found[0]


def test_a_setting_with_a_different_figure_is_named_in_the_list_spelling_too() -> None:
    """A compose `command:` is a string or a list, and the reader has to see both. A figure that
    drifted from the row is a different finding from a figure that is missing.

    Delete this and a list-form command reads as setting nothing, or a changed figure reads as
    agreeing."""
    files = _files("full")
    command = [
        "postgres",
        "-c",
        "shared_buffers=512MB",
        "-c",
        "work_mem=16MB",
        "-c",
        "maintenance_work_mem=256MB",
        "-c",
        "autovacuum_work_mem=64MB",
    ]
    found = ps.settings_gaps("full", _with_command(files, command))

    assert found == ("profile 'full' sets autovacuum_work_mem=64MB and is sized 128MB",)


def test_a_container_limit_that_differs_from_the_sizing_is_named() -> None:
    """The sum is only meaningful against the container that runs. Halving the limit in the
    compose file without touching `brain.ops.connections` has to be seen here.

    Delete this and the arithmetic checks a 2048 MiB container that no profile runs."""
    files = _files("standard")
    for document in files.values():
        body = (document.get("services") or {}).get("db")
        if isinstance(body, dict) and body:
            body["deploy"]["resources"]["limits"]["memory"] = "1024M"

    found = ps.settings_gaps("standard", files)
    assert len(found) == 1, found
    assert "1024M" in found[0]


def test_the_sized_figures_fit_the_container_with_room_for_every_declared_connection() -> None:
    """Asserted against `brain.ops.connections` rather than against this module's own row: the
    container limit and the connection demand both come from there, and the sum has to fit.

    Delete this and raising `work_mem` for one slow query becomes an out-of-memory kill the
    first time the declared clients all sort at once."""
    sizing = database("db")
    for profile in PROFILES:
        worst = ps.SETTINGS_FOR[profile].worst_case_mib(demand_on("db"))
        assert worst <= sizing.memory_mib, (profile, worst)


def test_a_sum_that_does_not_fit_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal half of the sum. Four autovacuum workers' worth of 512 MiB cannot fit a
    2048 MiB container, and the finding says why the autovacuum figure is set at all.

    Delete this and the sum check could be removed with every test above still green."""
    oversized = ps.PostgresSettings(
        shared_buffers_mib=512,
        work_mem_mib=16,
        maintenance_work_mem_mib=256,
        autovacuum_work_mem_mib=512,
    )
    monkeypatch.setattr(ps, "SETTINGS_FOR", {**ps.SETTINGS_FOR, "lite": oversized})
    files = _with_command(
        _files("lite"),
        "postgres -c shared_buffers=512MB -c work_mem=16MB "
        "-c maintenance_work_mem=256MB -c autovacuum_work_mem=512MB",
    )
    found = ps.settings_gaps("lite", files)

    assert len(found) == 1, found
    assert "MiB at once" in found[0]
    assert ps.AN_UNSET_AUTOVACUUM_WORK_MEM_IS_THREE_TIMES_MAINTENANCE in found[0]


def test_a_row_that_disagrees_with_the_connection_budget_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile row and its compose file can agree with each other and both leave
    `brain.ops.connections` behind, which is the module every other memory sum reads.

    Delete this and `shared_buffers` can be halved in both places while the budget keeps
    counting the old figure."""
    smaller = ps.PostgresSettings(
        shared_buffers_mib=256,
        work_mem_mib=16,
        maintenance_work_mem_mib=256,
        autovacuum_work_mem_mib=128,
    )
    monkeypatch.setattr(ps, "SETTINGS_FOR", {**ps.SETTINGS_FOR, "lite": smaller})
    files = _with_command(
        _files("lite"),
        "postgres -c shared_buffers=256MB -c work_mem=16MB "
        "-c maintenance_work_mem=256MB -c autovacuum_work_mem=128MB",
    )

    found = ps.settings_gaps("lite", files)
    assert len(found) == 1, found
    assert "brain.ops.connections budgets 512MB" in found[0]


def test_the_autovacuum_worker_count_is_postgres_default_and_nothing_raises_it() -> None:
    """The multiplier in the sum is only true while no compose file raises
    `autovacuum_max_workers`. Read across every compose file in the repository.

    Delete this and a raised worker count makes the sum an understatement by the difference."""
    assert ps.AUTOVACUUM_MAX_WORKERS == 3
    for path in REPO.glob("docker-compose*.yml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for body in (document.get("services") or {}).values():
            if isinstance(body, dict):
                assert "autovacuum_max_workers" not in ps.command_settings(body.get("command"))


def test_an_unknown_profile_is_refused() -> None:
    """A typo in a profile name must not return an empty, passing list."""
    with pytest.raises(KeyError):
        ps.settings_gaps("medium", {})
