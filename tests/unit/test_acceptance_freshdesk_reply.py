"""The Freshdesk reply acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a helpdesk made
up for the run connected and read, an installed agent's reply held and approved, and the worker's
run of approved actions made three times. It passes, and every table it writes holds afterwards
what it held before. Then it is run against the product broken where it proves, and each break
fails it with its own sentence.

Task ids: M11.8.12
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_freshdesk_reply as module
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_freshdesk_reply"
NAME = "an_approved_ticket_reply_is_posted_once_and_read_back"
WHOLE = "a_connector_write_is_turned_on_sent_read_back_and_announced"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        NAME: ("M11.8.12",),
        WHOLE: ("M11.8.10",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= leaves


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME, WHOLE]


@pytest.mark.needs_db
def test_on_a_real_database_an_approved_reply_is_posted_once_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before. Delete this and a reply's path from the gate to the
    helpdesk can break on a real schema with nothing on the install saying so."""
    with at_head("brain_acceptance_freshdesk_reply") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAME: (PASSED, ""), WHOLE: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("read_key", module.A_REPLY_WAS_SENT_WITHOUT_ITS_KEY),
        ("read_back", module.A_REPLY_WAS_NOT_SENT_AND_READ_BACK),
        ("once", module.A_REPLY_WAS_SENT_TWICE),
    ],
)
def test_the_check_fails_where_the_reply_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks in the product: a write sent with the read key's slot, a read-back that never
    finds the reply among the ticket's conversations, and a resume that runs every time it is
    asked. Each fails the check with its own sentence. Delete this and the check can pass with the
    property gone."""
    import brain.connectors.freshdesk as freshdesk
    import brain.gate.leash as leash
    import brain.ops.connector_write_run as write_run
    from brain.ops.credentials import connector_key_slot

    if broken == "read_key":
        monkeypatch.setattr(
            write_run,
            "connector_write_slot",
            lambda connector, grant: connector_key_slot(connector),
        )
    elif broken == "read_back":
        monkeypatch.setattr(
            freshdesk.TicketReplyWrites, "differs", lambda self, action, found: ("reply",)
        )
    else:

        def always(action: Any, *, execute: Any, ledger: Any, intent: Any) -> Any:
            del ledger, intent
            return execute(action)

        monkeypatch.setattr(leash, "run_real", always)
    with at_head(f"brain_acceptance_freshdesk_reply_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("unrecorded", module.TURNING_THE_WRITE_ON_WAS_NOT_RECORDED),
        ("read_key", module.A_WRITE_WAS_ON_BEFORE_IT_WAS_TURNED_ON),
        ("unsigned", module.THE_EVENT_WAS_NOT_DELIVERED_AFTER_A_REFUSAL),
        ("no_retry", module.THE_EVENT_WAS_NOT_DELIVERED_AFTER_A_REFUSAL),
    ],
)
def test_the_whole_write_check_fails_where_its_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks in the product: the key kept with its record lost, a write sent with the read
    key's slot, an event signed over other bytes than it sends, and a refused delivery never tried
    again. Each fails the M11.8.10 check with its own sentence. Delete this and the check can pass
    with the turning on, the key, the signature or the retry gone."""
    import brain.ops.connector_write_run as write_run
    import brain.ops.credential_write_store as credential_write_store
    import brain.ops.outbox as outbox
    import brain.ops.outbox_store as outbox_store
    from brain.ops.credentials import connector_key_slot

    if broken == "unrecorded":

        async def forgotten(self: Any, **kwargs: Any) -> None:
            del self, kwargs

        monkeypatch.setattr(credential_write_store.StoredCredentialWrites, "record", forgotten)
    elif broken == "read_key":
        monkeypatch.setattr(
            write_run,
            "connector_write_slot",
            lambda connector, grant: connector_key_slot(connector),
        )
    elif broken == "unsigned":
        signed = outbox.signature_for

        def over_nothing(*, secret: str, sent_at: Any, body: bytes) -> str:
            del body
            return signed(secret=secret, sent_at=sent_at, body=b"")

        monkeypatch.setattr(outbox, "signature_for", over_nothing)
    else:
        monkeypatch.setattr(outbox_store, "plan_next", _never_again(outbox.plan_next))
    with at_head(f"brain_acceptance_freshdesk_whole_{broken}") as url:
        outcome = run_checks(url, (mine()[WHOLE],))
    assert outcome[WHOLE] == (FAILED, reason)


def _never_again(plan: Any) -> Any:
    """`plan_next` with every refused attempt treated as the last, so nothing is tried again."""

    def planned(*args: Any, **kwargs: Any) -> Any:
        from brain.ops.outbox import DeliveryState

        found = plan(*args, **kwargs)
        if found.delivery.state is DeliveryState.PENDING:
            given_up = dataclasses.replace(found.delivery, state=DeliveryState.EXHAUSTED)
            return dataclasses.replace(found, delivery=given_up)
        return found

    return planned
