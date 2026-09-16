"""Deploying the compose stack with Coolify: what the panel does to the files, and what it needs.

Coolify is a deployment panel that runs a compose file as a resource, puts its own Traefik proxy
in front of it and issues a certificate for every domain given to a service. The owner's staging
install runs on it, and every fault found there that was about the panel rather than the product
had the same shape: **Coolify does not run the repository's compose file, it runs its own stored
copy**, edited in a text box, with variables it created from the first copy it was given. So the
product half of a Coolify deployment is not a second set of files. It is knowing, per profile,
which properties of the files a stored copy changes, and saying them in `docs/install/coolify.md`
as tables this module computes.

**Four questions, each answered from the files rather than from a list somebody keeps.**

Which services get a domain, and on which port. The application declares no port and listens on
8000, the identity provider on 8080, and Coolify's domain field takes the container port after
the host: `https://console.example.com:8000`. `ROUTES` holds the four, and `route_gaps` compares
each against the port the service's own compose entry declares or its healthcheck dials, so a
port that moves in a compose file moves the guide's table or fails a test.

Which values Coolify keeps from the first save. A `${NAME:-default}` becomes a variable in the
panel holding that default, and Coolify keeps a variable's value when the compose file is
reloaded, so a default a later release changes never reaches the install. `stored_defaults`
lists every non-empty default a profile's files carry. An empty default is not listed: it
creates an empty variable, which is what an unset one is anyway. See
`A_DEFAULT_IS_COPIED_ONCE_AND_NEVER_AGAIN`.

Which services finish and exit. A one-shot helper shows as exited beside healthy services, and
Coolify's `exclude_from_hc: true` keeps it out of the resource's health. That key is Coolify's
and not compose's: `docker compose` refuses a service carrying it, so it is added to the stored
copy on the panel and never to a file in this repository. `coolify_gaps` refuses it here. See
`A_PANEL_ONLY_KEY_IN_A_PRODUCT_FILE_BREAKS_EVERY_OTHER_INSTALL`.

Which files have to be on the server before the first deploy. A settings file mounted from an
absolute path is created by the installer, and a Coolify install has no installer: the stored
copy mounts a path that does not exist, and Docker creates an empty directory there and starts
the container. `host_files` lists them from the mounts themselves.

**What `coolify_gaps` refuses, and each is a Coolify failure that is silent.** A relative bind
mount, which the stored copy resolves against a directory with no repository in it
(`brain.ops.compose.A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE`). A published port, which
answers beside the proxy rather than through it, so it has no certificate, and a host firewall
does not stop it. `BRAIN_COMMIT_SHA` in any environment, which on staging froze the reported
commit at the literal `unknown` for weeks, because the panel resolved the variable once and an
environment entry beats the value the image bakes in. And a panel-only key in a product file.

Rejected: a Coolify-specific compose file per profile. It is the copy this repository has twice
refused elsewhere, and Coolify would still store its own copy of that copy.

What this module cannot see is the stored copy itself. It lives in the panel's database on the
client's server, and whether it matches a release is a comparison an operator makes; the guide
says how, and `docs/install/coolify.md` says which parts nothing checks.

Task ids: M30.1.1, M30.1.2
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from brain.ops.compose import ComposeFiles, relative_bind_mounts

#: The services a browser reaches, against the container port Coolify's domain field names.
ROUTES: Final[Mapping[str, int]] = {
    "app": 8000,
    "keycloak": 8080,
    "langfuse-web": 3000,
    "activepieces": 80,
}

#: Keys Coolify reads on a service that compose does not accept. Added on the panel, never here.
PANEL_ONLY_KEYS: Final[frozenset[str]] = frozenset({"exclude_from_hc"})

#: The variable whose runtime value would replace the commit the image carries.
IMAGE_IDENTITY_VARIABLE: Final = "BRAIN_COMMIT_SHA"

A_DEFAULT_IS_COPIED_ONCE_AND_NEVER_AGAIN: Final = (
    "Coolify turns ${NAME:-default} into a variable on the resource holding the default, and "
    "keeps that value when the compose file is reloaded. A later release that changes the "
    "default changes the repository and not the install, so every non-empty default is a value "
    "an operator checks by hand after an update."
)

A_PANEL_ONLY_KEY_IN_A_PRODUCT_FILE_BREAKS_EVERY_OTHER_INSTALL: Final = (
    "exclude_from_hc is read by Coolify and refused by docker compose as an unknown property, "
    "so the same file that tidies a panel's health display stops every install that runs "
    "compose directly. It belongs in the stored copy on the panel."
)

A_PUBLISHED_PORT_ANSWERS_BESIDE_THE_PROXY: Final = (
    "Coolify's proxy routes a domain to a container port on the resource's network and issues "
    "its certificate. A published port answers on the host beside that route, with no "
    "certificate, and Docker's rule for it is read before the host firewall's."
)

AN_ENVIRONMENT_ENTRY_BEATS_THE_IMAGE: Final = (
    "The image records the commit it was built from. An environment entry for the same variable "
    "replaces it, and Coolify resolves the entry once, when the compose file is saved, so the "
    "application reports whatever the panel knew that day. On staging that was the word unknown."
)

_DEFAULT: Final = re.compile(r"\$\{([A-Z][A-Z0-9_]*):-([^}]+)\}")
_PORT_IN_HEALTHCHECK: Final = re.compile(r"(?:127\.0\.0\.1|localhost):(\d+)")


def _services(files: ComposeFiles) -> dict[str, list[Mapping[str, Any]]]:
    """Every body each service has across the files, in order."""
    found: dict[str, list[Mapping[str, Any]]] = {}
    for name in files:
        for service, body in (files[name].get("services") or {}).items():
            if isinstance(body, Mapping):
                found.setdefault(str(service), []).append(body)
    return found


def _values(value: Any) -> list[str]:
    """Every scalar inside a value, as text, so a default is found wherever it is written."""
    if isinstance(value, Mapping):
        return [text for one in value.values() for text in _values(one)]
    if isinstance(value, list | tuple):
        return [text for one in value for text in _values(one)]
    return [str(value)]


def declared_ports(bodies: list[Mapping[str, Any]]) -> set[int]:
    """The ports a service says it listens on: its `expose` entries and its healthcheck's."""
    ports: set[int] = set()
    for body in bodies:
        for entry in body.get("expose") or ():
            ports.add(int(str(entry).split("/")[0]))
        healthcheck = body.get("healthcheck") or {}
        for text in _values(healthcheck.get("test") if isinstance(healthcheck, Mapping) else ""):
            ports.update(int(one) for one in _PORT_IN_HEALTHCHECK.findall(text))
    return ports


def routes_for(files: ComposeFiles) -> dict[str, int]:
    """The domains a profile composing these files needs, as service against container port."""
    services = _services(files)
    return {name: port for name, port in ROUTES.items() if name in services}


def route_gaps(files: ComposeFiles) -> tuple[str, ...]:
    """Every routed service whose declared port is not the one the guide gives Coolify."""
    services = _services(files)
    findings: list[str] = []
    for name, port in routes_for(files).items():
        ports = declared_ports(services[name])
        if port not in ports:
            findings.append(
                f"{name!r} is given a Coolify domain on port {port} and its compose entry "
                f"declares {sorted(ports) or 'no port'}, so the proxy would route to nothing"
            )
    return tuple(findings)


def stored_defaults(files: ComposeFiles) -> dict[str, str]:
    """Every non-empty `${NAME:-default}` in these files.

    See `A_DEFAULT_IS_COPIED_ONCE_AND_NEVER_AGAIN`.
    """
    found: dict[str, str] = {}
    for bodies in _services(files).values():
        for body in bodies:
            for text in _values(body):
                for name, default in _DEFAULT.findall(text):
                    found[name] = default
    return dict(sorted(found.items()))


def one_shot_services(files: ComposeFiles) -> tuple[str, ...]:
    """Services that are meant to exit, which a panel shows as exited beside healthy ones."""
    return tuple(
        sorted(
            name
            for name, bodies in _services(files).items()
            if any(str(body.get("restart", "")) == "no" for body in bodies)
        )
    )


def host_files(files: ComposeFiles) -> tuple[tuple[str, str], ...]:
    """Every absolute path a service mounts from the host, against the service, sorted."""
    found: set[tuple[str, str]] = set()
    for name, bodies in _services(files).items():
        for body in bodies:
            for entry in body.get("volumes") or ():
                source = (
                    str(entry.get("source", ""))
                    if isinstance(entry, Mapping)
                    else str(entry).split(":", 1)[0]
                )
                if source.startswith("/"):
                    found.add((source, name))
    return tuple(sorted(found))


def external_networks(files: ComposeFiles) -> tuple[str, ...]:
    """The networks these files expect the host to have already, by the name Docker knows them.

    On Coolify the one this repository names is the proxy's own network, which the panel creates.
    Anywhere else nothing creates it, and compose refuses to start a service joined to it.
    """
    found: set[str] = set()
    for name in files:
        for key, body in (files[name].get("networks") or {}).items():
            if isinstance(body, Mapping) and body.get("external") is True:
                found.add(str(body.get("name") or key))
    return tuple(sorted(found))


def coolify_gaps(files: ComposeFiles) -> tuple[str, ...]:
    """Everything in these files that a Coolify stored copy would turn into a silent failure."""
    findings = [
        f"{line}; Coolify stores the file with no repository beside it"
        for line in relative_bind_mounts(files)
    ]
    for name, bodies in sorted(_services(files).items()):
        for body in bodies:
            panel = sorted(PANEL_ONLY_KEYS & set(body))
            if panel:
                findings.append(
                    f"{name!r} carries {panel}. "
                    f"{A_PANEL_ONLY_KEY_IN_A_PRODUCT_FILE_BREAKS_EVERY_OTHER_INSTALL}"
                )
            if body.get("ports"):
                findings.append(
                    f"{name!r} publishes {body.get('ports')}. "
                    f"{A_PUBLISHED_PORT_ANSWERS_BESIDE_THE_PROXY}"
                )
            environment = body.get("environment") or {}
            keys = (
                set(environment)
                if isinstance(environment, Mapping)
                else {str(one).split("=", 1)[0] for one in environment}
            )
            if IMAGE_IDENTITY_VARIABLE in keys:
                findings.append(
                    f"{name!r} sets {IMAGE_IDENTITY_VARIABLE}. "
                    f"{AN_ENVIRONMENT_ENTRY_BEATS_THE_IMAGE}"
                )
    findings.extend(route_gaps(files))
    return tuple(findings)
