"""Which release this install is on, and whether anything newer exists, without guessing either.

An install holds three statements about its own version and **no two of them answer the same
question**, which is why this is a module rather than a field. The release marker at
`INSTALL_HOME` says which tag was unpacked; `APP_IMAGE` says which image the containers were
selected by; and the manifest inside the image says which commit the running code was built
from. Only the third is measured by this process, and the third is a commit rather than a
release. See `THREE_STATEMENTS_AND_ONLY_ONE_OF_THEM_IS_MEASURED`.

**The release cannot be baked into the image, so it arrives the way the image was chosen.**
The deploy pipeline builds and signs one image per commit, and a release is that digest given a
second name later, so nothing inside an image can say which release it became. What does name
it is the reference the compose command selected the container by, and since 2026-09-16 the
compose files hand that same variable to the application's environment, where
`brain.settings.Settings.app_image` reads it. One compose evaluation sets both, so it is a
statement about this container rather than about a file beside the install. The marker is
deliberately not handed over: an update writes it before it recreates the containers, so it is
the one statement that is wrong about a running container while an update is part-way through.
See `A_RELEASE_TAG_IS_A_NAME_GIVEN_AFTER_THE_BUILD`.

**Two of them can disagree and neither is wrong.** An update writes the marker before it
recreates anything, so for as long as that takes, and for ever if it stops part-way, the marker
names one release and the containers run another. A screen picking one of the two would be
reporting a version that is true of a file and not of the containers, on exactly the install
somebody is looking at because an update went wrong. So this **names no release at all** when
two statements it was handed do not agree, and says which two they are and what each one means.
See `SHOWING_ONE_OF_TWO_VERSION_FACTS_THAT_DISAGREE_IS_A_SCREEN_THAT_LIES_QUIETLY`.

**Nothing here asks anything outside this install whether a newer release exists, and the
asking is switched off until an install switches it on.** This product is single-tenant,
installed on a client's own server and owned outright, and a check that runs by default is an
outbound connection nobody agreed to: it discloses that this product is installed at that
address, when that server is up, how often somebody administers it, and, if the check sends the
running version so the answer can be narrower, which installs are behind. That last one is a
list of who is unpatched, held by somebody who does not operate the install.
`WHAT_A_RELEASE_CHECK_WOULD_SEND` is that cost written down item by item, and
`release_check_cost` is it as a check rather than as a sentence in a commit message nobody
re-reads: it is what an install agrees to by switching the check on.

`brain.deployment.release_feed` does the asking, in the background of whichever request opens
the screen, and produces either a `Told` or an `Unanswered`. The asking lives there and not
here, so this module still reaches nothing. What this module has to be able to say is every way
of not having an answer: switched off, switched on and not finished looking yet, and looked and
failed. They are three standings rather than one because the remedy differs, and none of them
is a tick. See
`A_RELEASE_LIST_THAT_DID_NOT_ANSWER_IS_NOT_A_RELEASE_LIST_WITH_NOTHING_NEWER_ON_IT`.

**"Up to date" and "cannot tell" must not be renderable alike, so the renderer is not trusted
with the difference.** `Standing` has nine members and `ANSWERS` gives each of them the two
sentences a client reads, so the words are this module's rather than a template's. `SETTLED`
holds the one member a tick may be drawn beside, and `Panel` refuses to be built claiming it
without a known running release and a telling that has not gone off. That is item 44's argument
about a "last verified restore" field applied to the field beside it: this is what somebody
checks before deciding not to worry, so the reassuring answer is the one with the most
conditions on it. See
`A_TICK_WITH_NOTHING_BEHIND_IT_IS_THE_FIELD_SOMEBODY_CHECKS_BEFORE_DECIDING_NOT_TO_WORRY`.

**Ordering two tags is where a version screen fails in the reassuring direction**, because the
obvious comparison is the string one and `v1.9.0` sorts after `v1.10.0` under it. So only tags
of one declared shape are ordered at all, anything else is reported as differing rather than as
equal, and a running release newer than the newest anybody named is its own answer rather than
being folded into "up to date". See
`A_TAG_COMPARISON_THAT_GUESSES_FAILS_IN_THE_REASSURING_DIRECTION`.

Rejected: reading the marker and the pin here. This module would then be untestable for the
case that matters, which is the install where one of them is missing. They are parameters,
exactly as `brain.console.installation.install_facts` takes its manifest, and
`facts_the_container_cannot_read` is the check that says which of them the application
container is handed.

Rejected: mounting the marker into the application container so all three statements reach
it. A bind mount of a file that does not exist makes docker create a directory in its place, on
the host, owned by root, and the next install on that host then fails to write its marker at
all. And what the mount would add is the statement that is wrong about the running container
during a failed update, which the pin already gets right.

Rejected: a `Source` and a `Fact` of this module's own. `brain.console.installation` already
distinguishes measured from declared from unknown for the install group, and a second
vocabulary would let one screen call a value measured while its neighbour called the same value
declared. This imports them.

Rejected: showing the commit as the version when the tag is unknown. It is the only measured
statement and it is the wrong answer: a client cannot look a commit up in a release list, ask
for its notes, or hand it to the update script, so a column headed with a version and filled
with a commit is a field that answers a question nobody asked, in the reassuring direction. It
is shown, labelled as the commit it is. See `A_COMMIT_IS_NOT_A_RELEASE_A_CLIENT_CAN_LOOK_UP`.

Rejected: naming this module `release_view`. `brain.release` and `brain.deployment.release`
both exist and neither is about a screen, and a third `release` in an import line is the shape
that gets imported by mistake.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything. `now`
is a parameter and every statement about the install is handed in.

Task ids: M42.3.9
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from brain.console.installation import Fact, Source
from brain.deployment.installer import INSTALL_ENV_FILE, INSTALL_HOME, THE_IMAGE_VARIABLE
from brain.deployment.release import NOT_A_RELEASE_TAG, release_marker
from brain.ops.compose import ComposeFiles, mounted_paths
from brain.ops.recovery import DRILL_INTERVAL_DAYS


class VersionError(Exception):
    """Raised when this panel would state a version, or its currency, more firmly than known."""


# ------------------------------------------------------------------ written-down reasons
#: Why an install's own version is three statements rather than one field.
THREE_STATEMENTS_AND_ONLY_ONE_OF_THEM_IS_MEASURED: Final = (
    "An install holds a marker file naming the tag it unpacked, an image variable naming what "
    "the compose command selected its containers by, and a manifest inside the image naming "
    "the commit the code was built from. The marker is a file on the host that nothing hands "
    "the application, the image variable reaches the application through the environment the "
    "same compose command gave it, and only the manifest is measured by this process, which "
    "is a commit rather than a release. A single version field on a screen is therefore one of "
    "three answers with the label of a fourth."
)

#: Why the running release is not baked into the image, and where it comes from instead.
A_RELEASE_TAG_IS_A_NAME_GIVEN_AFTER_THE_BUILD: Final = (
    "The deploy pipeline builds, signs and publishes one image per commit, and a release is "
    "made afterwards by putting the release tag on that same digest as a second name. Building "
    "again at release time to bake the tag in would publish a second digest from the same "
    "source, unsigned and untested, so a build argument can carry the commit and never the "
    "release. What names the release is the image reference the containers were selected by, "
    "and the compose files hand that same variable to the application's environment in the "
    "same evaluation that selects its image, so it is a statement about the running container "
    "rather than about a file beside the install."
)

#: Why the panel names no release when two statements about it disagree.
SHOWING_ONE_OF_TWO_VERSION_FACTS_THAT_DISAGREE_IS_A_SCREEN_THAT_LIES_QUIETLY: Final = (
    "An update writes the marker before it recreates the containers, so for as long as that "
    "takes, and for ever if the update stops part-way, the marker names one release and the "
    "running containers another, and neither statement is wrong: one records what was "
    "downloaded and the other records what is running. A screen showing either one under a "
    "heading reading version is right about a file and wrong about the install, and it is read "
    "by somebody deciding whether they are patched. So it names neither, names both "
    "statements, and says what each of them is."
)

#: Why the reassuring answer carries the most conditions.
A_TICK_WITH_NOTHING_BEHIND_IT_IS_THE_FIELD_SOMEBODY_CHECKS_BEFORE_DECIDING_NOT_TO_WORRY: Final = (
    "Up to date and cannot tell are read the same way when they are drawn the same way, and "
    "the second is the default one: an install that has not switched the check on has never "
    "been told which release is newest. A tick there is worse than no indicator at all, because "
    "an indicator is what "
    "somebody looks at before deciding to stop looking. So the reassuring answer needs a "
    "known running release, a telling, and a telling that has not gone off, and the words for "
    "every other answer belong to this module rather than to whatever draws it."
)

#: Why an install does not ask a vendor whether it is behind.
AN_INSTALL_THAT_ASKS_A_VENDOR_WHETHER_IT_IS_BEHIND_HAS_TOLD_THE_VENDOR_IT_EXISTS: Final = (
    "This product is single-tenant, installed on a client's own server and owned outright, "
    "and nobody operates it on their behalf. A check that runs by default is an outbound "
    "connection nobody agreed to, and the request is the disclosure whatever the reply is: it "
    "says this product is installed at that address, when that server is up and how often "
    "somebody administers it, and a check that sends the running release so the answer can be "
    "narrower turns the collection into a list of which installs are unpatched. So the check "
    "is built switched off: an install asks only once its own configuration switches it on, "
    "and the list it asks can be a copy on the client's own network."
)

#: Why a list that did not answer is its own standing.
A_RELEASE_LIST_THAT_DID_NOT_ANSWER_IS_NOT_A_RELEASE_LIST_WITH_NOTHING_NEWER_ON_IT: Final = (
    "An install switched on to read a release list that times out, refuses, or answers with "
    "something that is not a list of releases has learned nothing about whether it is behind. "
    "Drawn as up to date it is a firewall change silently turning into reassurance; drawn as "
    "switched off, it sends the reader to switch on a thing that is already on. So it is its "
    "own answer, it carries the reason, and it is not in SETTLED."
)

#: Why the measured statement is not the one shown as the version.
A_COMMIT_IS_NOT_A_RELEASE_A_CLIENT_CAN_LOOK_UP: Final = (
    "The commit the image was built from is the only statement this process can measure, and "
    "it is the wrong answer to which release am I on. A client cannot look a commit up in a "
    "list of releases, ask for its notes, or hand it to the update script, and a release tag "
    "is a name given to an image after it was built, so nothing inside the image can match "
    "the commit back to one. It is shown, labelled as the commit, and never under the heading "
    "a client reads as their version."
)

#: Why only one shape of tag is ordered, and why the rest are reported as differing.
A_TAG_COMPARISON_THAT_GUESSES_FAILS_IN_THE_REASSURING_DIRECTION: Final = (
    "The obvious comparison of two tags is the string one, under which v1.9.0 sorts after "
    "v1.10.0 and an install nine releases behind reads as up to date. Every wrong answer a "
    "loose comparison gives is wrong in that direction, because the reader stops at the first "
    "reassuring word. So a pair is ordered only when both tags are the one shape this module "
    "declares, and anything else is reported as differing, which is true and is not "
    "reassuring."
)

#: Why a release this install is already past is its own answer.
RUNNING_SOMETHING_NEWER_THAN_ANYBODY_NAMED_IS_NOT_BEING_BEHIND: Final = (
    "The newest release on a copy of the release list goes out of date the moment somebody "
    "installs from the published list and nobody refreshes the copy, which is the ordinary case "
    "for a mirror rather than the odd one. Folded into up to date it hides that the list has "
    "stopped moving; folded into behind it sends somebody to install a release older than the "
    "one they are running. It is its own answer and it asks for the one thing that fixes it, "
    "which is the list being brought up to date."
)


# ------------------------------------------------------------------ what somebody was told
#: The only way a link to a release's notes may begin. See `Told`.
NOTES_ARE_READ_OVER: Final = "https://"

#: How long an answer about which release is newest is worth anything, in days.
#:
#: **Taken from the drill interval rather than chosen, because the two answer one question:**
#: how long may a console go on repeating a reassurance that nobody has re-proven. A figure of
#: this module's own would be a second answer to that, and the one that drifts is the one on
#: the screen. `brain.ops.recovery.DRILL_INTERVAL_DAYS` is itself bounded from above by the
#: backup retention window, so this inherits a figure that is argued rather than picked.
#:
#: The figure that would actually be right is the interval at which this product publishes a
#: release, and there is not one: no release has ever been published, so there is nothing to
#: measure. That is the honest reason it is borrowed, and the day there is a measured cadence
#: it is the thing this should be read from.
TELLING_GOES_OFF_AFTER_DAYS: Final[int] = DRILL_INTERVAL_DAYS


@dataclass(frozen=True)
class Told:
    """The newest release somebody has told this install about, and who said so.

    **`by` is required and it is not decoration.** An answer about whether a client is patched
    is worth exactly as much as whoever supplied it, and the two plausible suppliers are very
    different: an administrator who read the release notes this morning, and a value typed
    during setup and never touched again. A renderer showing the tag without the source invites
    the reader to treat the second as the first.

    `brain.deployment.release_feed.ask` produces one when an install is switched on to read a
    release list, and nothing produces one otherwise. See
    `AN_INSTALL_THAT_ASKS_A_VENDOR_WHETHER_IT_IS_BEHIND_HAS_TOLD_THE_VENDOR_IT_EXISTS`.

    **`notes` is an https address or nothing, refused here rather than escaped by whatever
    draws it.** It comes from a list somebody else serves, a console turns it into a link, and
    a link whose address is `javascript:` runs in the administrator's session on the one screen
    they open to decide whether to update. A console that had to remember to check would be
    the second place the rule lives.
    """

    #: The release tag somebody says is newest.
    tag: str
    #: When they said it. Timezone-aware, for the reason `brain.ops.recovery.drill_due` gives.
    at: datetime
    #: Who said so, in words a reader can weigh.
    by: str
    #: Where that release's notes are read, as an https address. Empty when nothing said.
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.tag.strip():
            msg = "a telling that names no release says nothing, and it would read as an answer"
            raise VersionError(msg)
        if self.tag.strip() == NOT_A_RELEASE_TAG:
            msg = (
                f"{NOT_A_RELEASE_TAG!r} is not a release, so recording it as the newest one "
                "gives this install a target it can never be on and an answer that never "
                "changes"
            )
            raise VersionError(msg)
        if not self.by.strip():
            msg = (
                f"{self.tag} was recorded with nobody named as having said it, so a reader "
                "cannot tell an administrator who checked this morning from a value typed once"
            )
            raise VersionError(msg)
        if self.at.tzinfo is None:
            msg = (
                f"{self.tag} was recorded at a naive instant, which compares against an aware "
                "now at this machine's offset and makes an answer look fresher or older than "
                "it is"
            )
            raise VersionError(msg)
        if self.notes and not self.notes.startswith(NOTES_ARE_READ_OVER):
            msg = (
                f"{self.tag} was recorded with notes at {self.notes!r}, which is not an https "
                "address, and a link to it is a link somebody else chose the scheme of"
            )
            raise VersionError(msg)


class Unasked(enum.StrEnum):
    """Why an install that could have been told which release is newest was not."""

    #: The install is not switched on to look, so it asked nobody.
    SWITCHED_OFF = "the release check is switched off"
    #: It asked, and the list could not be reached.
    UNREACHABLE = "the release list could not be reached"
    #: It asked, and the answer was not a list naming a release this install can order.
    UNREADABLE = "the release list did not name a release"


@dataclass(frozen=True)
class Unanswered:
    """The outcome of asking a release list that produced no answer, and why.

    A value rather than an exception, because it is drawn: the reader is owed the reason, and
    an exception caught by whatever renders the panel is a reason that becomes a blank.
    """

    why: Unasked
    #: What happened, in words a reader can act on.
    detail: str
    #: When the question was asked. Timezone-aware, for the reason `Told.at` is.
    at: datetime

    def __post_init__(self) -> None:
        if not self.detail.strip():
            msg = f"{self.why.value}, with nothing saying what happened, is a blank with a label"
            raise VersionError(msg)
        if self.at.tzinfo is None:
            msg = "an unanswered question recorded at a naive instant cannot be placed in time"
            raise VersionError(msg)


# --------------------------------------------------------- what this install says it is on
#: The name of each statement, as it appears on the screen.
MARKER_FACT: Final = "release marker"
PINNED_FACT: Final = "pinned image"
COMMIT_FACT: Final = "built commit"


def image_tag(reference: str) -> str:
    """The tag half of an image reference, or an empty string when it carries none.

    The last path segment is what a tag can be in, which is the whole of why this is not a
    `rsplit(":", 1)` on the reference: a registry with a port in it puts a colon in the first
    segment, so the simple split returns the port of the host as the release this install is
    running. An install pointed at a registry on a port is not a shape anybody here has, which
    is exactly why it would not be noticed.
    """
    segment = reference.strip().rsplit("/", 1)[-1]
    tag = segment.rsplit(":", 1)[1] if ":" in segment else ""
    return tag.strip()


@dataclass(frozen=True)
class Running:
    """Which release this install is on, the statements it was read from, or why neither.

    Exactly one of `tag` and `cannot_say` is set, refused in the constructor rather than left
    to a renderer. A `Running` carrying both would be drawn as a version with a caveat beside
    it, and a caveat beside a number is read as a number.

    `commit` travels beside both and is never a substitute for `tag`. A screen with no release
    to name still owes the reader what is running, and the commit is the measured answer to
    that; carried as its own field, it is drawn under its own label rather than picked out of
    `facts` by name, which is a console deciding which row is the version. See
    `A_COMMIT_IS_NOT_A_RELEASE_A_CLIENT_CAN_LOOK_UP`.
    """

    #: The release this install is on, when the statements agree it is one. Empty otherwise.
    tag: str
    #: One statement per place that can say, each labelled with how firmly it is known.
    facts: tuple[Fact, ...]
    #: Why no release is named. Required when `tag` is empty, and empty when it is not.
    cannot_say: str = ""
    #: The commit the running image was built from, measured. Empty when nothing reported one.
    commit: str = ""

    def __post_init__(self) -> None:
        if not self.facts:
            msg = "a running release read from nothing is not a reading"
            raise VersionError(msg)
        if self.tag and self.cannot_say:
            msg = (
                f"{self.tag} is named and a reason not to name one is set beside it, and a "
                "caveat beside a version number is read as a version number"
            )
            raise VersionError(msg)
        if not self.tag and not self.cannot_say:
            msg = (
                "no release is named and nothing says why, so the reader goes looking for a "
                "setting that would not have helped. "
                f"{THREE_STATEMENTS_AND_ONLY_ONE_OF_THEM_IS_MEASURED}"
            )
            raise VersionError(msg)


def running_release(*, marker: str = "", pinned_image: str = "", built_commit: str = "") -> Running:
    """What this install is running, from the three places that can say (M42.3.9).

    Every argument is what somebody else read, for the reason
    `brain.console.installation.install_facts` takes its manifest: a function that opened them
    could not be tested for the install where one is missing.

    `marker` is the content of the release marker, `pinned_image` the whole image reference the
    containers were selected by, and `built_commit` the commit the running image reports. Inside
    the application `brain.install_routes` hands in the last two, from
    `brain.settings.Settings.app_image` and the image's own manifest, and never the marker. See
    `A_RELEASE_TAG_IS_A_NAME_GIVEN_AFTER_THE_BUILD`. Each produces a labelled statement whether
    or not it was supplied, because an absent statement is a thing the reader has to know about
    rather than a row to leave out.

    **An install with no release in its image reference is not pinned, and the marker cannot
    describe its containers.** A reference ending in `latest`, or in no tag at all, runs
    whatever was newest when it was pulled, so it is named as unpinned rather than reported as
    the marker's tag. See
    `SHOWING_ONE_OF_TWO_VERSION_FACTS_THAT_DISAGREE_IS_A_SCREEN_THAT_LIES_QUIETLY`.
    """
    named = marker.strip()
    pin = pinned_image.strip()
    commit = built_commit.strip()
    # An image reference with no tag at all is `latest` to docker, so the two are one case
    # here: neither of them selects a release.
    pinned = image_tag(pin) or NOT_A_RELEASE_TAG
    facts = (_marker_fact(named), _pinned_fact(pin, pinned), _commit_fact(commit))

    if not named and not pin:
        return Running(
            tag="",
            facts=facts,
            commit=commit,
            cannot_say=(
                "nothing handed this application the image reference it was started from, "
                "and no release marker either, so no statement about a version has been read "
                "at all. An install's own compose files hand the reference over; a deployment "
                "tool that keeps its own copy of the compose file does so once that copy "
                "carries the line"
            ),
        )
    if pinned == NOT_A_RELEASE_TAG:
        return Running(
            tag="",
            facts=facts,
            commit=commit,
            cannot_say=(
                "this install pins no release: nothing selects a release tag for its "
                "containers, so they run whatever was newest when they were last pulled. A "
                "marker, when there is one, records what was downloaded and cannot describe "
                "what is running. Running the update script with a release tag pins one"
            ),
        )
    if named and named != pinned:
        return Running(
            tag="",
            facts=facts,
            commit=commit,
            cannot_say=(
                f"the release marker says {named} and the containers are pinned to {pinned}, "
                "so these two disagree about the same install. One of them is a record of what "
                "was downloaded and the other selects what runs, and naming either as the "
                "version would be right about one and wrong about the other"
            ),
        )
    return Running(tag=named or pinned, facts=facts, commit=commit)


def _marker_fact(named: str) -> Fact:
    """The tag the install unpacked, declared, or the admission that nothing reported it."""
    if not named:
        return Fact(
            name=MARKER_FACT,
            source=Source.UNKNOWN,
            because=(
                "the release marker is a file beside the install on the server, and it is not "
                "handed to the application on purpose: an update writes it before it restarts "
                "anything, so it can name a release no container is running yet. The pinned "
                "image below is the statement about what is running"
            ),
        )
    return Fact(
        name=MARKER_FACT,
        source=Source.DECLARED,
        value=named,
        because=(
            "the tag this install downloaded and unpacked. It records what was fetched rather "
            "than what the containers are running, and while an update is part-way through "
            "those are two different facts"
        ),
    )


def _pinned_fact(pin: str, pinned: str) -> Fact:
    """The image the containers were told to run, declared, or the admission of no pin."""
    if not pin:
        return Fact(
            name=PINNED_FACT,
            source=Source.UNKNOWN,
            because=(
                "nothing handed this application the image reference its container was "
                "started from, so there is no version here to read. The compose files an "
                "install runs pass it in; a deployment tool with its own stored copy of a "
                "compose file passes it once that copy is brought up to date"
            ),
        )
    if pinned == NOT_A_RELEASE_TAG:
        return Fact(
            name=PINNED_FACT,
            source=Source.DECLARED,
            value=pin,
            because=(
                f"{NOT_A_RELEASE_TAG} is not a release: it names whatever was published most "
                "recently, so the next pull changes what this install runs with nobody having "
                "decided anything"
            ),
        )
    return Fact(
        name=PINNED_FACT,
        source=Source.DECLARED,
        value=pin,
        because=(
            "the image reference this application's container was started from, handed to it "
            "by the same command that selected the image. It names the release that was asked "
            "for; the built commit below is the measured half"
        ),
    )


def _commit_fact(commit: str) -> Fact:
    """The commit the running image was built from, measured, or the admission of no manifest."""
    if not commit:
        return Fact(
            name=COMMIT_FACT,
            source=Source.UNKNOWN,
            because=(
                "no release manifest was written into this image, so nothing here can say "
                "which commit is running"
            ),
        )
    return Fact(
        name=COMMIT_FACT,
        source=Source.MEASURED,
        value=commit,
        because=A_COMMIT_IS_NOT_A_RELEASE_A_CLIENT_CAN_LOOK_UP,
    )


# --------------------------------------------------------------- whether anything is newer
class Standing(enum.StrEnum):
    """Where this install stands against the newest release anybody has named.

    Nine answers rather than two, because the two-answer version of this screen is a tick and
    the absence of one, and the absence of a tick is read as a tick that has not loaded. Every
    member has a producer in `standing_of` and a sentence in `ANSWERS`.

    **Three of them are ways of having no answer, and the difference is what to do next.**
    Switched off sends the reader to a setting, not looked yet sends them back in a minute, and
    failed sends them to the network. One word for all three would send two of those readers to
    the wrong place, and would make the most common one, switched off, look like a fault.
    """

    #: A newer release is known to exist.
    BEHIND = "newer release available"
    #: Running the newest release anybody named, recently enough for that to mean something.
    CURRENT = "current"
    #: Running the newest release anybody named, and nobody has named one for a long time.
    STALE = "stale"
    #: Running something newer than the newest anybody named.
    AHEAD = "ahead"
    #: Not on the release last named, and the two tags cannot be put in an order.
    DIFFERS = "differs"
    #: This install is not switched on to look for newer releases, so nothing has said.
    SWITCHED_OFF = "check switched off"
    #: Switched on, and no look has finished in this process yet.
    NOT_LOOKED_YET = "not checked yet"
    #: Switched on, and the last look at the release list did not get an answer.
    CHECK_FAILED = "check failed"
    #: Nothing here can say which release is running, so there is nothing to compare.
    UNKNOWN_RUNNING = "unknown running"


#: The answers a renderer may draw as reassurance, and there is exactly one.
#:
#: A set rather than a boolean on each answer, so the question "which of these is a tick" is
#: asked in one place and a member added later is outside it by default. `Panel` refuses to be
#: built claiming one of these without the conditions that make it true.
SETTLED: Final[frozenset[Standing]] = frozenset({Standing.CURRENT})


@dataclass(frozen=True)
class Answer:
    """What a client reads for one standing, and what they do about it.

    Both required, and they are different things, exactly as
    `brain.deployment.release.Level` keeps them apart: `says` is the state, and without
    `what_to_do` a state is a word three people read three ways. Written for somebody with a
    server and no source tree, which is why none of them names a file, a module or a task.
    """

    says: str
    what_to_do: str

    def __post_init__(self) -> None:
        for field, value in (("says", self.says), ("what_to_do", self.what_to_do)):
            if not value.strip():
                msg = f"an answer with no {field} is a label rather than an answer"
                raise VersionError(msg)


#: The two sentences for every standing. Complete over `Standing`, and a test holds that.
ANSWERS: Final[Mapping[Standing, Answer]] = MappingProxyType(
    {
        Standing.BEHIND: Answer(
            says=(
                "A newer release than the one this install is running has been published. "
                "Which one it is, and where its notes are, is shown below. How urgent it is, "
                "and whether it changes your database, are in those notes."
            ),
            what_to_do=(
                "Read that release's notes, then run the update script with its tag. Take a "
                "backup first if the notes say it changes your database."
            ),
        ),
        Standing.CURRENT: Answer(
            says=(
                "This install is running the newest release on the release list it read, and "
                "it read that list recently. That is as strong as this screen gets: it is a "
                "statement about that list, and not about everything published anywhere."
            ),
            what_to_do=(
                "Nothing today. This install reads the list again by itself when this page is "
                "opened, so the answer is never older than the date shown below."
            ),
        ),
        Standing.STALE: Answer(
            says=(
                "This install is running the newest release it knows of, and it learned that a "
                "long time ago. A release published since then would look exactly like this."
            ),
            what_to_do=(
                "Open this page again in a minute, because opening it starts a fresh look. If "
                "it still says this, check the published list of releases by hand."
            ),
        ),
        Standing.AHEAD: Answer(
            says=(
                "This install is running a release newer than the newest one on the release "
                "list it read, so that list is out of date rather than this install."
            ),
            what_to_do=(
                "If this install reads a copy of the release list, bring the copy up to date. "
                "Until then nothing on this page can tell you whether something newer exists."
            ),
        ),
        Standing.DIFFERS: Answer(
            says=(
                "This install is not running the newest release on the list it read, and the "
                "two cannot be put in an order, so nothing here can say which of them is the "
                "later."
            ),
            what_to_do=(
                "Compare the two by hand against the published list of releases. A pair that "
                "cannot be ordered is usually one of them being something other than a release."
            ),
        ),
        Standing.SWITCHED_OFF: Answer(
            says=(
                "This install does not look for newer releases, so it cannot tell you whether "
                "it is behind. This is not the same as being up to date. It is the default, "
                "because this product asks nothing outside your network unless you switch it on."
            ),
            what_to_do=(
                "Check the published list of releases by hand, or set BRAIN_RELEASE_CHECK to "
                "true so this install looks for itself whenever this page is opened."
            ),
        ),
        Standing.NOT_LOOKED_YET: Answer(
            says=(
                "This install is switched on to look for newer releases and has not finished "
                "looking since it started. This is not the same as being up to date."
            ),
            what_to_do=(
                "Open this page again in a minute. Opening it is what started the look, and "
                "nothing on this page waits for the answer."
            ),
        ),
        Standing.CHECK_FAILED: Answer(
            says=(
                "This install looked for newer releases and did not get an answer, so it cannot "
                "tell you whether a newer release exists. This is not the same as being up to "
                "date. The reason is shown below."
            ),
            what_to_do=(
                "Check that the server can reach the address it asks, or check the published "
                "list of releases by hand. Until it answers, treat this install as possibly "
                "behind."
            ),
        ),
        Standing.UNKNOWN_RUNNING: Answer(
            says=(
                "Nothing here can say which release this install is running, so there is "
                "nothing to compare a newer one against. The reason is shown below."
            ),
            what_to_do=(
                "Run the update script with the release tag you mean to run, which pins it. "
                "Until this install can say which release it is on, no answer about whether it "
                "is behind is worth anything."
            ),
        ),
    }
)


#: A release tag this module will put in an order: `v` and dot-separated whole numbers.
#:
#: One shape rather than a best effort at every shape, and everything else is reported as
#: differing. See `A_TAG_COMPARISON_THAT_GUESSES_FAILS_IN_THE_REASSURING_DIRECTION`.
ORDERABLE_TAG: Final = re.compile(r"^v(\d+(?:\.\d+)*)$")


def ordinal(tag: str) -> tuple[int, ...] | None:
    """The tag as numbers to compare, or `None` when it is not a shape this module orders.

    Public because `brain.deployment.release_feed` chooses the newest release off a list with
    it, and a second ordering there would be a second answer to which of two tags is later.
    """
    found = ORDERABLE_TAG.match(tag.strip())
    if found is None:
        return None
    return tuple(int(one) for one in found.group(1).split("."))


def _ordered(running: str, newest: str) -> Standing:
    """Which of two different tags is the later, or the admission that nothing here knows.

    Padded to the same length before comparing, so `v1.4` and `v1.4.1` order the way a person
    reads them. Two spellings that pad to the same numbers are reported as differing rather
    than as equal: they are two tags, a registry holds them as two things, and calling them one
    release is a guess in the reassuring direction.
    """
    here, there = ordinal(running), ordinal(newest)
    if here is None or there is None:
        return Standing.DIFFERS
    width = max(len(here), len(there))
    here += (0,) * (width - len(here))
    there += (0,) * (width - len(there))
    if here < there:
        return Standing.BEHIND
    if here > there:
        return Standing.AHEAD
    return Standing.DIFFERS


def standing_of(
    running: Running,
    told: Told | Unanswered | None,
    *,
    now: datetime,
    goes_off_after_days: int = TELLING_GOES_OFF_AFTER_DAYS,
) -> Standing:
    """Where this install stands, in one word, with every way of not knowing kept apart.

    `told` is `None` when a look is switched on and none has finished, which is a different
    thing from an `Unanswered` saying the check is off: see `Standing`.

    The order of the questions is the argument. An unknown running release is asked first,
    because every answer after it would be a comparison against nothing. A telling that has
    gone off only changes the reassuring answer: a newer release that was published a year ago
    is still published, so `BEHIND` does not go stale, and `CURRENT` is the only claim whose
    whole value is that somebody looked recently.

    `now` and the window are parameters for the reason `brain.ops.limits` keeps its clock
    outside itself: a boundary is the only interesting case and it cannot be tested through a
    function that reads the process clock.
    """
    if now.tzinfo is None:
        msg = "a naive now compares against a recorded instant at this machine's offset"
        raise VersionError(msg)
    if goes_off_after_days < 0:
        msg = (
            f"a telling cannot go off after {goes_off_after_days} days, and a negative window "
            "would make every answer reassuring"
        )
        raise VersionError(msg)
    if not running.tag:
        return Standing.UNKNOWN_RUNNING
    if told is None:
        return Standing.NOT_LOOKED_YET
    if isinstance(told, Unanswered):
        if told.why is Unasked.SWITCHED_OFF:
            return Standing.SWITCHED_OFF
        return Standing.CHECK_FAILED
    if told.at > now:
        msg = (
            f"{told.tag} was recorded later than the moment being asked about, so the two "
            "clocks disagree and the answer's age would read as fresher than it is"
        )
        raise VersionError(msg)
    if told.tag.strip() != running.tag:
        return _ordered(running.tag, told.tag.strip())
    if now - told.at > timedelta(days=goes_off_after_days):
        return Standing.STALE
    return Standing.CURRENT


@dataclass(frozen=True)
class Panel:
    """The whole version panel: what is running, what was said, and where that leaves it.

    **The refusals are on the reassuring answer alone**, which is deliberate rather than
    uneven. Every other member is a statement that something is not known or not current, and
    stating one of those too firmly costs a reader nothing. See
    `A_TICK_WITH_NOTHING_BEHIND_IT_IS_THE_FIELD_SOMEBODY_CHECKS_BEFORE_DECIDING_NOT_TO_WORRY`.
    """

    running: Running
    told: Told | Unanswered | None
    standing: Standing
    #: How long ago somebody last named the newest release, in days. `None` when nobody has.
    told_days_ago: int | None = None
    #: The window this panel's standing was decided against, carried so a renderer can say it.
    goes_off_after_days: int = TELLING_GOES_OFF_AFTER_DAYS

    def __post_init__(self) -> None:
        if self.standing not in SETTLED:
            return
        if not self.running.tag:
            msg = (
                f"{self.standing.value} is claimed and nothing here says which release is "
                "running, so the reassuring answer would be about an install nobody identified"
            )
            raise VersionError(msg)
        if not isinstance(self.told, Told) or self.told_days_ago is None:
            msg = (
                f"{self.standing.value} is claimed and nobody has said which release is "
                "newest, which is the tick with nothing behind it this panel exists to refuse"
            )
            raise VersionError(msg)
        if self.told_days_ago > self.goes_off_after_days:
            msg = (
                f"{self.standing.value} is claimed against something recorded "
                f"{self.told_days_ago} days ago, and it goes off after "
                f"{self.goes_off_after_days}. A release published since would look identical"
            )
            raise VersionError(msg)

    @property
    def answer(self) -> Answer:
        """The two sentences a client reads. Never assembled by whatever draws this."""
        return ANSWERS[self.standing]


def panel(
    running: Running,
    told: Told | Unanswered | None,
    *,
    now: datetime,
    goes_off_after_days: int = TELLING_GOES_OFF_AFTER_DAYS,
) -> Panel:
    """The panel M42.3.9 asks for: the running version, and whether anything newer exists.

    The age is whole days and is rounded down, which is the direction that matters: a telling
    made twenty-three hours before the window closes is not yet stale and a rounding that made
    it so would be refusing to reassure somebody who has just looked. The other direction would
    be the one this module spends its whole length refusing.
    """
    where = standing_of(running, told, now=now, goes_off_after_days=goes_off_after_days)
    days = (now - told.at).days if isinstance(told, Told) else None
    return Panel(
        running=running,
        told=told,
        standing=where,
        told_days_ago=days,
        goes_off_after_days=goes_off_after_days,
    )


# ------------------------------------------------------------------------- the diagnostics
#: What an install would send outside a client's network to ask whether it is behind.
#:
#: Written as the list somebody would have to put in a client agreement rather than as a
#: paragraph, for the reason `brain.console.installation.RECOVERY_NEEDS` is a list: a later
#: reader can tell which items an eventual design actually removed, which a paragraph makes
#: surprisingly hard. Every one of them is true of the smallest possible version of the check,
#: which is a plain fetch of a static file.
#:
#: The check `brain.deployment.release_feed` makes is that plain fetch and sends nothing of the
#: install's own, so the third item is the one its design removes; pointed at a copy inside the
#: client's network, it removes every item but the last.
WHAT_A_RELEASE_CHECK_WOULD_SEND: Final[tuple[str, ...]] = (
    "the address the client's server leaves its network by, which is enough on its own to "
    "say that this product is installed there",
    "the moment of every check and the gaps between them, which is a record of when that "
    "server is running and when somebody is administering it",
    "the release this install is on, if the check sends it so the answer can be narrower, "
    "which turns the collection into a list of which installs are unpatched",
    "the name being looked up, which reaches the client's own resolver and whoever it "
    "forwards to, whether or not the request itself is encrypted",
    "an outbound allowance that has to stay open, in a deployment whose outbound traffic is "
    "otherwise enumerated and reviewed",
)


def release_check_cost() -> tuple[str, ...]:
    """What a check for newer releases would cost, as a check rather than as a sentence.

    Non-empty by construction and expected to stay that way, which is why it is kept apart
    from anything that has to be green, exactly as
    `brain.console.installation.recovery_gaps` is. It is not a defect list. It is the record
    that the decision was made rather than missed, and it is what an install agrees to by
    switching the check on. See
    `AN_INSTALL_THAT_ASKS_A_VENDOR_WHETHER_IT_IS_BEHIND_HAS_TOLD_THE_VENDOR_IT_EXISTS`.
    """
    return tuple(
        f"an install that asks whether a newer release exists sends {one}"
        for one in WHAT_A_RELEASE_CHECK_WOULD_SEND
    )


#: The service every compose file of this deployment runs the application as.
#:
#: Asserted against `brain.ops.reliability.BASELINE_COMPONENTS` by the test rather than being
#: a name written here and nowhere else, because a renamed service would otherwise turn the
#: check below into one that always reports the same two findings.
THE_APPLICATION_SERVICE: Final = "app"


def facts_the_container_cannot_read(
    files: ComposeFiles,
    *,
    service: str = THE_APPLICATION_SERVICE,
    home: str = INSTALL_HOME,
) -> tuple[str, ...]:
    """Which statements on this panel nothing inside the application container can obtain.

    Both findings are read out of the compose documents rather than asserted: the first is true
    while no service of this name mounts anything from the install directory, and the second
    while the image variable is in no environment entry of that service. Either one stops being
    reported on the day somebody wires it, which is what makes this a check rather than a
    comment.

    **Against this repository's compose files it reports the marker alone, and that one is
    kept on purpose.** Until 2026-09-16 it reported both, which was the state in which the
    panel named no release on any install. The image variable is now in the application's
    environment in both compose files that run it, so the second finding is gone and a compose
    file that drops the line brings it back. The first is the decision recorded under
    "Rejected: mounting the marker" in this module's header, kept as a finding for the reason
    `release_check_cost` is: it is the record that the choice was made rather than missed.
    """
    _, marker = release_marker()
    findings: list[str] = []
    mounted = any(
        where == service and (source == home or source.startswith(f"{home}/"))
        for _, where, source in mounted_paths(files)
    )
    if not mounted:
        findings.append(
            f"the release marker at {home}/{marker} is a file on the host and no compose file "
            f"mounts anything from {home} into the {service!r} service, so nothing inside the "
            "container can read which release this install unpacked"
        )
    if THE_IMAGE_VARIABLE not in _environment_of(files, service):
        findings.append(
            f"{THE_IMAGE_VARIABLE} is read from {home}/{INSTALL_ENV_FILE} by the compose "
            f"command on the host and is in no environment entry of the {service!r} service, "
            "so nothing inside the container can read the image its own containers were "
            "selected by"
        )
    return tuple(findings)


def _environment_of(files: ComposeFiles, service: str) -> dict[str, str]:
    """One service's environment, merged across the files that declare it.

    A reader of its own rather than `brain.ops.compose`'s, which is private and answers about
    every service at once. The same choice `brain.deployment.release` makes about the volumes
    block and for the same reason: six lines here, against a public function on a module whose
    other callers do not want this shape.
    """
    found: dict[str, str] = {}
    for name in sorted(files):
        services = files[name].get("services")
        body: Any = services.get(service) if isinstance(services, Mapping) else None
        if not isinstance(body, Mapping):
            continue
        declared = body.get("environment") or {}
        if isinstance(declared, Mapping):
            found.update({str(key): str(value) for key, value in declared.items()})
            continue
        if isinstance(declared, Sequence) and not isinstance(declared, str):
            for entry in declared:
                key, _, value = str(entry).partition("=")
                found[key] = value
    return found
