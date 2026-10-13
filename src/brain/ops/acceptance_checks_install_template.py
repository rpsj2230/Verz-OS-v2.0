"""The install acceptance checks for the client deployment template: the installer, the guides, the
release pin, the update scripts and the version screen, read from the image this install runs.

**These read what the release carries, and what the install is pinned to.** The installer is a
plan (`brain.deployment.installer.PLAN`) rendered into a script, so the plan in the running image
is the script every install made from this release ran; the guides are `docs/install` in that
image, served at `/build`; the pin is the `APP_IMAGE` the compose files hand the container. None of
these needs a database, so the checks take the harness only because the registry gives it, and none
of them writes anything.

**Where a file is not in the image, the check says it was not run.** The worker's image carries
`docs/` and not `ops/install/`, so the shipped script is judged by the plan and the renderer it
comes from, which is what `release.yml` publishes, and not by a copy of the file.

**The refusal of `latest` is run, not read.** The update script's first step is a shell test, and a
test that cannot fail is the failure this repository keeps meeting. The check runs it twice in a
shell, with `latest` and with a tag, and requires the first to be refused and the second admitted.

Rejected: reading `.env` on the host. The worker does not mount it, and an install check that needs
a second mount is an install that cannot be checked until somebody changes its compose file.

Task ids: M42.1.2, M42.1.3, M42.1.4, M42.2.3, M42.2.8, M42.3.1, M42.3.6
Task ids: M42.3.9, M42.5.1, M42.5.2, M42.5.15
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Final

import structlog

from brain.deployment.installer import PLAN
from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1810

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Said when the guides are not in the image this check runs in.
NO_GUIDES_HERE: Final = (
    "the image running this check carries no install guides, so the written install cannot be "
    "held against the installer's plan here"
)

#: Said when the container was not told which image it runs.
NOT_TOLD_ITS_IMAGE: Final = (
    "the application was not handed the image reference it was started with, so there is no pin "
    "to read; the compose files hand it over, and a deployment that predates that line does not"
)

#: Said when this install is on a build and not a release.
PINNED_TO_A_BUILD: Final = (
    "this install runs an image named by a build and not by a release tag, which the installer "
    "never produces; re-pin it to a published release with the update script"
)

#: Said where no shell is installed to run the refusal in.
NO_SHELL_HERE: Final = "this image has no shell to run the update script's first step in"

#: The names the installer's plan must hold, one for each of the things its first leaf lists.
WHAT_THE_INSTALLER_DOES: Final = (
    ("check the machine", "checks the machine"),
    ("download and unpack the release", "downloads the release"),
    ("mint this installation's secrets", "generates its own secrets"),
    ("start the secrets vault", "starts the vault"),
    ("pull the images this profile runs", "pulls the images"),
    ("start the database and wait for it", "builds the database"),
    ("start everything else", "starts the application"),
    ("wait for the application to report ready", "waits until it is ready"),
    ("furnish the install", "furnishes it"),
    ("present the setup code, once", "hands over the setup code once"),
)

#: The two steps that put a value in front of the person installing, once: the vault's recovery
#: key and the setup code.
PRESENTS_A_VALUE_ONCE: Final = (
    "initialise the secrets vault and keep its recovery key",
    "present the setup code, once",
)

#: The secrets the installer mints on the client's own server.
MINTED_ON_THE_SERVER: Final = ("POSTGRES_PASSWORD", "APP_ROLE_PASSWORD", "BRAIN_SETUP_SECRET")


def _guides() -> Path:
    from brain.docs_routes import DOCS

    return DOCS / "install"


@check(
    leaves=("M42.3.1", "M42.5.1", "M42.5.15"),
    sentence=(
        "Every step of the installer this release carries that writes something says when it is "
        "already done, every step says what to do when it fails, none puts a value where it can "
        "be read except the one that presents the setup code, and the plan holds a step for each "
        "thing the one command is meant to do."
    ),
)
async def the_installer_steps_say_when_done_and_what_to_do_on_failure(h: Harness) -> None:
    del h
    if not PLAN:
        raise CheckFailedError("this release carries no installer plan")
    for step in PLAN:
        if step.changes and not step.already_done.strip():
            raise CheckFailedError("an installer step that writes cannot say it is already done")
        if not step.changes and step.already_done.strip():
            raise CheckFailedError("an installer step that writes nothing carries a done test")
        if not step.on_failure.strip():
            raise CheckFailedError("an installer step does not say what to do when it fails")
        if step.presents_once and step.name not in PRESENTS_A_VALUE_ONCE:
            raise CheckFailedError("a step other than the setup code presents a value")
    names = [one.name for one in PLAN]
    if len(set(names)) != len(names):
        raise CheckFailedError("two installer steps share a name, so progress cannot name them")
    for name, _what in WHAT_THE_INSTALLER_DOES:
        if name not in names:
            raise CheckFailedError("the installer holds no step for something it is meant to do")


@check(
    leaves=("M42.1.2", "M42.5.2"),
    sentence=(
        "The installer mints the database password, the application role's password and the "
        "setup secret on the client's own server; and every credential this install's "
        "application holds is non-empty, long enough to have been generated, and not one value "
        "doing for two credentials."
    ),
)
async def every_secret_the_install_holds_was_minted_here_and_none_repeats(h: Harness) -> None:
    del h
    from brain.deployment.variables import unminted_secrets
    from brain.ops.install_docs import minted_variables
    from brain.settings import process_environment

    minted = minted_variables(PLAN)
    if any(one not in minted for one in MINTED_ON_THE_SERVER):
        raise CheckFailedError("the installer does not mint every secret it is meant to")
    from brain.deployment.app_environment import application_reads

    # Only what the application reads: the rest of a container's environment is somebody
    # else's variables, and a short token of the platform's is not this install's secret.
    environment = process_environment()
    names = {one for accepted in application_reads().values() for one in accepted}
    found = unminted_secrets(
        {name: environment[name] for name in sorted(names) if name in environment}
    )
    if found:
        # Names only, never values, to the worker's log; the result names nothing.
        log.warning("acceptance.secrets_not_minted", findings=list(found))
        raise CheckFailedError(
            "a credential this install holds is empty, short enough to be guessed or shared "
            "between two settings; the worker's log names which"
        )


@check(
    leaves=("M42.2.3", "M42.2.8"),
    sentence=(
        "The install guides this release serves are held to what the installer runs: the step "
        "table names every step in order, the checklist and the troubleshooting guide are "
        "complete, and the operations chapter agrees with the job registry and the queue's "
        "plan."
    ),
)
async def the_install_guides_are_held_to_the_installer_and_the_checklist(
    h: Harness,
) -> None:
    del h
    from brain.ops.install_docs import (
        checklist_gaps,
        mechanism_gaps,
        queue_step_gaps,
        step_gaps,
        troubleshooting_gaps,
    )

    where = _guides()

    def read(name: str) -> str:
        return (where / name).read_text(encoding="utf-8")

    if not where.is_dir():
        raise CheckNotRunError(NO_GUIDES_HERE)
    if step_gaps(read("install.md"), plan=PLAN):
        raise CheckFailedError("the install guide and the installer's plan disagree")
    if checklist_gaps(read("checklist.md")):
        raise CheckFailedError("the install checklist is not complete")
    if troubleshooting_gaps(read("troubleshooting.md")):
        raise CheckFailedError("an entry in the troubleshooting guide cannot be used")
    if mechanism_gaps(read("operations.md")) or queue_step_gaps(read("operations.md")):
        raise CheckFailedError("the operations chapter and what the install runs disagree")


@check(
    leaves=("M42.1.3", "M42.1.4"),
    sentence=(
        "The image this install runs is named by the product's repository and a release tag, "
        "never latest and never untagged, so the install holds one published image at a version "
        "somebody chose."
    ),
)
async def the_install_runs_one_published_image_at_a_named_release(h: Harness) -> None:
    from brain.console.version_view import image_tag, ordinal
    from brain.deployment.installer import PRODUCT_IMAGE

    pinned = h.settings.app_image.strip()
    if not pinned:
        raise CheckNotRunError(NOT_TOLD_ITS_IMAGE)
    tag = image_tag(pinned)
    if not tag or tag == "latest":
        raise CheckFailedError("this install is pinned to latest or to no tag at all")
    if not pinned.startswith(f"{PRODUCT_IMAGE}:"):
        raise CheckFailedError("this install runs an image that is not the product's published one")
    if ordinal(tag) is None:
        raise CheckNotRunError(PINNED_TO_A_BUILD)


async def _runs(script: str) -> int:
    shell = shutil.which("sh")
    if shell is None:
        raise CheckNotRunError(NO_SHELL_HERE)
    run = await asyncio.create_subprocess_exec(
        shell,
        "-c",
        script,
        env={"PATH": os.defpath},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await asyncio.wait_for(run.wait(), timeout=20)


@check(
    leaves=("M42.3.6",),
    sentence=(
        "The update script's first step refuses latest and admits a release tag, run in a shell; "
        "it records the release it replaces before anything changes, and the rollback script "
        "takes no tag, reads the recorded one and removes it only at its end."
    ),
)
async def the_update_refuses_latest_and_the_rollback_reads_the_previous(
    h: Harness,
) -> None:
    del h
    from brain.deployment.release import (
        NOT_A_RELEASE_TAG,
        PREVIOUS_MARKER,
        release_marker,
        rollback_plan,
        update_plan,
    )

    variable, _marker = release_marker(PLAN)
    update = update_plan(PLAN)
    refuses = update[0]
    functions = 'say() { printf "%s\\n" "$1"; }; fail() { printf "%s\\n" "$1" >&2; exit 1; }; '
    if await _runs(f'{functions}{variable}="{NOT_A_RELEASE_TAG}"; {refuses.run}') == 0:
        raise CheckFailedError("the update script's first step admitted latest")
    if await _runs(f'{functions}{variable}="v1.2.3"; {refuses.run}') != 0:
        raise CheckFailedError("the update script's first step refused a release tag")
    recorded = [one for one in update if PREVIOUS_MARKER in one.run]
    if not recorded or update.index(recorded[0]) > 2:
        raise CheckFailedError("the update does not record the release it replaces first")
    back = rollback_plan(PLAN)
    if (
        not any(PREVIOUS_MARKER in one.run for one in back[:-1])
        or PREVIOUS_MARKER not in back[-1].run
    ):
        raise CheckFailedError("the rollback does not read the recorded release and remove it last")


@check(
    leaves=("M42.3.9",),
    sentence=(
        "The Updates screen, opened by an administrator, names the running release or says why it "
        "cannot, names the commit, and answers whether a newer release exists in one of its nine "
        "stated ways, switched off included, and never with a bare tick."
    ),
)
async def the_updates_screen_names_the_version_and_whether_newer_exists(
    h: Harness,
) -> None:
    from brain.console.version_view import ANSWERS, SETTLED, Standing
    from brain.core.scope import Scope
    from brain.install_routes import updates
    from brain.ops.acceptance import RESERVED_DEPARTMENTS
    from brain.ops.acceptance_checks_company_views import _screens_over
    from brain.ops.acceptance_people_signed_in import console

    await h.found_departments()
    c = await console(h)
    reader = h.principal(RESERVED_DEPARTMENTS[0], "updates")
    await h.person(
        reader,
        department=RESERVED_DEPARTMENTS[0],
        grants=_screens_over(Scope.unrestricted(), "updates"),
    )
    asked = await c.asked(reader)
    with c.as_route():
        view = await updates(c.request(), asked)
    if not view.running.tag and not view.running.cannot_say:
        raise CheckFailedError("the screen neither names the running release nor says why not")
    if view.running.tag and view.running.cannot_say:
        raise CheckFailedError("the screen names a release and says it cannot, together")
    if view.standing not in {one.value for one in Standing}:
        raise CheckFailedError("the screen's answer about a newer release is not one of the nine")
    if not view.says.strip() or not view.what_to_do.strip():
        raise CheckFailedError("the screen's answer about a newer release says nothing")
    settled = {one.value for one in SETTLED}
    if view.standing in settled and (view.told is None or not view.running.tag):
        raise CheckFailedError("the screen shows a tick with nothing behind it")
    if set(ANSWERS) != set(Standing):
        raise CheckFailedError("a standing of the Updates screen has no sentence to say")
