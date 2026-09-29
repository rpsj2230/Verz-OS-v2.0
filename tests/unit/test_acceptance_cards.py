"""The approval card install checks: registered, passing on PostgreSQL, and made to fail.

The pure half holds the three checks to their leaves, to `docs/wbs.json` and to the rule that a
reason is a literal sentence, and holds a press the checks build to the install's own wire. The
database half builds PostgreSQL to head once and runs the checks as the worker does: each passes
with no reason and every table any of them wrote to holds afterwards what it held before. Then each
check is run against a product broken in the one place a property of its sentence rests on, and
fails with its own sentence.

Not broken here, and said rather than dropped. A press by a bound person the card was not built
for: that guard is one comparison inside `brain.approval_cards.ApprovalCards.press`, which no
product attribute can replace without replacing the method, so it is broken by mutation against
`tests/unit/test_approval_cards.py`, which drives the same route. And a press after the approval
was decided in the console: four walls refuse it, row-level security hiding a decided row from
an approver, the Approvals screen's own question, the held row's second asking of it and the
update's pending clause, so breaking any one leaves the check green for a reason that is correct.
The mutation is equivalent at the check's level, and the unit tests over an in-memory store,
which has no row-level security, hold the other three.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M10.2.3, M10.2.4, M10.7.1, M10.7.4
"""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_cards as cards
from brain.ops.acceptance import CHECK_MODULES, FAILED, PASSED, REASON_CHARS, Check, registered
from tests.unit.test_acceptance import at_head, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_cards"
SOURCE = ROOT / "src" / "brain" / "ops" / "acceptance_checks_cards.py"

TYPED = "typed_approve_decides_nothing_and_the_approver_gets_one_card"
PRESSED = "a_card_press_decides_as_its_approver_alone_and_closes_the_card"
POLICY = "group_chat_and_channel_policy_hold_on_one_install"

#: Each check and the leaves it proves.
LEAVES = {
    TYPED: ("M10.7.1", "M10.2.3", "M10.7.4"),
    PRESSED: ("M10.2.3", "M10.2.4"),
    POLICY: ("M10.7.4",),
}

#: What the database half hands the run: an issuer the gate is built for, and an address of the
#: install's own for the links to Ask and to Approvals.
INSTALL = {
    "INSTALL_OIDC_ISSUER": "https://id.example.invalid/realms/brain",
    "INSTALL_OIDC_REDIRECT_URIS": "https://brain.example.invalid/callback",
}


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_card_checks_are_in_the_suite_with_the_leaves_they_prove() -> None:
    """Named in `CHECK_MODULES`, in this order, each with its leaves. Delete this and a card check
    drops out of the suite with the Install page simply showing one fewer row."""
    assert MODULE in CHECK_MODULES
    assert {one.name: one.leaves for one in mine()} == LEAVES
    assert [one.name for one in mine()] == [TYPED, PRESSED, POLICY]


def test_every_leaf_the_card_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Delete this and a renumbered leaf closes the wrong task on the install's word."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


def test_every_reason_a_card_check_raises_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA` over this module. Delete this and a reason can quote a card."""
    raised = 0
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("CheckFailedError", "CheckNotRunError"):
            continue
        raised += 1
        [argument] = node.args
        assert isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        assert len(argument.value) <= REASON_CHARS
    assert raised > 15


def test_the_card_message_is_the_one_the_check_s_lark_answers_a_send_with() -> None:
    """A press names the message Lark answered the card's send with. Delete this and the check
    presses a card that was never sent, and its replacement goes to an id nothing holds."""
    from brain.ops.acceptance_checks_chat import SENT_ENVELOPE

    data = SENT_ENVELOPE["data"]
    assert isinstance(data, dict) and data["message_id"] == cards.CARD_MESSAGE


def test_a_press_the_check_seals_is_read_by_the_install_s_wire_as_a_press() -> None:
    """The check's callback is sealed from Lark's algorithm, not the wire's code, so this holds
    the two together: the wire opens it and reads a press naming the value, the option and the
    card. Delete this and the checks could post presses the install reads as nothing."""
    from brain.channels.adapter import Arrived
    from brain.channels.lark import WIRE, LarkSecret
    from brain.ops.acceptance_checks_chat import sealed

    secret = LarkSecret(app_secret="a" * 16, encrypt_key="k" * 16, verification_token="t" * 16)
    event = cards.press_event(
        app_id="cli_0",
        token=secret.verification_token,
        operator="ou_x",
        value={"a": "b"},
        option="needs_more_detail",
    )
    raw, headers = sealed(event, secret.encrypt_key)
    read = WIRE.read(
        WIRE.verify(Arrived(headers=headers, body=raw), secret.kept(), datetime.now(UTC))
    )
    assert read.press is not None
    assert (read.press.value, read.press.option, read.press.message_id) == (
        {"a": "b"},
        "needs_more_detail",
        cards.CARD_MESSAGE,
    )


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_cards") as url:
        yield url


@pytest.fixture(autouse=True)
def install(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine
    from brain.settings import settings_from

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.mark.needs_db
def test_on_a_real_database_every_card_check_passes_and_leaves_nothing_behind(head: str) -> None:
    """**The three checks as the worker runs them, against PostgreSQL at head.** Each passes with
    no reason, and every table the suite counts, the suspensions, the ledger, the bindings, the
    channel's records, claims and deliveries among them, holds afterwards what it held before.
    Delete this and a card check that cannot pass on the real schema, or one that commits a
    decision to a client's install, reaches the owner's server first."""
    before = counts(head)
    outcomes = run_checks(head, mine())
    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert counts(head) == before


# ------------------------------------------------------------------ each check can fail
@pytest.mark.needs_db
def test_a_channel_that_offers_no_card_fails_the_typed_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With Lark no longer offered cards, the approver is told where to decide and sent nothing to
    press, and the check says so. Delete this and the check passes over an install whose cards
    never reach anybody."""
    monkeypatch.setattr("brain.approval_cards.carries_cards", lambda channel: False)
    assert run_checks(head, (by_name(TYPED),))[TYPED] == (
        FAILED,
        "the approver was not sent exactly one card, in their own chat",
    )


@pytest.mark.needs_db
def test_a_decision_word_answered_as_a_question_fails_the_typed_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the text path no longer recognising a decision word, approve reaches the gate as a
    question and nobody is told where to decide. Delete this and the check passes over an install
    where typing approve is answered by the model."""
    monkeypatch.setattr("brain.channels.inbound.is_decision_reply", lambda text: False)
    assert run_checks(head, (by_name(TYPED),))[TYPED] == (
        FAILED,
        "an approver typing approve was not told where approvals are decided",
    )


@pytest.mark.needs_db
def test_a_card_offered_to_anybody_who_asks_fails_the_typed_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the Approvals screen's own question bypassed, the bystander and the asker are sent the
    card too. Delete this and the check passes over an install that sends an approval's card to
    people who could never decide it."""
    from brain.approval_routes import shown_card
    from brain.console.approvals import Card

    def to_everybody(suspension: Any, reach: Any, now: datetime) -> Card | None:
        del reach
        return shown_card(suspension, _holding_it(suspension), now)

    monkeypatch.setattr("brain.approval_cards.shown_card", to_everybody)
    assert run_checks(head, (by_name(TYPED),))[TYPED] == (
        FAILED,
        "somebody who may not decide was sent more than the sentence",
    )


def _holding_it(suspension: Any) -> Any:
    """A reach holding exactly the capability this suspension's action needs, everywhere."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope

    required = Capability(value=suspension.action.tool.required_capability)
    return EntitlementSet(
        principal_id="acceptance.someone",
        grants=(Grant(capability=required, scope=Scope.unrestricted()),),
    )


@pytest.mark.needs_db
def test_a_press_admitted_only_what_a_message_is_fails_the_press_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a card press admitted only a binding's read, no approval is one a press could decide,
    so none is offered as a card and the check says so at the first place it meets the admission.
    Delete this and the check passes over an install where no card can decide anything."""
    from brain.gate.admission import Assurance, admit

    monkeypatch.setattr(
        "brain.approval_cards.admit_card_press",
        lambda held, channel, switched_on: admit(held, channel, Assurance.BOUND),
    )
    assert run_checks(head, (by_name(PRESSED),))[PRESSED] == (
        FAILED,
        "the approver was not offered a card for each waiting promotion",
    )


@pytest.mark.needs_db
def test_a_card_that_decides_while_the_switch_is_off_fails_the_press_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the cards reading the Approve from Lark cards switch as on whatever it says, the
    approver's press decides while it is off, and the check says so. Delete this and the check
    passes over an install whose cards approve with the switch the owner left off."""
    from dataclasses import replace

    from brain.approval_cards import ApprovalCards

    real = ApprovalCards.of

    def always_on(request: Any, *, bindings: Any) -> ApprovalCards:
        return replace(real(request, bindings=bindings), switched_on=True)

    monkeypatch.setattr(ApprovalCards, "of", staticmethod(always_on))
    assert run_checks(head, (by_name(PRESSED),))[PRESSED] == (
        FAILED,
        "a press decided an approval while approving from Lark was off",
    )


@pytest.mark.needs_db
def test_a_card_offered_with_buttons_while_the_switch_is_off_fails_the_typed_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The typed check's half of the same switch: read as on whatever it says, the card sent
    while it is off carries buttons, and the check says so. Delete this and the check passes over
    cards that offer to approve on an install that switched that off."""
    from dataclasses import replace

    from brain.approval_cards import ApprovalCards

    real = ApprovalCards.of

    def always_on(request: Any, *, bindings: Any) -> ApprovalCards:
        return replace(real(request, bindings=bindings), switched_on=True)

    monkeypatch.setattr(ApprovalCards, "of", staticmethod(always_on))
    assert run_checks(head, (by_name(TYPED),))[TYPED] == (
        FAILED,
        "with Lark approvals off the card offered a button or no console",
    )


@pytest.mark.needs_db
def test_a_press_whose_choice_is_lost_fails_the_press_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With what a press chose no longer read as a decision, the approver's own press decides
    nothing, and the check says so. Delete this and the check passes over an install whose cards
    are offered and can never be pressed to any effect."""
    monkeypatch.setattr("brain.approval_cards.decision_asked", lambda decision, option: None)
    assert run_checks(head, (by_name(PRESSED),))[PRESSED] == (
        FAILED,
        "the approver's press was not answered as their approval",
    )


@pytest.mark.needs_db
def test_a_decided_card_left_standing_fails_the_press_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nothing closing a card after its press decided it, the card goes on offering buttons,
    and the check says so. Delete this and the check passes over stale cards."""

    async def left_standing(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    monkeypatch.setattr("brain.channel_routes.closed_after", left_standing)
    assert run_checks(head, (by_name(PRESSED),))[PRESSED] == (
        FAILED,
        "the decided card was not replaced by one saying what was decided",
    )


@pytest.mark.needs_db
def test_a_press_claimed_twice_fails_the_press_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every delivery claimed as a first one, the same signed press posted twice is taken
    twice, and the check says so. Delete this and the check passes over replayable presses."""

    class EveryTimeFirst:
        async def first(self, event: Any) -> bool:
            del event
            return True

    monkeypatch.setattr("brain.channel_routes.claims_of", lambda request: EveryTimeFirst())
    assert run_checks(head, (by_name(PRESSED),))[PRESSED] == (
        FAILED,
        "a replayed press was not refused by the claim",
    )


@pytest.mark.needs_db
def test_a_refused_replacement_with_no_fallback_fails_the_press_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the fallback dropped from what a press plans, a card Lark would not replace is left
    showing an open decision with nothing said, and the check says so. Delete this and the check
    passes over the one case M10.2.4's text fallback exists for."""
    from dataclasses import replace

    from brain.approval_cards import ApprovalCards

    real = ApprovalCards._closing

    async def without_fallback(self: Any, *args: Any, **kwargs: Any) -> Any:
        return replace(await real(self, *args, **kwargs), fallback=None)

    monkeypatch.setattr(ApprovalCards, "_closing", without_fallback)
    assert run_checks(head, (by_name(PRESSED),))[PRESSED] == (
        FAILED,
        "a refused replacement was not followed by the text fallback",
    )


@pytest.mark.needs_db
def test_a_channel_that_carries_any_class_fails_the_policy_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the ceiling no longer asked of what leaves, Lark carries a reply marked restricted, and
    the check says so. Delete this and the check passes over a channel that carries anything."""
    monkeypatch.setattr("brain.channels.outbound.assert_can_send", lambda *args, **kwargs: None)
    assert run_checks(head, (by_name(POLICY),))[POLICY] == (
        FAILED,
        "Lark carried a class its ceiling excludes, or refused one it takes",
    )
