"""Every install setting the realm importer reads reaches the container the importer runs in.

`brain.ops.realm_import.importable_realm` reads `INSTALL_OIDC_REDIRECT_URIS` through
`brain.install.value_of`, which has no default and raises when the value is absent. The
`keycloak-realm` service in `docker-compose.keycloak.yml` had no environment at all, so from
2026-09-09 the importer exited 1 on every start and Keycloak, which waits for the importer to
complete, was left "Created" and never ran. Measured on the owner's server, where it took an
unrelated restart of the stack to surface: the service had been running since before the setting
was required.

The names are read out of the importer's source rather than listed here, so a second setting the
importer starts reading fails this test on the day it is added, not on the next restart of
somebody's server.

Task ids: none
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml

import brain.ops.realm_import as realm_import
from brain.install import BY_NAME

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.keycloak.yml"
IMPORTER_SERVICE = "keycloak-realm"


def settings_the_importer_reads() -> set[str]:
    """The names `realm_import` hands to `value_of`, resolving the constants it names them by."""
    tree = ast.parse(Path(realm_import.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "value_of"
            and node.args
        ):
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                names.add(argument.value)
            elif isinstance(argument, ast.Name):
                names.add(str(getattr(realm_import, argument.id)))
    return names


def environment_of(service: dict[str, Any]) -> dict[str, str]:
    """A service's environment, whether written as a mapping or as a list of NAME=value."""
    raw = service.get("environment") or {}
    if isinstance(raw, list):
        pairs: dict[str, str] = {}
        for entry in raw:
            name, _, value = str(entry).partition("=")
            pairs[name] = value
        return pairs
    return {str(key): str(value) for key, value in raw.items()}


def missing_settings(compose: dict[str, Any], needed: set[str]) -> list[str]:
    """Each setting the importer needs that its service is not given, or is given with a default."""
    service = compose.get("services", {}).get(IMPORTER_SERVICE, {})
    environment = environment_of(service)
    findings = []
    for name in sorted(needed):
        value = environment.get(name)
        if value is None:
            findings.append(f"{name} is not passed to {IMPORTER_SERVICE}")
        elif value == f"${{{name}:-}}" and BY_NAME[name].default:
            # A declared default answers a blank, which `brain.install.value_of` reads as unset.
            continue
        elif not value.startswith(f"${{{name}:?"):
            findings.append(f"{name} is passed to {IMPORTER_SERVICE} without being required")
    return findings


def test_every_setting_the_realm_importer_reads_reaches_its_container() -> None:
    """The rule over the real files. Delete this and a setting the importer starts reading can be
    left off the compose file again, and the first anybody hears of it is Keycloak never
    starting on a client's server after a restart."""
    needed = settings_the_importer_reads()
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))

    assert "INSTALL_OIDC_REDIRECT_URIS" in needed
    assert missing_settings(compose, needed) == []


def test_a_setting_left_off_the_importer_or_given_a_default_is_a_finding() -> None:
    """The refusal sibling, so the rule above is not satisfied by a check that finds nothing.
    Delete this and `missing_settings` can return an empty list for every file."""
    needed = {"INSTALL_OIDC_REDIRECT_URIS"}
    absent = {"services": {IMPORTER_SERVICE: {"image": "x"}}}
    defaulted = {
        "services": {
            IMPORTER_SERVICE: {
                "environment": {
                    "INSTALL_OIDC_REDIRECT_URIS": "${INSTALL_OIDC_REDIRECT_URIS:-https://x}"
                }
            }
        }
    }
    as_list = {
        "services": {
            IMPORTER_SERVICE: {
                "environment": ["INSTALL_OIDC_REDIRECT_URIS=${INSTALL_OIDC_REDIRECT_URIS:?set it}"]
            }
        }
    }

    assert missing_settings(absent, needed) == [
        "INSTALL_OIDC_REDIRECT_URIS is not passed to keycloak-realm"
    ]
    assert missing_settings(defaulted, needed) == [
        "INSTALL_OIDC_REDIRECT_URIS is passed to keycloak-realm without being required"
    ]
    assert missing_settings(as_list, needed) == []


def test_the_importer_is_found_reading_its_setting_so_the_scan_is_not_blind() -> None:
    """The positive case for the scan. If the parser stopped finding `value_of` calls, the rule
    above would pass with nothing needed. Delete this and a scan reading the wrong file passes."""
    assert settings_the_importer_reads() == {
        realm_import.ORIGIN_SETTING,
        realm_import.REALM_SETTING,
        realm_import.CLIENT_ID_SETTING,
        realm_import.BROKER_SETTING,
        realm_import.BROKER_CLIENT_SETTING,
        realm_import.STAFF_SOURCE_SETTING,
        realm_import.STAFF_LOCATION_SETTING,
    }


def test_a_blank_pass_through_is_accepted_only_for_a_setting_with_a_declared_default() -> None:
    """`INSTALL_OIDC_REALM` has a default, so `${INSTALL_OIDC_REALM:-}` hands the importer a blank
    it reads as the default. The redirect URIs have none, so the same spelling for them is still a
    finding. Delete this and the exemption can widen to a required setting, and Keycloak waits on
    an importer that exits 1 on a server nobody is watching."""
    blank = {
        "services": {
            IMPORTER_SERVICE: {
                "environment": {
                    "INSTALL_OIDC_REALM": "${INSTALL_OIDC_REALM:-}",
                    "INSTALL_OIDC_REDIRECT_URIS": "${INSTALL_OIDC_REDIRECT_URIS:-}",
                }
            }
        }
    }

    assert missing_settings(blank, {"INSTALL_OIDC_REALM", "INSTALL_OIDC_REDIRECT_URIS"}) == [
        "INSTALL_OIDC_REDIRECT_URIS is passed to keycloak-realm without being required"
    ]
