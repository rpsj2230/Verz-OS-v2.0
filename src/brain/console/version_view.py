"""Which release this install is on, and whether anything newer exists, without guessing either.

An install holds three statements about its own version and **no two of them answer the same
question**, which is why this is a module rather than a field. The release marker at
`INSTALL_HOME` says which tag was unpacked; `APP_IMAGE` in the install's environment file says
which image the compose command was told to select; and the manifest inside the image says
which commit the running code was built from. The first two are host files the application
container mounts nothing of, the third is the only one this process can measure, and the third
is a commit rather than a release. See `THREE_STATEMENTS_AND_ONLY_ONE_OF_THEM_IS_MEASURED`.

**Two of them can disagree from the first day of an install and neither is wrong.** A fresh
install writes the marker and writes nothing that selects an image, so every container falls
back to the compose default, which ends in `latest`. `docs/install/update-and-rollback.md` says
so in those words. A screen picking one of the two would therefore be reporting a version that
is true of a file and not of the containers, on every install that has never run the update
script, which is every install today. So this **names no release at all** when the two
statements do not agree, and says which two they are and what each one means. See
`SHOWING_ONE_OF_TWO_VERSION_FACTS_THAT_DISAGREE_IS_A_SCREEN_THAT_LIES_QUIETLY`.

**Nothing here asks anything outside this install whether a newer release exists, and that is
a decision rather than an omission.** The honest options were a check that phones a vendor,
somebody telling the install, or admitting it cannot know. This product is single-tenant,
installed on a client's own server and owned outright, and a check that runs by default is an
outbound connection nobody agreed to: it discloses that this product is installed at that
address, when that server is up, how often somebody administers it, and, if the check sends the
running version so the answer can be narrower, which installs are behind. That last one is a
list of who is unpatched, held by somebody who does not operate the install.
`WHAT_A_RELEASE_CHECK_WOULD_SEND` is that cost written down item by item, and
`release_check_cost` is it as a check rather than as a sentence in a commit message nobody
re-reads, which is the construction `brain.console.installation.recovery_gaps` uses for the
screen it declines to build.

So the half that can be built is built: **the comparison, and the age of the answer it is
comparing against**. `Told` is what somebody has said the newest release is, carrying who said
so and when, and nothing here produces one. That is the honest shape rather than a gap: the day
an owner decides that an install may ask, the asker produces a `Told` and every sentence below
is unchanged.

**"Up to date" and "cannot tell" must not be renderable alike, so the renderer is not trusted
with the difference.** `Standing` has seven members and `ANSWERS` gives each of them the two
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

Rejected: reading the marker and the pin here. They are host files and this module would then
be untestable for the case that matters, which is the install where one of them is missing.
They are parameters, exactly as `brain.console.installation.install_facts` takes its manifest,
and `facts_the_container_cannot_read` is the finding that nothing inside the application
container can supply either of them today.

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
from brain.deployment.installer import INSTALL_ENV_FILE, INSTALL_HOME
from brain.deployment.release import NOT_A_RELEASE_TAG, THE_IMAGE_VARIABLE, release_marker
from brain.ops.compose import ComposeFiles, mounted_paths
from brain.ops.recovery import DRILL_INTERVAL_DAYS


class VersionError(Exception):
    """Raised when this panel would state a version, or its currency, more firmly than known."""


# ------------------------------------------------------------------ written-down reasons
#: Why an install's own version is three statements rather than one field.
THREE_STATEMENTS_AND_ONLY_ONE_OF_THEM_IS_MEASURED: Final = (
    "An install holds a marker file naming the tag it unpacked, an image variable in its "
    "environment file naming what the compose command was told to select, and a manifest "
    "inside the image naming the commit the code was built from. The first two are files on "
    "the host and the application container mounts nothing of either, so the only one this "
    "process can measure is the third, and the third is a commit rather than a release. A "
    "single version field on a screen is therefore one of three answers with the label of a "
    "fourth."
)

#: Why the panel names no release when two statements about it disagree.
SHOWING_ONE_OF_TWO_VERSION_FACTS_THAT_DISAGREE_IS_A_SCREEN_THAT_LIES_QUIETLY: Final = (
    "A fresh install writes the marker and writes nothing that selects an image, so every "
    "container falls back to the compose default, which ends in latest. The marker and the "
    "running containers therefore disagree from the first day and neither statement is wrong: "
    "one records what was downloaded and the other records what is running. A screen showing "
    "either one under a heading reading version is right about a file and wrong about the "
    "install, and it is read by somebody deciding whether they are patched. So it names "
    "neither, names both statements, and says what each of them is."
)

#: Why the reassuring answer carries the most conditions.
A_TICK_WITH_NOTHING_BEHIND_IT_IS_THE_FIELD_SOMEBODY_CHECKS_BEFORE_DECIDING_NOT_TO_WORRY: Final = (
    "Up to date and cannot tell are read the same way when they are drawn the same way, and "
    "the second is the common one: nothing outside this install has ever said which release "
    "is newest. A tick there is worse than no indicator at all, because an indicator is what "
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
    "narrower turns the collection into a list of which installs are unpatched. A client can "
    "decline a thing that is not built."
)

#: Why the measured statement is not the one shown as the version.
A_COMMIT_IS_NOT_A_RELEASE_A_CLIENT_CAN_LOOK_UP: Final = (
    "The commit the image was built from is the only statement this process can measure, and "
    "it is the wrong answer to which release am I on. A client cannot look a commit up in a "
    "list of releases, ask for its notes, or hand it to the update script, and no image is "
    "published carrying a release tag at all, so the commit cannot even be matched back to "
    "one. It is shown, labelled as the commit, and never under the heading a client reads as "
    "their version."
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
    "The newest release anybody told this install about goes out of date the moment somebody "
    "updates and does not say so, which is the ordinary case rather than the odd one. Folded "
    "into up to date it hides that nothing has been said for a while; folded into behind it "
    "sends somebody to install a release older than the one they are running. It is its own "
    "answer and it asks for the one thing that fixes it, which is somebody saying what the "
    "newest release is now."
)


# ------------------------------------------------------------------ what somebody was told
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

    Nothing in this repository produces one. See
    `AN_INSTALL_THAT_ASKS_A_VENDOR_WHETHER_IT_IS_BEHIND_HAS_TOLD_THE_VENDOR_IT_EXISTS`.
    """

    #: The release tag somebody says is newest.
    tag: str
    #: When they said it. Timezone-aware, for the reason `brain.ops.recovery.drill_due` gives.
    at: datetime
    #: Who said so, in words a reader can weigh.
    by: str

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
    """

    #: The release this install is on, when the statements agree it is one. Empty otherwise.
    tag: str
    #: One statement per place that can say, each labelled with how firmly it is known.
    facts: tuple[Fact, ...]
    #: Why no release is named. Required when `tag` is empty, and empty when it is not.
    cannot_say: str = ""

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

    Every argument is what somebody else read off the server, for the reason
    `brain.console.installation.install_facts` takes its manifest: these are host files and a
    function that opened them could not be tested for the install where one is missing, which
    is every install that has never been updated.

    `marker` is the content of the release marker, `pinned_image` the whole value of the image
    variable from the install's environment file, and `built_commit` the commit the running
    image reports. Each produces a labelled statement whether or not it was supplied, because
    an absent statement is a thing the reader has to know about rather than a row to leave out.

    **An install with no image pin is not pinned, and the marker cannot describe its
    containers.** That is the case on every install that has never run the update script, so it
    is the common answer rather than the odd one, and it is named as such rather than reported
    as the marker's tag. See
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
            cannot_say=(
                "nothing here reports the release this install unpacked or the image its "
                "containers were told to run, so no statement about a version has been read "
                "at all"
            ),
        )
    if pinned == NOT_A_RELEASE_TAG:
        return Running(
            tag="",
            facts=facts,
            cannot_say=(
                "this install pins no release, so its containers run whatever the image "
                "default pointed at when they were last pulled. The marker records what was "
                "downloaded and cannot describe what is running. Running the update script "
                "once writes the pin and makes these one fact"
            ),
        )
    if named and named != pinned:
        return Running(
            tag="",
            facts=facts,
            cannot_say=(
                f"the release marker says {named} and the containers are pinned to {pinned}, "
                "so these two disagree about the same install. One of them is a record of what "
                "was downloaded and the other selects what runs, and naming either as the "
                "version would be right about one and wrong about the other"
            ),
        )
    return Running(tag=named or pinned, facts=facts)


def _marker_fact(named: str) -> Fact:
    """The tag the install unpacked, declared, or the admission that nothing reported it."""
    if not named:
        return Fact(
            name=MARKER_FACT,
            source=Source.UNKNOWN,
            because=(
                "the release marker is a file on the server beside the install and nothing "
                "handed its contents to this screen"
            ),
        )
    return Fact(
        name=MARKER_FACT,
        source=Source.DECLARED,
        value=named,
        because=(
            "the tag this install downloaded and unpacked. It records what was fetched rather "
            "than what the containers are running, and until the first update those are two "
            "different facts"
        ),
    )


def _pinned_fact(pin: str, pinned: str) -> Fact:
    """The image the containers were told to run, declared, or the admission of no pin."""
    if not pin:
        return Fact(
            name=PINNED_FACT,
            source=Source.UNKNOWN,
            because=(
                f"nothing in this install's environment file selects an image, so every "
                f"container falls back to the default in the compose file, which ends in "
                f"{NOT_A_RELEASE_TAG}. There is no version here to read"
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
            "the image every container of this install is selected by. It says what they were "
            "told to run rather than what each of them is running, which is the same "
            "distinction the update script makes when it checks nothing stayed behind"
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

    Seven answers rather than two, because the two-answer version of this screen is a tick and
    the absence of one, and the absence of a tick is read as a tick that has not loaded. Every
    member has a producer in `standing_of` and a sentence in `ANSWERS`.
    """

    #: A newer release is known to exist.
    BEHIND = "behind"
    #: Running the newest release anybody named, recently enough for that to mean something.
    CURRENT = "current"
    #: Running the newest release anybody named, and nobody has named one for a long time.
    STALE = "stale"
    #: Running something newer than the newest anybody named.
    AHEAD = "ahead"
    #: Not on the release last named, and the two tags cannot be put in an order.
    DIFFERS = "differs"
    #: Nothing has ever told this install which release is newest.
    NOBODY_HAS_SAID = "nobody has said"
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
                "A newer release than the one this install is running has been published. How "
                "urgent it is, and whether it changes your database, are in its notes."
            ),
            what_to_do=(
                "Read that release's notes, then run the update script with its tag. Take a "
                "backup first if the notes say it changes your database."
            ),
        ),
        Standing.CURRENT: Answer(
            says=(
                "This install is running the newest release anybody has told it about, and it "
                "was told recently. That is as strong as this screen gets: nothing here asks "
                "anywhere outside your network, so this is a statement about what somebody "
                "recorded rather than about what has been published."
            ),
            what_to_do=(
                "Nothing today. Keep the recorded release up to date, because everything on "
                "this panel is measured against it."
            ),
        ),
        Standing.STALE: Answer(
            says=(
                "This install is running the newest release anybody told it about, and nobody "
                "has told it anything for a long time. A release published since then would "
                "look exactly like this."
            ),
            what_to_do=(
                "Check what the newest release is and record it here. Until somebody does, "
                "this panel cannot tell being up to date from not having looked."
            ),
        ),
        Standing.AHEAD: Answer(
            says=(
                "This install is running a release newer than the newest one anybody recorded "
                "here, so the recorded answer is out of date rather than this install."
            ),
            what_to_do=(
                "Record the release this install is now on as the newest one you know of. "
                "Until then nothing on this panel can tell you whether something newer exists."
            ),
        ),
        Standing.DIFFERS: Answer(
            says=(
                "This install is not running the release last recorded as the newest one, and "
                "the two cannot be put in an order, so nothing here can say which of them is "
                "the later."
            ),
            what_to_do=(
                "Compare the two by hand against the published list of releases, and record "
                "the newest one. A pair that cannot be ordered is usually one of them being "
                "something other than a release."
            ),
        ),
        Standing.NOBODY_HAS_SAID: Answer(
            says=(
                "Nothing has ever told this install which release is the newest, so it cannot "
                "tell you whether it is behind. This is not the same as being up to date, and "
                "it is the ordinary state: this product does not ask anywhere outside your "
                "network on its own."
            ),
            what_to_do=(
                "Check the published list of releases, and record the newest one here. Do it "
                "again whenever you install one."
            ),
        ),
        Standing.UNKNOWN_RUNNING: Answer(
            says=(
                "Nothing here can say which release this install is running, so there is "
                "nothing to compare a newer one against. The reason is on the panel above."
            ),
            what_to_do=(
                "Fix the statement above first. Until this install can say which release it "
                "is on, no answer about whether it is behind is worth anything."
            ),
        ),
    }
)


#: A release tag this module will put in an order: `v` and dot-separated whole numbers.
#:
#: One shape rather than a best effort at every shape, and everything else is reported as
#: differing. See `A_TAG_COMPARISON_THAT_GUESSES_FAILS_IN_THE_REASSURING_DIRECTION`.
ORDERABLE_TAG: Final = re.compile(r"^v(\d+(?:\.\d+)*)$")


def _ordinal(tag: str) -> tuple[int, ...] | None:
    """The tag as numbers to compare, or `None` when it is not a shape this module orders."""
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
    here, there = _ordinal(running), _ordinal(newest)
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
    told: Told | None,
    *,
    now: datetime,
    goes_off_after_days: int = TELLING_GOES_OFF_AFTER_DAYS,
) -> Standing:
    """Where this install stands, in one word, with every way of not knowing kept apart.

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
        return Standing.NOBODY_HAS_SAID
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
    told: Told | None
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
        if self.told is None or self.told_days_ago is None:
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
    told: Told | None,
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
    days = None if told is None else (now - told.at).days
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
    that the decision was made rather than missed, and it is what an owner would be agreeing
    to on the day they decide an install may ask. See
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

    **This is the finding, and it is why every input above is a parameter.** The marker and
    the image pin are files in the install directory on the host. Both findings are read out
    of the compose documents rather than asserted: the first is true while no service of this
    name mounts anything from the install directory, and the second while the image variable
    is in no environment entry of that service. Either one stops being reported on the day
    somebody wires it, which is what makes this a check rather than a comment.

    Non-empty against this repository's compose files today, both findings, which is the
    honest state of the leaf: the panel is built and the two statements it most needs have no
    route into the process that would draw it.
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
