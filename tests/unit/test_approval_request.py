"""An approver's view of a held action: rendered at their reach, locked where they cannot read.

Needs-rupash item 14 and M33.8.1. The renderer locks what the reader may not read and shows what
they may; a `RenderedRequest` exists only as `render_request` or `render_terms` made it; and no
approver surface reads the requester's artefact except for the product's own stated terms, which
the source is read to prove.

Task ids: M33.8.1
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.redaction import LOCK_TEXT
from brain.core.scope import Scope
from brain.gate.approval_request import (
    RenderedRequest,
    RequestRefusedError,
    render_request,
    render_terms,
)
from brain.gate.leash import Action

#: Far outside any plausible wall clock. See CLAUDE.md on a fixture with a date in it.
NOW = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)
SRC = Path(__file__).resolve().parents[2] / "src" / "brain"

POLICY = FieldPolicy(
    rules=(
        FieldRule.of(
            "price_list", "sell_price", "read:price_list.sell_price", Classification.INTERNAL
        ),
        FieldRule.of("price_list", "cost", "read:price_list.cost", Classification.INTERNAL),
    )
)


def reader(
    *capabilities: str, department: str = "sales", principal: str = "u_reader"
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.department(department))
            for one in capabilities
        ),
    )


def action(department: str = "sales") -> Action:
    return Action(
        agent_id="agent_prices",
        tool=ToolDefinition(
            name="prices.change_price",
            description="Change one price",
            entity="price_list",
            required_capability="approve:price_list",
            side_effect=SideEffect.WRITE,
        ),
        target="price_list",
        touched_fields=("cost", "sell_price"),
        row={"department": department},
        args={"cost": "17.37", "sell_price": "41.00"},
    )


def test_an_argument_the_reader_may_not_read_is_locked_and_one_they_may_is_shown() -> None:
    """**A_REQUEST_IS_RENDERED_AT_ITS_READER_S_REACH.** A reader holding the sell price's read and
    not the cost's is shown the sell price and the one lock for the cost, and the cost's value is
    nowhere in the text; a reader holding both is shown both. Delete this and a renderer that
    copied every value, which is what the requester's artefact did, passes."""
    narrow = render_request(action(), reader("read:price_list.sell_price"), POLICY, NOW)
    wide = render_request(
        action(), reader("read:price_list.sell_price", "read:price_list.cost"), POLICY, NOW
    )

    assert narrow.text.splitlines() == [
        "prices.change_price on price_list",
        "agent: agent_prices",
        "effect: write",
        f"  cost: {LOCK_TEXT}",
        "  sell_price: 41.00",
    ]
    assert "17.37" not in narrow.text
    assert "  cost: 17.37" in wide.text.splitlines()


def test_a_read_held_in_another_department_does_not_unlock_this_row() -> None:
    """The mask is evaluated on the action's own row, so a grant scoped to another department reads
    nothing of it. Delete this and the renderer can ask whether the reader holds a capability
    anywhere, which shows a sales price to somebody who reads finance's."""
    elsewhere = reader("read:price_list.sell_price", "read:price_list.cost", department="finance")

    shown = render_request(action("sales"), elsewhere, POLICY, NOW).text

    assert f"  cost: {LOCK_TEXT}" in shown.splitlines()
    assert f"  sell_price: {LOCK_TEXT}" in shown.splitlines()


def test_a_request_is_rendered_for_its_reader_at_the_reach_they_hold_then() -> None:
    """**NO_REACH_CHECK_COMPARES_A_VALUE_THE_CALLER_ASSERTS.** The principal and the hash on a
    request are the reader's own at the moment of rendering, computed by the renderer, for a
    rendered request and for the product's stated terms alike. Delete this and the renderer can
    carry a hash a caller passed in, which is the comparison the 2026-09-06 fix was bypassed by."""
    one = reader("read:price_list.sell_price", principal="u_one")

    for rendered in (render_request(action(), one, POLICY, NOW), render_terms("Publish it.", one)):
        assert (rendered.rendered_for, rendered.ent_hash) == ("u_one", one.ent_hash())


def test_a_request_is_never_written_by_hand_and_never_blank() -> None:
    """A `RenderedRequest` built anywhere but the two functions here is refused, so a caller cannot
    write the hash a card builder will compare; and a request with nothing on it is refused,
    because an approver pressing approve on an empty card has approved whatever it was. The
    positive half is every test above, which builds one. Delete this and a request, its reach and
    its reader can all be a caller's own words."""
    with pytest.raises(ValueError, match="never written by hand"):
        RenderedRequest(text="prices.change_price on price_list", rendered_for="u", ent_hash="e")
    with pytest.raises(RequestRefusedError, match="nothing"):
        render_terms("  \n ", reader())


#: Every function under `src/brain` that reads `.artefact`, and why each may.
ARTEFACT_READERS = {
    # The product's own stated terms, for the closed set `terms_not_data` holds.
    ("console/approvals.py", "request_for"),
    # Writing the suspension's own row, which is where the artefact is kept.
    ("gate/suspension_store.py", "row_values"),
}


def test_no_approver_surface_reads_the_requester_s_artefact() -> None:
    """**The structural pin item 14 promised, at the place it was bypassed.** Read from the source:
    the only functions under `src/brain` that read `.artefact` are the store writing its row and
    `request_for`, the one function every approver surface draws a request from, which reads it
    only for the product's own terms. Delete this and a surface can show the stored artefact again
    with every card, payload and view field still pinned, which is how it came back on
    2026-09-09."""
    found: set[tuple[str, str]] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr == "artefact"
                    and isinstance(node.ctx, ast.Load)
                ):
                    found.add((path.relative_to(SRC).as_posix(), function.name))
    assert found == ARTEFACT_READERS


def test_every_field_an_approver_s_view_carries_is_a_closed_list() -> None:
    """**NO_CARD_CARRIES_A_FREE_FORM_RECORD_OF_REQUEST_CONTENT, on the console's card, the wire's
    view and the member's envelope.** Each type's fields are exactly these, and the request is a
    `RenderedRequest` on the two that hold one in process. The Lark card's own fields and payload
    keys are held in `test_cards.py`. Delete this and a field can be added beside the request that
    carries the requester's rendering, with the request itself still correct."""
    from dataclasses import fields

    from brain.approval_routes import ApprovalCardView
    from brain.console.approvals import Card
    from brain.member.approvals import Envelope

    assert {one.name for one in fields(Card)} == {
        "suspension_id",
        "request",
        "runs_as",
        "raised_at",
        "expires_at",
        "may_take_over",
        "unsent_because",
    }
    assert set(ApprovalCardView.model_fields) == {one.name for one in fields(Card)}
    assert {one.name for one in fields(Envelope)} == {
        "suspension",
        "what_will_happen",
        "effect",
        "if_nothing_happens",
    }
    assert {one.name: one.type for one in fields(Card)}["request"] in (
        RenderedRequest,
        "RenderedRequest",
    )
    assert {one.name: one.type for one in fields(Envelope)}["what_will_happen"] in (
        RenderedRequest,
        "RenderedRequest",
    )
