"""The part of a prompt every caller sends identically, and why nothing of theirs may enter it.

A provider bills a cached prefix at a fraction of the ordinary input rate, and only when the
bytes match exactly, from the first character, across the requests meant to share it. So a
prefix is not a tidy way to arrange a prompt. It is a byte-for-byte contract between requests
that have never met, and everything in this module follows from that.

**The ordering is derived from the tools and never from how they arrived.** A registry is a
mapping, a projection walks it, and both hand back an order that is an accident of insertion.
Two callers holding the same tools would then send the same list in two different orders, the
bytes would differ at the first entry, and every request would pay full price for a preamble
that was identical in content. Nothing raises, nothing is logged, and the only symptom is a
bill. `build_prefix` sorts on the rendered text of each definition, which is total because
strings order totally and because a rendered form is a function of the definition alone, and
it renders `args_schema` with sorted keys so a dictionary's insertion order cannot reach the
bytes either. `brain.gate.catalogue.project` already sorts by name for the same reason; this
module is what makes the *bytes* stable, not merely the membership.

**The builder cannot reach a caller, and its signature is what says so.** There is no
parameter here of a type that carries a principal, an entitlement, a gate context or a
projected catalogue, and `tests/unit/test_prefix.py` asserts that over the signature rather
than over behaviour. Behaviour today says nothing about what a parameter added tomorrow would
do, and the failure being prevented is invisible: caller material in the prefix does not make
an answer wrong, it silently takes the hit rate to zero for everybody and no test goes red.

Being honest about the limit of that: a signature cannot stop somebody passing a question in
a `str`. What it does stop is the whole shape where this function reaches into a request for
itself. The remaining route by which caller material historically gets into a block labelled
static is templating, so `A_SUBSTITUTION_POINT_IS_HOW_CALLER_MATERIAL_GETS_IN` is checked:
a persona carrying `{client}` is one `str.format` away from being per-caller.

**A shared prefix is not a shared answer, and the difference is the permission boundary.**
See `A_SHARED_PREFIX_IS_NOT_A_SHARED_ANSWER`. `brain.gate.answer_cache` keys on the
entitlement hash because two people asking the same words with different reach must get
different answers. Nothing of that kind can happen here, and the reason is structural rather
than careful: the shared region of a `PromptLayout` is typed as `StablePrefix`, a
`StablePrefix` can only be built by `build_prefix`, and `build_prefix` has no way to obtain a
row, a tool result or a question. A caller's own material is a `str` and there is exactly one
place a `str` may go, which is after the breakpoint.

Rejected: rendering the prefix inside `catalogue.project`, which already knows which tools are
shared. It would put the byte format of a prompt inside the module that decides permissions,
and the next person changing the wording of a tool description would be editing the projector.
Rejected too: caching the rendered prefix in this process. The provider is the cache; a second
one here would be a second thing to invalidate when a tool's description changes, and the
copy that goes stale is the one being sent.

Task ids: M6.4.1, M6.4.2
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import ToolDefinition
from brain.core.principal import Principal
from brain.gate.catalogue import ProjectedCatalogue
from brain.gate.context import GateContext, Recorder

# ------------------------------------------------------------------ written-down reasons
#: Where the line between a safe shared cache and a permission leak actually falls.
A_SHARED_PREFIX_IS_NOT_A_SHARED_ANSWER = (
    "A provider cache is shared across callers, so what may enter it is a permission "
    "question and not a performance one. A prefix is safe to share because it holds only "
    "material every caller in the sharing set would have been sent anyway: standing "
    "instructions, an agent's persona, and the definitions of tools each of them was "
    "already shown. It holds no retrieved row, no tool result and no question. An answer is "
    "not safe to share, which is why brain.gate.answer_cache keys on the entitlement hash: "
    "two people asking the same words with different reach must receive different answers. "
    "The test is therefore never 'is this cached' but 'was this derived from one caller's "
    "data'. Anything derived from one caller's data goes after the breakpoint, where it is "
    "sent in full on every request and cached for nobody."
)

#: Why the prefix builder's signature is the enforcement rather than a rule in review.
THE_PREFIX_BUILDER_CANNOT_SEE_THE_CALLER = (
    "Putting caller material in the prefix does not break correctness. It destroys the hit "
    "rate for everybody and nothing anywhere fails, so no test turns red and no alert "
    "fires. A guard that has to be remembered is therefore worthless here, because the "
    "thing it guards against has no symptom. build_prefix takes no parameter whose type "
    "carries a principal, an entitlement, a gate context or a projected catalogue, and no "
    "parameter named after one; the signature is asserted, so a parameter added later has "
    "to pass the same check as the ones here today."
)

#: Why the ordering is a function of the definitions and of nothing else.
ORDERING_IS_TOTAL_SO_THE_BYTES_ARE_IDENTICAL = (
    "Two callers who hold the same tools must send the same bytes. Registration order, "
    "mapping iteration order and set iteration order are all accidents of how a list was "
    "assembled, and any of them reaching the output makes the shared prefix shared in "
    "content and different in bytes, which is the same as having no shared prefix at all. "
    "So the tools are sorted on their rendered text, which orders totally, and every "
    "dictionary inside a definition is rendered with sorted keys."
)

#: Why an unfilled substitution point is refused in the shared region.
A_SUBSTITUTION_POINT_IS_HOW_CALLER_MATERIAL_GETS_IN = (
    "Nobody writes a caller's name into a static block on purpose. What happens is that a "
    "block acquires a placeholder, somebody upstream calls format on it, and the block is "
    "per-caller from that moment while still being called static everywhere it is "
    "described. Refusing a placeholder in the shared region is the cheapest point at which "
    "that is visible, because after the format call there is nothing left to detect."
)

#: Parameter and field names that would mean a function can see one request's caller. Held
#: here as the written-down rule; `tests/unit/test_prefix.py` anchors it to the fields of
#: `GateContext` and to `cache_key.CacheKeyParts.question` so it cannot be quietly shrunk,
#: and `tests/unit/test_effort.py` holds the per-lane pins to the same list.
CALLER_MATERIAL_NAMES: frozenset[str] = frozenset(
    {
        "asker",
        "caller",
        "channel",
        "context",
        "ent_hash",
        "entitlement",
        "entitlements",
        "lane",
        "payload",
        "principal",
        "query",
        "question",
        "received_at",
        "recorder",
        "records",
        "result",
        "results",
        "retrieved",
        "rows",
        "trace_id",
        "traffic_class",
        "user",
    }
)

#: Types that carry one request's caller. None of these may appear anywhere in the prefix
#: builder's signature. `ProjectedCatalogue` is here although it looks harmless: its
#: `caller_specific` half is exactly the material this module exists to keep out, and a
#: builder holding one would be one attribute access away from putting it in.
CALLER_BEARING_TYPES: tuple[type, ...] = (
    Principal,
    EntitlementSet,
    GateContext,
    Recorder,
    ProjectedCatalogue,
)

#: Substrings that mark a block as a template rather than as text. `%`-style formatting is
#: represented by its specifiers rather than by a bare `%`, because a percentage is ordinary
#: English and refusing it would make the guard something people work around.
SUBSTITUTION_MARKERS: tuple[str, ...] = ("{", "}", "%s", "%d", "%(")


class UnshareablePrefixError(Exception):
    """Raised when something offered for the shared region cannot be shared.

    A programming error rather than an outcome a person is shown, so deliberately not a
    `BrainError`: nobody asking a question ever sees this, and a request that reached it has
    a prompt assembled wrongly rather than a permission problem.
    """


# ----------------------------------------------------------------------- the shared region
class PrefixSection(enum.IntEnum):
    """The order of the shared region. Numbers leave room to insert without renumbering.

    The order is by breadth of sharing, widest first, and that is the whole of the reasoning.
    Every agent in the company sends the same house rules, so those are the bytes the largest
    number of requests have in common and they must come first. A persona is shared by every
    caller of one agent. Tool definitions are shared by every caller of one agent who reaches
    the same tools, which is the narrowest of the three. Putting the narrowest first would cut
    the common span to nothing the moment two agents differed by one tool.
    """

    HOUSE_RULES = 10
    AGENT_PERSONA = 20
    TOOL_DEFINITIONS = 30


#: The standing instructions every agent in the company carries, identical for every caller.
#:
#: They restate the rules this system is built on rather than adding new ones, because prompt
#: material is a request to a model and never an enforcement: the redactor is what withholds a
#: field, and `brain.core.redaction` is what makes DENIED and ABSENT indistinguishable. What
#: these buy is a model that does not narrate around a guard that already ran, which is the
#: one leak the enforcement layer cannot close, because the model's own explanation of what it
#: just did is the channel nobody audits.
HOUSE_RULES: tuple[str, ...] = (
    "Answer only from the records and documents supplied with this request. "
    "Where they do not contain the answer, say that plainly.",
    "Never say that something exists but was withheld, and never describe a gap in what you "
    "were given. A record you were not given is absent as far as this answer goes.",
    "Never state or imply how many items were not shown, including by subtraction.",
    "Name the record and the field behind every figure you give.",
)


def _check_shareable(text: str, what: str) -> None:
    """Refuse a block that carries a substitution point. See the reason constant."""
    for marker in SUBSTITUTION_MARKERS:
        if marker in text:
            msg = (
                f"{what} contains {marker!r}, which makes it a template rather than a "
                "static block; a formatted block is per-caller and shares with nobody. "
                f"{A_SUBSTITUTION_POINT_IS_HOW_CALLER_MATERIAL_GETS_IN}"
            )
            raise UnshareablePrefixError(msg)


def render_tool(tool: ToolDefinition) -> str:
    """One tool definition as bytes, and as a function of the definition alone.

    Every field that changes what the tool does is in here, so two definitions that differ
    render differently and cannot silently share a cache entry. `args_schema` goes through
    `json.dumps` with sorted keys because it is a `dict` and a dictionary's insertion order
    is not part of what it means: two callers whose schema was built key by key in a
    different order would otherwise send different bytes for the same tool.

    `default=str` is there because `args_schema` is typed `dict[str, Any]` and a value the
    encoder does not know would otherwise raise here, at prompt assembly, for a tool that
    works perfectly well. Rendering it as its `repr` is stable, which is all this needs.
    """
    schema = json.dumps(tool.args_schema, sort_keys=True, separators=(",", ":"), default=str)
    return (
        f"- {tool.name} (object: {tool.entity}, needs: {tool.required_capability}, "
        f"effect: {tool.side_effect.value}, identity: {tool.identity_mode.value}) "
        f"{tool.description} args={schema}"
    )


@dataclass(frozen=True)
class PrefixSegment:
    """One block of the shared region, and which section it is."""

    section: PrefixSection
    text: str


#: Only `build_prefix` holds this, so only `build_prefix` can make a `StablePrefix`. The same
#: device as `catalogue._PROJECTION_TOKEN`, used for the same reason: a type that cannot be
#: constructed elsewhere is a guarantee, while a type anybody can construct is a habit.
_PREFIX_TOKEN = object()


@dataclass(frozen=True)
class StablePrefix:
    """The shared region of one prompt: identical bytes for every caller who shares it.

    **This type cannot be constructed outside `build_prefix`.** That is what makes the
    permission argument structural. `PromptLayout.shared` is typed as a `StablePrefix`, so
    the only way to put anything into the shared region is to go through a function that has
    no means of obtaining a caller's rows, tool results or question. A `str` field there
    would have been a hole the size of the whole module.
    """

    segments: tuple[PrefixSegment, ...]
    #: Not data. The constructor guard.
    token: object = None

    def __post_init__(self) -> None:
        if self.token is not _PREFIX_TOKEN:
            msg = (
                "a stable prefix may only be built by brain.gate.prefix.build_prefix; "
                f"{THE_PREFIX_BUILDER_CANNOT_SEE_THE_CALLER}"
            )
            raise UnshareablePrefixError(msg)

    @property
    def blocks(self) -> tuple[str, ...]:
        return tuple(segment.text for segment in self.segments)

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)

    def digest(self) -> str:
        """A fingerprint of the bytes, so a trace can say whether two requests shared.

        Over the joined text rather than over the segment list, because the joined text is
        what the provider actually matches on. A digest over the structure could agree while
        the bytes differed, which would report a cache hit that never happened.
        """
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def build_prefix(
    tools: Iterable[ToolDefinition],
    *,
    persona: str = "",
) -> StablePrefix:
    """The shared region, in a fixed order, from material that belongs to nobody in particular.

    Note what is not in this signature, and see `THE_PREFIX_BUILDER_CANNOT_SEE_THE_CALLER`.
    There is no principal, no entitlement, no gate context and no question, and there is no
    `ProjectedCatalogue` either: this takes the tool definitions themselves, so the
    `caller_specific` half of a catalogue is not reachable from in here even by accident.

    `tools` is an `Iterable` rather than a `Sequence` on purpose. Accepting an unordered
    collection makes it obvious that the caller's order is not consulted, and the sort below
    means it cannot be.

    The house rules are a module constant rather than a parameter for the same reason: a
    parameter is somewhere an order could differ between two callers who meant the same thing.
    `persona` is a parameter because it genuinely varies, by agent and not by caller, and
    leaving it out would push the largest constant block in a prompt to after the breakpoint.

    An empty section is omitted rather than emitted blank, so the bytes never carry a
    separator for something that is not there.
    """
    _check_shareable(persona, "the persona")
    for rule in HOUSE_RULES:
        _check_shareable(rule, "a house rule")

    segments: list[PrefixSegment] = []
    segments.append(PrefixSegment(PrefixSection.HOUSE_RULES, "\n".join(HOUSE_RULES)))

    if persona.strip():
        segments.append(PrefixSegment(PrefixSection.AGENT_PERSONA, persona.strip()))

    # Sorted on the rendered text, which is total and is a function of each definition
    # alone. See `ORDERING_IS_TOTAL_SO_THE_BYTES_ARE_IDENTICAL`. Two definitions that
    # render identically are indistinguishable in the output, so their relative order
    # cannot change the bytes.
    rendered = sorted(render_tool(tool) for tool in tools)
    if rendered:
        segments.append(PrefixSegment(PrefixSection.TOOL_DEFINITIONS, "\n".join(rendered)))

    return StablePrefix(segments=tuple(segments), token=_PREFIX_TOKEN)


# ------------------------------------------------------------------------- the breakpoint
@dataclass(frozen=True)
class PromptLayout:
    """A whole prompt, split at the point the provider is asked to cache.

    `cache_breakpoint` is the index of the first block that is not shared, which is the
    number of blocks the provider is told to retain. Reported rather than implied, for the
    reason `catalogue.cache_prefix_length` gives: a number nobody can see is a number nobody
    notices going to zero.

    The two regions are different types and that is the entire safety argument. `shared` is a
    `StablePrefix`, which only `build_prefix` can make. `variable` is `str`, which is what a
    question, a rendered row and a tool result all are. There is nowhere to put a caller's
    material except after the breakpoint, and no conversion from one region to the other.
    """

    shared: StablePrefix
    #: Everything derived from this one request: the question, the retrieved rows, the tool
    #: results so far, and any instruction that varies per request such as an output length.
    variable: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Checked at run time as well as by mypy, because the value this refuses is a plain
        # string, and a plain string is what every piece of caller material is: a question, a
        # rendered row, a tool result. mypy alone covers only the callers it can see.
        #
        # The token is what is checked rather than the class, for two reasons. `isinstance`
        # against the declared type is provably unreachable under `warn_unreachable`, so it
        # would have to be silenced to compile at all, and a silenced check reads as
        # decoration. And the token is the stronger question: a subclass constructed around
        # `__post_init__` would pass an `isinstance` and still hold whatever was put in it.
        if getattr(self.shared, "token", None) is not _PREFIX_TOKEN:
            msg = (
                "the shared region must be a StablePrefix built by build_prefix, not text "
                f"assembled by a caller. {A_SHARED_PREFIX_IS_NOT_A_SHARED_ANSWER}"
            )
            raise UnshareablePrefixError(msg)

    @property
    def cache_breakpoint(self) -> int:
        return len(self.shared.segments)

    @property
    def blocks(self) -> tuple[str, ...]:
        return self.shared.blocks + self.variable

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)

    @property
    def shared_characters(self) -> int:
        """How much of this prompt is eligible for the provider cache.

        Characters rather than tokens, because tokenising needs the provider's own
        vocabulary and this module deliberately does not depend on one. It is a ratio worth
        watching over time rather than a figure to bill against.
        """
        return len(self.shared.text)


def lay_out(prefix: StablePrefix, *caller_blocks: str) -> PromptLayout:
    """Put this request's own material after the shared region.

    A function rather than leaving callers to build the dataclass, so there is one obvious
    place to read and one place a future trace record can attach. It takes the caller's
    blocks last and variadically because that is the order they go in, and because a keyword
    argument would invite somebody to pass one to the wrong region.
    """
    return PromptLayout(shared=prefix, variable=tuple(caller_blocks))
