"""Where a denial alert is kept once raised: the digest's log and each recipient's alerts.

`test_denial_alerts.py` holds who may be told and what they are told. What is here is the store:
that what a pass raised is what a reader reads back, that the log survives a worker restart,
that writing twice is writing once, and that nothing kept can carry more than the alert did.

Task ids: M23.2.2
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from brain.ops.denial_alert_store import (
    ALERTS_KEPT_FOR,
    ALERTS_KEPT_PER_RECIPIENT,
    AlertStore,
    alert_store_of,
    kept_key,
    sent_key,
)
from brain.ops.denial_alerts import ALERT_TEXT, DIGEST_WINDOW, AlertLog, DenialAlert, Digest
from brain.ops.limits import DenialShape
from tests.fixtures.fake_alert_valkey import FakeAlertValkey

NOW = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)


def alert(
    recipient: str = "u_admin", subject: str = "u_weiling", *, at: datetime = NOW
) -> DenialAlert:
    shape = DenialShape.ENUMERATION
    return DenialAlert(
        recipient_id=recipient,
        subject_id=subject,
        shape=shape,
        raised_at=at,
        text=ALERT_TEXT[shape],
    )


def kept(*alerts: DenialAlert) -> tuple[AlertStore, FakeAlertValkey]:
    client = FakeAlertValkey()
    store = AlertStore(client=client)
    store.keep(Digest(alerts=alerts, log=AlertLog()))
    return store, client


def test_what_a_pass_raised_is_what_its_recipient_reads_back() -> None:
    """The positive case the rest need. Delete this and a store that keeps nothing passes every
    test below about what it must not keep."""
    store, _ = kept(alert())

    assert store.alerts_for("u_admin") == (alert(),)


def test_a_person_reads_their_own_alerts_and_nobody_elses() -> None:
    """Each recipient's alerts are a key of their own. Delete this and one key for everybody
    tells every reader about every alert anybody was entitled to."""
    store, _ = kept(alert("u_admin"), alert("u_other", subject="u_jason"))

    assert [one.subject_id for one in store.alerts_for("u_admin")] == ["u_weiling"]
    assert store.alerts_for("u_nobody") == ()


def test_the_log_survives_a_restart_so_nobody_is_told_twice_in_a_window() -> None:
    """`AlertLog` is rebuilt from the store, so a worker that restarts between two passes knows
    what it already said. Delete this and every restart re-alerts everybody."""
    _, client = kept(alert())

    rebuilt = AlertStore(client=client).load_log()

    assert rebuilt.last_sent(("u_admin", "u_weiling", DenialShape.ENUMERATION)) == NOW
    assert client.ttls[sent_key(("u_admin", "u_weiling", DenialShape.ENUMERATION))] >= (
        DIGEST_WINDOW.total_seconds()
    )


def test_keeping_one_pass_twice_leaves_the_store_as_keeping_it_once_did() -> None:
    """Every write is a put by content. Delete this and a retried pass puts a second copy of one
    alert on somebody's screen, which `brain.ops.effects` classifies as a repeat a person reads."""
    store, _ = kept(alert())
    store.keep(Digest(alerts=(alert(),), log=AlertLog()))

    assert store.alerts_for("u_admin") == (alert(),)


def test_a_persons_alerts_are_bounded_by_age_and_by_number() -> None:
    """A week and fifty, newest first. Delete this and a busy estate grows one person's key for
    ever, and the screen reads all of it."""
    many = [alert(subject=f"u_{n:03d}", at=NOW + timedelta(minutes=n)) for n in range(60)]
    store, client = kept(*many)
    store.keep(
        Digest(alerts=(alert(subject="u_old", at=NOW - ALERTS_KEPT_FOR * 2),), log=AlertLog())
    )

    read = store.alerts_for("u_admin")

    assert len(read) == ALERTS_KEPT_PER_RECIPIENT
    assert read[0].subject_id == "u_059"
    assert "u_old" not in {one.subject_id for one in read}
    assert client.ttls[kept_key("u_admin")] == int(ALERTS_KEPT_FOR.total_seconds())


def test_what_is_kept_is_who_what_shape_and_when_and_never_the_sentence() -> None:
    """The sentence is looked up when read, so a stored row cannot carry words the code did not
    write. A row with extra words in it is read back with today's sentence and nothing else.

    Delete this and the store becomes somewhere a capability or a count could be put and shown."""
    store, client = kept(alert())
    [row] = client.sets[kept_key("u_admin")]
    assert set(json.loads(row)) == {"subject", "shape", "raised_at"}

    client.sets[kept_key("u_admin")] = {
        json.dumps(
            {**json.loads(row), "text": "denied 40 times on read:client.contract_value"}
        ): 1.0
    }

    [read] = store.alerts_for("u_admin")
    assert read.text == ALERT_TEXT[DenialShape.ENUMERATION]


def test_a_kept_alert_about_the_reader_is_never_read_back_to_them() -> None:
    """A row naming the reader as its subject, however it got there, is passed over: an alert
    about your own refusals is a probe oracle. Delete this and a hand-written row is one.

    The sibling row beside it is read, so the pass-over is of one row and not of the list."""
    store, client = kept(alert())
    client.sets[kept_key("u_admin")][
        json.dumps({"subject": "u_admin", "shape": "enumeration", "raised_at": NOW.isoformat()})
    ] = 2.0

    assert [one.subject_id for one in store.alerts_for("u_admin")] == ["u_weiling"]


def test_a_row_that_does_not_build_is_passed_over_rather_than_failing_the_screen() -> None:
    """A shape since removed, or anything that is not a row. Delete this and one bad row takes
    the whole Notifications screen down."""
    store, client = kept(alert())
    client.sets[kept_key("u_admin")]["not json"] = 3.0
    client.sets[kept_key("u_admin")][json.dumps({"subject": "u_x", "shape": "gone"})] = 4.0

    assert [one.subject_id for one in store.alerts_for("u_admin")] == ["u_weiling"]


def test_a_process_with_a_cache_reads_alerts_over_it_and_one_without_has_none() -> None:
    """The same client the answer cache holds. Delete this and the screen reads a store nothing
    writes, or opens a second connection per request."""

    class State:
        pass

    assert alert_store_of(State()) is None
    wired = State()
    wired.answer_client = FakeAlertValkey()  # type: ignore[attr-defined]
    assert alert_store_of(wired) is not None
