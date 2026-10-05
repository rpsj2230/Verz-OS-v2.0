"""An agent's connector list is compiled into its ceiling, and decided nowhere else.

Over `brain.agents.binding` and `brain.agents.model.entitlement_ceiling`, with no database. The
database half, the stored list and the renamed entities, is `tests/unit/test_migration_0186.py`.

Task ids: M13.7.8, M13.8.1
"""

from __future__ import annotations

import ast
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.agents import binding
from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    entitlement_ceiling,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.roster import run_entitlement
from brain.knowledge.visibility import Visibility

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "brain"

#: Far from any wall clock: nothing here is about the present.
NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)

TICKET_READS = ("read:ticket", "read:ticket.subject")


def agent(*capabilities: str, connectors: tuple[str, ...] = ()) -> AgentRecord:
    """A company-wide agent whose authority names exactly `capabilities` and `connectors`."""
    return AgentRecord(
        agent_id="helpdesk_agent",
        display_name="Helpdesk agent",
        persona="Answers questions about the helpdesk.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            scope=Scope.unrestricted(),
            capabilities=tuple(Capability(value=one) for one in capabilities),
            connectors=connectors,
        ),
        created_by="u_steward",
    )


def person(*capabilities: str) -> EntitlementSet:
    """A person holding `capabilities` everywhere."""
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def held(ceiling: EntitlementSet) -> set[str]:
    return {one.capability.value for one in ceiling.grants}


# ------------------------------------------------------------------ the ceiling (M13.8.1)
def test_a_ceiling_drops_a_sources_reads_when_the_agent_does_not_name_the_source() -> None:
    """**The defect this module exists for.** An agent holding the helpdesk's reads and naming no
    connector compiled them into its ceiling, so it read the helpdesk whenever its caller could.
    Delete this and the connector list can go back to being read only at install."""
    assert held(entitlement_ceiling(agent(*TICKET_READS))) == set()


def test_a_ceiling_keeps_a_sources_reads_when_the_agent_names_the_source() -> None:
    """The sibling: binding is what admits the reads, so a ceiling that dropped every connector's
    entity whatever the list said would pass the test above. Delete this and an agent bound to its
    helpdesk can lose the helpdesk with nothing failing."""
    assert held(entitlement_ceiling(agent(*TICKET_READS, connectors=("freshdesk",)))) == set(
        TICKET_READS
    )


def test_naming_one_source_admits_none_of_another_s_reads() -> None:
    """A list is a list of sources, not a switch: an agent bound to the ledger holding the
    helpdesk's reads still reaches no ticket. Delete this and naming any connector could admit
    every connector's entities."""
    ceiling = entitlement_ceiling(
        agent(*TICKET_READS, "read:xero_invoice.status", connectors=("xero",))
    )

    assert held(ceiling) == {"read:xero_invoice.status", "read:xero_invoice"}


def test_a_capability_no_connector_provides_is_untouched_by_the_list() -> None:
    """The company's own knowledge, its uploaded tables and the demo are not connectors and no list
    can name them, so narrowing them by one would take away what nothing could give back. Delete
    this and every knowledge agent naming no connector retrieves nothing."""
    ceiling = entitlement_ceiling(agent("read:knowledge.document", "read:client.name"))

    assert {"read:knowledge.document", "read:client.name"} <= held(ceiling)


def test_an_entity_a_source_discovers_at_connect_time_is_bound_to_that_source() -> None:
    """Lark Base names one entity per table, `lark_<table>`, and none of them is known before an
    install connects it, so the prefix it declares is what binds them. Delete this and every Lark
    Base table is readable through an agent that names no Lark."""
    reads = ("read:lark_tblprojects", "read:lark_tblprojects.*")

    assert held(entitlement_ceiling(agent(*reads))) == set()
    assert held(entitlement_ceiling(agent(*reads, connectors=("lark_base",)))) == set(reads)


# ------------------------------------------------------------------ the run (M13.7.8)
def test_a_run_through_an_unbound_agent_cannot_read_a_source_its_caller_reads() -> None:
    """**The leaf's sentence, through the one intersection a run uses.** The person reads the
    helpdesk directly; the same person through an agent holding the helpdesk's reads but not
    bound to it reaches no ticket, and through one that is bound, does. Delete this and the
    binding can be compiled into a ceiling no run is computed from."""
    caller = person(*TICKET_READS)
    subject = Capability(value="read:ticket.subject")

    unbound = run_entitlement(caller, agent(*TICKET_READS))
    bound = run_entitlement(caller, agent(*TICKET_READS, connectors=("freshdesk",)))

    assert caller.holds(subject, NOW)
    assert not unbound.holds(subject, NOW)
    assert bound.holds(subject, NOW)


# ------------------------------------------------------------------ one source per entity
def test_no_entity_is_provided_by_two_sources() -> None:
    """**What makes an entity-level binding exact.** A grant names no source, so a name two
    sources provide reaches both. Counted over every connector, the demo and the product's own
    tables. Delete this and a new connector can ship a `contact` again, and an agent bound to it
    reads the other source's contacts."""
    from brain.tools.startup import BUILT_IN_ROW_ENTITIES, source_row_entities

    by_entity: dict[str, set[str]] = defaultdict(set)
    for one in BUILT_IN_ROW_ENTITIES:
        by_entity[one.entity].add("the product")
    for source, classified in source_row_entities().items():
        for one in classified:
            by_entity[one.entity].add(source)
    for entity, source in binding.providers().items():
        by_entity[entity].add(source)

    assert {entity: names for entity, names in by_entity.items() if len(names) > 1} == {}


def test_the_three_shared_names_are_named_for_their_sources() -> None:
    """The names this change gave the entities that were shared, spelled out rather than read
    from the constants that hold them, so a constant moved back to `contact` fails here. Delete
    this and `test_no_entity_is_provided_by_two_sources` is the only guard, and it passes for a
    name moved back while the other source is not shipped."""
    from brain.connectors import freshdesk, xero

    assert (freshdesk.CONTACT, xero.ENTITY_CONTACT, xero.ENTITY_INVOICE) == (
        "freshdesk_contact",
        "xero_contact",
        "xero_invoice",
    )
    assert binding.providers()["freshdesk_contact"] == "freshdesk"
    assert binding.providers()["xero_invoice"] == "xero"


def _declared(name: str, *entities: str) -> Any:
    """A declaration reading `entities` and nothing else, as `entities_of` reads one."""
    reading = SimpleNamespace(entities=lambda: entities)
    return SimpleNamespace(name=name, reading=reading, live=None, console=None, provides=())


def test_a_name_two_connectors_provide_is_refused() -> None:
    """The map refuses a collision rather than letting the second source win, which would bind
    the entity to whichever sorted last. Delete this and a shared name is silently given to one
    source and the other is read through agents bound to the first."""
    with pytest.raises(ValueError, match="provided by both"):
        binding.providers_of({"one": _declared("one", "record"), "two": _declared("two", "record")})


def test_two_connectors_with_their_own_names_are_both_mapped() -> None:
    """The sibling: a map that refused every pair would pass the test above. Delete this and
    `providers_of` can refuse the shipped set without a test naming why."""
    assert dict(
        binding.providers_of({"one": _declared("one", "a"), "two": _declared("two", "b")})
    ) == {"a": "one", "b": "two"}


def test_a_wiki_page_is_bound_to_lark_wiki_and_the_library_read_is_not() -> None:
    """Lark Wiki's pages are read by a module of its own under `read:wiki_page`, which no reading
    names, so the declaration says it provides that entity. The library read stays unbound, because
    it is the company's own documents. Delete this and an agent holding the library read reaches
    the wiki whether or not it names Lark Wiki, which is the gap `0187` closed."""
    reads = ("read:knowledge", "read:wiki_page")

    assert binding.provider_of("wiki_page") == "lark_wiki"
    assert held(entitlement_ceiling(agent(*reads))) == {"read:knowledge"}
    assert held(entitlement_ceiling(agent(*reads, connectors=("lark_wiki",)))) == set(reads)


def test_a_tool_declared_only_on_a_connectors_manifest_is_bound_to_it() -> None:
    """Freshdesk's contact read is declared by its manifest's tools and by no reading, so the map
    reads the manifest its form builds. Delete this and that tool's entity is bound to nothing,
    which leaves it readable through every agent."""
    assert binding.provider_of("freshdesk_contact") == "freshdesk"


# ------------------------------------------------------------------ decided once (M13.8.1)
def _calls_and_reads() -> tuple[dict[str, set[str]], set[str]]:
    """Every function calling `bound_capabilities`, by module, and every module reading an
    agent's connector list off its authority."""
    callers: dict[str, set[str]] = defaultdict(set)
    readers: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        module = ".".join(path.relative_to(SRC.parent).with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Call):
                    called = node.func
                    name = called.attr if isinstance(called, ast.Attribute) else None
                    if isinstance(called, ast.Name):
                        name = called.id
                    if name == "bound_capabilities":
                        callers[module].add(function.name)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "connectors"
                and (
                    (isinstance(node.value, ast.Attribute) and node.value.attr == "authority")
                    or (isinstance(node.value, ast.Name) and node.value.id == "authority")
                )
            ):
                readers.add(module)
    return dict(callers), readers


def test_connector_access_is_compiled_in_the_ceiling_and_decided_nowhere_else() -> None:
    """**M13.8.1's own sentence: a test fails if connector access is decided anywhere else.** The
    binding is applied by `entitlement_ceiling` alone, and an agent's connector list is read off
    its authority only there and where the record is carried or stored. Read from the source, so a
    second module deciding access from the list, or applying the binding a second time, fails here
    by name. Delete this and a route can grow its own idea of which sources an agent may read."""
    callers, readers = _calls_and_reads()

    assert callers == {"brain.agents.model": {"entitlement_ceiling"}}
    assert readers == {
        "brain.agents.model",
        "brain.agents.install",
        "brain.agents.install_store",
    }
