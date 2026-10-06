"""`0196`'s copies held to the product's, and the agent row's trigger held to `0190`'s.

A migration copies the values it needs rather than importing live code, for the reason `0009`
gives, so each copy is a second statement of something the product also states and the two can
drift. These hold each one to the product from outside it. The behaviour of the tables and the
triggers is proved on PostgreSQL in `tests/unit/test_agent_attachment_routes.py`.

Task ids: M39.8.6, M39.1.1.3
"""

from __future__ import annotations

from types import ModuleType

from brain.agents.binding import providers
from brain.audit.record import INFERRED_ACTOR
from brain.connectors.declaration import shipped
from brain.ops import acceptance_workspace, attachment_store
from brain.tables import attachment
from tests.unit.test_tables import VERSIONS, migration_module


def migration() -> ModuleType:
    return migration_module(VERSIONS / "0196_tool_attachments.py")


def lifecycle() -> ModuleType:
    return migration_module(VERSIONS / "0137_agent_lifecycle_audit.py")


def as_0190_left_it() -> str:
    """The function `0190` installs, computed from `0190` and `0137` here rather than by `0196`."""
    channels = migration_module(VERSIONS / "0190_agent_channels_audited.py")
    return str(channels.replaced(lifecycle().AGENT_TRIGGER_FUNCTION))


def test_the_migrations_widths_and_vocabularies_are_the_tables() -> None:
    """Every width and pattern `0196` builds the table with is the model's, and the one part a row
    may be on is the model's `TOOL_ROWS_ONLY`. Delete this and the model accepts a value the
    table refuses, which surfaces as a 500 on the first press that carries it, or the table
    quietly starts admitting connector rows the model says it never holds."""
    built = migration()
    assert (
        built.AGENT_ID_CHARS,
        built.REFERENCE_CHARS,
        built.PART_CHARS,
        built.TRACE_ID_CHARS,
        built.REASON_CHARS,
        built.ENT_HASH_PATTERN,
        built.REASON_PATTERN,
    ) == (
        attachment.AGENT_ID_CHARS,
        attachment.REFERENCE_CHARS,
        attachment.PART_CHARS,
        attachment.TRACE_ID_CHARS,
        attachment.REASON_CHARS,
        attachment.ENT_HASH_PATTERN,
        attachment.REASON_PATTERN,
    )
    assert built.PARTS == attachment.TOOL_ROWS_ONLY == "part = 'tool'"


def test_the_downgrade_restores_0190s_function_exactly() -> None:
    """`AS_SHIPPED_BEFORE` is the function `0190` installs, computed here from `0190` and `0137` and
    not from `0196`. Delete this and a downgrade leaves a function that is neither the old one nor
    the new one, or `0137`'s without the channels branch, and channel switches stop reaching the
    ledger with nobody having decided they should."""
    assert migration().AS_SHIPPED_BEFORE.strip() == as_0190_left_it().strip()
    assert "OLD.channels IS DISTINCT FROM NEW.channels" in migration().AS_SHIPPED_BEFORE


def test_the_replaced_function_keeps_every_line_of_0190s_and_adds_the_connectors() -> None:
    """Every line of `0190`'s function is in the replacement, in its order, so each lifecycle
    movement and the channels switch it recorded is still recorded; the replacement adds a
    `compose_change` entry for a connector moved and nothing for the persona. Delete this and the
    replacement can drop `archived`, `published` or `channels_changed` from the ledger while the
    connector half works perfectly."""
    before = [one for one in as_0190_left_it().strip().splitlines() if one.strip()]
    after = migration().AGENT_TRIGGER_FUNCTION.splitlines()
    place = 0
    for line in before[1:]:
        place = after.index(line, place) + 1
    body = migration().AGENT_TRIGGER_FUNCTION
    assert "'channels_changed'" in body
    assert "OLD.connectors IS DISTINCT FROM NEW.connectors" in body
    assert body.count("'compose_change'") == 2
    assert "persona" not in body
    # The connectors are appended after every entry the function already writes.
    assert body.index("'channels_changed'") < body.index("OLD.connectors IS DISTINCT")


def test_the_migrations_copies_are_the_products() -> None:
    """The setting a connector press names its reason in, the reason a statement gets, and the
    inferred-actor word are the product's. Delete this and the console's reason is written to a
    setting the trigger never reads, so every press is recorded as unexplained, or the inferred
    marker becomes a value the ledger's own model refuses to load."""
    built = migration()
    assert built.REASON_SETTING == attachment_store.REASON_SETTING
    assert built.INFERRED == INFERRED_ACTOR
    assert built.UNEXPLAINED != ""
    # Revises whichever migration lands before it, which the release train re-points, so the chain
    # is held as an order rather than as one number.
    assert built.down_revision is not None and built.down_revision < built.revision


def test_the_acceptance_checks_connector_is_shipped_and_provides_an_entity() -> None:
    """The connector the install check binds is one this release ships and one the binding maps
    an entity to. Delete this and a renamed connector fails the check on an install, where the
    message says a run did not read through it, rather than here."""
    assert acceptance_workspace.BOUND_CONNECTOR in shipped()
    assert acceptance_workspace.BOUND_CONNECTOR in set(providers().values())
