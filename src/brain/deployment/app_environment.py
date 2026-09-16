"""What the application container has to be handed, and the checks that it is.

**A setting the application reads and a compose file does not name never reaches the
container**, and nothing anywhere says so. Compose hands a service the variables its
`environment` names and no others, so a line in an install's environment file that no compose
file names is a line nothing reads. Until 2026-09-16 the application service in both base
files named five: the database and cache addresses, the environment, the role password and the
image. So the installer minted `BRAIN_SETUP_SECRET` and `BRAIN_SETUP_ISSUED_AT` into the
environment file, printed the code to the person at the terminal, and started a container that
had no code to accept, which `brain.setup_wizard` answers by refusing the wizard. And
`brain.app` records the same absence measured on a deployed container on 2026-09-15: it carried
the database and cache addresses and no `INSTALL_OIDC_ISSUER`. Every `INSTALL_` value was in the
same position, as was every `BRAIN_` setting past the first. Found on the owner's staging
install while the vault credentials were being built; nothing about it was particular to that
install, because it is a fact about the two files every install composes.

**The list is derived, and the exemptions are argued.** `application_reads` is every field of
`brain.settings.Settings`, under the names pydantic itself would read it from, and every setting
`brain.install.INSTALLATION` declares. A setting added to either is a setting
`passthrough_gaps` reports as not passed on the day it is added, which is the recurrence this
module exists to stop. A field is left out of the base files only with a sentence in
`NOT_PASSED_BY_A_PROFILE`, and a field in that table that a base file passes anyway is reported
too, because the reason written there is a claim about the file.

**Passed under its own name, and a key naming a different variable is not passed.** A key
`BRAIN_SETUP_SECRET: ${BRAIN_SETUP_CODE:-}` reads as handed through to anybody scanning the
keys, and delivers whatever an unrelated line says. The two addresses the file composes from
service names are the one exception, and `COMPOSED_BY_THE_FILE` names them.

**`${NAME:-}` and never `${NAME:?}` for an installation value.** An unset issuer is an install
that starts unready for sign-in rather than one that does not start, which
`brain.app.AN_INSTALL_THAT_CANNOT_CHECK_A_SIGN_IN_IS_UNREADY_RATHER_THAN_STOPPED` argues, and a
required interpolation would turn that into a compose file that refuses every install that has
not set it, the setup wizard with it. A blank then reads as unset:
`brain.settings.A_BLANK_VARIABLE_IS_AN_UNSET_ONE` is the half of this fix inside the process,
without which the setup code's own instant, left blank, stops the application starting.

**The vault is an overlay, `docker-compose.vault.yml`.** Its network is created by the vault's
own compose project, so it is external here and exists only where the vault runs, and a base
file naming it stops every install without one. The overlay requires both variables, because
composing it in is the choice, and it adds one network and nothing else. `vault_overlay_gaps`
holds that, and the release's update and rollback scripts compose it when the environment file
names an address, as they do for the tunnel's token; see `VAULT_CHOICE`.

Rejected: `env_file: .env` on the application service. It is one line, and it hands the
container every line of the file: the database superuser's password, the identity provider's
bootstrap administrator and the tunnel's token, none of which the application reads and every
one of which is then in its process environment and in anything that dumps it. On a deployment
panel that stores its own copy of the compose file the relative path also resolves to nothing,
which is `brain.ops.compose.A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE` again.

Rejected: passing the three model provider keys. `brain.ops.provider_keys.load_into_environment`
does not overwrite a variable the environment already sets, and `names_in_environment` reports
one as outranking the vault, so a key named here even blank-by-default would make the vault's
copy the one that loses on an install whose file ever carried one. They reach the process from
the vault; see `ops/openbao/credential-slots.md`.

**Scope: the `app` service in the base files a client's profile composes.**
`docker-compose.staging.yml` is this repository's own staging stack and no profile composes it,
which is `brain.deployment.release._compose_rules`' reason for leaving it out of the archive.
The two workers run the same image with an environment of their own and are not checked here;
whether a job they run reads an `INSTALL_` value is an open question this module does not answer.

Task ids: M41.1.3, M42.5.3, M5.1.2
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from pydantic import AliasChoices, AliasPath
from pydantic.fields import FieldInfo

from brain.deployment.requirements import files_for
from brain.install import INSTALLATION
from brain.ops.wiring import PROFILES
from brain.settings import Settings

# ------------------------------------------------------------------- the files and the names

#: The service every check here is about, by the name every compose file gives it.
APPLICATION_SERVICE: Final = "app"

#: The overlay that hands the application a vault, by the name an operator passes with `-f`.
VAULT_OVERLAY: Final = "docker-compose.vault.yml"

#: The vault's own compose project. Its network's name is what the overlay has to join.
VAULT_PROJECT: Final = "ops/openbao/compose.yml"

#: The vault's network, as `VAULT_PROJECT` names it. Held equal to that file by a test.
VAULT_NETWORK: Final = "brain-vault"

#: The line in an install's environment file that records the vault was chosen. See
#: `AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT`.
VAULT_CHOICE: Final = "BRAIN_VAULT_ADDRESS"

#: The two settings the overlay hands the application, in the order the file writes them.
VAULT_SETTINGS: Final[tuple[str, ...]] = ("BRAIN_VAULT_ADDRESS", "BRAIN_VAULT_TOKEN")

#: `${NAME}`, `${NAME:-default}` or `${NAME:?message}`, as the whole value and nothing else.
INTERPOLATION: Final = re.compile(r"\A\$\{([A-Z][A-Z0-9_]*)(?:(:[-?])([^}]*))?\}\Z")

# ------------------------------------------------------------------ written-down reasons

#: Why a setting nobody names in a compose file is a defect and not a default.
A_SETTING_NO_COMPOSE_FILE_NAMES_NEVER_REACHES_THE_CONTAINER: Final = (
    "Compose hands a service the variables its environment names and no others. A line in the "
    "install's environment file that no compose file names is read by nothing, and the setting "
    "takes its default with every step of the install reporting success. The installer minted "
    "the setup code into that file and printed it, and the container it started had no code "
    "to accept."
)

#: Why an installation value is passed with a default and never required.
AN_UNSET_INSTALLATION_VALUE_MUST_NOT_STOP_THE_STACK: Final = (
    "An install with no issuer starts unready for sign-in, which is how an operator reaches the "
    "status page and the setup wizard to fix it. ${NAME:?} refuses to compose the stack at all "
    "while the value is unset, so the application an operator would fix it from never starts."
)

#: Why the vault overlay is chosen by a line in the environment file.
AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT: Final = (
    "The overlay refuses to compose without the vault's address, so an address in the "
    "environment file is the choice and nothing beside it is. An update that recreated the "
    "application without the overlay would start it with no vault, and every provider key the "
    "console had put there would stop being loaded with the update reporting success."
)

# ------------------------------------------------------------------------ the exemptions

#: Every `Settings` field the base files deliberately do not pass, and why. Keyed by field.
NOT_PASSED_BY_A_PROFILE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "commit_sha": (
            "The image carries its own commit, and an environment entry beats an image's ENV, "
            "so a deployment panel that resolved it once at save time would pin every later "
            "container to that answer. See brain.settings.Settings.resolved_commit."
        ),
        "vault_address": (
            f"Passed by {VAULT_OVERLAY}, composed in only where the vault runs, because the "
            "network it has to be reached on exists only there."
        ),
        "vault_token": f"Passed by {VAULT_OVERLAY}, for the reason vault_address is.",
    }
)

#: The fields whose value the base files build from service names rather than pass through.
COMPOSED_BY_THE_FILE: Final[frozenset[str]] = frozenset({"database_url", "valkey_url"})


# ------------------------------------------------------------------------ the decisions


def accepted_names(name: str, field: FieldInfo) -> frozenset[str]:
    """Every environment variable pydantic-settings would populate this field from.

    Derived from the model rather than typed out: a field with no alias is the prefix and its
    name, a field with `AliasChoices` is exactly the names it lists, and neither is remembered by
    whoever adds the next one. The same reading `tests/unit/test_config.py` makes of
    `.env.example`.
    """
    alias = field.validation_alias
    if isinstance(alias, AliasChoices):
        return frozenset(str(one) for one in alias.choices if not isinstance(one, AliasPath))
    if isinstance(alias, str):
        return frozenset({alias})
    prefix = str(Settings.model_config.get("env_prefix") or "")
    return frozenset({f"{prefix}{name}".upper()})


def application_reads() -> dict[str, frozenset[str]]:
    """Every setting the application reads, by field or setting name, with the names it takes.

    `Settings` fields under their field names and `INSTALLATION` settings under their own, so a
    finding can name what was dropped in the words the declaration uses.
    """
    reads = {
        name: accepted_names(name, field) for name, field in sorted(Settings.model_fields.items())
    }
    reads.update({one.name: frozenset({one.name}) for one in INSTALLATION})
    return reads


def application_files(profiles: tuple[str, ...] = PROFILES) -> tuple[str, ...]:
    """The base files a client's profile composes that could declare the application.

    Every profile's first file, which is the one declaring `app`, and never an overlay or the
    staging stack. Read off `files_for` rather than listed, so a profile added there is checked
    the same day.
    """
    return tuple(sorted({files_for(profile)[0] for profile in profiles}))


def environment_of(document: Mapping[str, Any], service: str) -> dict[str, str] | None:
    """One service's `environment`, in either compose spelling, or None when it has none."""
    services = document.get("services")
    body = services.get(service) if isinstance(services, Mapping) else None
    if not isinstance(body, Mapping):
        return None
    environment = body.get("environment")
    if isinstance(environment, Mapping):
        return {str(key): "" if value is None else str(value) for key, value in environment.items()}
    if isinstance(environment, list):
        pairs = (str(one).partition("=") for one in environment)
        return {key: value for key, _, value in pairs}
    return None


def passthrough_gaps(
    document: Mapping[str, Any],
    *,
    name: str = "the compose file",
    reads: Mapping[str, frozenset[str]] | None = None,
) -> tuple[str, ...]:
    """Every setting the application reads that this base file does not hand it, in name order.

    Empty for a file that passes everything. Each finding names the setting and the rule, so a
    test that breaks one line can assert which one was caught. See
    `A_SETTING_NO_COMPOSE_FILE_NAMES_NEVER_REACHES_THE_CONTAINER`.
    """
    environment = environment_of(document, APPLICATION_SERVICE)
    if environment is None:
        return (f"{name} gives the {APPLICATION_SERVICE} service no environment at all",)
    found: list[str] = []
    for setting, names in sorted((reads if reads is not None else application_reads()).items()):
        passed = sorted(names & environment.keys())
        if setting in NOT_PASSED_BY_A_PROFILE:
            if passed:
                found.append(
                    f"{name} passes {passed[0]}, and it is not passed by a profile: "
                    f"{NOT_PASSED_BY_A_PROFILE[setting]}"
                )
            continue
        if not passed:
            found.append(
                f"{name} does not pass {sorted(names)[0]} to {APPLICATION_SERVICE}, so the "
                f"setting {setting} never reaches the container. "
                f"{A_SETTING_NO_COMPOSE_FILE_NAMES_NEVER_REACHES_THE_CONTAINER}"
            )
            continue
        if setting in COMPOSED_BY_THE_FILE:
            continue
        key = passed[0]
        matched = INTERPOLATION.match(environment[key])
        if matched is None or matched.group(1) != key:
            found.append(
                f"{name} names {key} and hands it {environment[key]!r}, which is not the "
                f"variable {key}, so a value set for {key} never arrives"
            )
            continue
        if setting.startswith("INSTALL_") and matched.group(2) == ":?":
            found.append(
                f"{name} requires {key} with ':?'. "
                f"{AN_UNSET_INSTALLATION_VALUE_MUST_NOT_STOP_THE_STACK}"
            )
    return tuple(found)


def required_variable(value: str) -> str | None:
    """The variable a value requires in the `${NAME:?message}` form, or None."""
    matched = INTERPOLATION.match(value)
    if matched is None or matched.group(2) != ":?":
        return None
    return matched.group(1)


def vault_overlay_gaps(
    document: Mapping[str, Any], *, vault_network: str = VAULT_NETWORK
) -> tuple[str, ...]:
    """Every way the vault overlay does more or less than hand the application a vault.

    Empty for the file as written. `vault_network` is the name the vault's own project gives its
    network, handed in by whoever parsed that file, so the two cannot drift apart unnoticed.
    """
    services = document.get("services")
    if not isinstance(services, Mapping) or APPLICATION_SERVICE not in services:
        return (f"{VAULT_OVERLAY} does not add to the {APPLICATION_SERVICE} service",)
    found: list[str] = []
    others = sorted(str(one) for one in services if one != APPLICATION_SERVICE)
    if others:
        found.append(
            f"{VAULT_OVERLAY} declares {others} beside {APPLICATION_SERVICE!r}, and a service "
            "on the vault's network is a service that can ask the vault"
        )
    body = services[APPLICATION_SERVICE]
    keys = sorted(str(one) for one in body) if isinstance(body, Mapping) else []
    extra = [one for one in keys if one not in {"environment", "networks"}]
    if extra:
        found.append(
            f"{VAULT_OVERLAY} sets {extra} on {APPLICATION_SERVICE}, which changes the "
            "profile's application for every install that chooses a vault"
        )
    environment = environment_of(document, APPLICATION_SERVICE) or {}
    for setting in VAULT_SETTINGS:
        if required_variable(environment.get(setting, "")) != setting:
            found.append(
                f"{VAULT_OVERLAY} does not require {setting} in the form "
                f"${{{setting}:?message}}, so a half-chosen vault starts an application that "
                "keeps no credential rather than failing when the stack is composed"
            )
    unexpected = sorted(set(environment) - set(VAULT_SETTINGS))
    if unexpected:
        found.append(f"{VAULT_OVERLAY} hands the application {unexpected} as well as the vault")
    networks = body.get("networks") if isinstance(body, Mapping) else None
    joined = sorted(str(one) for one in networks) if isinstance(networks, list | Mapping) else []
    if joined != [vault_network]:
        found.append(
            f"{VAULT_OVERLAY} joins {APPLICATION_SERVICE} to {joined}, and it must join "
            f"{vault_network!r} alone: the profile already gives it every other network"
        )
    declared = document.get("networks")
    network = declared.get(vault_network) if isinstance(declared, Mapping) else None
    if not (
        isinstance(network, Mapping)
        and network.get("external") is True
        and network.get("name") == vault_network
    ):
        found.append(
            f"{VAULT_OVERLAY} does not declare {vault_network!r} as external under that name, "
            "so compose would create a second network the vault is not on"
        )
    return tuple(found)


def vault_network_of(document: Mapping[str, Any]) -> str | None:
    """The name the vault's own compose project gives its one network, or None."""
    networks = document.get("networks")
    if not isinstance(networks, Mapping) or len(networks) != 1:
        return None
    [(key, body)] = networks.items()
    named = body.get("name") if isinstance(body, Mapping) else None
    return str(named) if named else str(key)
