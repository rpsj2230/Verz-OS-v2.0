"""The installer runs the secrets vault, opens it once, and hands the install its tokens.

Two kinds of evidence, and the difference matters. **Read:** the committed `ops/install/install.sh`
and the compose files, parsed, for what the vault steps enable, load, mint, print and revoke, and
for which profiles compose which overlay. **Run against a stand-in:** the four vault steps cut out
of the committed script and run by this machine's shell with a `docker` on the path that answers
as `bao` does, which is what catches a quoting mistake, a pipe that loses a piece or a token that
reaches an argument list. Neither is a vault: nothing here has initialised OpenBao, and
`ops/openbao/REHEARSAL.md` is the run on a server that would.

Task ids: M42.6.2, M42.5.14, M31.3.2.3, M31.3.2.6, M38.4.1.3
"""

from __future__ import annotations

import fnmatch
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
    VAULT_AUDIT_LOG,
    VAULT_AUDIT_VOLUME,
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
    APPLY_SCRIPT,
    DECLINABLE_PROFILES,
    DEPLOY_POLICY,
    DEPLOY_TOKEN_PERIOD,
    ENGINES,
    NO_DEPLOY_TOKEN_EXIT,
    OBJECT_STORE_FILE,
    SEAL_KEY_BYTES,
    SEAL_KEY_FILE,
    TOKEN_METHOD_MAX_TTL,
    TOKEN_PERIOD,
    VAULT_ADDRESS,
    VAULT_NETWORK_NAME,
    VAULT_PORT,
    VAULT_SERVICE,
    VAULT_STATE_DIR,
    render_apply,
    vault_choice_lines,
)
from brain.ops.channel_lease import SEND_POLICY, SEND_ROLE_MAX_TTL_SECONDS, SEND_TOKEN_ROLE
from brain.ops.connector_lease import (
    PERSON_POLICY,
    PERSON_ROLE_MAX_TTL_SECONDS,
    PERSON_TOKEN_ROLE,
    ROTATE_POLICY,
    ROTATE_ROLE_MAX_TTL_SECONDS,
    ROTATE_TOKEN_ROLE,
    RUN_POLICY,
    RUN_ROLE_MAX_TTL_SECONDS,
    RUN_TOKEN_ROLE,
)
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.openbao import STATIC_PREFIXES
from brain.ops.vault_quorum import RECOVERY_SPLIT
from brain.ops.wiring import PROFILES
from tests.unit.test_deployment_release import REPOSITORY, TOKEN, an_install, run_script

#: The vault steps, by the names the plan gives them, in the order they run.
VAULT_STEPS = (
    "make the secrets vault's seal key",
    "start the secrets vault",
    "initialise the secrets vault and keep its recovery key",
    "configure the secrets vault and give this install its tokens",
    "apply this release's vault policies, engines and roles",
    "compose the secrets vault in",
)

#: What the stand-in's `bao operator init` prints: recovery keys and a root token, as OpenBao does.
PIECES = tuple(f"piece-{n}-b64+/=" for n in range(1, 6))
RECOVERY = "the-one-recovery-key-b64+/="
ROOT = "root-token-printed-once"
APP_TOKEN = "application-token-minted"
WORKER_TOKEN = "worker-token-minted"
DEPLOY_TOKEN = "deploy-token-minted"

#: A `docker` that answers as `bao` inside `brain-vault` does, recording what it was asked, with
#: which `BAO_TOKEN` in its environment, and holding what the apply script reads back: policies
#: by name, the run role's settings and each slot's metadata, printed as OpenBao prints them
#: (measured on 2.4.1 on 2026-09-29: a list as `[a]`, custom metadata as `map[k:v k:v]`).
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
known() { case "$presented" in __ROOT__|__APP__|__WORKER__|__DEPLOY__) return 0 ;; esac; return 1; }
case "$asked" in
  "operator init -status") test -f "$state/initialised" && exit 0; exit 2 ;;
  "operator init -recovery-shares=1 -recovery-threshold=1")
    touch "$state/initialised"
    printf 'Recovery Key 1: %s\n\nInitial Root Token: %s\n\nSuccess!\n' \
      "__RECOVERY__" "__ROOT__"
    exit 0 ;;
  "operator init -recovery-shares=5 -recovery-threshold=3")
    touch "$state/initialised"
    n=1
    for piece in __PIECES__; do printf 'Recovery Key %s: %s\n' "$n" "$piece"; n=$((n + 1)); done
    printf '\nInitial Root Token: %s\n\nSuccess! Vault is initialized\n' "__ROOT__"
    exit 0 ;;
  "status") exit 0 ;;
  "token lookup") known && exit 0; exit 2 ;;
  "token renew") exit 0 ;;
  "secrets list")
    printf 'cubbyhole/    cubbyhole    n/a\n'
    for engine in $(cat "$state/engines" 2>/dev/null); do
      printf '%s/    kv    n/a\n' "$engine"
    done
    exit 0 ;;
  "secrets enable -path="*" kv-v2")
    engine="${asked#secrets enable -path=}"
    printf '%s\n' "${engine% kv-v2}" >> "$state/engines"; exit 0 ;;
  "read -field=policy sys/policies/acl/"*) cat "$state/policy.${asked##*/}" 2>/dev/null; exit $? ;;
  "policy write "*" -")
    name="${asked#policy write }"; name="${name% -}"
    # The deploy token's own policy and the default one are read-only to it, as deploy.hcl says.
    if test "$presented" = "__DEPLOY__" \
      && { test "$name" = deploy || test "$name" = default; }; then
      cat >/dev/null; exit 2
    fi
    cat > "$state/policy.$name"; exit 0 ;;
  "write auth/token/roles/"*)
    rest="${asked#write auth/token/roles/}"; role="${rest%% *}"
    for pair in ${rest#* }; do
      printf '%s\n' "${pair#*=}" > "$state/role.$role.${pair%%=*}"
    done
    exit 0 ;;
  "read -field=allowed_policies auth/token/roles/"*)
    role="${asked##*/}"
    test -f "$state/role.$role.allowed_policies" \
      && printf '[%s]\n' "$(cat "$state/role.$role.allowed_policies")"
    exit 0 ;;
  "read -field="*" auth/token/roles/"*)
    role="${asked##*/}"; field="${asked#read -field=}"
    cat "$state/role.$role.${field%% *}" 2>/dev/null; exit 0 ;;
  "read -field=custom_metadata connector_keys/metadata/"*)
    cat "$state/slot.${asked##*/}" 2>/dev/null; exit 0 ;;
  "kv metadata put -mount=connector_keys "*) ;;
  "auth tune -max-lease-ttl=8760h token/") exit 0 ;;
  "token create -policy=application"*) printf '%s' "__APP__"; exit 0 ;;
  "token create -policy=worker"*) printf '%s' "__WORKER__"; exit 0 ;;
  "token create -policy=deploy"*) printf '%s' "__DEPLOY__"; exit 0 ;;
  "token revoke -self") exit 0 ;;
  *) exit 99 ;;
esac
# kv metadata put: the arguments one by one, so a scope with spaces in it arrives whole.
shift 3
scopes=""; refused=""; name=""
for one in "$@"; do
  case "$one" in
    -custom-metadata=scopes=*) scopes="${one#-custom-metadata=scopes=}" ;;
    -custom-metadata=not_requested=*) refused="${one#-custom-metadata=not_requested=}" ;;
    *) name="$one" ;;
  esac
done
printf 'map[not_requested:%s scopes:%s]\n' "$refused" "$scopes" > "$state/slot.$name"
exit 0
"""


#: The policy files and the switch, as the release lays them out.
POLICY_FILES = tuple(sorted((REPO / "ops/openbao/policies").glob("*.hcl")))
SWITCH_SCRIPT = "ops/openbao/switch-to-auto-unseal.sh"


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


def stand_in() -> str:
    """The stand-in `docker`, with this file's values put where it prints them."""
    return (
        STAND_IN.replace("__PIECES__", " ".join(f"'{one}'" for one in PIECES))
        .replace("__RECOVERY__", RECOVERY)
        .replace("__ROOT__", ROOT)
        .replace("__APP__", APP_TOKEN)
        .replace("__WORKER__", WORKER_TOKEN)
        .replace("__DEPLOY__", DEPLOY_TOKEN)
    )


def an_install_with_the_vaults_files(tmp_path: Path) -> tuple[Path, Path]:
    """An install directory carrying this release's `ops/openbao`, and a state directory for it.

    The committed `apply-release.sh` is copied with the one path it names outside the install, the
    deploy token's, moved into the throwaway state directory: a test run must never read or write
    `/etc` on the machine it runs on, and the path is the only rewrite.
    """
    home = an_install(tmp_path / "install")
    shutil.copytree(
        REPO / "ops/openbao/policies", home / "ops/openbao/policies", dirs_exist_ok=True
    )
    etc = tmp_path / "etc-brain-vault"
    home.joinpath(APPLY_SCRIPT).write_text(
        (REPO / APPLY_SCRIPT).read_text(encoding="utf-8").replace(VAULT_STATE_DIR, etc.as_posix()),
        encoding="utf-8",
        newline="\n",
    )
    return home, etc


def installing(
    tmp_path: Path, args: Sequence[str], *, env_lines: Sequence[str] = (), initialised: bool = False
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Run the vault steps once, against a stand-in vault, in a throwaway install directory."""
    home, etc = an_install_with_the_vaults_files(tmp_path)
    with home.joinpath(INSTALL_ENV_FILE).open("a", encoding="utf-8", newline="\n") as env:
        env.writelines(f"{one}\n" for one in env_lines)
    state = tmp_path / "vault"
    state.mkdir(exist_ok=True)
    if initialised:
        state.joinpath("initialised").touch()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(stand_in(), encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    script = tmp_path / "install.sh"
    script.write_text(
        the_vault_steps(committed())
        .replace(INSTALL_HOME, home.as_posix())
        .replace(VAULT_STATE_DIR, etc.as_posix()),
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
    """**The leaf's installer half, run.** The seal key is written root-only and never printed; the
    one recovery key goes to its root-only file and never to the terminal; nothing unseals the
    vault, which opens itself; the release's engines, every policy file, the run role and every
    slot are applied under the root token and read back; the application's, the worker's and the
    deploy token are minted under it, the deploy token into its own root-only file; the root token
    is revoked last; the apply step finds everything in force with the deploy token; and the file
    list the rest of the install composes gains both overlays.

    Delete this and the vault steps can be valid shell that prints the recovery key, passes the
    root token as an argument, writes a token nothing composes, leaves the deploy token readable,
    or never revokes the root token, and every test that reads the script still passes."""
    done, home, state = installing(tmp_path, ("--release", "v1.0.0", "--profile", "standard"))

    assert done.returncode == 0, done.stderr
    out = done.stdout + done.stderr
    etc = tmp_path / "etc-brain-vault"
    seal = etc / "seal.key"
    assert seal.stat().st_size == SEAL_KEY_BYTES
    assert oct(seal.stat().st_mode & 0o777) == "0o400"
    assert oct(etc.stat().st_mode & 0o777) == "0o700"
    assert (etc / "recovery.key").read_text(encoding="utf-8").strip() == RECOVERY
    assert oct((etc / "recovery.key").stat().st_mode & 0o777) == "0o400"
    assert (etc / "deploy.token").read_text(encoding="utf-8") == DEPLOY_TOKEN
    assert oct((etc / "deploy.token").stat().st_mode & 0o777) == "0o400"
    for secret in (RECOVERY, ROOT, APP_TOKEN, WORKER_TOKEN, DEPLOY_TOKEN):
        assert secret not in out
    argv = (state / "argv").read_text(encoding="utf-8")
    for secret in (RECOVERY, ROOT, APP_TOKEN, WORKER_TOKEN, DEPLOY_TOKEN):
        assert secret not in argv
    assert "unseal" not in argv
    assert f"network create {VAULT_NETWORK_NAME}" not in argv  # the stand-in says it exists

    calls = [one.split("|", 1) for one in lines(state / "calls")]
    as_root = [asked for presented, asked in calls if presented == ROOT]
    assert not [one for one in as_root if one.startswith("audit")]
    assert [one for one in as_root if one.startswith("secrets enable")] == [
        f"secrets enable -path={engine} kv-v2" for engine in ENGINES
    ]
    policies = sorted(path.stem for path in (REPO / "ops/openbao/policies").glob("*.hcl"))
    assert DEPLOY_POLICY in policies
    assert sorted(path.name.removeprefix("policy.") for path in state.glob("policy.*")) == policies
    assert (state / "policy.application").read_text(encoding="utf-8").strip() == (
        REPO / "ops/openbao/policies/application.hcl"
    ).read_text(encoding="utf-8").replace("\r", "").strip()
    assert [one for one in as_root if one.startswith("write auth/token/roles")] == [
        f"write auth/token/roles/{RUN_TOKEN_ROLE} allowed_policies={RUN_POLICY} orphan=false "
        "renewable=false token_no_default_policy=true "
        f"token_explicit_max_ttl={RUN_ROLE_MAX_TTL_SECONDS}",
        f"write auth/token/roles/{SEND_TOKEN_ROLE} allowed_policies={SEND_POLICY} orphan=false "
        "renewable=false token_no_default_policy=true "
        f"token_explicit_max_ttl={SEND_ROLE_MAX_TTL_SECONDS}",
        f"write auth/token/roles/{ROTATE_TOKEN_ROLE} allowed_policies={ROTATE_POLICY} "
        "orphan=false renewable=false token_no_default_policy=true "
        f"token_explicit_max_ttl={ROTATE_ROLE_MAX_TTL_SECONDS}",
        f"write auth/token/roles/{PERSON_TOKEN_ROLE} allowed_policies={PERSON_POLICY} "
        "orphan=false renewable=false token_no_default_policy=true "
        f"token_explicit_max_ttl={PERSON_ROLE_MAX_TTL_SECONDS}",
    ]
    defined = [one for one in as_root if one.startswith("kv metadata put")]
    assert [one.rsplit(" ", 1)[-1] for one in defined] == sorted(SLOT_SCOPES)
    for name, slot in SLOT_SCOPES.items():
        assert (state / f"slot.{name}").read_text(encoding="utf-8").strip() == (
            f"map[not_requested:{'; '.join(slot.refuse)} scopes:{'; '.join(slot.request)}]"
        )
    assert f"auth tune -max-lease-ttl={TOKEN_METHOD_MAX_TTL} token/" in as_root
    assert [one for one in as_root if one.startswith("token create")] == [
        f"token create -policy=application -orphan -period={TOKEN_PERIOD} -field=token",
        f"token create -policy=worker -orphan -period={TOKEN_PERIOD} -field=token",
        f"token create -policy={DEPLOY_POLICY} -no-default-policy -orphan "
        f"-period={DEPLOY_TOKEN_PERIOD} -field=token",
    ]
    revoked = next(i for i, (who, asked) in enumerate(calls) if asked == "token revoke -self")
    assert calls[revoked][0] == ROOT
    assert all(who != ROOT for who, _ in calls[revoked + 1 :])
    # The apply step's done test ran with the deploy token and found everything in force.
    after = calls[revoked + 1 :]
    assert [who for who, _ in after if who] and all(who in ("", DEPLOY_TOKEN) for who, _ in after)
    assert not [
        asked
        for _, asked in after
        if not asked.startswith(("read", "secrets list", "status", "token lookup"))
    ]
    assert f"{VAULT_STEPS[4]} - already done, skipping" in done.stdout

    assert lines(home / INSTALL_ENV_FILE)[-3:] == [
        f"BRAIN_VAULT_ADDRESS={VAULT_ADDRESS}",
        f"BRAIN_VAULT_TOKEN={APP_TOKEN}",
        f"{WORKER_VAULT_CHOICE}={WORKER_TOKEN}",
    ]
    composed = done.stdout.strip().splitlines()[-1].removeprefix("files: ").split()
    assert [one.rsplit("/", 1)[-1] for one in composed[1::2]] == [
        *files_for("standard"),
        VAULT_OVERLAY,
        WORKER_VAULT_OVERLAY,
    ]


def test_the_recovery_split_prints_five_pieces_once_and_writes_no_recovery_file(
    tmp_path: Path,
) -> None:
    """The stricter choice: five recovery pieces for five people, printed once, numbered, and kept
    nowhere on the server. Delete this and `--recovery-split` can write the pieces to a file beside
    the seal key, which is one person holding all five, or print the root token with them."""
    done, _, state = installing(
        tmp_path, ("--release", "v1.0.0", "--profile", "standard", "--recovery-split")
    )

    assert done.returncode == 0, done.stderr
    for n, piece in enumerate(PIECES, 1):
        assert done.stdout.count(f"piece {n} of {RECOVERY_SPLIT.shares}: {piece}") == 1
    assert ROOT not in done.stdout + done.stderr
    assert not (tmp_path / "etc-brain-vault" / "recovery.key").exists()
    asked = [one.split("|", 1)[1] for one in lines(state / "calls")]
    assert "operator init -recovery-shares=5 -recovery-threshold=3" in asked
    assert "operator init -recovery-shares=1 -recovery-threshold=1" not in asked


def test_a_second_run_skips_every_vault_step_that_writes_and_still_composes_the_vault_in(
    tmp_path: Path,
) -> None:
    """Safe to run twice, which for the vault means never initialising it again and never writing a
    second seal key: a key made now could not open the vault the first one sealed. Delete this and a
    re-run could replace the seal key, or lose the overlays it no longer remembers choosing."""
    first, home, state = installing(tmp_path, ("--release", "v1.0.0", "--profile", "standard"))
    assert first.returncode == 0, first.stderr
    (state / "calls").unlink()
    seal = (tmp_path / "etc-brain-vault" / "seal.key").read_bytes()

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
    for name in VAULT_STEPS[:5]:
        assert f"{name} - already done, skipping" in second.stdout
    assert (tmp_path / "etc-brain-vault" / "seal.key").read_bytes() == seal
    assert "operator init -recovery" not in "\n".join(lines(state / "calls"))
    assert not any(one.startswith(ROOT) for one in lines(state / "calls"))
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


def test_the_engines_enabled_are_the_five_the_product_writes_and_the_policy_names() -> None:
    """Delete this and an engine the console writes to is one no release ever enabled, which
    reads as the vault refusing: a 404 on a write is an engine that is not mounted. The template
    signing key's and the join-key pepper's engines are granted on their one slot rather than on
    every name, which is the write-once rule of `brain.ops.template_key` and
    `brain.ops.join_key_pepper`, so each is held to that exact path."""
    assert ENGINES == ("providers", "webhooks", "connector_keys", "template_signing", "resolution")
    assert tuple(one.rstrip("/") for one in STATIC_PREFIXES) == ENGINES
    policy = (REPO / "ops/openbao/policies/application.hcl").read_text(encoding="utf-8")
    for engine in ENGINES[:-2]:
        assert f'path "{engine}/data/+"' in policy
    assert 'path "template_signing/data/key"' in policy
    assert 'path "template_signing/data/+"' not in policy
    assert 'path "resolution/data/pepper"' in policy
    assert 'path "resolution/data/+"' not in policy
    applied = (REPO / APPLY_SCRIPT).read_text(encoding="utf-8").splitlines()
    assert applied.count(f"for engine in {' '.join(ENGINES)}; do") == 2


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


def vault_config() -> str:
    """The vault's BAO_LOCAL_CONFIG as shipped, with HCL comments cut off."""
    body = load(VAULT_PROJECT)["services"][VAULT_SERVICE]
    config = str(body["environment"]["BAO_LOCAL_CONFIG"])
    return "\n".join(line.split("#", 1)[0] for line in config.splitlines())


def audit_devices(config: str) -> dict[str, dict[str, str]]:
    """Every `audit "file" "<path>" { options { k = "v" } }` block, as path to its options."""
    found: dict[str, dict[str, str]] = {}
    block = re.compile(r'audit\s+"file"\s+"([\w-]+)"\s*\{\s*options\s*\{([^}]*)\}\s*\}')
    for path, options in block.findall(config):
        found[path] = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', options))
    return found


def test_the_shipped_vault_config_starts_on_openbao_2_4_and_audits_both_devices() -> None:
    """Found on the owner's install with openbao 2.4.1: a `disable_mlock` line stops the vault
    starting, `bao audit enable` is refused so devices must be declared, `stderr` is read as a
    file name, and without BAO_ADDR `bao` dials https and the healthcheck never passes. Delete
    this and any of the four comes back with every other test green."""
    body = load(VAULT_PROJECT)["services"][VAULT_SERVICE]
    config = vault_config()

    assert "disable_mlock" not in config
    assert "IPC_LOCK" not in (body.get("cap_add") or [])
    assert audit_devices(config) == {
        "file": {
            "file_path": "/openbao/logs/audit.log",
            "log_raw": "false",
            "hmac_accessor": "true",
            "mode": "0644",
        },
        "stdout": {"file_path": "stdout", "log_raw": "false"},
    }
    assert body["environment"]["BAO_ADDR"] == f"http://127.0.0.1:{VAULT_PORT}"
    assert "bao status" in " ".join(body["healthcheck"]["test"])
    # The file device writes onto the volume the worker's overlay mounts as the audit log.
    logs = next(one for one in body["volumes"] if one.startswith("brain-vault-logs:"))
    mounted = logs.split(":", 1)[1]
    assert audit_devices(config)["file"]["file_path"] == f"{mounted}/audit.log"
    assert VAULT_AUDIT_LOG.rsplit("/", 1)[1] == "audit.log"


def test_the_config_reader_sees_a_mlock_line_and_a_stderr_device() -> None:
    """The positive control: a reader that found nothing would pass the test above."""
    old = (
        'disable_mlock = false\naudit "file" "stderr" {\n  options {\n'
        '    file_path = "stderr"\n  }\n}\n'
    )
    assert "disable_mlock" in old
    assert audit_devices(old) == {"stderr": {"file_path": "stderr"}}


def checking_swap(tmp_path: Path, swaps: str, *settings: str) -> subprocess.CompletedProcess[str]:
    """The committed script's helpers and its swap check, reading `swaps` as /proc/swaps."""
    script = committed()
    opening = 'BRAIN_SWAP_PLAIN=""'
    check = script[script.index(opening) : script.index('fi\nsay "  note: a reverse proxy')]
    table = tmp_path / "swaps"
    table.write_text(swaps, encoding="utf-8", newline="\n")
    body = "\n".join(
        (
            script[: script.index("usage() {")],
            *settings,
            check.replace("/proc/swaps", table.as_posix()) + "fi",
            'printf "refusals=%s\n" "$BRAIN_REFUSALS"',
        )
    )
    runner = tmp_path / "swap.sh"
    runner.write_text(body, encoding="utf-8", newline="\n")
    return subprocess.run(
        [a_shell(), runner.as_posix()],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


HEADER = "Filename   Type   Size   Used   Priority\n"
A_SWAP_FILE = HEADER + "/swapfile  file   2097148   0   -2\n"


def test_plain_swap_is_said_and_stops_the_install_unless_somebody_accepts_it(
    tmp_path: Path,
) -> None:
    """Most VPS images ship a plain /swapfile, the owner's included. Delete this and the check
    can go back to turning those machines away, or wave them through with nothing said."""
    refused = checking_swap(tmp_path, A_SWAP_FILE)
    assert "refusals=1" in refused.stdout
    assert "swaps to /swapfile, which is not encrypted" in refused.stdout
    assert "--accept-unencrypted-swap" in refused.stderr
    assert "accepted:" not in refused.stdout

    accepted = checking_swap(tmp_path, A_SWAP_FILE, 'BRAIN_ACCEPT_SWAP="yes"')
    assert "refusals=0" in accepted.stdout
    assert "swaps to /swapfile, which is not encrypted" in accepted.stdout
    assert "accepted: unencrypted swap, by --accept-unencrypted-swap" in accepted.stdout
    assert "Type yes to continue with unencrypted swap:" in committed()
    assert '--accept-unencrypted-swap) BRAIN_ACCEPT_SWAP="yes"; shift ;;' in committed()


def test_no_swap_zram_or_no_vault_asks_nothing(tmp_path: Path) -> None:
    """The negative controls: a check that always spoke would pass the test above."""
    for swaps, settings in (
        (HEADER, ()),
        (HEADER + "/dev/zram0 partition 1048572 0 100\n", ()),
        (A_SWAP_FILE, ('BRAIN_VAULT="no"',)),
    ):
        done = checking_swap(tmp_path, swaps, *settings)
        assert done.stdout == "refusals=0\n", (swaps, settings, done.stdout)
        assert done.stderr == ""


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
            if step.name == VAULT_STEPS[2]:
                continue
            assert found.group("rest").lstrip().startswith("|"), (step.name, line)
    assert step_named(VAULT_STEPS[2]).presents_once


def test_no_piece_or_token_is_put_on_an_argument_list_or_in_a_here_string() -> None:
    """Delete this and the obvious spelling, `bao operator unseal <piece>` or
    `-e BAO_TOKEN=<token>`,
    puts a secret where every local user can read it for as long as the command runs, and a
    here-string writes it to a temporary file on the bash an older distribution ships."""
    text = "\n".join(step_named(name).run for name in VAULT_STEPS) + render_apply()
    assert "<<" not in text
    # A vault that opens itself is never given a piece, by the command or by the API.
    assert "operator unseal" not in text
    assert "sys/unseal" not in text
    assert "BAO_TOKEN=$" not in text.replace('BAO_TOKEN="$', "")
    assert "-e BAO_TOKEN=" not in text
    assert "-e BAO_TOKEN " in text


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
    assert step_named(VAULT_STEPS[5]).run.splitlines() == list(chosen)
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


# ============================================================================ apply-release.sh
def applying(
    tmp_path: Path, *args: str, token: str = DEPLOY_TOKEN, state: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the committed apply script against the stand-in vault, the token given in its file."""
    home, etc = an_install_with_the_vaults_files(tmp_path)
    etc.mkdir(exist_ok=True)
    if token:
        (etc / "deploy.token").write_text(token, encoding="utf-8", newline="\n")
    vault = state or tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(stand_in(), encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    shell = shutil.which("sh")
    assert shell is not None
    env = {key: value for key, value in os.environ.items() if key not in {"BAO_TOKEN", "BAO_ADDR"}}
    done = subprocess.run(
        [shell, (home / APPLY_SCRIPT).as_posix(), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={
            **env,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "FAKE_VAULT": vault.as_posix(),
        },
    )
    return done, vault


def test_the_committed_apply_script_is_what_the_module_renders() -> None:
    """Generated, and every path that applies a release's vault changes runs the committed copy: the
    installer, the update, the rollback, the automatic deploy and the switch. Delete this and an
    engine added to the module reaches none of them, or an edit to the file is overwritten silently
    by the next regeneration."""
    assert (REPO / APPLY_SCRIPT).read_text(encoding="utf-8") == render_apply()


def test_a_release_applies_its_own_changes_reads_them_back_and_a_second_run_writes_nothing(
    tmp_path: Path,
) -> None:
    """**Owner decision 2 of needs-rupash 114, run.** On a vault holding none of it, the deploy
    token enables the four engines, loads every policy except its own, defines the run role and the
    eight slots, and says they are in force; `--check` then passes; and a second apply writes
    nothing, because a deploy that changed nothing must change nothing.

    Delete this and the apply script can write and never read back, or rewrite every slot on every
    deploy, or report success over a policy the vault did not take."""
    state = tmp_path / "vault"
    state.mkdir()
    # The deploy policy is loaded by the installer under root before the deploy token exists.
    (state / "policy.deploy").write_text(
        (REPO / "ops/openbao/policies/deploy.hcl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    before, _ = applying(tmp_path / "a", "--check", state=state)
    assert before.returncode == 1
    assert "not in force: the providers engine" in before.stderr
    assert "not in force: the application policy" in before.stderr

    first, _ = applying(tmp_path / "b", state=state)
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == (
        f"vault: in force: {len(ENGINES)} engines, "
        f"{len(list((REPO / 'ops/openbao/policies').glob('*.hcl')))} policies, 4 token roles "
        f"({RUN_TOKEN_ROLE}, {SEND_TOKEN_ROLE}, {ROTATE_TOKEN_ROLE}, {PERSON_TOKEN_ROLE}) and "
        f"{len(SLOT_SCOPES)} credential slots"
    )
    calls = lines(state / "calls")
    assert all(one.startswith((f"{DEPLOY_TOKEN}|", "|status")) for one in calls)
    assert f"{DEPLOY_TOKEN}|policy write deploy -" not in calls

    checked, _ = applying(tmp_path / "c", "--check", state=state)
    assert checked.returncode == 0, checked.stderr

    (state / "calls").unlink()
    again, _ = applying(tmp_path / "d", state=state)
    assert again.returncode == 0, again.stderr
    writes = [
        one
        for one in lines(state / "calls")
        if one.split("|", 1)[1].startswith(("secrets enable", "policy write", "write ", "kv "))
    ]
    assert writes == []
    for secret in (DEPLOY_TOKEN, ROOT):
        assert secret not in first.stdout + first.stderr + again.stdout + again.stderr


def test_a_release_enables_the_pepper_engine_and_never_writes_or_reads_inside_it(
    tmp_path: Path,
) -> None:
    """**The join-key pepper survives every release, rollback and re-run, because none of them
    touches it.** The apply script enables the `resolution` engine where it is missing and does
    nothing else there: no read, no write, no metadata, under the root token at install or the
    deploy token after. The deploy policy names no path in the engine at all, so even an edited
    script could not reach the pepper with the token a release runs as. See
    `brain.ops.join_key_pepper.THE_RELEASE_SCRIPT_CANNOT_CREATE_IT_SO_THE_APPLICATION_DOES`.

    Delete this and a later edit can teach the release to create the pepper, which needs the
    deploy token's own policy changed and holds back every release on every install already
    running (`test_a_release_that_changes_the_deploy_policy_is_refused_in_words`), or to write it,
    which unjoins every stored digest."""
    from brain.ops.join_key_pepper import PEPPER_SLOT

    mount = PEPPER_SLOT.split("/", 1)[0]
    deploy = _granted(REPO / "ops/openbao/policies/deploy.hcl")
    assert not [path for path in deploy if path.startswith(f"{mount}/")]

    state = tmp_path / "vault"
    state.mkdir()
    (state / "policy.deploy").write_text(
        (REPO / "ops/openbao/policies/deploy.hcl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for run in ("first", "again"):
        done, _ = applying(tmp_path / run, state=state)
        assert done.returncode == 0, done.stderr
    touching = [one.split("|", 1)[1] for one in lines(state / "calls") if mount in one]
    assert touching == [f"secrets enable -path={mount} kv-v2"]


def _granted(path: Path) -> set[str]:
    """Every path a policy file names in a `path "..."` rule, comments cut off."""
    text = "\n".join(
        line.split("#", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
    )
    return set(re.findall(r'path\s+"([^"]+)"', text))


def test_a_release_that_changes_the_deploy_policy_is_refused_in_words(tmp_path: Path) -> None:
    """The one policy a deploy may not load itself, so no deploy can widen its own reach. Delete
    this and the refusal can become a generic "would not load", which sends somebody looking for a
    fault
    in the vault instead of for the root token the change needs."""
    state = tmp_path / "vault"
    state.mkdir()
    (state / "policy.deploy").write_text("an older deploy policy\n", encoding="utf-8")
    done, _ = applying(tmp_path / "a", state=state)
    assert done.returncode == 1
    assert "changes the deploy token's own policy" in done.stderr
    assert "In an emergency" in done.stderr


def test_with_no_deploy_token_the_apply_says_so_and_exits_with_its_own_status(
    tmp_path: Path,
) -> None:
    """An install made before the vault opened itself has no deploy token. Its update must carry on
    (the release's step reads this status and says what moves it), so the status has to be told
    apart from a failure. Delete this and every update of such an install either stops or reports
    the vault's changes applied when nothing was."""
    done, state = applying(tmp_path, token="")
    assert done.returncode == NO_DEPLOY_TOKEN_EXIT
    assert "switch-to-auto-unseal.sh" in done.stderr
    assert not (state / "calls").exists()


def test_the_update_carries_on_past_an_install_with_no_deploy_token_and_stops_on_a_failure() -> (
    None
):
    """The step the update and the rollback share with the installer, read as the shell it renders.
    Delete this and an older install's update can stop at the vault step for ever, or a failed apply
    can be passed over as though it were an older install."""
    run = step_named(VAULT_STEPS[4]).run
    assert f'test "$BRAIN_VAULT_APPLIED" -eq {NO_DEPLOY_TOKEN_EXIT}' in run
    assert 'elif test "$BRAIN_VAULT_APPLIED" -ne 0; then' in run
    for render in (render_update, render_rollback):
        rendered = render(repository=REPOSITORY, tunnel_token=TOKEN)
        assert re.search(rf"^# step \d+ of \d+: {re.escape(VAULT_STEPS[4])}$", rendered, re.M)
        assert rendered.index(VAULT_STEPS[4]) < rendered.index("recreate the containers")


# ============================================================================ the seal
def test_the_vault_opens_itself_from_a_root_only_key_file_and_never_from_the_environment() -> None:
    """**Owner decision 1 of needs-rupash 114, read out of the compose file.** A static seal
    naming a file; the file bind-mounted read-only from the path the installer writes, refused
    rather than invented when missing; copied by the entrypoint into a tmpfs the vault's own user
    reads; and the vault still dropping root. Delete this and the seal can move to an environment
    variable, which `docker inspect` prints, or the mount can go back to the short form, where a
    missing key becomes
    an empty directory and a vault that never opens."""
    body = load(VAULT_PROJECT)["services"][VAULT_SERVICE]
    config = vault_config()
    seal = re.search(r'seal\s+"static"\s*\{([^}]*)\}', config)
    assert seal is not None
    fields = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', seal.group(1)))
    assert fields["current_key"].startswith("file://")
    assert "env://" not in config
    inside = fields["current_key"].removeprefix("file://")
    mounts = [one for one in body["volumes"] if isinstance(one, dict)]
    assert len(mounts) == 1
    key = mounts[0]
    assert key["type"] == "bind"
    assert key["read_only"] is True
    assert key["bind"]["create_host_path"] is False
    assert key["source"] == f"${{BRAIN_VAULT_SEAL_KEY:-{SEAL_KEY_FILE}}}"
    entry = " ".join(body["entrypoint"])
    assert f"{key['target']} {inside}" in entry
    assert "install -o openbao -g openbao -m 0400" in entry
    assert entry.rstrip().endswith("exec /usr/local/bin/docker-entrypoint.sh server")
    assert any(one.startswith(inside.rsplit("/", 1)[0] + ":") for one in body["tmpfs"])
    assert "BAO_SKIP_DROP_ROOT" not in str(body.get("environment"))
    assert "SKIP_DROP_ROOT" not in entry


def test_the_vaults_names_default_to_the_ones_every_other_file_reads() -> None:
    """The container, the network and both volumes are parameters so the switch can bring a vault up
    under the old one's names, and each default is a name another file depends on: the address the
    installer writes, the external network the application's overlay joins, and the audit volume
    the worker mounts by name. Delete this and a default can drift from the file that reads it."""
    project = load(VAULT_PROJECT)
    body = project["services"][VAULT_SERVICE]
    assert body["container_name"] == "${BRAIN_VAULT_CONTAINER:-brain-vault}"
    network = project["networks"][VAULT_NETWORK]
    assert network["external"] is True
    assert network["name"] == f"${{BRAIN_VAULT_NETWORK:-{VAULT_NETWORK_NAME}}}"
    assert VAULT_NETWORK_NAME == VAULT_NETWORK
    assert project["volumes"]["brain-vault-logs"]["name"] == (
        f"${{BRAIN_VAULT_LOGS_VOLUME:-{VAULT_AUDIT_VOLUME}}}"
    )
    assert project["volumes"]["brain-vault-data"]["name"] == (
        "${BRAIN_VAULT_DATA_VOLUME:-brain-vault_brain-vault-data}"
    )
    assert f"docker network create {VAULT_NETWORK_NAME}" in step_named(VAULT_STEPS[1]).run


def test_the_seal_key_step_never_writes_over_a_key_or_makes_one_for_an_older_vault() -> None:
    """A key made now could not open a vault sealed with another, so the step is skipped when a key
    is there and when a vault is already initialised. Delete this and a second run can replace the
    seal key of a running vault, which opens nothing at its next restart."""
    step = step_named(VAULT_STEPS[0])
    assert f"test -s {SEAL_KEY_FILE}" in step.already_done
    assert "operator init -status" in step.already_done
    assert f"mv {SEAL_KEY_FILE}.new {SEAL_KEY_FILE}" in step.run
    assert f"head -c {SEAL_KEY_BYTES} /dev/urandom" in step.run
    assert "printf" not in step.run.replace('say "', "")


# ============================================================================ the deploy policy
def test_the_deploy_token_may_load_policies_and_can_neither_read_a_secret_nor_widen_itself() -> (
    None
):
    """What `policies/deploy.hcl` grants, parsed. Measured against OpenBao 2.4.1 on 2026-09-29: the
    most specific path wins, so the two exact read-only rules replace the policy glob for the deploy
    token's own policy and the default one. Delete this and a well-meant edit can let a deploy read
    a provider key, mint a token, remove an engine, or rewrite its own policy and so everything."""
    text = (REPO / "ops/openbao/policies/deploy.hcl").read_text(encoding="utf-8")
    live = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    granted = {
        path: re.findall(r'"([^"]+)"', caps)
        for path, caps in re.findall(
            r'path\s+"([^"]+)"\s*\{[^}]*capabilities\s*=\s*\[([^\]]*)\]', live, re.S
        )
    }
    assert granted["sys/policies/acl/deploy"] == ["read"]
    assert granted["sys/policies/acl/default"] == ["read"]
    assert set(granted["sys/policies/acl/*"]) == {"create", "update", "read", "list"}
    assert not [path for path, caps in granted.items() if "delete" in caps or "sudo" in caps]
    assert not [path for path in granted if "/data/" in path or path.endswith("/data")]
    assert not [path for path in granted if path.startswith("auth/token/create")]
    assert set(granted) <= {
        "sys/policies/acl/*",
        "sys/policies/acl",
        "sys/policies/acl/deploy",
        "sys/policies/acl/default",
        "sys/mounts",
        "sys/mounts/*",
        "auth/token/roles/*",
        "connector_keys/metadata/*",
        "auth/token/lookup-self",
        "auth/token/renew-self",
    }


def ignored_by_the_build(path: str) -> bool:
    """Whether `.dockerignore` keeps this path out of the build, reading its rules in order."""
    excluded = False
    for line in (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines():
        rule = line.strip()
        if not rule or rule.startswith("#"):
            continue
        negated = rule.startswith("!")
        pattern = rule.removeprefix("!")
        parts = path.split("/")
        prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
        if any(fnmatch.fnmatch(one, pattern) for one in prefixes):
            excluded = not negated
    return excluded


def test_the_image_carries_its_releases_vault_changes_where_the_deploy_hook_reads_them() -> None:
    """A server that deploys from the image alone (`ops/deploy/brain-deploy`) has no checkout, so a
    release's policies reach it inside the image or not at all. Three halves, each of which alone is
    satisfied by a pair that disagrees: the Dockerfile copies the script and the policies to where
    the hook copies them from, and `.dockerignore`, which keeps the rest of `ops` out, lets both
    through. Delete this and a trimmed build drops them, and every deploy says its image carries no
    vault changes while its policies wait for nobody."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    copied = dict(
        re.findall(r"^COPY\s+(?:--\S+\s+)*(ops/openbao/\S+)\s+(\S+)\s*$", dockerfile, re.M)
    )
    assert copied == {
        APPLY_SCRIPT: f"/app/{APPLY_SCRIPT}",
        "ops/openbao/policies": "/app/ops/openbao/policies",
    }
    hook = (REPO / "ops/deploy/brain-deploy").read_text(encoding="utf-8")
    assert 'docker cp "$cid:/app/ops/openbao/." "$dir/"' in hook
    assert 'sh "$dir/apply-release.sh"' in hook
    for path in (APPLY_SCRIPT, *(f"ops/openbao/policies/{one.name}" for one in POLICY_FILES)):
        assert not ignored_by_the_build(path), path
    assert ignored_by_the_build("ops/openbao/UNSEAL.md")
    assert ignored_by_the_build(SWITCH_SCRIPT)
