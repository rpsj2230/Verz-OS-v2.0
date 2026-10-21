"""A desktop application an agent may operate, and the sandbox it is operated in.

M19.8.1 asks for an agent to operate an allowlisted desktop application inside an isolated virtual
desktop, every action recorded, every write held for a person, and no route to any other
application or network. **This module is the part of that which is a decision**, and it decides
it by reusing what the browser already decides rather than by writing a second set of rules.

**A desktop application is a target.** Its windows are surfaces, its buttons and fields are
controls a person declared (`brain.browsing.targets.Control`), its snapshot is the accessibility
tree the desktop toolkit gives (the same shape Chromium gives), and its one origin is
`https://<name>.desktop.invalid`: a name under a reserved suffix that cannot resolve, so the one
origin check every action already passes (`enforcer.authorise`) admits this application and no
other, and the proxy that admits origins is not needed because **there is no proxy and no network**.
So the envelope, its approval, the enforcer, the recording, the session limits and the halt are the
browser's own and not repeated here. A write is a click, a type or a submit, which the targets
module already counts as a write and the envelope already holds for a person.

**What is different is the sandbox, and it is stricter.** A browser run has a network with a proxy
as its one member that reaches out. A desktop run has a network with **no other member at all**: the
Engine's internal network gives it no gateway, and nothing is connected to it but the runner. The
rest of the hardening is `brain.browsing.sandbox.container_gaps` unchanged (gVisor, a read-only
root, tmpfs only, no capability, no bind, no device, caps), so a desktop container is held to the
list a browser container is held to, plus the four things that are about being a desktop: no
proxy variable (there is nowhere to send a request), no second network, exactly the declared
command as what starts, and an image of its own.

**The command is declared, absolute, and inside the image's applications directory.** The runner
launches the declared command and nothing a snapshot or an instruction names, so what a page, a
document or a model says cannot start another program. It is refused when it is declared, not when
a launch fails.

**It is not offered, and `DESKTOP_RUNNER_MODULE` is not this module.** The Profile says computer use
is not offered until an isolated desktop runner is part of the product
(`brain.console.agent_behaviour`). The launcher creating this sandbox and the driver sending a run
to it are not built, so this module is named for what it is (an application and its sandbox) and the
runner module the Profile looks for does not exist yet; the day it does, that sentence changes by
itself, which is the point of asking the import machinery.

Rejected: a keyboard and a pointer for the whole desktop with an application "focused", which makes
the allowlist a suggestion; a desktop with the network on and a proxy in front, which is the browser
sandbox with a larger attack surface and an argument for each address; and a screenshot-driven
actor, which is `brain.browsing.observation`'s refusal for the same reason as the browser's.

Not built, and stated: the launcher creating this sandbox, the driver relaying a desktop run, the
runner image's behaviour on a host (`ops/desktop/`), and so no run has happened. The install check
says so in a sentence rather than passing on bodies alone.

Task ids: M19.8.1
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from brain.browsing.sandbox import (
    CONTAINER_TMP,
    ROLE_LABEL,
    RUN_ID_RE,
    RUN_LABEL,
    SECRET_SHAPED_ENV,
    Caps,
    Container,
    SandboxError,
    _host_config,
    container_gaps,
    runner_image_for,
)
from brain.browsing.targets import NAME_RE, Surface, Target, TargetError
from brain.ops.features import is_on
from brain.ops.features_declared.desktop_runs import DESKTOP_RUNS

#: The reserved suffix every desktop application's origin ends in. `.invalid` is never resolvable
#: (RFC 6761), so an origin under it names an application and not a place on any network.
DESKTOP_ORIGIN_SUFFIX: Final = ".desktop.invalid"

#: Where the runner image keeps the applications an install may declare. A declared command is a
#: path under it, so a program outside the image's own directory cannot be started.
APPLICATIONS_DIRECTORY: Final = "/opt/desktop-apps/"

#: A declared command: absolute, inside `APPLICATIONS_DIRECTORY`, with no `..` and no shell syntax.
COMMAND_RE: Final = re.compile(r"^/opt/desktop-apps/[a-z0-9_-]+(?:/[a-z0-9_.-]+)*$")

#: What a desktop image is called beside the application image it is built with.
DESKTOP_TAG_SUFFIX: Final = "-desktop"

#: The user the desktop runner runs as, and the file that starts it in the image.
DESKTOP_USER: Final = "desktop"
DESKTOP_ENTRY: Final = "/opt/desktop-runner/desktop_runner.py"

#: The variable that tells the runner which origin its one application is addressed by.
ORIGIN_VARIABLE: Final = "DESKTOP_APP_ORIGIN"

#: The display the virtual desktop is on, inside the container only.
VIRTUAL_DISPLAY: Final = ":99"

#: The caps for one virtual desktop. Larger than a browser's: an X server, a window manager and an
#: application. Judged, not measured, like `sandbox.RUNNER_CAPS`; the tmpfs and shared memory are
#: held under the cap by `Caps` itself.
DESKTOP_CAPS: Final = Caps(
    memory_mib=1536,
    millicpus=1000,
    pids=512,
    tmpfs=((CONTAINER_TMP, 128), (f"/home/{DESKTOP_USER}", 256)),
    shm_mib=256,
    floor_mib=768,
)

#: Variables that would give the runner somewhere to send a request.
PROXY_VARIABLES: Final = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")

#: Why there is no proxy and no network.
A_DESKTOP_HAS_NOWHERE_TO_GO: Final = (
    "A browser needs the internet to do its work, so it is given one proxy that checks every "
    "address. A desktop application the install allowlisted needs nothing outside its own window, "
    "so it is given nothing: a network with no gateway and no other member, no proxy variable, no "
    "resolver beyond the container. What cannot be reached cannot be told to do something, and "
    "there is no address list to get wrong."
)


class DesktopError(Exception):
    """A desktop application was declared in a way that cannot be made safe."""


def origin_of(name: str) -> str:
    """The origin a desktop application is addressed by, from its name."""
    if not NAME_RE.match(name):
        msg = f"desktop application name {name!r} is not a lowercase slug"
        raise DesktopError(msg)
    return f"https://{name.replace('_', '-')}{DESKTOP_ORIGIN_SUFFIX}"


@dataclass(frozen=True)
class DesktopApp:
    """One application an install allows, its windows and the one program that starts it."""

    name: str
    command: str
    windows: tuple[Surface, ...]

    def __post_init__(self) -> None:
        origin = origin_of(self.name)
        if not COMMAND_RE.match(self.command) or ".." in self.command:
            msg = (
                f"command {self.command!r} is not a path under {APPLICATIONS_DIRECTORY}, so the "
                "runner could be told to start a program the image does not carry for this"
            )
            raise DesktopError(msg)
        if not self.windows:
            msg = f"desktop application {self.name!r} declares no window, so nothing to operate"
            raise DesktopError(msg)
        for window in self.windows:
            if window.origin != origin:
                msg = (
                    f"window {window.name!r} of {self.name!r} sits on {window.origin!r}, and a "
                    f"desktop application's windows sit on {origin!r} and nowhere else"
                )
                raise DesktopError(msg)

    @property
    def origin(self) -> str:
        return origin_of(self.name)

    def target(self) -> Target:
        """The application as a target, so every rule that governs a browser target governs it."""
        try:
            return Target(name=self.name, origins=frozenset({self.origin}), surfaces=self.windows)
        except TargetError as refused:
            raise DesktopError(str(refused)) from None


def desktop_image_for(app_image: str) -> str:
    """The desktop runner image built with this release, found by its tag as the browser's is."""
    return runner_image_for(app_image).removesuffix("-browser") + DESKTOP_TAG_SUFFIX


@dataclass(frozen=True)
class DesktopSandbox:
    """One desktop run: its network, which has no other member, and its one container."""

    run_id: str
    network: dict[str, Any]
    runner: Container
    command: str

    @property
    def network_name(self) -> str:
        return str(self.network["Name"])


def desktop_sandbox_for(run_id: str, *, app: DesktopApp, app_image: str) -> DesktopSandbox:
    """The network and container for one desktop run, built and not yet created."""
    if not RUN_ID_RE.match(run_id):
        msg = f"run id {run_id!r} cannot name a container without being rewritten"
        raise SandboxError(msg)
    name = f"brain-desktop-{run_id}"
    network = {
        "Name": name,
        "Driver": "bridge",
        "Internal": True,
        "Attachable": False,
        "Labels": {RUN_LABEL: run_id},
    }
    runner = Container(
        name=f"{name}-runner",
        body={
            "Image": desktop_image_for(app_image),
            "User": DESKTOP_USER,
            "Entrypoint": ["python"],
            "Cmd": [DESKTOP_ENTRY, "--command", app.command],
            "Env": [
                f"DISPLAY={VIRTUAL_DISPLAY}",
                f"{ORIGIN_VARIABLE}={app.origin}",
                f"HOME=/home/{DESKTOP_USER}",
                "PYTHONUNBUFFERED=1",
            ],
            "Labels": {RUN_LABEL: run_id, ROLE_LABEL: "desktop"},
            "AttachStdin": True,
            "AttachStdout": True,
            "AttachStderr": False,
            "OpenStdin": True,
            "StdinOnce": True,
            "Tty": False,
            "HostConfig": _host_config(DESKTOP_CAPS, name),
        },
    )
    return DesktopSandbox(run_id=run_id, network=network, runner=runner, command=app.command)


def desktop_gaps(box: DesktopSandbox, app: DesktopApp) -> tuple[str, ...]:
    """Every way these bodies would let a desktop run reach, keep or leave something."""
    gaps: list[str] = []
    name = box.network_name
    if box.network.get("Internal") is not True:
        gaps.append(f"network {name} is not internal, so the desktop has a route out")
    if box.network.get("Labels", {}).get(RUN_LABEL) != box.run_id:
        gaps.append(f"network {name} is not labelled with its run, so no sweep would find it")
    gaps.extend(container_gaps("desktop", box.runner, DESKTOP_CAPS, name, box.run_id))
    body = box.runner.body
    if body.get("NetworkingConfig"):
        gaps.append("the desktop joins a network beyond its run's own")
    environment = [str(one) for one in body.get("Env", [])]
    for entry in environment:
        variable = entry.split("=", 1)[0].upper()
        if variable in PROXY_VARIABLES:
            gaps.append(f"the desktop is given {variable}, so it has somewhere to send a request")
        if any(shape in variable for shape in SECRET_SHAPED_ENV):
            gaps.append(f"the desktop's environment carries {variable}, which it must never hold")
    if body.get("Cmd") != [DESKTOP_ENTRY, "--command", app.command]:
        gaps.append("the desktop starts something other than the declared program")
    if body.get("Image") != desktop_image_for(_application_image(box)):
        gaps.append("the desktop does not run the desktop image of this release")
    return tuple(gaps)


def _application_image(box: DesktopSandbox) -> str:
    """The application image the desktop image was derived from, read back off the body."""
    image = str(box.runner.body.get("Image", ""))
    return image.removesuffix(DESKTOP_TAG_SUFFIX)


#: How the desktop toolkit's accessibility roles are spelt in the tree the rest of the pipeline
#: reads, which is the browser's. A control a person declared by role and name
#: (`targets.Control`) is matched against these spellings, so the table is the vocabulary a desktop
#: application is declared in. A role not in it is `GENERIC_ROLE`: it can be read, and a declared
#: control cannot match it by accident.
ROLE_NAMES: Final[Mapping[str, str]] = {
    "push button": "button",
    "toggle button": "button",
    "check box": "checkbox",
    "radio button": "radio",
    "entry": "textbox",
    "text": "textbox",
    "password text": "textbox",
    "combo box": "combobox",
    "menu item": "menuitem",
    "label": "text",
    "link": "link",
    "list item": "listitem",
    "page tab": "tab",
    "frame": "window",
    "dialog": "dialog",
}

#: What a role the table does not know becomes.
GENERIC_ROLE: Final = "generic"

#: The roles whose contents a picture must paint over, as the toolkit spells them.
MASKED_ROLES: Final = frozenset({"entry", "text", "password text", "combo box"})


def window_path(address: str) -> str:
    """The window a desktop address names: the path of an address under a desktop origin."""
    parsed = urlsplit(address)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host.endswith(DESKTOP_ORIGIN_SUFFIX):
        msg = f"{address!r} is not an address of a desktop application"
        raise DesktopError(msg)
    return parsed.path or "/"


def accessibility_tree(entries: Sequence[tuple[int, str, str]]) -> dict[str, Any]:
    """The toolkit's nodes, as the accessibility tree `wire.snapshot_from_accessibility` reads.

    Each entry is a number the runner assigned to one widget for as long as it exists, the
    toolkit's role and the widget's name. The number plays the part of a backend node id: **it is
    held by the runner and not by the application**, so an application that replaces a button
    under a reference produces a widget with a new number, and the old reference is an unknown
    one, which is the browser's own protection carried across.
    """
    nodes: list[dict[str, Any]] = []
    for number, role, name in entries:
        nodes.append(
            {
                "nodeId": str(number),
                "backendDOMNodeId": number,
                "ignored": False,
                "role": {"type": "role", "value": ROLE_NAMES.get(role, GENERIC_ROLE)},
                "name": {"type": "computedString", "value": name},
            }
        )
    return {"nodes": nodes}


async def desktop_runs_are_on(session: AsyncSession) -> bool:
    """Whether this install has switched desktop runs on. Off until an administrator does."""
    return await is_on(session, DESKTOP_RUNS)
