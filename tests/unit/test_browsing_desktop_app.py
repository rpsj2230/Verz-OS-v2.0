"""A desktop application as a target, and the sandbox it would run in.

Nothing here starts a container or a display. What is held is the product's own description of a
desktop run: that an application is declared by a name and one program under the applications
directory, that its only origin is a name that cannot resolve, that its sandbox has no member but
the runner and no route out, and that its widgets are read as the tree the enforcer already reads.
The runner that would run in it (`ops/desktop/desktop_runner.py`) is written and never run, and
the install check says so (`test_acceptance_checks_desktop.py`).

Task ids: M19.8.1
"""

from __future__ import annotations

import ast
import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from brain.browsing import desktop_app, sandbox
from brain.browsing.desktop_app import (
    COMMAND_RE,
    DESKTOP_ORIGIN_SUFFIX,
    DesktopApp,
    DesktopError,
    accessibility_tree,
    desktop_gaps,
    desktop_image_for,
    desktop_sandbox_for,
    origin_of,
    window_path,
)
from brain.browsing.sessions import BROWSE_SURFACE
from brain.browsing.targets import Surface, Verb
from brain.browsing.wire import snapshot_from_accessibility
from brain.ops.features_declared.desktop_runs import DESKTOP_RUNS

NAME = "notes_app"
COMMAND = "/opt/desktop-apps/notes/notes"
ORIGIN = "https://notes-app.desktop.invalid"
RUNNER = Path(__file__).resolve().parents[2] / "ops" / "desktop" / "desktop_runner.py"


def window(name: str = "main", origin: str = ORIGIN) -> Surface:
    return Surface(
        name=name,
        origin=origin,
        path=f"/{name}",
        verbs=frozenset({Verb.OPEN, Verb.READ}),
        capability=BROWSE_SURFACE,
        reads=("title",),
    )


def app(**changed: Any) -> DesktopApp:
    base: dict[str, Any] = {"name": NAME, "command": COMMAND, "windows": (window(),)}
    base.update(changed)
    return DesktopApp(**base)


def box(run_id: str = "r1") -> desktop_app.DesktopSandbox:
    return desktop_sandbox_for(run_id, app=app(), app_image="app:1")


def with_host(planted: desktop_app.DesktopSandbox, **host: Any) -> desktop_app.DesktopSandbox:
    body = dict(planted.runner.body)
    body["HostConfig"] = {**body["HostConfig"], **host}
    return replace(planted, runner=replace(planted.runner, body=body))


def with_body(planted: desktop_app.DesktopSandbox, **keys: Any) -> desktop_app.DesktopSandbox:
    return replace(planted, runner=replace(planted.runner, body={**planted.runner.body, **keys}))


# ------------------------------------------------------------------ the application is a target
def test_a_declared_application_becomes_a_target_whose_only_origin_is_its_own() -> None:
    """The positive case, and the property the whole reuse rests on: the browser's origin check
    admits this application and no other. Delete this and a desktop application could be given the
    origin of a website."""
    target = app().target()

    assert target.name == NAME
    assert target.origins == frozenset({ORIGIN})
    assert target.allows_origin(ORIGIN)
    assert not target.allows_origin("https://other-app.desktop.invalid")
    assert not target.allows_origin("https://example.com")


def test_an_origin_is_under_the_suffix_no_resolver_will_ever_answer() -> None:
    """RFC 6761 reserves `.invalid`, so an origin under it names an application and never a place
    on any network. Delete this and the suffix can be changed to a real domain, which turns an
    application name into an address something could answer."""
    assert DESKTOP_ORIGIN_SUFFIX.endswith(".invalid")
    assert origin_of(NAME) == ORIGIN
    assert origin_of(NAME).endswith(DESKTOP_ORIGIN_SUFFIX)


@pytest.mark.parametrize("name", ["", "Notes", "9notes", "notes app", "notes.app", "a/b"])
def test_a_name_that_is_not_a_lowercase_slug_names_no_origin(name: str) -> None:
    """The name becomes part of a host name, so it is held to the slug every target name is. Delete
    this and a name with a dot or a slash writes a different host into the origin."""
    with pytest.raises(DesktopError):
        origin_of(name)


@pytest.mark.parametrize(
    "command",
    [
        "/bin/sh",
        "notes",
        "/opt/desktop-apps/",
        "/opt/desktop-apps/../../bin/sh",
        "/opt/desktop-apps/notes/notes --evil",
        "/opt/desktop-apps/notes;reboot",
        "/opt/desktop-apps/Notes",
        "/opt/desktop-apps//notes",
    ],
)
def test_a_command_outside_the_applications_directory_is_refused_when_declared(
    command: str,
) -> None:
    """The runner launches the declared command and nothing a message names, so what the
    declaration accepts is the whole set of programs a run can start. Delete this and a path
    to a shell, a relative path or a path with arguments is declared and launched."""
    with pytest.raises(DesktopError):
        app(command=command)


def test_a_command_under_the_applications_directory_is_accepted() -> None:
    """The sibling of the refusals above. Delete this and a pattern that refuses everything passes
    them all."""
    assert COMMAND_RE.match("/opt/desktop-apps/notes/notes")
    assert COMMAND_RE.match("/opt/desktop-apps/editor-2/bin/editor.bin")
    assert app().command == COMMAND


def test_dot_dot_is_refused_even_where_the_pattern_would_let_it_through() -> None:
    """`..` is made of characters the pattern allows in a name, so the explicit refusal is what
    stops it. Delete this and a path that climbs out of the directory is declared."""
    assert COMMAND_RE.match("/opt/desktop-apps/a/../b")
    with pytest.raises(DesktopError):
        app(command="/opt/desktop-apps/a/../b")


def test_an_application_with_no_window_is_refused() -> None:
    """With no window there is nothing to operate, and a target with no surfaces would read as
    unrestricted to a careless reader. Delete this and one is declared."""
    with pytest.raises(DesktopError):
        app(windows=())


def test_a_window_on_another_origin_is_refused() -> None:
    """A window of this application on a website's origin would make the browser's origin check
    admit that website. Delete this and a declaration can name one."""
    with pytest.raises(DesktopError):
        app(windows=(window(origin="https://example.com"),))
    with pytest.raises(DesktopError):
        app(windows=(window(), window("second", "https://other-app.desktop.invalid")))


def test_a_target_the_registry_refuses_is_a_desktop_error() -> None:
    """The target constructor's refusal reaches the caller as this module's own. Delete this and a
    refusal surfaces as another module's exception and the route that declared the application
    answers a server error."""
    clash = replace(app(), windows=(window(), window()))

    with pytest.raises(DesktopError):
        clash.target()


# ------------------------------------------------------------------ an address names a window
def test_a_windows_address_names_its_path() -> None:
    """The runner raises the window an address names. Delete this and an OPEN goes to whichever
    window was last used."""
    assert window_path(f"{ORIGIN}/main") == "/main"
    assert window_path(ORIGIN) == "/"


@pytest.mark.parametrize(
    "address",
    ["https://example.com/main", "http://notes-app.desktop.invalid/main", "file:///etc/passwd", ""],
)
def test_an_address_that_is_not_a_desktop_application_names_no_window(address: str) -> None:
    """Delete this and an open of a website reaches the runner as a window to raise."""
    with pytest.raises(DesktopError):
        window_path(address)


# ------------------------------------------------------------------ the sandbox
def test_a_desktop_sandbox_built_from_a_declaration_has_no_gaps() -> None:
    """The positive case for every refusal below. Delete this and a gap check that refuses
    everything passes them."""
    assert desktop_gaps(box(), app()) == ()


def test_the_network_has_no_gateway_and_no_member_but_the_runner() -> None:
    """A desktop has nowhere to go: an internal network, and one container. Delete this and a
    desktop is given a gateway or a neighbour."""
    built = box()

    assert built.network["Internal"] is True
    assert built.network["Attachable"] is False
    assert "NetworkingConfig" not in built.runner.body
    assert built.runner.body["HostConfig"]["NetworkMode"] == built.network_name


def test_two_runs_get_two_networks_and_two_containers() -> None:
    """Delete this and two runs of one application share a network, which is how one reaches the
    other."""
    first, second = box("r1"), box("r2")

    assert first.network_name != second.network_name
    assert first.runner.name != second.runner.name


def test_a_run_id_that_cannot_be_a_container_name_is_refused() -> None:
    """Delete this and a run id with a slash or a space is rewritten into a different name."""
    with pytest.raises(sandbox.SandboxError):
        desktop_sandbox_for("r 1", app=app(), app_image="app:1")


def test_the_desktop_image_is_the_release_tag_with_desktop_on_the_end() -> None:
    """The browser image is the same tag with `-browser`; a desktop is its own image, found the
    same way. Delete this and a desktop runs the browser image, which carries no display."""
    assert desktop_image_for("app:1") == "app:1-desktop"
    assert not desktop_image_for("app:1").endswith("-browser-desktop")
    assert box().runner.body["Image"] == "app:1-desktop"


def test_the_runner_starts_the_declared_program_and_names_its_origin() -> None:
    """Delete this and the command the runner is given is not the one that was declared."""
    body = box().runner.body

    assert body["Cmd"] == [desktop_app.DESKTOP_ENTRY, "--command", COMMAND]
    assert f"{desktop_app.ORIGIN_VARIABLE}={ORIGIN}" in body["Env"]
    assert body["User"] == desktop_app.DESKTOP_USER


def test_the_runner_reads_the_variable_and_the_pattern_the_sandbox_sets() -> None:
    """The runner file is outside the package, so nothing imports it to catch a renamed constant.
    Delete this and the product sets one variable name and the runner reads another."""
    imported = {
        alias.name
        for node in ast.walk(ast.parse(RUNNER.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module == "brain.browsing.desktop_app"
        for alias in node.names
    }

    assert {"ORIGIN_VARIABLE", "COMMAND_RE", "accessibility_tree", "window_path"} <= imported


@pytest.mark.parametrize(
    "plant",
    [
        lambda b: replace(b, network={**b.network, "Internal": False}),
        lambda b: replace(b, network={**b.network, "Labels": {}}),
        lambda b: with_body(b, NetworkingConfig={"EndpointsConfig": {"other": {}}}),
        lambda b: with_body(b, Env=[*b.runner.body["Env"], "HTTPS_PROXY=http://egress:3128"]),
        lambda b: with_body(b, Env=[*b.runner.body["Env"], "https_proxy=http://egress:3128"]),
        lambda b: with_body(b, Env=[*b.runner.body["Env"], "API_TOKEN=x"]),
        lambda b: with_body(b, Env=[*b.runner.body["Env"], "DB_PASSWORD=x"]),
        lambda b: with_body(b, Cmd=[desktop_app.DESKTOP_ENTRY, "--command", "/bin/sh"]),
        lambda b: with_body(b, Image="app:1"),
        lambda b: with_body(b, Image="app:1-browser"),
        lambda b: with_host(b, Runtime="runc"),
        lambda b: with_host(b, ReadonlyRootfs=False),
        lambda b: with_host(b, Privileged=True),
        lambda b: with_host(b, Binds=["/home/staff:/home/desktop"]),
        lambda b: with_body(b, Volumes={"/profile": {}}),
    ],
)
def test_each_way_out_of_a_desktop_sandbox_is_found(plant: Any) -> None:
    """One weakness per case, each against a sandbox that has none. Delete this and a gap check
    that finds nothing is indistinguishable from one that finds everything."""
    assert desktop_gaps(plant(box()), app())


def test_the_hardening_is_the_browsers_own_list_and_not_a_copy() -> None:
    """A desktop is held to the same container list a browser is, by name. Delete this and the
    two lists can drift apart until a desktop is allowed what a browser is not."""
    assert vars(desktop_app)["container_gaps"] is sandbox.container_gaps
    assert sandbox.container_gaps is sandbox._container_gaps


def test_a_second_secret_shaped_variable_is_named_in_the_finding() -> None:
    """Delete this and the gap says something happened and not what, which is a finding nobody can
    act on."""
    found = desktop_gaps(with_body(box(), Env=[*box().runner.body["Env"], "API_TOKEN=x"]), app())

    assert any("API_TOKEN" in one for one in found)


def test_the_proxy_variables_are_the_ones_that_give_a_process_somewhere_to_send() -> None:
    """Delete this and one of the four is dropped from the list and a runner given it is not
    found."""
    assert set(desktop_app.PROXY_VARIABLES) == {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }


def test_a_desktop_is_given_at_least_what_a_browser_is() -> None:
    """An X server, a window manager and an application are more than one browser. That the mounts
    fit under the memory cap is `Caps`' own refusal, at import. Delete this and the desktop's caps
    are lowered below the browser's until the application is killed for memory."""
    assert desktop_app.DESKTOP_CAPS.memory_mib >= sandbox.RUNNER_CAPS.memory_mib
    assert desktop_app.DESKTOP_CAPS.pids >= sandbox.RUNNER_CAPS.pids


# ------------------------------------------------------------------ the toolkit read as a tree
def read(entries: list[tuple[int, str, str]]) -> list[tuple[str, str, str]]:
    snap = snapshot_from_accessibility(
        accessibility_tree(entries), run_id="r1", sequence=1, origin=ORIGIN
    )
    return [(one.ref, one.role, one.name) for one in snap.nodes]


def test_a_desktops_widgets_are_read_as_the_tree_the_enforcer_reads() -> None:
    """Numbers become references, roles take the browser's spellings. Delete this and a control
    declared as a button never matches a toolkit's push button."""
    assert read([(7, "push button", "Save"), (8, "entry", "Title"), (9, "frame", "main")]) == [
        ("n7", "button", "Save"),
        ("n8", "textbox", "Title"),
        ("n9", "window", "main"),
    ]


def test_a_role_the_table_does_not_know_is_generic_and_not_a_guess() -> None:
    """A control cannot match a role by accident. Delete this and an unknown role is passed through
    spelt as the toolkit spells it, which a declared control could be written to match."""
    assert read([(3, "unheard of", "x")]) == [("n3", "generic", "x")]
    assert "generic" not in desktop_app.ROLE_NAMES.values()


def test_two_widgets_are_two_references_and_the_same_number_is_the_same_reference() -> None:
    """The runner numbers a widget once. Delete this and a re-read of the same widget gives it a
    new reference, and a click on the old one is refused as unknown for ever."""
    first = read([(1, "push button", "A"), (2, "push button", "A")])
    again = read([(1, "push button", "A")])

    assert [one[0] for one in first] == ["n1", "n2"]
    assert again[0][0] == "n1"


def test_an_editable_widget_is_one_a_picture_paints_over() -> None:
    """The set of roles a picture must mask is the editable ones. Delete this and a password entry
    is left out of it."""
    assert {"entry", "password text", "text"} <= desktop_app.MASKED_ROLES
    assert not {"push button", "label"} & desktop_app.MASKED_ROLES


# ------------------------------------------------------------------ the switch
def test_the_switch_is_named_and_names_the_reader_that_asks() -> None:
    """That it ships off is `test_features.py`'s to say. Delete this and the switch names a reader
    that does not exist, which `feature_gaps` would report but only against a whole tree."""
    assert DESKTOP_RUNS.name == "desktop_runs"
    assert DESKTOP_RUNS.read_by == ("brain.browsing.desktop_app:desktop_runs_are_on",)


def test_the_reader_asks_the_switch_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete this and the reader answers yes whatever the install chose."""
    asked: list[object] = []

    async def is_on(session: object, one: object) -> bool:
        asked.append(one)
        return False

    monkeypatch.setattr(desktop_app, "is_on", is_on)

    assert asyncio.run(desktop_app.desktop_runs_are_on(object())) is False  # type: ignore[arg-type]
    assert asked == [DESKTOP_RUNS]
