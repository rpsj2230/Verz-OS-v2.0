"""The streaming replica overlay, held to its primary and to the primary's disk (M36.1.2.1).

The positive cases read `docker-compose.replica.yml` against both files that describe the
primary. Every refusal is the real overlay with one thing changed.

Task ids: M36.1.2.1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops.streaming_replica import (
    A_SLOT_WITHOUT_A_CEILING_FILLS_THE_PRIMARYS_DISK,
    A_STANDBY_REPLAYS_THE_PRIMARY_AND_NEEDS_ITS_BINARIES,
    OVERLAY,
    REPLICA_SERVICE,
    REPLICA_URL_SETTING,
    SETUP_SERVICE,
    SLOT,
    THE_SETUP_WRITES_ONE_RULE_TO_THE_PRIMARYS_VOLUME_AND_NOTHING_ELSE,
    WAL_KEPT_FOR_A_STOPPED_REPLICA,
    replica_overlay_gaps,
    setup_write_gaps,
)
from brain.settings import Settings

REPO = Path(__file__).resolve().parents[2]


def load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}
    return loaded


def overlay() -> dict[str, Any]:
    return load(OVERLAY)


def services(document: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = document["services"]
    return found


# ===================================================================== the real overlay
@pytest.mark.parametrize("base", ["docker-compose.yml", "docker-compose.lite.yml"])
def test_the_overlay_gives_a_replica_postgres_accepts_and_the_primary_survives(base: str) -> None:
    """The positive case against both files that describe `db`. Delete this and every refusal
    below can pass against a check that refuses the real overlay as well."""
    assert replica_overlay_gaps(load(base), overlay()) == ()


def test_the_setting_the_overlay_names_is_the_one_the_application_reads() -> None:
    """The overlay hands the application `BRAIN_READ_REPLICA_URL`, and `brain.settings` is the
    one place configuration is read. Asserted against the settings class rather than against the
    constant, so a renamed field fails here. Delete this and the overlay can set a variable the
    application never reads, and every console page goes on being read from the primary."""
    fields = Settings.model_fields
    prefix = str(Settings.model_config.get("env_prefix", ""))

    assert REPLICA_URL_SETTING.removeprefix(prefix).lower() in fields
    assert REPLICA_URL_SETTING in services(overlay())["app"]["environment"]


def test_the_wal_ceiling_in_the_file_is_the_one_the_module_states() -> None:
    """Delete this and the figure the documentation quotes and the figure the primary is given can
    differ, and the one an operator lowers for a small disk is the wrong one."""
    command = "\n".join(services(overlay())[SETUP_SERVICE]["command"])

    assert f"max_slot_wal_keep_size = '{WAL_KEPT_FOR_A_STOPPED_REPLICA}'" in command


def test_nothing_in_the_overlay_is_published() -> None:
    """The replica holds a copy of every row. Delete this and a port on it is a second, less
    watched way to the whole database."""
    for name, body in services(overlay()).items():
        assert "ports" not in body, name


# ============================================================================ the refusals
def test_a_slot_with_no_ceiling_is_refused() -> None:
    """The one that stops the primary. Delete this and the ceiling line can be removed, after
    which a replica that stops fills the primary's disk."""
    document = overlay()
    setup = services(document)[SETUP_SERVICE]
    setup["command"] = [
        "\n".join(
            line
            for line in setup["command"][0].splitlines()
            if "max_slot_wal_keep_size" not in line
        )
    ]

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any(A_SLOT_WITHOUT_A_CEILING_FILLS_THE_PRIMARYS_DISK in one for one in found), found


@pytest.mark.parametrize("ceiling", ["-1", "200GB"])
def test_an_unlimited_or_different_ceiling_is_refused(ceiling: str) -> None:
    """`-1` is PostgreSQL's spelling of no ceiling. Delete this and the line can stay while
    saying nothing."""
    document = overlay()
    setup = services(document)[SETUP_SERVICE]
    setup["command"] = [
        setup["command"][0].replace(f"'{WAL_KEPT_FOR_A_STOPPED_REPLICA}'", f"'{ceiling}'")
    ]

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any(A_SLOT_WITHOUT_A_CEILING_FILLS_THE_PRIMARYS_DISK in one for one in found), found


def test_a_replica_on_another_image_is_refused() -> None:
    """Delete this and the replica can be moved to a newer major by one edit, which is a standby
    that refuses to replay."""
    document = overlay()
    services(document)[REPLICA_SERVICE]["image"] = "postgres:17"

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any(A_STANDBY_REPLAYS_THE_PRIMARY_AND_NEEDS_ITS_BINARIES in one for one in found)


def test_a_replica_admitting_fewer_connections_than_the_primary_is_refused() -> None:
    """A hot standby refuses to start below its primary's figure. Delete this and the replica can
    be tuned down to save memory into a container that never becomes ready."""
    document = overlay()
    replica = services(document)[REPLICA_SERVICE]
    replica["command"] = [
        replica["command"][0].replace("max_connections=100", "max_connections=50")
    ]

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any("admits 50 connections" in one for one in found), found


def test_a_copy_not_taken_through_the_slot_is_refused() -> None:
    """Delete this and the slot the setup creates keeps WAL for a replica that is not using it,
    which is the disk-filling case with nothing ever reading the WAL."""
    document = overlay()
    replica = services(document)[REPLICA_SERVICE]
    replica["command"] = [replica["command"][0].replace(f"--slot={SLOT} ", "")]

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any("keeps WAL for nobody" in one for one in found), found


@pytest.mark.parametrize(
    "line",
    [
        "rm -rf /var/lib/postgresql/18/docker/pg_wal",
        'printf x > "$$hba"',
        "echo x >> /var/lib/postgresql/18/docker/postgresql.conf",
    ],
)
def test_a_setup_that_writes_anything_else_to_the_primarys_volume_is_refused(line: str) -> None:
    """The container holding the primary's data directory may append one rule to one file.
    Delete this and a line that truncates the rules file, writes the server's configuration or
    removes WAL passes as setup."""
    document = overlay()
    setup = services(document)[SETUP_SERVICE]
    setup["command"] = [setup["command"][0] + "\n" + line]

    found = setup_write_gaps(document)
    assert any(
        THE_SETUP_WRITES_ONE_RULE_TO_THE_PRIMARYS_VOLUME_AND_NOTHING_ELSE in one or "appends" in one
        for one in found
    ), found


def test_the_real_setup_writes_one_rule_and_nothing_else() -> None:
    """The positive half of the refusal above. Delete this and a check refusing every command
    passes it."""
    assert setup_write_gaps(overlay()) == ()


def test_a_replication_password_that_can_be_unset_is_refused() -> None:
    """Delete this and the replication login can be created with an empty password on an install
    that forgot to set one."""
    document = overlay()
    services(document)[SETUP_SERVICE]["environment"]["BRAIN_REPLICATION_PASSWORD"] = (
        "${BRAIN_REPLICATION_PASSWORD}"
    )

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any("so an unset password refuses to start" in one for one in found), found


def test_a_replica_that_does_not_wait_for_the_setup_is_refused() -> None:
    """Delete this and the first copy can start before the replication login exists, and fail
    in a way that reads as a wrong password."""
    document = overlay()
    del services(document)[REPLICA_SERVICE]["depends_on"]

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any("races the replication login" in one for one in found), found


def test_the_application_pointed_anywhere_but_the_replica_is_refused() -> None:
    """Pointed at `db`, every lag reading says not a replica and every page falls back, so the
    overlay does nothing and nothing says so. Delete this and that can ship."""
    document = overlay()
    environment = services(document)["app"]["environment"]
    environment[REPLICA_URL_SETTING] = environment[REPLICA_URL_SETTING].replace("db-replica", "db")

    found = replica_overlay_gaps(load("docker-compose.yml"), document)
    assert any("reaches 'db', not 'db-replica'" in one for one in found), found
