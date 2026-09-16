"""The install for somebody who does not use a terminal: a script they double-click on Windows.

`ops/install/install.sh` is one command, and one command is still a terminal, an SSH client, a
`sudo` and a line of shell typed without a mistake. The person most likely to be installing
this for a company of forty is the person who does not do that. So the release carries a
helper for a Windows computer, `ops/install/windows/install-from-windows.ps1`, and a launcher
beside it that a person double-clicks. It asks five questions in plain words, shows who the
server says it is and asks the person to confirm that, and then runs **the same install
command `docs/install/install.md` documents**, over the SSH client Windows already has. This
module holds that command, so the guide, the helper and the tests have one answer to what it
is. See `THE_HELPER_RUNS_THE_DOCUMENTED_COMMAND_AND_NO_OTHER`.

**A PowerShell script and a one-line launcher, rather than a program, and the reason is
measured on the owner's own machine.** Windows Smart App Control refuses an unsigned
executable it is asked to start, and it has refused four of them in this repository already
(CLAUDE.md, "Before you say something is done"). A helper compiled to an `.exe` would be the
fifth, on the machine of the person least able to work out why. `powershell.exe` is signed
and present on every Windows 10 and 11, and so is `ssh.exe` in `System32\\OpenSSH`. The
script is also something a careful person can open in Notepad and read before running, which
an executable is not. Rejected: a Python script, which needs an interpreter nobody on this
path has installed; and an installer package, which is the unsigned executable again.

**The script is written to run in Constrained Language Mode**, which is what Windows runs an
unsigned script in when an application control policy is enforcing scripts. So it calls
cmdlets and the SSH tools and no .NET type outside the short list that mode allows, and
`tests/unit/test_windows_helper.py` runs the whole of it in that mode as well as in the full
one. See `AN_UNSIGNED_SCRIPT_RUNS_CONSTRAINED`.

**Who the server is, confirmed by the person and then enforced.** The first connection asks
the server for its identity and offers it nothing: every authentication method is switched
off, so no key and no password reaches a machine nobody has confirmed. The identity it
presents is written to a file in a temporary folder, its fingerprint is shown in the words a
hosting company uses, and only a typed `yes` goes on. The install connection then accepts
**that key and no other**, with strict checking against that file alone, so a machine that
answered the first connection and not the second is refused by SSH rather than trusted. See
`THE_KEY_THE_PERSON_CONFIRMED_IS_THE_ONLY_KEY_ACCEPTED` and
`NOTHING_IS_OFFERED_TO_A_SERVER_NOBODY_HAS_CONFIRMED`.

**`ssh-keyscan` was the obvious way to ask and it does not work on Windows.** Measured on
2026-09-17: the `ssh-keyscan.exe` that ships with Windows 11 (OpenSSH_for_Windows_9.5p2,
LibreSSL) offers a key exchange its own build cannot complete and fails with
`choose_kex: unsupported KEX method sntrup761x25519-sha512@openssh.com` against any server that
also offers it, which is every current OpenSSH. `ssh.exe` from the same folder completes the
exchange. So the identity is asked of `ssh.exe` itself, with `StrictHostKeyChecking=accept-new`
writing what the server presented into the helper's own file, and read back with
`ssh-keygen -l`, which is the fingerprint in exactly the form SSH prints elsewhere.

**The file is named relative to a folder the helper changes into, and that is not a style.**
A known-hosts path given to `-o` is split on spaces by SSH's own option parser, and a Windows
temporary folder sits under the user's name, which may have a space in it. Quoting it inside
the option is spelled differently by Windows PowerShell 5.1 and by PowerShell 7, so a quoted
path works on one and breaks on the other. A bare file name inside the current folder has no
space to quote. Measured the same day against a folder whose name has one.

**Nothing is written that holds a secret, and nothing is left behind.** The one file is the
server's public key, in a folder removed before the script ends, whether it ends well or not.
No password is asked for: when the server wants one, `ssh.exe` asks for it itself, on the
console, and the helper never sees it. No transcript is started. See
`THE_HELPER_NEVER_SEES_WHAT_THE_PERSON_SIGNS_IN_WITH`.

**The setup code is shown by the installer, on the helper's own window, and never read by the
helper.** The installer's last step prints it, and the SSH session writes that straight to the
console. Capturing the session so the helper could print the code again, in a box, was the
friendlier design and it was rejected on what it breaks: Windows PowerShell reads a program's
captured output a line at a time, and `sudo`'s password prompt does not end in a line break,
so a captured install would sit silently at a prompt nobody could see. It would also put the
one credential the installer prints into a variable of a script. So the helper points at the
line rather than repeating it. See `THE_SETUP_CODE_IS_POINTED_AT_AND_NEVER_READ`.

**A release is fetched over https and nothing else.** The command runs a script as root that
it has just downloaded, so a release address anybody on the network path could rewrite is a
root shell for whoever sits on that path. The helper refuses an `http` address rather than
warning about one. See `A_RELEASE_OVER_PLAIN_HTTP_IS_A_ROOT_SHELL_FOR_THE_NETWORK`.

**Every answer is refused unless it is made of characters that cannot change the command.**
The server address becomes an argument to `ssh.exe` and the release address becomes part of a
line a shell runs as root, so an address beginning with a dash is an SSH option
(`-oProxyCommand=...` runs a program on the person's own computer) and an address carrying a
quote, a space or a semicolon is a second command. The helper checks shape rather than
escaping, because an answer with no quoting to get wrong has no quoting to get wrong in two
versions of PowerShell. See `AN_ANSWER_IS_A_SHAPE_OR_IT_IS_REFUSED`.

**How the person gets it.** The release workflow publishes both files beside the archive and
`install.sh`, found in the file list `brain.deployment.release` already produces, and the
archive carries them under `ops/install/windows/` for the reason it carries `install.sh`: the
copy inside is the record of what was run. The person downloads both from the release page
into one folder and double-clicks the launcher; `docs/install/windows.md` is that, in numbered
steps. The release address the helper asks for is that same page, so a person holding the
helper is already holding the answer to its hardest question.

**What has never happened.** No release has been published, so no person has downloaded this
from one, and the helper has never installed anything on a server. What is tested is that it
refuses what it must refuse, asks SSH for exactly what is described above in exactly that
order, runs exactly the documented command, and writes nothing that outlives it, against a
stand-in for SSH, in both PowerShell language modes.

Task ids: M42.6.6
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Final

from brain.deployment.install_script import RELEASE_URL_VARIABLE, SCRIPT_PATH

# ------------------------------------------------------------------ written-down reasons
#: Why the helper has no command of its own.
THE_HELPER_RUNS_THE_DOCUMENTED_COMMAND_AND_NO_OTHER: Final = (
    "A helper that ran its own variant of the install would be a second install path, and the "
    "one nobody reading the guide can check. It runs the guide's command, minus the step where "
    "a person reads the script first, and the test holds the command it hands to SSH equal to "
    "the one this module builds and the guide's code block equal to it too."
)

#: Why the install connection is strict against one file.
THE_KEY_THE_PERSON_CONFIRMED_IS_THE_ONLY_KEY_ACCEPTED: Final = (
    "Showing a fingerprint and then connecting with SSH's ordinary checking would confirm one "
    "machine and trust whichever answers next. The install connection checks strictly against "
    "the file holding the key that was shown, for the user and the global list both, so a "
    "different key is refused by SSH itself and the person's own list is never consulted."
)

#: Why the first connection offers nothing.
NOTHING_IS_OFFERED_TO_A_SERVER_NOBODY_HAS_CONFIRMED: Final = (
    "The first connection exists to learn who the server is. A key offered or a password typed "
    "there goes to a machine the person has not yet agreed is theirs, so every authentication "
    "method is off and the connection ends at the refusal, having learned the identity and "
    "given nothing."
)

#: Why an unsigned script avoids .NET types.
AN_UNSIGNED_SCRIPT_RUNS_CONSTRAINED: Final = (
    "Where Windows enforces an application control policy on scripts, an unsigned script runs "
    "in Constrained Language Mode, which refuses most .NET types. A helper that hashed a key "
    "with a cryptography class would fail there with a message about a language mode, on the "
    "machine of somebody who does not know what one is."
)

#: Why the helper never holds a password.
THE_HELPER_NEVER_SEES_WHAT_THE_PERSON_SIGNS_IN_WITH: Final = (
    "SSH asks for a password on the console itself when a server wants one, and sudo asks on "
    "the server's own terminal. A helper that asked instead would hold the value in a variable "
    "and hand it to a program, which is two places for it to leak and a feature nobody needs."
)

#: Why the setup code is not repeated by the helper.
THE_SETUP_CODE_IS_POINTED_AT_AND_NEVER_READ: Final = (
    "The installer prints the setup code to the session and the session writes to the console. "
    "Capturing it to print it again would leave a sudo password prompt, which ends in no line "
    "break, invisible behind Windows PowerShell's line buffering, and would put the code in a "
    "script variable. So the helper tells the person which line to copy."
)

#: Why http is refused rather than warned about.
A_RELEASE_OVER_PLAIN_HTTP_IS_A_ROOT_SHELL_FOR_THE_NETWORK: Final = (
    "The command fetches a script and runs it as root. Over http anybody on the network path "
    "can replace the script or the archive, and a warning the person clicks past is that "
    "replacement with their consent."
)

#: Why answers are checked for shape rather than escaped.
AN_ANSWER_IS_A_SHAPE_OR_IT_IS_REFUSED: Final = (
    "The server address becomes an SSH argument and the release address becomes part of a "
    "line run as root. An address beginning with a dash is an option, and one with a quote, a "
    "space or a semicolon is a second command. Refusing every character that could change the "
    "command leaves no quoting to get wrong, in either version of PowerShell."
)

# --------------------------------------------------------------------- the figures
#: Where the helper lives, relative to the repository root. Under `ops/install` so the archive
#: carries it by the rule that already carries `install.sh`.
HELPER_SCRIPT_PATH: Final = "ops/install/windows/install-from-windows.ps1"

#: The file a person double-clicks. It does nothing but start the script beside it.
HELPER_LAUNCHER_PATH: Final = "ops/install/windows/install-from-windows.cmd"

#: The guide for the helper, written for somebody who does not use a terminal.
HELPER_GUIDE_PATH: Final = "docs/install/windows.md"

#: The installer's name on the server and in the release, which is the committed script's.
SCRIPT_NAME: Final = PurePosixPath(SCRIPT_PATH).name

#: What the release workflow calls the archive of one tag. `.github/workflows/release.yml` builds
#: `brain-$TAG.tar.gz`, and the test holds the two equal.
ARCHIVE_NAME: Final = "brain-{release}.tar.gz"

#: The two lines of the documented command the helper runs, in order. The guide's third line,
#: reading the script, is the one a person who does not use a terminal cannot do.
FETCH_LINE: Final = "curl -fsSL {script_url} -o " + SCRIPT_NAME
RUN_LINE: Final = (
    "sudo " + RELEASE_URL_VARIABLE + "={archive_url} bash " + SCRIPT_NAME + " "
    "--release {release} --profile {profile}"
)

#: The flag the console address is passed with, when there is one.
CONSOLE_ADDRESS_FLAG: Final = "--console-address"

#: How the two lines are joined into the one line SSH runs: the second only if the first worked.
JOINED_BY: Final = " && "


def archive_name(release: str) -> str:
    """The archive of one release, as the release workflow names it."""
    return ARCHIVE_NAME.format(release=release)


def install_lines(
    *, script_url: str, archive_url: str, release: str, profile: str, console_address: str = ""
) -> tuple[str, str]:
    """The documented install command, as the two lines the helper runs.

    Nothing is quoted, and that is the helper's refusal doing the work rather than an
    oversight: every value that reaches here has been checked for a shape that cannot change
    the line. See `AN_ANSWER_IS_A_SHAPE_OR_IT_IS_REFUSED`.
    """
    run = RUN_LINE.format(archive_url=archive_url, release=release, profile=profile)
    if console_address:
        run = f"{run} {CONSOLE_ADDRESS_FLAG} {console_address}"
    return FETCH_LINE.format(script_url=script_url), run


def remote_command(
    *, script_url: str, archive_url: str, release: str, profile: str, console_address: str = ""
) -> str:
    """The one line the helper hands to SSH to run on the server."""
    return JOINED_BY.join(
        install_lines(
            script_url=script_url,
            archive_url=archive_url,
            release=release,
            profile=profile,
            console_address=console_address,
        )
    )
