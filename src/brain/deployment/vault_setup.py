"""The installer runs the secrets vault, opens it once, and hands the install its tokens.

A provider key was kept only where a vault was attached, and the installer attached none. So on
a fresh hosted install the setup wizard's provider screen refused with `no_vault` unless somebody
had hand-edited the key, or `BRAIN_VAULT_ADDRESS` and `BRAIN_VAULT_TOKEN`, into the server's
environment file, which is the staging finding CLAUDE.md records as open. Every step of fixing
it by hand was already written, in `ops/openbao/UNSEAL.md` and `ops/openbao/credential-slots.md`:
start the vault, initialise it, open it, enable the engines, load the policies, mint two tokens,
write them into the environment file, compose the overlay in. This module is those steps as the
installer's, so the wizard's key has somewhere to go on the first run. See
`THE_VAULT_RUNS_WHEREVER_A_CREDENTIAL_IS_KEPT`.

**Four steps, and the split is where the secrets are.** Starting the vault writes nothing secret.
Initialising it makes the unseal pieces and the root token, and shows the pieces, which is why it
is its own small step with `presents_once`: `brain.deployment.installer.Step` keeps that exemption
on the smallest step there is. Opening it uses the pieces and the root token that step left in the
running shell and never on disk, and ends by revoking the root token. Composing the overlays in
runs on every run, because it reads the environment file rather than remembering, so a second run
of the installer composes the vault exactly as the first did.

**What an operator keeps is five pieces with five people, and nothing else.** The split is
`brain.ops.vault_quorum.DEFAULT_POLICY`'s, five pieces any three of which open the vault, and the
installer prints them once, numbered, at the terminal it runs in. The root token is revoked by the
step that made it. The two tokens go into the environment file the installer already owns, beside
the database password, under the mode it already writes. See
`THE_UNSEAL_PIECES_ARE_SHOWN_ONCE_AND_KEPT_BY_PEOPLE` and `THE_ROOT_CREDENTIAL_LIVES_FOR_ONE_STEP`.

**The installer names no holder, and does not ask the quorum policy whether holders are named.**
`vault_quorum.main` refuses while its five slots read `UNASSIGNED`, and that refusal cannot be the
installer's: the people who hold a company's pieces are that company's decision, and a name typed
into this repository is a company's detail in the product. So the installer takes the two numbers
and prints the pieces as piece 1 to 5, and the person at the terminal hands them out. See
`THE_INSTALLER_TAKES_THE_SPLIT_AND_NAMES_NOBODY`.

**Nothing secret reaches an argument list, a temporary file or the environment file's neighbours.**
A piece reaches the vault through `printf`, which is a shell builtin, piped into `docker exec -i`
reading `key=-`; the root token reaches it through the docker client's environment with `-e
BAO_TOKEN` and no value; and nothing uses a here-string, which bash before 5.1 writes to a
temporary file. See `NO_PIECE_REACHES_AN_ARGUMENT_LIST_OR_A_FILE`.

**A vault an earlier run initialised and did not finish is finished by hand, and the step says
so.** The root token existed only in the shell that initialised the vault, so a run that stops
between initialising and minting leaves a vault nobody can configure without three pieces and
`bao operator generate-root`. The opening step refuses with that sentence rather than guessing,
and `UNSEAL.md` has the steps. See `A_VAULT_AN_EARLIER_RUN_INITIALISED_IS_FINISHED_BY_HAND`.

Rejected: writing the pieces to a file under `umask 077` for the person to collect. A file on the
server is the one place `UNSEAL.md` says the pieces must never be, because a vault whose pieces
sit beside it opens for anybody who gets the server, which is automatic unsealing with extra steps.

Rejected: keeping the root token for a later step or a later run. See the named constant; it is
the permanent, unattributable bypass `vault_quorum` already refuses to keep in an envelope.

Rejected: auto-unsealing so a restarted vault opens itself. `UNSEAL.md` argues it: a key the
machine can read opens the vault for whoever has the machine.

Task ids: M42.6.2, M42.5.14, M31.3.2.1
"""

from __future__ import annotations

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
from brain.ops.openbao import STATIC_PREFIXES
from brain.ops.vault_quorum import DEFAULT_POLICY, VAULT_CONTAINER, init_args
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

#: What the person at the terminal keeps, and what they must not.
THE_UNSEAL_PIECES_ARE_SHOWN_ONCE_AND_KEPT_BY_PEOPLE: Final = (
    "The vault prints its unseal pieces once, at initialisation, and nothing can print them again. "
    "The installer shows them once at the terminal and writes them nowhere: not the environment "
    "file, not a log, not a temporary file. The operator keeps exactly this: each piece with a "
    "different person, off the server, three of whom open the vault after every restart of its "
    "container. A terminal that was recorded, or a run piped through tee, holds the pieces, and "
    "that record has to be destroyed."
)

#: Why the root token is revoked inside the step that uses it.
THE_ROOT_CREDENTIAL_LIVES_FOR_ONE_STEP: Final = (
    "The root token bypasses every policy and the audit log cannot tell its use from an "
    "administrator's. The installer needs it for one step, to enable the engines and the audit "
    "devices, load the policies and mint two tokens, and revokes it at the end of that step. If "
    "one is needed again, three holders regenerate it with bao operator generate-root."
)

#: Why the installer does not ask the quorum policy for names.
THE_INSTALLER_TAKES_THE_SPLIT_AND_NAMES_NOBODY: Final = (
    "The shares and the threshold are the product's decision and are read from "
    "brain.ops.vault_quorum. Who holds each piece is the installing company's, and a name in this "
    "repository would be a company's detail in the product. So the pieces are printed by number "
    "and the person at the terminal hands them out; vault_quorum.assert_configured is not asked."
)

#: How a piece and the root token travel.
NO_PIECE_REACHES_AN_ARGUMENT_LIST_OR_A_FILE: Final = (
    "A command's arguments are readable by every local user for as long as it runs, and bash "
    "before 5.1 writes a here-string to a temporary file. So a piece is written by printf, a shell "
    "builtin, into a pipe that docker exec -i reads as key=-, the root token reaches the vault "
    "through the docker client's own environment passed by name, and the tokens go straight into "
    "the environment file the installer already writes credentials to."
)

#: Why a half-finished vault is not finished automatically.
A_VAULT_AN_EARLIER_RUN_INITIALISED_IS_FINISHED_BY_HAND: Final = (
    "The root token existed only in the shell that initialised the vault. A later run finds the "
    "vault initialised and the tokens missing, and has no way to configure it: guessing would mean "
    "a root token kept somewhere, which is the thing refused. So it stops and names the section of "
    "ops/openbao/UNSEAL.md that finishes it with three pieces and generate-root."
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

#: The base file declaring the object store, by which a profile is known to run one.
OBJECT_STORE_FILE: Final = "docker-compose.objectstore.yml"

#: The flag that declines the vault, and the shell variable it sets.
DECLINE_FLAG: Final = "--no-vault"

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


def _vault_project(home: str) -> str:
    return f'"{home}/{VAULT_PROJECT}"'


def start_run(home: str) -> str:
    """Start the vault's own compose project and wait until it answers, sealed or not."""
    return "\n".join(
        (
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
        f'test "${{BRAIN_VAULT:-yes}}" = "no" || docker compose -f {_vault_project(home)} ps '
        f"--status running --services | grep -qx {VAULT_SERVICE}"
    )


def initialise_done() -> str:
    """True when the vault was declined, or it has been initialised by any run, ever."""
    return (
        'test "${BRAIN_VAULT:-yes}" = "no" || '
        f"docker exec {_BAO_ADDR} {VAULT_CONTAINER} bao operator init -status >/dev/null 2>&1"
    )


def initialise_run() -> str:
    """Initialise the vault with the policy's split and show the pieces, once."""
    shares, threshold = DEFAULT_POLICY.shares, DEFAULT_POLICY.threshold
    backslash = chr(92)
    number = f"{backslash}([0-9]*{backslash})"
    return "\n".join(
        (
            f'BRAIN_VAULT_INIT="$(docker exec {_BAO_ADDR} {VAULT_CONTAINER} bao operator init '
            f'{" ".join(init_args(DEFAULT_POLICY))})" || fail "the secrets vault refused to '
            "initialise, so no piece was made and nothing is lost. Read docker logs "
            f'{VAULT_CONTAINER}, then run this again"',
            'say ""',
            f"say \"The secrets vault's unseal key, in {shares} pieces. Any {threshold} of them "
            'open the vault."',
            'say "This is the only time they are shown. Nothing on this server keeps them, and '
            'nothing can show them again."',
            f'if test "$(printf "%s{backslash}n" "$BRAIN_VAULT_INIT" | grep -c "^Unseal Key ")" '
            f"-eq {shares}; then",
            f'  printf "%s{backslash}n" "$BRAIN_VAULT_INIT" | sed -n "s/^Unseal Key {number}: '
            f'/  piece {backslash}1 of {shares}: /p"',
            "else",
            '  say "The vault answered in a shape this installer cannot read, so its whole answer '
            "is below: the pieces and the root token are in it. Keep the pieces as the next lines "
            'say, and finish by hand with ops/openbao/UNSEAL.md."',
            f'  printf "%s{backslash}n" "$BRAIN_VAULT_INIT"',
            '  fail "the vault is initialised and this installer could not read its answer. '
            'Finish by hand with ops/openbao/UNSEAL.md, under Finishing what the installer began"',
            "fi",
            'say ""',
            f'say "Give each piece to a different person now, each by a different route, and keep '
            f"none of them on this server. After any restart of the vault, {threshold} of those "
            'people open it again: ops/openbao/UNSEAL.md, under After a restart."',
            'say "If this terminal is being recorded, or this run is going through tee or into a '
            'log, that record now holds the pieces. Destroy it."',
            "if test -t 0; then",
            '  printf "%s " "Press Enter once every piece is somewhere other than this server:" '
            ">&2",
            "  read -r BRAIN_ANSWER",
            "fi",
        )
    )


def open_done(home: str, env_file: str) -> str:
    """True when the vault was declined, or every token this profile needs is in the file."""
    path = f'"{home}/{env_file}"'
    return (
        'test "${BRAIN_VAULT:-yes}" = "no" || { '
        f'grep -q "^{VAULT_CHOICE}=." {path} && grep -q "^{APPLICATION_TOKEN[1]}=." {path} && '
        f'{{ test -z "${{{WORKER_FILES_VARIABLE}:-}}" || '
        f'grep -q "^{WORKER_TOKEN[1]}=." {path}; }}; }}'
    )


def open_run(home: str, env_file: str) -> str:
    """Open the vault, configure it as root, mint both tokens, and revoke the root token."""
    threshold = DEFAULT_POLICY.threshold
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
            f'vault_piece() {{ printf "%s{newline}" "$BRAIN_VAULT_INIT" | sed -n '
            '"s/^Unseal Key $1: //p"; }',
            f'vault_root() {{ printf "%s{newline}" "$BRAIN_VAULT_INIT" | sed -n '
            '"s/^Initial Root Token: //p"; }',
            'as_vault_root() { BAO_TOKEN="$(vault_root)" docker exec -e BAO_TOKEN '
            f'{_BAO_ADDR} {VAULT_CONTAINER} bao "$@" </dev/null; }}',
            'as_vault_root_reading() { BAO_TOKEN="$(vault_root)" docker exec -i -e BAO_TOKEN '
            f'{_BAO_ADDR} {VAULT_CONTAINER} bao "$@"; }}',
            f"for piece in $(seq 1 {threshold}); do",
            '  printf "%s" "$(vault_piece "$piece")" | '
            f"docker exec -i {_BAO_ADDR} {VAULT_CONTAINER} bao write sys/unseal key=- >/dev/null",
            "done",
            f'{exec_} status >/dev/null 2>&1 || fail "the vault is still sealed after {threshold} '
            "of its pieces. Nothing has been written to the environment file. Open it with "
            'ops/openbao/UNSEAL.md, then finish by hand under Finishing what the installer began"',
            'BRAIN_VAULT_AUDIT="$(as_vault_root audit list 2>/dev/null || true)"',
            'case "$BRAIN_VAULT_AUDIT" in',
            '  *"file/"*) ;;',
            "  *) as_vault_root audit enable -path=file file file_path=/openbao/logs/audit.log "
            "log_raw=false hmac_accessor=true >/dev/null ;;",
            "esac",
            'case "$BRAIN_VAULT_AUDIT" in',
            '  *"stderr/"*) ;;',
            "  *) as_vault_root audit enable -path=stderr file file_path=stderr log_raw=false "
            ">/dev/null ;;",
            "esac",
            'BRAIN_VAULT_ENGINES="$(as_vault_root secrets list)" || fail "the vault would not '
            "list its engines under the root token. Finish by hand with ops/openbao/UNSEAL.md, "
            'under Finishing what the installer began"',
            f"for engine in {' '.join(ENGINES)}; do",
            '  case "$BRAIN_VAULT_ENGINES" in',
            '    *"$engine/ "*) ;;',
            '    *) as_vault_root secrets enable -path="$engine" kv-v2 >/dev/null ;;',
            "  esac",
            "done",
            f'for policy in "{home}/ops/openbao/policies/"*.hcl; do',
            f'  tr -d "{backslash}015" < "$policy" | '
            'as_vault_root_reading policy write "$(basename "$policy" .hcl)" - >/dev/null',
            "done",
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
