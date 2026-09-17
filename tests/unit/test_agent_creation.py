"""A new agent's id, audience, draft and ceiling, decided before anything is written.

`brain.agents.creation` is what turns a press of Install or Duplicate into a draft
`brain.agents.install_store.StoredAgentInstalls.finish` takes. These tests hold its four decisions
without a route and without a database: a minted id is a slug the agent table admits and carries
nothing a person typed beyond the name, a new agent is seen by its maker or their department and
never by the company, a duplicate is the source's version with the source's overlay, and a copy
wider than its source in any part is named.

Task ids: M27.11.6, M27.11.7
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from brain.agents.creation import (
    ID_STEM_CHARS,
    NAME_PATH,
    duplicate_draft,
    install_draft,
    mint_agent_id,
    new_audience,
    widened,
)
from brain.agents.model import AGENT_ID_CHARS, AgentAudience, AgentAuthority, AgentRecord
from brain.agents.template import TemplateError, install, publish
from brain.core.department import SLUG_PATTERN
from brain.core.entitlement import Capability
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from tests.unit.test_agent_lifecycle_routes import manifest, signed
from tests.unit.test_agent_routes import KEY

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

#: The longest suffix the route mints: three random bytes as hex.
SUFFIX = "a1b2c3"


def test_a_minted_id_is_a_slug_the_agent_table_admits_whatever_the_name() -> None:
    """Names with digits first, punctuation, other scripts, nothing usable, and far too long each
    give an id the slug grammar and the column width admit, ending in the suffix.

    Delete this and a name like "3 Pricing Desk!" fails the agent table's own constraint on the
    press of Install, or a long one is cut inside the suffix and two installs collide."""
    for name in (
        "Pricing desk",
        "3 Pricing Desk!",
        "Café à la carte",
        "!!!",
        "",
        "__leading and trailing__",
        "x" * 200,
        "word " * 40,
    ):
        minted = mint_agent_id(name, suffix=SUFFIX)
        assert re.fullmatch(SLUG_PATTERN, minted), (name, minted)
        assert len(minted) <= AGENT_ID_CHARS
        assert minted.endswith(f"_{SUFFIX}")
    assert mint_agent_id("Pricing desk", suffix=SUFFIX) == f"pricing_desk_{SUFFIX}"
    assert mint_agent_id("!!!", suffix=SUFFIX) == f"agent_{SUFFIX}"
    assert ID_STEM_CHARS + 1 + len(SUFFIX) <= AGENT_ID_CHARS


def test_a_new_agent_is_seen_by_its_maker_or_their_department_and_never_by_the_company() -> None:
    """Delete this and an install could choose the company level, which is a publication made
    without the second person `brain.agents.lifecycle.publish` requires."""
    assert new_audience("u_aaron", None) == AgentAudience(
        level=Visibility.PERSONAL, owner_id="u_aaron"
    )
    assert new_audience("u_aaron", "") == AgentAudience(
        level=Visibility.PERSONAL, owner_id="u_aaron"
    )
    assert new_audience("u_aaron", "web") == AgentAudience(
        level=Visibility.DEPARTMENT, owner_id="u_aaron", department="web"
    )


def test_an_install_draft_is_named_only_when_the_name_is_not_the_templates_own() -> None:
    """Delete this and every install carries an overlaid name, so every agent reads as diverged
    from its template on the composition diff, whatever its maker did."""
    version = signed()

    kept = install_draft(version, agent_id="invoice_desk_000001", maker_id="u_a", display_name=None)
    same = install_draft(
        version, agent_id="invoice_desk_000002", maker_id="u_a", display_name="Invoice desk"
    )
    renamed = install_draft(
        version, agent_id="invoice_desk_000003", maker_id="u_a", display_name="Tenders desk"
    )

    assert dict(kept.answers) == dict(same.answers) == {}
    assert dict(renamed.answers) == {NAME_PATH: "Tenders desk"}
    assert (renamed.instance_id, renamed.installer) == ("invoice_desk_000003", "u_a")


def test_a_duplicate_draft_carries_every_overlaid_path_of_its_source_but_the_name() -> None:
    """The source overlaid its persona, its tier and its name: the copy carries the first two and
    the name its maker gave.

    Delete this and a duplicate is the template rather than the agent, which loses every local
    change the source's owner made."""
    version = signed()
    source = install(
        version,
        key=KEY,
        instance_id="invoice_desk",
        created_by="u_builder",
        at=AT,
        overlay={"persona": "Answer in one line.", "tier": "heavy", NAME_PATH: "Old name"},
    )

    draft = duplicate_draft(
        version, source, agent_id="copy_000001", maker_id="u_a", display_name="New name"
    )

    assert dict(draft.answers) == {
        "persona": "Answer in one line.",
        "tier": "heavy",
        NAME_PATH: "New name",
    }
    assert draft.offer.signed == version


def test_a_duplicate_of_a_version_its_source_does_not_pin_is_refused() -> None:
    """Delete this and a duplicate could be finished against a newer version than its source's,
    which is an upgrade nobody accepted."""
    older = signed()
    source = install(older, key=KEY, instance_id="invoice_desk", created_by="u_b", at=AT)
    newer = manifest().model_copy(
        update={"identity": manifest().identity.model_copy(update={"version": 3})}
    )
    other = publish(newer, key=KEY, signed_by="u_publisher", at=AT)

    with pytest.raises(TemplateError, match="a duplicate is made from that version"):
        duplicate_draft(other, source, agent_id="copy_000001", maker_id="u_a", display_name="C")
    # The sibling: the version it pins is accepted.
    assert duplicate_draft(older, source, agent_id="copy_000002", maker_id="u_a", display_name="C")


def record(
    *,
    capabilities: tuple[str, ...] = ("read:invoice.reference",),
    tools: frozenset[str] = frozenset({"ledger.read_invoice"}),
    scope: Scope | None = None,
    effect: SideEffect = SideEffect.NONE,
    agent_id: str = "invoice_desk",
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name="Invoice desk",
        persona="Answer briefly.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id="u_a"),
        authority=AgentAuthority(
            scope=scope if scope is not None else Scope.department("finance"),
            capabilities=tuple(Capability(value=one) for one in capabilities),
            allowed_tools=tools,
            max_side_effect=effect,
        ),
        created_by="u_a",
    )


def test_a_copy_as_wide_as_its_source_or_narrower_widens_nothing() -> None:
    """The positive half: an identical ceiling, and one narrower in every part, name nothing.

    Delete this and `widened` could name everything, refusing every duplicate there is."""
    source = record(
        capabilities=("read:invoice.reference", "read:invoice.total"),
        tools=frozenset({"ledger.read_invoice", "books.read_invoice"}),
        effect=SideEffect.DRAFT,
    )

    assert (
        widened(
            source,
            record(
                agent_id="copy",
                capabilities=("read:invoice.reference", "read:invoice.total"),
                tools=frozenset({"ledger.read_invoice", "books.read_invoice"}),
                effect=SideEffect.DRAFT,
            ),
            now=AT,
        )
        == ()
    )
    narrower = record(
        agent_id="copy",
        capabilities=("read:invoice.reference",),
        tools=frozenset({"ledger.read_invoice"}),
        scope=Scope(clauses=(*Scope.department("finance").clauses, *Scope.department("x").clauses)),
        effect=SideEffect.NONE,
    )
    assert widened(source, narrower, now=AT) == ()


def test_a_copy_wider_in_a_tool_a_capability_a_scope_or_a_side_effect_is_named_part_by_part() -> (
    None
):
    """Each of the four ways a ceiling grows, one at a time, names exactly what grew.

    Delete this and a duplicate that binds a newly registered tool, or carries a looser scope, is
    made as though it were the agent it copies."""
    source = record()

    assert widened(
        source, record(tools=frozenset({"ledger.read_invoice", "books.read_invoice"})), now=AT
    ) == ("books.read_invoice",)
    assert widened(
        source, record(capabilities=("read:invoice.reference", "read:invoice.total")), now=AT
    ) == ("read:invoice.total",)
    assert widened(source, record(scope=Scope.unrestricted()), now=AT) == (
        "read:invoice",
        "read:invoice.reference",
    )
    assert widened(source, record(effect=SideEffect.WRITE), now=AT) == ("write",)
