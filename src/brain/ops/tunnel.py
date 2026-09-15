"""The Cloudflare Tunnel option, held to the overlay file and to the page that explains it.

A client may expose the console through a Cloudflare Tunnel instead of opening 80 and 443 to
a reverse proxy. The tunnel container dials out to Cloudflare and carries requests back over
that connection, so the server needs no inbound port at all. `docker-compose.tunnel.yml` is
the option and `docs/install/network.md` is how a person uses it.

**Why an overlay and not a service in the base file.** The obvious shape is one more service
in `docker-compose.yml` behind a compose profile, switched on per install. Compose interpolates
the whole file before it filters by profile, so a `${CLOUDFLARE_TUNNEL_TOKEN:?...}` on a
service nobody switched on still refuses to start every install that did not set it. Making the
token optional instead is the one thing this option must not do: see
`A_TUNNEL_WITH_NO_CREDENTIAL_REFUSES_TO_START`. A separate file is the only shape in which the
token is required exactly where it is used.

**Why no port has to be taken away.** Compose cannot remove a `ports` entry from an overlay,
so if any profile published a port, this option would need every base file to bind it to the
loopback address. None does, which `brain.deployment.requirements.published_ports` already
reports for every profile, so the overlay only adds and the base files stay untouched.

**Why a token and not a tunnel configured by file.** A locally configured tunnel reads a
credentials file and an ingress list from a mount. The mount is the failure
`brain.ops.compose.A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE` describes, and the
ingress list names the client's own addresses, which would be a client value in a file this
repository ships. With a token the addresses live in the client's own Cloudflare account and
the file carries nothing about them.

**What the option does not do, stated so nobody reads it as done.**

- `brain.deployment.release.INCLUDED` carries only the compose files some profile composes, so
  a release archive does not contain this overlay, and the update script composes the profile's
  files without it. `THE_RELEASE_DOES_NOT_CARRY_THE_OVERLAY` is pinned by a test that fails
  on the day that changes.
- The identity provider on `standard` and `full` sits on the deployment panel's proxy network
  and not on `default`, so this tunnel reaches the console and not the sign-in page. See
  `THE_TUNNEL_REACHES_THE_CONSOLE_AND_NOT_THE_IDENTITY_PROVIDER`.
- No tunnel has ever been started from this file.

Task ids: M30.1.3
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

#: The overlay, by the name an operator passes with `-f`.
OVERLAY: Final = "docker-compose.tunnel.yml"

#: The one service the overlay declares.
SERVICE: Final = "cloudflared"

#: The image repository the service runs.
IMAGE_REPOSITORY: Final = "cloudflare/cloudflared"

#: The environment name cloudflared reads its token from when `--token` is not given.
CREDENTIAL_SETTING: Final = "TUNNEL_TOKEN"

#: The command after the image's own entrypoint, which already carries `--no-autoupdate`.
COMMAND: Final[tuple[str, ...]] = ("tunnel", "run")

#: The service the tunnel's public hostname points at, and the port it listens on.
APPLICATION_SERVICE: Final = "app"
APPLICATION_PORT: Final = 8000

#: The port cloudflared dials out to Cloudflare on. An outbound rule, never an inbound one.
EDGE_PORT: Final = 7844

#: The network guide's section for this option, as its level-two heading reads.
SECTION_HEADING: Final = "Cloudflare Tunnel instead of opening 80 and 443"

#: Cloudflare's release tags are calendar versions. `latest`, a build id and an
#: architecture-suffixed tag are all published beside them and are all refused: the first moves,
#: the second is not a release, and the third runs on one kind of server only.
RELEASE_TAG: Final = re.compile(r"\A\d{4}\.\d{1,2}\.\d+\Z")

#: `${NAME:?message}`, which refuses to start when NAME is unset or empty.
REQUIRED_VARIABLE: Final = re.compile(r"\A\$\{([A-Z][A-Z0-9_]*):\?[^}]+\}\Z")

#: A level-two heading in the network guide.
LEVEL_TWO: Final = re.compile(r"^##\s+(.+?)\s*$", re.M)

A_TUNNEL_PUBLISHES_NOTHING: Final = (
    "The tunnel dials out and carries requests back over its own connection, so it has nothing "
    "to listen on. A `ports` entry on it opens an inbound port on the server, which is the one "
    "thing the option exists to avoid, and `network_mode` would put its listeners on the host's "
    "interfaces rather than inside the compose network."
)

A_MOVING_TAG_IS_A_DIFFERENT_BINARY_HOLDING_THE_CREDENTIAL: Final = (
    "The tunnel container holds the credential that decides which server a public address "
    "reaches. An image on `latest`, or on no tag, is whatever was published on the day it was "
    "pulled, so two servers on one release run two different programs with that credential."
)

A_TUNNEL_WITH_NO_CREDENTIAL_REFUSES_TO_START: Final = (
    "The token has to be required in the `${NAME:?message}` form. A bare `${NAME}` or a default "
    "starts the stack with an empty or shared token, which is a tunnel that fails in a restart "
    "loop at best and one connected to somebody else's account at worst."
)

THE_CREDENTIAL_IS_NOT_ON_THE_COMMAND_LINE: Final = (
    "cloudflared reads the token from TUNNEL_TOKEN. Passed as `--token` it sits in the process "
    "list, which every user on the host can read. The image's entrypoint is kept because it "
    "carries `--no-autoupdate`, and a replaced entrypoint drops it."
)

THE_TUNNEL_STAYS_OFF_THE_CANVAS_NETWORK: Final = (
    "The tunnel joins `default`, which reaches the application, and nothing else. `tool-api` is "
    "the automation canvas's only route to this application, so a tunnel on it is a service an "
    "assembled flow can reach."
)

THE_TUNNEL_WAITS_FOR_THE_APPLICATION: Final = (
    "The tunnel depends on the application being healthy, so it carries no request to a "
    "container that is still migrating, and cannot be composed onto a set with no application."
)

THE_EDGE_TERMINATES_TLS_AND_READS_EVERY_REQUEST: Final = (
    "Cloudflare holds the certificate and decrypts every request at its edge before the tunnel "
    "carries it on. Every question a member of staff asks and every answer this system gives "
    "passes through Cloudflare in the clear, which a reverse proxy on the client's own server "
    "does not do. That is a decision for the client, and the network guide says so first."
)

THE_RELEASE_DOES_NOT_CARRY_THE_OVERLAY: Final = (
    "The release archive is derived from the compose files each profile composes, and no "
    "profile composes the tunnel. An install from a release therefore has no overlay on disk, "
    "and the update script brings the stack up without it. Until the archive includes it, the "
    "file is copied onto the server by hand and the tunnel is started again after every update."
)

THE_TUNNEL_REACHES_THE_CONSOLE_AND_NOT_THE_IDENTITY_PROVIDER: Final = (
    "On `standard` and `full` the identity provider joins the deployment panel's proxy network "
    "and its own internal one, never `default`. The tunnel joins `default` only, because joining "
    "an external network that exists only where the panel runs would stop `lite` starting at "
    "all. So through this overlay the sign-in page is unreachable, and the option is complete "
    "for `lite` alone."
)


def _names(value: object) -> set[str]:
    """Service or network names from either compose spelling, a list or a mapping."""
    if isinstance(value, Mapping):
        return {str(one) for one in value}
    if isinstance(value, list):
        return {str(one) for one in value}
    return set()


def token_variable(document: Mapping[str, Any]) -> str | None:
    """The variable the overlay requires for the token, or None when it requires none."""
    services = document.get("services")
    body = services.get(SERVICE) if isinstance(services, Mapping) else None
    environment = body.get("environment") if isinstance(body, Mapping) else None
    if not isinstance(environment, Mapping):
        return None
    matched = REQUIRED_VARIABLE.match(str(environment.get(CREDENTIAL_SETTING, "")))
    return matched.group(1) if matched else None


def overlay_gaps(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Every way this overlay fails to be a pinned tunnel with no inbound port, in file order.

    Empty for the file as written. Each finding names the rule it breaks, so the test that
    builds a broken copy asserts which rule caught it rather than that something did.
    """
    services = document.get("services")
    if not isinstance(services, Mapping):
        return (f"{OVERLAY} declares no services, so there is no tunnel to check",)
    found: list[str] = []
    others = sorted(str(one) for one in services if one != SERVICE)
    if others:
        found.append(
            f"{OVERLAY} declares {others} beside {SERVICE!r}, and an overlay that redefines a "
            "service changes the base stack for every install that picks the option"
        )
    body = services.get(SERVICE)
    if not isinstance(body, Mapping):
        found.append(f"{OVERLAY} has no {SERVICE!r} service")
        return tuple(found)

    if "ports" in body or "network_mode" in body:
        found.append(
            f"{SERVICE!r} can listen outside the compose network. {A_TUNNEL_PUBLISHES_NOTHING}"
        )

    repository, _, tag = str(body.get("image", "")).rpartition(":")
    if repository != IMAGE_REPOSITORY or not RELEASE_TAG.match(tag):
        found.append(
            f"{SERVICE!r} runs {body.get('image')!r}, not {IMAGE_REPOSITORY} at a release. "
            f"{A_MOVING_TAG_IS_A_DIFFERENT_BINARY_HOLDING_THE_CREDENTIAL}"
        )

    if token_variable(document) is None:
        found.append(
            f"{SERVICE!r} does not require {CREDENTIAL_SETTING}. "
            f"{A_TUNNEL_WITH_NO_CREDENTIAL_REFUSES_TO_START}"
        )

    command = body.get("command")
    argv = tuple(command.split()) if isinstance(command, str) else tuple(command or ())
    if argv != COMMAND or "entrypoint" in body:
        found.append(
            f"{SERVICE!r} runs {argv!r} rather than {COMMAND!r} under the image's own "
            f"entrypoint. {THE_CREDENTIAL_IS_NOT_ON_THE_COMMAND_LINE}"
        )

    networks = _names(body["networks"]) if "networks" in body else {"default"}
    if networks != {"default"}:
        found.append(
            f"{SERVICE!r} joins {sorted(networks)}. {THE_TUNNEL_STAYS_OFF_THE_CANVAS_NETWORK}"
        )

    if APPLICATION_SERVICE not in _names(body.get("depends_on")):
        found.append(
            f"{SERVICE!r} does not wait for {APPLICATION_SERVICE!r}. "
            f"{THE_TUNNEL_WAITS_FOR_THE_APPLICATION}"
        )
    return tuple(found)


def tunnel_section(page: str) -> str | None:
    """The text under the network guide's tunnel heading, up to the next level-two heading."""
    headings = list(LEVEL_TWO.finditer(page))
    for index, one in enumerate(headings):
        if one.group(1) == SECTION_HEADING:
            end = headings[index + 1].start() if index + 1 < len(headings) else len(page)
            return page[one.end() : end]
    return None


def page_gaps(page: str, *, variable: str | None) -> tuple[str, ...]:
    """What a person following the network guide's tunnel section would not be told.

    Read inside the section only, so a file name mentioned elsewhere on the page cannot supply
    a step this section leaves out. `variable` is read off the overlay by `token_variable`
    rather than written here, so the page is held to what the file actually requires.
    """
    section = tunnel_section(page)
    if section is None:
        return (
            f"the network guide has no section headed {SECTION_HEADING!r}, so the option is a "
            "file nobody installing this is told about",
        )
    if variable is None:
        return ("the overlay requires no token variable, so the page has no name to give",)
    wanted = {
        f"`{OVERLAY}`": "the file to compose",
        f"`{variable}`": "the variable the overlay refuses to start without",
        f"`{APPLICATION_SERVICE}:{APPLICATION_PORT}`": "where the public hostname points",
        "ss -tlnp": "how to confirm nothing is listening",
        str(EDGE_PORT): "the outbound port the tunnel needs",
    }
    return tuple(
        f"the tunnel section does not give {text}, {why}"
        for text, why in wanted.items()
        if text not in section
    )
