"""The plugin registry, held to the lifecycle it stores and to the two edges the table enforces.

Without a server: a stored row becomes an `Installed` through the manifest parser, and a record
that did not arrive installed is refused before anything is written. With one: `0032` is run for
real, a plugin is taken through install, enable, upgrade, disable, rollback and removal with every
record read back, and PostgreSQL is asked what it does with a plugin written switched on, a removal
from anything but disabled, a second document under a version that ran, and a point that does not
take a plugin.

Task ids: M29.2.2
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import psycopg
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.plugin_registry import (
    RegistryError,
    installed_from,
    manifest_for,
    records,
    remove,
    save,
)
from brain.plugins.lifecycle import (
    Installed,
    LifecycleError,
    PluginState,
    disable,
    enable,
    install,
    rollback,
    upgrade,
)
from brain.plugins.manifest import PluginManifest, manifest_from
from brain.plugins.points import Answer, points_answering
from brain.tables.plugin import PLUGIN_POINTS, PluginInstallRow
from tests.fixtures.scratch_postgres import (
    built,
    engine,
    migrate,
    modelled,
    present,
    run,
    secured,
    shape,
    sql,
)

#: Far outside any plausible wall clock.
AT = datetime(2999, 3, 1, tzinfo=UTC)
CORE = "1.0.0"
TABLES = ("ops.plugin_version", "ops.plugin_install")


def a_manifest(plugin_id: str, version: str = "1.0.0", **overrides: object) -> PluginManifest:
    raw: dict[str, object] = {
        "plugin_id": plugin_id,
        "version": version,
        "point": "connector",
        "requires": [{"value": "read:ticket.status"}],
        "core_min": "0.1.0",
        "core_max": "9.0.0",
    }
    raw.update(overrides)
    return manifest_from(raw)


# ------------------------------------------------------------------- without a server
def test_the_points_a_row_may_name_are_the_ones_the_register_says_take_a_plugin() -> None:
    """Held against the register's own answer and against two names it refuses, rather than
    against a list written here.

    Delete this and a constraint widened by hand to admit the storage backend, which the register
    refuses as a plugin point in writing, would pass."""
    assert set(PLUGIN_POINTS) == {one.name for one in points_answering(Answer.PLUGIN)}
    assert "storage_backend" not in PLUGIN_POINTS
    assert "scope_pack" not in PLUGIN_POINTS
    assert "connector" in PLUGIN_POINTS


def test_a_stored_row_becomes_the_record_it_was_written_from() -> None:
    """The producer, from a raw row whose manifest is a document and whose history is a list.

    Delete this and `installed_from` could drop the history, which is the one field a rollback
    reads, with every lifecycle test still passing."""
    manifest = a_manifest("ticket-bridge", "1.1.0")
    row = PluginInstallRow(
        plugin_id="ticket-bridge",
        version="1.1.0",
        point="connector",
        state="enabled",
        since=AT,
        history=["1.0.0", "1.1.0"],
        manifest=manifest.model_dump(mode="json"),
    )

    assert installed_from(row) == Installed(
        manifest=manifest, state=PluginState.ENABLED, since=AT, history=("1.0.0", "1.1.0")
    )


def test_a_stored_manifest_carrying_reach_is_refused_on_the_way_back_out() -> None:
    """A document edited in the database to carry a grant is refused by name when it is read.

    Delete this and `installed_from` could validate with pydantic alone, which calls a smuggled
    `capabilities` key an unknown field rather than an attempt at reach."""
    document = a_manifest("ticket-bridge").model_dump(mode="json")
    document["capabilities"] = ["admin:everything"]
    row = PluginInstallRow(
        plugin_id="ticket-bridge",
        version="1.0.0",
        point="connector",
        state="installed",
        since=AT,
        history=["1.0.0"],
        manifest=document,
    )

    with pytest.raises(Exception, match="does not carry reach"):
        installed_from(row)


class _Empty(AsyncSession):
    """A session with nothing stored, which records what is added."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def get(self, entity: Any, ident: Any, **_: Any) -> Any:
        return None

    def add(self, instance: Any, _warn: bool = True) -> None:
        self.added.append(instance)

    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        return None


def test_a_record_that_did_not_arrive_installed_is_refused_before_it_is_written() -> None:
    """An enabled record for a plugin with no row is the absent-to-enabled edge nobody has.

    Delete this and the insert policy is the only refusal, in the words of a policy."""
    arrived = install(a_manifest("ticket-bridge"), core_version=CORE, at=AT)
    switched_on = enable(arrived, at=AT)

    session = _Empty()
    with pytest.raises(RegistryError):
        run(lambda: save(session, switched_on))
    assert [type(one).__name__ for one in session.added] == ["PluginVersionRow"]

    session = _Empty()
    run(lambda: save(session, arrived))
    assert [type(one).__name__ for one in session.added] == ["PluginVersionRow", "PluginInstallRow"]


# ------------------------------------------------------- what only a server can answer
@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    with built("brain_plugin_registry_check", "0032") as url:
        yield url


async def _in_session(url: str, work: Any, *, as_app: bool = True) -> Any:
    from sqlalchemy import text

    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session, session.begin():
            if as_app:
                await session.execute(text("SET LOCAL ROLE brain_app"))
            return await work(session)
    finally:
        await made.dispose()


def test_a_plugin_goes_through_its_whole_life_and_every_record_reads_back(server: str) -> None:
    """Install, enable, upgrade, disable, roll back to the version it ran, and remove, saved and
    read back after each step as the application role.

    Delete this and the registry could lose the history or the state on any one step, and the
    first rollback on a real install would be refused for a version it has run."""
    first = a_manifest("life-cycle")
    later = a_manifest("life-cycle", "1.1.0")
    steps: list[Installed] = []
    steps.append(install(first, core_version=CORE, at=AT))
    steps.append(enable(steps[-1], at=AT + timedelta(minutes=1)))
    steps.append(upgrade(steps[-1], later, core_version=CORE, at=AT + timedelta(minutes=2)))
    steps.append(disable(steps[-1], at=AT + timedelta(minutes=3)))

    for step in steps:
        run(partial(_in_session, server, partial(save, record=step)))
        assert run(lambda: _in_session(server, records))["life-cycle"] == step

    ran = run(lambda: _in_session(server, lambda s: manifest_for(s, "life-cycle", "1.0.0")))
    assert ran == first
    back = rollback(steps[-1], ran, at=AT + timedelta(minutes=4))
    run(lambda: _in_session(server, lambda s: save(s, back)))
    assert run(lambda: _in_session(server, records))["life-cycle"] == back

    run(lambda: _in_session(server, lambda s: remove(s, "life-cycle", at=AT + timedelta(hours=1))))
    assert "life-cycle" not in run(lambda: _in_session(server, records))
    assert sql(
        server, "SELECT version FROM ops.plugin_version WHERE plugin_id = 'life-cycle' ORDER BY 1"
    ) == [("1.0.0",), ("1.1.0",)]


def test_nothing_is_removed_unless_it_is_disabled(server: str) -> None:
    """Refused by the lifecycle through the store, and refused by the check constraint to an
    UPDATE written past the store.

    Delete this and an enabled plugin can be taken off the install while its work is in flight."""
    arrived = install(a_manifest("still-on"), core_version=CORE, at=AT)
    run(lambda: _in_session(server, lambda s: save(s, arrived)))
    run(lambda: _in_session(server, lambda s: save(s, enable(arrived, at=AT))))

    with pytest.raises(LifecycleError):
        run(lambda: _in_session(server, lambda s: remove(s, "still-on", at=AT)))

    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE ops.plugin_install SET removed_at = %s WHERE plugin_id = 'still-on'", (AT,)
            )
        conn.rollback()
    assert "still-on" in run(lambda: _in_session(server, records))


def test_a_removed_plugin_cannot_be_removed_again_and_keeps_when_it_came_off(server: str) -> None:
    """Removed once, then removed again a day later: refused, and the first instant stands.

    A retired row is still `disabled`, so the lifecycle's own transition check passes a second
    removal. Only the store's check that the row is not already retired refuses it.

    Delete this and whoever presses remove second moves the record of when a plugin stopped
    running here, which is the one fact the retired row exists to keep."""
    arrived = install(a_manifest("off-once"), core_version=CORE, at=AT)
    run(lambda: _in_session(server, lambda s: save(s, arrived)))
    run(lambda: _in_session(server, lambda s: save(s, disable(enable(arrived, at=AT), at=AT))))
    run(lambda: _in_session(server, lambda s: remove(s, "off-once", at=AT)))

    with pytest.raises(RegistryError):
        run(lambda: _in_session(server, lambda s: remove(s, "off-once", at=AT + timedelta(days=1))))
    assert sql(
        server, "SELECT removed_at FROM ops.plugin_install WHERE plugin_id = 'off-once'"
    ) == [(AT,)]


def test_the_application_role_cannot_delete_an_install_row(server: str) -> None:
    """No DELETE is granted, so a removal is a retirement and the row survives it.

    Delete this and a DELETE grant added back to the table passes every other test here, and the
    record of when a plugin stopped running is one statement from gone."""
    arrived = install(a_manifest("kept-row"), core_version=CORE, at=AT)
    run(lambda: _in_session(server, lambda s: save(s, arrived)))
    run(lambda: _in_session(server, lambda s: save(s, disable(enable(arrived, at=AT), at=AT))))

    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM ops.plugin_install WHERE plugin_id = 'kept-row'")
        conn.rollback()


def test_a_removed_plugin_comes_back_installed_and_never_enabled(server: str) -> None:
    """Removed, then written back enabled through the store and through a bare UPDATE, both
    refused; written back installed, and it is on the install again.

    Delete this and the second route out of absent, an update of a retired row, puts a plugin on
    the server switched on, which the insert policy alone was never going to see."""
    arrived = install(a_manifest("comes-back"), core_version=CORE, at=AT)
    run(lambda: _in_session(server, lambda s: save(s, arrived)))
    run(lambda: _in_session(server, lambda s: save(s, disable(enable(arrived, at=AT), at=AT))))
    run(lambda: _in_session(server, lambda s: remove(s, "comes-back", at=AT)))
    assert "comes-back" not in run(lambda: _in_session(server, records))

    with pytest.raises(RegistryError):
        run(lambda: _in_session(server, lambda s: save(s, enable(arrived, at=AT))))

    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "UPDATE ops.plugin_install SET removed_at = NULL, state = 'enabled' "
                "WHERE plugin_id = 'comes-back'"
            )
        conn.rollback()

    back = install(a_manifest("comes-back"), core_version=CORE, at=AT + timedelta(days=1))
    run(lambda: _in_session(server, lambda s: save(s, back)))
    assert run(lambda: _in_session(server, records))["comes-back"] == back


def test_a_plugin_written_switched_on_is_refused_by_the_table(server: str) -> None:
    """The insert policy, past the store: `enabled` is refused and `installed` is written.

    Delete this and one INSERT puts a plugin on a server switched on, which is the edge the
    lifecycle's whole docstring is about not having."""
    document = a_manifest("arrives-on").model_dump(mode="json")
    sql(
        server,
        "INSERT INTO ops.plugin_version (plugin_id, version, manifest) "
        "VALUES ('arrives-on', '1.0.0', %s)",
        psycopg.types.json.Jsonb(document),
    )
    insert = (
        "INSERT INTO ops.plugin_install "
        "(plugin_id, version, point, state, since, history, manifest) "
        "VALUES ('arrives-on', '1.0.0', 'connector', %s, %s, ARRAY['1.0.0'], %s)"
    )

    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(insert, ("enabled", AT, psycopg.types.json.Jsonb(document)))
        conn.rollback()
        conn.execute("SET ROLE brain_app")
        conn.execute(insert, ("installed", AT, psycopg.types.json.Jsonb(document)))
        conn.commit()


def test_a_version_that_ran_cannot_come_back_as_a_different_document(server: str) -> None:
    """Saved once, then saved again under the same version with a different requirement.

    Delete this and a rollback can return to a version string whose document changed after it
    ran."""
    original = install(a_manifest("one-document"), core_version=CORE, at=AT)
    run(lambda: _in_session(server, lambda s: save(s, original)))
    rewritten = install(
        a_manifest("one-document", requires=[{"value": "admin:plugin"}]), core_version=CORE, at=AT
    )

    with pytest.raises(RegistryError):
        run(lambda: _in_session(server, lambda s: save(s, rewritten)))


def test_a_point_the_register_refuses_as_a_plugin_point_is_refused_by_the_table(
    server: str,
) -> None:
    """A manifest for the storage backend parses, and the table will not hold it.

    Delete this and the register's refusal of that point is a paragraph with nothing behind it in
    the database."""
    record = install(a_manifest("wrong-point", point="storage_backend"), core_version=CORE, at=AT)

    with pytest.raises(IntegrityError):
        run(lambda: _in_session(server, lambda s: save(s, record)))


def test_row_level_security_is_on_for_both_registry_tables(server: str) -> None:
    """Asked of the two tables `0032` builds.

    Delete this and a table created without its ENABLE statement is found by CI only."""
    assert secured(server, TABLES) == dict.fromkeys(TABLES, True)


def test_the_migration_builds_exactly_what_the_models_declare(server: str) -> None:
    """Every constraint by name and definition, every index and every column.

    Delete this and the migration and the models can disagree about a constraint's name, which is
    the thing a later migration dropping it has to get right."""
    with modelled("brain_plugin_registry_modelled", TABLES) as from_models:
        assert shape(server, TABLES) == shape(from_models, TABLES)


def test_the_migration_comes_down_and_goes_back_up() -> None:
    """Upgrade, downgrade and upgrade again, asking after the tables each time.

    Delete this and a downgrade dropping the version table first, which the foreign key refuses, is
    found on the day a release is rolled back."""
    with built("brain_plugin_registry_round_trip", "0032") as url:
        assert present(url, TABLES) == set(TABLES)
        migrate("brain_plugin_registry_round_trip", "downgrade", "0031")
        assert present(url, TABLES) == set()
        migrate("brain_plugin_registry_round_trip", "upgrade", "0032")
        assert present(url, TABLES) == set(TABLES)
