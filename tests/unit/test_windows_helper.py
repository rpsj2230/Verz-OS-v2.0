"""The Windows install helper, run against a stand-in for SSH and held to the documented command.

`brain.deployment.windows_helper` argues the shape. What is proved here is what can be proved
without a server: that the helper refuses an address it must refuse, that it asks SSH for
exactly what that module describes and in that order, that the one line it hands SSH to run is
the install command `docs/install/install.md` documents, and that nothing it writes outlives
it or holds a secret.

**The script is run, not read.** Every test below that is about behaviour starts PowerShell:
`powershell.exe` where it exists, which is Windows PowerShell 5.1 and the version a person
double-clicking the launcher gets, and `pwsh` otherwise, which is what the ubuntu runner has.
SSH and `ssh-keygen` are replaced on `PATH` by two small Python programs that record their
arguments and their working folder and answer the way the real ones do. Where neither
PowerShell exists the behavioural tests skip and say so, and the reading tests still run.

**Both language modes.** The happy path runs again in Constrained Language Mode, which is how
Windows runs an unsigned script under an enforcing application control policy, because a
helper that works in the full language and not in that one fails on exactly the machine it was
written for.

**Nothing here has touched a real server.** The stand-in answers what `ssh.exe` answered when
it was measured against a real one on 2026-09-17; that is the whole of the evidence about the
far end.

Task ids: M42.6.6
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.install_script import FLAGS, RELEASE_URL_VARIABLE
from brain.deployment.release import REPO, included_by
from brain.deployment.windows_helper import (
    ARCHIVE_NAME,
    HELPER_GUIDE_PATH,
    HELPER_LAUNCHER_PATH,
    HELPER_SCRIPT_PATH,
    archive_name,
    install_lines,
    remote_command,
)
from brain.ops.wiring import PROFILES

SCRIPT: Path = REPO / HELPER_SCRIPT_PATH
LAUNCHER: Path = REPO / HELPER_LAUNCHER_PATH
GUIDE: Path = REPO / HELPER_GUIDE_PATH
INSTALL_GUIDE: Path = REPO / "docs" / "install" / "install.md"
WORKFLOW: Path = REPO / ".github" / "workflows" / "release.yml"

#: `powershell.exe` first, because it is the version the launcher starts.
POWERSHELL: str | None = shutil.which("powershell") or shutil.which("pwsh")

needs_powershell = pytest.mark.skipif(
    POWERSHELL is None, reason="no PowerShell on this machine, so the helper cannot be run"
)

#: A public key as SSH writes one into a known-hosts file. Public, and made of repeated bytes,
#: so it names no machine.
KEY_BLOB: bytes = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes([0x11]) * 32
KEY_TEXT: str = base64.b64encode(KEY_BLOB).decode("ascii")
FINGERPRINT: str = "SHA256:" + base64.b64encode(hashlib.sha256(KEY_BLOB).digest()).decode(
    "ascii"
).rstrip("=")

#: What the stand-in installer prints as the code, so a test can look for it in every file.
SENTINEL_CODE: str = "c0ffee" * 10 + "beef"

SERVER = "server.example.invalid"
RELEASE_PAGE = "https://releases.example.invalid/owner/brain/releases/tag/v0.1.0"
CONSOLE = "https://brain.example.invalid"

STUB_SSH = """
import json, os, sys
argv = sys.argv[1:]
options = [argv[i + 1] for i, one in enumerate(argv) if one == "-o" and i + 1 < len(argv)]
known = next((one.split("=", 1)[1] for one in options if one.startswith("UserKnownHostsFile=")), "")
entry = {"argv": argv, "cwd": os.getcwd(), "files": sorted(os.listdir(os.getcwd()))}
if known and os.path.exists(known):
    with open(known, encoding="utf-8") as held:
        entry["known_hosts"] = held.read()
with open(os.environ["BRAIN_STUB_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(entry) + "\\n")
host = argv[argv.index("--") + 1]
if "StrictHostKeyChecking=accept-new" in options:
    if os.environ.get("BRAIN_STUB_REACH") == "unknown":
        sys.stderr.write("ssh: Could not resolve hostname " + host + ": No such host is known.\\n")
        sys.exit(255)
    with open(known, "a", encoding="utf-8") as held:
        held.write(host + " ssh-ed25519 " + os.environ["BRAIN_STUB_KEY"] + "\\n")
    sys.stderr.write("Warning: Permanently added '" + host + "' (ED25519) to known hosts.\\n")
    sys.stderr.write("root@" + host + ": Permission denied (publickey).\\n")
    sys.exit(255)
print("setup code: " + os.environ["BRAIN_STUB_CODE"])
sys.exit(int(os.environ.get("BRAIN_STUB_INSTALL_EXIT", "0")))
"""

STUB_KEYGEN = """
import base64, hashlib, sys
path = sys.argv[sys.argv.index("-f") + 1]
for line in open(path, encoding="utf-8"):
    parts = line.split()
    if len(parts) < 3:
        continue
    digest = base64.b64encode(hashlib.sha256(base64.b64decode(parts[2])).digest()).decode()
    print("256 SHA256:" + digest.rstrip("=") + " " + parts[0] + " (ED25519)")
"""


@dataclass(frozen=True)
class Run:
    """One run of the helper: what it printed, how it ended, and every call SSH received."""

    code: int
    said: str
    calls: tuple[dict[str, Any], ...]
    temp: Path


def _stubs(bin_dir: Path) -> None:
    """Put the two stand-ins on a folder that goes first on `PATH`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (("ssh", STUB_SSH), ("ssh-keygen", STUB_KEYGEN)):
        source = bin_dir / f"{name}_stub.py"
        source.write_text(body, encoding="utf-8", newline="\n")
        if os.name == "nt":
            launcher = bin_dir / f"{name}.cmd"
            launcher.write_text(
                f'@"{sys.executable}" "{source}" %*\r\n@exit /b %ERRORLEVEL%\r\n',
                encoding="ascii",
                newline="",
            )
        else:
            launcher = bin_dir / name
            launcher.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8", newline="\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_helper(
    tmp_path: Path,
    answers: Sequence[str],
    *,
    constrained: bool = False,
    env: Mapping[str, str] | None = None,
) -> Run:
    """Run the helper once, answering its questions in order, with SSH replaced."""
    assert POWERSHELL is not None
    bin_dir = tmp_path / "bin"
    temp = tmp_path / "temp"
    temp.mkdir(exist_ok=True)
    _stubs(bin_dir)
    log = tmp_path / "ssh-calls.jsonl"
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "TEMP": str(temp),
        "TMP": str(temp),
        "TMPDIR": str(temp),
        "BRAIN_STUB_LOG": str(log),
        "BRAIN_STUB_KEY": KEY_TEXT,
        "BRAIN_STUB_CODE": SENTINEL_CODE,
        **(env or {}),
    }
    mode = (
        "$ExecutionContext.SessionState.LanguageMode = 'ConstrainedLanguage'; "
        if constrained
        else ""
    )
    command = f"{mode}& '{SCRIPT}'; exit $LASTEXITCODE"
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        input="\n".join(answers) + "\n",
        capture_output=True,
        text=True,
        timeout=180,
        env=environment,
        cwd=tmp_path,
        check=False,
    )
    calls: tuple[dict[str, Any], ...] = ()
    if log.exists():
        calls = tuple(json.loads(line) for line in log.read_text(encoding="utf-8").splitlines())
    return Run(code=done.returncode, said=done.stdout + done.stderr, calls=calls, temp=temp)


def call_functions(tmp_path: Path, table: Sequence[str], row: str) -> dict[str, list[str]]:
    """Dot-source the helper, which asks nothing, and evaluate `row` once for each entry.

    `row` sees the entry as `$_` and returns the fields it wants as an array, or `$null` for a
    refusal. One line comes back per entry, fields separated by a character no entry holds,
    because `ConvertTo-Json` wraps nested arrays differently in the two PowerShells.
    """
    assert POWERSHELL is not None
    listed = ", ".join("'" + one.replace("'", "''") + "'" for one in table)
    command = (
        f". '{SCRIPT}'; @({listed}) | ForEach-Object {{ $found = & {{ {row} }}; "
        "if ($null -eq $found) { $_ + '|REFUSED' } else { $_ + '|' + ($found -join '|') } }"
    )
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
        check=True,
    )
    rows = [line.split("|") for line in done.stdout.splitlines() if "|" in line]
    return {one[0]: one[1:] for one in rows}


#: Every answer a person gives on the way to a finished install, in the order they are asked.
HAPPY: tuple[str, ...] = (SERVER, "admin", RELEASE_PAGE, "lite", CONSOLE, "yes", "yes", "")

EXPECTED_COMMAND = remote_command(
    script_url="https://releases.example.invalid/owner/brain/releases/download/v0.1.0/install.sh",
    archive_url=(
        "https://releases.example.invalid/owner/brain/releases/download/v0.1.0/"
        + archive_name("v0.1.0")
    ),
    release="v0.1.0",
    profile="lite",
    console_address=CONSOLE,
)


def _option(argv: Sequence[str], name: str) -> list[str]:
    """Every value SSH was given for one `-o` option, by its name."""
    return [
        argv[i + 1].split("=", 1)[1]
        for i, one in enumerate(argv)
        if one == "-o" and i + 1 < len(argv) and argv[i + 1].startswith(f"{name}=")
    ]


# ============================================================ the command it runs
@needs_powershell
def test_the_command_run_on_the_server_is_exactly_the_documented_install_command(
    tmp_path: Path,
) -> None:
    """The leaf's own words: it runs the one install command there. Asserted on the argument
    SSH received as the command to run, whole, against the command this repository builds,
    and the guide's code block is held to the same builder by the next test.

    Delete this and the helper can drift into a variant of the install nobody reading the guide
    would recognise, which is a second install path with no documentation."""
    done = run_helper(tmp_path, HAPPY)

    assert done.code == 0, done.said
    install = done.calls[-1]["argv"]
    assert install[-1] == EXPECTED_COMMAND
    assert install[-3:-1] == ["--", SERVER]
    assert install[install.index("-l") + 1] == "admin"


def test_the_guides_command_is_the_command_the_helper_is_held_to() -> None:
    """The other half of the chain. `install.md` shows the command with placeholders and a
    step for reading the script first; with that step taken out and the continuation joined,
    what is left is `install_lines` given the same placeholders.

    Delete this and the guide and the helper can each be edited alone, and both stay green
    against their own copy."""
    text = INSTALL_GUIDE.read_text(encoding="utf-8")
    block = re.search(r"## Run this one command\s+```\n(.*?)```", text, re.S)
    assert block is not None, "install.md no longer has the one command"
    lines = [one.strip() for one in block.group(1).replace("\\\n", " ").splitlines()]
    shown = [re.sub(r"\s+", " ", one) for one in lines if one and not one.startswith("less ")]

    assert tuple(shown) == install_lines(
        script_url="<where install.sh is published for your release>",
        archive_url="<where the release archive is>",
        release="<tag>",
        profile="lite",
        console_address="https://brain.example.invalid",
    )


def test_the_command_speaks_the_installers_own_flags_and_variable() -> None:
    """The builder spells the flags and the variable out, so it is held against the installer's
    own declarations rather than against itself: a flag renamed there and not here is a command
    the installer refuses as an unknown option.

    Delete this and the positive test above stays green on a renamed flag, because it compares
    the builder with the builder."""
    line = remote_command(
        script_url="https://a.example.invalid/install.sh",
        archive_url="https://a.example.invalid/a.tar.gz",
        release="v1",
        profile="lite",
        console_address="https://b.example.invalid",
    )
    declared = {flag for flag, _ in FLAGS}
    used = set(re.findall(r"(?<=\s)--[a-z-]+", line))

    assert used <= declared, used - declared
    assert {"--release", "--profile", "--console-address"} <= used
    assert f"sudo {RELEASE_URL_VARIABLE}=https://a.example.invalid/a.tar.gz bash" in line


def test_the_archive_name_is_the_one_the_release_workflow_builds() -> None:
    """The helper fetches `brain-<tag>.tar.gz` because that is what the workflow publishes.
    Read out of the workflow's tar step rather than restated.

    Delete this and a rename of the archive in the workflow publishes a release the helper
    points at a file that is not there, found on a client's server as a 404 from curl."""
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["archive"]["steps"]
    tar = next(str(one["run"]) for one in steps if "tar -czf" in str(one.get("run", "")))
    named = re.search(r'"\$RUNNER_TEMP/(brain-\$TAG\.tar\.gz)"', tar)

    assert named is not None
    assert named.group(1) == ARCHIVE_NAME.format(release="$TAG")


# ============================================================ who the server is
@needs_powershell
def test_nothing_is_offered_to_a_server_before_its_identity_is_confirmed(tmp_path: Path) -> None:
    """`NOTHING_IS_OFFERED_TO_A_SERVER_NOBODY_HAS_CONFIRMED`. The first call is the probe, it
    comes before the install, and every way SSH could authenticate is switched off on it.

    Delete this and the probe can offer the person's key, or wait at a password prompt, to a
    machine nobody has agreed is theirs."""
    done = run_helper(tmp_path, HAPPY)

    assert len(done.calls) == 2, done.said
    probe = done.calls[0]["argv"]
    assert _option(probe, "StrictHostKeyChecking") == ["accept-new"]
    assert _option(probe, "BatchMode") == ["yes"]
    assert _option(probe, "PubkeyAuthentication") == ["no"]
    assert _option(probe, "PasswordAuthentication") == ["no"]
    assert _option(probe, "KbdInteractiveAuthentication") == ["no"]
    assert probe[-2:] == ["--", SERVER], "the probe runs a command, or takes an option as a host"


@needs_powershell
def test_the_install_connection_accepts_only_the_key_the_person_confirmed(tmp_path: Path) -> None:
    """`THE_KEY_THE_PERSON_CONFIRMED_IS_THE_ONLY_KEY_ACCEPTED`. The install call checks strictly,
    against the helper's own file for both the user and the global list, and that file held
    exactly the key whose fingerprint was shown when the call was made.

    Delete this and the install connection can go back to SSH's ordinary checking, which
    confirms one machine on the screen and trusts whichever answers the second connection."""
    done = run_helper(tmp_path, HAPPY)
    install = done.calls[1]

    assert FINGERPRINT in done.said, "the fingerprint shown is not the key's"
    assert _option(install["argv"], "StrictHostKeyChecking") == ["yes"]
    assert _option(install["argv"], "UserKnownHostsFile") == ["brain-known-hosts"]
    assert _option(install["argv"], "GlobalKnownHostsFile") == ["brain-known-hosts"]
    assert install["known_hosts"] == f"{SERVER} ssh-ed25519 {KEY_TEXT}\n"
    assert install["cwd"] == done.calls[0]["cwd"], "the two calls read different files"


@needs_powershell
def test_a_server_not_confirmed_is_never_installed_on(tmp_path: Path) -> None:
    """Anything but `yes` at the fingerprint stops, before the install call, and says why. The
    sibling of the happy path, which is what proves the question is asked rather than printed.

    The answer after the refusal is `yes`, and that is the point of it: a mutation that let the
    fingerprint through survived the first version of this test, because that version answered
    nothing to the start question that follows and the second gate stopped the run instead.

    Delete this and the confirmation can become a line of text the helper carries on past."""
    done = run_helper(tmp_path, (SERVER, "admin", RELEASE_PAGE, "lite", CONSOLE, "no", "yes", ""))

    assert done.code == 1
    assert len(done.calls) == 1, "something after the probe reached SSH"
    assert "You did not confirm the server." in done.said
    assert "Nothing was installed." in done.said


@needs_powershell
def test_a_server_that_cannot_be_found_is_told_in_words_and_nothing_is_installed(
    tmp_path: Path,
) -> None:
    """A probe that learns no identity has nothing to show and nothing to confirm, so the
    helper says what is wrong in words a person can act on and stops.

    Delete this and a mistyped address reaches the fingerprint question with no fingerprint,
    which a person answers yes to."""
    done = run_helper(
        tmp_path,
        (SERVER, "admin", RELEASE_PAGE, "lite", CONSOLE, ""),
        env={"BRAIN_STUB_REACH": "unknown"},
    )

    assert done.code == 2
    assert len(done.calls) == 1
    assert "could not be found" in done.said


# ============================================================ what it refuses
@needs_powershell
def test_an_empty_or_malformed_server_address_is_refused_and_a_good_one_is_not(
    tmp_path: Path,
) -> None:
    """`AN_ANSWER_IS_A_SHAPE_OR_IT_IS_REFUSED`, over the table of what a person pastes. A leading
    dash is the one that matters most: SSH reads it as an option, and `-oProxyCommand=...` runs
    a program on the person's own computer. The accepted half is asserted beside it, or a check
    refusing everything would pass.

    Delete this and the address check can loosen to anything without a space."""
    refused = [
        "",
        "-host",
        "-oProxyCommand=calc",
        "user@host",
        "host name",
        "999.1.1.1",
        "host:0",
        "host:70000",
        "a..b",
        "host;reboot",
        "http://host",
    ]
    accepted = {
        "server.example.invalid": ["server.example.invalid", "22"],
        "server.example.invalid:2222": ["server.example.invalid", "2222"],
        "10.0.0.1": ["10.0.0.1", "22"],
        "[2001:db8::1]:2200": ["2001:db8::1", "2200"],
    }
    by_address = call_functions(
        tmp_path,
        [*refused, *accepted],
        "$r = Split-BrainServer $_; if ($null -ne $r) { @($r.Name, [string]$r.Port) }",
    )

    assert {one for one in refused if by_address[one] != ["REFUSED"]} == set()
    assert {one: by_address[one] for one in accepted} == accepted


@needs_powershell
def test_a_release_address_is_https_and_names_a_release_or_it_is_refused(tmp_path: Path) -> None:
    """`A_RELEASE_OVER_PLAIN_HTTP_IS_A_ROOT_SHELL_FOR_THE_NETWORK`, and the three shapes a person
    pastes: a release page, a link to one of its files, and a folder named for the release.

    Delete this and an `http` address, or one carrying a shell character, reaches a line that
    runs as root."""
    refused = [
        "http://releases.example.invalid/owner/brain/releases/tag/v0.1.0",
        "https://releases.example.invalid/owner/brain/releases/latest",
        "https://releases.example.invalid/v1;reboot",
        "https://releases.example.invalid/v1 --x",
        "releases.example.invalid/v0.1.0",
        "",
    ]
    page = "https://releases.example.invalid/owner/brain/releases"
    accepted = {
        f"{page}/tag/v0.1.0": f"{page}/download/v0.1.0",
        f"{page}/download/v0.1.0/install.sh": f"{page}/download/v0.1.0",
        "https://mirror.example.invalid/brain/v0.2.0/": "https://mirror.example.invalid/brain/v0.2.0",
    }
    by_address = call_functions(
        tmp_path,
        [*refused, *accepted],
        "$r = Get-BrainReleaseFiles $_; "
        "if ($null -ne $r) { @($r.Release, $r.ScriptUrl, $r.ArchiveUrl) }",
    )

    assert {one for one in refused if by_address[one] != ["REFUSED"]} == set()
    for given, folder in accepted.items():
        release = folder.rsplit("/", 1)[1]
        assert by_address[given] == [
            release,
            f"{folder}/install.sh",
            f"{folder}/{archive_name(release)}",
        ], given


@needs_powershell
def test_answers_that_are_never_usable_stop_the_helper_before_ssh_is_run(tmp_path: Path) -> None:
    """Five wrong answers to one question stop the helper, and a helper with nobody answering
    does not ask for ever. Nothing reaches SSH on the way.

    Delete this and a helper started with its input closed spins, and a person who cannot get
    an address right is asked the same question until they close the window."""
    done = run_helper(tmp_path, ["-oProxyCommand=calc"] * 5 + [""])

    assert done.code == 1
    assert done.calls == ()
    assert "No usable server address was given." in done.said


# ============================================================ what it leaves behind
@needs_powershell
def test_nothing_the_helper_writes_outlives_it_or_holds_a_secret(tmp_path: Path) -> None:
    """`THE_HELPER_NEVER_SEES_WHAT_THE_PERSON_SIGNS_IN_WITH` and
    `THE_SETUP_CODE_IS_POINTED_AT_AND_NEVER_READ`, measured. While SSH ran, the helper's folder
    held one file and it was a public key line; after the helper ended that folder is gone; and
    the setup code the stand-in printed reached the person's screen and no file anywhere under
    the test's folder.

    Delete this and a transcript, a saved answer or a left-behind folder can arrive in a later
    edit, and every other test here stays green."""
    done = run_helper(tmp_path, HAPPY)

    assert done.code == 0, done.said
    assert [call["files"] for call in done.calls] == [[], ["brain-known-hosts"]]
    assert re.fullmatch(r"\S+ ssh-ed25519 [A-Za-z0-9+/=]+\n", done.calls[1]["known_hosts"])
    folder = Path(done.calls[0]["cwd"])
    assert folder.resolve().is_relative_to(done.temp.resolve()), "not the temporary folder"
    assert not folder.exists(), "the helper left its folder behind"
    assert SENTINEL_CODE in done.said, "the code never reached the person"
    written = [
        one
        for one in tmp_path.rglob("*")
        if one.is_file() and SENTINEL_CODE in one.read_text(encoding="utf-8", errors="ignore")
    ]
    assert written == []


@needs_powershell
def test_an_install_that_fails_on_the_server_says_so_and_cleans_up(tmp_path: Path) -> None:
    """The failing half of the install call: the helper reports the stop in words, exits with
    its own failure code and still removes its folder.

    Delete this and a failed install can print the finished message, which sends a person to a
    setup screen on a server that has nothing running."""
    done = run_helper(tmp_path, HAPPY, env={"BRAIN_STUB_INSTALL_EXIT": "1"})

    assert done.code == 2
    assert "The install stopped before it finished." in done.said
    assert "The install finished." not in done.said
    assert not Path(done.calls[0]["cwd"]).exists(), "the helper left its folder behind"


@needs_powershell
def test_the_helper_runs_whole_in_constrained_language_mode(tmp_path: Path) -> None:
    """`AN_UNSIGNED_SCRIPT_RUNS_CONSTRAINED`. The whole happy path, in the language mode Windows
    gives an unsigned script under an enforcing policy, ending in the same command.

    Delete this and a .NET call can be added that works on a developer's machine and fails with
    a message about a language mode on the machine this helper exists for."""
    done = run_helper(tmp_path, HAPPY, constrained=True)

    assert done.code == 0, done.said
    assert done.calls[-1]["argv"][-1] == EXPECTED_COMMAND


# ============================================================ the files themselves
def test_the_sizes_the_helper_offers_are_the_installers_profiles() -> None:
    """Read out of the script. A profile added to the installer and not to the helper is a size
    nobody using the helper can choose; one removed is a size the installer refuses at the end.

    Delete this and the two lists agree until somebody edits one of them."""
    declared = re.search(r"^\$BrainSizes = @\(([^)]*)\)", SCRIPT.read_text(encoding="utf-8"), re.M)

    assert declared is not None
    assert tuple(re.findall(r"'([a-z]+)'", declared.group(1))) == PROFILES


def test_the_launcher_starts_the_helper_beside_it_and_does_nothing_else() -> None:
    """The file a person double-clicks. It starts Windows PowerShell on the script in its own
    folder, for this run only, and has no other command in it.

    Delete this and the launcher can grow a second command, or start a script by a path that
    only exists on the machine it was written on."""
    commands = [
        one.strip()
        for one in LAUNCHER.read_text(encoding="ascii").splitlines()
        if one.strip() and not one.strip().lower().startswith(("rem ", "@echo off"))
    ]

    assert commands == [
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0'
        f'{Path(HELPER_SCRIPT_PATH).name}"'
    ]


def test_the_helper_files_are_plain_ascii_with_no_dashes_a_console_mangles() -> None:
    """Windows PowerShell 5.1 reads a script with no byte-order mark in the system code page,
    so any character outside ASCII arrives as something else. Plain ASCII has no such question.

    Delete this and a typographic quote pasted into a message turns into two characters of
    nonsense on the screen of the person this is for."""
    for one in (SCRIPT, LAUNCHER):
        assert one.read_bytes().isascii(), one


def test_the_release_carries_the_helper_and_publishes_it_beside_the_archive() -> None:
    """How a person gets it. The archive carries both files by the rule that carries
    `install.sh`, and the publish step finds both in the declared file list and attaches them,
    the same way it attaches the installer, because the helper is needed before the archive.

    Delete this and the helper is in the repository and on no release page."""
    publish = str(
        next(
            one
            for one in yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["archive"][
                "steps"
            ]
            if "gh release create" in str(one)
        )["run"]
    )

    assert included_by(HELPER_SCRIPT_PATH) and included_by(HELPER_LAUNCHER_PATH)
    assert r"install-from-windows\.(ps1|cmd)$" in publish
    assert '"$RUNNER_TEMP/files.txt"' in publish
    assert publish.index("install-from-windows") < publish.index("gh release create")


def test_the_guide_for_the_helper_names_its_files_and_every_size() -> None:
    """The page a person reads. Held to the file names they download and the sizes the helper
    asks them to choose between, which are the two facts a page like this goes stale on.

    Delete this and the guide can tell a person to double-click a file the release no longer
    carries."""
    text = GUIDE.read_text(encoding="utf-8")

    assert Path(HELPER_LAUNCHER_PATH).name in text
    assert Path(HELPER_SCRIPT_PATH).name in text
    assert all(f"`{one}`" in text for one in PROFILES)
