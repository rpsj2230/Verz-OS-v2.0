"""What a person declared about a system, written before any run and read instead of a page.

A planner that may not read the page still has to know that the invoice list is at
`/invoices` and that the button on it says Export. Something has to supply that, and the
choice of what is the difference between this package and a prompt-injection surface: either
the agent finds out by looking, or somebody wrote it down in advance. This module is the
second answer. A surface map is a declaration by a person who has an account on that system,
reviewed the same way a connector is, and it is the only description of a target that
anything in this package plans against.

**The cost of that choice is real and worth stating.** A declared map goes stale when the
vendor moves a button, and the run then fails rather than adapting. That is the trade being
made deliberately: a system that adapts to what the page now says is a system that does what
the page now says, and a page that has been changed by somebody who wants our session is
indistinguishable from a page whose vendor shipped a redesign. Failing on a redesign is a
support ticket; adapting to an attacker is a payment run.

**A click is classified as a write, and that is not conservatism for its own sake.** What a
click does is decided by the page, not by us: the same node can be a link, a form submit or
a JavaScript handler that posts. Since the party deciding is the untrusted one, every verb
that dispatches an event to the page is counted against the write budget in
`brain.browsing.envelope`. Only `OPEN` and `READ` are treated as reads, and both are things
we do to the page rather than through it.

**`api_tools` is here rather than in the skill loader.** M19.6.7 refuses a browser skill for
a job an API tool already does, and the fact that a tool exists for this target belongs
beside the target rather than in the module that refuses. A list maintained where the
refusal happens is a list nobody updates when a connector ships, and the refusal then stops
firing exactly as the API becomes available.

Rejected: normalising origins here. `brain.channels.widget.normalise_origin` already folds a
scheme and a host, refuses `null`, refuses a credential in the authority and refuses a port
outside the valid range, and it carries three mutation-tested comments explaining which of
its checks are load bearing. A second origin parser is a second answer to whether
`HTTPS://Bank.example./` is the same place as `https://bank.example`, and the wrong answer
is the one that admits a look-alike.

Task ids: M19.2.4
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Final

from brain.channels.widget import normalise_origin
from brain.core.entitlement import Capability

#: What a target and a surface may be called: a lowercase slug, so that a name is safe in a
#: policy key, a trace field and a log line without anybody quoting it.
NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_]*$")


class TargetError(Exception):
    """A target or surface was declared in a way that cannot be planned against safely."""


class Verb(enum.StrEnum):
    """What a step may do. Six members and a hard split down the middle.

    Ordered read verbs first only for reading; nothing compares them. `IntEnum` would invite
    a comparison, and `OPEN < CLICK` means nothing that anybody should rely on.
    """

    #: Navigate to a declared surface. Nothing on the page is touched.
    OPEN = "open"
    #: Take a snapshot and read declared fields out of it.
    READ = "read"
    #: Dispatch a click. What that does is the page's decision, which is why it is a write.
    CLICK = "click"
    #: Enter text into a field, which is also how a credential reaches a login form.
    TYPE = "type"
    #: Submit a form. The one verb whose name matches what everyone assumes a write is.
    SUBMIT = "submit"
    #: Send a file. Separate from TYPE because what leaves is a document rather than a value.
    UPLOAD = "upload"


#: The verbs that only observe. Everything else is a write, and the set is defined this way
#: round on purpose: a seventh verb added later is a write until somebody argues otherwise,
#: rather than a read until somebody notices.
READ_VERBS: Final[frozenset[Verb]] = frozenset({Verb.OPEN, Verb.READ})

#: Why `CLICK` is over here rather than beside `READ`.
THE_PAGE_DECIDES_WHAT_A_CLICK_DOES: Final = (
    "A click is not a read that happens to move the pointer. The node it lands on may be a "
    "link, a form submit or a handler that posts a payment, and which of those it is was "
    "decided by whoever wrote the page. Classifying it by what it usually does means "
    "classifying it by what an honest page usually does, and the page this package exists "
    "for is the dishonest one. Every verb that dispatches an event to the page is counted "
    "against the write budget."
)

#: Why the map is written by a person and never learned from the page.
A_MAP_LEARNED_FROM_THE_PAGE_IS_A_MAP_THE_PAGE_WROTE: Final = (
    "A target registry that filled itself in by crawling would be a planner reading page "
    "content with an extra step and a database row in between. The staleness is the price "
    "and it is the cheaper failure: a moved button fails a run, and a learned map lets a "
    "compromised page describe a surface that does what it wants."
)


def is_write(verb: Verb) -> bool:
    """Whether this verb changes anything, decided by exclusion from `READ_VERBS`."""
    return verb not in READ_VERBS


@dataclass(frozen=True)
class Surface:
    """One declared place on a target, and the only things a plan may do there.

    `capability` is what a caller must hold for a step on this surface to survive envelope
    compilation. It is a `Capability` rather than a string, so an unparseable one fails when
    the surface is declared instead of making the surface silently unreachable at run time,
    which is the argument `brain.tools.registry.capability_for` makes at length.
    """

    name: str
    #: The origin this surface lives on, normalised. Every action there is checked against it.
    origin: str
    #: The path a run navigates to. Recorded so a plan can be read by a person.
    path: str
    verbs: frozenset[Verb]
    capability: Capability
    #: Declared field names a READ on this surface may return. Empty means the surface is
    #: navigation only, which is a legitimate thing for a login page to be.
    reads: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not NAME_RE.match(self.name):
            msg = f"surface name {self.name!r} is not a lowercase slug"
            raise TargetError(msg)
        # The empty case first, and it is not covered by the check below. `normalise_origin`
        # returns the empty string for everything it cannot parse, so an empty declared origin
        # passes "is normalised" by comparing "" with "", and `Target.allows_origin` would
        # then admit every action whose origin failed to parse. Mutation testing found this in
        # the sibling check on `Binding`.
        if not self.origin:
            msg = (
                f"surface {self.name!r} declares no origin; the empty string is what "
                "normalisation returns for anything unparseable, so allowing it would admit "
                "every action whose origin could not be read"
            )
            raise TargetError(msg)
        if normalise_origin(self.origin) != self.origin:
            msg = (
                f"surface {self.name!r} declares origin {self.origin!r}, which is not the "
                "normalised form; comparing a normalised action origin against a raw "
                "declaration is how a trailing slash becomes a refusal nobody can explain"
            )
            raise TargetError(msg)
        if not self.path.startswith("/"):
            msg = f"surface {self.name!r} has path {self.path!r}, which is not rooted at /"
            raise TargetError(msg)
        if not self.verbs:
            msg = (
                f"surface {self.name!r} declares no verbs, so every step on it would be "
                "refused and the surface exists only to look like a capability"
            )
            raise TargetError(msg)
        if Verb.READ in self.verbs and not self.reads:
            msg = (
                f"surface {self.name!r} admits READ and declares no fields, so what a read "
                "returns would be decided by whatever the page happened to contain"
            )
            raise TargetError(msg)

    def admits(self, verb: Verb) -> bool:
        return verb in self.verbs

    def writes(self) -> frozenset[Verb]:
        """The declared verbs that change something. Used to size the envelope's budget."""
        return frozenset(verb for verb in self.verbs if is_write(verb))


@dataclass(frozen=True)
class Target:
    """One system a browser may be pointed at, and everything declared about it.

    `origins` is the allowlist `brain.browsing.enforcer` checks every action against, and it
    is a set rather than one value because a real system serves its login on an identity host
    and its application on another. It is not derived from the surfaces: a surface that
    slipped in with an origin nobody meant to allow would then allow itself.
    """

    name: str
    origins: frozenset[str]
    surfaces: tuple[Surface, ...] = ()
    #: Tool names that already do this target's work without a browser. See M19.6.7.
    api_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not NAME_RE.match(self.name):
            msg = f"target name {self.name!r} is not a lowercase slug"
            raise TargetError(msg)
        if not self.origins:
            msg = (
                f"target {self.name!r} allows no origin, so either every action is refused "
                "or somebody later reads the empty set as no restriction"
            )
            raise TargetError(msg)
        for origin in self.origins:
            if not origin:
                msg = (
                    f"target {self.name!r} allows the empty origin, which is what "
                    "normalisation returns for anything it cannot parse; the allowlist would "
                    "then admit every action whose origin could not be read"
                )
                raise TargetError(msg)
            if normalise_origin(origin) != origin:
                msg = f"target {self.name!r} allows {origin!r}, which is not a normalised origin"
                raise TargetError(msg)
        names = [surface.name for surface in self.surfaces]
        if len(names) != len(set(names)):
            msg = f"target {self.name!r} declares two surfaces with one name"
            raise TargetError(msg)
        for surface in self.surfaces:
            if surface.origin not in self.origins:
                msg = (
                    f"surface {surface.name!r} sits on {surface.origin!r}, which target "
                    f"{self.name!r} does not allow; a surface that widened the allowlist by "
                    "existing would let a declaration authorise itself"
                )
                raise TargetError(msg)

    def surface(self, name: str) -> Surface | None:
        for one in self.surfaces:
            if one.name == name:
                return one
        return None

    def allows_origin(self, origin: str) -> bool:
        """Exact membership after normalisation, never a suffix test, never on a parse failure.

        A suffix test is how `bank.example.evil.test` matches an allowlist entry for
        `bank.example`, and it reads as the more forgiving option right up to the moment it
        forgives the wrong host.

        The `bool(normalised)` half is deliberately stated here as well as refused in the
        constructor. `normalise_origin` answers with the empty string for `null`, for a
        `file://` document and for anything malformed, so a membership test alone would admit
        all of them the moment an empty entry reached the set by any route.
        """
        normalised = normalise_origin(origin)
        return bool(normalised) and normalised in self.origins


@dataclass(frozen=True)
class TargetRegistry:
    """Every declared target. Frozen, because a registry a run can add to is not a ceiling.

    A dataclass holding a tuple rather than a mutable registry like
    `brain.tools.registry.ToolRegistry`, which has a `freeze` step for a good reason of its
    own: tools are registered by import side effects across many modules and cannot all be
    known at construction. Targets are configuration, read in one place, and there is no
    moment at which one is discovered.
    """

    targets: tuple[Target, ...] = ()

    def __post_init__(self) -> None:
        names = [target.name for target in self.targets]
        if len(names) != len(set(names)):
            msg = "two targets share a name, and which one a plan resolves to would be import order"
            raise TargetError(msg)

    def get(self, name: str) -> Target | None:
        for target in self.targets:
            if target.name == name:
                return target
        return None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(target.name for target in self.targets))

    def origins(self) -> frozenset[str]:
        """Every origin any declared target allows. The union is deliberate and is not a
        policy: `brain.browsing.enforcer` checks an action against one target's set, and this
        exists for an operator asking what this installation may reach at all."""
        found: set[str] = set()
        for target in self.targets:
            found |= target.origins
        return frozenset(found)
