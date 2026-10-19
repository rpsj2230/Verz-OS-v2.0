"""A load run's result as a row: its key, its shape, its reader and the switch that ships off.

The database half (the row written and read back inside a rolled-back transaction) is
`tests/unit/test_acceptance_load_peak.py`; this file holds what needs no database: that a record
survives its own serialisation, that a value of the wrong shape is no record, that the key is a key
the table accepts, and that the feature declares itself and ships off.

Task ids: M22.3.3
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.ops.features import FEATURES, feature, feature_gaps
from brain.ops.load_run_store import (
    NAMESPACE,
    LaneFigures,
    RunRecord,
    RunStoreError,
    database_keeper,
    record_from,
    runs_in,
)
from brain.ops.setting_store import SettingState, checked_key

#: Far outside any plausible wall clock, because nothing here is about the present.
THEN = datetime(2999, 1, 1, tzinfo=UTC)


def record(run_id: str = "abc123", *, at: datetime = THEN, held: bool = True) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        commit="a-release",
        profile="full",
        started_at=at,
        seconds_run=600.5,
        stated_arrivals_per_second=2.0,
        stated_in_flight=8.0,
        arrivals_per_second=2.0,
        planned=1200,
        sent=1200,
        not_sent=0,
        most_in_flight=9,
        people=2,
        at_stated_peak=True,
        held=held,
        interactive_shed=0,
        lanes=(
            LaneFigures("answer", 960, 4200.0, 0.999, 0),
            LaneFigures("fast", 240, None, None, 0),
        ),
        findings=("a finding",),
    )


def state(value: Any, key: str = "load_test.run_abc123") -> SettingState:
    return SettingState(key=key, value_type="json", value=value, updated_by="x", updated_at=THEN)


def test_a_record_survives_being_written_as_json_and_read_back() -> None:
    """Through `json.dumps` and `json.loads`, which is what the column does, including a lane with
    no measured figures. Delete this and a value that the column cannot hold, or one that comes back
    as something else, is found by the first operator who runs the command."""
    one = record()
    again = json.loads(json.dumps(one.as_value()))
    assert record_from(again) == one


@pytest.mark.parametrize(
    "broken",
    [None, "text", [], {}, {"run_id": "abc"}],
)
def test_a_value_that_is_not_a_run_is_no_record(broken: object) -> None:
    """Delete this and a row somebody wrote by hand is read as a run, or breaks the page that
    lists them."""
    assert record_from(broken) is None


def test_a_value_with_one_field_of_the_wrong_type_is_no_record() -> None:
    """Every field present and one the wrong type. Delete this and `record_from` believes the
    shape because the keys are there."""
    value = record().as_value()
    value["planned"] = "many"
    assert record_from(value) is None
    value = record().as_value()
    value["lanes"] = [{"lane": "answer"}]
    assert record_from(value) is None


def test_a_verdict_is_held_only_when_the_stored_value_is_the_boolean_true() -> None:
    """A stored `held` of a truthy string or a one. Delete this and a hand-written row saying
    "no" or "0" is read as a run that held, and the stored verdict is not the verdict."""
    for stored in ("no", "False", 1, "yes"):
        value = record().as_value()
        value["held"] = stored
        value["at_stated_peak"] = stored
        got = record_from(value)
        assert got is not None
        assert not got.held
        assert not got.at_stated_peak


def test_runs_are_listed_newest_first_and_a_row_that_is_not_a_run_is_skipped() -> None:
    """Three rows in one namespace, one of them somebody else's. Delete this and the newest run is
    not the one shown first, or a stray row in the namespace breaks the list."""
    old = record("old1", at=THEN - timedelta(days=2))
    new = record("new1", at=THEN)
    held = {
        "load_test.run_old1": state(old.as_value(), "load_test.run_old1"),
        "load_test.run_new1": state(new.as_value(), "load_test.run_new1"),
        "load_test.note": state("not a run", "load_test.note"),
    }
    assert runs_in(held) == (new, old)


def test_a_row_outside_the_run_keys_is_not_listed_even_when_its_value_is_a_run() -> None:
    """A valid run's value under a key that is not a run's. Delete this and anything somebody keeps
    in the namespace that happens to have the shape is listed as a measured run."""
    one = record("abc123")
    held = {
        "load_test.run_abc123": state(one.as_value()),
        "load_test.something_else": state(record("zzz").as_value(), "load_test.something_else"),
    }
    assert runs_in(held) == (one,)


def test_a_run_is_written_as_one_json_row_attributed_to_the_command() -> None:
    """The statements `keep_run` sends, compiled and read. Delete this and the row is written with
    a type the column's own constraint refuses, which only a real database finds, after the
    spend."""
    import asyncio

    from sqlalchemy.dialects.postgresql import Insert

    from brain.ops.load_run_store import WRITER, keep_run

    sent: list[Any] = []

    class Recorder:
        async def execute(self, statement: Any) -> None:
            sent.append(statement)

    one = record()
    asyncio.run(keep_run(Recorder(), one))  # type: ignore[arg-type]
    inserts = [s for s in sent if isinstance(s, Insert)]
    assert len(inserts) == 1
    params = inserts[0].compile().params
    assert params["key"] == one.key
    assert params["value_type"] == "json"
    assert params["updated_by"] == WRITER
    assert params["value"] == one.as_value()
    assert len(sent) == 4, "three attributions, then the row"


def test_a_run_s_key_is_one_the_settings_table_accepts_and_is_the_runs_own() -> None:
    """The key against the table's own grammar. Delete this and a change to the id's shape
    produces a key the column refuses, found only when a real run tries to keep its result."""
    one = record()
    assert one.key == f"{NAMESPACE}.run_abc123"
    assert checked_key(one.key) == one.key
    assert record("other").key != one.key


@pytest.mark.parametrize("bad", ["", "Has-Capitals", "with space", "UPPER", "a.b"])
def test_a_run_id_that_could_not_end_a_setting_key_is_refused(bad: str) -> None:
    """Delete this and an id is accepted that only the database refuses, after the spend."""
    with pytest.raises(RunStoreError):
        record(bad)


def test_a_record_names_no_person_and_no_question_because_it_has_no_field_for_one() -> None:
    """The record's own field names. Delete this and a field that could carry a person or a
    question can be added to the row anybody who reads settings can see."""
    names = set(record().as_value())
    forbidden = {"token", "tokens", "principal", "principal_id", "question", "questions", "person"}
    assert not names & forbidden
    assert not any("token" in one or "question" in one for one in names)


def test_the_feature_ships_off_names_its_reader_and_the_reader_asks() -> None:
    """The switch is declared in its own module, is in the list, and `feature_gaps` finds its
    reader asking. Delete this and the switch can be declared and read by nothing, so it renders
    and changes a row and the command runs regardless."""
    one = feature("load_test")
    assert one in FEATURES
    assert one.read_by == ("brain.ops.load_run_store:load_test_is_on",)
    assert not [gap for gap in feature_gaps() if "load_test" in gap]


def test_a_command_with_no_database_to_keep_its_result_in_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the real keeper is built over an empty address and fails after the spend."""
    for name in ("DATABASE_URL", "BRAIN_DATABASE_URL", "BRAIN_MIGRATION_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RunStoreError):
        database_keeper()
