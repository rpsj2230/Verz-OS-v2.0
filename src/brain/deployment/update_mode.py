"""How an install updates: it stays on a release somebody chose, or it follows every release.

The install checks ask whether the image an install runs is "one published image at a named
release", and for a client's production that is exactly right: an install that follows `latest`
changes what it runs whenever somebody publishes, with nobody having decided anything. The
owner's own staging install is the opposite on purpose. Its auto-deploy watches the newest image
so that every release reaches it at once, which is the whole use of a staging server, and on
2026-10-14 the check reported that as a fault on every run.

**So whether an install is meant to follow every release is a fact about the install, and the
install has to be able to say it.** Two places could have absorbed it and both are wrong. A check
that excused `latest` everywhere would be green on the client production install pinned to
`latest` by accident, which is the exact fault the check exists to find, and the one nobody
would then be told about. A branch for the staging install would be a branch for one company,
which this repository does not have. A setting is the third way, and it is the one that is the
same on a server belonging to a company nobody here has met: `INSTALL_UPDATE_MODE`, with two
values.

- `release` is the default and is what every install ships as: it stays on a release tag
  somebody chose, the update script refuses `latest`, and the install checks hold it to that.
- `continuous` follows every release by choice, as staging does. It is for an install whose
  owner wants each published release without deciding about it, and it is never the default,
  because the default has to be the one a client's production wants.

**The default is `release` and so is anything unrecognised.** An install that has never said
anything, or whose environment file holds a word that is neither, keeps the strict behaviour,
because the other direction turns a typo into a silent permission to run whatever was pushed
last. The Settings screen refuses any other word before it is saved (`update_mode_problem`), so
only a hand edit of the environment file reaches here with one.

**Continuous mode excuses one question and no other.** What is not asked is "is the image at a
named release", and the checks report that as not run with the reason, rather than passing it,
so the page never shows a tick for a pin that is not there. Everything else about the image is
still held: the Updates screen still names the built commit, and the release list is still read
when the check for newer releases is on.

Rejected: a single boolean such as `INSTALL_PIN_RELEASE`. A boolean cannot say what the install
does instead of pinning, and the sentence on the Updates screen and on the check's page has to
say it. Two words an owner can read are the interface.

Rejected: reading the answer from the image's own tag, which would make an install that is
accidentally on `latest` indistinguishable from one that chose it, and that difference is the
only reason the setting exists.

Task ids: M42.1.3, M42.1.4, M42.3.9
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final

from brain.install import InstallError, value_of

#: The installation setting naming how this install updates.
UPDATE_MODE_SETTING: Final = "INSTALL_UPDATE_MODE"


class UpdateMode(enum.StrEnum):
    """How this install updates. The setting's two words."""

    #: Stays on a release tag somebody chose. The default, and what a client's production wants.
    RELEASE = "release"
    #: Follows every release the moment it is published, by choice, as a staging server does.
    CONTINUOUS = "continuous"


#: Why continuous is never the default and why a stray word reads as release.
A_STRAY_WORD_MUST_NOT_BECOME_PERMISSION_TO_RUN_WHATEVER_WAS_PUSHED_LAST: Final = (
    "An install that follows every release changes what it runs whenever somebody publishes, so "
    "it is something an owner chooses and never something a typo reaches. Anything that is not "
    "exactly the word for it keeps the install on a release it names, which is what an install "
    "did before the setting existed and what every client's production wants."
)

#: What the Updates screen says about the running release on an install that follows every one.
THIS_INSTALL_FOLLOWS_EVERY_RELEASE_BY_CHOICE: Final = (
    "this install is set to follow every release, so it runs the newest image whatever its tag "
    "and names no release of its own; the commit below is what is running. Setting how this "
    "install updates to release, on Install, Settings, makes it stay on a release tag you choose"
)

#: What an install that follows every release is told to do about being behind.
AN_INSTALL_THAT_FOLLOWS_EVERY_RELEASE_IS_NEVER_BEHIND_BY_CHOICE: Final = (
    "This install follows every release by choice, so it takes each one as it is published and "
    "has no release of its own to compare a newer one against. The reason is shown below."
)

#: What to do on an install that follows every release.
NOTHING_PINS_THIS_INSTALL_AND_THE_BUILT_COMMIT_SAYS_WHAT_RUNS: Final = (
    "Nothing to pin: to see what is running, read the built commit below. To stay on a release "
    "you choose instead, set how this install updates to release on Install, Settings, then run "
    "the update script with that release's tag."
)


def update_mode(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> UpdateMode:
    """This install's answer; the release mode for a value that is neither word. See the note."""
    try:
        word = value_of(UPDATE_MODE_SETTING, env, saved).strip().casefold()
    except InstallError:
        return UpdateMode.RELEASE
    known = {one.value: one for one in UpdateMode}
    return known.get(word, UpdateMode.RELEASE)


def follows_every_release(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> bool:
    """Whether this install is set to take every release as it is published.

    The one question the Updates screen and the install checks ask, so none of them can answer it
    differently.
    """
    return update_mode(env, saved) is UpdateMode.CONTINUOUS


def update_mode_problem(value: str) -> str:
    """What is wrong with a value somebody typed for how this install updates, or empty."""
    if value.strip().casefold() in {one.value for one in UpdateMode}:
        return ""
    return (
        f"Choose {UpdateMode.RELEASE.value}, to stay on a release you choose, or "
        f"{UpdateMode.CONTINUOUS.value}, to follow every release."
    )
