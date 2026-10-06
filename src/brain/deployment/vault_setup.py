"""The installer runs the secrets vault, which opens itself, and every release keeps it current.

A provider key was kept only where a vault was attached, and the installer attached none, so on a
fresh hosted install the setup wizard refused the key it asked for. This module is the installer's
vault steps, which is how the wizard's key has somewhere to go on the first run. See
`THE_VAULT_RUNS_WHEREVER_A_CREDENTIAL_IS_KEPT`.

**Since 2026-09-29 the vault opens itself, and nobody holds a piece to reopen it.** Until then the
installer printed five unseal pieces and every restart of the vault needed three people. On
2026-09-29 a release changed two policies, loading them needed a root token from three pieces, and
the owner could not find his. He decided (`docs/needs-rupash.md` item 114) that the vault unseals
itself from a key file only root on the server can read, that every release applies its own
policies, engines and roles during deploy, and that recovery pieces are an optional emergency spare.
The trade-off is written there in plain words: anyone with root on the server can open the vault,
and on one server that person can already read the running application's memory. See
`THE_VAULT_OPENS_ITSELF_FROM_A_KEY_ONLY_ROOT_CAN_READ`.

**Five steps, and the split is where the secrets are.** Making the seal key writes one root-only
file and nothing else. Starting the vault writes nothing secret. Initialising it makes the recovery
key and the root token: the default single recovery key goes to a root-only file and the stricter
split (`--recovery-split`) is printed once, which is why that step carries `presents_once`.
Configuring it uses the root token that step left in the running shell and never on disk: it runs
this release's own `apply-release.sh` under root, mints the application's, the worker's and the
deploy token, and revokes the root token. The last step applies the release's vault changes with
the deploy token, which on a fresh install proves the token works and on an update is the whole
point. See `A_RELEASE_APPLIES_ITS_OWN_VAULT_CHANGES`.

**One script applies a release's vault changes, whoever runs it.** `render_apply` writes
`ops/openbao/apply-release.sh`, and the installer (under the root token), the update and the
rollback (under the deploy token), the automatic deploy on a hosting panel (`ops/deploy/
brain-deploy`, from the new image) and the switch an older install makes
(`ops/openbao/switch-to-auto-unseal.sh`) all run it. Four copies of the engine list were the
defect this replaces: the installer enabled engines a runbook then told three people to enable
by hand.

**Nothing secret reaches an argument list, a temporary file or a terminal it was not meant for.**
The root token reaches the vault through the docker client's environment with `-e BAO_TOKEN` and
no value; minted tokens go straight into the environment file or, for the deploy token, from the
vault's own answer into its root-only file; nothing uses a here-string, which bash before 5.1 writes
to a temporary file. See `NOTHING_KEPT_REACHES_AN_ARGUMENT_LIST_OR_A_FILE`.

Rejected: keeping the three-of-five unseal ceremony as the default. It is still offered, as the
recovery split, for a company that wants no single person able to make a root token; as the
default it was the ceremony that stopped a release from taking effect.

Rejected: `BAO_SKIP_DROP_ROOT` so the vault process can read a root-only key file. It runs the
whole vault as root to spare one `install` line; the entrypoint copies the key into a tmpfs the
vault's own user reads, and the vault still drops root (ops/openbao/compose.yml).

Rejected: the seal key in an environment variable (`env://`). `docker inspect` prints every
variable of a container, so the key would be one command away from anybody who may run docker.

Rejected: keeping the root token for a later step or a later run. It is the permanent,
unattributable bypass `vault_quorum` refuses to keep in an envelope; the deploy token is the
narrow, attributable thing a release needs.

Task ids: M42.6.2, M42.5.14, M31.3.2.1, M31.3.2.2, M31.3.2.3, M31.3.2.6, M38.4.1.3, M11.8.6
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Final

from brain.deployment.app_environment import (
    VAULT_CHOICE,
    VAULT_OVERLAY,
    VAULT_PROJECT,
    VAULT_SETTINGS,
    WORKER_FILE,
    WORKER_VAULT_CHOICE,
    worker_vault_overlays_for,
)
from brain.deployment.requirements import files_for
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
from brain.ops.connector_slots import REFUSE_KEY, REQUEST_KEY, SLOT_SCOPES, SlotScopes
from brain.ops.openbao import CONNECTOR_KEY_PREFIX, STATIC_PREFIXES
from brain.ops.vault_quorum import (
    RECOVERY_SPLIT,
    SINGLE_RECOVERY_KEY,
    SPLIT_FLAG,
    VAULT_CONTAINER,
    init_args,
)
from brain.ops.wiring import PROFILES

# ------------------------------------------------------------ written-down reasons

#: Why the installer runs the vault by default.
THE_VAULT_RUNS_WHEREVER_A_CREDENTIAL_IS_KEPT: Final = (
    "Every profile's application keeps credentials put in from a browser: the setup wizard's "
    "provider key, the mail relay's password, a webhook subscriber's signing secret, a connected "
    "source's key. The vault is the only place any of them is kept, and nothing falls back to a "
    "table, so an install with no vault refuses each of them in words. Running it by default on "
    "every profile is what lets the first run keep the key it asks for with no hand edit."
)

#: Why only a profile running neither the worker nor the object store may decline it.
A_PROFILE_WHOSE_OWN_SERVICES_READ_NO_STORED_KEY_MAY_DECLINE_IT: Final = (
    "Standard and full run the general worker, which signs every webhook delivery with a secret "
    "read from the vault and renews its own token there, and the object store, whose key pair the "
    "application reads from the vault at start. Declining the vault there is a stack whose file "
    "store never connects and whose deliveries all fail. Lite runs neither, so a lite install "
    "whose model needs no key it has to keep, a model on its own hardware or behind an endpoint "
    "that asks for none, may pass --no-vault. What it gives up is said: the wizard then refuses a "
    "hosted provider's key unless the environment file already carries it, and the console "
    "keeps no credential."
)

#: The owner's decision of 2026-09-29, and the trade-off he accepted with it.
THE_VAULT_OPENS_ITSELF_FROM_A_KEY_ONLY_ROOT_CAN_READ: Final = (
    "The vault's root key is encrypted with 32 random bytes kept in a file only root on the "
    "server can read, and the vault reads that file whenever it starts, so a restart or a reboot "
    "needs nobody. Anyone with root on the server can therefore open the vault; on one server "
    "that person can already read the running application's memory, where every key the vault "
    "hands out ends up. Decided by the owner on 2026-09-29, needs-rupash 114, and reversible: a "
    "company can move back to pieces held by people with bao operator rekey and a seal migration."
)

#: Where the seal key must be copied, and where it must never be.
THE_SEAL_KEY_IS_KEPT_APART_FROM_ANY_COPY_OF_THE_VAULT: Final = (
    "Without the seal key the vault's data can never be read again, by anybody, so it needs a "
    "copy off the server. With it, a copy of the vault's data opens for whoever holds both, so "
    "that copy must never sit beside a backup of the vault's volume. The product's own backups "
    "copy the database and never this directory; a company keeps the key in its password manager "
    "or its own key store, as ops/openbao/UNSEAL.md says."
)

#: What the recovery key is for, now that it does not open the vault.
THE_RECOVERY_KEY_IS_AN_EMERGENCY_SPARE: Final = (
    "A recovery key does not open the vault; the seal key does. What it does is generate a root "
    "token, which is needed only when the deploy token has lapsed or a release changes the deploy "
    "token's own policy. The default is one key, written to a root-only file for whoever installs "
    "to move into a password manager and delete; --recovery-split makes five pieces any three of "
    "which are needed, printed once for five people, for a company that wants no one person to "
    "hold it."
)

#: Why a release applies its own vault changes, and with what.
A_RELEASE_APPLIES_ITS_OWN_VAULT_CHANGES: Final = (
    "A release that changed a policy or added an engine used to wait until three people generated "
    "a root token. Now every release runs its own apply-release.sh during deploy, with a deploy "
    "token kept root-only beside the seal key: it enables any engine the release adds, loads every "
    "policy, defines the token role and the source slots, reads each back, and fails loudly if one "
    "did not take. It is idempotent, so a deploy that changed nothing changes nothing."
)

#: What the deploy token can and cannot do, said without flattering it.
A_DEPLOY_MAY_WIDEN_OTHERS_AND_NEVER_ITSELF: Final = (
    "A token that loads policies may widen what the application's and the worker's tokens reach, "
    "so it is as sensitive as the vault and lives where the seal key lives. It reads no secret, "
    "writes no secret value, mints no token and removes nothing, and its own policy and the "
    "default one are read-only to it, so it cannot widen itself. Every use is in the audit log "
    "under its own accessor, where a root token's would be indistinguishable from any "
    "administrator's."
)

#: Why the token auth method's ceiling is raised to a year, and why that touches nothing else.
A_DEPLOY_OUTLIVES_A_QUIET_QUARTER: Final = (
    "OpenBao caps a periodic token's lifetime at the token method's maximum, 768 hours by default, "
    "measured on 2.4.1: a token minted with an 8760 hour period came back with 768 hours to live. "
    "A company that updates quarterly would find its deploy token lapsed at every update. So the "
    "installer raises that maximum to a year, and every deploy renews the token. Nothing else is "
    "minted without its own ceiling: the application's and the worker's tokens carry a 768 hour "
    "period and a connector run's token its role's one hour, so the raise reaches the deploy token "
    "alone."
)

#: How a piece and the root token travel.
NOTHING_KEPT_REACHES_AN_ARGUMENT_LIST_OR_A_FILE: Final = (
    "A command's arguments are readable by every local user for as long as it runs, and bash "
    "before 5.1 writes a here-string to a temporary file. So the root token reaches the vault "
    "through the docker client's own environment passed by name, the application's and the "
    "worker's tokens go straight into the environment file the installer already writes "
    "credentials to, the deploy token goes from the vault's answer into its root-only file, and "
    "the recovery key is cut out of the vault's answer by sed into its root-only file."
)

#: Why the audit devices are declared in the vault's compose file and not enabled by this step.
THE_AUDIT_DEVICES_ARE_DECLARED_NOT_ENABLED: Final = (
    "OpenBao 2.4 refuses bao audit enable over the API, so the installer enables no audit device. "
    "Both are declared in ops/openbao/compose.yml's BAO_LOCAL_CONFIG and come up with the vault: "
    "a file device on the log volume with mode 0644, so the worker, another user reading that "
    "volume read-only, can ship it into the ledger, and a stdout device in the docker log. Every "
    "usable value in the log is an HMAC and raw logging stays off."
)

#: Why the installer creates the connector-run token role and defines every source's slot.
A_RUN_ROLE_AND_EMPTY_SLOTS_ARE_MADE_AT_INSTALL: Final = (
    "Both are configuration only a policy-writing token can make. The role is what the worker "
    "mints a run token against, fixing its one policy, its TTL ceiling and no renewal; the slots "
    "are each source's metadata with the scopes its key must have, and no version, so the vault "
    "says what a key may do before one is issued. apply-release.sh defines both, under the root "
    "token at install and under the deploy token at every release."
)

#: Why a half-finished vault is not finished automatically.
A_VAULT_AN_EARLIER_RUN_INITIALISED_IS_FINISHED_BY_HAND: Final = (
    "The root token existed only in the shell that initialised the vault. A later run finds the "
    "vault initialised and the tokens missing, and has no way to configure it: guessing would mean "
    "a root token kept somewhere, which is the thing refused. So it stops and names the section of "
    "ops/openbao/UNSEAL.md that finishes it with the recovery key and generate-root."
)

# --------------------------------------------------------------------- the figures

#: The service and port `ops/openbao/compose.yml` gives the vault, which is how both containers
#: reach it on the vault's network. A test reads both out of that file.
VAULT_SERVICE: Final = "vault"
VAULT_PORT: Final = 8200

#: The address written into the environment file, and never one on the host: nothing publishes one.
VAULT_ADDRESS: Final = f"http://{VAULT_SERVICE}:{VAULT_PORT}"

#: The address `bao` uses inside the vault's own container, which listens without TLS.
INSIDE_THE_CONTAINER: Final = f"http://127.0.0.1:{VAULT_PORT}"

#: The network the vault and the two containers that reach it share. The compose file declares
#: it external, so the installer creates it; a test holds this equal to the file's default.
VAULT_NETWORK_NAME: Final = "brain-vault"

#: The kv engines the product reads and writes, derived from the client's own prefixes so an engine
#: the client admits is an engine the installer enables on the same day.
ENGINES: Final[tuple[str, ...]] = tuple(prefix.rstrip("/") for prefix in STATIC_PREFIXES)

#: The period both tokens are minted with, as `credential-slots.md` documents it. A month, which is
#: also the vault's default maximum lifetime: a periodic token is exempt from that maximum for as
#: long as it is renewed inside its period, which `brain.ops.vault_renewal` does.
TOKEN_PERIOD: Final = "768h"  # noqa: S105  a duration, never a credential
TOKEN_PERIOD_SECONDS: Final = 768 * 3600

#: The policy each minted token carries, and the line of the environment file it is written to.
APPLICATION_TOKEN: Final = ("application", VAULT_SETTINGS[1])
WORKER_TOKEN: Final = ("worker", WORKER_VAULT_CHOICE)

#: The deploy token's policy, its period and the ceiling the token method is raised to so the
#: period holds. See `A_DEPLOY_OUTLIVES_A_QUIET_QUARTER`.
DEPLOY_POLICY: Final = "deploy"
DEPLOY_TOKEN_PERIOD: Final = "8760h"  # noqa: S105  a duration, never a credential
TOKEN_METHOD_MAX_TTL: Final = DEPLOY_TOKEN_PERIOD

#: Where the vault's three root-only files live on the server: the seal key, the deploy token and,
#: until somebody moves it, the recovery key. Outside the install's own directory on purpose: the
#: release is unpacked over that directory and a backup of it would carry the key with the data.
VAULT_STATE_DIR: Final = "/etc/brain-vault"
SEAL_KEY_FILE: Final = f"{VAULT_STATE_DIR}/seal.key"
DEPLOY_TOKEN_FILE: Final = f"{VAULT_STATE_DIR}/deploy.token"
RECOVERY_KEY_FILE: Final = f"{VAULT_STATE_DIR}/recovery.key"

#: The seal key's length. OpenBao's static seal takes a raw 256-bit AES key, measured on 2.4.1.
SEAL_KEY_BYTES: Final = 32

#: The script every path runs to apply a release's vault changes, as the release lays it out.
APPLY_SCRIPT: Final = "ops/openbao/apply-release.sh"

#: How apply-release.sh says it found no deploy token, which is an older install's state rather
#: than a failure: that install moves with the switch, and until then its updates carry on.
NO_DEPLOY_TOKEN_EXIT: Final = 3

#: The base file declaring the object store, by which a profile is known to run one.
OBJECT_STORE_FILE: Final = "docker-compose.objectstore.yml"

#: The flag that declines the vault, and the shell variable it sets.
DECLINE_FLAG: Final = "--no-vault"

#: The shell variable the recovery choice is carried in, set to `split` by `SPLIT_FLAG`.
RECOVERY_VARIABLE: Final = "BRAIN_VAULT_RECOVERY"

#: The shell variable carrying the worker's overlay flags for the profile being installed.
WORKER_FILES_VARIABLE: Final = "BRAIN_WORKER_VAULT_FILES"


def may_decline(profile: str) -> bool:
    """Whether this profile may be installed without the vault. See the named constant."""
    files = files_for(profile)
    return WORKER_FILE not in files and OBJECT_STORE_FILE not in files


#: The profiles `--no-vault` is accepted for, computed from their files.
DECLINABLE_PROFILES: Final[tuple[str, ...]] = tuple(one for one in PROFILES if may_decline(one))


def worker_files_argument(profile: str, *, home: str) -> str:
    """The worker overlay's `-f` flag for this profile, or empty where no worker runs."""
    return " ".join(f"-f {home}/{name}" for name in worker_vault_overlays_for(files_for(profile)))


# ------------------------------------------------------------------ the shell, by step

_BAO_ADDR: Final = f"-e BAO_ADDR={INSIDE_THE_CONTAINER}"
_DECLINED: Final = 'test "${BRAIN_VAULT:-yes}" = "no"'


def _vault_project(home: str) -> str:
    return f'"{home}/{VAULT_PROJECT}"'


def seal_key_done() -> str:
    """True when the vault was declined, the key is there, or a vault is already initialised.

    The third clause is the one that matters on a second run: a key made now for a vault that was
    initialised with another could never open it, and making one would only suggest it could.
    """
    return (
        f"{_DECLINED} || test -s {SEAL_KEY_FILE} || "
        f"docker exec {_BAO_ADDR} {VAULT_CONTAINER} bao operator init -status >/dev/null 2>&1"
    )


def seal_key_run() -> str:
    """Write 32 random bytes to the root-only seal key file, once, and never over an existing one.

    Written beside itself and moved into place, so a run that stops half way leaves no short key
    the vault would then refuse to start with. Nothing is printed: the key is not for reading.
    """
    return "\n".join(
        (
            "umask 077",
            f"mkdir -p {VAULT_STATE_DIR}",
            f"chmod 0700 {VAULT_STATE_DIR}",
            f"head -c {SEAL_KEY_BYTES} /dev/urandom > {SEAL_KEY_FILE}.new",
            f'test "$(wc -c < {SEAL_KEY_FILE}.new)" -eq {SEAL_KEY_BYTES} || fail "the seal key '
            f'came out short; nothing has been started. Run this again"',
            f"chmod 0400 {SEAL_KEY_FILE}.new",
            f"mv {SEAL_KEY_FILE}.new {SEAL_KEY_FILE}",
            f"say \"The vault's seal key is in {SEAL_KEY_FILE}, readable only by root. Copy it "
            "somewhere off this server that is not beside a backup of the vault: without it the "
            'vault can never be opened again. ops/openbao/UNSEAL.md says where."',
        )
    )


def start_run(home: str) -> str:
    """Create the vault's network, start its own compose project and wait until it answers."""
    return "\n".join(
        (
            f"docker network inspect {VAULT_NETWORK_NAME} >/dev/null 2>&1 || "
            f"docker network create {VAULT_NETWORK_NAME} >/dev/null",
            f"docker compose -f {_vault_project(home)} up -d",
            "BRAIN_VAULT_ANSWER=1",
            "for _ in $(seq 1 30); do",
            "  BRAIN_VAULT_ANSWER=0",
            f"  docker exec {_BAO_ADDR} {VAULT_CONTAINER} bao operator init -status "
            '>/dev/null 2>&1 || BRAIN_VAULT_ANSWER="$?"',
            '  test "$BRAIN_VAULT_ANSWER" -ne 1 && break',
            "  sleep 2",
            "done",
            'test "$BRAIN_VAULT_ANSWER" -ne 1 || fail "the secrets vault started and never '
            f'answered. Read docker logs {VAULT_CONTAINER}, then run this again"',
        )
    )


def start_done(home: str) -> str:
    """True when the vault was declined, or its container is already running."""
    return (
        f"{_DECLINED} || docker compose -f {_vault_project(home)} ps "
        f"--status running --services | grep -qx {VAULT_SERVICE}"
    )


def initialise_done() -> str:
    """True when the vault was declined, or it has been initialised by any run, ever."""
    return (
        f"{_DECLINED} || "
        f"docker exec {_BAO_ADDR} {VAULT_CONTAINER} bao operator init -status >/dev/null 2>&1"
    )


def _init_line(args: Sequence[str]) -> str:
    return (
        f'BRAIN_VAULT_INIT="$(docker exec {_BAO_ADDR} {VAULT_CONTAINER} bao operator init '
        f'{" ".join(args)})" || fail "the secrets vault refused to initialise, so no key was made '
        f'and nothing is lost. Read docker logs {VAULT_CONTAINER}, then run this again"'
    )


def initialise_run() -> str:
    """Initialise the vault with the chosen recovery split, and keep or show the recovery key."""
    backslash = chr(92)
    number = f"{backslash}([0-9]*{backslash})"
    shares, threshold = RECOVERY_SPLIT.shares, RECOVERY_SPLIT.threshold
    return "\n".join(
        (
            f'if test "${{{RECOVERY_VARIABLE}:-single}}" = "split"; then',
            f"  {_init_line(init_args(RECOVERY_SPLIT))}",
            '  say ""',
            f"  say \"The secrets vault's recovery key, in {shares} pieces. Any {threshold} of "
            'them make a root token in an emergency; none of them is needed to open the vault."',
            '  say "This is the only time they are shown. Nothing on this server keeps them, and '
            'nothing can show them again."',
            f'  if test "$(printf "%s{backslash}n" "$BRAIN_VAULT_INIT" '
            f'| grep -c "^Recovery Key ")" -eq {shares}; then',
            f'    printf "%s{backslash}n" "$BRAIN_VAULT_INIT" | sed -n "s/^Recovery Key {number}: '
            f'/  piece {backslash}1 of {shares}: /p"',
            "  else",
            '    say "The vault answered in a shape this installer cannot read, so its whole '
            "answer is below: the pieces and the root token are in it. Keep the pieces as the next "
            'lines say, and finish by hand with ops/openbao/UNSEAL.md."',
            f'    printf "%s{backslash}n" "$BRAIN_VAULT_INIT"',
            '    fail "the vault is initialised and this installer could not read its answer. '
            'Finish by hand with ops/openbao/UNSEAL.md, under Finishing what the installer began"',
            "  fi",
            '  say ""',
            '  say "Give each piece to a different person now, each by a different route, and keep '
            'none of them on this server: ops/openbao/UNSEAL.md, under In an emergency."',
            '  say "If this terminal is being recorded, or this run is going through tee or into a '
            'log, that record now holds the pieces. Destroy it."',
            "  if test -t 0; then",
            '    printf "%s " "Press Enter once every piece is somewhere other than this server:" '
            ">&2",
            "    read -r BRAIN_ANSWER",
            "  fi",
            "else",
            f"  {_init_line(init_args(SINGLE_RECOVERY_KEY))}",
            "  umask 077",
            f"  mkdir -p {VAULT_STATE_DIR}",
            f'  printf "%s{backslash}n" "$BRAIN_VAULT_INIT" | sed -n "s/^Recovery Key 1: //p" '
            f"> {RECOVERY_KEY_FILE}.new",
            f'  test -s {RECOVERY_KEY_FILE}.new || fail "the vault is initialised and this '
            "installer could not read its recovery key out of the answer. Finish by hand with "
            'ops/openbao/UNSEAL.md, under Finishing what the installer began"',
            f"  chmod 0400 {RECOVERY_KEY_FILE}.new",
            f"  mv {RECOVERY_KEY_FILE}.new {RECOVERY_KEY_FILE}",
            f"  say \"The vault's recovery key is in {RECOVERY_KEY_FILE}, readable only by root. "
            "It does not open the vault, which opens itself; it makes a root token in an "
            'emergency. Move it into your password manager, then delete the file."',
            "fi",
        )
    )


def configure_done(home: str, env_file: str) -> str:
    """True when the vault was declined, or every token this profile needs is in the file."""
    path = f'"{home}/{env_file}"'
    return (
        f"{_DECLINED} || {{ "
        f'grep -q "^{VAULT_CHOICE}=." {path} && grep -q "^{APPLICATION_TOKEN[1]}=." {path} && '
        f'{{ test -z "${{{WORKER_FILES_VARIABLE}:-}}" || '
        f'grep -q "^{WORKER_TOKEN[1]}=." {path}; }}; }}'
    )


def configure_run(home: str, env_file: str) -> str:
    """Wait for the vault to open itself, configure it as root, mint three tokens, revoke root."""
    backslash = chr(92)
    newline = f"{backslash}n"
    path = f'"{home}/{env_file}"'
    exec_ = f"docker exec {_BAO_ADDR} {VAULT_CONTAINER} bao"
    minted = f"-orphan -period={TOKEN_PERIOD} -field=token"
    return "\n".join(
        (
            'test -n "${BRAIN_VAULT_INIT:-}" || fail "the secrets vault on this server was '
            "initialised by an earlier run that stopped before this step, and the root token this "
            "step needs existed only in that run. Finish it by hand with ops/openbao/UNSEAL.md, "
            'under Finishing what the installer began"',
            f'vault_root() {{ printf "%s{newline}" "$BRAIN_VAULT_INIT" | sed -n '
            '"s/^Initial Root Token: //p"; }',
            'as_vault_root() { BAO_TOKEN="$(vault_root)" docker exec -e BAO_TOKEN '
            f'{_BAO_ADDR} {VAULT_CONTAINER} bao "$@" </dev/null; }}',
            "BRAIN_VAULT_OPEN=no",
            "for _ in $(seq 1 30); do",
            f"  {exec_} status >/dev/null 2>&1 && {{ BRAIN_VAULT_OPEN=yes; break; }}",
            "  sleep 2",
            "done",
            f'test "$BRAIN_VAULT_OPEN" = "yes" || fail "the vault did not open itself from its '
            f"seal key. Read docker logs {VAULT_CONTAINER}; nothing has been written to the "
            'environment file"',
            f'BAO_TOKEN="$(vault_root)" sh "{home}/{APPLY_SCRIPT}" || fail "this release\'s vault '
            "policies, engines and roles did not take under the root token; the lines above say "
            "which. Finish by hand with ops/openbao/UNSEAL.md, under Finishing what the installer "
            'began"',
            f"as_vault_root auth tune -max-lease-ttl={TOKEN_METHOD_MAX_TTL} token/ >/dev/null || "
            "fail \"the vault would not raise the token method's ceiling for the deploy token. "
            'Finish by hand with ops/openbao/UNSEAL.md, under Finishing what the installer began"',
            f'BRAIN_VAULT_APP_TOKEN="$(as_vault_root token create -policy={APPLICATION_TOKEN[0]} '
            f'{minted})" || fail "the vault would not mint the application\'s token. Finish by '
            'hand with ops/openbao/UNSEAL.md, under Finishing what the installer began"',
            'BRAIN_VAULT_WORKER_TOKEN=""',
            f'if test -n "${{{WORKER_FILES_VARIABLE}:-}}"; then',
            f'  BRAIN_VAULT_WORKER_TOKEN="$(as_vault_root token create -policy={WORKER_TOKEN[0]} '
            f'{minted})" || fail "the vault would not mint the worker\'s token. Finish by hand '
            'with ops/openbao/UNSEAL.md, under Finishing what the installer began"',
            "fi",
            f'BAO_TOKEN="$BRAIN_VAULT_APP_TOKEN" docker exec -e BAO_TOKEN {_BAO_ADDR} '
            f"{VAULT_CONTAINER} bao token lookup >/dev/null </dev/null || "
            "fail \"the application's new token was refused by the vault that minted it. Nothing "
            'has been written; finish by hand with ops/openbao/UNSEAL.md"',
            "umask 077",
            f"mkdir -p {VAULT_STATE_DIR}",
            f"as_vault_root token create -policy={DEPLOY_POLICY} -no-default-policy -orphan "
            f"-period={DEPLOY_TOKEN_PERIOD} -field=token > {DEPLOY_TOKEN_FILE}.new || "
            'fail "the vault would not mint the deploy token. Finish by hand with '
            'ops/openbao/UNSEAL.md, under Finishing what the installer began"',
            f"chmod 0400 {DEPLOY_TOKEN_FILE}.new",
            f"mv {DEPLOY_TOKEN_FILE}.new {DEPLOY_TOKEN_FILE}",
            "{",
            f'  printf "{VAULT_CHOICE}=%s{newline}" "{VAULT_ADDRESS}"',
            f'  printf "{APPLICATION_TOKEN[1]}=%s{newline}" "$BRAIN_VAULT_APP_TOKEN"',
            f'  if test -n "${{{WORKER_FILES_VARIABLE}:-}}"; then',
            f'    printf "{WORKER_TOKEN[1]}=%s{newline}" "$BRAIN_VAULT_WORKER_TOKEN"',
            "  fi",
            f"}} >> {path}",
            'as_vault_root token revoke -self >/dev/null || fail "the tokens are written and the '
            "root token could not be revoked. Revoke it by hand now: ops/openbao/UNSEAL.md, under "
            'Finishing what the installer began"',
            "unset BRAIN_VAULT_INIT BRAIN_VAULT_APP_TOKEN BRAIN_VAULT_WORKER_TOKEN",
        )
    )


def apply_done(home: str, env_file: str) -> str:
    """True when this install runs no vault, or everything this release declares is in force."""
    return (
        f'! grep -q "^{VAULT_CHOICE}=." "{home}/{env_file}" 2>/dev/null || '
        f'sh "{home}/{APPLY_SCRIPT}" --check >/dev/null 2>&1'
    )


def apply_run(home: str) -> str:
    """Apply this release's vault changes with the deploy token, loudly if they do not take.

    An install with no deploy token is an install made before 2026-09-29. Its update carries on and
    says, once, what moves it: its vault is still opened by people, so the release's policies wait
    for them exactly as they always did, and stopping every update until then would strand it.
    """
    return "\n".join(
        (
            "BRAIN_VAULT_APPLIED=0",
            f'sh "{home}/{APPLY_SCRIPT}" || BRAIN_VAULT_APPLIED="$?"',
            f'if test "$BRAIN_VAULT_APPLIED" -eq {NO_DEPLOY_TOKEN_EXIT}; then',
            "  say \"This install's vault has no deploy token, so this release's vault policies "
            "are not applied. It was made before the vault opened itself: "
            'ops/openbao/UNSEAL.md, under Moving an older install, moves it with one command."',
            'elif test "$BRAIN_VAULT_APPLIED" -ne 0; then',
            "  fail \"this release's vault policies, engines or roles did not take; the lines "
            "above say which. ops/openbao/UNSEAL.md, under When a release's vault changes do not "
            'take"',
            "fi",
        )
    )


def compose_run(home: str, env_file: str) -> str:
    """Add the overlays to the file list when the environment file chose them. Writes nothing."""
    return "\n".join(vault_choice_lines(home, env_file))


def vault_choice_lines(home: str, env_file: str) -> tuple[str, ...]:
    """The lines composing the application's and the worker's overlays in, each on its own line.

    The same lines in the installer, the update and the rollback, so the three compose a vault
    in exactly one way. Each overlay is chosen by the line in the environment file it requires, a
    value after the `=`, for `brain.deployment.release._tunnel_choice`'s reason. The worker's is
    composed only where `WORKER_FILES_VARIABLE` names a file, which is a profile running a worker.
    """
    path = f'"{home}/{env_file}"'
    return (
        f'if grep -q "^{VAULT_CHOICE}=." {path} 2>/dev/null; then '
        f'BRAIN_COMPOSE_FILES="$BRAIN_COMPOSE_FILES -f {home}/{VAULT_OVERLAY}"; '
        'say "The environment file names a secrets vault, so the vault overlay is composed in."; '
        "fi",
        f'if test -n "${{{WORKER_FILES_VARIABLE}:-}}" && '
        f'grep -q "^{WORKER_VAULT_CHOICE}=." {path} 2>/dev/null; then '
        f'BRAIN_COMPOSE_FILES="$BRAIN_COMPOSE_FILES ${WORKER_FILES_VARIABLE}"; '
        "say \"The environment file holds the worker's vault token, so its overlay is composed "
        'in."; fi',
    )


def decline_lines(profiles: tuple[str, ...] = DECLINABLE_PROFILES) -> tuple[str, ...]:
    """The install script's refusal of `--no-vault` on a profile that may not decline it."""
    arms = "|".join(profiles)
    return (
        'if test "$BRAIN_VAULT" = "no"; then',
        '  case "$BRAIN_PROFILE" in',
        f'    {arms}) say "{DECLINE_FLAG}: this install runs no secrets vault, so it keeps no '
        'provider key, relay password, signing secret or source key from the browser." ;;',
        f'    *) fail "{DECLINE_FLAG} is refused for the $BRAIN_PROFILE profile: its worker signs '
        "every webhook delivery with a secret from the vault and its object store's key is read "
        f'from there, so without one neither works. It is accepted for: {" ".join(profiles)}" ;;',
        "  esac",
        "fi",
    )


# ------------------------------------------------------------ apply-release.sh

#: Characters a slot's scopes may not contain, because the script carries them single-quoted on a
#: command line and compares them with what the vault prints back.
_UNSAFE_IN_A_SLOT: Final = frozenset("'\"\\`$<>&")


def _slot_text(slot: SlotScopes) -> tuple[str, str]:
    """A slot's two metadata values, refused when the script could not carry them intact."""
    request, refuse = "; ".join(slot.request), "; ".join(slot.refuse)
    for text in (request, refuse):
        if _UNSAFE_IN_A_SLOT & set(text):
            msg = (
                f"{slot.connector}'s scopes contain a character apply-release.sh cannot carry "
                f"single-quoted and compare with the vault's own printing: {text!r}"
            )
            raise ValueError(msg)
    return request, refuse


def slot_lines(caller: str) -> tuple[str, ...]:
    """Every source's slot, scopes and no key: read, written only where it differs, read again.

    Compared as the vault prints custom metadata, `map[not_requested:... scopes:...]`, keys sorted,
    which is Go's own printing of a map and measured on OpenBao 2.4.1. Written only on a difference,
    so a deploy that changed nothing writes nothing and adds nothing to the audit log.
    """
    mount = CONNECTOR_KEY_PREFIX.rstrip("/")
    lines = [
        f'slot_ok() {{ test "$({caller} read -field=custom_metadata "{mount}/metadata/$1" '
        '2>/dev/null)" = "$2"; }',
    ]
    for name in sorted(SLOT_SCOPES):
        request, refuse = _slot_text(SLOT_SCOPES[name])
        printed = f"'map[{REFUSE_KEY}:{refuse} {REQUEST_KEY}:{request}]'"
        lines.extend(
            (
                f"if ! slot_ok {name} {printed}; then",
                '  if test "$CHECK_ONLY" = no; then',
                f"    {caller} kv metadata put -mount={mount} "
                f"-custom-metadata='{REQUEST_KEY}={request}' "
                f"-custom-metadata='{REFUSE_KEY}={refuse}' {name} >/dev/null || "
                f'fail "the vault would not define the credential slot for {name}"',
                "  fi",
                f'  slot_ok {name} {printed} || missing "the credential slot for {name}"',
                "fi",
            )
        )
    return tuple(lines)


#: Every token role the release defines, as (role, the one policy it gives, its TTL ceiling). The
#: connector run's, one channel send's, one rotated refresh token's write and one read of a person's
#: own refresh token: see
#: `brain.ops.connector_lease` and `brain.ops.channel_lease`.
TOKEN_ROLES: Final[tuple[tuple[str, str, int], ...]] = (
    (RUN_TOKEN_ROLE, RUN_POLICY, RUN_ROLE_MAX_TTL_SECONDS),
    (SEND_TOKEN_ROLE, SEND_POLICY, SEND_ROLE_MAX_TTL_SECONDS),
    (ROTATE_TOKEN_ROLE, ROTATE_POLICY, ROTATE_ROLE_MAX_TTL_SECONDS),
    (PERSON_TOKEN_ROLE, PERSON_POLICY, PERSON_ROLE_MAX_TTL_SECONDS),
)


def role_lines(caller: str) -> tuple[str, ...]:
    """Every token role: its five settings read, written only where one differs."""
    lines: list[str] = []
    for name, policy, max_ttl in TOKEN_ROLES:
        role = f"auth/token/roles/{name}"
        wanted = (
            ("allowed_policies", f"[{policy}]"),
            ("orphan", "false"),
            ("renewable", "false"),
            ("token_no_default_policy", "true"),
            ("token_explicit_max_ttl", str(max_ttl)),
        )
        checks = " && ".join(
            f'test "$({caller} read -field={field} {role} 2>/dev/null)" = "{value}"'
            for field, value in wanted
        )
        check = f"role_ok_{name.replace('-', '_')}"
        lines.extend(
            (
                f"{check}() {{ {checks}; }}",
                f"if ! {check}; then",
                '  if test "$CHECK_ONLY" = no; then',
                f"    {caller} write {role} allowed_policies={policy} "
                "orphan=false renewable=false token_no_default_policy=true "
                f"token_explicit_max_ttl={max_ttl} >/dev/null || "
                f'fail "the vault would not define the {name} token role"',
                "  fi",
                f'  {check} || missing "the {name} token role"',
                "fi",
            )
        )
    return tuple(lines)


def render_apply() -> str:
    """`ops/openbao/apply-release.sh`, which every path that applies a release's vault changes runs.

    POSIX `sh`, because it runs on a server from an update script, a deploy hook and the installer,
    and the least of those is dash. It prints counts and names and never a value: the only secret
    it touches is the token it runs as, which travels by name into `docker exec`.
    """
    backslash = chr(92)
    caller = "bao_"
    lines = [
        "#!/bin/sh",
        "# Generated by brain.deployment.vault_setup.render_apply. Do not edit: edit the module "
        "and",
        "# regenerate with `uv run python -m brain.deployment.vault_setup > ops/openbao/"
        "apply-release.sh`,",
        "# or the script and the tested module disagree.",
        "#",
        "# Applies this release's vault engines, policies, token role and credential slots to the",
        "# running vault, reads each back, and fails loudly if one did not take. Idempotent: a",
        "# release that changed nothing changes nothing. Run by the installer (as root), by the",
        "# update and the rollback, by the automatic deploy (ops/deploy/brain-deploy) and by the",
        "# switch an older install makes. See brain.deployment.vault_setup.",
        "#",
        "# Usage: sh ops/openbao/apply-release.sh [--check]",
        "#   --check  change nothing; exit 0 only when everything is already in force",
        "# The token is BAO_TOKEN when set, otherwise the deploy token file. Exit 0: in force.",
        f"# Exit {NO_DEPLOY_TOKEN_EXIT}: no deploy token on this server (an install that has "
        "not moved yet).",
        "# Any other exit: something did not take, and the lines above it say what.",
        "",
        "set -eu",
        "",
        'HERE="$(cd "$(dirname "$0")" && pwd)"',
        f'CONTAINER="${{BRAIN_VAULT_CONTAINER:-{VAULT_CONTAINER}}}"',
        f'TOKEN_FILE="${{BRAIN_VAULT_DEPLOY_TOKEN_FILE:-{DEPLOY_TOKEN_FILE}}}"',
        "CHECK_ONLY=no",
        'test "${1:-}" = "--check" && CHECK_ONLY=yes',
        "NOT_IN_FORCE=0",
        "",
        'say() { printf "vault: %s' + backslash + 'n" "$1"; }',
        'fail() { printf "vault: %s' + backslash + 'n" "$1" >&2; exit 1; }',
        'missing() { printf "vault: not in force: %s' + backslash + 'n" "$1" >&2; '
        "NOT_IN_FORCE=$((NOT_IN_FORCE + 1)); }",
        "",
        'if test -z "${BAO_TOKEN:-}"; then',
        '  if ! test -r "$TOKEN_FILE"; then',
        '    printf "vault: %s' + backslash + 'n" "there is no deploy token at $TOKEN_FILE, so '
        "this release's vault changes were not applied. An install made before the vault opened "
        'itself moves with ops/openbao/switch-to-auto-unseal.sh" >&2',
        f"    exit {NO_DEPLOY_TOKEN_EXIT}",
        "  fi",
        '  BAO_TOKEN="$(cat "$TOKEN_FILE")"',
        "fi",
        "export BAO_TOKEN",
        f'{caller}() {{ docker exec -e BAO_TOKEN {_BAO_ADDR} "$CONTAINER" bao "$@" </dev/null; }}',
        f'{caller}in() {{ docker exec -i -e BAO_TOKEN {_BAO_ADDR} "$CONTAINER" bao "$@"; }}',
        "",
        f'docker exec {_BAO_ADDR} "$CONTAINER" bao status >/dev/null 2>&1 || fail "$CONTAINER is '
        "not running, or is sealed. It opens itself from its seal key; if it stays sealed, "
        'read docker logs $CONTAINER and ops/openbao/UNSEAL.md"',
        f'{caller} token lookup >/dev/null 2>&1 || fail "the vault refused the token this ran '
        "with. If it is the deploy token it has lapsed or been revoked: ops/openbao/UNSEAL.md, "
        'under In an emergency, makes a new one"',
        "",
        "# The engines, enabled where missing and never removed.",
        f'ENGINES_NOW="$({caller} secrets list)" || fail "the vault would not list its engines"',
        f"for engine in {' '.join(ENGINES)}; do",
        '  case "$ENGINES_NOW" in',
        '    *"$engine/ "*) ;;',
        '    *) if test "$CHECK_ONLY" = yes; then missing "the $engine engine"; '
        f'else {caller} secrets enable -path="$engine" kv-v2 >/dev/null || '
        'fail "the vault would not enable the $engine engine"; fi ;;',
        "  esac",
        "done",
        f'ENGINES_NOW="$({caller} secrets list)" || fail "the vault would not list its engines"',
        f"for engine in {' '.join(ENGINES)}; do",
        '  case "$ENGINES_NOW" in *"$engine/ "*) ;; *) test "$CHECK_ONLY" = yes || '
        'missing "the $engine engine" ;; esac',
        "done",
        "",
        "# Every policy file, written where the vault holds different text, then read back. The",
        "# deploy token's own policy is read-only to it, so a change there says what it needs.",
        "POLICIES=0",
        'for file in "$HERE"/policies/*.hcl; do',
        '  name="$(basename "$file" .hcl)"',
        f'  want="$(tr -d \'{backslash}015\' < "$file")"',
        f'  have="$({caller} read -field=policy "sys/policies/acl/$name" 2>/dev/null || true)"',
        '  if test "$have" != "$want" && test "$CHECK_ONLY" = no; then',
        f'    printf "%s{backslash}n" "$want" '
        f'| {caller}in policy write "$name" - >/dev/null 2>&1 || {{',
        f'      test "$name" = "{DEPLOY_POLICY}" && fail "this release changes the deploy '
        "token's own policy, which the deploy token may not load itself. Load it with a root "
        'token: ops/openbao/UNSEAL.md, under In an emergency"',
        '      fail "the vault would not load the $name policy"',
        "    }",
        f'    have="$({caller} read -field=policy "sys/policies/acl/$name" 2>/dev/null || true)"',
        "  fi",
        '  test "$have" = "$want" || missing "the $name policy"',
        "  POLICIES=$((POLICIES + 1))",
        "done",
        "",
        "# The token roles a connector run's token and one send's token are minted against.",
        *role_lines(caller),
        "",
        "# Every connected source's slot: its scopes, and no key.",
        *slot_lines(caller),
        "",
        'if test "$NOT_IN_FORCE" -ne 0; then',
        '  test "$CHECK_ONLY" = yes && fail "$NOT_IN_FORCE of this release\'s vault changes are '
        'not in force"',
        '  fail "$NOT_IN_FORCE of this release\'s vault changes did not take after being written"',
        "fi",
        'if test "$CHECK_ONLY" = no; then',
        f"  {caller} token renew >/dev/null 2>&1 || true",
        "fi",
        f'say "in force: {len(ENGINES)} engines, $POLICIES policies, '
        f"{len(TOKEN_ROLES)} token roles ({', '.join(name for name, _, _ in TOKEN_ROLES)}) "
        f'and {len(SLOT_SCOPES)} credential slots"',
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print `apply-release.sh`: how the committed file under `ops/openbao/` is produced."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(f"usage: python -m {__name__}", file=sys.stderr)
        return 2
    print(render_apply(), end="")
    return 0


#: The flag `ops/install/install.sh` takes for the stricter recovery choice, re-exported so the
#: install script's flag table reads it from the module that carries the choice into the shell.
RECOVERY_SPLIT_FLAG: Final = SPLIT_FLAG


if __name__ == "__main__":  # pragma: no cover - the command that writes the committed script
    raise SystemExit(main())
