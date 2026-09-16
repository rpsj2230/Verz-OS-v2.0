"""The setup wizard's answers are kept in `ops.setting` and resolved ahead of the environment.

Three halves. The resolution order and the key mapping without a database; the rows and the
round trip against a real one, skipped when `DATABASE_URL` is unset; and the property that
makes the whole thing safe to have built, which is that a saved key can never be a permission.

**The environment is put back after every test that touches it.** `brain.install` holds the
saved values on the module, which is process state: a test that left one set would configure
every test that ran after it, and the failure would be somewhere else. `nothing_saved` is the
autouse fixture that restores whatever was held.

Dates are pinned in 2019 for the reason `tests/unit/test_setup_wizard.py` gives: nothing here
is about the present.

Task ids: M42.5.10, M42.5.14, M31.3.1.4
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain.db import normalise_database_url
from brain.identity.first_administrator import (
    FirstAdministratorRefusedError,
    FirstAdministrators,
)
from brain.install import (
    BY_NAME,
    INSTALLATION,
    InstallError,
    hold_saved,
    missing,
    saved_values,
    value_of,
)
from brain.ops.install_settings import (
    SAVED_TYPE,
    SETTING_NAMESPACE,
    key_for,
    load,
    name_for,
    refresh,
    rows_for,
    save,
    values_from,
)
from brain.session import make_session_factory
from brain.setup_wizard import SECRET_ANSWERS, apply_install, settings_from
from brain.tables.config import (
    RESERVED_KEY_PREFIXES,
    SETTING_KEY_PATTERN,
    SettingRow,
    SettingType,
)
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_first_administrator import FIRST, NAME, audited, first_run_grant
from tests.unit.test_setup_wizard import INSIDE, SECRET, an_enrolment, answered

#: Who the rows say changed them last. The appointed principal, which is what `appoint` passes.
BY_WHOM = FIRST


@pytest.fixture(autouse=True)
def nothing_saved() -> Iterator[None]:
    """Every test starts with nothing held and leaves whatever was held before it."""
    before = hold_saved({})
    yield
    hold_saved(before)


def wizard_settings(*, hosted: bool = False) -> dict[str, str]:
    """Exactly what one finished wizard sets, through the wizard's own entry point."""
    return dict(settings_from(answered(hosted=hosted)))


# ----------------------------------------------------------------- the resolution order


def test_a_saved_answer_is_read_before_the_environment_and_the_environment_before_the_default() -> (
    None
):
    """The order, all three rungs at one name, which is the positive case the refusals below
    need.

    Delete this and the order can be reversed with every other test here still green, and the
    reversal is the one that makes the whole change invisible: an install that copied
    `.env.example` carries `INSTALL_COMPANY_NAME=Your Company` as a literal, so the wizard would
    save the company's real name and the screens would go on reading the template's."""
    declared = BY_NAME["INSTALL_COMPANY_NAME"].default
    environment = {"INSTALL_COMPANY_NAME": "From The File"}

    assert value_of("INSTALL_COMPANY_NAME", {}, {}) == declared
    assert value_of("INSTALL_COMPANY_NAME", environment, {}) == "From The File"
    assert (
        value_of("INSTALL_COMPANY_NAME", environment, {"INSTALL_COMPANY_NAME": "From The Wizard"})
        == "From The Wizard"
    )


def test_a_saved_value_that_is_blank_falls_through_to_the_environment() -> None:
    """The sibling of the order: a row holding whitespace is not an answer.

    Delete this and a row somebody blanked in the console shadows the environment with an empty
    string, which `value_of` would then return as this install's company name."""
    environment = {"INSTALL_COMPANY_NAME": "From The File"}

    assert value_of("INSTALL_COMPANY_NAME", environment, {"INSTALL_COMPANY_NAME": "  "}) == (
        "From The File"
    )


def test_a_required_setting_comes_from_a_saved_value_and_refuses_when_neither_source_has_it() -> (
    None
):
    """`value_of` and `missing` ask both sources in the same order, and refuse only when both are
    silent.

    Delete this and one of the two keeps the environment-only rule: a required setting the wizard
    saved is then reported as missing by a startup check while every reader resolves it happily,
    which is `ONE_READER_OR_TWO_DEFAULTS` arriving through the back door."""
    required = [one.name for one in INSTALLATION if one.required]
    saved = {name: f"saved-{name.lower()}" for name in required}

    with pytest.raises(InstallError):
        value_of(required[0], {}, {})
    assert missing({}, {}) == tuple(required)
    assert value_of(required[0], {}, saved) == saved[required[0]]
    assert missing({}, saved) == ()


def test_only_declared_settings_are_held_and_a_held_mapping_is_given_back_whole() -> None:
    """`hold_saved` drops a name nothing declares and returns what it replaced.

    Delete this and a row written by hand under `install.anything` becomes configuration nothing
    declared, with a default nobody wrote down, and a test that holds a value has no way to put
    the process back as it found it."""
    before = hold_saved({"INSTALL_COMPANY_NAME": "A Company", "INSTALL_MADE_UP": "no"})

    held = dict(saved_values())
    replaced = hold_saved({"INSTALL_PRODUCT_NAME": "Desk"})

    assert before == {}
    assert held == {"INSTALL_COMPANY_NAME": "A Company"}
    assert replaced == held
    assert dict(saved_values()) == {"INSTALL_PRODUCT_NAME": "Desk"}


def test_a_process_that_has_loaded_nothing_resolves_as_it_did_before_the_table_had_a_reader() -> (
    None
):
    """The sibling that keeps this change invisible where it should be. A process with no
    database, which is every command and every test, reads the environment and then the default.

    Delete this and the saved values can become a required source, after which a worker, a sweep
    or a migration with no session resolves nothing at all."""
    assert dict(saved_values()) == {}
    assert value_of("INSTALL_PRODUCT_NAME", {"INSTALL_PRODUCT_NAME": "Desk"}) == "Desk"
    assert value_of("INSTALL_PRODUCT_NAME", {}) == BY_NAME["INSTALL_PRODUCT_NAME"].default


# --------------------------------------------------------------------- the key mapping


@pytest.mark.parametrize("declared", [one.name for one in INSTALLATION])
def test_every_declared_setting_has_a_key_the_table_accepts_and_it_reads_back_to_the_same_name(
    declared: str,
) -> None:
    """Both directions over the real declaration, and the key held against the column's own
    grammar and its reserved namespaces rather than against a reading of them.

    Delete this and a setting whose key the check constraint refuses ships, and the refusal
    arrives on a client's server at the end of their wizard, after the code has been spent."""
    key = key_for(declared)

    assert re.match(SETTING_KEY_PATTERN, key), key
    assert not any(key.startswith(f"{prefix}.") for prefix in RESERVED_KEY_PREFIXES)
    assert name_for(key) == declared


def test_the_namespace_saved_settings_use_is_not_one_the_permission_model_owns() -> None:
    """The property that makes this table safe to write installation values into at all.

    Asserted against `RESERVED_KEY_PREFIXES` rather than by reading the list, because that list
    is deliberately wider than it needs to be and grows. Delete this and a later addition to it
    that happens to be this namespace turns every appointment into a constraint violation."""
    assert SETTING_NAMESPACE not in RESERVED_KEY_PREFIXES
    assert SAVED_TYPE is SettingType.STRING


@pytest.mark.parametrize(
    "key", ["leash.default_rung", "install", "install.", "install.made_up", "other.company_name"]
)
def test_a_key_outside_the_namespace_or_naming_nothing_declared_resolves_to_no_setting(
    key: str,
) -> None:
    """The refusal half of the mapping, empty rather than raising, because these are rows a
    person with a psql prompt can write and a startup must not die on one.

    Delete this and a row under any namespace at all is read back as an installation value."""
    assert name_for(key) == ""


def test_saving_a_setting_nobody_declared_is_refused_before_a_row_exists() -> None:
    """The writer's refusal, which is the one that has to raise: a value saved under a name
    nothing declares is configuration with no meaning, no default and no reader.

    Delete this and the wizard can write a row for a setting that was never declared, and the
    only sign is a row nothing ever reads."""
    with pytest.raises(InstallError):
        key_for("INSTALL_MADE_UP")
    with pytest.raises(InstallError):
        rows_for({"INSTALL_MADE_UP": "no"}, updated_by=BY_WHOM)


def test_a_row_carries_the_declarations_own_meaning_and_who_changed_it() -> None:
    """The positive case for the rows, in key order.

    Delete this and the description can go empty, which the table's `described` constraint
    refuses, or be a sentence written beside the declaration that goes stale the first time the
    declared meaning changes."""
    rows = rows_for({"INSTALL_PRODUCT_NAME": "Desk", "INSTALL_COMPANY_NAME": "A"}, updated_by="u_x")

    assert [one["key"] for one in rows] == ["install.company_name", "install.product_name"]
    assert rows[0] == {
        "key": "install.company_name",
        "value_type": SettingType.STRING.value,
        "value": "A",
        "description": BY_NAME["INSTALL_COMPANY_NAME"].meaning,
        "updated_by": "u_x",
    }


@pytest.mark.parametrize(
    "row",
    [
        ("other.company_name", "string", "A"),
        ("install.made_up", "string", "A"),
        ("install.company_name", "integer", 4),
        ("install.company_name", "json", {"clauses": []}),
    ],
)
def test_a_row_in_another_namespace_or_of_another_shape_is_not_resolved(
    row: tuple[str, str, Any],
) -> None:
    """The reader's refusals. Delete this and a json object stored under a settings key is
    handed to `value_of` as a value that is not a string, and whichever reader casts it first
    fails somewhere else entirely."""
    assert values_from([row]) == {}


def test_every_setting_one_finished_wizard_produces_can_be_saved_and_no_secret_answer_is() -> None:
    """The join: what `settings_from` produces is exactly what this can keep, and the provider
    key is not among it.

    Delete this and a question added to the wizard with a new setting is discovered on a
    client's server, and the guard that the wizard's secret answers never become rows rests on
    nobody having written one into `Applied.settings`."""
    hosted = apply_install(
        answered(hosted=True),
        an_enrolment(),
        SECRET,
        principal_id=FIRST,
        administrators=0,
        now=INSIDE,
    )
    rows = rows_for(dict(hosted.settings), updated_by=BY_WHOM)

    assert dict(hosted.settings)
    assert {name_for(one["key"]) for one in rows} == set(hosted.settings)
    assert hosted.provider_key
    assert all(hosted.provider_key != one["value"] for one in rows)
    assert SECRET_ANSWERS
    assert values_from([(one["key"], one["value_type"], one["value"]) for one in rows]) == dict(
        hosted.settings
    )


# ------------------------------------------------------------------------ the database


def with_sessions[T](
    url: str,
    work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]],
    *,
    as_owner: bool = False,
) -> T:
    """Run `work` over application-role sessions on this database, as every request does.

    `as_owner` connects without the role instead, which is what a migration and a script do.
    No policy applies there, which is the case `load`'s own `deleted_at` test is written for.
    """

    async def go() -> T:
        engine = (
            create_async_engine(normalise_database_url(url), poolclass=NullPool)
            if as_owner
            else app_engine(url)
        )
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def appoint_with(url: str, values: dict[str, str], *, principal_id: str = FIRST) -> str:
    """Appoint through the real store with these settings, saying what came of it."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> str:
        store = FirstAdministrators(sessions)
        try:
            await store.appoint(
                first_run_grant(principal_id),
                display_name=NAME,
                trace_id="trace-install-settings",
                settings=values,
            )
        except FirstAdministratorRefusedError as refused:
            return refused.reason.value
        return "appointed"

    return with_sessions(url, work)


def saved_rows(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT key, value_type, value, updated_by FROM ops.setting"
        " WHERE deleted_at IS NULL ORDER BY key",
    )


def test_an_appointments_settings_are_read_back_by_a_process_that_did_not_write_them() -> None:
    """The end the whole design is for: the wizard's answers land in `ops.setting` as
    `brain_app`, and a session factory that never saw the write loads them and `value_of`
    resolves them over an environment that carries nothing.

    Delete this and the write can go to a table nothing reads, or the read can come back empty,
    and every test above still passes because every one of them is handed its own mapping."""
    values = wizard_settings()
    with audited("brain_install_settings_round_trip") as url:
        outcome = appoint_with(url, values)
        rows = saved_rows(url)
        loaded = dict(with_sessions(url, refresh))

    assert outcome == "appointed"
    assert loaded == values
    assert [str(one[0]) for one in rows] == sorted(key_for(name) for name in values)
    assert {str(one[1]) for one in rows} == {SettingType.STRING.value}
    assert {str(one[3]) for one in rows} == {FIRST}
    assert dict(saved_values()) == values
    assert value_of("INSTALL_COMPANY_NAME", {}) == values["INSTALL_COMPANY_NAME"]


def test_an_appointment_that_is_refused_writes_no_settings_at_all() -> None:
    """The refusal sibling, and the reason the rows are written inside `appoint`'s transaction:
    a second appointment is refused under the lock and leaves the first install's configuration
    exactly as it was.

    Delete this and the settings can be written beside the appointment rather than inside it,
    after which a refused second attempt rewrites a finished install's company name."""
    first = wizard_settings()
    second = {**first, "INSTALL_COMPANY_NAME": "Somebody Else"}
    with audited("brain_install_settings_refused") as url:
        appointed = appoint_with(url, first)
        beaten = appoint_with(url, second, principal_id="u_second")
        rows = saved_rows(url)
        loaded = dict(with_sessions(url, refresh))

    assert (appointed, beaten) == ("appointed", "already_administered")
    assert loaded == first
    assert not any("Somebody Else" in str(one[2]) for one in rows)


def test_saving_the_same_settings_twice_leaves_one_live_row_for_each_name() -> None:
    """`save` says the same thing run twice, against the partial unique index rather than by
    deleting first.

    Delete this and a second save duplicates every key, after which the partial unique index
    refuses the write, or two live rows make the effective configuration depend on which row
    came back first."""
    values = wizard_settings()
    changed = {**values, "INSTALL_PRODUCT_NAME": "Second Name"}

    async def twice(sessions: async_sessionmaker[AsyncSession]) -> int:
        async with sessions() as session, session.begin():
            await save(session, values, updated_by=BY_WHOM)
            return await save(session, changed, updated_by=BY_WHOM)

    with audited("brain_install_settings_twice") as url:
        written = with_sessions(url, twice)
        rows = saved_rows(url)
        loaded = with_sessions(url, _load_once)

    assert written == len(changed)
    assert len(rows) == len(changed)
    assert loaded["INSTALL_PRODUCT_NAME"] == "Second Name"


async def _load_once(sessions: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    """`load` over one transaction, without holding the result on the process."""
    async with sessions() as session, session.begin():
        return await load(session)


def test_the_application_role_can_write_and_read_these_rows_under_row_level_security() -> None:
    """The row-level security half, asserted as a property of the table rather than of the
    connection: the rows are written and read as `brain_app`, the role every request answers as,
    and a retired row stops being configuration.

    Delete this and the write can be made to work only as the owner, which every test here would
    still pass and no deployed process could ever do."""
    values = wizard_settings()
    with audited("brain_install_settings_rls") as url:
        assert appoint_with(url, values) == "appointed"
        live = with_sessions(url, _load_once)
        sql(url, "UPDATE ops.setting SET deleted_at = now() WHERE key = %s", "install.product_name")
        after = with_sessions(url, _load_once)
        enabled = sql(
            url, "SELECT relrowsecurity FROM pg_class WHERE oid = 'ops.setting'::regclass"
        )

    assert live == values
    assert "INSTALL_PRODUCT_NAME" in live
    assert "INSTALL_PRODUCT_NAME" not in after
    assert after == {k: v for k, v in values.items() if k != "INSTALL_PRODUCT_NAME"}
    assert [bool(one[0]) for one in enabled] == [True]


def test_a_retired_row_is_not_resolved_by_a_reader_no_policy_applies_to() -> None:
    """The half the policy cannot cover. `load` tests `deleted_at` itself, and every reader that
    goes through `brain_app` has `setting_live` doing it already, so the only way to tell whether
    the module does it too is to read as the role that owns the table, which is what a migration
    and `python -m brain.deployment.database` connect as.

    Delete this and the test in `load` is a line no test can reach, which is this repository's
    recurring defect exactly: retiring an override is how an install goes back to its default,
    and a script reading these values would resurrect every one somebody had retired."""
    values = wizard_settings()
    with audited("brain_install_settings_owner") as url:
        assert appoint_with(url, values) == "appointed"
        sql(url, "UPDATE ops.setting SET deleted_at = now() WHERE key = %s", "install.product_name")
        as_owner = with_sessions(url, _load_once, as_owner=True)
        all_rows = sql(url, "SELECT count(*) FROM ops.setting")

    assert [int(one[0]) for one in all_rows] == [len(values)]
    assert as_owner == {k: v for k, v in values.items() if k != "INSTALL_PRODUCT_NAME"}


def test_the_row_the_reader_selects_is_the_tables_own_column_set() -> None:
    """The positive case for `load`'s statement, held against the model rather than against a
    string: it selects the three columns `values_from` reads, in that order.

    Delete this and the columns can be reordered so that a value is read as a type, which
    `values_from` answers by dropping every row, and an install silently resolves nothing."""
    assert [SettingRow.key.key, SettingRow.value_type.key, SettingRow.value.key] == [
        "key",
        "value_type",
        "value",
    ]
