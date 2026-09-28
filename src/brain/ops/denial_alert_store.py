"""Where a denial alert is kept once it is raised, and when each was last said.

`brain.ops.denial_alerts` decides who may be told about a run of refusals and what they are
told, and stores nothing, for the reason `brain.ops.limits` gives: a debouncer that owned its
store could not be tested at the window boundary. This is the store. It keeps two things in the
Valkey the limit windows live in, which is where `denial_alerts.AlertLog` said its rows would.

**When each alert was last said**, one key per recipient, subject and shape, holding the instant
and expiring a little after `DIGEST_WINDOW`. `load_log` rebuilds `AlertLog` from them, so a
worker that restarts between two passes does not tell everybody again.

**What each person has been told**, one sorted set per recipient scored by when each alert was
raised, trimmed to `ALERTS_KEPT_FOR` and to `ALERTS_KEPT_PER_RECIPIENT`. The Notifications
screen reads a reader's own set and nobody else's.

**Every write is a put by content, so a pass that is run again changes nothing.** The member is
the alert itself (who, what shape, when raised) and the sent key holds an instant, so writing
either twice leaves the store as writing it once did. A list with a push was the first shape and
it was refused by `brain.ops.effects`' rule: a second push is a second alert on somebody's
screen, which is a repeat a person reads.

**What is stored is who, what shape and when, and never the sentence.** The sentence is
`denial_alerts.ALERT_TEXT[shape]`, looked up when the alert is read back, so a stored alert
cannot carry words the code did not write, and correcting a sentence corrects every alert
already kept. There is no capability, object, count or denial time to store, because
`DenialAlert` has none: `THE_ALERT_NAMES_A_SHAPE_AND_NEVER_A_THING` is kept by the shape of the
row as well as by the shape of the alert.

**An alert about the reader is never read back to them.** `DenialAlert`'s constructor refuses
one, and `alerts_for` passes over a stored row it cannot build rather than failing the screen,
so a row written by hand into the store cannot become a probe oracle either. See
`denial_alerts.THE_SUBJECT_IS_NEVER_A_RECIPIENT`.

Rejected: keeping alerts in the database. No table holds a notice addressed to a person, and
`ops.outbox_event`'s kinds are held by a check constraint, so either would be a migration for
a list that is worth a week and is rebuilt by the next pass anyway.

Task ids: M23.2.2
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, Protocol, cast
from urllib.parse import quote, unquote

import structlog

from brain.ops.denial_alerts import (
    ALERT_TEXT,
    DIGEST_WINDOW,
    AlertKey,
    AlertLog,
    DenialAlert,
    Digest,
)
from brain.ops.limits import DenialShape

log = structlog.get_logger()

#: The prefix of the keys saying when an alert was last said.
SENT_PREFIX: Final = "dalert:sent"

#: The prefix of each recipient's list of alerts.
KEPT_PREFIX: Final = "dalert:for"

#: How long a person's alerts are kept. A week: long enough that somebody away for a few days
#: finds what they were told, short enough that the list is about now.
ALERTS_KEPT_FOR: Final = timedelta(days=7)

#: How many alerts one person's list holds, newest first.
ALERTS_KEPT_PER_RECIPIENT: Final = 50

#: Added to a sent key's expiry beyond the digest window, so a key never expires a moment before
#: the digest would have judged it, which is `limit_store.TTL_SLACK_SECONDS`' reason.
SENT_SLACK_SECONDS: Final = 60


class AlertClient(Protocol):
    """The Valkey commands this store needs. `redis.Redis` satisfies it structurally.

    `min` and `max` shadow builtins because redis-py spells them so, for the reason
    `limit_store.WindowPipeline` gives.
    """

    def scan_iter(self, match: str | None = None, count: int | None = None) -> Iterator[Any]: ...
    def get(self, name: str) -> Any: ...
    def set(self, name: str, value: str, ex: int | None = None) -> object: ...
    def zadd(self, name: str, mapping: Mapping[str, float]) -> object: ...
    def zremrangebyscore(self, name: str, min: Any, max: Any) -> object: ...  # noqa: A002
    def zremrangebyrank(self, name: str, min: int, max: int) -> object: ...  # noqa: A002
    def expire(self, name: str, time: int) -> object: ...
    def zrevrange(self, name: str, start: int, end: int) -> Any: ...


def _text(raw: object) -> str:
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def sent_key(key: AlertKey) -> str:
    """One key per recipient, subject and shape. Every segment escaped, so none can forge one."""
    recipient, subject, shape = key
    return ":".join((SENT_PREFIX, *(quote(one, safe="") for one in (recipient, subject, shape))))


def _alert_key(rendered: str) -> AlertKey | None:
    parts = rendered.split(":")
    if len(parts) != 5 or ":".join(parts[:2]) != SENT_PREFIX:
        return None
    try:
        shape = DenialShape(unquote(parts[4]))
    except ValueError:
        return None
    return (unquote(parts[2]), unquote(parts[3]), shape)


def kept_key(recipient_id: str) -> str:
    return f"{KEPT_PREFIX}:{quote(recipient_id, safe='')}"


@dataclass(frozen=True)
class AlertStore:
    """The digest's log and every recipient's list, over one Valkey client."""

    client: AlertClient

    def load_log(self) -> AlertLog:
        """When each alert was last said, for the keys that have not expired."""
        sent: dict[AlertKey, datetime] = {}
        for raw in self.client.scan_iter(match=f"{SENT_PREFIX}:*", count=500):
            name = _text(raw)
            key = _alert_key(name)
            value = self.client.get(name)
            if key is None or value is None:
                continue
            try:
                sent[key] = datetime.fromisoformat(_text(value))
            except ValueError:
                continue
        return AlertLog(sent=sent)

    def keep(self, digest: Digest) -> None:
        """Record every alert the pass raised, in the log and in its recipient's set.

        Each recipient's set is trimmed by age and then by rank after the write, so it holds at
        most `ALERTS_KEPT_PER_RECIPIENT` alerts none older than `ALERTS_KEPT_FOR`, and the key
        itself expires a week after the last alert was kept in it.
        """
        window = int(DIGEST_WINDOW.total_seconds()) + SENT_SLACK_SECONDS
        kept_for = int(ALERTS_KEPT_FOR.total_seconds())
        for alert in digest.alerts:
            key = (alert.recipient_id, alert.subject_id, alert.shape)
            self.client.set(sent_key(key), alert.raised_at.isoformat(), ex=window)
            row = json.dumps(
                {
                    "subject": alert.subject_id,
                    "shape": alert.shape.value,
                    "raised_at": alert.raised_at.isoformat(),
                },
                sort_keys=True,
            )
            name = kept_key(alert.recipient_id)
            raised = alert.raised_at.timestamp()
            self.client.zadd(name, {row: raised})
            self.client.zremrangebyscore(name, "-inf", raised - kept_for)
            self.client.zremrangebyrank(name, 0, -ALERTS_KEPT_PER_RECIPIENT - 1)
            self.client.expire(name, kept_for)

    def alerts_for(self, recipient_id: str) -> tuple[DenialAlert, ...]:
        """What this person has been told, newest first, rebuilt with today's sentences.

        A row that does not build is passed over with a log line naming nothing, rather than
        failing the screen it is read for: a shape since removed, a row written by hand, and an
        alert about the reader themselves, which the constructor refuses.
        """
        found: list[DenialAlert] = []
        for raw in self.client.zrevrange(kept_key(recipient_id), 0, ALERTS_KEPT_PER_RECIPIENT - 1):
            try:
                row = json.loads(_text(raw))
                shape = DenialShape(row["shape"])
                found.append(
                    DenialAlert(
                        recipient_id=recipient_id,
                        subject_id=str(row["subject"]),
                        shape=shape,
                        raised_at=datetime.fromisoformat(row["raised_at"]),
                        text=ALERT_TEXT[shape],
                    )
                )
            except (ValueError, KeyError, TypeError):
                log.info("a kept denial alert did not build and was passed over")
        return tuple(found)


def make_alert_store(client: object) -> AlertStore:
    """Wrap a `redis.Redis`. A cast at a library boundary, as `limit_store.make_store` casts."""
    return AlertStore(client=cast(AlertClient, client))


def alert_store_of(state: object) -> AlertStore | None:
    """The alert store a screen reads: what a test attached, the cache's own client, or None.

    `brain.app.lifespan` opens one synchronous client for the answer cache where a cache is
    configured, and `brain.api_routes.limit_store_of` counts questions over it; this reads the
    alerts over the same one, under its own prefix, so no second connection is opened.
    """
    found = getattr(state, "alert_store", None)
    if isinstance(found, AlertStore):
        return found
    client = getattr(state, "answer_client", None)
    return None if client is None else make_alert_store(client)
