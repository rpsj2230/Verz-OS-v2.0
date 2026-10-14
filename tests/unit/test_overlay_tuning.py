"""The model server is one overlay among the others, and its limit is the install's own choice.

`brain.ops.overlays` already holds the one costing for every optional service (`plan_in_room`) and
the Settings screen already refuses a list that would not all start in the room the server last
measured (`memory_problem`). These tests hold that the model server goes through that costing and
no other: charged at the figure its install's settings give, refused alone when what its settings
choose cannot be started, handed its variables as `ENV` lines, and judged at save with the settings
as they would then stand.

Every figure is a fixture of a host that does not exist, never anybody's.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from brain.ops import overlays, setting_store
from brain.ops.model_server import config_from, effective_limit_mib, environment
from brain.ops.overlays import (
    BY_NAME,
    OVERLAYS,
    ROOM_KEY,
    Host,
    Tuned,
    memory_problem,
    plan,
    plan_in_room,
    planned,
    render,
    switched_on,
    tuned_for,
)
from brain.ops.wiring import HOST_RESERVE_MIB, component
from tests.unit import test_overlays as harness

SERVER = BY_NAME["modelserver"]
PRESIDIO = BY_NAME["presidio"]
FLOOR = sum(one.cost_mib for one in OVERLAYS if one.always)
EVERY_RUNTIME = frozenset({"runc"})


def tuned(**settings: str) -> Tuned:
    return tuned_for("modelserver", {f"INSTALL_MODEL_{k.upper()}": v for k, v in settings.items()})


def test_the_model_server_is_an_optional_overlay_in_the_registry_everyone_else_uses() -> None:
    """One registry and one word: `modelserver` in `INSTALL_SERVICES` switches it on, it is costed
    from a component `brain.ops.wiring` budgets, it is in no profile, and it comes after the
    detector in the order item 120 gave the room.

    Delete this and the server is a second mechanism for starting a service, or a service the
    setting does not name."""
    assert switched_on("modelserver") == (SERVER,)
    assert SERVER.components == ("inference-server",)
    assert SERVER.files == ("docker-compose.inference.yml",)
    assert SERVER.prepare == ("modelserver.prepare.sh",)
    assert component("inference-server").profiles == frozenset()
    names = [one.name for one in OVERLAYS]
    assert names.index("presidio") < names.index("modelserver") < names.index("langfuse")


def test_nothing_but_the_model_server_is_tuned_so_every_other_plan_is_exactly_what_it_was() -> None:
    """The other overlays answer with nothing, which is what keeps their plans byte for byte
    unchanged. Delete this and the detector's cost starts to depend on the model server."""
    for one in OVERLAYS:
        if one.name != "modelserver":
            assert tuned_for(one.name, {"INSTALL_MODEL_PARTS": "layout"}) == Tuned()


def test_the_default_choice_is_charged_the_budgets_own_row_and_a_larger_choice_more() -> None:
    """The plan charges the install's figure and not the row's: the default choice is the row, and
    choosing the layout part charges what `brain.ops.model_server` says it needs.

    Delete this and every install is charged 1,088 MiB whatever it chose, which is the fixed
    figure this design replaced."""
    default = plan_in_room((SERVER,), 10_000, EVERY_RUNTIME, {"modelserver": tuned()})
    layout = plan_in_room((SERVER,), 10_000, EVERY_RUNTIME, {"modelserver": tuned(parts="layout")})

    assert default.costs["modelserver"] == component("inference-server").memory_mib
    assert layout.costs["modelserver"] == effective_limit_mib(config_from(parts="layout"))
    assert layout.costs["modelserver"] > default.costs["modelserver"]


def test_a_choice_that_fits_the_room_starts_and_one_a_mebibyte_over_it_is_refused_in_words() -> (
    None
):
    """At the line, both ways: the room that holds the default exactly starts it, and one a
    mebibyte less names the shortfall in the plan's own sentence. The same room refuses a larger
    choice the default would have fitted in.

    Delete this and a choice larger than the room is started, or one that fits is refused."""
    cost = effective_limit_mib(config_from())
    fitting = plan_in_room((SERVER,), cost, EVERY_RUNTIME, {"modelserver": tuned()})
    assert [one.name for one in fitting.start] == ["modelserver"] and not fitting.refused

    short = plan_in_room((SERVER,), cost - 1, EVERY_RUNTIME, {"modelserver": tuned()})
    [(one, why)] = short.refused
    assert one is SERVER and not short.start
    assert f"needs {cost} MiB and this server has {cost - 1} MiB left for it" in why

    larger = plan_in_room((SERVER,), cost, EVERY_RUNTIME, {"modelserver": tuned(parts="layout")})
    assert larger.refused and not larger.start


def test_without_any_tuning_the_plan_charges_the_budgets_row_as_it_always_did() -> None:
    """`tuning` is optional and absent means the row, so a caller that does not know about it, and
    every plan made before it existed, is costed as before.

    Delete this and the new parameter is a required one every older caller breaks on."""
    host = Host(total_mib=10_000 + HOST_RESERVE_MIB, reserved_mib=0, unlimited_used_mib=0)

    assert plan((SERVER,), host).costs == {"modelserver": component("inference-server").memory_mib}


def test_a_choice_that_cannot_be_started_refuses_the_model_server_alone() -> None:
    """The typo that must not take the detector away: a limit set under what the parts need is the
    server's problem and the detector is planned and started as if it had not been named. The
    server's refusal says why in the configuration's own words.

    Delete this and one mistyped setting stops every optional service."""
    broken = tuned(parts="layout", memory_mib="100")
    result = plan_in_room(
        (PRESIDIO, SERVER), 20_000, EVERY_RUNTIME, {"presidio": Tuned(), "modelserver": broken}
    )

    assert [one.name for one in result.start] == ["presidio"]
    [(one, why)] = result.refused
    assert one is SERVER and "is not started" in why and "layout" in why
    assert broken.problem and not broken.limits and not broken.environment


def test_a_setting_that_is_not_a_configuration_is_a_refusal_in_words_and_not_a_crash() -> None:
    """Every way the four can be wrong reaches the plan as a sentence, so the plan is made and the
    others start. Delete this and the first one raises out of the planner, which then stops
    nothing and starts nothing for the whole server."""
    for settings in (
        {"parts": "nonsense"},
        {"idle_seconds": "soon"},
        {"upload_mb": "0"},
        {"memory_mib": "tiny"},
    ):
        assert tuned(**settings).problem, settings


def test_the_variables_are_handed_over_as_env_lines_before_the_preparation_that_needs_them() -> (
    None
):
    """The step exports each `ENV` line as it reads it, and the weights fetch is told the parts by
    that export, so the line must come first. Asserted on the lines, in order, for the one overlay
    that has any, and absent for every other.

    Delete this and the fetch runs without knowing which parts were chosen."""
    host = Host(total_mib=10_000 + HOST_RESERVE_MIB, reserved_mib=0, unlimited_used_mib=0)
    tuning = {"presidio": Tuned(), "modelserver": tuned(parts="embedding,ocr")}
    lines = render(plan(planned((PRESIDIO, SERVER)), host, tuning), host).splitlines()

    start = lines.index("START modelserver")
    own = lines[start : start + 12]
    env = [one for one in own if one.startswith("ENV ")]
    assert env == [
        f"ENV {key}={value}" for key, value in environment(config_from(parts="embedding,ocr"))
    ]
    assert lines.index(env[0]) < lines.index("PREPARE modelserver.prepare.sh")
    assert not [one for one in lines[: lines.index("START modelserver")] if one.startswith("ENV ")]
    assert all(re.fullmatch(r"ENV [A-Z_]+=[A-Za-z0-9_,]+", one) for one in env)


# ------------------------------------------------------------------ the save check
class _Row:
    def __init__(self, value: object) -> None:
        self.value = value


def _asked(
    monkeypatch: pytest.MonkeyPatch, services: str, room: int | None, saved: dict[str, str]
) -> str:
    async def held(session: object, namespace: str) -> dict[str, object]:
        assert namespace == "overlay"
        return {} if room is None else {ROOM_KEY: _Row({"available_mib": room, "total_mib": 1})}

    monkeypatch.setattr(setting_store, "read_namespace", held)
    return asyncio.run(memory_problem(object(), services, saved))  # type: ignore[arg-type]


def test_a_save_is_judged_with_the_model_settings_as_they_would_then_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same room, the same services, and two sets of settings: the default fits and the layout
    part does not. The check reads the settings it is handed and not the ones saved so far, because
    the question is whether the result of this save fits.

    Delete this and a person is allowed to choose a part that the next release then drops."""
    room = FLOOR + effective_limit_mib(config_from())

    assert _asked(monkeypatch, "modelserver", room, {}) == ""
    short = _asked(monkeypatch, "modelserver", room, {"INSTALL_MODEL_PARTS": "layout"})
    assert short.startswith(overlays.NOT_ALL_OF_THESE_FIT_ON_THIS_SERVER)
    assert "(modelserver)" in short


def test_with_no_measurement_a_save_is_allowed_and_the_deploy_decides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refusing on a guess would block the first switch-on of every install, so nothing measured is
    nothing refused, whatever was chosen.

    Delete this and the first install to choose the model server cannot save the choice."""
    assert _asked(monkeypatch, "modelserver", None, {"INSTALL_MODEL_PARTS": EVERYTHING}) == ""


EVERYTHING = "embedding,layout,ocr,tika,entities"


def test_the_settings_route_asks_the_one_costing_for_each_of_the_four_and_for_the_services() -> (
    None
):
    """The route judges a save of `INSTALL_SERVICES` and of each model setting through
    `memory_problem` with the candidate settings, and through nothing of its own. Parsed from the
    source, so a comment cannot satisfy it.

    Delete this and the route can stop asking, and a model setting is saved without any memory
    check while the services setting still has one."""
    import ast

    source = (harness.REPO / "src" / "brain" / "settings_routes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    save = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "save_setting"
    )
    calls = [
        n
        for n in ast.walk(save)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "memory_problem"
    ]
    assert len(calls) == 1
    keywords = {k.arg for k in calls[0].keywords}
    assert "saved" in keywords or len(calls[0].args) == 3
    guarded = [
        n
        for n in ast.walk(save)
        if isinstance(n, ast.Name) and n.id in {"SERVICES_SETTING", "MODEL_SERVER_SETTINGS"}
    ]
    assert {n.id for n in guarded} == {"SERVICES_SETTING", "MODEL_SERVER_SETTINGS"}


# ------------------------------------------------------------------ the step, run for real
@harness.pytestmark_sh
def test_the_step_exports_the_plans_variables_and_names_the_image_from_the_applications_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What reaches compose: the memory limit and the parts the plan computed, and an image named
    from the application's (the same repository with `-modelserver` on its name and the same tag).
    The fetch that runs before it is handed the parts too, and docker is asked to start the one
    file.

    Delete this and the server is started at the compose file's defaults whatever the install
    chose, or with no image at all."""
    image = '        *Config.Image*) echo "registry.example/brain:abc123" ;;'
    stub = harness.STUB.replace(
        '*compose.project*) echo "$2" ;;',
        f'*compose.project*) echo "$2" ;;\n{image}',
    ).replace(
        "  compose)\n",
        '  compose)\n    echo "$INFERENCE_MEMORY_MIB $INFERENCE_PARTS ${INFERENCE_IMAGE:-none}"'
        ' >> "$S/composeenv"\n',
    )
    monkeypatch.setattr(harness, "STUB", stub)
    host = Host(total_mib=10_000 + HOST_RESERVE_MIB, reserved_mib=0, unlimited_used_mib=0)
    chosen = tuned(parts="embedding,ocr")
    planned_text = render(plan((SERVER,), host, {"modelserver": chosen}), host)

    ran = harness.apply(tmp_path, planned=planned_text)

    assert ran.code == 0, ran.output
    asked = (tmp_path / "state" / "composeenv").read_text(encoding="utf-8").splitlines()
    limit = effective_limit_mib(config_from(parts="embedding,ocr"))
    assert asked and all(
        line == f"{limit} embedding,ocr registry.example/brain-modelserver:abc123" for line in asked
    ), asked
    assert any("docker-compose.inference.yml" in call for call in ran.calls)
    assert any(
        call.startswith("run ") and "inference_server.fetch embedding ocr" in call
        for call in ran.calls
    )
