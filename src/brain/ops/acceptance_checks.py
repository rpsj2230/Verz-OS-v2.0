"""The install acceptance checks: each a function proving named leaves on the install it runs on.

Each check is handed a `brain.ops.acceptance_run.Harness` and exercises the install's own services
as reserved principals of the reserved departments: its database through the product's stores and
their policies, its cache, its registry, its parsers. None of them signs anybody in. A check that
needs a person's reach loads it through `brain.gate.entitlement_store.StoredEntitlements`, the one
resolver, and calls the function the route would have called with that reach, which is how
`brain.ops.canary_run` asks as a reach without an account.

**How to add one.** Write an async function taking the harness, decorate it with `@check(leaves=...,
sentence=...)`, and raise `CheckFailedError` or `CheckNotRunError` with a literal sentence when the
install does not do what the sentence says. The sentence is what a person closing the task would
write; the reasons are what the Install page shows beside a red row, so each one says what was not
seen and never what was read. Everything a check writes goes through `harness.sessions` and is
rolled back when it ends; anything outside the database it touches is registered with
`harness.removes`.

**What each check deliberately does not do, stated once.** The webhook check holds its secret in
memory and never writes the vault: the install keeps one record and one slot per channel kind, the
application's vault policy cannot delete a slot, and a check that wrote one would replace the
install's own. Its reply goes to a transport that keeps the request and sends nothing, and its
operation ledger is held in memory, because `brain.ops.idempotency` commits a claim before the
vendor call by design and a committed claim cannot be rolled back. The documents check stores the
item the upload door reads, and stores it without queueing an embedding, which is the install with
no worker that M7.6.3 names.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from itertools import pairwise
from typing import Any, Final, cast

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_run import Harness

A, B = RESERVED_DEPARTMENTS

#: The four reads a department's knowledge reader holds, as a Starter pack assignment grants them.
KNOWLEDGE_READS: Final = (
    "read:knowledge",
    "read:knowledge.document",
    "read:knowledge.title",
    "read:knowledge.updated_at",
)


def _in(department: str, *capabilities: str) -> tuple[tuple[str, Scope], ...]:
    return tuple((one, Scope.department(department)) for one in capabilities)


async def _ledger(h: Harness, subject: str) -> list[tuple[str, dict[str, Any]]]:
    """The actor and details of every entry about `subject` the check's transaction holds."""
    rows = (
        await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry"
                " WHERE subject = :subject ORDER BY seq"
            ).bindparams(subject=subject)
        )
    ).all()
    return [
        (str(actor), details if isinstance(details, dict) else json.loads(details))
        for actor, details in rows
    ]


# ------------------------------------------------------------------------ 1. limits
@check(
    leaves=("M23.1.1", "M23.1.2", "M23.1.3", "M23.1.5"),
    sentence=(
        "In the install's own cache, a person, a channel and an agent each asked past a window of "
        "two a minute are refused with a retry hint, and the refused asks are not counted, so the "
        "window does not move."
    ),
)
async def asking_past_a_window_is_refused_with_a_retry_hint(h: Harness) -> None:
    from brain.cache import make_client
    from brain.ops.limit_store import make_store, refusals_key, render_key
    from brain.ops.limits import LimitScope, request_limits, retry_after_header, retry_hint

    if not h.settings.valkey_url:
        raise CheckNotRunError("this install names no cache, so there is no window to ask")
    client = make_client(h.settings.valkey_url)
    store = make_store(client)
    wide, tight = 1000, 2
    for scope in (LimitScope.PRINCIPAL, LimitScope.CHANNEL, LimitScope.AGENT):
        asker = h.principal(A, f"asker{scope.value}")
        limits = request_limits(
            principal_id=asker,
            channel=f"acceptance.{h.run}.{scope.value}",
            agent_id=f"acceptance.{h.run}.{scope.value}",
            principal_per_minute=tight if scope is LimitScope.PRINCIPAL else wide,
            channel_per_minute=tight if scope is LimitScope.CHANNEL else wide,
            agent_per_minute=tight if scope is LimitScope.AGENT else wide,
        )
        keys = [render_key(one.key) for one in limits] + [refusals_key(asker)]
        # Only this run's own subjects: see WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME.
        h.removes(partial(cast(Any, client).delete, *keys))
        binding = next(one for one in limits if one.scope is scope)

        async def ask(at: float, limits: Any = limits, asker: str = asker) -> Any:
            return await asyncio.to_thread(
                store.check_and_record,
                now=datetime.fromtimestamp(at).astimezone(),
                limits=limits,
                caller=asker,
            )

        start = time.time()
        admitted = [await ask(start), await ask(start + 1)]
        if any(one.degraded for one in admitted):
            raise CheckFailedError("the cache did not answer, so every window failed open")
        if not all(one.allowed for one in admitted):
            raise CheckFailedError("a window of two refused one of its first two asks")
        refused = [await ask(start + 2), await ask(start + 3), await ask(start + 4)]
        if any(one.allowed for one in refused):
            raise CheckFailedError("a third ask inside a window of two was admitted")
        first = refused[0].decision
        if first.binding is None or first.binding.key != binding.key:
            raise CheckFailedError("a refusal named a window other than the one it was past")
        wait = retry_hint(
            first.retry_after_seconds,
            consecutive_refusals=refused[0].consecutive_refusals,
            jitter=0.0,
        )
        if not 0 < wait <= binding.window_seconds or int(retry_after_header(wait)) < 1:
            raise CheckFailedError("a refusal carried no usable hint of when to ask again")
        hints = [one.decision.retry_after_seconds for one in refused]
        if any(later > earlier for earlier, later in pairwise(hints)):
            raise CheckFailedError("a refused ask pushed the end of its window further away")
        held = await asyncio.to_thread(cast(Any, client).zrange, render_key(binding.key), 0, -1)
        if len(held) != len(admitted):
            raise CheckFailedError("the window holds more asks than it admitted")


# ----------------------------------------------------------------------- 2. webhook
@dataclass
class _Secret:
    """`brain.channels.inbound.ChannelSecrets` over a secret this check made and holds."""

    value: str = field(repr=False)

    def read(self, ref: object) -> str | None:
        del ref
        return self.value

    def held(self, ref: object) -> bool:
        del ref
        return True


@dataclass
class _Kept:
    """`brain.channels.adapter.ChannelTransport` that keeps each request and sends nothing."""

    sent: list[Any] = field(default_factory=list)

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        self.sent.append(request)
        return VendorAnswer(status=200)

    def read(self, request: Any) -> Any:
        """Nothing is read from a vendor either: the check has no vendor behind it."""
        from brain.channels.adapter import VendorAnswer

        del request
        return VendorAnswer(connection_failed=True)


class _HeldLedger:
    """`brain.ops.idempotency.OperationLedger` in memory, with claim, win and settle's rules."""

    def __init__(self) -> None:
        self.records: dict[str, Any] = {}

    def claim(self, operation: Any) -> Any:
        return self.records.setdefault(operation.key, operation)

    def win(self, key: str) -> bool:
        from brain.ops.idempotency import OperationState

        record = self.records[key]
        if record.state is not OperationState.PENDING:
            return False
        self.records[key] = record.advanced(OperationState.SENT)
        return True

    def settle(self, key: str, *, frm: Any, to: Any) -> Any:
        from brain.ops.idempotency import advance

        advance(frm, to)
        record = self.records[key]
        if record.state is not frm:
            raise CheckFailedError("the operation ledger was asked to move a record twice")
        self.records[key] = record.advanced(to)
        return self.records[key]


@dataclass
class _Spy:
    """The install's webhook wire, counting how often it was asked to read a body."""

    wire: Any
    reads: int = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.wire, name)

    def read(self, arrived: Any) -> Any:
        self.reads += 1
        return self.wire.read(arrived)


@check(
    leaves=("M10.2.1", "M10.3.3", "M10.4.5", "M10.6.3"),
    sentence=(
        "A webhook channel set up with a secret the check made refuses a bad signature before "
        "reading the body, claims a signed message once and its redelivery never, sends an unbound "
        "sender the prompt, re-checks a reply's reach at send time, and switched off neither "
        "receives nor sends while every other channel's record is untouched."
    ),
)
async def a_webhook_channel_receives_once_and_stops_both_ways(h: Harness) -> None:
    from brain.channels.adapter import channel_wires
    from brain.channels.inbound import NoBindingsYet, receive, reply_for
    from brain.channels.outbound import Outgoing, deliver
    from brain.channels.webhook import REPLY_URL, SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
    from brain.gate.context import Channel
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.ingress import Unrecognised
    from brain.ops.channel_store import StoredChannels, StoredClaims, StoredDeliveries
    from brain.ops.idempotency import Intent
    from brain.tables.channel import DeliveryOutcome, RefusedBecause

    await h.found_departments()
    recipient = h.principal(A, "recipient")
    await h.person(recipient, department=A, grants=_in(A, "read:knowledge"))
    channels = StoredChannels(h.sessions)
    before = {one.channel: one for one in await channels.every() if one.channel != Channel.WEBHOOK}
    record = await channels.save(
        Channel.WEBHOOK,
        enabled=True,
        tenant={REPLY_URL: f"https://acceptance.invalid/{h.run}"},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    made = _Secret(secrets.token_hex(32))
    spy = _Spy(channel_wires()[Channel.WEBHOOK])
    claims, deliveries = StoredClaims(h.sessions), StoredDeliveries(h.sessions)
    message = json.dumps(
        {"id": f"acceptance-{h.run}", "sender": f"acceptance-{h.run}", "text": h.word()}
    ).encode()
    read_bodies: list[int] = []

    async def arrive(record: Any, signed_with: str) -> Any:
        stamp = str(int(time.time()))

        async def body() -> bytes:
            read_bodies.append(1)
            return message

        return await receive(
            spy,
            record=record,
            headers={TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: sign(signed_with, stamp, message)},
            declared_length=len(message),
            body=body,
            secrets=made,
            claims=claims,
            deliveries=deliveries,
            now=h.now,
        )

    forged = await arrive(record, secrets.token_hex(32))
    if forged.reason is not RefusedBecause.BAD_SIGNATURE or spy.reads:
        raise CheckFailedError("a message with a bad signature was not refused before it was read")
    accepted = await arrive(record, made.value)
    again = await arrive(record, made.value)
    if accepted.inbound is None or again.inbound is not None:
        raise CheckFailedError("a signed message and its redelivery were not claimed exactly once")
    claimed = (
        await h.execute(
            text(
                "SELECT count(*) FROM gate.channel_event WHERE channel = :c AND external_id = :e"
            ).bindparams(c=Channel.WEBHOOK.value, e=f"acceptance-{h.run}")
        )
    ).scalar_one()
    if claimed != 1:
        raise CheckFailedError("the channel's dedupe index did not hold one claim for a message")

    kept, ledger = _Kept(), _HeldLedger()
    reach = StoredEntitlements(h.sessions)

    async def send(outgoing: Any, record: Any) -> Any:
        return await deliver(
            outgoing,
            record=record,
            secrets=made,
            reach=reach,
            transport=kept,
            ledger=lambda work: work(cast(Any, ledger)),
            deliveries=deliveries,
            now=h.now,
        )

    prompts = await reply_for(
        accepted, record=record, bindings=NoBindingsYet(), answerer=None, now=h.now
    )
    unbound = Unrecognised(channel=Channel.WEBHOOK).prompt
    if prompts is None or [one.text for one in prompts] != [unbound]:
        raise CheckFailedError("a sender bound to nobody was not answered with the binding prompt")
    if (await send(prompts[0], record)).outcome is not DeliveryOutcome.SENT or len(kept.sent) != 1:
        raise CheckFailedError("the prompt to an unbound sender was not sent once")

    planned = (await h.reach(recipient)).ent_hash()

    def answer(n: int) -> Any:
        return Outgoing(
            channel=Channel.WEBHOOK,
            to=f"acceptance-{h.run}",
            intent=Intent(principal_id=recipient, intent_ref=f"acceptance.{h.run}.{n}"),
            text="An acceptance check reply.",
            recipient=recipient,
            planned_hash=planned,
        )

    if (await send(answer(1), record)).outcome is not DeliveryOutcome.SENT:
        raise CheckFailedError("an answer made at its recipient's current reach was not sent")
    await h.grant(recipient, "read:knowledge.title", Scope.department(A))
    changed = await send(answer(2), record)
    if changed.reason is not RefusedBecause.REACH_CHANGED or len(kept.sent) != 2:
        raise CheckFailedError("an answer was sent after its recipient's reach changed")

    off = await channels.switch(
        Channel.WEBHOOK, enabled=False, actor=h.actor, ent_hash="0" * 32, trace_id=h.trace_id
    )
    if off is None or off.enabled:
        raise CheckFailedError("the channel could not be switched off")
    read_bodies.clear()
    stopped_in = await arrive(off, made.value)
    stopped_out = await send(answer(3), off)
    if stopped_in.reason is not RefusedBecause.SWITCHED_OFF or read_bodies:
        raise CheckFailedError("a switched-off channel read a message it should have refused")
    if stopped_out.reason is not RefusedBecause.SWITCHED_OFF or len(kept.sent) != 2:
        raise CheckFailedError("a switched-off channel sent a message")
    after = {one.channel: one for one in await channels.every() if one.channel != Channel.WEBHOOK}
    if after != before:
        raise CheckFailedError("switching one channel off changed another channel's record")
    changes = [d.get("change") for _, d in await _ledger(h, f"setting:channel.{record.channel}")]
    if "set" not in changes or changes[-1:] != ["switched_off"]:
        raise CheckFailedError("setting up and switching off the channel did not reach the ledger")


# ----------------------------------------------------------------------- 4. documents
async def _upload(
    h: Harness,
    uploader: str,
    *,
    filename: str,
    declared: str,
    body: bytes,
) -> Any:
    """The upload route's own sequence, as `uploader`: placed, admitted, read, then stored."""
    from brain.knowledge.chunk_store import ingest_document
    from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET
    from brain.knowledge.ingest import ParseFailure, admit_upload, ceiling_for
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.uploads import (
        ReceivedUpload,
        assert_declared_length,
        assert_safe_filename,
        placement_for_upload,
        text_path_type,
    )
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_routes import (
        live_departments,
        may_add,
        read_one_at_a_time,
        reads_knowledge,
    )
    from brain.tables.audit import attributed_to

    reach = await h.reach(uploader)
    placement = placement_for_upload(
        Visibility.DEPARTMENT,
        department=A,
        owner_id=uploader,
        may_add=may_add(reach, await live_departments(h.sessions), h.now),
        reads_knowledge=reads_knowledge(reach, h.now),
    )
    assert_safe_filename(filename)
    media_type = text_path_type(declared)
    assert_declared_length(media_type=media_type, content_length=len(body))
    if len(body) > ceiling_for(media_type):
        raise CheckFailedError("a document well inside the limits was over them")
    received = ReceivedUpload(
        upload=admit_upload(filename=filename, declared_type=media_type.value, content=body),
        body=body,
    )
    read = await asyncio.to_thread(
        read_one_at_a_time,
        received,
        kind=KnowledgeKind.SOP,
        placement=placement,
        owner_id=uploader,
    )
    if isinstance(read, ParseFailure):
        return read

    async def no_queue(job: object) -> object:
        raise CheckFailedError("an upload on the text path queued work for a worker")

    await ingest_document(
        h.sessions,
        read.item,
        enqueue=no_queue,
        now=h.now,
        env={REVISION_SETTING: REVISION_UNSET},
        blocks=read.blocks,
        attributed=attributed_to(actor_id=uploader, ent_hash=reach.ent_hash(), trace_id=h.trace_id),
    )
    return read


async def _found(h: Harness, reader: str, word: str) -> tuple[Any, list[dict[str, Any]]]:
    """A text search for `word` as `reader`, and what the passage policy lets them read of it."""
    from brain.core.redaction import redact
    from brain.gate.model_lane import PASSAGE_POLICY
    from brain.knowledge.document_tools import DocumentSearch, searcher
    from brain.knowledge.row_store import SessionRowSource

    reach = await h.reach(reader)
    found = await searcher(SessionRowSource(h.sessions))(
        DocumentSearch(question=word), entitlement=reach, now=h.now
    )
    kept = redact(found, entitlement=reach, policy=PASSAGE_POLICY, now=h.now).payload
    return found, [dict(one) for one in kept.records]


@check(
    leaves=("M7.1.1", "M7.2.5", "M7.4.3", "M7.6.3", "M7.7.1"),
    sentence=(
        "A Markdown, a PDF and a Word file uploaded into acceptance_a with no worker are found by "
        "text search by the test member, each passage carrying its department, level and owner; a "
        "reader in acceptance_b gets what a search for nothing gets; no upload is placed wider "
        "than its uploader may add; a damaged PDF and an unread type are refused by name."
    ),
)
async def documents_are_answered_in_their_department_only(h: Harness) -> None:
    from brain.knowledge.ingest import (
        CAUSE_TEXT,
        IngestRefused,
        MediaType,
        ParseCause,
        ParseFailure,
    )
    from brain.knowledge.uploads import (
        UploadNotOffered,
        assert_declared_length,
        placement_for_upload,
        text_path_type,
    )
    from brain.knowledge.visibility import Visibility, VisibilityError
    from brain.knowledge_routes import live_departments, may_add, reads_knowledge
    from brain.ops.acceptance_documents import (
        CORRUPT_PDF,
        a_markdown_document,
        a_pdf,
        a_word_document,
    )

    await h.found_departments()
    reader_a = await h.test_login("member", department=A, grants=_in(A, *KNOWLEDGE_READS))
    admin, reader_b = h.principal(A, "library"), h.principal(B, "user")
    await h.person(admin, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(reader_b, department=B, grants=_in(B, *KNOWLEDGE_READS))
    held = await h.reach(admin)
    registry = await live_departments(h.sessions)
    for level, department in ((Visibility.COMPANY, A), (Visibility.DEPARTMENT, B)):
        try:
            placement_for_upload(
                level,
                department=department,
                owner_id=admin,
                may_add=may_add(held, registry, h.now),
                reads_knowledge=reads_knowledge(held, h.now),
            )
        except (UploadNotOffered, VisibilityError):
            continue
        raise CheckFailedError("an upload was placed wider than its uploader may add")
    words = {kind: h.word() for kind in ("markdown", "pdf", "word")}
    files = (
        (
            "markdown",
            "Acceptance.md",
            MediaType.MARKDOWN,
            a_markdown_document("Check", words["markdown"]),
        ),
        ("pdf", "Acceptance.pdf", MediaType.PDF, a_pdf(words["pdf"])),
        ("word", "Acceptance.docx", MediaType.DOCX, a_word_document("Check", words["word"])),
    )
    for kind, filename, media_type, body in files:
        read = await _upload(h, admin, filename=filename, declared=media_type.value, body=body)
        if isinstance(read, ParseFailure):
            raise CheckFailedError("a well-formed document the door accepts could not be read")
        del kind
    nothing = await _found(h, reader_b, h.word())
    for word in words.values():
        found, kept = await _found(h, reader_a, word)
        placed = {(one.department, one.visibility, one.owner_id) for one in found.records}
        if placed != {(A, "department", admin)}:
            raise CheckFailedError(
                "a passage did not carry the department, level and owner it was stored with"
            )
        if not any(word in str(one.get("document", "")) for one in kept):
            raise CheckFailedError("a reader in the document's department was not answered from it")
        other, _ = await _found(h, reader_b, word)
        if (other.records, other.truncated, other.source) != (
            nothing[0].records,
            nothing[0].truncated,
            nothing[0].source,
        ):
            raise CheckFailedError("a reader in another department could tell the document exists")
    broken = await _upload(
        h, admin, filename="Damaged.pdf", declared=MediaType.PDF.value, body=CORRUPT_PDF
    )
    if not isinstance(broken, ParseFailure) or broken.cause is not ParseCause.CORRUPT:
        raise CheckFailedError("a damaged PDF was not refused as damaged")
    if CAUSE_TEXT[ParseCause.CORRUPT] not in broken.message():
        raise CheckFailedError("the refusal of a damaged PDF did not name the cause")
    for refused in (
        lambda: text_path_type(MediaType.PNG.value),
        lambda: assert_declared_length(media_type=MediaType.MARKDOWN, content_length=10**9),
    ):
        try:
            refused()
        except IngestRefused:
            continue
        raise CheckFailedError("the upload door admitted a type or a size outside its limits")
