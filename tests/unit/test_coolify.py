"""A Coolify deployment of the compose stack, held to the files and to the page (M30.1.1, M30.1.2).

Every table on `docs/install/coolify.md` is computed from the compose files each profile composes
and compared in both directions: a row the files do not support fails, and so does something the
files need that has no row. The checks in `brain.ops.coolify` are also run over every profile,
and each refusal is built from a real profile's files with one thing changed.

Task ids: M30.1.1, M30.1.2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.installer import INSTALL_SETTINGS, MOUNTED_SETTINGS, PLAN
from brain.deployment.requirements import COMPOSE_FILES_FOR, files_for
from brain.ops.coolify import (
    A_PANEL_ONLY_KEY_IN_A_PRODUCT_FILE_BREAKS_EVERY_OTHER_INSTALL,
    A_PUBLISHED_PORT_ANSWERS_BESIDE_THE_PROXY,
    AN_ENVIRONMENT_ENTRY_BEATS_THE_IMAGE,
    ROUTES,
    coolify_gaps,
    external_networks,
    host_files,
    one_shot_services,
    route_gaps,
    routes_for,
    stored_defaults,
)
from brain.ops.install_docs import bare, minted_variables, table_after
from brain.ops.tunnel import APPLICATION_PORT, IDENTITY_PORT

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs" / "install" / "coolify.md"

MINTED = "<!-- checked: the values the installer mints and a Coolify install mints by hand -->"
DEFAULTS = "<!-- checked: the non-empty defaults Coolify stores on the first save -->"
FILES = "<!-- checked: the files a Coolify install puts on the server before the first deploy -->"
ROUTED = "<!-- checked: the services Coolify routes, and the port each listens on -->"
NETWORKS = "<!-- checked: the networks the files expect the server to have already -->"
ONE_SHOTS = "<!-- checked: the services that finish and show as exited -->"


def profile(name: str) -> dict[str, Any]:
    return {
        one: yaml.safe_load((REPO / one).read_text(encoding="utf-8")) for one in files_for(name)
    }


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def by_profile(compute: Any) -> dict[Any, set[str]]:
    """What a check returns for each profile, as item against the profiles that have it."""
    found: dict[Any, set[str]] = {}
    for name in COMPOSE_FILES_FOR:
        for item in compute(profile(name)):
            found.setdefault(item, set()).add(name)
    return found


def profiles_cell(names: set[str]) -> str:
    return ", ".join(one for one in COMPOSE_FILES_FOR if one in names)


# ================================================================= the checks, per profile
@pytest.mark.parametrize("name", sorted(COMPOSE_FILES_FOR))
def test_no_profile_carries_anything_a_coolify_stored_copy_turns_into_a_silent_failure(
    name: str,
) -> None:
    """The positive case over every profile's real files. Delete this and each refusal below can
    pass against a check that refuses the deployment as well."""
    assert coolify_gaps(profile(name)) == ()


def test_the_routed_ports_are_the_ones_the_tunnel_and_the_compose_files_already_use() -> None:
    """The application's 8000 and the identity provider's 8080 are asserted against the tunnel's
    constants, which were read off the same services, rather than against `ROUTES` itself.
    Delete this and both tables can move together to a port nothing listens on."""
    assert ROUTES["app"] == APPLICATION_PORT
    assert ROUTES["keycloak"] == IDENTITY_PORT
    assert route_gaps(profile("full")) == ()


def test_a_panel_only_key_in_a_product_file_is_refused() -> None:
    """`exclude_from_hc` is Coolify's, and compose refuses it. Delete this and a tidy health
    display on one panel stops every install that runs compose directly."""
    files = profile("standard")
    files["docker-compose.keycloak.yml"]["services"]["keycloak-realm"]["exclude_from_hc"] = True

    found = coolify_gaps(files)
    assert any(
        A_PANEL_ONLY_KEY_IN_A_PRODUCT_FILE_BREAKS_EVERY_OTHER_INSTALL in one for one in found
    )


def test_a_published_port_is_refused() -> None:
    """Delete this and a port answering beside the proxy, with no certificate, passes."""
    files = profile("lite")
    files["docker-compose.lite.yml"]["services"]["app"]["ports"] = ["8000:8000"]

    assert any(A_PUBLISHED_PORT_ANSWERS_BESIDE_THE_PROXY in one for one in coolify_gaps(files))


def test_the_commit_variable_in_an_environment_is_refused() -> None:
    """The staging finding: the panel froze it at `unknown`. Delete this and it comes back."""
    files = profile("lite")
    environment = files["docker-compose.lite.yml"]["services"]["app"]["environment"]
    environment["BRAIN_COMMIT_SHA"] = "${BRAIN_COMMIT_SHA:-unknown}"

    assert any(AN_ENVIRONMENT_ENTRY_BEATS_THE_IMAGE in one for one in coolify_gaps(files))


def test_a_relative_bind_mount_is_refused() -> None:
    """Delete this and a settings file mounted from beside the compose file, which a stored copy
    has no directory for, passes as a Coolify deployment."""
    files = profile("standard")
    files["docker-compose.objectstore.yml"]["services"]["seaweedfs"]["volumes"] = [
        "./ops/seaweedfs/s3.json:/etc/seaweedfs/s3.json:ro"
    ]

    assert any("./ops/seaweedfs/s3.json" in one for one in coolify_gaps(files))


def test_a_routed_service_whose_port_moved_is_refused() -> None:
    """Delete this and the guide can tell an operator to route the identity provider to a port it
    no longer listens on."""
    files = profile("standard")
    files["docker-compose.keycloak.yml"]["services"]["keycloak"]["expose"] = ["9090"]

    assert any(
        "'keycloak' is given a Coolify domain on port 8080" in one for one in route_gaps(files)
    )


def test_a_default_is_found_wherever_it_is_written_and_an_empty_one_is_not() -> None:
    """A default in a command or a label is kept by the panel as surely as one in an environment.
    Delete this and the defaults table can miss one written anywhere but `environment`."""
    files = {
        "a.yml": {
            "services": {
                "one": {
                    "command": ["run", "--level=${LEVEL:-info}"],
                    "environment": {"EMPTY": "${EMPTY:-}", "REQUIRED": "${REQUIRED:?x}"},
                }
            }
        }
    }

    assert stored_defaults(files) == {"LEVEL": "info"}


# ===================================================================== the page, both ways
def test_the_page_lists_exactly_the_values_the_installer_mints() -> None:
    """Delete this and a sixth minted value is one a Coolify install never generates, and the
    stack starts with it empty."""
    rows = {bare(row[0]) for row in table_after(page(), MINTED)}

    assert rows == set(minted_variables(PLAN))


def test_the_page_lists_exactly_the_defaults_the_files_carry() -> None:
    """Delete this and a default a later release adds is one no Coolify install is told to
    check after an update."""
    rows = {bare(row[0]): bare(row[1]) for row in table_after(page(), DEFAULTS)}
    wanted: dict[str, str] = {}
    for name in COMPOSE_FILES_FOR:
        wanted.update(stored_defaults(profile(name)))

    assert rows == wanted


def test_the_page_lists_exactly_the_settings_files_and_who_reads_them() -> None:
    """Held against the mounts and against the installer's own list, which is what a plain server
    gets. Delete this and a fifth settings file is an empty directory on every Coolify install."""
    rows = {(bare(row[0]), bare(row[1]), row[2].strip()) for row in table_after(page(), FILES)}
    wanted = {
        (path, service, profiles_cell(names))
        for (path, service), names in by_profile(host_files).items()
    }

    assert rows == wanted
    assert {path for path, _, _ in rows} == {
        f"{INSTALL_SETTINGS}/{one}" for one in MOUNTED_SETTINGS
    }


def test_the_page_routes_exactly_the_services_a_browser_reaches() -> None:
    """Delete this and a service the proxy must route can be missing from the page, or a port in
    it can differ from the one the files declare."""
    rows = {(bare(row[0]), bare(row[1]), row[2].strip()) for row in table_after(page(), ROUTED)}
    wanted = {
        (service, str(port), profiles_cell(names))
        for (service, port), names in by_profile(lambda f: routes_for(f).items()).items()
    }

    assert rows == wanted


def test_the_page_names_the_networks_and_the_helpers_the_files_have() -> None:
    """Delete this and the Coolify network the identity provider needs, or a helper that exits,
    can change with nothing on the page following it."""
    networks = {(bare(row[0]), row[1].strip()) for row in table_after(page(), NETWORKS)}
    helpers = {(bare(row[0]), row[1].strip()) for row in table_after(page(), ONE_SHOTS)}

    assert networks == {
        (one, profiles_cell(names)) for one, names in by_profile(external_networks).items()
    }
    assert helpers == {
        (one, profiles_cell(names)) for one, names in by_profile(one_shot_services).items()
    }
