"""The personal data analyser as deployed, held to what the product says about it.

`docker-compose.presidio.yml` makes four decisions (image, port, readiness, memory) and one
boundary (no route off the host). Each is compared here against something outside the file:
the budget in `brain.ops.wiring`, the address `brain.ops.pii` dials, the recognisers
`brain.ops.pii` relies on, the licence audit, and the other files that declare the network.
A test that read a value out of the file and compared it with itself would be green for every
value it could hold.

Task ids: M0.4.2
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from brain.config import check
from brain.deployment.requirements import files_for
from brain.ops.dependency_policy import IMAGE_TERMS, repository_of
from brain.ops.pii import (
    AN_ANALYSER_ADDRESS_ON_LITE_IS_SOMEBODY_ELSES_HOST,
    PRESIDIO_ADDRESS_SETTING,
    PRESIDIO_BUILT_INS,
    PRESIDIO_PORT,
    PRESIDIO_SERVICE,
    analyzer_address,
    deploys_presidio,
    presidio_config_conflicts,
)
from brain.ops.sweeps import licence_is_allowed
from brain.ops.wiring import COMPONENTS
from brain.settings import Settings

REPO = Path(__file__).resolve().parents[2]
COMPOSE = "docker-compose.presidio.yml"


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8"))
    return loaded


def _service() -> dict[str, Any]:
    service: dict[str, Any] = _load(COMPOSE)["services"][PRESIDIO_SERVICE]
    return service


def _probe() -> str:
    test = _service()["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL"
    return str(test[1])


# ------------------------------------------------------------------ the four decisions
def test_the_image_is_microsofts_own_pinned_to_a_release_and_admitted_by_the_licence_audit() -> (
    None
):
    """A floating tag is a different container on every pull, and an image the audit does not
    name is a licence nobody read. The terms are asserted against the allowlist rather than
    against themselves.

    Delete this and `latest` can go in, and an analyser changes under an install with no
    release to point at."""
    image = str(_service()["image"])
    assert re.fullmatch(r"mcr\.microsoft\.com/presidio-analyzer:\d+\.\d+\.\d+", image), image

    terms = IMAGE_TERMS[repository_of(image)]
    assert licence_is_allowed(terms.licence)
    assert terms.commercial_key is False


def test_the_container_is_sized_to_the_component_it_is_budgeted_as() -> None:
    """`brain.ops.wiring` decides what this may take and every profile's arithmetic is
    computed from it, so a limit here that differs is memory the budget does not know about.
    The figure is also held above the 1500Mi Microsoft requests for this image, which is the
    outside fact it rests on.

    Delete this and the file and the budget can disagree, and the host figure quoted to a
    client is wrong by the difference."""
    component = next(one for one in COMPONENTS if one.name == PRESIDIO_SERVICE)
    limit = str(_service()["deploy"]["resources"]["limits"]["memory"])

    assert limit == f"{component.memory_mib}M"
    assert component.memory_mib * 1024 * 1024 >= 1500 * 1024 * 1024


def test_the_address_the_product_dials_is_the_service_and_the_port_this_file_opens() -> None:
    """The default address is a service name and a port, and both are only right while this
    file says the same. The port is checked against both `expose` and the image's `PORT`,
    because the server listens on the second and the network opens the first.

    Delete this and the port can move in one place, and the redactor dials a closed port on
    every install that took the default."""
    service = _service()
    assert [str(one) for one in service["expose"]] == [str(PRESIDIO_PORT)]
    assert str(service["environment"]["PORT"]) == str(PRESIDIO_PORT)
    assert PRESIDIO_SERVICE in _load(COMPOSE)["services"]

    assert analyzer_address("full") == f"http://{PRESIDIO_SERVICE}:{PRESIDIO_PORT}"
    assert analyzer_address("standard") == analyzer_address("full")


def test_readiness_is_an_analysis_that_returns_an_entity_the_product_relies_on() -> None:
    """`/health` answers as soon as the web server listens, before the model is serving, so
    it proves nothing about the thing a caller needs. The probe posts text to `/analyze` and
    passes only when the entity it asked for comes back, and that entity is one of
    `PRESIDIO_BUILT_INS`, so the probe exercises a recogniser the scrub actually uses.

    Delete this and the healthcheck can become a heartbeat, and a container whose model failed
    to load reports healthy."""
    probe = _probe()
    body = re.search(r"-d '(\{.*?\})'", probe)
    assert body is not None, probe
    request = yaml.safe_load(body.group(1))
    wanted = request["entities"]

    assert f"http://127.0.0.1:{PRESIDIO_PORT}/analyze" in probe
    assert "/health" not in probe
    assert request["language"] == "en"
    assert len(wanted) == 1
    assert wanted[0] in {one.presidio_name for one in PRESIDIO_BUILT_INS}
    assert probe.rstrip().endswith(f"grep -q {wanted[0]}")


# ------------------------------------------------------------------ the boundary
def test_the_analyser_sits_only_on_an_internal_network_and_publishes_nothing() -> None:
    """The text sent here is the text about to leave the building, before it is scrubbed. An
    internal network has no gateway, so there is no route off the host for it, and `expose`
    without `ports` means nothing outside the project can hand it text.

    Delete this and `default` can be added back, which is a route out for every question."""
    service = _service()
    networks = _load(COMPOSE)["networks"]

    assert service["networks"] == ["pii"]
    assert networks["pii"] == {"internal": True}
    assert "ports" not in service
    assert "volumes" not in service, "a volume is somewhere a copy of the text could be kept"


def test_the_application_joins_the_analysers_network_declared_identically_everywhere() -> None:
    """The application is the only other member, and it declares the network in its own file
    so that file starts without this one. Both declarations are held equal, which is the rule
    `test_compose_networks.py` holds for every network, stated here for this one.

    Delete this and the application can lose the network, and every analysis times out on
    the one profile the analyser exists for."""
    for name in ("docker-compose.yml", "docker-compose.lite.yml"):
        document = _load(name)
        assert "pii" in document["services"]["app"]["networks"], name
        assert document["networks"]["pii"] == _load(COMPOSE)["networks"]["pii"], name

    database_side = {"db", "pgbouncer", "cache"}
    for name in ("docker-compose.yml",):
        for service, body in _load(name)["services"].items():
            if service in database_side:
                assert "pii" not in (body or {}).get("networks", []), service


def test_the_file_is_composed_by_the_profiles_that_budget_the_analyser_and_no_other() -> None:
    """Budget and file set are two declarations of one fact. `lite` runs no analyser and must
    not compose it; `standard` and `full` budget it and must.

    Delete this and a profile can budget the analyser without starting it, which is the gap
    this file was written to close."""
    for profile in ("lite", "standard", "full"):
        assert (COMPOSE in files_for(profile)) == deploys_presidio(profile), profile
    assert deploys_presidio("standard") and deploys_presidio("full")
    assert not deploys_presidio("lite")


def test_no_profiles_key_so_the_analyser_starts_under_the_installers_command() -> None:
    """A service with `profiles:` starts only when a profile is named with `--profile` or
    `COMPOSE_PROFILES`, and the installer names neither, so the key would give a container
    that never starts on the installs that budget it.

    Delete this and the key can be added for tidiness, and the analyser silently never runs."""
    assert "profiles" not in _service()


# ------------------------------------------------------------------ the configuration
def test_an_address_set_on_lite_is_refused_at_startup_and_accepted_where_it_is_deployed() -> None:
    """`lite` has no analyser, so an address there came from somewhere else, and following it
    sends unscrubbed text to a host nobody chose. The positive half matters as much: on
    `standard` an override is an ordinary choice and must not be refused.

    Delete this and an environment file copied from another install sends text off the
    host."""
    address = "http://192.0.2.10:3000"

    conflicts = presidio_config_conflicts("lite", {PRESIDIO_ADDRESS_SETTING: address})
    assert len(conflicts) == 1
    assert PRESIDIO_ADDRESS_SETTING in conflicts[0]
    assert presidio_config_conflicts("lite", {PRESIDIO_ADDRESS_SETTING: "  "}) == ()
    assert presidio_config_conflicts("standard", {PRESIDIO_ADDRESS_SETTING: address}) == ()
    assert "nobody here chose" in AN_ANALYSER_ADDRESS_ON_LITE_IS_SOMEBODY_ELSES_HOST

    base = {"database_url": "postgresql+psycopg://u:p@h/db", "valkey_url": "redis://h/0"}
    problems = check("production", {**base, "profile": "lite", PRESIDIO_ADDRESS_SETTING: address})
    assert any(PRESIDIO_ADDRESS_SETTING in one.problem for one in problems)
    fine = check("production", {**base, "profile": "full", PRESIDIO_ADDRESS_SETTING: address})
    assert not any(PRESIDIO_ADDRESS_SETTING in one.problem for one in fine)


def test_the_address_is_a_setting_an_override_wins_and_lite_has_none() -> None:
    """The address is configuration read in one place: an install's value wins, a blank takes
    the product's own service, and `lite` gets None so a caller must handle an absent analyser
    rather than dial a name that does not resolve.

    Delete this and the default can shadow an install's override, or `lite` can be handed a
    hostname that exists on no network it has."""
    assert PRESIDIO_ADDRESS_SETTING in Settings.model_fields
    assert analyzer_address("full", "http://analyser.internal:3000") == (
        "http://analyser.internal:3000"
    )
    assert analyzer_address("full", "   ") == f"http://{PRESIDIO_SERVICE}:{PRESIDIO_PORT}"
    assert analyzer_address("lite") is None
    assert analyzer_address("lite", "http://analyser.internal:3000") is None
