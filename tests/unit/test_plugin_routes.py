"""The plugin registry routes: refused before the database to anybody without the authority over
everything, refused while the switch is off, and drawn from the register and the stored records.

The stub holds `ops.setting` in memory (`tests.fixtures.setting_rows`) and answers the one select
the registry's list makes; every write needs a real transaction and is proved by the install check
`brain.ops.acceptance_checks_plugin_registry` over PostgreSQL.

Task ids: M29.1.2, M29.1.3, M29.1.4, M29.1.5, M29.1.7, M29.1.12, M29.2.1, M29.2.2, M29.2.3, M29.2.6
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.ops.features import PLUGIN_REGISTRY
from brain.plugin_routes import parsed
from brain.plugins.lifecycle import PLUGIN_ADMIN, PLUGIN_NOT_AVAILABLE
from brain.plugins.points import Answer, points_answering
from brain.routers import ROUTERS
from brain.tables.plugin import PluginInstallRow
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.setting_rows import NAMESPACE_COLUMNS, Result, SettingRows

PLUGINS = f"{API_PREFIX}/install/plugins"
EVERYWHERE = Scope.unrestricted()

#: `u_admin` holds the authority over everything and the capability a stand-in plugin needs;
#: `u_narrow` holds the authority in one department, which an install-wide record cannot be;
#: `u_none` holds nothing.
GRANTS = {
    "u_admin": (
        Grant(capability=PLUGIN_ADMIN, scope=EVERYWHERE),
        Grant(capability=Capability(value="read:ticket.status"), scope=EVERYWHERE),
    ),
    "u_narrow": (Grant(capability=PLUGIN_ADMIN, scope=Scope.department("web")),),
    "u_none": (),
}

A_MANIFEST: dict[str, Any] = {
    "plugin_id": "stand-in",
    "version": "1.0.0",
    "point": "connector",
    "requires": [{"value": "read:ticket.status"}],
    "core_min": "0.1.0",
    "core_max": "9.0.0",
}


def stored(manifest: dict[str, Any], state: str = "installed") -> SimpleNamespace:
    """A row of `ops.plugin_install` as the registry's list reads one."""
    return SimpleNamespace(
        plugin_id=manifest["plugin_id"],
        version=manifest["version"],
        point=manifest["point"],
        state=state,
        since=datetime(2019, 1, 1, tzinfo=UTC),
        history=[manifest["version"]],
        manifest=manifest,
        removed_at=None,
    )


class Registry:
    """The one select the registry's list makes, answering the rows a test holds."""

    def __init__(self) -> None:
        self.rows: list[SimpleNamespace] = []
        self.asked = 0

    def answer(self, statement: Any) -> Result | None:
        if not isinstance(statement, Select):
            return None
        if statement.column_descriptions[0].get("entity") is not PluginInstallRow:
            return None
        self.asked += 1
        return Result(self.rows)


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.fixture
def served(settings: SettingRows, registry: Registry) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.extend([settings.answer, registry.answer])
        yield client, stub


def test_the_router_is_mounted_by_the_application() -> None:
    """Delete this and the routes can be written, tested and never served."""
    assert any(
        getattr(one, "path", "").startswith(f"{API_PREFIX}/install/plugins")
        for router in ROUTERS
        for one in router.routes
    )


# -------------------------------------------------------------------------- the authority
EVERY_ROUTE = (
    ("GET", PLUGINS, None),
    ("POST", PLUGINS, {"manifest": A_MANIFEST}),
    ("POST", f"{PLUGINS}/stand-in/enable", None),
    ("POST", f"{PLUGINS}/stand-in/disable", None),
    ("POST", f"{PLUGINS}/stand-in/upgrade", {"manifest": A_MANIFEST}),
    ("POST", f"{PLUGINS}/stand-in/rollback", {"version": "1.0.0"}),
    ("POST", f"{PLUGINS}/stand-in/remove", None),
    ("POST", f"{PLUGINS}/stand-in/plan", None),
)


def call(client: TestClient, pid: str, method: str, path: str, body: Any) -> Any:
    if method == "GET":
        return get(client, pid, path)
    return post(client, pid, path, body)


@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
@pytest.mark.parametrize(("method", "path", "body"), EVERY_ROUTE)
def test_a_caller_without_the_authority_over_everything_is_refused_before_the_database(
    pid: str, method: str, path: str, body: Any
) -> None:
    """The same refusal with a database and without one, naming no capability,
    and no statement reaches a store.

    Delete this and a department-scoped holder administers plugins for the whole install, or a
    caller with nothing learns whether this process has a pool."""
    with console_client(GRANTS, database=False) as (client, _):
        without = call(client, pid, method, path, body)
    with console_client(GRANTS) as (client, stub):
        with_pool = call(client, pid, method, path, body)
    assert without.status_code == with_pool.status_code == 404
    assert without.json()["message"] == with_pool.json()["message"]
    assert PLUGIN_ADMIN.value not in with_pool.json()["message"]
    assert stub.statements == []


def test_a_password_only_sign_in_holding_the_authority_is_refused(
    served: tuple[TestClient, Stub],
) -> None:
    """`brain.gate.admission` withholds `admin:` from a session with no second factor, and the
    route asks the admitted reach rather than the grants on file.

    Delete this and a stolen password alone records a plugin on the install."""
    client, stub = served
    refused = post(client, "u_admin", PLUGINS, {"manifest": A_MANIFEST}, strong=False)
    assert refused.status_code == 404
    assert stub.statements == []


# ------------------------------------------------------------------------------ the list
def test_the_list_draws_every_extension_point_and_the_plugins_on_the_install(
    served: tuple[TestClient, Stub], registry: Registry
) -> None:
    """The register as the register states it, the six points that name an existing contract
    among them with the tier each runs at, and the records as stored.

    Delete this and the screen can omit a point, invent a tier, or draw a plugin that is not
    stored."""
    registry.rows.append(stored(A_MANIFEST, "enabled"))
    client, _ = served
    body = get(client, "u_admin", PLUGINS).json()

    by_name = {one["name"]: one for one in body["points"]}
    assert {name for name, one in by_name.items() if one["answer"] == "plugin"} == {
        one.name for one in points_answering(Answer.PLUGIN)
    }
    assert {
        name: (by_name[name]["leaf"], by_name[name]["tier"])
        for name in (
            "connector",
            "skill",
            "template",
            "model_provider",
            "field_classifier",
            "notification_sink",
        )
    } == {
        "connector": ("M29.1.2", "sidecar"),
        "skill": ("M29.1.3", "sandbox"),
        "template": ("M29.1.4", "in_process"),
        "model_provider": ("M29.1.5", "sidecar"),
        "field_classifier": ("M29.1.7", "sandbox"),
        "notification_sink": ("M29.1.12", "sidecar"),
    }
    assert [(one["plugin_id"], one["state"], one["requires"]) for one in body["plugins"]] == [
        ("stand-in", "enabled", ["read:ticket.status"])
    ]
    assert body["no_plugin_is_loaded"] is True
    assert body["registry_is_on"] is False


def test_the_list_says_the_registry_is_on_once_the_switch_is(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and the screen offers buttons the route will refuse, or hides ones it accepts."""
    settings.hold(PLUGIN_REGISTRY.key, True, value_type="boolean")
    client, _ = served
    assert get(client, "u_admin", PLUGINS).json()["registry_is_on"] is True


# ------------------------------------------------------------------------- the switch
@pytest.mark.parametrize(
    ("path", "body"),
    [
        (PLUGINS, {"manifest": A_MANIFEST}),
        (f"{PLUGINS}/stand-in/enable", None),
        (f"{PLUGINS}/stand-in/upgrade", {"manifest": A_MANIFEST}),
        (f"{PLUGINS}/stand-in/rollback", {"version": "1.0.0"}),
    ],
)
def test_the_four_writes_that_open_a_state_are_refused_while_the_switch_is_off(
    served: tuple[TestClient, Stub], settings: SettingRows, path: str, body: Any
) -> None:
    """Delete this and a feature that ships off is on for every install the day it arrives."""
    client, stub = served
    refused = post(client, "u_admin", path, body)
    assert refused.status_code == 404
    assert "switched off" in refused.json()["message"]
    assert stub.commits == 0
    assert settings.writes == []


@pytest.mark.parametrize("verb", ["disable", "remove"])
def test_the_two_writes_that_undo_a_state_never_ask_the_switch(
    served: tuple[TestClient, Stub], registry: Registry, verb: str
) -> None:
    """With the switch off and no plugin by that name, the refusal is that the plugin is not
    there, and no setting was read to decide it.

    Delete this and a plugin enabled while the switch was on cannot be turned off with it off,
    which is a stop with no way back."""
    client, stub = served
    refused = post(client, "u_admin", f"{PLUGINS}/stand-in/{verb}")
    assert refused.status_code == 404
    assert "is not on this install" in refused.json()["message"]
    assert registry.asked == 1
    assert not any(
        isinstance(one, Select)
        and [d["name"] for d in one.column_descriptions] == NAMESPACE_COLUMNS
        for one in stub.statements
    )


# ----------------------------------------------------------------- the manifest's refusals
def test_a_manifest_that_asks_for_reach_is_refused_by_the_key_it_used() -> None:
    """Delete this and a manifest carrying a grant is read as a manifest with an unknown key and
    the author is sent looking for a typo."""
    from brain.core.errors import Absent

    with pytest.raises(Absent) as refused:
        parsed({**A_MANIFEST, "grants": ["read:everything"]})
    assert "grants" in refused.value.public_message


def test_a_manifest_that_does_not_read_is_refused_without_repeating_what_was_sent() -> None:
    """Where and what: the field, and the validator's own sentence, and not the library's dump of
    the whole input.

    Delete this and a refusal quotes the entire document, including config an author pasted by
    mistake, back into a log line."""
    from brain.core.errors import Absent

    with pytest.raises(Absent) as refused:
        parsed({**A_MANIFEST, "version": "not-a-version-QQ7"})
    assert "version" in refused.value.public_message
    assert "input_value" not in refused.value.public_message
    assert "pydantic" not in refused.value.public_message


def test_a_manifest_that_reads_is_returned_as_the_model() -> None:
    """The positive half. Delete this and a `parsed` that refuses everything passes the tests
    above."""
    assert parsed(A_MANIFEST).plugin_id == "stand-in"


# ----------------------------------------------------------------------------- the plan
def test_a_plugin_is_planned_with_the_callers_own_reach_and_nothing_wider(
    served: tuple[TestClient, Stub], registry: Registry
) -> None:
    """`contract.plan_run` as the caller: the reach a plugin would be handed hashes the same as
    the caller's own.

    Delete this and the property that a plugin cannot widen entitlements has no test through a
    route."""
    registry.rows.append(stored(A_MANIFEST, "enabled"))
    client, _ = served
    answer = post(client, "u_admin", f"{PLUGINS}/stand-in/plan").json()
    assert answer == {"would_run": True, "reach_is_the_callers": True, "refusal": ""}


def test_a_plugin_needing_a_capability_the_caller_lacks_gets_the_one_refusal(
    served: tuple[TestClient, Stub], registry: Registry
) -> None:
    """Whatever the reason, one sentence, so the answer cannot enumerate the register or the
    caller's reach by difference.

    Delete this and a refusal can name the capability the caller lacks."""
    registry.rows.append(stored({**A_MANIFEST, "requires": [{"value": "read:payroll.total"}]}))
    client, _ = served
    answer = post(client, "u_admin", f"{PLUGINS}/stand-in/plan").json()
    assert answer == {
        "would_run": False,
        "reach_is_the_callers": False,
        "refusal": PLUGIN_NOT_AVAILABLE,
    }
    assert "payroll" not in str(answer)
