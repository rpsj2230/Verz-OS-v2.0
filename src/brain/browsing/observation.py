"""Everything a page said, in exactly one module, so that not importing it is checkable.

A browser driving somebody's accounting system is a principal with hands, and the thing it
is holding is a document written by whoever controls that page. Every other module in this
package is built around one question: which code is allowed to have seen that document.
The answer is enforced by putting all of it here, because "module X does not import module
Y" is a property a parser can settle and "the planner does not really look at the page" is
a promise.

**A node's `name` is text an attacker chose.** It is the accessible name of a button, and a
button can be labelled anything at all, including a paragraph of instructions addressed to a
model. `PAGE_AUTHORED` names the fields that are in that category, and
`brain.browsing.shape` is what stops one of them reaching a planner: no function in this
package may take a type defined here and return a plan, an envelope or a rubric. That is the
whole of M19.2.1 and it is a structural refusal rather than a prompt.

**There is no image field and there must never be one.** M19.4.5 asks for vision to be
disabled so that a credential cannot be read off a screenshot, and the way a screenshot
reaches a model is not a decision anybody makes at request time: it is a field somebody adds
here with a plausible default, six months after this sentence was written. `vision_gaps`
fails on the field rather than on the behaviour, in the shape `brain.ops.halt.halt_gaps`
refuses an expiry, because by the time the behaviour is wrong the field is load bearing.

The second reason is cheaper and just as good. An accessibility tree is a list of roles and
names with stable references; a screenshot is a bitmap that a model has to be asked to
interpret, and asking a model where the button is reintroduces the guess this package exists
to remove. M19.1.4 chose the tree over the picture and this type is that choice written
down.

**A snapshot carries a sequence number, and that is not bookkeeping.** `brain.browsing.
enforcer` validates every element reference against the snapshot that produced it, and a
reference is only meaningful against the tree it came from: the page can replace the button
under a reference between one action and the next, which is clickjacking with extra steps.
The number is how "the snapshot just produced" is expressed as a value rather than as an
assumption about ordering.

Rejected: holding the raw HTML alongside the tree "for debugging". It is the same document,
it would be the field every future author reads because it is familiar, and a debugging
field is exactly how page text reaches somewhere no one meant it to.

Rejected: making `Snapshot` a Pydantic model like `brain.core.envelope.ToolDefinition`.
Nothing validates a snapshot against a schema, because there is nothing to validate: a page
may legitimately contain any role and any name. A frozen dataclass says that plainly.

Scope: domain logic. Nothing here opens a browser, and no browser exists in this repository
to open. What is here is the type a runner would fill in and the refusals that govern it.

Task ids: M19.4.5
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields
from typing import Any, Final, cast

#: Why the picture is refused rather than merely unused.
A_SCREENSHOT_IS_A_CREDENTIAL_READER_WITH_A_PLAUSIBLE_DEFAULT: Final = (
    "Vision is not disabled by nobody switching it on. It is disabled by there being no "
    "field for a picture to arrive in, because a run that types a password into a login "
    "form has, at that instant, the password on the screen. A screenshot taken one frame "
    "later is the credential in a blob that goes to a model, into a trace and into whatever "
    "stores the trace, and every one of those is outside the custody that "
    "brain.ops.secrets spends its whole length establishing."
)

#: Why every page-derived value is in one file.
EVERYTHING_A_PAGE_SAID_LIVES_IN_ONE_MODULE: Final = (
    "The planner must not read page content, and an assertion about what a planner reads is "
    "worth nothing unless page content is a thing with edges. Putting all of it in one "
    "module turns the claim into an import-graph question, which a parser settles, and out "
    "of a code review, which settles it once and then never again."
)

#: Why a reference is only good against one tree.
A_REFERENCE_WITHOUT_ITS_SNAPSHOT_NAMES_WHATEVER_IS_THERE_NOW: Final = (
    "An element reference is a name the runner minted for a node it saw. The page can "
    "replace that node between the snapshot and the action, so a reference validated "
    "against nothing in particular authorises clicking whatever now occupies that slot. "
    "The sequence number is how the enforcer can require the tree the agent actually read."
)

#: Field names on the types here that hold text somebody else wrote. Named so that a reader
#: of `brain.browsing.shape` can see what the structural refusal is protecting, and so that
#: adding a fifth one is a decision rather than an omission.
PAGE_AUTHORED: Final[frozenset[str]] = frozenset({"name", "value", "title", "url"})

#: Field names that would put a picture, a recording or a raw document into a snapshot. Read
#: as substrings, because `thumbnail_png` and `png` are the same mistake.
IMAGE_SHAPED: Final[tuple[str, ...]] = (
    "screenshot",
    "image",
    "png",
    "jpeg",
    "jpg",
    "pixel",
    "bitmap",
    "video",
    "frame",
    "data_url",
    "html",
    "dom",
)


class ObservationError(Exception):
    """A snapshot was built in a way that cannot be validated against.

    One type for every refusal here, as `brain.tools.registry.ToolRegistrationError` is, and
    for the same reason: the refusals differ in message and not in what a caller can do about
    them, and a taxonomy would invite catching some of them.
    """


@dataclass(frozen=True)
class Node:
    """One element of an accessibility tree: what it is, what it is called, how to name it.

    `ref` is minted by the runner and is the only part of this a plan or an action may quote.
    `role` is a fixed vocabulary the browser assigns. `name` is the accessible name, which is
    whatever the page author wrote, and is therefore the field this whole package is built to
    keep away from anything that decides what to do next.
    """

    ref: str
    role: str
    name: str

    def __post_init__(self) -> None:
        if not self.ref.strip():
            msg = "a node with no reference cannot be acted on or validated against"
            raise ObservationError(msg)
        if not self.role.strip():
            msg = (
                f"node {self.ref!r} has no role, so nothing can tell a button from a "
                "paragraph, and the write checks are decided on what a node is"
            )
            raise ObservationError(msg)


@dataclass(frozen=True)
class Snapshot:
    """One accessibility tree, from one origin, at one point in a run.

    Deliberately not a container of anything but nodes. A snapshot that also carried the URL
    it was fetched from as a mutable field, or the response headers, or the console log,
    would be the natural place for the next reader to add the one field that undoes this.
    """

    run_id: str
    #: Which snapshot this is within the run, from one upwards. The enforcer refuses an
    #: action citing anything but the newest.
    sequence: int
    #: Normalised by `brain.channels.widget.normalise_origin` before it gets here.
    origin: str
    nodes: tuple[Node, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            msg = "a snapshot belonging to no run cannot be matched to a policy"
            raise ObservationError(msg)
        if self.sequence < 1:
            msg = (
                f"snapshot sequence {self.sequence} is not a position in a run; sequences "
                "start at one so that a zero-valued default cannot pass for the first one"
            )
            raise ObservationError(msg)
        if not self.origin.strip():
            msg = (
                f"snapshot {self.sequence} of run {self.run_id!r} names no origin, and the "
                "origin check per action is decided against it"
            )
            raise ObservationError(msg)
        seen = [node.ref for node in self.nodes]
        if len(seen) != len(set(seen)):
            msg = (
                "two nodes in one snapshot share a reference, so validating a reference "
                "against this tree would authorise acting on either of them"
            )
            raise ObservationError(msg)

    def refs(self) -> frozenset[str]:
        return frozenset(node.ref for node in self.nodes)

    def has(self, ref: str) -> bool:
        return ref in self.refs()

    def node(self, ref: str) -> Node | None:
        for node in self.nodes:
            if node.ref == ref:
                return node
        return None


def is_current(snapshot: Snapshot, *, run_id: str, sequence: int) -> bool:
    """Whether this is the tree the run just produced, for this run.

    Both halves matter and the second is the one that looks redundant. A snapshot from
    another run with the right sequence number would otherwise satisfy a reference check,
    and two runs against the same target produce trees whose references collide by
    construction, because the runner mints them per tree rather than globally.
    """
    return snapshot.run_id == run_id and snapshot.sequence == sequence


def vision_gaps(observed: Iterable[type] = ()) -> tuple[str, ...]:
    """Every way a picture could reach a model through the types here (M19.4.5).

    Checked against the dataclass fields rather than against behaviour, because the failure
    is not somebody deciding to send a screenshot: it is a field arriving with a sensible
    default and a helpful name, and being filled in by the runner two changes later because
    it was there. `brain.ops.halt.halt_gaps` refuses an expiry field on exactly this
    argument.

    Defaults to the types in this module, and takes an iterable so a test can plant a type
    carrying `screenshot` and prove the check is looking rather than that it is empty. An
    absence asserted against a scan that never scanned is the failure
    `tests/invariants/test_single_implementation.py` records finding in itself.
    """
    subjects = tuple(observed) or (Node, Snapshot)
    gaps: list[str] = []
    for subject in subjects:
        # `dataclasses.fields` is annotated against a protocol that only exists while type
        # checking, so a plain `type` cannot be proved to satisfy it. The cast buys nothing
        # to prove and the call raises on a non-dataclass, which is the honest failure for a
        # caller that handed one in.
        for field_ in fields(cast(Any, subject)):
            lowered = field_.name.lower()
            # One finding per field rather than one per matching word. `screenshot_png`
            # matches twice, and a report that says the same thing about one field twice is a
            # report somebody starts counting rather than reading.
            if any(shape in lowered for shape in IMAGE_SHAPED):
                gaps.append(
                    f"{subject.__name__}.{field_.name} would carry a picture or a raw "
                    "document into an observation, and a run that has just typed a "
                    "password has the password on the screen"
                )
    return tuple(gaps)
