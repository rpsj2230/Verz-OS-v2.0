"""The backup installer's refusals: where copies go, who can read them, and the drill service.

The installer is a root-only bash script that writes systemd units, so every test runs it as a
stand-in root with the directories it writes to redirected into a temporary one and `systemctl`
replaced by a recorder. Every assertion is about what it did: its exit status, the files it wrote,
the environment file's lines and the units it enabled. None is about the script's own text.

**The refusals are held from both sides.** For each one the sibling test shows the same
configuration, corrected, installing, because a guard tested only by its refusals is satisfied by a
script that refuses everything.

**The placement is declared and also checked against the obvious.** `BRAIN_BACKUP_OFF_HOST=yes` is
the declaration, which only a person can make; an address that is plainly this machine is refused
even when declared, which is the mistake a declaration is made carelessly with.

Task ids: M30.3.3, M30.3.4
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INSTALLER = REPO / "ops" / "backup" / "brain-install-backup"
BASH = shutil.which("bash")
OPENSSL = shutil.which("openssl")

pytestmark = pytest.mark.skipif(
    BASH is None or OPENSSL is None, reason="no bash or openssl here to run the installer with"
)

FAKE_DOCKER = """#!/bin/sh
[ "$1" = ps ] || exit 1
cat "$FAKE_DIR/containers"
"""

FAKE_ID = """#!/bin/sh
echo 0
"""

FAKE_SYSTEMCTL = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_DIR/systemctl.log"
"""


def _executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


class Server:
    """A directory standing in for a server: the binaries it holds, the units it has and a PATH."""

    def __init__(self, root: Path) -> None:
        self.root = root
        for name in (
            "brain-backup",
            "brain-backup-crypt",
            "brain-drill-service",
            "brain-restore-drill",
        ):
            _executable(root / "usr" / name, "#!/bin/sh\n")
        _executable(root / "stubs" / "docker", FAKE_DOCKER)
        _executable(root / "stubs" / "id", FAKE_ID)
        _executable(root / "stubs" / "aws", "#!/bin/sh\n")
        _executable(root / "stubs" / "systemctl", FAKE_SYSTEMCTL)
        (root / "containers").write_text("db-example\nseaweedfs-example\n", encoding="utf-8")
        (root / "units").mkdir()
        self.public = root / "client.pub"
        private = root / "client.pem"
        assert OPENSSL is not None
        subprocess.run(
            [OPENSSL, "genrsa", "-out", str(private), "2048"], capture_output=True, check=True
        )
        subprocess.run(
            [OPENSSL, "rsa", "-in", str(private), "-pubout", "-out", str(self.public)],
            capture_output=True,
            check=True,
        )
        self.private = private

    @property
    def env_file(self) -> Path:
        return self.root / "brain-backup.env"

    def run(self, **env: str | None) -> subprocess.CompletedProcess[str]:
        assert BASH is not None
        base = {
            "PATH": str(self.root / "stubs") + os.pathsep + os.environ["PATH"],
            "FAKE_DIR": str(self.root),
            "BRAIN_BIN_DIR": str(self.root / "usr"),
            "BRAIN_BACKUP_ENV_FILE": str(self.env_file),
            "BRAIN_SYSTEMD_DIR": str(self.root / "units"),
            "BRAIN_SYSTEMCTL": str(self.root / "stubs" / "systemctl"),
            "BRAIN_INSTALL_ENV": str(self.root / "absent.env"),
            "HOME": str(self.root),
            "AWS_ACCESS_KEY_ID": "key-id",
            "AWS_SECRET_ACCESS_KEY": "key-secret",
            "BRAIN_BACKUP_ENDPOINT": "https://objects.example.net",
            "BRAIN_BACKUP_OFF_HOST": "yes",
            "BRAIN_BACKUP_RECIPIENT": str(self.public),
        }
        for name, value in env.items():
            if value is None:
                base.pop(name, None)
            else:
                base[name] = value
        return subprocess.run(
            [BASH, str(INSTALLER)],
            env=base,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )

    def written(self) -> dict[str, str]:
        lines = self.env_file.read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines)

    def enabled(self) -> list[str]:
        log = self.root / "systemctl.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture
def server(tmp_path: Path) -> Server:
    return Server(tmp_path)


def test_a_configuration_naming_another_machine_and_a_client_key_installs_and_says_so(
    server: Server,
) -> None:
    """The positive case, from which every refusal below departs. Delete this and the installer
    can be a script that refuses everything, and every install is then configured by hand."""
    result = server.run()
    assert result.returncode == 0, result.stderr
    written = server.written()
    assert written["BRAIN_BACKUP_OFF_HOST"] == "yes"
    assert written["BRAIN_BACKUP_RECIPIENT"] == str(server.public)
    assert written["BRAIN_BACKUP_ENDPOINT"] == "https://objects.example.net"
    assert "enable --now brain-backup.timer" in server.enabled()
    assert not (server.root / "units" / "brain-drill.timer").exists()
    assert "another machine" in result.stdout and "encrypted" in result.stdout


def test_the_environment_file_is_readable_by_root_alone(server: Server) -> None:
    """It holds the bucket's secret. Delete this and the secret is written world-readable."""
    server.run()
    assert (server.env_file.stat().st_mode & 0o777) == 0o600


def test_there_is_no_default_place_for_copies_to_go(server: Server) -> None:
    """The old default was the install's own file store, on the machine it is a copy of. Delete
    this and the default comes back, and every install keeps its copies beside the original."""
    result = server.run(BRAIN_BACKUP_ENDPOINT=None)
    assert result.returncode == 1
    assert "no default" in result.stderr
    assert not server.env_file.exists()


def test_an_endpoint_not_declared_off_the_host_is_refused(server: Server) -> None:
    """A person has to say it. Delete this and an address is taken as another machine because it
    looks like a name."""
    result = server.run(BRAIN_BACKUP_OFF_HOST=None)
    assert result.returncode == 1
    assert "not yes" in result.stderr
    assert not server.env_file.exists()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:8333",
        "http://127.0.0.1:8333",
        "http://[::1]:8333",
        "http://seaweedfs-example:8333",
    ],
)
def test_an_address_that_is_plainly_this_machine_is_refused_even_when_declared_off_it(
    server: Server, endpoint: str
) -> None:
    """Loopback, localhost and a container running here. Delete this and a careless yes puts the
    copies on the machine they protect."""
    result = server.run(BRAIN_BACKUP_ENDPOINT=endpoint)
    assert result.returncode == 1
    assert "not off the host" in result.stderr
    assert not server.env_file.exists()


def test_this_machines_own_name_is_refused_too(server: Server) -> None:
    """The hostname is the address a person types when they mean here. Delete this and it passes
    as another machine."""
    name = subprocess.run(["hostname"], capture_output=True, text=True, check=True).stdout.strip()
    result = server.run(BRAIN_BACKUP_ENDPOINT=f"https://{name}:8333")
    assert result.returncode == 1
    assert "not off the host" in result.stderr


def test_keeping_copies_on_the_host_is_possible_only_by_saying_so_and_is_recorded(
    server: Server,
) -> None:
    """The knowing choice. Delete this and the only alternative to off-host is no install, and
    people pass a false yes to get past it."""
    result = server.run(
        BRAIN_BACKUP_ENDPOINT="http://localhost:8333", BRAIN_BACKUP_ALLOW_ON_HOST="yes"
    )
    assert result.returncode == 0, result.stderr
    assert server.written()["BRAIN_BACKUP_OFF_HOST"] == "no"
    assert "THIS machine" in result.stdout


def test_a_recipient_that_is_not_there_or_is_a_private_key_is_refused(server: Server) -> None:
    """A private key must stay with the client. Delete this and the key that opens every copy is
    written into the environment of the machine that makes them."""
    for recipient, why in (
        (str(server.root / "nowhere.pub"), "no file there"),
        (str(server.private), "not a public key"),
    ):
        result = server.run(BRAIN_BACKUP_RECIPIENT=recipient)
        assert result.returncode == 1
        assert why in result.stderr
    assert not server.env_file.exists()


def test_no_recipient_is_refused_unless_unencrypted_copies_are_asked_for_by_name(
    server: Server,
) -> None:
    """Delete this and an install with no key stores the company's records readable without anyone
    having said so."""
    refused = server.run(BRAIN_BACKUP_RECIPIENT=None)
    assert refused.returncode == 1
    assert "BRAIN_BACKUP_ALLOW_UNENCRYPTED" in refused.stderr
    allowed = server.run(BRAIN_BACKUP_RECIPIENT=None, BRAIN_BACKUP_ALLOW_UNENCRYPTED="yes")
    assert allowed.returncode == 0, allowed.stderr
    assert server.written()["BRAIN_BACKUP_RECIPIENT"] == ""
    assert "NOT ENCRYPTED" in allowed.stdout


def test_credentials_are_required_and_the_helper_scripts_have_to_be_there(server: Server) -> None:
    """Delete this and a copy that cannot authenticate fails every night into a journal nobody
    reads, or the timer points at a script that is not installed."""
    assert server.run(AWS_SECRET_ACCESS_KEY=None).returncode == 1
    (server.root / "usr" / "brain-backup-crypt").unlink()
    result = server.run()
    assert result.returncode == 1
    assert "brain-backup-crypt" in result.stderr


# ------------------------------------------------------------------------------ the drill service


def test_the_drill_service_is_not_installed_unless_it_is_asked_for(server: Server) -> None:
    """It starts containers on the server, which is the owner's decision (item 235). Delete this
    and an ordinary install gets a service nobody agreed to."""
    server.run()
    assert not (server.root / "units" / "brain-drill.service").exists()
    assert "BRAIN_APP_IMAGE" not in server.written()


def test_the_drill_service_installs_with_its_image_and_its_timer_when_asked_for(
    server: Server,
) -> None:
    """The positive case. Delete this and the opt-in installs nothing, and the weekly rehearsal
    this is for is never scheduled."""
    result = server.run(BRAIN_DRILL_SERVICE="yes", BRAIN_APP_IMAGE="registry.example.net/app:1.2.3")
    assert result.returncode == 0, result.stderr
    assert server.written()["BRAIN_APP_IMAGE"] == "registry.example.net/app:1.2.3"
    timer = (server.root / "units" / "brain-drill.timer").read_text(encoding="utf-8")
    assert "OnUnitInactiveSec=10min" in timer
    service = (server.root / "units" / "brain-drill.service").read_text(encoding="utf-8")
    assert f"ExecStart={server.root / 'usr' / 'brain-drill-service'}" in service
    assert "enable --now brain-drill.timer" in server.enabled()


def test_the_drill_service_reads_the_image_the_installer_wrote_when_none_is_given(
    server: Server,
) -> None:
    """The image is the install's own, written beside the compose file. Delete this and every
    install has to be told what it is already running."""
    (server.root / "absent.env").write_text(
        "OTHER=1\nAPP_IMAGE=registry.example.net/app:9\n", encoding="utf-8"
    )
    result = server.run(
        BRAIN_DRILL_SERVICE="yes", BRAIN_INSTALL_ENV=str(server.root / "absent.env")
    )
    assert result.returncode == 0, result.stderr
    assert server.written()["BRAIN_APP_IMAGE"] == "registry.example.net/app:9"


def test_the_drill_service_is_refused_without_an_image_or_without_its_scripts(
    server: Server,
) -> None:
    """Delete this and the timer is enabled over a service that cannot run."""
    no_image = server.run(BRAIN_DRILL_SERVICE="yes")
    assert no_image.returncode == 1
    assert "application image" in no_image.stderr
    (server.root / "usr" / "brain-drill-service").unlink()
    no_script = server.run(BRAIN_DRILL_SERVICE="yes", BRAIN_APP_IMAGE="registry.example.net/app:1")
    assert no_script.returncode == 1
    assert "brain-drill-service" in no_script.stderr
    assert not (server.root / "units" / "brain-drill.timer").exists()


def test_an_identity_left_for_rehearsals_is_written_only_when_the_service_is_asked_for(
    server: Server,
) -> None:
    """The client's private key path is the one value that trades secrecy for convenience. Delete
    this and it is written into installs that never asked for rehearsals."""
    server.run(BRAIN_BACKUP_IDENTITY="/etc/example/identity.pem")
    assert "BRAIN_BACKUP_IDENTITY" not in server.written()
    server.run(
        BRAIN_DRILL_SERVICE="yes",
        BRAIN_APP_IMAGE="registry.example.net/app:1",
        BRAIN_BACKUP_IDENTITY="/etc/example/identity.pem",
    )
    assert server.written()["BRAIN_BACKUP_IDENTITY"] == "/etc/example/identity.pem"
