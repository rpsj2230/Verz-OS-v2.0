"""The shared prompt region, held to the two properties it exists for.

The first is byte identity across callers who share a provider cache, which is what M6.4.1
means and what nothing else in the repository checks: `catalogue.project` sorts by name, so
the *membership* is stable, and the bytes are a separate claim.

The second is that the shared region cannot acquire caller material. That failure has no
symptom, so the tests below assert it over the signature and over the types rather than over
what the code happens to do today.

Task ids: M6.4.1, M6.4.2
"""

from __future__ import annotations

import inspect
import os
from dataclasses import fields
from typing import Any, cast, get_args, get_type_hints

import pytest

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.core.principal import Principal
from brain.gate.cache_key import CacheKeyParts
from brain.gate.catalogue import ProjectedCatalogue
from brain.gate.context import GateContext, Recorder
from brain.gate.prefix import (
    CALLER_BEARING_TYPES,
    CALLER_MATERIAL_NAMES,
    HOUSE_RULES,
    SUBSTITUTION_MARKERS,
    PrefixSection,
    PromptLayout,
    StablePrefix,
    UnshareablePrefixError,
    build_prefix,
    lay_out,
    render_tool,
)


def a_tool(
    name: str,
    *,
    description: str = "Reads one record.",
    entity: str = "client",
    schema: dict[str, Any] | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        entity=entity,
        args_schema=schema or {},
        required_capability=f"read:{entity}.name",
        side_effect=SideEffect.NONE,
        identity_mode=IdentityMode.DELEGATED,
    )


#: Four tools whose sorted order is none of the orders they are handed over in below. One
#: element would make a sort a no-op and two would make a reversal look like a shuffle, so
#: the fixture has to discriminate before any assertion over it means anything.
APOLLO = a_tool("apollo.list_contact")
FRESHDESK = a_tool("freshdesk.read_ticket", entity="ticket")
LARK = a_tool("lark.read_client")
XERO = a_tool("xero.read_invoice", entity="invoice")

SORTED_ORDER = (APOLLO, FRESHDESK, LARK, XERO)
REGISTERED_BACKWARDS = (XERO, LARK, FRESHDESK, APOLLO)
REGISTERED_SHUFFLED = (FRESHDESK, APOLLO, XERO, LARK)


def tool_lines(prefix: StablePrefix) -> list[str]:
    """The tool block's lines, found by section rather than by position in the text."""
    for segment in prefix.segments:
        if segment.section is PrefixSection.TOOL_DEFINITIONS:
            return segment.text.splitlines()
    return []


# ------------------------------------------------------------------------------- M6.4.1
def test_two_registration_orders_produce_a_byte_identical_prefix() -> None:
    """**The reason this module exists.** A provider matches a cached prefix on the bytes,
    from the first character. Two callers holding the same tools in two different orders send
    the same list, the bytes differ at the first entry, and every request pays full price for
    a preamble that was identical in content. Nothing raises and nothing is logged, so the
    only symptom is the bill.

    Three orders rather than two, and one of them reverse-sorted, because a reversal of a
    correct sort would leave two shuffled inputs agreeing with each other while agreeing with
    nothing else. Compared on the digest as well as the text so a change to how the text is
    joined cannot pass by making both sides wrong in the same way.

    Delete this and the ordering can come from the registry again, which is the state the
    system is in without this module, and no other test in the repository would notice."""
    from_backwards = build_prefix(REGISTERED_BACKWARDS)
    from_shuffled = build_prefix(REGISTERED_SHUFFLED)
    from_sorted = build_prefix(SORTED_ORDER)

    assert from_backwards.text == from_shuffled.text
    assert from_backwards.text == from_sorted.text
    assert from_backwards.digest() == from_shuffled.digest() == from_sorted.digest()


def test_the_tool_block_is_in_one_canonical_order_whatever_the_registry_did() -> None:
    """The sibling of the test above, and it catches what that one cannot.

    Reversing the sort leaves every caller agreeing with every other caller, so byte identity
    still holds and the equality test above stays green. What breaks is the shared span with
    anybody who was already sending the canonical order, which is every request made before
    the change. So the order is asserted against a sort computed here, outside the module,
    rather than against the module's own idea of what order it produced.

    Delete this and `sorted(..., reverse=True)` is invisible."""
    lines = tool_lines(build_prefix(REGISTERED_SHUFFLED))

    assert len(lines) == len(SORTED_ORDER), "a tool went missing from the block"
    assert lines == sorted(lines), f"the tool block is not in canonical order: {lines}"
    assert lines[0].startswith("- apollo.list_contact")
    assert lines[-1].startswith("- xero.read_invoice")


def test_a_schema_written_key_by_key_in_another_order_produces_the_same_prefix() -> None:
    """`args_schema` is a `dict`, and a dictionary's insertion order is not part of what it
    means. Two callers whose schema was assembled in a different order would send different
    bytes for the same tool, which is the tool-ordering failure again one level down and
    harder to see, because the two schemas compare equal everywhere except in the prompt.

    The dictionaries below are built key by key rather than as literals, because a literal
    written twice in the same file tends to get tidied into the same order by whoever reads
    it next, and the test would then stop discriminating without anybody noticing.

    Delete this and `sort_keys=True` can go, and the same tool renders two ways depending on
    which connector happened to describe it first."""
    forwards: dict[str, Any] = {}
    forwards["client"] = {"type": "string"}
    forwards["since"] = {"type": "string"}
    forwards["limit"] = {"type": "integer"}

    backwards: dict[str, Any] = {}
    backwards["limit"] = {"type": "integer"}
    backwards["since"] = {"type": "string"}
    backwards["client"] = {"type": "string"}

    assert list(forwards) != list(backwards), "the fixture no longer discriminates"
    assert forwards == backwards

    one = build_prefix([a_tool("lark.read_client", schema=forwards)])
    other = build_prefix([a_tool("lark.read_client", schema=backwards)])

    assert one.text == other.text


def test_a_rendered_tool_carries_every_field_that_changes_what_it_does() -> None:
    """The positive case for the renderer, and a guard against a cheaper one.

    Rendering only the name and description would make the ordering above stable and the
    prompt wrong: two tools differing in the capability they need, or in whose credentials
    they run under, would render identically and share a cache entry that describes one of
    them. `identity_mode` is the sharpest of these, because a SERVICE tool runs under a shared
    credential and a DELEGATED one does not.

    Delete this and the renderer can be trimmed to a name and a sentence, and the sort above
    goes on passing."""
    delegated = render_tool(a_tool("lark.read_client"))
    service = render_tool(
        ToolDefinition(
            name="lark.read_client",
            description="Reads one record.",
            entity="client",
            required_capability="read:client.name",
            identity_mode=IdentityMode.SERVICE,
        )
    )

    assert delegated != service
    assert "read:client.name" in delegated
    assert IdentityMode.DELEGATED.value in delegated
    assert IdentityMode.SERVICE.value in service


# ------------------------------------------------------------------------------- M6.4.2
def types_within(annotation: object) -> set[type]:
    """Every class mentioned anywhere in an annotation, however deeply nested."""
    found: set[type] = set()
    if isinstance(annotation, type):
        found.add(annotation)
    for argument in get_args(annotation):
        found |= types_within(argument)
    return found


def test_the_prefix_builder_cannot_be_handed_a_caller() -> None:
    """**M6.4.2 asserted over the signature rather than over behaviour**, because behaviour
    today says nothing about what a parameter added tomorrow would do, and the failure has no
    symptom: caller material in the prefix does not make an answer wrong, it takes the hit
    rate to zero for everybody while every test stays green.

    Both halves matter. The type check stops a `GateContext` or a `ProjectedCatalogue`
    arriving, which is the shape somebody reaches for when they want the caller's tools. The
    name check stops `question: str`, which is the shape somebody reaches for when they want
    to put the question at the top of the prompt.

    Asserted over every parameter, so a parameter added later has to pass the same check.

    Delete this and the builder can grow a `context: GateContext` in one line, the prefix
    becomes per-caller, and the only thing that changes is the invoice."""
    signature = inspect.signature(build_prefix)
    hints = get_type_hints(build_prefix)

    assert signature.parameters, "the builder takes nothing, so this checks nothing"

    for name, parameter in signature.parameters.items():
        assert name not in CALLER_MATERIAL_NAMES, (
            f"build_prefix takes {name!r}, which names one request's caller"
        )
        annotation = hints.get(name)
        assert annotation is not None, f"{name} is unannotated, so nothing can be asserted"
        for found in types_within(annotation):
            assert found not in CALLER_BEARING_TYPES, (
                f"build_prefix takes {name}: {found.__name__}, which carries a caller"
            )
        assert parameter.kind is not inspect.Parameter.VAR_KEYWORD, (
            "**kwargs would let anything through unannotated"
        )


def test_the_forbidden_type_list_names_the_types_that_carry_a_caller() -> None:
    """The test above compares a signature against a list held in the module it is testing,
    which is green for every value that list could hold. This anchors the list to the classes
    themselves, imported here from the modules that define them.

    `ProjectedCatalogue` is on the list although it looks like the useful thing to pass: its
    `caller_specific` half is precisely the material the shared region must not contain, and a
    builder holding a catalogue is one attribute access away from putting it there.

    Delete this and the forbidden list can be emptied, and the signature test passes for a
    builder that takes a principal."""
    assert set(CALLER_BEARING_TYPES) >= {
        Principal,
        EntitlementSet,
        GateContext,
        Recorder,
        ProjectedCatalogue,
    }


def test_the_caller_material_names_cover_everything_a_gate_context_carries() -> None:
    """The same anchoring problem for the name list, solved the same way.

    `GateContext` is the definition of what the gate knows about one request, so every field
    on it is by construction a per-request value, and none of those words may name a parameter
    of the prefix builder. `question` is anchored separately to `CacheKeyParts`, which is the
    module that decides what makes two questions the same question.

    Deriving the set here rather than importing it means shrinking the constant fails, and
    adding a field to `GateContext` without adding its name fails too.

    Delete this and `CALLER_MATERIAL_NAMES` can lose `question` and the signature test above
    goes green for `build_prefix(tools, question=...)`."""
    per_request = {f.name for f in fields(GateContext)}

    assert per_request, "GateContext has no fields, so this anchors nothing"
    assert per_request <= CALLER_MATERIAL_NAMES, (
        f"not named as caller material: {sorted(per_request - CALLER_MATERIAL_NAMES)}"
    )
    assert "question" in {f.name for f in fields(CacheKeyParts)}
    assert "question" in CALLER_MATERIAL_NAMES


def test_a_callers_own_material_cannot_be_put_in_the_shared_region() -> None:
    """**The permission argument, made structural.** A shared provider cache is shared across
    people, so a retrieved row in it would be one caller's data sitting in a region another
    caller's request matches against. `brain.gate.answer_cache` keys on the entitlement hash
    for exactly this reason at the answer layer.

    The defence here is a type rather than a rule: the shared region is a `StablePrefix`, and
    a rendered row, a tool result and a question are all `str`. There is no conversion, so the
    only region text can reach is the one after the breakpoint.

    Delete this and `PromptLayout` accepts a string in the shared region, and the type
    distinction that carries the whole argument becomes a convention."""
    rows = "Acme Pte Ltd, contract value 84,000"

    # `cast` at the boundary the test exists to probe: mypy refuses this call, which is half
    # the guarantee, and the run-time refusal is the other half for anything reaching it
    # through untyped code.
    with pytest.raises(UnshareablePrefixError):
        PromptLayout(shared=cast(StablePrefix, rows))

    layout = lay_out(build_prefix(SORTED_ORDER), rows)

    assert rows not in layout.shared.text
    assert rows in layout.variable
    assert layout.blocks[layout.cache_breakpoint] == rows


def test_a_stable_prefix_cannot_be_built_outside_build_prefix() -> None:
    """The other half of the same argument. A type only one function can construct is a
    guarantee about what is in it; a type anybody can construct is a habit.

    The token is what makes `build_prefix`'s signature load-bearing: without it, somebody
    wanting the caller's question at the top of the prompt assembles a `StablePrefix` directly
    and the signature check above becomes decoration.

    The positive sibling is every other test in this file, all of which build one through
    `build_prefix`.

    Delete this and the constructor guard can go, and the shared region is whatever anybody
    puts in it."""
    with pytest.raises(UnshareablePrefixError):
        StablePrefix(segments=())

    with pytest.raises(UnshareablePrefixError):
        StablePrefix(segments=(), token=object())


def test_a_block_carrying_a_substitution_point_is_refused() -> None:
    """Nobody writes a caller's name into a static block deliberately. What happens is that a
    block acquires a placeholder, something upstream calls `format` on it, and the block is
    per-caller from then on while every docstring goes on calling it static.

    Refusing the placeholder is the last point at which that is detectable, because after the
    format call there is nothing left to see.

    The positive case is asserted beside the refusal, because a guard tested only by what it
    rejects is satisfied by a function that rejects everything, and a persona with an ordinary
    apostrophe or a percentage in it has to survive.

    Delete this and a persona reading "You are {client}'s account manager" ships, and the
    prefix is per-client from the first request."""
    with pytest.raises(UnshareablePrefixError):
        build_prefix(SORTED_ORDER, persona="You help {client} with their account.")

    with pytest.raises(UnshareablePrefixError):
        build_prefix(SORTED_ORDER, persona="You help %s with their account.")

    ordinary = "You answer questions about Verz's clients. Roughly 95% of them are hosting."
    built = build_prefix(SORTED_ORDER, persona=ordinary)

    assert ordinary in built.text


def test_the_house_rules_are_constant_text_with_nowhere_to_interpolate() -> None:
    """The house rules are the widest-shared bytes in the system, sent by every agent on every
    request, so a placeholder in one of them would cost the cache more than a placeholder
    anywhere else.

    Checked against `SUBSTITUTION_MARKERS` rather than against a list written here, so a marker
    added to the guard is applied to the rules without anybody remembering to.

    Delete this and a rule can acquire "{company}" and the whole estate's prefix becomes
    per-tenant, which on a single-tenant deployment looks fine right up until it does not."""
    assert HOUSE_RULES, "there are no house rules, so this checks nothing"
    assert len(set(HOUSE_RULES)) == len(HOUSE_RULES), "a house rule is written twice"

    for rule in HOUSE_RULES:
        assert rule.strip(), "a house rule is blank"
        for marker in SUBSTITUTION_MARKERS:
            assert marker not in rule, f"a house rule carries {marker!r}"


def test_the_widest_shared_material_comes_first() -> None:
    """M6.4.2 is "the stable prefix first", and inside the prefix the same argument applies
    again: the bytes shared by the most requests belong at the front.

    Every agent sends the same house rules; one agent's callers share its persona; only the
    callers who reach the same tools share the tool block. Ordering those the other way round
    would cut the common span to nothing the moment two agents differed by one tool.

    Asserted as the sections being ascending rather than as three literal positions, so a
    section inserted later is placed by its own number and this test still means what it says.

    Delete this and the assembly order can be rearranged for readability, and two agents stop
    sharing anything."""
    prefix = build_prefix(SORTED_ORDER, persona="You answer questions about clients.")
    sections = [segment.section for segment in prefix.segments]

    assert sections == sorted(sections), f"sections are out of order: {sections}"
    assert sections[0] is PrefixSection.HOUSE_RULES
    assert PrefixSection.HOUSE_RULES < PrefixSection.AGENT_PERSONA < PrefixSection.TOOL_DEFINITIONS


def test_two_agents_share_the_house_rules_and_diverge_after_them() -> None:
    """The property the ordering above is *for*, measured rather than argued.

    Two agents with different personas and different tools still send an identical leading
    span, and that span is the whole house-rules block. This is the positive case for the
    module: everything else here asserts that something cannot happen, and a prefix builder
    that returned the empty string would satisfy all of it.

    Delete this and the sharing claim in the module docstring has nothing behind it."""
    support = build_prefix([FRESHDESK], persona="You answer questions about tickets.")
    finance = build_prefix([XERO], persona="You answer questions about invoices.")

    shared = os.path.commonprefix([support.text, finance.text])

    assert support.text != finance.text, "the fixture no longer discriminates"
    assert shared.startswith("\n".join(HOUSE_RULES))
    assert len(shared) >= len("\n".join(HOUSE_RULES))


def test_a_prefix_with_no_tools_still_carries_the_house_rules() -> None:
    """The fast lane projects an empty catalogue by design, and an agent under configuration
    has none yet. Emitting a blank tool section for them would put a separator in the bytes
    for something that is not there, so those requests would share nothing with the requests
    that do have tools even up to the point where the two agree.

    Delete this and the empty case grows a trailing separator, and the sharing above breaks
    for exactly the requests that are cheapest to serve."""
    empty = build_prefix([])

    assert [segment.section for segment in empty.segments] == [PrefixSection.HOUSE_RULES]
    assert empty.text == "\n".join(HOUSE_RULES)
    assert not empty.text.endswith("\n")


def test_the_breakpoint_names_the_first_block_the_provider_must_not_cache() -> None:
    """The breakpoint is the number handed to a provider as "retain this much", so an
    off-by-one either wastes the last shared block or, in the direction that matters, tells
    the provider to cache the first block of one caller's data.

    Asserted against the block list rather than against a count, so a change to how the
    regions are joined cannot leave the number right and the split wrong.

    Delete this and `cache_breakpoint` can return zero and every request pays full price,
    which is the same failure the ordering tests guard against arriving by another road."""
    prefix = build_prefix(SORTED_ORDER, persona="You answer questions about clients.")
    layout = lay_out(prefix, "How many hours are left on Acme?", "client Acme: hours 12")

    assert layout.cache_breakpoint == len(prefix.segments)
    assert layout.blocks[: layout.cache_breakpoint] == prefix.blocks
    assert layout.blocks[layout.cache_breakpoint :] == layout.variable
    assert layout.text.startswith(prefix.text)
    assert layout.shared_characters == len(prefix.text)


def test_two_prefixes_agree_on_a_digest_only_when_their_bytes_agree() -> None:
    """The digest is what a trace reports so somebody can see whether two requests shared a
    prefix. A digest over the structure rather than the bytes would agree while the bytes
    differed, which reports a cache hit that never happened, and a number nobody can trust is
    worse than no number.

    The algorithm is pinned against `hashlib` here rather than against the module's own
    output, so switching to a shorter or non-cryptographic digest fails.

    Delete this and the digest can be computed over the segment list, and the trace starts
    claiming hits that did not occur."""
    import hashlib

    one = build_prefix(SORTED_ORDER, persona="You answer questions about clients.")
    same = build_prefix(REGISTERED_BACKWARDS, persona="You answer questions about clients.")
    other = build_prefix(SORTED_ORDER, persona="You answer questions about invoices.")

    assert one.digest() == same.digest()
    assert one.digest() != other.digest()
    assert one.digest() == hashlib.sha256(one.text.encode("utf-8")).hexdigest()
