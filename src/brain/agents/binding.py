"""Which source provides each entity, and an agent's capabilities narrowed to the sources it names.

M13.7.8 asks that an agent run reach only the connectors bound to that agent, and that a call to
any other be refused by the gate even when the asking person could reach that source directly.
M13.8.1 asks that the connector list compile into the agent's ceiling, that the gate resolve it
through the one intersection used for every ceiling entry, and that a test fail if connector
access is decided anywhere else.

**The connector list is compiled into the ceiling, and nowhere else decides it.** Until this
module an agent's `connectors` were read once, by `brain.agents.install.connector_readiness`, to
say whether the install served them, and then dropped. A run's reach was the caller's narrowed by
`authority.capabilities` alone, so an agent holding `read:ticket.*` and naming no helpdesk read
the helpdesk whenever its caller could. `bound_capabilities` is now called by
`brain.agents.model.entitlement_ceiling` and by nothing else that builds a reach: a capability on
an entity some connector provides stays in the ceiling only when the agent names that connector.
The ceiling then goes through `EntitlementSet.intersect` like every other, so there is still one
intersection and the binding is inside its right-hand side. See
`AN_AGENT_READS_ONLY_THE_SOURCES_IT_NAMES`.

**A capability on an entity no connector provides is untouched.** The company's own knowledge,
its uploaded tables, the demo source and the price list are not connectors and an agent cannot
name them, so narrowing them by a connector list would take away what no list could give back.

**This only works because an entity names one source.** Grants carry a capability and a scope and
no source, so `read:contact.name` cannot say whether it means the helpdesk's contacts or the
ledger's. Until 2026-10-06 Freshdesk and Xero both provided `contact` and Xero and the demo both
provided `invoice`, and an agent bound to Freshdesk holding `read:contact.*` would still have read
Xero's. They are `freshdesk_contact`, `xero_contact` and `xero_invoice` now, as HubSpot's and
Laravel's always were, and `tests/unit/test_agent_binding.py` holds every source to entity names
no other source provides. Rejected: filtering the sources an answer reads by the agent's list
after the reach is computed, which would be the second place deciding connector access that
M13.8.1 forbids. See `AN_ENTITY_NAMES_ONE_SOURCE`.

**A source whose read is not one of its own entities declares what it provides.** Lark Wiki's
pages were read under the knowledge library's read alone, so an entity-level ceiling could not
tell a wiki page from a company document and an agent holding the library read reached the wiki
whether or not it named it. Since 2026-10-06 a page also needs `read:wiki_page`, which Lark Wiki
declares it provides (`ConnectorDeclaration.provides`), so it is bound like every other source.
See `A_WIKI_PAGE_HAS_A_READ_OF_ITS_OWN`.

Task ids: M13.7.8, M13.8.1
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from brain.connectors.declaration import ConnectorDeclaration
    from brain.core.entitlement import Capability

# ------------------------------------------------------------------ written-down reasons
#: What the connector list does to an agent's ceiling.
AN_AGENT_READS_ONLY_THE_SOURCES_IT_NAMES: Final = (
    "An agent's ceiling keeps a capability on an entity a connector provides only when the agent "
    "names that connector, so a run through it cannot reach a source it is not bound to however "
    "widely its caller reaches. The narrowing is compiled into the ceiling, the right-hand side "
    "of the one intersection, and nothing after the intersection decides connector access again."
)

#: Why every entity name belongs to one source.
AN_ENTITY_NAMES_ONE_SOURCE: Final = (
    "A grant names a capability and a scope and no source, so a capability on an entity two "
    "sources provide reaches both, and an agent bound to one of them reaches the other. Every "
    "entity a source provides is named for that source alone, and a test refuses a second "
    "source providing the same name."
)

#: Why a wiki page needs a read beside the library's.
A_WIKI_PAGE_HAS_A_READ_OF_ITS_OWN: Final = (
    "A Lark Wiki page is told to a reader holding both the knowledge library's read and "
    "read:wiki_page, each admitting the page, and Lark Wiki provides wiki_page. The library read "
    "alone was the same capability as the company's own documents, so no agent's connector list "
    "could withhold the wiki. Everybody who held the library read was given read:wiki_page in "
    "the same release, so nobody's reach shrank."
)


def entities_of(declaration: ConnectorDeclaration) -> frozenset[str]:
    """Every entity this source provides: its classified rows, what it declares it provides, its
    readings, its live reads and the tools its console form's manifest declares.

    The manifest's tools are read from the form built with the declaration's own example settings,
    which name nobody, because a tool such as Freshdesk's contact read is declared there and in no
    reading. A form that does not build raises here rather than providing nothing, because an
    entity left out of this set is an entity no agent's list narrows.
    """
    from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES
    from brain.ops.credentials import connector_key_slot
    from brain.ops.secrets import SecretRef, VaultRole

    found = {one.entity for one in CONNECTOR_ROW_ENTITIES.get(declaration.name, ())}
    found.update(declaration.provides)
    for part in (declaration.reading, declaration.live):
        if part is not None:
            found.update(part.entities())
    form = declaration.console
    if form is not None and form.example is not None:
        # The reference `brain.ops.connectable.key_reference` builds, made here rather than
        # imported: that module reaches the worker's custom-code runner and, through the
        # schedule, the offline calibration, and nothing on the request path may import either
        # (`tests/invariants/test_no_ml_on_the_request_path.py`). Held equal to it by
        # `test_the_binding_builds_a_forms_key_reference_as_connectable_does`.
        key = SecretRef(path=connector_key_slot(declaration.name).path, role=VaultRole.WORKER)
        built = form.build(form.example.settings, key)
        found.update(tool.entity for tool in built.tools if tool.entity)
    return frozenset(found)


def providers_of(declarations: Mapping[str, ConnectorDeclaration]) -> Mapping[str, str]:
    """Each entity these connectors provide, mapped to the connector providing it.

    An entity two connectors provide is refused, so a process holding a shared name cannot answer
    through agents with a binding that reaches both. See `AN_ENTITY_NAMES_ONE_SOURCE`.
    """
    found: dict[str, str] = {}
    for name, declaration in sorted(declarations.items()):
        for entity in sorted(entities_of(declaration)):
            if found.setdefault(entity, name) != name:
                msg = f"{entity!r} is provided by both {found[entity]!r} and {name!r}"
                raise ValueError(msg)
    return MappingProxyType(found)


@cache
def providers() -> Mapping[str, str]:
    """`providers_of` the shipped connectors, cached for the process: the release fixes them."""
    from brain.connectors.declaration import shipped

    return providers_of(shipped())


@cache
def discovered_prefixes() -> Mapping[str, str]:
    """Each prefix a shipped connector names the entities it discovers at connect time with.

    Lark Base names one entity per table it is switched on for, so its entities are not known
    until an install connects it, and the prefix is what says they are its.
    """
    from brain.connectors.declaration import shipped

    return MappingProxyType(
        {one.discovers: name for name, one in sorted(shipped().items()) if one.discovers}
    )


def provider_of(entity: str) -> str | None:
    """The connector that provides this entity, or None when no connector does."""
    named = providers().get(entity)
    if named is not None:
        return named
    return next(
        (name for prefix, name in discovered_prefixes().items() if entity.startswith(prefix)),
        None,
    )


def bound_capabilities(
    capabilities: Iterable[Capability], connectors: Iterable[str]
) -> tuple[Capability, ...]:
    """`capabilities` less every one on an entity a connector provides that `connectors` omits.

    Order is kept, so a ceiling compiled from a template reads in the template's order. See
    `AN_AGENT_READS_ONLY_THE_SOURCES_IT_NAMES`.
    """
    named = frozenset(connectors)
    kept: list[Capability] = []
    for capability in capabilities:
        source = provider_of(capability.noun)
        if source is None or source in named:
            kept.append(capability)
    return tuple(kept)
