"""Reading a connected source on a schedule: may it be read, what is kept, what a failure costs.

`brain.ops.connector_admin` connects a source from the console and until this module nothing on any
install read one: no worker ran a connector, so a connected source was never synced, projected,
health-checked or answered from, and its key sat in the vault read by nothing. This is the policy
half of the control that reads them. It opens no connection, reads no clock and holds no key;
`brain.ops.connector_sync_run` is the worker's half and `brain.ops.connector_sync_store` the SQL,
for the split CLAUDE.md names: nothing that decides policy owns a client.

**A source is read only when five things already in the repository agree that it may be.**
`plan_for` asks them in order and stops at the first that refuses, and each refusal is a sentence
the Connectors screen shows rather than a source quietly left out:

- this release has a reading for the source (`READINGS`, read off each connector's own
  `CONNECTOR` declaration at start-up, so a new source is read with no edit here);
- the manifest its stored settings build today is the one agreed to at connect, which is
  `brain.connectors.registry.reconnect`'s pin applied to a scheduled read: a release that changed
  what a connector declares waits for a person, it is not read under a declaration nobody accepted;
- every entity it projects keeps a visibility predicate this store can carry (see below);
- `brain.connectors.throttle.limits_for` finds a verified ceiling, which it refuses to invent. That
  is why HubSpot is not read today: `hubspot.A_CEILING_NOBODY_VERIFIED_IS_NOT_A_CEILING`;
- and a source whose connector is custom code has a sandbox runner to run it in
  (`brain.connectors.custom_code.A_CUSTOM_SOURCE_WITH_NO_RUNNER_IS_NOT_READ`), which no install
  has until the sandbox service is running (needs-rupash 154).

**The source's visibility travels on the record as fields, because that is the only place the row
plane can evaluate it.** `brain.tables.projection` has no visibility column, and argues why: the
predicate is the manifest's. But nothing evaluates a manifest at read time; `brain.knowledge.rows`
compiles the *reader's* grant scope into the WHERE clause, over the record's stored fields, and the
redactor tests the same scope against the record it is handed. A record that does not carry the
field a scope tests satisfies neither, so nobody reaches it, which `brain.demo.
A_RECORD_NO_SCOPE_CAN_MATCH_IS_A_RECORD_NOBODY_REACHES` measured on the seeded company. So each
equality clause of the source's predicate (Xero's tenant, HubSpot's portal) is laid over the
projected fields, and a grant scoped to that tenant reaches the row while a grant scoped to a
department does not. See `THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS`. Only
an equality can be stored this way: a prefix or a set is a predicate over many values and a row
holds one, so a manifest declaring one is not read at all rather than read into rows no predicate
can reach.

**What a sync keeps is the source's minimal index and nothing else, and it is checked at the
write.** The owner's rule is that connectors never bulk-sync
(`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`): ids, names, dates, status and the few
fields a manifest names, with every value read live at question time. `kept_fields` holds each row
to its manifest with `brain.connectors.minimal_index.assert_minimal_index` before the page is
written, so a connector whose code keeps a field its manifest never declared is refused at the
write rather than found in the table. Until 2026-09-28 a reading could also hand each row to the
corpus as a document, embedded into `know.chunk`; that was a bulk sync of bodies, and it was
removed rather than left unfed. See `A_SYNC_KEEPS_NO_BODY`.

**A failure makes the next attempt later and marks the source unhealthy after the third in a row.**
`after_attempt` is the whole rule and `A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY`
argues it. A quota refusal is not a failure, for `throttle.A_QUOTA_REFUSAL_IS_NOT_ILL_HEALTH`'s
reason, and it waits as long as the source asked.

**A read asks only for what changed since the last complete read, where the source can be asked
that** (M11.4.6). The instant the last complete read began is kept with the sync state, on the
attempt that completed it (`ReadState`), and a source whose reading is
`brain.connectors.declaration.ChangedSince` is asked for its changes since then, less a few
minutes for two clocks that disagree. The first read of a connection reads everything, and so does
a read once the source's change subscription says a reconciliation is owed. See
`A_READ_ASKS_ONLY_FOR_WHAT_CHANGED_SINCE_THE_LAST_COMPLETE_READ`. The mechanism is the
updated-since cursor: no webhook receiver is built, because the cursor is a pull the worker's own
schedule makes, and a pull that did not happen is visible where a push that did not arrive is not
(`brain.connectors.change_signal.A_WEBHOOK_MISS_IS_SILENT`).

**A read cut short carries on where it stopped** (M11.4.8). The page each entity would be read from
next is kept with the attempt as a `brain.connectors.backfill.BackfillCursor`, whose own rule
refuses a next page that is the page just read, and the next attempt asks that page. Each call is
still admitted by the source's verified ceiling before it is made, and a run still reads at most
`MAX_PAGES_PER_ENTITY` pages of an entity. See `A_READ_CUT_SHORT_CARRIES_ON_WHERE_IT_STOPPED`.
Rejected: `backfill.next_step` as the pacing, which holds a search's result cap against the list a
sync walks and would stop Freshdesk's list at three hundred tickets.

**What a complete read of everything did not return is retired, and a record the source returns
again serves from its own row while the retirement stays on file** (M11.8.11). See
`WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED` and `brain.tables.projection`.

**A pass cut short at its page bound is carried on whatever shape its walk takes** (M11.9.15).
What an entity's walk would ask next is kept as that page's own arguments, so a reading that carries
its walk in them, as Google Drive carries the folders still to list, is carried on with no code of
its own; a routed reading's next route is a page like any other; and an entity listed under
another keeps the page of the parent it stopped under, with the parents after it read from the
index this read has already written. A pass that skipped something to finish (a routed server that
did not answer, a folder past the walk's bound) is marked partial and retires nothing. A
database's views are the one shape not carried on: see `A_VIEW_READ_IS_ONE_BOUNDED_READ`.

**A read that changed a source's rows advances that source's epoch** (M11.8.4), in the transaction
that changed them, and the answer cache's key carries it. See
`A_CHANGED_READ_ADVANCES_ITS_SOURCE_S_EPOCH` and `brain.tables.projection.SourceEpochRow`.

Rejected: registering a `ConnectorRegistry` from the stored connections and driving `reconnect` on
every run. It would quarantine a connection in memory that the next run rebuilds from the same row,
so the quarantine would last one run, and it would add a second in-memory opinion about whether a
source is connected beside the table that already says so.

**A source consented to by OAuth fails in three more sentences of its own (M11.8.6).** A vendor that
refused the renewal has withdrawn the consent (`CONSENT_WITHDRAWN`, from `brain.connectors.oauth`),
which is down at once like any refused key; a source nobody has consented to yet has no refresh
token to renew with (`NOT_CONSENTED`); and a token the vendor rotated that the vault would not keep
is a consent the next read cannot use (`ROTATED_REFRESH_NOT_KEPT`).

Task ids: M42.6.5, M11.9.1, M11.4.1, M27.15.8, M11.4.6, M11.4.8, M11.8.4, M11.8.11, M11.9.15
Task ids: M11.1.2, M11.1.5, M11.8.6, M11.7.8
"""

from __future__ import annotations

import enum
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from brain.connectors.backfill import BackfillCursor
from brain.connectors.contract import ConnectorContractError, HealthState
from brain.connectors.declaration import (
    ChangedSince,
    CodeReading,
    Reading,
    RoutedReading,
)
from brain.connectors.declaration import PageReply as PageReply
from brain.connectors.declaration import SourceReading as SourceReading
from brain.connectors.declaration import ViewReading as ViewReading
from brain.connectors.manifest import ConnectorManifest, manifest_digest
from brain.connectors.minimal_index import MinimalIndexError, StoredRow, assert_minimal_index
from brain.connectors.oauth import CONSENT_WITHDRAWN as CONSENT_WITHDRAWN
from brain.connectors.projection import MISSED_REFRESHES_BEFORE_STALE, ProjectedRecord
from brain.connectors.throttle import CallOutcome, UnmeasuredSourceError, limits_for, retry_delay
from brain.core.scope import Op, Scope
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_catalogue import Derived
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_store import Connection
from brain.ops.limits import Limit
from brain.tools.run_skill import ScriptRunner

# ------------------------------------------------------------------ written-down reasons

#: Why the predicate's fields are written onto the record.
THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS: Final = (
    "The row plane compiles a reader's grant scope into the WHERE clause over proj.record's stored "
    "fields, and the redactor evaluates the same scope against the record it builds. Nothing reads "
    "the manifest's predicate when a row is read. So the only way a source's own rule narrows who "
    "reaches its rows is for each row to carry the field the rule tests, with the value the rule "
    "names: a grant scoped to that value then reaches the row, a grant scoped to anything else "
    "does not, and no grant reaches it by the field being absent. A projected field that already "
    "holds a different value under that name is refused rather than overwritten, because one field "
    "with two values is two answers to who may read the row."
)

#: Why a failing source is not retried on every run, and why it is still retried.
A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY: Final = (
    "A source that failed is asked again after its own refresh interval, then after twice that, "
    "and so on, doubling per failure in a row, and never later than a day. Retrying on every run "
    "turns an expired key into a call spent every few minutes on a refusal already known, against "
    "an allowance the client shares with every other integration. Never retrying, or retrying "
    "weekly, means a key replaced in the source's own settings is not noticed working for a week. "
    "A day is the longest a person fixing a source should wait to see it read."
)

#: Why the health word turns to down at the third failure and not the first.
A_SOURCE_IS_UNHEALTHY_AFTER_THREE_FAILURES_IN_A_ROW: Final = (
    "One failed read is a network that dropped a connection, two can be a coincidence, and three "
    "in a row is the source or its key not working. The number is "
    "brain.connectors.projection.MISSED_REFRESHES_BEFORE_STALE, reached by the same argument about "
    "the same pipeline, so the projection turns stale and the source turns down at the same point. "
    "A refused authorisation is down at once, because a retry reproduces it exactly."
)

#: Why a quota refusal carries the failure count over rather than adding to it.
A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED: Final = (
    "A 429 is the source's allowance working, not the source failing, and counting it would mark "
    "the busiest source unhealthy for being asked. It waits for the longer of what the platform's "
    "backoff computes and what the source said, and it neither clears nor adds to the failures in "
    "a row."
)

#: Why nothing from the source can reach a run's record.
A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE: Final = (
    "A run's record is read on the Connectors screen by whoever may see the connection, which is a "
    "different audience and a different retention from the rows the run wrote. Its detail is one "
    "of this module's constant sentences, chosen by what kind of thing happened, and never a "
    "response body, an exception's message, a setting or a filter value, which could carry a "
    "client's name or the key itself."
)

#: What a read asks a source for. See the module docstring.
A_READ_ASKS_ONLY_FOR_WHAT_CHANGED_SINCE_THE_LAST_COMPLETE_READ: Final = (
    "A source that can be asked for what changed since an instant is asked exactly that, from the "
    "instant the last complete read began, so a read costs what changed rather than everything "
    "the source holds. The start of a read and not its end, because a record changed while a "
    "read walked past it is newer than that read's start and older than its end. The first read "
    "of a connection reads everything, and so does any read once the source's subscription says "
    "a reconciliation is owed, because a cursor never mentions a record that was removed."
)

#: Why a read of changes asks from a little before the cursor.
A_CURSOR_REACHES_BACK_PAST_A_CLOCK_THAT_DISAGREES: Final = (
    "The cursor is this install's clock and the source compares it with its own, and two clocks a "
    "few minutes apart would lose every record changed in the gap between them. So a read asks "
    "from CURSOR_OVERLAP before the cursor: a record changed in those minutes is read twice, "
    "which writes the same index row again, and none is missed."
)

#: Why a read that stopped part-way is not started again.
A_READ_CUT_SHORT_CARRIES_ON_WHERE_IT_STOPPED: Final = (
    "A read stopped by the pages one run may read, by the source's allowance, by this install's "
    "share of it or by a failure keeps, with its attempt, the page each entity would be read from "
    "next, and the next attempt asks that page rather than the first. Starting again spends a "
    "second time every call the stopped read spent, against a ceiling the client shares with "
    "every other integration, and a source larger than one run's pages would never be read to "
    "its end at all. brain.connectors.backfill.RESUMING_IS_NOT_RESTARTING makes the same case."
)

#: When a read retires a record, and why that became safe.
WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED: Final = (
    "A read of everything a source holds, from each entity's first page to its last with nothing "
    "asked only for changes, is the one view of the source that shows a record has gone: a live "
    "record it did not return is retired, stamped with when that was noticed. A read of changes "
    "cannot show it, because a deleted record is not changed, it stops being mentioned; and a read "
    "cut short cannot, because the records past where it stopped were not asked for. Until 0179 "
    "nothing was retired, because a retirement was final for the record, so a sweep that was "
    "wrong (a page the source skipped while another was deleted in front of it) would have kept a "
    "record out of every answer for good. Now a record the source returns again serves from its "
    "own row, and the copy kept in proj.record_retired stays as the record of when it went, so a "
    "wrong retirement lasts until the next read that sees the record. A pass that skipped "
    "something to finish, a routed server that did not answer or a folder past the walk's bound, "
    "is partial and retires nothing, because what it skipped was not asked for either."
)

#: Why a pass is carried on in every shape a walk takes.
A_WALK_CUT_SHORT_IS_CARRIED_ON_IN_EVERY_SHAPE: Final = (
    "A pass stopped at its page bound keeps the arguments of the page it would ask next, and the "
    "next attempt asks exactly that page. Every walk the worker makes is a sequence of pages, so "
    "this one rule carries on each of them: a reading that holds its walk in the page arguments, "
    "as Google Drive holds the folders still to list, needs nothing of its own; a routed "
    "reading's next route is a page; and an entity listed under another keeps the page under the "
    "parent it stopped at, then reads every later parent this read kept, from the index, because "
    "the parents were written by an earlier attempt and are not in this one's memory. Parents are "
    "walked in the order of their ids, so the attempt that carries on knows which come after."
)

#: Why a database's views are read from the start every time.
A_VIEW_READ_IS_ONE_BOUNDED_READ: Final = (
    "A database's view is read by one statement bounded by the row cap its administrator set, and "
    "the statement has no page to resume from: the reading asks no keyset and the view promises "
    "no order. A read that reached the cap says it was cut short and the next one reads the view "
    "again from the start, and it never retires anything, because a capped read did not see the "
    "rows past the cap. Raising the cap is the administrator's remedy, up to the connector's own "
    "ceiling."
)

#: When a source's epoch moves, and when it does not.
A_CHANGED_READ_ADVANCES_ITS_SOURCE_S_EPOCH: Final = (
    "A page that writes a record the index did not hold, or changes a field of one it did, and a "
    "retirement advance the source's epoch in the same transaction, and the answer cache's key "
    "carries every epoch its reader's sources have, so an answer cached before the change is "
    "never found after it. A page that only confirms what the index already says moves each row's "
    "last_seen_at and not the epoch, so a source nobody changed keeps its cached answers."
)

#: Why a sync hands nothing to the corpus.
A_SYNC_KEEPS_NO_BODY: Final = (
    "A scheduled read keeps each record's minimal index in proj.record and nothing else. It once "
    "also handed a reading's rows to the corpus as documents, where they were chunked and "
    "embedded: a copy of every body the source held, refreshed on a timer, which is the bulk sync "
    "the owner has ruled out twice. A document from a connected source is found by its indexed "
    "title and id and read live when a question needs it; `docs/needs-rupash.md` item 99 asks the "
    "owner to confirm that for Drive and Wiki bodies, and this is its recommended answer."
)

#: Why a test's row copies the schedule's figures rather than moving them.
A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT: Final = (
    "A test is one call a person asked for, and its row is the source's newest attempt, so the "
    "screen shows what the test found as the source's health. It does not move the schedule: the "
    "failures in a row and the next attempt are copied from the attempt before it, so a test that "
    "fails does not push a failing source further into its backoff and a test that works does not "
    "clear a backoff the scheduled read earned. The one exception is the source's own word: a test "
    "the source refused for volume waits as long as the source asked, as a scheduled read would."
)

# -------------------------------------------------------------------------- the numbers

#: Failures in a row after which a source is down. See
#: `A_SOURCE_IS_UNHEALTHY_AFTER_THREE_FAILURES_IN_A_ROW`.
UNHEALTHY_AFTER_FAILURES: Final = MISSED_REFRESHES_BEFORE_STALE

#: The longest a failing source waits before it is asked again.
LONGEST_WAIT_AFTER_FAILURES: Final = timedelta(days=1)

#: How often the control runs. A third of the shortest interval any source this release reads
#: promises (HubSpot's quarter-hourly cursor), so a source due a read is late by at most a third of
#: its own promise, and the tick never equals an interval, which is `brain.ops.schedule.TICK`'s
#: reason about a cadence that would start a control every other tick.
CONTROL_EVERY: Final = timedelta(minutes=5)

#: How many pages of one entity one run reads. A read that reaches it stops, keeps what it read and
#: says it was cut short; the next run carries on from the page after. Fifty pages of a hundred
#: records is five thousand invoices, and against Xero's day it is a hundredth of the allowance.
MAX_PAGES_PER_ENTITY: Final = 50

#: How far before the cursor a read of changes asks from. See
#: `A_CURSOR_REACHES_BACK_PAST_A_CLOCK_THAT_DISAGREES`. Minutes rather than seconds, because a
#: server whose clock is not kept by NTP drifts by minutes and is still an ordinary server; shorter
#: than any interval a source asked for its changes is read at, so a read of changes never asks for
#: more than the interval before it and this.
CURSOR_OVERLAP: Final = timedelta(minutes=5)

#: How long one run may wait, in total, for its own share of a source's minute to have room before
#: it stops that source for this run. Well inside `brain.ops.schedule_runner.STALLED_AFTER`.
MAX_SECONDS_WAITING_IN_A_RUN: Final = 120.0

#: The principal a scheduled read is counted against in `brain.ops.limits`. Not a person and not a
#: row in `auth.principal`: it is the subject of a window, so the worker's reads take their fair
#: share of a source's minute and leave the rest for questions.
SYNC_PRINCIPAL: Final = "worker.connector_sync"

# ------------------------------------------------------------------------ the sentences

#: Why a connected source is not read, one per check in `plan_for`.
NO_READING: Final = "Nothing reads this source: this release has no scheduled reading for it."
DECLARATION_CANNOT_BE_REBUILT: Final = (
    "Nothing reads this source: this release cannot rebuild what it was connected as. Disconnect "
    "it and connect it again."
)
DECLARATION_NOT_AGREED: Final = (
    "Nothing reads this source: what it declares today is not what was agreed to when it was "
    "connected, so it is not read until somebody connects it again and agrees to the new "
    "declaration."
)
VISIBILITY_NOT_STORABLE: Final = (
    "Nothing reads this source: its visibility rule is not one a stored record can carry, so a "
    "record read from it could be reached by no grant."
)
NO_VERIFIED_CEILING: Final = (
    "Nothing reads this source: no verified call ceiling is recorded for it, and it is not read "
    "against a ceiling nobody measured."
)
#: A custom-code source on an install that runs no sandbox (M11.1.5).
NO_SANDBOX: Final = (
    "Nothing reads this source: its connector is custom code, and this install runs no sandbox to "
    "run it in."
)

#: What an attempt came to, one per kind of thing that happened. Constants, for
#: `A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.
READ_TO_THE_END: Final = "Read to the end."
READ_BUT_CUT_SHORT: Final = (
    "Read as far as one run reads, which was not the end; the next run carries on from where this "
    "one stopped."
)

#: A pass read to its end that met a bound its reading will not cross. Google Drive's is a folder
#: nested deeper than `brain.connectors.google_drive.MAX_FOLDER_DEPTH`, Google's own limit.
READ_BUT_PART_LEFT_OUT: Final = (
    "Read to the end of what its reading goes into, which is not all of the source: part of it "
    "lies past a bound the reading does not cross, so that part was not read and nothing was "
    "retired. "
    "In Google Drive that is a folder nested more than 100 levels below the one connected; move it "
    "nearer the connected folder and the next run reads it."
)
SOURCE_ALLOWANCE_REFUSED: Final = (
    "The source's call allowance refused the read. It is tried again once the source said it would "
    "have room."
)
OWN_SHARE_SPENT: Final = (
    "This install's share of the source's call allowance ran out during the read. It is read again "
    "on a later run."
)
SOURCE_UNREACHABLE: Final = "The source did not answer."
SOURCE_TIMED_OUT: Final = "The source did not answer in time."
KEY_DECLINED: Final = (
    "The source declined the key this install holds for it. Replace the key from this source's "
    "Manage menu."
)
#: What a database's refusal leaves, which a key's refusal does not describe: the password, the
#: grant on the views and the views themselves are the database administrator's, and any of them
#: moving is the same refusal to this install (M11.6.1).
DATABASE_REFUSED: Final = (
    "The database refused the read: the user's password, its grant on the views, or a view itself "
    "is no longer what was connected. Its administrator can say which; replace the user from this "
    "source's Manage menu if its password changed."
)
SHAPE_DISAGREED: Final = (
    "The source answered in a shape its declaration does not describe, so nothing from that answer "
    "was kept."
)
ADDRESS_REFUSED: Final = (
    "The source's address resolved inside this network, so nothing was sent to it."
)
NO_VAULT: Final = (
    "The worker has no secrets vault, so the source's key could not be read. Set "
    "BRAIN_VAULT_ADDRESS and BRAIN_VAULT_TOKEN in the worker's environment, with a token minted "
    "against the worker policy, and restart the worker."
)
NO_KEY: Final = (
    "The vault holds no key for this source. Replace the key from this source's Manage menu."
)
VAULT_REFUSED: Final = (
    "The vault refused the worker's read of this source's key, or minted a run token wider than a "
    "run may hold. The worker and connector-run policies or the connector-run token role may not "
    "be loaded: ops/openbao/credential-slots.md has the steps."
)
VAULT_UNREACHABLE: Final = "The vault did not answer, so the source's key could not be read."
#: A source whose key file is exchanged for a token, read by a process given no way to post for one.
NO_KEY_FILE_EXCHANGE: Final = (
    "This process was given no way to exchange the source's key file for a token, so the source "
    "was not asked."
)
#: An MCP server that no longer lists a tool the connector calls as it was reviewed (M11.1.2).
TOOL_NOT_AS_REVIEWED: Final = (
    "The source's server no longer lists a tool this connector calls as it was reviewed, so no "
    "tool was called. It is read again once the connector is reviewed against the new definition."
)
#: A source whose calls are posts, read by a process given no way to post (M11.1.2, M11.1.5).
NO_WAY_TO_POST: Final = (
    "This process was given no way to post, and this source is read by posting, so it was not "
    "asked."
)
#: Custom code handed something carrying the source's key, so it was not run (M11.1.5).
KEY_KEPT_OUT: Final = (
    "What the connector's code would have been handed carried the source's key, so the code was "
    "not run and nothing was kept."
)
#: An MCP tool, or a custom connector's answer, that said in so many words that the read failed.
TOOL_SAID_IT_FAILED: Final = (
    "The source answered that it could not do the read, so nothing from that answer was kept."
)
#: Custom code that did not complete in its sandbox (M11.1.5).
CODE_DID_NOT_COMPLETE: Final = (
    "The connector's code did not complete in its sandbox, so nothing from that read was kept."
)
#: A source consented to by OAuth that nobody has consented to yet, or whose consent's refresh token
#: is not in the vault (M11.8.6).
NOT_CONSENTED: Final = (
    "Nobody has consented to this connection at the vendor yet, so there is nothing to renew its "
    "access with. Connect it with the vendor from this source's page."
)
#: A refresh token the vendor rotated during a read, which the vault would not keep. The vendor
#: voided the old one when it issued the new, so the next read cannot renew with it (M11.8.6).
ROTATED_REFRESH_NOT_KEPT: Final = (
    "The vendor issued a new refresh token with this read and the vault would not keep it, so the "
    "next read has nothing to renew with. Check the connector-rotate role and policy are loaded "
    "(ops/openbao/apply-release.sh), then connect it with the vendor again."
)
NOT_READ_YET: Final = "Not read yet. The worker reads it on its next run."

#: The screen's words for an attempt's outcome, by what follows it.
TRIED_AGAIN: Final = "It is tried again after"
FAILED_IN_A_ROW: Final = "Attempts that failed in a row:"

#: What a test of the connection came to, when it is not one of the failures above. Constants, for
#: `A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.
PROBE_ANSWERED: Final = (
    "The source accepted this install's key and answered in the shape this release reads. Nothing "
    "it sent was kept."
)
PROBE_REFUSED_FOR_NOW: Final = (
    "The source said its call allowance is spent for now, so the key could not be tested. Test "
    "again once the source has room."
)
PROBE_NOT_SENT_WHILE_WAITING: Final = (
    "No call was made: the source asked this install to wait before calling it again. Test again "
    "once that wait is over."
)
PROBE_NOT_SENT_SHARE_SPENT: Final = (
    "No call was made: tests have used this install's share of the source's call allowance for "
    "now. Test again later."
)
#: What a test on request says of an MCP or custom-code source, which it does not test yet.
PROBE_NOT_BUILT: Final = (
    "No call was made: testing this kind of source on request is not built yet. Its scheduled "
    "read says whether it works."
)
#: What the screen puts before a test's sentence, so it is not read as a scheduled read.
TESTED_ON_REQUEST: Final = "Tested on request:"


class SyncOutcome(enum.StrEnum):
    """What one attempt came to. Four, and `brain.tables.connector_sync.OUTCOMES` holds them.

    `QUOTA` is its own outcome rather than a kind of failure, for
    `A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED`. `PROBED` is a test a person asked for,
    for `A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT`; what the test found is its health and its
    sentence, read back by `verdict_of`.
    """

    SYNCED = "synced"
    QUOTA = "quota"
    FAILED = "failed"
    PROBED = "probed"


class ConnectorSyncError(Exception):
    """A reading produced something this store cannot keep. Raised before anything is written."""


INDEX_EXCEEDED: Final = (
    "A record read from this source holds a field its declaration does not name, so nothing from "
    "that answer was kept."
)


# ---------------------------------------------------------------- where a read stands


class ReadStateError(ValueError):
    """A read state that cannot be what a worker wrote."""


def _instant(value: object) -> datetime | None:
    """An aware instant from its stored form, or None for null. Raises for anything else."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReadStateError("an instant is stored as text")
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ReadStateError("a stored instant carries its zone")
    return moment


def page_cursor(arguments: Mapping[str, str]) -> str:
    """One page's arguments as the text a `BackfillCursor` carries, the same text for the same page.

    Keys sorted, so a page asked with its arguments in another order is still the page the loop
    check in `BackfillCursor.advance` compares against.
    """
    return json.dumps(dict(arguments), sort_keys=True, separators=(",", ":"))


def page_of(cursor: str) -> Mapping[str, str]:
    """The arguments a cursor holds, handed back to the reading unread. Raises for anything else."""
    held = json.loads(cursor)
    if not isinstance(held, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in held.items()
    ):
        raise ReadStateError("a page cursor holds a page's arguments and nothing else")
    return MappingProxyType(held)


@dataclass(frozen=True)
class ReadPass:
    """One read of a source from each entity's first page to its last, which may take attempts.

    `since` is what it asks for: the changes since that instant, or None for everything the source
    holds, which is the one kind of read that may retire (see
    `WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED`). `walks` holds, for each entity
    begun, where it has got to; an entity with no walk has not been asked for yet.
    """

    started_at: datetime
    since: datetime | None = None
    walks: Mapping[str, BackfillCursor] = field(default_factory=dict)
    #: Whether this read skipped something to reach its end: a routed server that did not answer, a
    #: folder past the walk's bound. A partial read retires nothing. See
    #: `WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED`.
    partial: bool = False

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or (self.since is not None and self.since.tzinfo is None):
            raise ReadStateError("a read's instants carry their zone")
        for entity, walk in self.walks.items():
            if walk.entity != entity:
                raise ReadStateError("a walk is filed under the entity it walks")

    @property
    def everything(self) -> bool:
        """Whether this read asks for everything rather than for what changed."""
        return self.since is None

    def walk(self, connector: str, entity: str) -> BackfillCursor:
        """Where this read has got to in one entity: its walk, or one not yet begun."""
        return self.walks.get(entity) or BackfillCursor(connector=connector, entity=entity)

    def advanced(self, walk: BackfillCursor) -> ReadPass:
        """This read with one entity's walk moved on."""
        return replace(self, walks=MappingProxyType({**self.walks, walk.entity: walk}))

    def complete(self, entities: Sequence[str]) -> bool:
        """Whether every entity was read to its last page. Not true of a read with no entity."""
        return bool(entities) and all(
            entity in self.walks and self.walks[entity].exhausted for entity in entities
        )

    def retires(self, entities: Sequence[str]) -> bool:
        """Whether this read may retire what it did not see: everything asked, nothing skipped,
        every entity read to its end. See
        `WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED`."""
        return self.everything and not self.partial and self.complete(entities)


@dataclass(frozen=True)
class ReadState:
    """Where reading one connected source stood when an attempt ended, as its row keeps it.

    The value of `ops.connector_sync.read_state`.

    `changed_since` is when the last complete read began, the cursor a read of changes asks from;
    `reconciled_at` when the last complete read of everything began, which the source's
    subscription measures a reconciliation from; `walking` the read an attempt stopped inside, which
    the next attempt carries on. See the module docstring.
    """

    changed_since: datetime | None = None
    reconciled_at: datetime | None = None
    walking: ReadPass | None = None

    def stored(self) -> dict[str, Any]:
        """The JSON the column holds. Instants, entity names and page cursors, and nothing else."""
        walking: dict[str, Any] | None = None
        if self.walking is not None:
            walking = {
                "started_at": self.walking.started_at.isoformat(),
                "since": None if self.walking.since is None else self.walking.since.isoformat(),
                "partial": self.walking.partial,
                "walks": {
                    entity: {
                        "cursor": walk.cursor,
                        "pages": walk.pages,
                        "records": walk.records,
                        "exhausted": walk.exhausted,
                    }
                    for entity, walk in sorted(self.walking.walks.items())
                },
            }
        return {
            "changed_since": None if self.changed_since is None else self.changed_since.isoformat(),
            "reconciled_at": None if self.reconciled_at is None else self.reconciled_at.isoformat(),
            "walking": walking,
        }

    @classmethod
    def from_stored(cls, connector: str, value: object) -> ReadState | None:
        """The state a column holds, or None where it holds none or nothing a worker wrote.

        None rather than a refusal for a value that does not parse: the next read then reads
        everything from the start, which costs calls and loses nothing, where a refusal would stop
        the source being read at all until somebody edited a row.
        """
        if not isinstance(value, dict):
            return None
        try:
            walking: ReadPass | None = None
            held = value.get("walking")
            if isinstance(held, dict):
                started = _instant(held.get("started_at"))
                if started is None:
                    raise ReadStateError("a read under way began at an instant")
                walks: dict[str, BackfillCursor] = {}
                stored_walks = held.get("walks")
                if not isinstance(stored_walks, dict):
                    raise ReadStateError("a read under way holds its walks")
                for entity, walk in stored_walks.items():
                    if not isinstance(entity, str) or not isinstance(walk, dict):
                        raise ReadStateError("a walk is an entity's")
                    cursor, pages = walk.get("cursor"), walk.get("pages")
                    records, exhausted = walk.get("records"), walk.get("exhausted")
                    if not (
                        isinstance(cursor, str)
                        and isinstance(pages, int)
                        and isinstance(records, int)
                        and isinstance(exhausted, bool)
                    ):
                        raise ReadStateError("a walk is a cursor and three counts")
                    if cursor:
                        page_of(cursor)
                    walks[entity] = BackfillCursor(
                        connector=connector,
                        entity=entity,
                        cursor=cursor,
                        pages=pages,
                        records=records,
                        exhausted=exhausted,
                    )
                partial = held.get("partial", False)
                if not isinstance(partial, bool):
                    raise ReadStateError("whether a read skipped something is true or false")
                walking = ReadPass(
                    started_at=started,
                    since=_instant(held.get("since")),
                    walks=MappingProxyType(walks),
                    partial=partial,
                )
            elif held is not None:
                raise ReadStateError("a read under way is an object")
            return cls(
                changed_since=_instant(value.get("changed_since")),
                reconciled_at=_instant(value.get("reconciled_at")),
                walking=walking,
            )
        except (ReadStateError, ValueError):
            return None


def next_read(reading: SourceReading, state: ReadState | None, *, now: datetime) -> ReadPass:
    """The read the next attempt makes, asked in the order the module docstring gives.

    The read an earlier attempt stopped inside, carried on; else, for a source that can be asked
    for its changes, a read of what changed since the last complete read began less
    `CURSOR_OVERLAP`, unless it has never been read whole or its subscription says a
    reconciliation is owed; else a read of everything, begun now.
    """
    if state is not None and state.walking is not None:
        return state.walking
    if (
        state is None
        or state.changed_since is None
        or state.reconciled_at is None
        or not isinstance(reading, ChangedSince)
    ):
        return ReadPass(started_at=now)
    reconciled_at = state.reconciled_at
    owed = any(
        reading.subscription(entity).reconciliation_due(now=now, last_reconciled_at=reconciled_at)
        for entity in reading.entities()
    )
    if owed:
        return ReadPass(started_at=now)
    return ReadPass(started_at=now, since=state.changed_since - CURSOR_OVERLAP)


def page_to_ask(
    reading: SourceReading,
    read: ReadPass,
    walk: BackfillCursor,
    *,
    settings: Mapping[str, str] = MappingProxyType({}),
) -> Mapping[str, str] | None:
    """The page a walk asks next: where it stopped, else the first, else None when it is done.

    A read of changes asks the first page through `ChangedSince.changed_since`; a reading that
    cannot be asked that is read from its ordinary first page, which asks for everything and so
    for at least what was wanted. A routed reading's first page is the connection's own first
    route, from `settings`, and None where it has none. See
    `A_WALK_CUT_SHORT_IS_CARRIED_ON_IN_EVERY_SHAPE`.
    """
    if walk.exhausted:
        return None
    if walk.cursor:
        return page_of(walk.cursor)
    if isinstance(reading, RoutedReading):
        return reading.first_route(walk.entity, settings=settings)
    if read.since is not None and isinstance(reading, ChangedSince):
        return reading.changed_since(walk.entity, read.since)
    return reading.first_page(walk.entity)


def after_the_read(
    previous: ReadState | None, read: ReadPass, entities: Sequence[str]
) -> ReadState:
    """What an attempt leaves: a finished read's start as the cursor, or the read to carry on."""
    before = previous or ReadState()
    if not read.complete(entities):
        return replace(before, walking=read)
    return ReadState(
        changed_since=read.started_at,
        reconciled_at=read.started_at if read.everything else before.reconciled_at,
        walking=None,
    )


def changed(
    held: Mapping[str, Mapping[str, StoredValue]],
    kept: Sequence[tuple[ProjectedRecord, Mapping[str, StoredValue]]],
) -> bool:
    """Whether writing a page changes what the index says. See
    `A_CHANGED_READ_ADVANCES_ITS_SOURCE_S_EPOCH`.

    `held` is the live index rows the page names, by source id, as they were before it is written.
    """
    return any(
        record.source_id not in held or dict(held[record.source_id]) != dict(fields)
        for record, fields in kept
    )


# ------------------------------------------------------------------------- what is kept


@dataclass(frozen=True)
class SyncState:
    """What a connection's last attempt left behind, as the next run and the screen read it."""

    connector: str
    finished_at: datetime
    outcome: SyncOutcome
    health: HealthState
    consecutive_failures: int
    next_attempt_at: datetime
    detail: str
    #: When the source was last read to the end, which may be long before this attempt.
    last_synced_at: datetime | None
    #: Where reading the source stood, from the newest attempt that recorded it. None before the
    #: first read and on every row before `0179`.
    read_state: ReadState | None = None


@dataclass(frozen=True)
class Attempt:
    """One finished attempt, as the row `brain.tables.connector_sync` keeps."""

    connector: str
    started_at: datetime
    finished_at: datetime
    outcome: SyncOutcome
    health: HealthState
    records: int
    consecutive_failures: int
    next_attempt_at: datetime
    detail: str
    #: How the attempt's vault lease ended. Set by `brain.ops.connector_sync_run.attempt`, which
    #: holds the lease; this module decides nothing about it. See `brain.ops.connector_lease`.
    lease: LeaseOutcome = LeaseOutcome.NONE
    #: Where reading the source stood when the attempt ended. None for a test of the connection,
    #: which reads nothing, so the worker carries on from the attempt before it.
    read_state: ReadState | None = None


#: A value `proj.record.fields` can hold as JSON.
StoredValue = str | int | float | bool | None


def storable_predicate(visibility: Scope) -> bool:
    """Whether every clause of a source's predicate is an equality a record can carry.

    See `THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS`. An unrestricted
    predicate is not storable either: `ProjectedEntity` already refuses one, and a record carrying
    no visibility field is a record the demo measured nobody reaching.
    """
    return bool(visibility.clauses) and all(
        clause.op is Op.EQ and isinstance(clause.value, str) for clause in visibility.clauses
    )


def stored_fields(record: ProjectedRecord, visibility: Scope) -> dict[str, StoredValue]:
    """What `proj.record.fields` holds for one record: its projected fields and its predicate's.

    Built through `ProjectedRecord` a second time, over the whole set, because the table's cap
    counts every key and the constructor is where the cap is enforced: the projected fields plus
    the predicate's must still be twelve or fewer. A timestamp is written as ISO 8601 with its zone,
    which is how `brain.connectors.projection.assess_staleness` and a reader both parse it back.
    """
    if not storable_predicate(visibility):
        raise ConnectorSyncError(VISIBILITY_NOT_STORABLE)
    placed = {clause.field: str(clause.value) for clause in visibility.clauses}
    clashing = sorted(
        name
        for name, value in placed.items()
        if name in record.fields and record.fields[name] != value
    )
    if clashing:
        msg = (
            f"{record.source}.{record.entity} {record.source_id} holds {clashing} with a value its "
            f"source's visibility rule does not name. "
            f"{THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS}"
        )
        raise ConnectorSyncError(msg)
    whole = ProjectedRecord(
        source=record.source,
        entity=record.entity,
        source_id=record.source_id,
        last_seen_at=record.last_seen_at,
        fields={**record.fields, **placed},
    )
    return {
        name: value.isoformat() if isinstance(value, datetime) else value
        for name, value in sorted(whole.fields.items())
    }


def kept_fields(record: ProjectedRecord, manifest: ConnectorManifest) -> dict[str, StoredValue]:
    """`stored_fields` for a record of this manifest, held to its minimal index before it is kept.

    The entity's projection is the manifest's, so a record of an entity the manifest does not
    project is refused, and the fields `stored_fields` lays out are checked by
    `assert_minimal_index`: declared, pointer-shaped, the predicate's value, and no longer than a
    label. A refusal carries `INDEX_EXCEEDED` and never the row, for
    `A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.
    """
    projection = manifest.projection_for(record.entity)
    if projection is None:
        raise ConnectorSyncError(INDEX_EXCEEDED)
    fields = stored_fields(record, projection.visibility)
    row = StoredRow(
        source=record.source, entity=record.entity, source_id=record.source_id, fields=fields
    )
    try:
        assert_minimal_index(manifest, (row,))
    except MinimalIndexError as exceeded:
        raise ConnectorSyncError(INDEX_EXCEEDED) from exceeded
    return fields


# ------------------------------------------------------------------------- the readings


#: Every source this release reads on a schedule, by connector name, read off each connector's
#: `CONNECTOR` declaration at start-up. `PageReply`, `SourceReading` and `ViewReading` are
#: `brain.connectors.declaration`'s, named here for the modules that read them from this one.
#: Since M11.7.8 they are `brain.ops.connector_catalogue.declarations`', so a connector reviewed on
#: this install is read from the first cycle after it is approved and not after it changes.
READINGS: Final[Mapping[str, Reading]] = Derived(
    lambda found: {name: one.reading for name, one in found.items() if one.reading is not None}
)


# ---------------------------------------------------------------------------- the plan


@dataclass(frozen=True)
class SyncPlan:
    """Whether one connection may be read, and everything a read needs when it may.

    `refused` is empty exactly when `manifest` and `reading` are set, and the constructor holds
    that, so a plan cannot say it may run while missing what running needs.
    """

    connector: str
    refused: str = ""
    manifest: ConnectorManifest | None = None
    reading: Reading | None = None
    limits: tuple[Limit, ...] = ()
    #: Whether its next attempt is owed now. False for a refused plan.
    due: bool = False

    def __post_init__(self) -> None:
        runnable = self.manifest is not None and self.reading is not None
        if runnable == bool(self.refused):
            msg = (
                f"a plan for {self.connector!r} must either say why it cannot run or carry what "
                "running needs, and this one does both or neither"
            )
            raise ConnectorSyncError(msg)
        if self.due and not runnable:
            msg = f"a refused plan for {self.connector!r} cannot be due"
            raise ConnectorSyncError(msg)


def plan_for(
    connection: Connection,
    *,
    last: SyncState | None,
    now: datetime,
    readings: Mapping[str, Reading] = READINGS,
    runner: ScriptRunner | None = None,
    manifests: Callable[[str, Mapping[str, str]], ConnectorManifest] | None = None,
) -> SyncPlan:
    """Whether this connection may be read now, asked in the order the module docstring gives.

    `runner` is the sandbox runner this install runs custom code with, or None when it runs none
    (`brain.ops.custom_code_run.installed_runner`); only a custom-code reading asks for it.
    `manifests` builds a connection's manifest from its settings: the console's own
    `manifest_for` when None, for every shipped connector; an acceptance check hands in one
    built for a connector it made up, so it reads that connector by this same plan.
    """
    name = connection.connector
    reading = readings.get(name)
    if reading is None:
        return SyncPlan(connector=name, refused=NO_READING)
    try:
        build = manifest_for if manifests is None else manifests
        manifest = build(name, connection.settings)
    except (NotConnectableError, ConnectorContractError):
        return SyncPlan(connector=name, refused=DECLARATION_CANNOT_BE_REBUILT)
    if manifest_digest(manifest) != connection.digest:
        return SyncPlan(connector=name, refused=DECLARATION_NOT_AGREED)
    if not all(storable_predicate(one.visibility) for one in manifest.projections):
        return SyncPlan(connector=name, refused=VISIBILITY_NOT_STORABLE)
    try:
        limits = limits_for(manifest, principal_id=SYNC_PRINCIPAL)
    except UnmeasuredSourceError:
        return SyncPlan(connector=name, refused=NO_VERIFIED_CEILING)
    if isinstance(reading, CodeReading) and runner is None:
        return SyncPlan(connector=name, refused=NO_SANDBOX)
    return SyncPlan(
        connector=name,
        manifest=manifest,
        reading=reading,
        limits=limits,
        due=last is None or now >= last.next_attempt_at,
    )


# ----------------------------------------------------------------- what an attempt costs


def after_attempt(
    *,
    connector: str,
    started_at: datetime,
    finished_at: datetime,
    outcome: SyncOutcome,
    detail: str,
    interval: timedelta,
    previous: SyncState | None,
    call: CallOutcome | None = None,
    retry_after_seconds: float | None = None,
    records: int = 0,
    cut_short: bool = False,
    read_state: ReadState | None = None,
) -> Attempt:
    """The row one attempt leaves: its health, the failures in a row, and when to try again.

    The whole backoff rule is here and nowhere else. See
    `A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY`,
    `A_SOURCE_IS_UNHEALTHY_AFTER_THREE_FAILURES_IN_A_ROW` and
    `A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED`.
    """
    carried = 0 if previous is None else previous.consecutive_failures
    if outcome is SyncOutcome.SYNCED:
        failures = 0
        health = HealthState.DEGRADED if cut_short else HealthState.OK
        wait = interval
    elif outcome is SyncOutcome.QUOTA:
        failures = carried
        health = HealthState.DEGRADED
        stated = 0.0 if retry_after_seconds is None else retry_after_seconds
        waited = retry_delay(retry_after_seconds=retry_after_seconds, consecutive_refusals=0)
        wait = timedelta(seconds=max(waited, stated))
    else:
        failures = carried + 1
        down = failures >= UNHEALTHY_AFTER_FAILURES or call is CallOutcome.REJECTED
        health = HealthState.DOWN if down else HealthState.DEGRADED
        # The exponent stops growing long after the cap binds, so a source failing for a year
        # cannot overflow the arithmetic that says to wait a day.
        wait = min(interval * 2 ** min(failures - 1, 16), LONGEST_WAIT_AFTER_FAILURES)
    return Attempt(
        connector=connector,
        started_at=started_at,
        finished_at=finished_at,
        outcome=outcome,
        health=health,
        records=records,
        consecutive_failures=failures,
        next_attempt_at=finished_at + wait,
        detail=detail,
        read_state=read_state,
    )


class ProbeVerdict(enum.StrEnum):
    """What a test found, read back from its sentence. `verdict_of` is the only reader."""

    #: The source took the key and answered in a shape this release reads.
    ANSWERED = "answered"
    #: The source refused for volume; the key is neither proved nor refused.
    WAITING = "waiting"
    #: The call was made, or the key could not be read, and it did not work.
    FAILED = "failed"
    #: No call was made, and the sentence says why.
    NOT_SENT = "not_sent"


#: Every sentence a test that made no call can leave: the plan's refusals, and the two waits.
NOT_SENT_SENTENCES: Final[frozenset[str]] = frozenset(
    {
        NO_READING,
        DECLARATION_CANNOT_BE_REBUILT,
        DECLARATION_NOT_AGREED,
        VISIBILITY_NOT_STORABLE,
        NO_VERIFIED_CEILING,
        PROBE_NOT_SENT_WHILE_WAITING,
        PROBE_NOT_SENT_SHARE_SPENT,
    }
)


def verdict_of(detail: str) -> ProbeVerdict:
    """What a test's row found, from its sentence, which is always one of this module's constants.

    Anything not named as answered, waiting or not sent is a failure, which is the direction to be
    wrong in: a sentence this build does not know is shown as not working rather than as working.
    """
    if detail == PROBE_ANSWERED:
        return ProbeVerdict.ANSWERED
    if detail == PROBE_REFUSED_FOR_NOW:
        return ProbeVerdict.WAITING
    if detail in NOT_SENT_SENTENCES:
        return ProbeVerdict.NOT_SENT
    return ProbeVerdict.FAILED


def after_probe(
    *,
    connector: str,
    started_at: datetime,
    finished_at: datetime,
    detail: str,
    interval: timedelta,
    previous: SyncState | None,
    call: CallOutcome | None = None,
    retry_after_seconds: float | None = None,
) -> Attempt:
    """The row one test leaves: what it found, and the schedule as the attempt before left it.

    See `A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT`. The health of a failure and the length of a
    wait are `after_attempt`'s, asked as though the test were a scheduled read, so there is one rule
    for when a source is down and one for how long a refusal waits. A test that made no call has
    learned nothing about the source and keeps the health it had; with no attempt before it, the
    only way to make no call is a plan that refuses, and a source nothing can read is down.
    """
    failures = 0 if previous is None else previous.consecutive_failures
    carried = finished_at if previous is None else max(previous.next_attempt_at, finished_at)

    def as_read(outcome: SyncOutcome) -> Attempt:
        return after_attempt(
            connector=connector,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            detail=detail,
            interval=interval,
            previous=previous,
            call=call,
            retry_after_seconds=retry_after_seconds,
        )

    next_at = carried
    match verdict_of(detail):
        case ProbeVerdict.ANSWERED:
            health = HealthState.OK
        case ProbeVerdict.WAITING:
            waited = as_read(SyncOutcome.QUOTA)
            health, next_at = waited.health, max(carried, waited.next_attempt_at)
        case ProbeVerdict.FAILED:
            health = as_read(SyncOutcome.FAILED).health
        case ProbeVerdict.NOT_SENT:
            health = HealthState.DOWN if previous is None else previous.health
    return Attempt(
        connector=connector,
        started_at=started_at,
        finished_at=finished_at,
        outcome=SyncOutcome.PROBED,
        health=health,
        records=0,
        consecutive_failures=failures,
        next_attempt_at=next_at,
        detail=detail,
    )


def failure_detail(call: CallOutcome, *, timed_out: bool = False) -> str:
    """The sentence a failed call leaves, by what kind of failure it was and nothing else."""
    if timed_out:
        return SOURCE_TIMED_OUT
    if call is CallOutcome.REJECTED:
        return KEY_DECLINED
    return SOURCE_UNREACHABLE


def database_failure_detail(call: CallOutcome) -> str:
    """The sentence a failed read of a database's view leaves. See `DATABASE_REFUSED`."""
    return DATABASE_REFUSED if call is CallOutcome.REJECTED else failure_detail(call)


def sync_in_words(plan: SyncPlan | None, state: SyncState | None) -> str:
    """What the Connectors screen says about reading one source.

    A refused plan says why nothing reads it, whatever an older attempt said, because the refusal is
    what is true now. A source nothing has tried says so rather than drawing a blank.
    """
    if plan is not None and plan.refused:
        return plan.refused
    if state is None:
        return NOT_READ_YET
    if state.outcome is SyncOutcome.PROBED:
        return f"{TESTED_ON_REQUEST} {state.detail}"
    if state.outcome is SyncOutcome.SYNCED:
        return state.detail
    said = f"{state.detail} {TRIED_AGAIN} {state.next_attempt_at.isoformat()}."
    if state.consecutive_failures > 1:
        said = f"{said} {FAILED_IN_A_ROW} {state.consecutive_failures}."
    return said
