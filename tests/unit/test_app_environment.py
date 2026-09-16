"""What the application container is handed, held to the compose files, the vault overlay, the
scripts that compose it and the steps a person follows.

Every assertion reads parsed YAML or the rendered script, never the raw text of a compose file.
The files' own comments name `BRAIN_COMMIT_SHA`, `env_file` and the vault's variables to explain
why each is where it is, so a substring check over a file would be satisfied by its explanation.

Each refusal has a positive sibling, and the first test of each half is it: the files as written
are clean, so a checker that refused everything fails there.

Task ids: M41.1.3, M42.5.3, M5.1.2
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.app_environment import (
    AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT,
    APPLICATION_SERVICE,
    COMPOSED_BY_THE_FILE,
    NOT_PASSED_BY_A_PROFILE,
    VAULT_CHOICE,
    VAULT_NETWORK,
    VAULT_OVERLAY,
    VAULT_PROJECT,
    VAULT_SETTINGS,
    application_files,
    application_reads,
    environment_of,
    passthrough_gaps,
    required_variable,
    vault_network_of,
    vault_overlay_gaps,
)
from brain.deployment.installer import INSTALL_ENV_FILE, PLAN
from brain.deployment.release import included_by, refused_by, render_rollback, render_update
from brain.deployment.requirements import files_for
from brain.install import INSTALLATION
from brain.ops.install_docs import minted_variables
from brain.ops.wiring import PROFILES
from brain.settings import Settings, settings_from
from tests.unit.test_deployment_release import REPOSITORY, TOKEN, an_install, run_script

REPO = Path(__file__).resolve().parents[2]


def load(name: str) -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}
    return parsed


def with_environment(name: str, **changes: str | None) -> dict[str, Any]:
    """A base file with the application's environment edited, None deleting the key."""
    document = copy.deepcopy(load(name))
    environment = document["services"][APPLICATION_SERVICE]["environment"]
    for key, value in changes.items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = value
    return document


def passed_names(document: dict[str, Any]) -> set[str]:
    return set(environment_of(document, APPLICATION_SERVICE) or {})


# ============================================================================ the base files
def test_the_base_files_are_the_two_every_profile_starts_from() -> None:
    """Delete this and `application_files` can return nothing, and every test below that is
    parametrised over it checks no file and passes."""
    assert application_files() == ("docker-compose.lite.yml", "docker-compose.yml")
    assert {files_for(profile)[0] for profile in PROFILES} == set(application_files())


@pytest.mark.parametrize("name", application_files())
def test_every_setting_the_application_reads_is_handed_to_its_container(name: str) -> None:
    """The defect, as the positive case. Until 2026-09-16 the application service named five
    variables, so the setup code the installer minted and printed, the identity provider's issuer
    and every other installation value stayed in the environment file and never reached the
    process. Delete this and the list goes back to whatever somebody last remembered."""
    assert passthrough_gaps(load(name), name=name) == ()


@pytest.mark.parametrize("name", application_files())
@pytest.mark.parametrize(
    "dropped", ["BRAIN_SETUP_SECRET", "BRAIN_SETUP_ISSUED_AT", "INSTALL_OIDC_ISSUER", "BRAIN_ENV"]
)
def test_a_setting_dropped_from_the_application_is_reported_by_name(
    name: str, dropped: str
) -> None:
    """The three the defect was found through, and one that was always passed. Delete this and
    the check can pass a file by counting keys, or report a drop without saying which, and the
    person reading the failure has to diff the file to find out."""
    [finding] = passthrough_gaps(with_environment(name, **{dropped: None}), name=name)
    assert f"does not pass {dropped} " in finding


def test_a_setting_added_to_the_application_later_is_a_finding_until_a_file_passes_it() -> None:
    """The recurrence, which is the point of deriving the list. A setting that exists in the
    reads and in no file is reported. Delete this and `application_reads` can be a fixed list,
    which is right until the next setting."""
    reads = {**application_reads(), "a_setting_nobody_passed": frozenset({"BRAIN_NEW_THING"})}
    [finding] = passthrough_gaps(load("docker-compose.yml"), reads=reads)
    assert "BRAIN_NEW_THING" in finding
    assert "a_setting_nobody_passed" in finding


def test_the_reads_are_every_settings_field_and_every_installation_value() -> None:
    """Delete this and `application_reads` can leave out one of its two sources, and every
    setting from the other passes the check by never being asked about."""
    reads = application_reads()
    assert set(Settings.model_fields) | {one.name for one in INSTALLATION} == set(reads)
    assert reads["database_url"] == {"BRAIN_DATABASE_URL", "DATABASE_URL"}
    assert reads["setup_secret"] == {"BRAIN_SETUP_SECRET"}
    assert reads["app_role_password"] == {"APP_ROLE_PASSWORD"}
    assert reads["INSTALL_OIDC_ISSUER"] == {"INSTALL_OIDC_ISSUER"}


def test_a_key_handed_another_variable_is_not_passed() -> None:
    """A key that reads as passed and delivers an unrelated line. Delete this and
    `BRAIN_SETUP_SECRET: ${BRAIN_SETUP_CODE:-}` satisfies the check and hands the container
    nothing the installer wrote."""
    document = with_environment("docker-compose.yml", BRAIN_SETUP_SECRET="${BRAIN_SETUP_CODE:-}")
    [finding] = passthrough_gaps(document)
    assert "BRAIN_SETUP_SECRET" in finding
    assert "is not the variable" in finding


def test_an_installation_value_required_with_a_question_mark_is_reported() -> None:
    """See `AN_UNSET_INSTALLATION_VALUE_MUST_NOT_STOP_THE_STACK`. Delete this and the issuer can
    be made required, and every install that has not set one, the setup wizard with it, stops
    at compose time instead of starting unready for sign-in."""
    document = with_environment(
        "docker-compose.yml", INSTALL_OIDC_ISSUER="${INSTALL_OIDC_ISSUER:?set it}"
    )
    [finding] = passthrough_gaps(document)
    assert "INSTALL_OIDC_ISSUER" in finding
    assert "':?'" in finding


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("BRAIN_COMMIT_SHA", "${BRAIN_COMMIT_SHA:-unknown}"),
        ("BRAIN_VAULT_ADDRESS", "${BRAIN_VAULT_ADDRESS:-}"),
        ("BRAIN_VAULT_TOKEN", "${BRAIN_VAULT_TOKEN:-}"),
    ],
)
def test_a_setting_written_down_as_not_passed_is_reported_when_a_base_file_passes_it(
    key: str, value: str
) -> None:
    """The exemptions are claims about the files, so they are checked in the other direction.
    Delete this and the commit can be passed again, which pins every later container to the
    answer a deployment panel resolved once, or the vault's pair can move into a base file and
    the overlay's required form stops being the only door."""
    [finding] = passthrough_gaps(with_environment("docker-compose.yml", **{key: value}))
    assert key in finding
    assert "not passed by a profile" in finding


def test_every_exemption_names_a_real_field() -> None:
    """Delete this and a renamed field leaves a stale exemption behind while the new name is
    silently required, or silently exempt under a name nothing has."""
    assert set(NOT_PASSED_BY_A_PROFILE) <= set(Settings.model_fields)
    assert set(COMPOSED_BY_THE_FILE) <= set(Settings.model_fields)


@pytest.mark.parametrize(
    "field",
    sorted(set(Settings.model_fields) - set(NOT_PASSED_BY_A_PROFILE) - COMPOSED_BY_THE_FILE),
)
def test_a_passed_setting_left_blank_still_starts_the_application_on_its_default(
    field: str,
) -> None:
    """See `brain.settings.A_BLANK_VARIABLE_IS_AN_UNSET_ONE`. Every setting is handed over as
    `${NAME:-}`, so an unset one arrives blank. Delete this and the setup code's own instant, the
    release check or the profile, arriving blank, refuses the settings object and the
    application does not start on any install that left one of them alone."""
    [name] = sorted(application_reads()[field])[:1]
    handed = settings_from({name: ""})
    assert getattr(handed, field) == Settings.model_fields[field].get_default(
        call_default_factory=True
    )


def test_every_value_the_installer_mints_that_the_application_reads_reaches_it() -> None:
    """The join the defect broke, read from both ends: the install plan's mint step and the
    compose file. Delete this and the installer can mint and print a value that no container
    receives, with every step of the install reporting success."""
    names = {name for names in application_reads().values() for name in names}
    minted = minted_variables(PLAN) & names
    assert {"BRAIN_SETUP_SECRET", "BRAIN_SETUP_ISSUED_AT", "APP_ROLE_PASSWORD"} <= minted
    for name in application_files():
        assert minted <= passed_names(load(name)), name


# ============================================================================ the vault overlay
def vault_network() -> str | None:
    return vault_network_of(load(VAULT_PROJECT))


def overlay(**changes: Any) -> dict[str, Any]:
    document = copy.deepcopy(load(VAULT_OVERLAY))
    for path, value in changes.items():
        *parents, last = path.split("__")
        node = document
        for one in parents:
            node = node[one]
        if value is None:
            node.pop(last, None)
        else:
            node[last] = value
    return document


def test_the_vault_overlay_hands_the_application_the_vault_and_its_network_and_nothing_else() -> (
    None
):
    """The positive case, against the network the vault's own project declares. Delete this and
    the overlay can name a network the vault is not on, and the application starts with an
    address it cannot reach."""
    assert vault_network() == VAULT_NETWORK
    assert vault_overlay_gaps(load(VAULT_OVERLAY), vault_network=VAULT_NETWORK) == ()
    environment = environment_of(load(VAULT_OVERLAY), APPLICATION_SERVICE) or {}
    assert tuple(environment) == VAULT_SETTINGS
    assert all(required_variable(environment[one]) == one for one in VAULT_SETTINGS)


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"services__app__environment__BRAIN_VAULT_TOKEN": "${BRAIN_VAULT_TOKEN:-}"}, "require"),
        ({"services__app__environment__BRAIN_VAULT_ADDRESS": None}, "BRAIN_VAULT_ADDRESS"),
        ({"services__app__networks": ["brain-vault", "tool-api"]}, "alone"),
        ({"services__app__networks": None}, "alone"),
        ({"services__app__ports": ["8200:8200"]}, "changes the profile's application"),
        ({"services__vault": {"image": "openbao/openbao:2.4.1"}}, "beside"),
        ({"networks__brain-vault__external": False}, "external"),
        ({"networks__brain-vault__name": "vault"}, "external"),
        ({"services__app__environment__BRAIN_ENV": "development"}, "as well as the vault"),
    ],
    ids=[
        "optional token",
        "no address",
        "a second network",
        "no network",
        "a port",
        "a second service",
        "not external",
        "another name",
        "another variable",
    ],
)
def test_an_overlay_that_does_more_or_less_than_hand_over_the_vault_is_reported(
    change: dict[str, Any], said: str
) -> None:
    """Each way the file could be wrong, each caught by its own rule. Delete this and the token
    can be optional, so a half-chosen vault starts an application that keeps no credential; or
    the overlay can join the canvas's network or publish the vault's port, which changes the
    stack for every install that chose a vault from a file nobody reviewing it would read."""
    found = vault_overlay_gaps(overlay(**change), vault_network=VAULT_NETWORK)
    assert len(found) == 1, found
    assert said in found[0]


@pytest.mark.parametrize("profile", PROFILES)
def test_composed_onto_a_profile_the_application_keeps_its_own_and_gains_the_vault(
    profile: str,
) -> None:
    """Compose merges `environment` as a mapping and `networks` as a union by name, modelled
    here. Delete this and an overlay that replaced the application's networks rather than adding
    one would cut it off from its own database on exactly the installs that chose a vault."""
    base = load(files_for(profile)[0])["services"][APPLICATION_SERVICE]
    added = load(VAULT_OVERLAY)["services"][APPLICATION_SERVICE]
    networks = {*base["networks"], *added["networks"]}
    environment = {**base["environment"], **added["environment"]}
    assert {"default", VAULT_NETWORK} <= networks
    assert set(VAULT_SETTINGS) <= set(environment)
    assert "BRAIN_SETUP_SECRET" in environment


def test_the_release_carries_the_vault_overlay() -> None:
    """Delete this and an update on an install that chose a vault stops on a file the archive
    never brought to its server."""
    assert included_by(VAULT_OVERLAY)
    assert not refused_by(VAULT_OVERLAY)


def test_the_choice_is_the_variable_the_overlay_requires() -> None:
    """See `AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT`. The scripts grep the
    environment file for this name, so it has to be one the overlay refuses to start without.
    Delete this and a rename in the overlay leaves the scripts looking for a line nobody writes."""
    environment = environment_of(load(VAULT_OVERLAY), APPLICATION_SERVICE) or {}
    assert required_variable(environment[VAULT_CHOICE]) == VAULT_CHOICE
    assert "update" in AN_ADDRESS_IN_THE_ENVIRONMENT_FILE_RECORDS_THE_VAULT


@pytest.mark.parametrize("script", ["update", "rollback"])
@pytest.mark.parametrize(
    ("line", "chosen"),
    [
        ("BRAIN_VAULT_ADDRESS=http://a-vault", True),
        ("BRAIN_VAULT_ADDRESS=", False),
        ("# BRAIN_VAULT_ADDRESS=http://a-vault", False),
        ("OTHER_BRAIN_VAULT_ADDRESS=http://a-vault", False),
    ],
    ids=["set", "empty", "commented", "a longer name"],
)
def test_both_scripts_compose_the_vault_exactly_when_the_environment_file_names_one(
    tmp_path: Path, script: str, line: str, *, chosen: bool
) -> None:
    """Run, not read: the opening of each rendered script against a real environment file, and
    the file list it ends with, by the release tests' own runner. Delete this and an update
    recreates the application without the overlay, so every provider key the console kept in the
    vault stops being loaded, with the update reporting success."""
    home = an_install(tmp_path / "install")
    with home.joinpath(INSTALL_ENV_FILE).open("a", encoding="utf-8", newline="\n") as env:
        env.write(f"{line}\n")
    render = render_update if script == "update" else render_rollback
    opening = render(repository=REPOSITORY, tunnel_token=TOKEN).split("\n# step ")[0]

    done = run_script(
        opening + '\nprintf "%s\\n" "$BRAIN_COMPOSE_FILES"\n',
        home=home,
        args=("lite", "v1.1.0"),
        url="https://x.invalid",
    )

    assert done.returncode == 0, done.stderr
    flags = done.stdout.strip().splitlines()[-1].split()
    names = [one.rsplit("/", 1)[-1] for one in flags[1::2]]
    assert names == [*files_for("lite"), *([VAULT_OVERLAY] if chosen else [])]
    assert ("vault overlay is composed in" in done.stdout) is chosen


# ============================================================================ the steps
def test_the_vault_steps_name_the_overlay_and_the_line_that_chooses_it() -> None:
    """The steps a person follows are where the overlay is switched on. Delete this and they can
    go back to saying no compose file does it, which was true until 2026-09-16 and would send
    somebody to write an override by hand that the next update discards."""
    page = (REPO / "ops" / "openbao" / "credential-slots.md").read_text(encoding="utf-8")
    steps = page.split("## Letting the application keep a provider key", 1)[1].split("\n## ", 1)[0]
    assert f"-f /opt/brain/{VAULT_OVERLAY} up -d app" in steps
    assert VAULT_CHOICE in steps
    assert "No compose file in this repository does either yet" not in page
    configuration = (REPO / "docs" / "install" / "configuration.md").read_text(encoding="utf-8")
    [row] = [one for one in configuration.splitlines() if one.startswith(f"| `{VAULT_CHOICE}` |")]
    assert VAULT_OVERLAY in row
