"""No service this repository did not build sits on a network with a route out, unless that
membership is written down with a reason.

**The rule, and why it is this rule.** Docker gives every bridge network a gateway unless it is
declared `internal: true`, and a container on a network with a gateway can reach the internet.
Proxy variables do not change that: `HTTP_PROXY` is a request to a client library, and Node's
built-in `fetch` does not honour it. So the only thing that stops a container reaching out is
the networks it is on. The property held here is:

    for every composition the product runs, for every network in it that is not internal,
    every member whose image is not the application's own is listed for that network in
    `ROUTE_OUT`, with a named reason.

**Why "not the application's image" and not a hand-picked list of sandboxes.** The application
image is the one thing this repository builds, reviews and gates per request, and it needs a
route out: model providers, connected sources and sign-in are all elsewhere. Everything else is
code whose outbound behaviour nobody here has read, whether it is a database, a trace store or
the automation canvas running flows a client's staff assembled. A list of sandboxes would be
correct on the day it was written and silent about the next service somebody adds; a rule over
images puts every new service in scope by default, and the only way past it is a line in
`ROUTE_OUT` a reviewer can read.

**Why per composition and not per file.** Nothing runs a compose file on its own except
`docker-compose.staging.yml`. `full` composes nine files into one project, the tunnel adds one
or two more, and Compose merges a top-level network across `-f` files with the later file
winning. The defect this module was written after was exactly that: `docker-compose.yml`
declared `tool-api` and `docker-compose.automation.yml` marked it `external`, each file looked
right, and the merged project had a network nothing created. So a membership is judged on the
merged set, the same set `ops/update/update.sh` passes, and a second test holds that every
file is part of some composition, so a new file cannot sit outside the rule by not being named.

**What is listed, and why each is deliberate rather than an oversight.** The application's own
stores sit on `default` beside it: moving them to an internal network of their own is a change
to the base file of every profile and to a live server, nobody has made it, and writing it down
is what keeps it a decision. The tunnel must reach Cloudflare, so it is on `default` knowingly.
The egress proxy is the route out by design. The identity provider joins the deployment panel's
network, which is declared outside this repository and cannot be made internal from here.

**What this does not see.** It reads the files, not a running host: Docker is not installed on
the machine this was written on, so the gateway behaviour above is Docker's documented
behaviour and not a measurement. A network created by hand on the server with different
settings, or a stored compose a deployment panel kept from before a change, is invisible to it.

Task ids: M32.6.1.1
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from brain.deployment.app_environment import VAULT_OVERLAY
from brain.deployment.requirements import COMPOSE_FILES_FOR, files_for
from brain.ops.tunnel import overlays_for

REPO = Path(__file__).resolve().parents[2]

#: Run on its own, as its own project. Every other file is composed through a profile.
STAGING: Final = "docker-compose.staging.yml"

#: The application's image, in the two variables that name it. A service built from one of
#: these is the code this repository reviews; anything else is somebody else's.
OURS = re.compile(r"^\$\{(APP_IMAGE|STAGING_IMAGE)[:}]")

THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT: Final = (
    "The application needs a route out and Compose grants one to a network, not to one of its "
    "members, so the pooler, the database, the cache, the trace ledger and the object store on "
    "`default` have one too. They are pinned store images handed no flow and no model. Closing "
    "it means an internal network for the stores in the base file of every profile, which has "
    "not been done, and this entry is where that is recorded rather than forgotten."
)

THE_TUNNEL_DIALS_OUT_TO_CLOUDFLARE: Final = (
    "cloudflared carries requests in over a connection it opens to Cloudflare on port 7844, so "
    "it cannot work without a route out. It joins `default`, which is where `app:8000` resolves, "
    "and never `tool-api`, which `brain.ops.tunnel` holds."
)

THE_PROXY_IS_THE_ROUTE_OUT: Final = (
    "The egress proxy is the one member of the automation sandbox that can reach out, because "
    "it is where the allowlist is applied. It sits on `egress` and the internal `automation` "
    "network, and nothing else joins `egress`."
)

THE_PANELS_NETWORK_IS_NOT_OURS_TO_DECLARE: Final = (
    "The identity provider joins the deployment panel's proxy network so staff browsers can "
    "reach the sign-in page. That network is external, created by the panel, and `internal` "
    "cannot be set on an external network from a compose file."
)

#: Every non-application service allowed on a network with a route out, and why. A service
#: missing from here that turns up on such a network fails
#: `test_no_service_but_the_application_reaches_out_unless_listed`.
ROUTE_OUT: Final[Mapping[str, Mapping[str, str]]] = {
    "default": {
        "pgbouncer": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "db": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "cache": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "langfuse-web": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "langfuse-worker": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "langfuse-clickhouse": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "langfuse-cache": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "seaweedfs": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "seaweedfs-init": THE_APPLICATIONS_STORES_SHARE_ITS_ROUTE_OUT,
        "cloudflared": THE_TUNNEL_DIALS_OUT_TO_CLOUDFLARE,
    },
    "egress": {"automation-egress": THE_PROXY_IS_THE_ROUTE_OUT},
    "proxy": {"keycloak": THE_PANELS_NETWORK_IS_NOT_OURS_TO_DECLARE},
}

#: Services that run work somebody outside this repository assembled or trained. No reason
#: written in `ROUTE_OUT` is good enough for these, which is why they are named twice.
SANDBOXED: Final = frozenset({"activepieces", "inference-server", "record-matcher"})


def load(name: str) -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}
    return parsed


def compositions() -> dict[str, tuple[str, ...]]:
    """Every set of files the product composes into one project, in `-f` order."""
    found: dict[str, tuple[str, ...]] = {STAGING: (STAGING,)}
    for profile in sorted(COMPOSE_FILES_FOR):
        files = files_for(profile)
        found[profile] = files
        found[f"{profile} with the tunnel"] = (*files, *overlays_for(files))
        # Composed onto any profile whose environment file names a vault. See
        # `brain.deployment.app_environment`.
        found[f"{profile} with the vault"] = (*files, VAULT_OVERLAY)
    return found


def _network_names(value: object) -> set[str]:
    """A service's `networks` in either spelling, a list or a mapping."""
    if isinstance(value, Mapping):
        return {str(one) for one in value}
    if isinstance(value, list):
        return {str(one) for one in value}
    return set()


def members(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, set[str]]:
    """Network key to the services on it, merged as Compose merges: a union by name, and a
    service no file gives a `networks` key joins `default`."""
    joined: dict[str, set[str]] = {}
    services: set[str] = set()
    named: set[str] = set()
    for document in documents.values():
        for service, body in (document.get("services") or {}).items():
            services.add(service)
            if isinstance(body, Mapping) and "networks" in body:
                named.add(service)
                for network in _network_names(body["networks"]):
                    joined.setdefault(network, set()).add(service)
    for service in services - named:
        joined.setdefault("default", set()).add(service)
    return joined


def declarations(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Network key to its declaration, merged in `-f` order with the later file winning."""
    merged: dict[str, dict[str, Any]] = {}
    for document in documents.values():
        for network, body in (document.get("networks") or {}).items():
            merged.setdefault(network, {}).update(body or {})
    return merged


def image_of(documents: Mapping[str, Mapping[str, Any]], service: str) -> str:
    """The image a service runs, from whichever file gives one. Overlays usually do not."""
    image = ""
    for document in documents.values():
        body = (document.get("services") or {}).get(service)
        if isinstance(body, Mapping) and body.get("image"):
            image = str(body["image"])
    return image


def reaches_out(declaration: Mapping[str, Any] | None) -> bool:
    """A network has a route out unless it is declared internal and is not external. An
    undeclared network (an implicit `default`) and an external one declared elsewhere both
    count as reaching out, because nothing in the set says otherwise."""
    if declaration is None:
        return True
    return declaration.get("internal") is not True or declaration.get("external") is True


def strangers_on_a_route_out(
    documents: Mapping[str, Mapping[str, Any]],
    allowed: Mapping[str, Mapping[str, str]] = ROUTE_OUT,
) -> list[str]:
    """Every `network: service` where a service not built from the application image sits on
    a network with a route out and is not listed for it."""
    declared = declarations(documents)
    found = []
    for network, services in sorted(members(documents).items()):
        if not reaches_out(declared.get(network)):
            continue
        for service in sorted(services):
            if OURS.match(image_of(documents, service)):
                continue
            if service not in allowed.get(network, {}):
                found.append(f"{network}: {service}")
    return found


# ================================================================================ the rule
@pytest.mark.parametrize("composition", sorted(compositions()))
def test_no_service_but_the_application_reaches_out_unless_listed(composition: str) -> None:
    """**The property this module exists for**, over every set of files the product composes.

    Delete this and a service can be added to any network with a gateway, or an internal
    network can lose `internal: true`, and nothing notices: that is how the automation canvas
    sat on `tool-api` with a direct route to the internet beside the egress proxy until
    2026-09-15, while every test of the sandbox passed."""
    documents = {name: load(name) for name in compositions()[composition]}

    assert strangers_on_a_route_out(documents) == []


@pytest.mark.parametrize("composition", sorted(compositions()))
def test_the_sandboxed_services_sit_only_on_internal_networks(composition: str) -> None:
    """The canvas, the inference server and the matcher, checked without the list, so a line
    added to `ROUTE_OUT` to make the rule above pass cannot admit one of them.

    Delete this and the escape hatch the rule above leaves for stores and the tunnel becomes
    an escape hatch for the three services the rule matters most for."""
    documents = {name: load(name) for name in compositions()[composition]}
    declared = declarations(documents)

    outward = sorted(
        f"{network}: {service}"
        for network, services in members(documents).items()
        for service in services & SANDBOXED
        if reaches_out(declared.get(network))
    )
    assert outward == []


def test_the_canvas_is_in_some_composition_so_the_sandbox_check_is_not_vacuous() -> None:
    """Every sandboxed service is actually composed somewhere. Delete this and a renamed
    service makes the test above pass by checking nothing."""
    composed = {
        service
        for files in compositions().values()
        for services in members({name: load(name) for name in files}).values()
        for service in services
    }

    assert composed >= SANDBOXED


def test_every_compose_file_is_part_of_a_composition_the_rule_reads() -> None:
    """A rule over compositions is blind to a file no composition names. Delete this and a new
    `docker-compose.something.yml` escapes the check by not yet being in a profile, which is
    exactly the state a file is in on the day somebody writes it."""
    on_disk = {path.name for path in REPO.glob("docker-compose*.yml")}
    read = {name for files in compositions().values() for name in files}

    assert on_disk - read == set()


def test_every_listed_membership_is_one_the_files_actually_have() -> None:
    """A stale entry pre-authorises a future service of that name, which then joins a route
    out with a reason written for something else. Delete this and `ROUTE_OUT` only grows."""
    present = {
        (network, service)
        for files in compositions().values()
        for network, services in members({name: load(name) for name in files}).items()
        for service in services
    }
    listed = {(network, service) for network, entries in ROUTE_OUT.items() for service in entries}

    assert listed - present == set()


@pytest.mark.parametrize("composition", sorted(compositions()))
def test_a_network_declared_in_two_files_of_one_composition_is_declared_the_same(
    composition: str,
) -> None:
    """Compose merges a network across files with the later one winning, so two declarations
    that differ produce a third that neither file shows. The `external: true` on `tool-api` in
    the sandbox's file is the case: merged after `docker-compose.yml`, it turned a network the
    project creates into one it expects somebody else to have created.

    Delete this and one file can drop `internal: true` while another keeps it, and the merged
    result depends on the order of `-f` flags in a shell script."""
    documents = {name: load(name) for name in compositions()[composition]}
    seen: dict[str, tuple[str, Any]] = {}

    for name, document in documents.items():
        for network, body in (document.get("networks") or {}).items():
            if network in seen:
                first, earlier = seen[network]
                assert (body or {}) == earlier, f"{network} differs between {first} and {name}"
            else:
                seen[network] = (name, body or {})


def test_every_declaration_of_one_named_network_is_the_same_in_every_file() -> None:
    """A fixed `name:` is one Docker network whichever project creates it, so `lite` and the
    standard base file describe the same object and must agree about it. Delete this and
    `docker-compose.lite.yml` can keep a `tool-api` with a gateway while the others lose it."""
    by_name: dict[str, dict[str, Any]] = {}

    for path in sorted(REPO.glob("docker-compose*.yml")):
        for network, body in (load(path.name).get("networks") or {}).items():
            if isinstance(body, Mapping) and "name" in body and body.get("external") is not True:
                earlier = by_name.setdefault(str(body["name"]), dict(body))
                assert dict(body) == earlier, f"{network} in {path.name} is declared differently"


def test_the_canvas_network_to_the_application_is_internal_in_every_composition_with_both() -> None:
    """The specific finding, stated directly so its failure names it. Delete this and the rule
    above still covers it, but reads as a list of strangers rather than as the sandbox's
    second route out."""
    for composition, files in compositions().items():
        documents = {name: load(name) for name in files}
        on_it = members(documents).get("tool-api", set())
        if "activepieces" in on_it:
            assert not reaches_out(declarations(documents).get("tool-api")), composition


# ================================================================================ the checker
def _third_party_on(network: str, *, internal: bool) -> dict[str, dict[str, Any]]:
    declaration: dict[str, Any] = {"internal": True} if internal else {}
    return {
        "a.yml": {
            "services": {
                "app": {"image": "${APP_IMAGE:?x}", "networks": ["default", network]},
                "stranger": {"image": "vendor/thing:1", "networks": [network]},
            },
            "networks": {network: declaration},
        }
    }


def test_a_third_party_service_on_an_internal_network_is_accepted() -> None:
    """The positive case. Delete this and a checker that reports every membership passes the
    refusal test below."""
    assert strangers_on_a_route_out(_third_party_on("quiet", internal=True), allowed={}) == []


def test_a_third_party_service_on_an_unlisted_outward_network_is_reported() -> None:
    """The refusal, on a synthetic set so it does not depend on today's files. Delete this and
    the checker can go blind while every real composition happens to be clean."""
    found = strangers_on_a_route_out(_third_party_on("loud", internal=False), allowed={})

    assert found == ["loud: stranger"]


def test_the_application_image_on_an_outward_network_is_not_reported() -> None:
    """The application needs a route out and is the one image exempt. Delete this and the
    exemption can widen to every `${...}` image, including the inference server's."""
    found = strangers_on_a_route_out(_third_party_on("loud", internal=False), allowed={})

    assert "default: app" not in found
    assert "loud: app" not in found


def test_an_image_named_by_another_variable_is_not_the_applications() -> None:
    """`${INFERENCE_IMAGE}` is built somewhere else and loads models. Delete this and the
    pattern can be loosened to any variable without a test noticing."""
    documents = {
        "a.yml": {"services": {"inference-server": {"image": "${INFERENCE_IMAGE:?x}"}}},
    }

    assert strangers_on_a_route_out(documents, allowed={}) == ["default: inference-server"]


def test_a_service_with_no_networks_key_is_judged_on_default() -> None:
    """Compose puts such a service on `default`, which has a gateway. Delete this and every
    service that simply omits `networks` is invisible to the rule."""
    documents = {"a.yml": {"services": {"store": {"image": "vendor/store:1"}}}}

    assert strangers_on_a_route_out(documents, allowed={}) == ["default: store"]


def test_an_external_network_counts_as_a_route_out_even_if_declared_internal_elsewhere() -> None:
    """An external network is created by somebody else, so its settings are not in the set,
    and a later file marking it external overrides an earlier internal declaration. Delete
    this and `external: true` becomes a way to make a network look internal."""
    documents: dict[str, dict[str, Any]] = {
        "a.yml": {
            "services": {"stranger": {"image": "vendor/thing:1", "networks": ["shared"]}},
            "networks": {"shared": {"internal": True}},
        },
        "b.yml": {"networks": {"shared": {"external": True}}},
    }

    assert strangers_on_a_route_out(documents, allowed={}) == ["shared: stranger"]


def test_a_listed_service_on_its_listed_network_is_accepted_and_nowhere_else() -> None:
    """The list admits a membership, not a service. Delete this and one entry for `default`
    could be read as admitting that service to any network."""
    documents = _third_party_on("loud", internal=False)

    assert strangers_on_a_route_out(documents, allowed={"loud": {"stranger": "why"}}) == []
    assert strangers_on_a_route_out(documents, allowed={"other": {"stranger": "why"}}) == [
        "loud: stranger"
    ]
