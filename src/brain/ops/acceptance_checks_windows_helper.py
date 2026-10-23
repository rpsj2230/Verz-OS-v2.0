"""The install acceptance checks for the Windows install helper, as far as a worker can see it.

`brain.deployment.windows_helper` holds the command the helper runs, and `ops/install/windows/`
holds the two files a person double-clicks. Their tests start PowerShell against a stand-in for SSH
and are the evidence for how the helper behaves; nothing here repeats that, and **nothing here
starts the helper**, because a worker is a Linux container with no PowerShell and no Windows
computer in front of it. What a worker can show is the two things a release can get wrong without
any test of the helper noticing: the guides drifting from the command, and the shipped files
drifting from what the guides promise.

**Two checks, because the image carries one half and not the other.** The worker's image carries
`docs/` and the module, and not `ops/install/`, as `brain.ops.acceptance_checks_install_template`
says of the installer. So the first check holds the command the helper builds to the one command
`docs/install/install.md` documents and to the installer's own flags, and holds the helper's guide
to the sizes the installer offers and to the file names the helper ships under. It runs on every
install. The second reads the shipped files themselves, and is not run where they are not in the
image: it is the check that the helper asks the five questions and the launcher starts nothing
else. See `THE_SHIPPED_FILES_ARE_NOT_IN_THE_IMAGE`.

**What is not shown, and what a person does.** The double-click run on a Windows computer against a
real server has never happened in this repository (`brain.deployment.windows_helper`, "What has
never happened"), and these checks do not change that. The person-run step is in
`docs/install/windows.md`: download the two files from the release page, double-click the launcher,
answer five questions and confirm the fingerprint.

Task ids: M42.6.6
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1815

# ------------------------------------------------------------------ written-down reasons
#: Why the second check is not run in the worker's image.
THE_SHIPPED_FILES_ARE_NOT_IN_THE_IMAGE: Final = (
    "The helper's two files are published beside the release archive and carried in the archive "
    "under ops/install, and the image a worker runs in carries docs and the modules but not that "
    "folder. A check that needed them in the image would be a check nobody could run without "
    "changing the Dockerfile, so it steps aside where they are not there and is run from a clone."
)

#: Said when the install guides are not in the image.
NO_GUIDES_HERE: Final = (
    "the image running this check carries no install guides, so the helper's command cannot be "
    "held against the guide here"
)

#: Said when the helper's files are not in the image.
NO_HELPER_FILES_HERE: Final = (
    "the image running this check does not carry the helper's two files, which are published "
    "beside the release and not shipped inside the application, so they cannot be read here"
)

# ------------------------------------------------------------------------ the figures
#: The five things the helper asks, in the order it asks them, as the script prompts them.
FIVE_QUESTIONS: Final = ("Address", "User name", "Release page", "Size", "Web address")


# ------------------------------------------------------------------------ the helpers
def _repository_file(relative: str) -> Path:
    """Where a file the release ships sits when this process runs from a clone."""
    from brain.deployment.release import REPO

    return REPO / relative


# ------------------------------------------------ 1. the command, the guide, the sizes
@check(
    leaves=("M42.6.6",),
    sentence=(
        "The install command the Windows helper runs on the server is the one command the install "
        "guide documents and speaks only flags the installer declares; the helper's guide names "
        "both of its files and every size the installer offers; and its launcher and script are "
        "published under the names the guide gives."
    ),
)
async def the_windows_helper_runs_the_documented_command_and_is_guided(
    h: Harness,
) -> None:
    from brain.deployment.install_script import FLAGS, RELEASE_URL_VARIABLE
    from brain.deployment.release import included_by
    from brain.deployment.windows_helper import (
        HELPER_GUIDE_PATH,
        HELPER_LAUNCHER_PATH,
        HELPER_SCRIPT_PATH,
        install_lines,
        remote_command,
    )
    from brain.docs_routes import DOCS
    from brain.ops.wiring import PROFILES

    install_guide = DOCS / "install" / "install.md"
    helper_guide = DOCS / "install" / Path(HELPER_GUIDE_PATH).name
    if not install_guide.is_file() or not helper_guide.is_file():
        raise CheckNotRunError(NO_GUIDES_HERE)

    # The guide's one command, with the step a person who uses no terminal cannot take removed, is
    # what the helper builds from the same placeholders.
    block = re.search(
        r"## Run this one command\s+```\n(.*?)```", install_guide.read_text(encoding="utf-8"), re.S
    )
    if block is None:
        raise CheckFailedError("the install guide no longer has the one command the helper runs")
    lines = [one.strip() for one in block.group(1).replace("\\\n", " ").splitlines()]
    shown = tuple(re.sub(r"\s+", " ", one) for one in lines if one and not one.startswith("less "))
    built = install_lines(
        script_url="<where install.sh is published for your release>",
        archive_url="<where the release archive is>",
        release="<tag>",
        profile="lite",
        console_address="https://brain.example.invalid",
    )
    if shown != built:
        raise CheckFailedError("the helper builds a command that is not the install guide's")

    # The flags are the installer's own, written out here and not read back from the helper.
    line = remote_command(
        script_url="https://releases.example.invalid/install.sh",
        archive_url="https://releases.example.invalid/brain.tar.gz",
        release="v1",
        profile="lite",
        console_address="https://brain.example.invalid",
    )
    declared = {flag for flag, _ in FLAGS}
    used = set(re.findall(r"(?<=\s)--[a-z-]+", line))
    if not used <= declared or not {"--release", "--profile", "--console-address"} <= used:
        raise CheckFailedError("the helper's command uses a flag the installer does not declare")
    if (
        "sudo " + RELEASE_URL_VARIABLE + "=https://releases.example.invalid/brain.tar.gz"
        not in line
    ):
        raise CheckFailedError(
            "the helper's command does not name the release by the installer's own variable"
        )

    # The page a person reads names what they download and every size they will be asked to pick.
    text = helper_guide.read_text(encoding="utf-8")
    if Path(HELPER_LAUNCHER_PATH).name not in text or Path(HELPER_SCRIPT_PATH).name not in text:
        raise CheckFailedError("the helper's guide does not name both files a person downloads")
    if not all(f"`{one}`" in text for one in PROFILES):
        raise CheckFailedError("the helper's guide does not name every size the installer offers")
    if not (included_by(HELPER_SCRIPT_PATH) and included_by(HELPER_LAUNCHER_PATH)):
        raise CheckFailedError("a file the helper needs is not one the release archive carries")


# ------------------------------------------------ 2. the shipped files
@check(
    leaves=("M42.6.6",),
    sentence=(
        "The Windows helper's script asks its five questions in order and offers the installer's "
        "sizes, its launcher starts that script and nothing else, and both files are plain ASCII "
        "a console cannot mangle; where the files are not in the image, it is not run."
    ),
)
async def the_shipped_helper_asks_five_questions_and_starts_only_itself(
    h: Harness,
) -> None:
    from brain.deployment.windows_helper import HELPER_LAUNCHER_PATH, HELPER_SCRIPT_PATH
    from brain.ops.wiring import PROFILES

    script, launcher = _repository_file(HELPER_SCRIPT_PATH), _repository_file(HELPER_LAUNCHER_PATH)
    if not script.is_file() or not launcher.is_file():
        raise CheckNotRunError(NO_HELPER_FILES_HERE)
    if not (script.read_bytes().isascii() and launcher.read_bytes().isascii()):
        raise CheckFailedError("a helper file holds a character a console can mangle")
    source = script.read_text(encoding="ascii")

    # The five questions are the first five a person is asked, and the script says five.
    asked = re.findall(r"Read-BrainAnswer '\s+([A-Za-z ]+)'", source)
    if tuple(asked[: len(FIVE_QUESTIONS)]) != FIVE_QUESTIONS:
        raise CheckFailedError("the helper does not ask its five questions in the order it says")
    if "five questions" not in source:
        raise CheckFailedError("the helper does not tell the person it asks five questions")
    sizes = re.search(r"^\$BrainSizes = @\(([^)]*)\)", source, re.M)
    if sizes is None or tuple(re.findall(r"'([a-z]+)'", sizes.group(1))) != PROFILES:
        raise CheckFailedError("the sizes the helper offers are not the installer's profiles")

    # The launcher does one thing, and it is start the script beside it.
    commands = [
        one.strip()
        for one in launcher.read_text(encoding="ascii").splitlines()
        if one.strip() and not one.strip().lower().startswith(("rem ", "@echo off"))
    ]
    if commands != [
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0'
        f'{Path(HELPER_SCRIPT_PATH).name}"'
    ]:
        raise CheckFailedError("the launcher does something other than start the script beside it")
