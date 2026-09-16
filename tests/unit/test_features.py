"""Feature switches: every one ships off, every one is read by what it names, and the Features
screen turns one only for a caller holding the authority over everything.

The registry is held to the source by `feature_gaps`, run here against this tree and against a
throwaway tree where a reader stopped asking and a stranger started, because a check that has
only ever seen the healthy tree has never been shown to fail. The route is driven through the
real application with `ops.setting` held in memory by `tests.fixtures.setting_rows`, so a switch
is followed to the row it writes and to the next read that sees it.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.feature_routes import FEATURE_AUTHORITY
from brain.ops import features
from brain.ops.features import (
    FEATURES,
    PROMPT_EDITING,
    SCHEDULE_CONTROL,
    Feature,
    FeatureError,
    feature,
    feature_gaps,
    switched_on_in,
)
from brain.ops.setting_store import SettingState, SettingStoreError, checked_key
from brain.tables.config import RESERVED_KEY_PREFIXES
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import SettingRows

FEATURES_PATH = f"{API_PREFIX}/install/features"
EVERYWHERE = Scope.unrestricted()

#: `u_admin` holds the authority over everything; `u_narrow` holds it in one department, which a
#: switch for the whole install cannot be; `u_none` holds nothing.
GRANTS = {
    "u_admin": (Grant(capability=FEATURE_AUTHORITY, scope=EVERYWHERE),),
    "u_narrow": (Grant(capability=FEATURE_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


def state(value: object, value_type: str = "boolean") -> SettingState:
    return SettingState(
        key="feature.x",
        value_type=value_type,
        value=value,
        updated_by="u_someone",
        updated_at=datetime(2019, 1, 1, tzinfo=UTC),
    )


# ------------------------------------------------------------------------ the registry


def test_every_feature_is_off_until_a_row_holds_true() -> None:
    """No row, a false row, and the string "true" are all off; only the JSON true is on.

    Delete this and a feature a person at a prompt switched with the string `"false"`, which is
    truthy, arrives switched on for every reader of the switch."""
    assert switched_on_in({}) == frozenset()
    assert switched_on_in({PROMPT_EDITING.name: state(False)}) == frozenset()
    assert switched_on_in({PROMPT_EDITING.name: state("true", "string")}) == frozenset()
    assert switched_on_in({PROMPT_EDITING.name: state(True)}) == {PROMPT_EDITING.name}


def test_a_row_naming_a_feature_nobody_declared_switches_nothing_on() -> None:
    """Delete this and a row somebody typed for a feature that does not exist reads as on."""
    assert switched_on_in({"made_up": state(True)}) == frozenset()


def test_a_feature_that_names_no_reader_is_refused_when_it_is_declared() -> None:
    """Delete this and a switch wired to nothing can be added to the registry."""
    with pytest.raises(FeatureError, match="names no reader"):
        Feature(name="orphan", title="An orphan", what="Does.", while_off="Does not.", read_by=())


def test_an_unknown_feature_is_refused_by_name_rather_than_answered_none() -> None:
    """Delete this and a caller handed None switches nothing and reports success."""
    assert feature(SCHEDULE_CONTROL.name) is SCHEDULE_CONTROL
    with pytest.raises(FeatureError, match="no feature named"):
        feature("made_up")


def test_every_declared_reader_asks_about_its_feature_and_nothing_else_asks() -> None:
    """The real tree has no gaps: each named function calls `is_on` with its own feature, and no
    function calls it without being named.

    Delete this and a route can stop asking whether its feature is on while the Features screen
    goes on switching a row nothing reads."""
    assert feature_gaps() == ()
    assert {reader.partition(":")[0] for one in FEATURES for reader in one.read_by} == {
        "brain.prompt_routes",
        "brain.jobs_routes",
    }


def test_the_reader_check_reports_a_reader_that_stopped_asking_and_an_asker_nobody_named(
    tmp_path: Path,
) -> None:
    """Against a tree with one undeclared asker, and a registry naming a function that exists and
    never asks.

    Delete this and `feature_gaps` can return nothing for ever, which the test above cannot tell
    from a healthy tree."""
    package = tmp_path / "brain"
    package.mkdir()
    (package / "stranger.py").write_text(
        "async def sneaks(session):\n    return await is_on(session, SCHEDULE_CONTROL)\n",
        encoding="utf-8",
        newline="\n",
    )
    silent = Feature(
        name="schedule_control",
        title="t",
        what="w",
        while_off="o",
        read_by=("brain.ops.features:switch_states",),
    )
    found = feature_gaps((silent,), src=package)

    assert any("never asks" in one for one in found), found
    assert any("brain.stranger:sneaks asks is_on" in one for one in found), found


def test_the_reader_check_matches_the_feature_a_reader_asks_about_not_only_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reader that asks about the other feature is a gap for this one.

    Delete this and a route gated on the wrong switch passes the check."""
    swapped = Feature(
        name="prompt_editing",
        title="t",
        what="w",
        while_off="o",
        read_by=("brain.jobs_routes:pause_job",),
    )
    monkeypatch.setattr(features, "SWAPPED", swapped, raising=False)

    found = feature_gaps((swapped,), src=Path(features.__file__).parent / "does-not-exist")

    assert any("never asks" in one for one in found), found


def test_a_switch_key_in_a_namespace_the_permission_model_owns_is_refused() -> None:
    """Delete this and a switch can be written under `grant.` or `leash.`, where a later reader
    could take it for a permission."""
    for prefix in RESERVED_KEY_PREFIXES:
        with pytest.raises(SettingStoreError, match="permission model"):
            checked_key(f"{prefix}.anything")
    assert checked_key(PROMPT_EDITING.key) == "feature.prompt_editing"


# ------------------------------------------------------------------------ the screen


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def served(settings: SettingRows) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(settings.answer)
        yield client, stub


def test_the_screen_lists_every_feature_off_on_a_fresh_install(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and the screen can draw a feature nobody switched as on."""
    client, _ = served
    body = get(client, "u_admin", FEATURES_PATH).json()

    assert [one["name"] for one in body["features"]] == [one.name for one in FEATURES]
    assert all(one["on"] is False and one["changed_by"] is None for one in body["features"])
    assert body["components_are_chosen_by_the_profile"] is True
    assert body["plugins_have_no_loader"] is True


def test_switching_a_feature_on_writes_its_row_and_the_next_read_sees_it(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """The write is followed to the row, who wrote it, the commit and the next read.

    Delete this and a switch can render as turned while writing a different key, or nothing."""
    client, stub = served
    answer = post(client, "u_admin", f"{FEATURES_PATH}/schedule_control", {"on": True})

    assert answer.status_code == 200, answer.text
    assert answer.json()["on"] is True
    assert settings.writes == [
        {
            "key": "feature.schedule_control",
            "value_type": "boolean",
            "value": True,
            "updated_by": "u_admin",
        }
    ]
    assert stub.commits == 1
    listed = get(client, "u_admin", FEATURES_PATH).json()
    on = {one["name"]: one["on"] for one in listed["features"]}
    assert on == {"prompt_editing": False, "schedule_control": True}


def test_switching_off_keeps_the_row_and_says_who_turned_it_off(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and turning a feature off erases the record of who turned it on."""
    client, _ = served
    settings.hold("feature.prompt_editing", True, value_type="boolean", by="u_elsewhere")
    answer = post(client, "u_admin", f"{FEATURES_PATH}/prompt_editing", {"on": False})

    assert answer.json()["on"] is False
    assert answer.json()["changed_by"] == "u_admin"
    assert settings.rows["feature.prompt_editing"].value is False


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
def test_a_caller_without_the_authority_over_everything_is_refused_before_the_database(
    pid: str,
) -> None:
    """The same refusal with a database and without one, and nothing written.

    Delete this and a department-scoped holder switches a feature for the whole install, or a
    caller with nothing learns whether this process has a pool."""
    with console_client(GRANTS, database=False) as (client, _):
        without = post(client, pid, f"{FEATURES_PATH}/schedule_control", {"on": True})
        listed_without = get(client, pid, FEATURES_PATH)
    with console_client(GRANTS) as (client, stub):
        rows = SettingRows()
        stub.answerers.append(rows.answer)
        with_pool = post(client, pid, f"{FEATURES_PATH}/schedule_control", {"on": True})
        listed_with = get(client, pid, FEATURES_PATH)

    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert listed_without.status_code == listed_with.status_code == 404
    assert listed_without.json()["message"] == listed_with.json()["message"]
    assert rows.writes == []
    assert stub.statements == []


def test_a_password_only_sign_in_holding_the_authority_cannot_switch_a_feature(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """`brain.gate.admission` withholds `admin:` from a session with no second factor, and the
    route asks the admitted reach rather than the grants on file.

    Delete this and a stolen password alone switches a feature for the whole install."""
    client, _ = served
    answer = post(
        client, "u_admin", f"{FEATURES_PATH}/schedule_control", {"on": True}, strong=False
    )

    assert answer.status_code == 404
    assert settings.writes == []


def test_a_caller_with_the_authority_is_told_a_name_is_not_a_feature_and_nothing_is_written(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a typo in a feature name writes a row under a key nothing reads."""
    client, stub = served
    answer = post(client, "u_admin", f"{FEATURES_PATH}/made_up", {"on": True})

    assert answer.status_code == 404
    assert "not a feature" in answer.json()["message"]
    assert settings.writes == []
    assert stub.commits == 0


def test_the_authority_is_an_administration_capability_the_first_administrator_holds() -> None:
    """Delete this and the Features screen needs a grant nobody on a fresh install has."""
    from brain.identity.first_administrator import ADMINISTRATION

    assert isinstance(FEATURE_AUTHORITY, Capability)
    assert FEATURE_AUTHORITY.value in ADMINISTRATION
