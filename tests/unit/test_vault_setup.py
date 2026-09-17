"""The installer runs the secrets vault, opens it once, and hands the install its tokens.

Two kinds of evidence, and the difference matters. **Read:** the committed `ops/install/install.sh`
and the compose files, parsed, for what the vault steps enable, load, mint, print and revoke, and
for which profiles compose which overlay. **Run against a stand-in:** the four vault steps cut out
of the committed script and run by this machine's shell with a `docker` on the path that answers
as `bao` does, which is what catches a quoting mistake, a pipe that loses a piece or a token that
reaches an argument list. Neither is a vault: nothing here has initialised OpenBao, and
`ops/openbao/REHEARSAL.md` is the run on a server that would.

Task ids: M42.6.2, M42.5.14
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.app_environment import (
    VAULT_NETWORK,
    VAULT_OVERLAY,
    VAULT_PROJECT,
    WORKER_FILE,
    WORKER_SERVICE,
    WORKER_VAULT_CHOICE,
    WORKER_VAULT_OVERLAY,
    worker_vault_overlay_gaps,
    worker_vault_overlays_for,
)
from brain.deployment.install_script import SCRIPT_PATH
from brain.deployment.installer import INSTALL_ENV_FILE, INSTALL_HOME, PLAN, step_named
from brain.deployment.release import REPO, render_rollback, render_update
from brain.deployment.requirements import files_for
from brain.deployment.vault_setup import (
    DECLINABLE_PROFILES,
    ENGINES,
    OBJECT_STORE_FILE,
    TOKEN_PERIOD,
    VAULT_ADDRESS,
    VAULT_PORT,
    VAULT_SERVICE,
    vault_choice_lines,
)
from brain.ops.openbao import STATIC_PREFIXES
from brain.ops.vault_quorum import DEFAULT_POLICY
from brain.ops.wiring import PROFILES
from tests.unit.test_deployment_release import REPOSITORY, TOKEN, an_install, run_script

#: The four vault steps, by the names the plan gives them, in the order they run.
VAULT_STEPS = (
    "start the secrets vault",
    "initialise the secrets vault and show its unseal pieces, once",
    "open the secrets vault and give this install its tokens",
    "compose the secrets vault in",
)

#: What the stand-in's `bao operator init` prints: five pieces and a root token, as OpenBao does.
PIECES = tuple(f"piece-{n}-b64+/=" for n in range(1, 6))
ROOT = "root-token-printed-once"
APP_TOKEN = "application-token-minted"
WORKER_TOKEN = "worker-token-minted"

#: A `docker` that answers as `bao` inside `brain-vault` does, recording what it was asked, with
#: which `BAO_TOKEN` in its environment, and what arrived on its standard input.
STAND_IN = r"""#!/bin/sh
state="$FAKE_VAULT"
printf '%s\n' "$*" >> "$state/argv"
case "$*" in
  "compose "*" up -d") touch "$state/started"; exit 0 ;;
  "compose "*" ps "*) test -f "$state/started" && printf 'vault\n'; exit 0 ;;
esac
test "$1" = "exec" || exit 0
shift
presented=""
while test "$#" -gt 0; do
  case "$1" in
    -i) shift ;;
    -e) test "$2" = "BAO_TOKEN" && presented="${BAO_TOKEN:-}"; shift 2 ;;
    brain-vault) shift; break ;;
    *) shift ;;
  esac
done
shift
asked="$*"
printf '%s|%s\n' "$presented" "$asked" >> "$state/calls"
case "$asked" in
  "operator init -status") test -f "$state/initialised" && exit 0; exit 2 ;;
  "operator init -key-shares=5 -key-threshold=3")
    touch "$state/initialised"
    n=1
    for piece in __PIECES__; do printf 'Unseal Key %s: %s\n' "$n" "$piece"; n=$((n + 1)); done
    printf '\nInitial Root Token: %s\n\nVault initialized with 5 key shares.\n' "__ROOT__"
    exit 0 ;;
  "write sys/unseal key=-") { cat; printf '\n'; } >> "$state/unsealed"; exit 0 ;;
  "status") exit 0 ;;
  "audit list") exit 2 ;;
  "audit enable"*) exit 0 ;;
  "secrets list") printf 'cubbyhole/    cubbyhole    n/a\n'; exit 0 ;;
  "secrets enable"*) exit 0 ;;
  "policy write "*" -") name="${asked#policy write }"; cat > "$state/policy.${name% -}"; exit 0 ;;
  "token create -policy=application"*) printf '%s' "__APP__"; exit 0 ;;
  "token create -policy=worker"*) printf '%s' "__WORKER__"; exit 0 ;;
  "token lookup") test "$presented" = "__APP__" && exit 0; exit 1 ;;
  "token revoke -self") exit 0 ;;
esac
exit 99
"""


def committed() -> str:
    return (REPO / SCRIPT_PATH).read_text(encoding="utf-8")


def load(name: str) -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}
    return parsed


def declares(name: str, service: str) -> bool:
    return service in (load(name).get("services") or {})


def the_vault_steps(script: str) -> str:
    """The script's opening, then the four vault steps and nothing else, as the shell reads them."""
    parts = script.split("\n# step ")
    kept = [parts[0]]
    for part in parts[1:]:
        name = part.split("\n", 1)[0].split(": ", 1)[1]
        if name in VAULT_STEPS:
            kept.append(part)
    assert len(kept) == 1 + len(VAULT_STEPS)
    return "\n# step ".join(kept) + '\nprintf "files: %s\\n" "$BRAIN_COMPOSE_FILES"\n'


def a_shell() -> str:
    """Bash, because the installer is a bash script and is documented as `bash install.sh`.

    Its header sets `pipefail`, which dash does not have. Measured on 2026-09-17: these tests
    passed on Windows, where `sh` is Git's bash, and every one failed on the ubuntu runner,
    where `sh` is dash, with `set: Illegal option -o pipefail` before a vault step ran. Running
    them with `sh` tested a shell nobody is told to use; the update and rollback scripts are
    different, being POSIX, and `test_deployment_release.py` rightly runs those with `sh`.
    """
    shell = shutil.which("bash")
    if shell is None:  # pragma: no cover - CI runs on Linux, where bash is installed
        pytest.skip("no bash on this machine to run the installer's vault steps with")
    return shell


def installing(
    tmp_path: Path, args: Sequence[str], *, env_lines: Sequence[str] = (), initialised: bool = False
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Run the vault steps once, against a stand-in vault, in a throwaway install directory."""
    home = an_install(tmp_path / "install")
    with home.joinpath(INSTALL_ENV_FILE).open("a", encoding="utf-8", newline="\n") as env:
        env.writelines(f"{one}\n" for one in env_lines)
    shutil.copytree(
        REPO / "ops/openbao/policies", home / "ops/openbao/policies", dirs_exist_ok=True
    )
    state = tmp_path / "vault"
    state.mkdir(exist_ok=True)
    if initialised:
        state.joinpath("initialised").touch()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(
        STAND_IN.replace("__PIECES__", " ".join(f"'{one}'" for one in PIECES))
        .replace("__ROOT__", ROOT)
        .replace("__APP__", APP_TOKEN)
        .replace("__WORKER__", WORKER_TOKEN),
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)
    script = tmp_path / "install.sh"
    script.write_text(
        the_vault_steps(committed()).replace(INSTALL_HOME, home.as_posix()),
        encoding="utf-8",
        newline="\n",
    )
    done = subprocess.run(
        [a_shell(), script.as_posix(), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        stdin=subprocess.DEVNULL,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "BRAIN_RELEASE_URL": "https://release.invalid/archive.tar.gz",
            "FAKE_VAULT": state.as_posix(),
        },
    )
    return done, home, state


def lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


# ============================================================================ run, with a stand-in
def test_a_fresh_standard_install_opens_the_vault_and_writes_both_tokens_and_the_address(
    tmp_path: Path,
) -> None:
    """**The leaf's installer half, run.** The pieces are printed once and never the root token;
    three of them reach the vault on standard input and on no argument list; both audit devices,
    the three engines and every policy file are loaded under the root token; both tokens are minted
    under it and written after the address; the root token is revoked last; and the file list the
    rest of the install composes gains both overlays.

    Delete this and the vault steps can be valid shell that loses a piece in a pipe, passes the
    root token as an argument, writes a token nothing composes, or never revokes the root token,
    and every test that reads the script still passes."""
    done, home, state = installing(tmp_path, ("--release", "v1.0.0", "--profile", "standard"))

    assert done.returncode == 0, done.stderr
    out = done.stdout
    for n, piece in enumerate(PIECES, 1):
        assert out.count(f"piece {n} of {DEFAULT_POLICY.shares}: {piece}") == 1
    assert ROOT not in out + done.stderr
    assert APP_TOKEN not in out + done.stderr
    assert lines(state / "unsealed") == list(PIECES[: DEFAULT_POLICY.threshold])
    argv = (state / "argv").read_text(encoding="utf-8")
    for secret in (*PIECES, ROOT, APP_TOKEN, WORKER_TOKEN):
        assert secret not in argv

    calls = [one.split("|", 1) for one in lines(state / "calls")]
    as_root = [asked for presented, asked in calls if presented == ROOT]
    assert [one for one in as_root if one.startswith("audit enable")] == [
        "audit enable -path=file file file_path=/openbao/logs/audit.log log_raw=false "
        "hmac_accessor=true",
        "audit enable -path=stderr file file_path=stderr log_raw=false",
    ]
    assert [one for one in as_root if one.startswith("secrets enable")] == [
        f"secrets enable -path={engine} kv-v2" for engine in ENGINES
    ]
    policies = sorted(path.stem for path in (REPO / "ops/openbao/policies").glob("*.hcl"))
    assert sorted(path.name.removeprefix("policy.") for path in state.glob("policy.*")) == policies
    assert (state / "policy.application").read_text(encoding="utf-8") == (
        REPO / "ops/openbao/policies/application.hcl"
    ).read_text(encoding="utf-8").replace("\r", "")
    assert [one for one in as_root if one.startswith("token create")] == [
        f"token create -policy=application -orphan -period={TOKEN_PERIOD} -field=token",
        f"token create -policy=worker -orphan -period={TOKEN_PERIOD} -field=token",
    ]
    assert calls[-1] == [ROOT, "token revoke -self"]
    assert [presented for presented, asked in calls if asked == "token lookup"] == [APP_TOKEN]

    assert lines(home / INSTALL_ENV_FILE)[-3:] == [
        f"BRAIN_VAULT_ADDRESS={VAULT_ADDRESS}",
        f"BRAIN_VAULT_TOKEN={APP_TOKEN}",
        f"{WORKER_VAULT_CHOICE}={WORKER_TOKEN}",
    ]
    composed = out.strip().splitlines()[-1].removeprefix("files: ").split()
    assert [one.rsplit("/", 1)[-1] for one in composed[1::2]] == [
        *files_for("standard"),
        VAULT_OVERLAY,
        WORKER_VAULT_OVERLAY,
    ]


def test_a_second_run_skips_every_vault_step_that_writes_and_still_composes_the_vault_in(
    tmp_path: Path,
) -> None:
    """Safe to run twice, which for the vault means never initialising it again: a second
    `operator init` on a vault that holds keys is refused by the vault, and one that got through
    would print pieces to nobody. Delete this and a re-run could lose the overlays it no longer
    remembers choosing, because the choice is only in the file."""
    first, home, state = installing(tmp_path, ("--release", "v1.0.0", "--profile", "standard"))
    assert first.returncode == 0, first.stderr
    (state / "calls").unlink()

    second = subprocess.run(
        [
            a_shell(),
            (tmp_path / "install.sh").as_posix(),
            "--release",
            "v1.0.0",
            "--profile",
            "standard",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        stdin=subprocess.DEVNULL,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
            "BRAIN_RELEASE_URL": "https://release.invalid/archive.tar.gz",
            "FAKE_VAULT": state.as_posix(),
        },
    )

    assert second.returncode == 0, second.stderr
    for name in VAULT_STEPS[:3]:
        assert f"{name} - already done, skipping" in second.stdout
    assert "operator init -key-shares" not in "\n".join(lines(state / "calls"))
    assert not any(one.startswith(ROOT) for one in lines(state / "calls"))
    assert "piece 1 of" not in second.stdout
    assert lines(home / INSTALL_ENV_FILE).count(f"BRAIN_VAULT_TOKEN={APP_TOKEN}") == 1
    assert (
        second.stdout.strip()
        .splitlines()[-1]
        .endswith(
            f"-f {home.as_posix()}/{VAULT_OVERLAY} -f {home.as_posix()}/{WORKER_VAULT_OVERLAY}"
        )
    )


def test_a_vault_an_earlier_run_initialised_and_did_not_finish_stops_and_names_the_way_on(
    tmp_path: Path,
) -> None:
    """The one state a later run cannot repair, refused in words. Delete this and the opening step
    can run with no root token, mint nothing, and write empty token lines the overlay then refuses,
    with a message about a variable rather than about the vault."""
    done, home, state = installing(
        tmp_path, ("--release", "v1.0.0", "--profile", "lite"), initialised=True
    )

    assert done.returncode != 0
    assert "Finishing what the installer began" in done.stderr
    assert "BRAIN_VAULT_TOKEN" not in (home / INSTALL_ENV_FILE).read_text(encoding="utf-8")
    assert not any(one.startswith("|token") for one in lines(state / "calls"))


def test_a_lite_install_mints_no_worker_token_and_composes_only_the_applications_overlay(
    tmp_path: Path,
) -> None:
    """Lite runs no worker. Delete this and it is handed a standing credential nothing reads, or an
    overlay naming a service its files do not declare, which stops the stack."""
    done, home, state = installing(tmp_path, ("--release", "v1.0.0", "--profile", "lite"))

    assert done.returncode == 0, done.stderr
    assert not any("-policy=worker" in one for one in lines(state / "calls"))
    written = (home / INSTALL_ENV_FILE).read_text(encoding="utf-8")
    assert f"BRAIN_VAULT_TOKEN={APP_TOKEN}" in written
    assert WORKER_VAULT_CHOICE not in written
    composed = done.stdout.strip().splitlines()[-1].removeprefix("files: ").split()
    assert [one.rsplit("/", 1)[-1] for one in composed[1::2]] == [*files_for("lite"), VAULT_OVERLAY]


def test_a_lite_install_that_declines_the_vault_asks_docker_nothing_and_composes_none(
    tmp_path: Path,
) -> None:
    """The positive half of `--no-vault`. Delete this and declining can leave one of the vault
    steps running, which starts a vault nobody opens and prints pieces nobody asked for."""
    done, home, state = installing(
        tmp_path, ("--release", "v1.0.0", "--profile", "lite", "--no-vault")
    )

    assert done.returncode == 0, done.stderr
    assert lines(state / "argv") == []
    assert "BRAIN_VAULT_TOKEN" not in (home / INSTALL_ENV_FILE).read_text(encoding="utf-8")
    composed = done.stdout.strip().splitlines()[-1].removeprefix("files: ").split()
    assert [one.rsplit("/", 1)[-1] for one in composed[1::2]] == [*files_for("lite")]


@pytest.mark.parametrize("profile", [one for one in PROFILES if one not in DECLINABLE_PROFILES])
def test_declining_the_vault_is_refused_on_a_profile_whose_services_need_it(
    tmp_path: Path, profile: str
) -> None:
    """Delete this and a standard install can be run with no vault, which comes up with a file
    store that never connects and a worker whose every delivery fails."""
    done, _, state = installing(
        tmp_path, ("--release", "v1.0.0", "--profile", profile, "--no-vault")
    )

    assert done.returncode != 0
    assert f"--no-vault is refused for the {profile} profile" in done.stderr
    assert lines(state / "argv") == []


# ============================================================================ read
def test_only_lite_may_decline_the_vault_as_only_its_files_run_no_worker_or_object_store() -> None:
    """Derived from the parsed compose files, not from the constant. Delete this and a profile that
    gains a worker keeps accepting `--no-vault`, or the file names the rule reads stop naming the
    services they stand for."""
    assert declares(WORKER_FILE, WORKER_SERVICE)
    assert declares(OBJECT_STORE_FILE, "seaweedfs")
    for profile in PROFILES:
        needs = any(
            declares(name, WORKER_SERVICE) or declares(name, "seaweedfs")
            for name in files_for(profile)
        )
        assert (profile in DECLINABLE_PROFILES) is not needs, profile
    assert DECLINABLE_PROFILES == ("lite",)


def test_the_engines_enabled_are_the_three_the_product_writes_and_the_policy_names() -> None:
    """Delete this and an engine the console writes to is one the installer never enabled, which
    reads as the vault refusing: a 404 on a write is an engine that is not mounted."""
    assert ENGINES == ("providers", "webhooks", "connector_keys")
    assert tuple(one.rstrip("/") for one in STATIC_PREFIXES) == ENGINES
    policy = (REPO / "ops/openbao/policies/application.hcl").read_text(encoding="utf-8")
    for engine in ENGINES:
        assert f'path "{engine}/data/+"' in policy
    assert (
        f"for engine in {' '.join(ENGINES)}; do"
        in committed().splitlines()[
            next(i for i, one in enumerate(committed().splitlines()) if "for engine in" in one)
        ]
    )


def test_the_period_is_the_documented_one_and_the_policies_minted_against_are_files_loaded() -> (
    None
):
    """Delete this and the installer can mint a period the runbook does not document, or a token
    against a policy name no file defines, which the vault mints and every request then refuses."""
    slots = (REPO / "ops/openbao/credential-slots.md").read_text(encoding="utf-8")
    assert f"-policy=application -period={TOKEN_PERIOD}" in slots
    assert f"-policy=worker -period={TOKEN_PERIOD}" in slots
    minted = re.findall(
        r"token create -policy=(\w[\w-]*) -orphan -period=(\S+) -field=token", committed()
    )
    assert sorted(minted) == [("application", TOKEN_PERIOD), ("worker", TOKEN_PERIOD)]
    loaded = {path.stem for path in (REPO / "ops/openbao/policies").glob("*.hcl")}
    assert {name for name, _ in minted} <= loaded


def test_the_address_written_is_the_service_and_port_the_vaults_own_project_declares() -> None:
    """Delete this and the vault's service can be renamed in its compose file while every install
    writes an address that resolves to nothing on the vault's network."""
    project = load(VAULT_PROJECT)
    body = project["services"][VAULT_SERVICE]
    assert str(VAULT_PORT) in [str(one) for one in body["expose"]]
    assert VAULT_NETWORK in body["networks"]
    assert f'printf "BRAIN_VAULT_ADDRESS=%s\\n" "{VAULT_ADDRESS}"' in committed()


def test_only_the_initialising_step_prints_the_vaults_answer_and_every_other_use_is_a_pipe() -> (
    None
):
    """The half of the leak rule its name check cannot see: the pieces travel in `BRAIN_VAULT_INIT`,
    which names a vault's answer rather than a credential. Delete this and a step can print that
    variable to the terminal with `Step`'s own check silent."""
    printing = re.compile(r'printf "%s\\n" "\$BRAIN_VAULT_INIT"(?P<rest>.*)$')
    for step in PLAN:
        for line in step.run.splitlines():
            found = printing.search(line)
            if found is None:
                continue
            if step.name == VAULT_STEPS[1]:
                continue
            assert found.group("rest").lstrip().startswith("|"), (step.name, line)
    assert step_named(VAULT_STEPS[1]).presents_once


def test_no_piece_or_token_is_put_on_an_argument_list_or_in_a_here_string() -> None:
    """Delete this and the obvious spelling, `bao operator unseal <piece>` or
    `-e BAO_TOKEN=<token>`,
    puts a secret where every local user can read it for as long as the command runs, and a
    here-string writes it to a temporary file on the bash an older distribution ships."""
    text = "\n".join(step_named(name).run for name in VAULT_STEPS)
    assert "<<" not in text
    assert "operator unseal" not in text
    assert "BAO_TOKEN=$" not in text.replace('BAO_TOKEN="$', "")
    assert "-e BAO_TOKEN=" not in text
    assert "sys/unseal key=-" in text


# ============================================================================ the overlays
def test_the_worker_overlay_hands_the_worker_its_own_token_under_the_name_it_reads() -> None:
    """Delete this and the overlay can hand the worker the application's token, or name only the
    vault's network and cut the worker off from its database."""
    assert worker_vault_overlay_gaps(load(WORKER_VAULT_OVERLAY)) == ()


@pytest.mark.parametrize(
    ("change", "found"),
    [
        (
            lambda d: d["services"]["brain-worker"]["environment"].update(
                BRAIN_VAULT_TOKEN="${BRAIN_VAULT_TOKEN:?the application's}"
            ),
            "BRAIN_WORKER_VAULT_TOKEN",
        ),
        (
            lambda d: d["services"]["brain-worker"].update(networks=["brain-vault"]),
            "loses the database",
        ),
        (lambda d: d["services"].update(app={"networks": ["brain-vault"]}), "nothing else"),
        (lambda d: d["networks"]["brain-vault"].update(external=False), "external"),
    ],
    ids=["the application's token", "no default network", "a second service", "not external"],
)
def test_a_worker_overlay_that_does_more_or_less_is_reported(change: Any, found: str) -> None:
    """The refusals, each against the real file with one thing changed. Delete this and the check
    above can pass by reporting nothing about anything."""
    document = load(WORKER_VAULT_OVERLAY)
    change(document)
    assert any(found in one for one in worker_vault_overlay_gaps(document))


def test_the_worker_overlay_is_composed_only_where_a_profiles_files_declare_the_worker() -> None:
    """Delete this and the worker overlay can be composed onto lite, where it names a service with
    no image and stops the stack, or left off standard, where every delivery fails."""
    for profile in PROFILES:
        files = files_for(profile)
        has_worker = any(declares(name, WORKER_SERVICE) for name in files)
        assert bool(worker_vault_overlays_for(files)) is has_worker, profile


def test_the_installer_update_and_rollback_compose_the_vault_in_one_way() -> None:
    """Delete this and an update can compose the vault differently from the install, which is an
    update that restarts the worker without its token."""
    chosen = vault_choice_lines(INSTALL_HOME, INSTALL_ENV_FILE)
    assert step_named(VAULT_STEPS[3]).run.splitlines() == list(chosen)
    for render in (render_update, render_rollback):
        rendered = render(repository=REPOSITORY, tunnel_token=TOKEN).splitlines()
        assert all(one in rendered for one in chosen)


@pytest.mark.parametrize(
    ("profile", "env_lines", "overlays"),
    [
        ("standard", ("BRAIN_VAULT_ADDRESS=http://vault:8200", f"{WORKER_VAULT_CHOICE}=t"), 2),
        ("standard", ("BRAIN_VAULT_ADDRESS=http://vault:8200",), 1),
        ("standard", (f"{WORKER_VAULT_CHOICE}=",), 0),
        ("lite", ("BRAIN_VAULT_ADDRESS=http://vault:8200", f"{WORKER_VAULT_CHOICE}=t"), 1),
    ],
    ids=["both", "an application vault set up by hand", "an empty worker line", "lite"],
)
def test_an_update_composes_the_worker_overlay_exactly_when_the_file_holds_the_workers_token(
    tmp_path: Path, profile: str, env_lines: Mapping[str, str] | Sequence[str], overlays: int
) -> None:
    """Run, not read, by the release tests' own runner. Delete this and an install whose vault was
    set up by hand for the application alone stops updating over a worker token it never had."""
    home = an_install(tmp_path / "install")
    with home.joinpath(INSTALL_ENV_FILE).open("a", encoding="utf-8", newline="\n") as env:
        env.writelines(f"{one}\n" for one in env_lines)
    opening = render_update(repository=REPOSITORY, tunnel_token=TOKEN).split("\n# step ")[0]

    done = run_script(
        opening + '\nprintf "%s\\n" "$BRAIN_COMPOSE_FILES"\n',
        home=home,
        args=(profile, "v1.1.0"),
        url="https://x.invalid",
    )

    assert done.returncode == 0, done.stderr
    names = [one.rsplit("/", 1)[-1] for one in done.stdout.strip().splitlines()[-1].split()[1::2]]
    assert names == [*files_for(profile), *(VAULT_OVERLAY, WORKER_VAULT_OVERLAY)[:overlays]]
