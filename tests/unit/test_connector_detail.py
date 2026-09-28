"""One source on the Connectors module: its status, its department, and who leans on it.

`brain.console.connector_detail` decides from values handed in, so these tests hand it values and
read what comes back. The route half, what a reader is sent over HTTP and that a hidden connection
reads as an absent one, is `tests/unit/test_connector_routes.py`.

Task ids: M27.11.9, M27.15.58
"""

from __future__ import annotations

from datetime import UTC, datetime

from brain.connectors.contract import HealthState
from brain.console.connector_detail import (
    NO_DEPARTMENT,
    SourceStatus,
    agents_naming,
    department_of,
    skills_from,
    status_of,
)
from brain.console.skill_library import added, read_package
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.ops.connectable import manifest_for
from brain.ops.connector_sync import SyncOutcome, SyncState
from brain.tools.registry import ToolRegistry
from tests.unit.test_skill_library import TicketRow

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
EARLIER = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LATER = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)


def _tickets() -> TypedResult[TicketRow]:
    return TypedResult[TicketRow]()


def an_attempt(outcome: SyncOutcome) -> SyncState:
    return SyncState(
        connector="xero",
        finished_at=EARLIER,
        outcome=outcome,
        health=HealthState.DEGRADED,
        consecutive_failures=1,
        next_attempt_at=LATER,
        detail="said",
        last_synced_at=None,
    )


def test_a_source_is_failing_only_when_its_newest_attempt_failed() -> None:
    """Connected, failing and not connected are three words, and a quota wait is not a failure.
    Delete this and a source waiting for its allowance, which will be read, reads as broken, or a
    failing one as connected."""
    assert status_of(False, an_attempt(SyncOutcome.FAILED)) is SourceStatus.NOT_CONNECTED
    assert status_of(True, an_attempt(SyncOutcome.FAILED)) is SourceStatus.FAILING
    assert status_of(True, an_attempt(SyncOutcome.QUOTA)) is SourceStatus.CONNECTED
    assert status_of(True, None) is SourceStatus.CONNECTED


def test_the_department_is_read_off_the_source_s_own_rule_and_never_guessed() -> None:
    """Freshdesk's rule names the one department that reads it; Xero's names an organisation and
    no department, and the page says so in words. Delete this and a page can name a department for
    a source whose records answer to none, which tells the reader the wrong people can see them."""
    helpdesk = manifest_for(
        "freshdesk", {"domain": "example.freshdesk.com", "department": "support"}
    )
    ledger = manifest_for("xero", {"tenant_id": "11111111-2222-3333-4444-555555555555"})

    assert department_of(helpdesk) == "support"
    assert department_of(ledger) is None
    assert department_of(None) is None
    assert "department" in NO_DEPARTMENT


def test_only_agents_the_reader_may_see_are_named_as_using_a_source() -> None:
    """The audience decides first: an agent outside it is never named whatever its manifest says,
    and one that names another source is not named either (M27.15.58). Delete this and the page
    lists an agent's name to somebody its audience does not include."""
    found = agents_naming(
        "xero",
        connectors_by_agent={
            "books": ("xero",),
            "hidden": ("xero",),
            "desk": ("freshdesk",),
            "also": ("hubspot", "xero"),
        },
        names={"books": "Books helper", "hidden": "Hidden", "desk": "Desk", "also": "Accounts"},
        visible={"books", "desk", "also"},
    )

    assert [(one.agent_id, one.display_name) for one in found] == [
        ("also", "Accounts"),
        ("books", "Books helper"),
    ]


def test_a_skill_uses_a_source_when_a_tool_of_its_newest_version_comes_from_it() -> None:
    """A tool's source is the registry's word, and the newest version of a skill is the one judged.
    Delete this and a skill that stopped using a source goes on being listed under it, or a skill
    naming a tool nothing registers is listed under whatever it claims."""
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="freshdesk.read_ticket",
            description="Reads a ticket's status",
            entity="ticket",
            required_capability="read:ticket.status",
            identity_mode=IdentityMode.DELEGATED,
            side_effect=SideEffect.NONE,
            source="freshdesk",
        ),
        _tickets,
    )
    old = added(
        read_package("SKILL.md", skill_md("1.0.0", "[freshdesk.read_ticket]").encode()),
        by="u_importer",
        at=EARLIER,
    )
    new = added(
        read_package("SKILL.md", skill_md("2.0.0", "[crm.read_client]").encode()),
        by="u_importer",
        at=LATER,
    )

    assert skills_from("freshdesk", [old], registry)[0].version == "1.0.0"
    assert skills_from("freshdesk", [old, new], registry) == ()
    assert skills_from("xero", [old], registry) == ()


def skill_md(version: str, tools: str) -> str:
    return (
        f"---\nname: ticket-chaser\ndescription: Use when a ticket is overdue\nversion: {version}\n"
        f"tools: {tools}\n---\nRead the ticket, then say how late it is.\n"
    )
