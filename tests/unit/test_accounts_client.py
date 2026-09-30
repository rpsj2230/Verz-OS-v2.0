"""Setting up the staff sync's accounts client: the application's command and the release's script.

`brain.ops.accounts_key` is what the application answers; `ops/keycloak/accounts-client.sh` is what
the server runs after every release and the installer runs once. The script is run here for real,
with `docker` replaced by a stand-in that plays the application's container and Keycloak's, so the
order of its steps, where the secret goes and what never reaches an argument are measured rather
than read off the file. Nothing here has called a Keycloak or a vault.

Task ids: M1.6.16
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain.connectors.sign_in_accounts import CLIENT_ID, CLIENT_ROLES, PROFILE_ATTRIBUTES
from brain.ops import accounts_key
from brain.ops.accounts_key import (
    SLOT,
    AccountsKeyError,
    client_representation,
    credential_for,
    held,
    keep,
    realm_name,
)
from brain.ops.credentials import KEY_FIELD, Credentials
from brain.ops.openbao import StaticVersion

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "keycloak" / "accounts-client.sh"
SH = shutil.which("sh")

#: What Keycloak made, and a string nothing else could contain.
SECRET = "SENTINEL-accounts-client-secret-7c1e"
#: Keycloak's own administrator password, as its container's environment holds it.
ADMIN_PASSWORD = "SENTINEL-keycloak-admin-password-2b9d"


# ------------------------------------------------------------------ the command
@dataclass
class Vault:
    """A vault slot store: what was written where, and nothing read back."""

    slots: dict[str, Mapping[str, str]] = field(default_factory=dict)

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        self.slots[path] = dict(fields)
        return datetime(2999, 3, 1, tzinfo=UTC)

    def static_kv_version(self, path: str) -> StaticVersion | None:
        return StaticVersion(written_at=None) if path in self.slots else None

    def read_static_kv(self, path: str) -> dict[str, object]:
        raise AssertionError("the application never reads a connector key back")


@dataclass
class Writes:
    recorded: list[tuple[str, str]] = field(default_factory=list)

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        self.recorded.append((slot, written_by))


def test_the_client_is_the_reviewed_realm_s_own_with_no_secret_and_no_browser_flow() -> None:
    """`--client` prints the export's entry, comments removed, so a realm the script adds it to and
    a realm imported fresh hold one client. Delete this and the script can make a client that
    accepts a browser sign-in or a password grant, or one Keycloak refuses for a comment field."""
    client = client_representation()

    assert client["clientId"] == CLIENT_ID == "brain-accounts"
    assert (client["publicClient"], client["serviceAccountsEnabled"]) == (False, True)
    assert not any(
        client[flow]
        for flow in ("standardFlowEnabled", "implicitFlowEnabled", "directAccessGrantsEnabled")
    )
    assert "secret" not in client
    assert not [key for key in client if key.startswith("_")]


def test_the_realm_export_gives_the_service_account_three_user_roles_and_no_other() -> None:
    """For a realm imported fresh. Delete this and the export can give the nightly job the realm's
    settings or its clients, which `THE_CLIENT_MAY_MANAGE_USERS_AND_NOTHING_ELSE` refuses."""
    realm = json.loads((REPO / "ops" / "keycloak" / "realm-export.json").read_text("utf-8"))
    (user,) = [one for one in realm.get("users") or () if one.get("serviceAccountClientId")]

    assert user["serviceAccountClientId"] == CLIENT_ID
    assert user["username"] == f"service-account-{CLIENT_ID}"
    assert list(user["clientRoles"]) == ["realm-management"]
    assert set(user["clientRoles"]["realm-management"]) == set(CLIENT_ROLES)
    assert set(CLIENT_ROLES) == {"manage-users", "view-users", "query-users"}
    assert "realmRoles" not in user and "credentials" not in user


def test_the_realm_is_the_one_the_issuer_names_and_an_unset_issuer_is_refused_in_words() -> None:
    """Delete this and the script can set up a client in a realm the worker never signs in to."""
    assert realm_name({"INSTALL_OIDC_ISSUER": "https://id.example.test/realms/acme"}) == "acme"
    with pytest.raises(AccountsKeyError):
        realm_name({"INSTALL_OIDC_ISSUER": "https://id.example.test/oauth"})


def test_the_secret_is_kept_as_the_client_s_credential_recorded_and_never_read_back() -> None:
    """What the worker's `token` reads, at `connector_keys/sign_in_accounts`, written once and
    recorded as the release's write. Delete this and the secret can be kept in a shape the run
    cannot use, or in a slot the worker's run token cannot read."""
    vault, writes = Vault(), Writes()
    credentials = Credentials(vault, writes=writes)
    assert held(credentials) is False

    asyncio.run(keep(credentials, f"{SECRET}\n", trace_id="release-accounts-client"))

    assert SLOT.path == "connector_keys/sign_in_accounts"
    assert vault.slots == {SLOT.path: {KEY_FIELD: f"{CLIENT_ID}:{SECRET}"}}
    assert credential_for(f" {SECRET} ") == f"brain-accounts:{SECRET}"
    assert writes.recorded == [(SLOT.path, "release.accounts-client")]
    assert held(credentials) is True


@pytest.mark.parametrize("given", ["", "   \n", "two words"])
def test_nothing_or_a_broken_paste_on_standard_input_keeps_nothing_and_names_no_value(
    given: str,
) -> None:
    """An empty pipe is what arrives when kcadm failed, and it must not be kept as a credential.
    Delete this and a failed read of the secret overwrites a working one with nothing."""
    vault = Vault()
    with pytest.raises(AccountsKeyError) as refused:
        asyncio.run(keep(Credentials(vault, writes=Writes()), given, trace_id="t"))
    assert vault.slots == {}
    assert "two words" not in str(refused.value)


def test_the_command_takes_one_flag_and_the_profile_on_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and the script's `--profile` step can print something that is not the realm's
    profile with the marks declared, which Keycloak then stores as the realm's profile."""
    assert accounts_key.main([]) == 2
    assert accounts_key.main(["--held", "--keep"]) == 2
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"attributes": [{"name": "email"}]})))
    assert accounts_key.main(["--profile"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [one["name"] for one in printed["attributes"]] == [
        "email",
        *(name for name, _ in PROFILE_ATTRIBUTES),
    ]
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert accounts_key.main(["--profile"]) == 1


# ------------------------------------------------------------------ the release's script
#: The stand-in docker. It plays two containers: `app-x`, the application, which answers
#: `python -m brain.ops.accounts_key`, and `kc-x`, Keycloak, which answers kcadm. Every call's
#: argv goes to `calls`, every standard input the application's --keep reads goes to `kept`.
STUB = r"""#!/bin/sh
S="$STUB_STATE"
printf '%s\n' "$*" >> "$S/calls"
case "$1" in
  inspect) echo "stub-project"; exit 0 ;;
  ps) [ -f "$S/no-keycloak" ] || echo "kc-x"; exit 0 ;;
esac
[ "$1" = exec ] || exit 0
shift
[ "$1" = -i ] && shift
who="$1"; shift
if [ "$who" = app-x ]; then
  case "$*" in
    *"accounts_key --held"*) [ -f "$S/held" ] && exit 0; exit 1 ;;
    *"accounts_key --realm"*) echo "brain"; exit 0 ;;
    *"accounts_key --client"*) echo '{"clientId": "brain-accounts"}'; exit 0 ;;
    *"accounts_key --profile"*) cat; exit 0 ;;
    *"accounts_key --keep"*) cat > "$S/kept"; [ -s "$S/kept" ] || exit 1; exit 0 ;;
  esac
  exit 1
fi
case "$1" in
  sh) exit "$(cat "$S/login-exit" 2>/dev/null || echo 0)" ;;
  rm) echo "removed $*" >> "$S/removed"; exit 0 ;;
esac
shift
case "$*" in
  "get clients/client-uuid/client-secret"*) echo "$SENTINEL_SECRET"; exit 0 ;;
  "get clients"*) [ -f "$S/made" ] && echo "client-uuid"; exit 0 ;;
  "create clients"*) cat > "$S/client-json"; touch "$S/made"; exit 0 ;;
  "add-roles"*) exit 0 ;;
  "get users/profile"*) echo '{"attributes": [{"name": "email"}]}'; exit 0 ;;
  "update users/profile"*) cat > "$S/profile"; exit 0 ;;
esac
exit 1
"""

pytestmark_sh = pytest.mark.skipif(SH is None, reason="the release's script is POSIX sh")


@dataclass
class Ran:
    code: int
    output: str
    calls: list[str]
    state: Path

    def read(self, name: str) -> str:
        one = self.state / name
        return one.read_text(encoding="utf-8") if one.exists() else ""


def run_script(
    tmp_path: Path,
    *,
    is_held: bool = False,
    keycloak: bool = True,
    made: bool = False,
    login_exit: int = 0,
) -> Ran:
    state, bin_dir = tmp_path / "state", tmp_path / "bin"
    state.mkdir()
    bin_dir.mkdir()
    (state / "calls").write_text("", encoding="utf-8", newline="\n")
    (state / "login-exit").write_text(str(login_exit), encoding="utf-8", newline="\n")
    for flag, name in ((is_held, "held"), (not keycloak, "no-keycloak"), (made, "made")):
        if flag:
            (state / name).write_text("", encoding="utf-8", newline="\n")
    fake = bin_dir / "docker"
    fake.write_text(STUB, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": state.as_posix(),
        "SENTINEL_SECRET": SECRET,
        "BRAIN_APP_CONTAINER": "app-x",
        # Keycloak's own environment is its container's; on this host it must never be read.
        "KC_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD,
    }
    assert SH is not None
    done = subprocess.run(
        [SH, SCRIPT.as_posix()], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    calls = (state / "calls").read_text(encoding="utf-8").splitlines()
    return Ran(done.returncode, done.stdout + done.stderr, calls, state)


@pytestmark_sh
def test_the_script_is_posix_sh() -> None:
    """It runs on a server's `sh`, which is not always bash. Delete this and a bashism ships."""
    assert SH is not None
    assert subprocess.run([SH, "-n", SCRIPT.as_posix()], check=False).returncode == 0


@pytestmark_sh
def test_on_a_realm_without_it_the_script_makes_the_client_gives_its_roles_and_keeps_its_secret(
    tmp_path: Path,
) -> None:
    """The whole path, in order: asked whether held, Keycloak found by label, signed in inside its
    container, the client made from the application's copy, its three roles, the marks declared,
    and the secret piped from kcadm into the application's --keep. Delete this and a step can go
    missing or move before the one it needs, with the file still reading well."""
    ran = run_script(tmp_path)

    assert ran.code == 0, ran.output
    assert ran.read("kept").strip() == SECRET
    assert json.loads(ran.read("client-json")) == {"clientId": "brain-accounts"}
    assert json.loads(ran.read("profile")) == {"attributes": [{"name": "email"}]}
    roles = next(one for one in ran.calls if "add-roles" in one)
    for role in ("manage-users", "view-users", "query-users"):
        assert f"--rolename {role}" in roles
    assert "--cclientid realm-management" in roles
    assert "--uusername service-account-brain-accounts" in roles
    order = [
        next(i for i, one in enumerate(ran.calls) if marker in one)
        for marker in (
            "accounts_key --held",
            "ps --filter",
            "kc-x sh -c",
            "create clients",
            "add-roles",
            "update users/profile",
        )
    ]
    assert order == sorted(order)
    # The secret's read and the keep are two ends of one pipe, started together, so in either order.
    piped = [
        next(i for i, one in enumerate(ran.calls) if marker in one)
        for marker in ("client-secret", "accounts_key --keep")
    ]
    assert min(piped) > order[-1]
    assert ran.read("removed").strip() != ""


@pytestmark_sh
def test_neither_the_secret_nor_the_administrator_s_password_is_ever_an_argument_or_printed(
    tmp_path: Path,
) -> None:
    """Arguments are readable by every user on the server in `ps`, and output lands in the deploy
    journal. Delete this and a change that passes either as a flag, or echoes the secret, ships."""
    ran = run_script(tmp_path)

    assert ran.code == 0, ran.output
    everything = "\n".join([*ran.calls, ran.output])
    assert SECRET not in everything
    assert ADMIN_PASSWORD not in everything
    login = next(one for one in ran.calls if "kc-x sh -c" in one)
    assert "KC_CLI_PASSWORD=" in login
    assert "--password" not in login


@pytestmark_sh
def test_the_script_never_asks_keycloak_to_send_anybody_anything(tmp_path: Path) -> None:
    """The owner's rule, held at the release as well as in the sync. Delete this and a step that
    sends an invitation or a verification email can be added to the release's set-up."""
    ran = run_script(tmp_path)

    for path in ("execute-actions-email", "send-verify-email", "reset-password-email"):
        assert not [one for one in ran.calls if path in one]


@pytestmark_sh
def test_once_held_it_does_nothing_and_a_realm_that_has_the_client_is_not_given_a_second(
    tmp_path: Path,
) -> None:
    """Idempotent both ways. Delete this and every deploy rewrites the secret, or makes a second
    client beside the first."""
    (tmp_path / "held").mkdir()
    (tmp_path / "made").mkdir()
    done = run_script(tmp_path / "held", is_held=True)
    existing = run_script(tmp_path / "made", made=True)

    assert done.code == 0
    assert done.calls == ["exec -i app-x python -m brain.ops.accounts_key --held"]
    assert existing.code == 0, existing.output
    assert not [one for one in existing.calls if "create clients" in one]
    assert existing.read("kept").strip() == SECRET


@pytestmark_sh
def test_with_no_keycloak_beside_the_application_it_says_so_and_changes_nothing(
    tmp_path: Path,
) -> None:
    """An install signing in elsewhere. Delete this and such an install fails every deploy's step,
    or is left with no sentence saying why the sync makes no accounts."""
    ran = run_script(tmp_path, keycloak=False)

    assert ran.code == 0, ran.output
    assert "no Keycloak runs beside" in ran.output
    assert ran.read("kept") == ""
    assert not [one for one in ran.calls if "kcadm" in one]


@pytestmark_sh
def test_a_refused_administrator_sign_in_fails_the_step_and_keeps_nothing(tmp_path: Path) -> None:
    """Delete this and a Keycloak whose administrator password was changed reads as set up, or
    leaves kcadm's session file behind in Keycloak's container."""
    ran = run_script(tmp_path, login_exit=1)

    assert ran.code == 1
    assert "could not sign in" in ran.output
    assert ran.read("kept") == ""
    assert ran.read("removed").strip() != ""
