"""The Cloudflare Tunnel option, held to its overlay, to every profile it composes onto, and to
the page a person follows.

Every assertion reads the parsed YAML or one section of the page, never the raw text. The
overlay's own comments quote `latest`, `--token` and `tool-api` to explain why each is absent,
so a substring check over the file would be satisfied by the explanation.

Each refusal has a positive sibling, and the first test is the sibling of all of them: the file
as written is clean, so a checker that refused everything fails there.

Two tests pin what is not done, and they are expected to fail on the day it is: the release
archive does not carry the overlay, and the identity provider is not on the tunnel's network.
That failure is the notification to change the page and the module with them.

Task ids: M30.1.3
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.release import INCLUDED
from brain.deployment.requirements import COMPOSE_FILES_FOR, files_for, published_ports
from brain.ops.tunnel import (
    A_MOVING_TAG_IS_A_DIFFERENT_BINARY_HOLDING_THE_CREDENTIAL,
    A_TUNNEL_PUBLISHES_NOTHING,
    A_TUNNEL_WITH_NO_CREDENTIAL_REFUSES_TO_START,
    APPLICATION_PORT,
    APPLICATION_SERVICE,
    OVERLAY,
    SECTION_HEADING,
    SERVICE,
    THE_CREDENTIAL_IS_NOT_ON_THE_COMMAND_LINE,
    THE_TUNNEL_STAYS_OFF_THE_CANVAS_NETWORK,
    THE_TUNNEL_WAITS_FOR_THE_APPLICATION,
    overlay_gaps,
    page_gaps,
    token_variable,
    tunnel_section,
)

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs" / "install" / "network.md"


def load(name: str) -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8"))
    return parsed


def edited(**changes: Any) -> dict[str, Any]:
    """The overlay with keys of its one service replaced, and a value of None deleting the key."""
    document = copy.deepcopy(load(OVERLAY))
    body = document["services"][SERVICE]
    for key, value in changes.items():
        if value is None:
            body.pop(key, None)
        else:
            body[key] = value
    return document


def only_finding(document: dict[str, Any]) -> str:
    found = overlay_gaps(document)
    assert len(found) == 1, found
    return found[0]


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def with_section(text: str, change: tuple[str, str]) -> str:
    """The page with one replacement made inside the tunnel section and nowhere else."""
    section = tunnel_section(text)
    assert section is not None
    assert change[0] in section, f"{change[0]!r} is not in the section, so nothing would change"
    return text.replace(section, section.replace(change[0], change[1]), 1)


# ================================================================================ the overlay
def test_the_overlay_as_written_is_a_pinned_tunnel_with_no_inbound_port() -> None:
    """The file itself, parsed. Every refusal below builds a broken copy, so without this the
    real overlay could gain a port, a moving tag or an optional token with every one of them
    still green.

    Delete this and the checker is tested against everything except the file it exists for."""
    document = load(OVERLAY)

    assert SERVICE in document["services"]
    assert overlay_gaps(document) == ()


@pytest.mark.parametrize(("key", "value"), [("ports", ["443:443"]), ("network_mode", "host")])
def test_a_tunnel_that_can_listen_outside_the_compose_network_is_a_finding(
    key: str, value: object
) -> None:
    """A published port is an inbound port, which the option exists to remove, and host
    networking puts the container's listeners on the server's own interfaces.

    Delete this and the first `ports` entry added while debugging a connection ships."""
    assert A_TUNNEL_PUBLISHES_NOTHING in only_finding(edited(**{key: value}))


@pytest.mark.parametrize(
    "image",
    [
        "cloudflare/cloudflared",
        "cloudflare/cloudflared:latest",
        "cloudflare/cloudflared:2026.9.1-amd64",
        "cloudflare/cloudflared:1934-f11dea9",
        "somebody/cloudflared:2026.9.1",
    ],
)
def test_an_image_that_is_not_a_release_of_cloudflared_is_a_finding(image: str) -> None:
    """Five tags the registry really publishes beside the releases, or a lookalike repository.
    No tag is `latest`; the build id is not a release; the architecture tag runs on one kind of
    server only; and a different repository is a different program holding the token.

    Delete this and the pin can be relaxed to `latest` with nothing going red."""
    finding = only_finding(edited(image=image))

    assert A_MOVING_TAG_IS_A_DIFFERENT_BINARY_HOLDING_THE_CREDENTIAL in finding


def test_a_later_release_tag_is_accepted() -> None:
    """The positive sibling of the pin. A check that accepted only the one tag in the file today
    would turn every routine upgrade into a red test, and a test that goes red for upgrades is
    one somebody weakens.

    Delete this and the release pattern can narrow to a single string without anything saying
    so."""
    assert overlay_gaps(edited(image="cloudflare/cloudflared:2027.12.10")) == ()


@pytest.mark.parametrize(
    "environment",
    [
        {"TUNNEL_TOKEN": "${CLOUDFLARE_TUNNEL_TOKEN}"},
        {"TUNNEL_TOKEN": "${CLOUDFLARE_TUNNEL_TOKEN:-}"},
        {"TUNNEL_TOKEN": "${CLOUDFLARE_TUNNEL_TOKEN:-shared}"},
        {"TUNNEL_TOKEN": "not-a-real-token"},
        {},
    ],
)
def test_a_token_that_is_not_required_is_a_finding(environment: dict[str, str]) -> None:
    """Unset or defaulted, compose starts the stack with an empty or shared token instead of
    refusing, and a literal is a credential in a file this repository ships.

    Delete this and `:?` can become `:-` in the overlay with nothing going red."""
    document = edited(environment=environment)

    assert token_variable(document) is None
    assert A_TUNNEL_WITH_NO_CREDENTIAL_REFUSES_TO_START in only_finding(document)


def test_the_required_variable_is_read_off_the_file_whatever_it_is_called() -> None:
    """The positive sibling, and what the guide is held to. The variable name comes out of the
    overlay rather than out of a constant, so renaming it in the file moves the page's
    requirement with it.

    Delete this and `token_variable` could return a fixed name and still pass the page test."""
    assert token_variable(load(OVERLAY)) == "CLOUDFLARE_TUNNEL_TOKEN"
    renamed = edited(environment={"TUNNEL_TOKEN": "${EDGE_CONNECTOR_TOKEN:?set it}"})
    assert token_variable(renamed) == "EDGE_CONNECTOR_TOKEN"
    assert overlay_gaps(renamed) == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"command": ["tunnel", "run", "--token", "${CLOUDFLARE_TUNNEL_TOKEN:?set it}"]},
        {"command": None},
        {"entrypoint": ["cloudflared"]},
    ],
)
def test_the_token_on_the_command_line_or_a_replaced_entrypoint_is_a_finding(
    changes: dict[str, Any],
) -> None:
    """`--token` puts the credential in the process list; no command runs the image's default,
    which prints a version and exits; a replaced entrypoint drops `--no-autoupdate`, which is
    what keeps the pin a pin.

    Delete this and the token can move onto the command line, which is how the dashboard's own
    copy-and-paste instruction writes it."""
    assert THE_CREDENTIAL_IS_NOT_ON_THE_COMMAND_LINE in only_finding(edited(**changes))


def test_the_command_written_as_one_string_is_the_same_command() -> None:
    """The positive sibling. Compose accepts either spelling, and refusing the string form would
    make the check about formatting rather than about what runs.

    Delete this and the comparison can quietly require a list."""
    assert overlay_gaps(edited(command="tunnel run")) == ()


@pytest.mark.parametrize("networks", [["default", "tool-api"], {"tool-api": {}}])
def test_a_tunnel_on_the_canvas_network_is_a_finding(networks: object) -> None:
    """`tool-api` carries the application and the automation canvas alone, and every member of a
    network can reach every other. A tunnel on it is a public entry point an assembled flow can
    reach.

    Delete this and the tunnel can join every network the application is on, which reads as the
    thorough choice."""
    assert THE_TUNNEL_STAYS_OFF_THE_CANVAS_NETWORK in only_finding(edited(networks=networks))


@pytest.mark.parametrize("networks", [None, ["default"], {"default": None}])
def test_the_default_network_in_any_spelling_is_accepted(networks: object) -> None:
    """The positive sibling: no `networks` key and both explicit spellings mean the same network.

    Delete this and the check can refuse the mapping form, or an absent key, for no reason a
    reader could find."""
    assert overlay_gaps(edited(networks=networks)) == ()


@pytest.mark.parametrize("depends_on", [None, ["cache"]])
def test_a_tunnel_that_does_not_wait_for_the_application_is_a_finding(depends_on: object) -> None:
    """Without it the tunnel carries requests to a container that is still migrating, and the
    overlay composes onto a set with no application without complaint.

    Delete this and the first thing a person sees after a start is a gateway error."""
    assert THE_TUNNEL_WAITS_FOR_THE_APPLICATION in only_finding(edited(depends_on=depends_on))


def test_waiting_for_the_application_in_the_list_spelling_is_accepted() -> None:
    """The positive sibling for the short form of `depends_on`.

    Delete this and the check can require the long form only."""
    assert overlay_gaps(edited(depends_on=[APPLICATION_SERVICE])) == ()


def test_an_overlay_that_touches_another_service_or_has_no_tunnel_is_a_finding() -> None:
    """An overlay that also redefines `app` changes the base stack for every install that picks
    the option, and one with no tunnel service is not the option at all.

    Delete this and a port can be added to the application from inside the tunnel's file, where
    nobody reviewing the base files would look."""
    document = copy.deepcopy(load(OVERLAY))
    document["services"]["app"] = {"ports": ["8000:8000"]}
    assert "redefines a service" in only_finding(document)

    assert overlay_gaps({"services": {}}) == (f"{OVERLAY} has no {SERVICE!r} service",)
    assert "declares no services" in overlay_gaps({})[0]


# ================================================================ composed onto every profile
@pytest.mark.parametrize("profile", sorted(COMPOSE_FILES_FOR))
def test_no_profile_publishes_a_port_with_the_tunnel_composed_on_top(profile: str) -> None:
    """The option's claim, made against the files an operator actually names with `-f`. Compose
    cannot remove a port in an overlay, so this holds only because no base file publishes one,
    and it is the test that goes red if one ever does.

    The second half proves the reader sees the overlay at all: a port on the tunnel is found, so
    an empty result above is about the files and not about a reader that skipped one.

    Delete this and a port added to any base file silently ends the zero-inbound claim."""
    files = {name: load(name) for name in files_for(profile)}
    files[OVERLAY] = load(OVERLAY)

    assert published_ports(files) == ()

    files[OVERLAY] = edited(ports=["443:443"])
    assert published_ports(files) == (f"{SERVICE}: 443:443",)


@pytest.mark.parametrize("profile", sorted(COMPOSE_FILES_FOR))
def test_the_application_the_tunnel_points_at_is_on_the_network_it_joins(profile: str) -> None:
    """The public hostname points at `app:8000`. That address resolves only if every profile has
    an application service on `default`, and the port is only right if the application's own
    readiness probe asks for it, which is the one place the base files write it down.

    Delete this and the application can move to another network or port while the guide keeps
    telling people to point the tunnel at an address that answers nothing."""
    files = {name: load(name) for name in files_for(profile)}
    apps = [
        document["services"][APPLICATION_SERVICE]
        for document in files.values()
        if APPLICATION_SERVICE in (document.get("services") or {})
    ]
    assert apps, f"{profile} composes no {APPLICATION_SERVICE!r} service"
    for app in apps:
        assert "default" in app.get("networks", ["default"])
        probe = " ".join(str(one) for one in app["healthcheck"]["test"])
        assert f"127.0.0.1:{APPLICATION_PORT}/" in probe


# ==================================================================================== the page
def test_the_network_guide_explains_the_option_with_the_values_the_file_requires() -> None:
    """The guide names the overlay, the variable the overlay really requires, the address, the
    outbound port and the listening check, inside its own section, and every compose file that
    section tells a person to use exists.

    Delete this and the file can be renamed, or its variable changed, with the step-by-step
    instructions still naming the old one."""
    text = page()
    section = tunnel_section(text)

    assert section is not None
    assert page_gaps(text, variable=token_variable(load(OVERLAY))) == ()
    named = set(re.findall(r"docker-compose[\w.-]*\.yml", section))
    assert OVERLAY in named
    assert all((REPO / one).is_file() for one in named), named


def test_an_overlay_with_no_required_variable_leaves_the_page_nothing_to_name() -> None:
    """The page cannot be held to a variable the file does not require. Without this refusal the
    check asks the section for a code span reading `None`, which reports a missing value when
    what is missing is the requirement in the file.

    Delete this and the guard can go, leaving a finding that sends the reader to the wrong file."""
    found = page_gaps(page(), variable=None)

    assert len(found) == 1, found
    assert "requires no token variable" in found[0]


def test_a_guide_with_no_section_is_a_finding() -> None:
    """The refusal for the whole section. Delete this and `tunnel_section` can return the whole
    page, which contains every value somewhere."""
    text = page().replace(f"## {SECTION_HEADING}", "## Something else", 1)

    assert tunnel_section(text) is None
    assert "no section headed" in page_gaps(text, variable="CLOUDFLARE_TUNNEL_TOKEN")[0]


@pytest.mark.parametrize(
    ("missing", "stand_in"),
    [
        ("`CLOUDFLARE_TUNNEL_TOKEN`", "the token variable"),
        (f"`{OVERLAY}`", "the overlay"),
        ("ss -tlnp", "a listening check"),
        ("`app:8000`", "the application"),
        ("7844", "the edge port"),
    ],
)
def test_a_section_missing_a_value_is_a_finding_even_if_the_page_names_it_elsewhere(
    missing: str, stand_in: str
) -> None:
    """Each value removed from the section and then written back further down the page, under a
    different heading. The finding still stands, which is what reading the section alone buys.

    Delete this and the check can be widened to the whole page, where the overlay's name can be
    supplied by the table of what is checked."""
    text = with_section(page(), (missing, stand_in)) + f"\n## Elsewhere\n\n{missing}\n"

    found = page_gaps(text, variable="CLOUDFLARE_TUNNEL_TOKEN")

    assert len(found) == 1, found
    assert missing in found[0]


# ================================================================== what is not done, pinned
def test_the_release_archive_does_not_carry_the_overlay_yet() -> None:
    """**Expected to fail on the day it is fixed, and that failure is the notification.**

    The archive is derived from the compose files each profile composes, and no profile composes
    the tunnel, so an install from a release has no overlay on disk. The guide's step copying
    the file by hand, `THE_RELEASE_DOES_NOT_CARRY_THE_OVERLAY` and the paragraph after an update
    all describe this, and all three change when this test goes red.

    Delete this and the archive can start carrying the file while the guide goes on telling
    people to copy it by hand, or stop carrying it after somebody claims the leaf."""
    patterns = {rule.pattern for rule in INCLUDED}

    assert "docker-compose.lite.yml" in patterns
    assert OVERLAY not in patterns


def test_the_identity_provider_is_not_on_the_network_the_tunnel_joins() -> None:
    """**Expected to fail on the day it is fixed.** The identity provider joins the panel's proxy
    network and its own, and the tunnel joins `default`, so on `standard` and `full` the sign-in
    page is not reachable through the tunnel. The guide's "complete for `lite` only" rests on
    this and on `lite` composing no identity provider at all.

    Delete this and the identity provider can join `default` while the guide still turns every
    `standard` install away from the option."""
    keycloak = load("docker-compose.keycloak.yml")["services"]["keycloak"]
    tunnel = load(OVERLAY)["services"][SERVICE]

    assert "default" not in set(keycloak["networks"])
    assert not set(keycloak["networks"]) & set(tunnel["networks"])
    assert "docker-compose.keycloak.yml" in files_for("standard")
    assert "docker-compose.keycloak.yml" not in files_for("lite")
