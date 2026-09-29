"""The one command that moves an older install's vault onto the seal that opens itself.

`ops/openbao/switch-to-auto-unseal.sh` is run once, by an owner, against the vault that holds every
credential his install has, so the properties worth holding are the ones that decide whether a bad
day loses anything: nothing changes until the pieces are proved against the running vault, no
piece or token is ever printed, the data is copied and the way back recorded before the vault is
touched, and the move keeps the vault's own tokens rather than minting new ones.

Two kinds of evidence. **Read:** the script, for the order of its steps and for every place a
secret is expanded. **Run against a stand-in:** its refusals, with a `docker` that answers as a
running vault does and records every call, so "nothing has been changed" is a list of calls rather
than a sentence. Neither is OpenBao: the whole move was rehearsed on throwaway containers on a
server on 2026-09-29 against openbao 2.4.1, and `ops/openbao/REHEARSAL.md` records what that run
showed.

Task ids: M31.3.2.1, M31.3.2.2
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "openbao" / "switch-to-auto-unseal.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="the switch is a bash script")

#: The shell variables that hold a piece, a root token, a token read from a container or an answer
#: carrying a key. None of them may reach a terminal.
SECRET_VARIABLES = ("ROOT", "P1", "P2", "P3", "value", "answer", "encoded", "body")

#: A `docker` that answers as a running, open, Shamir-sealed vault brought up by compose, refuses
#: every key offered for a root token, and records every call.
STAND_IN = r"""#!/bin/sh
printf '%s\n' "$*" >> "$STUB_STATE/calls"
case "$*" in
  "inspect brain-vault") exit 0 ;;
  *"com.docker.compose.project\""*"brain-vault") printf 'brain-vault\n'; exit 0 ;;
  *"com.docker.compose.service\""*"brain-vault") printf 'vault\n'; exit 0 ;;
  *"com.docker.compose.project.working_dir\""*"brain-vault") printf '/opt/brain-vault\n'; exit 0 ;;
  *"com.docker.compose.project.config_files\""*"brain-vault")
    printf '/opt/brain-vault/compose.yml\n'; exit 0 ;;
  *'"/openbao/file"'*) printf 'brain-vault_brain-vault-data\n'; exit 0 ;;
  *'"/openbao/logs"'*) printf 'brain-vault_brain-vault-logs\n'; exit 0 ;;
  *"NetworkSettings.Networks"*) printf 'brain-vault\n'; exit 0 ;;
  *"bao status -format=json") printf '{\n  "type": "shamir",\n  "sealed": false\n}\n'; exit 0 ;;
  *"bao status") printf 'Seal Type    shamir\nSealed       false\n'; exit 0 ;;
  *"sys/generate-root/attempt") printf '{\n  "nonce": "a-nonce",\n  "otp": "an-otp"\n}\n'; exit 0 ;;
  *"sys/generate-root/update"*) cat >/dev/null; exit 2 ;;
esac
exit 0
"""


def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def switching(tmp_path: Path, *args: str, pieces: str | None) -> tuple[int, str, list[str]]:
    """Run the real script as a stand-in root with a stand-in docker, from the release directory."""
    release = tmp_path / "openbao"
    shutil.copytree(REPO / "ops" / "openbao", release)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", STAND_IN), ("id", '#!/bin/sh\nprintf "0\\n"\n')):
        stub = bin_dir / name
        stub.write_text(body, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    (state / "calls").write_text("", encoding="utf-8")
    command = [str(BASH), (release / SCRIPT.name).as_posix(), *args]
    if pieces is not None:
        piece_file = tmp_path / "pieces.txt"
        piece_file.write_text(pieces, encoding="utf-8", newline="\n")
        command += ["--pieces-file", piece_file.as_posix()]
    command += [
        "--state-dir",
        (tmp_path / "etc").as_posix(),
        "--backups",
        (tmp_path / "backups").as_posix(),
    ]
    done = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "STUB_STATE": state.as_posix(),
        },
    )
    calls = (state / "calls").read_text(encoding="utf-8").splitlines()
    return done.returncode, done.stdout + done.stderr, calls


def test_the_script_parses_and_stops_on_the_first_error() -> None:
    """Delete this and a syntax error ships in the one script an owner runs against his vault, or a
    failed step is carried past with the vault half moved."""
    assert BASH is not None
    parsed = subprocess.run([BASH, "-n", SCRIPT.as_posix()], capture_output=True, check=False)
    assert parsed.returncode == 0, parsed.stderr
    lines = text().splitlines()
    assert "set -euo pipefail" in lines
    assert "umask 077" in lines


def test_no_piece_token_or_key_is_ever_printed() -> None:
    """Every line that expands a variable holding a secret either hands it to docker by name, pipes
    it, or assigns it; none prints it. Delete this and an innocent-looking `say` with a token in it
    puts the owner's vault token into his terminal scrollback and whatever records it."""
    # The two functions whose whole job is to hand a piece or the recovery key to a pipe.
    producers = re.compile(r"^(piece|recovery_piece)\(\) \{")
    secret = re.compile(rf"\$\{{?(?:{'|'.join(SECRET_VARIABLES)})\b")
    for number, line in enumerate(text().splitlines(), 1):
        if producers.match(line):
            continue
        # Each command on the line, with the separator that follows it.
        pieces = re.split(r"(\|\||&&|;|\|)", line)
        for index in range(0, len(pieces), 2):
            segment = pieces[index].strip().lstrip("{( ").strip()
            follows = pieces[index + 1] if index + 1 < len(pieces) else ""
            if not secret.search(segment):
                continue
            assert not re.match(r"(say|step|fail|echo)\b", segment), (number, line)
            if segment.startswith("printf"):
                assert follows == "|" or ">" in segment, (number, line)
        # And every use of the two producers is piped or captured, never left on the terminal.
        # `make_root` takes the producer's name as an argument and pipes it itself.
        if line.strip().startswith("make_root "):
            continue
        for call in re.finditer(r'(?<![\w-])(piece "\$\w+"|"\$2" "\$n"|recovery_piece\b)', line):
            rest = line[call.end() :]
            assert rest.lstrip().startswith(("|", ")")), (number, line)


def test_the_pieces_are_proved_before_the_vault_is_touched_and_the_way_back_is_kept_first() -> None:
    """The order the owner's data depends on: a root token made from the pieces (and revoked) while
    the vault is still open, then the seal key, then the vault stopped and its data copied with the
    record --rollback reads, and only then recreated. Delete this and a reordering can stop the
    vault before knowing whether the pieces open it, which on a vault whose pieces are wrong is a
    vault
    that never opens again."""
    body = text()
    proved = body.index("make_any_root\nrevoke_root")
    sealed = body.index('head -c 32 /dev/urandom > "$SEAL_KEY.new"')
    stopped = body.index('docker stop "$VAULT" >/dev/null\n  MOUNT=')
    copied = body.index('tar -czf "$BACKUP"')
    recorded = body.index('} > "$RECORD"')
    recreated = body.index('docker compose -p "$PROJECT" -f "$HERE/compose.yml" up -d')
    assert proved < sealed < stopped < copied < recorded < recreated


def test_the_move_keeps_the_vaults_own_tokens_and_mints_only_the_deploy_token() -> None:
    """In place, so the application's and the worker's tokens are the ones they already hold, and a
    hosting panel's stored settings never change. Measured on openbao 2.4.1: a custom token id with
    the `s.` prefix is refused, so a move that minted new ones could never give them the old values.
    Delete this and the script can grow a `token create` for them, which strands every container
    that holds the old one."""
    body = text()
    created = re.findall(r"token create (-policy=\S+)", body)
    assert created == ["-policy=deploy"]
    assert "-id=" not in body
    assert 'BRAIN_VAULT_DATA_VOLUME="$DATA_VOLUME"' in body
    assert 'BRAIN_VAULT_LOGS_VOLUME="$LOGS_VOLUME"' in body
    assert 'BRAIN_VAULT_NETWORK="$NETWORK"' in body


def test_without_a_pieces_file_it_refuses_and_asks_docker_nothing(tmp_path: Path) -> None:
    """Delete this and a run with no pieces can go on to stop the vault, which without pieces is the
    one thing that loses it."""
    code, out, calls = switching(tmp_path, pieces=None)
    assert code != 0
    assert "--pieces-file is required" in out
    assert calls == []


def test_pieces_the_vault_does_not_accept_change_nothing(tmp_path: Path) -> None:
    """The refusal the order above exists for, run: three well-formed pieces the vault refuses, and
    the script stops having made no seal key, stopped nothing, copied nothing and recreated nothing.
    Delete this and the proof can move after the first change without any read test noticing."""
    pieces = "".join(f"Unseal Key {n}: piece-{n}-not-this-vaults\n" for n in range(1, 6))
    code, out, calls = switching(tmp_path, pieces=pieces)
    assert code != 0
    # Said as the pieces being wrong, at the first one refused, which is what the owner can act on.
    assert "did not accept key 1 of 3" in out
    assert "the keys in hand are not this vault's. Nothing has been changed" in out
    assert not (tmp_path / "etc" / "seal.key").exists()
    assert not [one for one in calls if one.startswith(("stop", "compose", "restart", "rm"))]
    for n in range(1, 6):
        assert f"piece-{n}-not-this-vaults" not in out
        assert not [one for one in calls if f"piece-{n}" in one]


def test_fewer_than_three_pieces_are_refused_before_the_vault_is_asked_anything(
    tmp_path: Path,
) -> None:
    """Pieces are read by the label `bao operator init` prints them under. Delete this and a file
    holding two pieces reaches the vault and fails half way through a root token attempt."""
    code, out, calls = switching(tmp_path, pieces="Unseal Key 1: one\nUnseal Key 2: two\n")
    assert code != 0
    assert "holds 2 distinct pieces" in out
    assert not [one for one in calls if "generate-root" in one]


def test_the_rollback_refuses_without_a_record_of_a_switch(tmp_path: Path) -> None:
    """The way back is only as good as what the switch recorded. Delete this and a rollback with no
    record can stop the vault and restore nothing."""
    code, out, calls = switching(tmp_path, "--rollback", pieces="Unseal Key 1: a\n")
    assert code != 0
    assert "no record of a switch" in out
    assert not [one for one in calls if one.startswith(("stop", "compose"))]
