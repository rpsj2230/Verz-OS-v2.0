"""The worker's half of reading a connected source: the key, the call, the pages, what each left.

`brain.ops.connector_sync` decides whether a connection may be read, what is kept from a row and
what an attempt costs; `brain.ops.connector_sync_store` holds the SQL. This is the four things
neither can hold, and `run_connector_sync_now` is what the worker's schedule starts as the
`connector_sync` control.

**The worker reads a source's key, and it is the only process that does, through a lease per
attempt.** The application writes a key when an administrator connects a source and reads only the
slot's metadata, because it runs no connector. The worker runs them, and since 2026-09-17 its own
token reads no key: each attempt mints a run token against the `connector-run` token role, reads the
key with it and revokes it when the attempt ends, and the attempt's row records how the lease ended.
`brain.ops.connector_lease` argues the shape. `WorkerConnectorKeys` refuses a reference outside
`connector_keys/` and one not made for the worker's role before the vault is asked. The
reference comes from the manifest the connection's own settings build
(`brain.ops.connectable.key_reference`), never from a column somebody could edit to point at a
provider key. See `THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES`.

**The key goes into one header of one request and nowhere else.** It is not logged, not put in an
exception, not kept on the reading, and not in a run's record: every detail a run leaves is one of
`brain.ops.connector_sync`'s constant sentences, chosen by the kind of thing that happened. A caller
that fails reports the failure's kind, never its message, because a message can quote a header.

**Every call is admitted by the source's verified ceiling before it is made.** `plan.limits` is
`brain.connectors.throttle.limits_for`, and each call is checked with `brain.ops.limits.check` and
recorded only once admitted, so the run takes its fair share of the source's minute and waits for
room rather than spending the client's allowance. The window counts this run's calls: the shared
window store (`brain.ops.limit_store`) has no caller anywhere yet, and the source's own figure,
Xero's `X-DayLimit-Remaining`, is what catches the calls other integrations made.

**The connection goes to the address the address rule checked**, through the same pinned connection
`brain.ops.webhook_delivery` sends through, for its reason: a name that answered outside to the
check and inside to the connection is the ordinary way past the rule.

**A page is written when it is read, and the read's place moves with it.** Each page's records are
upserted in a transaction of their own before the next page is asked for, so a run that fails on
page four keeps pages one to three, with the reading time each was read at, and the attempt's row
records that page four is where the next attempt starts (`brain.ops.connector_sync.
A_READ_CUT_SHORT_CARRIES_ON_WHERE_IT_STOPPED`). The first page a read asks is the one
`brain.ops.connector_sync.next_read` decides: where the last attempt stopped, the source's changes
since the last complete read, or everything.

**A page that changes what the index says advances the source's epoch in its own transaction**,
and a complete read of everything retires, in one more, the rows it did not see. The comparison is
with the live rows the page names, read in the same transaction just before they are written, so
a page that only confirms them moves no epoch. See
`brain.ops.connector_sync.A_CHANGED_READ_ADVANCES_ITS_SOURCE_S_EPOCH` and
`WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED`.

**An entity listed under another is walked once under each parent this read kept (M11.7.3).**
Cloudflare lists a DNS record only under its zone, so the zones are read first and the records then
read zone by zone, each page named by the zone's id and its own (`walks`,
`brain.connectors.declaration.ListedUnder`). Rejected: the parents read from the index the last run
left, which would list records under a zone the source has since removed and miss one it added.
**A read carried on over several attempts reads its parents from the index all the same, and that
is not the rejected design**: the rows it reads are the ones this read wrote, since it began
(`brain.ops.connector_sync_store.seen_since`), so a zone removed before the read is not among them
and one added is, exactly as if the read had kept them in memory.

**A pass cut short is carried on whatever shape its walk takes (M11.9.15).** The walk's place is the
arguments of the page it would ask next, which a Drive walk fills with the folders still to list, a
routed reading with its next route, and a walk under a parent with that parent's id; a walk ended
by `MAX_PAGES_PER_ENTITY` stops its entity there, and the next attempt asks that page first. A pass
that skipped something to reach its end, a routed server that did not answer or a folder past a
`brain.connectors.declaration.BoundedWalk`'s bound, is partial and retires nothing. A database's
views are read again from the start: see `brain.ops.connector_sync.A_VIEW_READ_IS_ONE_BOUNDED_READ`.

**What is written is the minimal index and nothing else.** Every record passes
`brain.ops.connector_sync.kept_fields` before its page is written, and the run hands nothing to the
knowledge corpus: until 2026-09-28 it opened the corpus and passed each row a reading called a
document to `brain.knowledge.chunk_store.ingest_document`, which is a bulk sync of bodies by the
owner's rule and was removed with the leg that fed it. See
`brain.ops.connector_sync.A_SYNC_KEEPS_NO_BODY`.

**A source that is views in a company's own database takes one typed branch of this loop
(M11.6.1).** Its reading is a `brain.connectors.declaration.ViewReading`, so `_read_views` reads
each view once, bounded, admitted by the same ceiling, written through the same `kept_fields` and
recorded by the same `after_attempt`. The lease hands over the user the slot keeps beside the
password, and the pair lives in a `DatabaseLogin` for the attempt and is dropped with the lease.
See `brain.connectors.declaration.A_DATABASE_IS_READ_BY_THE_SAME_LOOP`.

**A Google source's key file is exchanged for a token here, for the one attempt (M11.7.1).**
`KeyScheme.GOOGLE_SERVICE_ACCOUNT` is presented as a bearer token that `mint_token` obtains from
Google's own token endpoint with the key the lease holds, through `SourcePoster`, the same pinned
connection a call to the source goes through. The token lives in the attempt's frame and goes when
the attempt does; `authorization` refuses to build such a source's header from anything but the
token, so the key file itself is never sent. See `brain.connectors.google_token`, which argues the
exchange once for both Google sources.

**An MCP server's tools and custom code take one typed branch too (M11.1.2, M11.1.5).** Both
read one entity at a time by calls this module makes with the leased key, each admitted by the
ceiling (`_read_by_calls`): an MCP session's posts (`brain.ops.mcp_session`), or the calls a
custom connector's sandboxed code planned (`brain.ops.custom_code_run`), whose code never holds
the key (`brain.connectors.custom_code.THE_KEY_NEVER_ENTERS_THE_SANDBOX`).
**A source consented to by OAuth renews its access here, by the read that needs it (M11.8.6).**
`KeyScheme.OAUTH_REFRESH` is presented as a bearer token that `renewed_access` obtains from the
vendor's token endpoint with the application's client secret (the key the lease holds), the client
id (a setting of the connection) and the refresh token the person's consent bought, which is read
under a lease of its own from its own slot (`brain.ops.connectable.refresh_reference`) and given
back at once. A vendor that refuses the renewal has withdrawn the consent, and the read fails with
`brain.connectors.oauth.CONSENT_WITHDRAWN`, down at once; a 429 or a 5xx is the endpoint's ill
health and is retried on the backoff like any source's. A vendor that rotates its refresh tokens
answers with a new one, and it is written back through `RotatesRefreshTokens` by a token that can
write that slot and read nothing (`brain.ops.connector_lease.
A_ROTATED_GRANT_IS_WRITTEN_BACK_BY_A_ROLE_THAT_CANNOT_READ_IT`). One function, `presented`, for
the scheduled read, the test and the live read, and one, `presenting_detail`, for what each says
when it failed, so the three cannot come to disagree about either.

Rejected: reading through `brain.tools.fetch.Fetcher`, which the connectors' own `connector_fetch`
closures take. It carries no headers and no status, so a key cannot be sent through it and a 429
cannot come back through it as anything but an exception, which is the collapse
`xero.AN_UNREACHABLE_LEDGER_IS_NOT_AN_EMPTY_ONE` refuses.

Task ids: M42.6.5, M31.3.2.3, M31.3.2.4, M11.9.1, M11.6.2, M11.6.1, M11.7.3, M11.7.1
Task ids: M11.4.6, M11.4.8, M11.8.4, M11.8.11, M11.9.15, M11.1.2, M11.1.5, M11.8.6, M11.7.8
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import http.client
import json
import ssl
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.backfill import BackfillCursor
from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.custom_code import CustomCodeError, KeyInSandboxError
from brain.connectors.declaration import (
    BoundedWalk,
    CodeReading,
    ConsentedReading,
    DatabaseLogin,
    KeyScheme,
    ListedUnder,
    PageReply,
    Reading,
    RoutedReading,
    ScopedReading,
    ToolReading,
    ViewReading,
    listed_under,
)
from brain.connectors.google_token import (
    A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER,
    MAX_TOKEN_ANSWER_BYTES,
    AccessToken,
    TokenNotIssuedError,
    exchange,
    token_from,
)
from brain.connectors.mcp import McpToolNotAsReviewedError
from brain.connectors.oauth import (
    A_CONSENTED_SOURCE_IS_SENT_ONLY_ITS_ACCESS,
    CONSENT_WITHDRAWN,
    NOT_CONNECTED_FOR_YOU,
    YOUR_CONSENT_WITHDRAWN,
    ConsentNotHeldError,
    ConsentWithdrawnError,
    OAuthConsent,
    RotatedTokenNotKeptError,
    refresh_exchange,
    tokens_from,
)
from brain.connectors.projection import ProjectedRecord
from brain.connectors.rest import MAX_RESPONSE_BYTES, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.ops.connectable import (
    READING_ROLE,
    key_reference,
    person_refresh_reference,
    refresh_reference,
)
from brain.ops.connector_lease import (
    PERSON_LEASE_TTL,
    PERSON_POLICY,
    PERSON_TOKEN_ROLE,
    ROTATE_LEASE_TTL,
    ROTATE_POLICY,
    ROTATE_TOKEN_ROLE,
    RUN_LEASE_TTL,
    RUN_POLICY,
    RUN_TOKEN_ROLE,
    LeaseOutcome,
    judge_minted,
)
from brain.ops.connector_sync import (
    ADDRESS_REFUSED,
    CODE_DID_NOT_COMPLETE,
    KEY_KEPT_OUT,
    MAX_PAGES_PER_ENTITY,
    MAX_SECONDS_WAITING_IN_A_RUN,
    NO_KEY,
    NO_KEY_FILE_EXCHANGE,
    NO_SANDBOX,
    NO_VAULT,
    NO_WAY_TO_POST,
    NOT_CONSENTED,
    OWN_SHARE_SPENT,
    READ_BUT_CUT_SHORT,
    READ_BUT_PART_LEFT_OUT,
    READ_TO_THE_END,
    READINGS,
    ROTATED_REFRESH_NOT_KEPT,
    SHAPE_DISAGREED,
    SOURCE_ALLOWANCE_REFUSED,
    TOOL_NOT_AS_REVIEWED,
    TOOL_SAID_IT_FAILED,
    VAULT_REFUSED,
    VAULT_UNREACHABLE,
    Attempt,
    ReadPass,
    ReadState,
    SourceReading,
    StoredValue,
    SyncOutcome,
    SyncPlan,
    SyncState,
    after_attempt,
    after_the_read,
    changed,
    database_failure_detail,
    failure_detail,
    kept_fields,
    next_read,
    page_cursor,
    page_to_ask,
    plan_for,
)
from brain.ops.connector_sync_store import (
    LiveConnection,
    advance_epoch,
    attempt_row,
    live_fields,
    read_live,
    read_states,
    record_upsert,
    retire_unseen,
    seen_since,
)
from brain.ops.credentials import KEY_FIELD, OAUTH_REFRESH_DIRECTORY, USER_FIELD
from brain.ops.custom_code_run import CodeRunFailedError, installed_runner, read_once
from brain.ops.custom_connector_store import refresh
from brain.ops.halt_store import Work, read_state, refusal_in
from brain.ops.lark_base_index import HttpsTokenIssuer, index_if_due
from brain.ops.leases import SealedSecret
from brain.ops.limits import Limit, LimiterState, check
from brain.ops.mcp_session import (
    CallNotAdmittedError,
    CallNotAnsweredError,
    open_session,
    read_entity,
)
from brain.ops.openbao import (
    CONNECTOR_KEY_PREFIX,
    OpenBaoVault,
    RoleToken,
    VaultRefusedError,
    VaultUnreachableError,
)
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.ops.webhook_delivery import HTTPS_PORT, SystemResolver, _PinnedHTTPSConnection
from brain.tools.fetch import Resolver, UnsafeAddressError, assert_fetchable
from brain.tools.run_skill import ScriptRunner

# ------------------------------------------------------------------ written-down reasons

#: Why the worker holds read on the connector keys and the application does not.
THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES: Final = (
    "A source's key is used for one thing, reading the source, and only the worker reads a source. "
    "So the worker's policy reads connector_keys/data/+ and the application's does not: the "
    "application writes a key when an administrator connects a source and reads the slot's "
    "metadata to say it is held, and a process that talks to a model has no reason to hold every "
    "source's key. The reader refuses a path outside connector_keys/ and a reference not made for "
    "the worker, so a declaration edited to point at a provider key is refused here before the "
    "vault is asked."
)

#: How long one call may take, connect to last byte. A page is a list of a hundred records and a
#: source that takes longer is reported as not answering in time, and tried again on its backoff.
CALL_TIMEOUT_SECONDS: Final = 30.0

#: What a source sees as the client. Names the product and nothing about the install.
USER_AGENT: Final = "company-brain-connectors/1"


class ConnectorKeyAbsentError(SecretsUnavailableError):
    """The vault answered and holds no key at this source's slot."""


def authorization(scheme: KeyScheme, key: str | AccessToken) -> str:
    """The one header value a source's key is sent in, in the shape its reading names.

    Here and not on the reading, for `brain.connectors.declaration.
    A_READING_NAMES_HOW_ITS_KEY_IS_SENT_AND_NEVER_HOLDS_IT`: this module already holds the key for
    one request, and a reading never does. A `match` over a closed enumeration, so a scheme added
    without a shape here fails mypy's exhaustiveness check rather than falling back to a bearer.

    A Google source's header is built from an `AccessToken` and from nothing else, so a caller
    that skipped `presented` sends nothing rather than the key file. See
    `brain.connectors.google_token.A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER`.
    """
    match scheme:
        case KeyScheme.BEARER:
            return f"Bearer {_plain(key)}"
        case KeyScheme.BASIC_KEY_AS_USER:
            pair = base64.b64encode(f"{_plain(key)}:X".encode()).decode("ascii")
            return f"Basic {pair}"
        case KeyScheme.NONE:
            return ""
        case KeyScheme.GOOGLE_SERVICE_ACCOUNT:
            if not isinstance(key, AccessToken):
                raise ConnectorContractError(A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER)
            return f"Bearer {key.value}"
        case KeyScheme.OAUTH_REFRESH:
            if not isinstance(key, AccessToken):
                raise ConnectorContractError(A_CONSENTED_SOURCE_IS_SENT_ONLY_ITS_ACCESS)
            return f"Bearer {key.value}"


def walks(
    reading: SourceReading,
    entity: str,
    under: ListedUnder | None,
    parents: Sequence[str],
    *,
    read: ReadPass,
    walk: BackfillCursor,
    settings: Mapping[str, str],
) -> tuple[tuple[str | None, Mapping[str, str]], ...]:
    """Where this attempt's walks of one entity start: where the read stopped, then the rest.

    An entity listed on its own is walked once, from the page `page_to_ask` names: where an
    earlier attempt of this read stopped, else its first page, its changes' first page, or a
    routed reading's first route. One listed under another
    (`brain.connectors.declaration.ListedUnder`) is walked once per parent this read kept, in the
    order of the parents' ids, the parent's id laid into the path, and a parent that kept nothing
    lists nothing under it. A walk carried on starts at the page it stopped at, under the parent
    that page names, and goes on to every parent whose id comes after it. Each walk is bounded by
    `MAX_PAGES_PER_ENTITY` on its own, so a zone with few records is never cut short by one with
    many. See `brain.ops.connector_sync.A_WALK_CUT_SHORT_IS_CARRIED_ON_IN_EVERY_SHAPE`.
    """
    asked = page_to_ask(reading, read, walk, settings=settings)
    if asked is None:
        return ()
    if under is None:
        return ((None, asked),)
    ordered = sorted(set(parents))
    if not walk.cursor:
        return tuple(
            (parent_id, MappingProxyType({**asked, under.parameter: parent_id}))
            for parent_id in ordered
        )
    stopped_under = asked.get(under.parameter, "")
    first = page_to_ask(reading, read, replace(walk, cursor=""), settings=settings)
    later: tuple[tuple[str | None, Mapping[str, str]], ...] = ()
    if first is not None:
        later = tuple(
            (parent_id, MappingProxyType({**first, under.parameter: parent_id}))
            for parent_id in ordered
            if parent_id > stopped_under
        )
    return ((stopped_under, asked), *later)


def _plain(key: str | AccessToken) -> str:
    return key.value if isinstance(key, AccessToken) else key


def call_headers(
    reading: SourceReading, settings: Mapping[str, str], key: str | AccessToken
) -> dict[str, str]:
    """Every header one call to a source carries: the connection's own, JSON, and the key.

    One function for a scheduled read and a test (`brain.ops.connector_probe_run`), so the two
    calls a source sees from this install cannot come to differ in what they send. `key` is what
    `presented` gave for this reading: the key itself, or the token a key file was exchanged for.
    """
    sent = authorization(reading.key_scheme(), key)
    return {
        **reading.call_headers(settings),
        "Accept": "application/json",
        # A source that takes no key is sent no `Authorization` at all, not an empty one.
        **({} if reading.key_scheme() is KeyScheme.NONE else {"Authorization": sent}),
    }


@dataclass
class Unleased:
    """`KeyLease` for a source that takes no key: nothing is minted, read or revoked (M11.7.4)."""

    def key(self) -> str:
        return ""

    def user(self) -> str:
        # A source that takes no key keeps no user either; only a database's slot holds one.
        raise ConnectorKeyAbsentError(NO_KEY)

    def close(self, now: datetime) -> LeaseOutcome:
        del now
        return LeaseOutcome.NONE


def borrowed(keys: ConnectorKeys, reading: Reading, ref: SecretRef, *, now: datetime) -> KeyLease:
    """The lease one read holds: none for a source that takes no key, and the vault's otherwise.

    A source whose record is published to anybody who asks has no slot to read, so asking the
    vault for one would fail every read with a missing key and mint a run token for nothing. A
    database's views are always read as a user with a password (M11.6.1), so a `ViewReading`, which
    declares no key scheme, is always leased.
    """
    if not isinstance(reading, ViewReading) and reading.key_scheme() is KeyScheme.NONE:
        return Unleased()
    return keys.lease(ref, now=now)


def page_operation(
    reading: SourceReading,
    entity: str,
    page: Mapping[str, str],
    *,
    settings: Mapping[str, str],
    resolver: Resolver,
) -> RestOperation:
    """The operation one page is read by: the reading's own, or a routed reading's for the page.

    See `brain.connectors.declaration.A_PAGE_MAY_BE_READ_FROM_ITS_OWN_SERVER`.
    """
    if isinstance(reading, RoutedReading):
        return reading.operation_for(entity, page, settings=settings, resolver=resolver)
    return reading.operation(entity, settings=settings, resolver=resolver)


def first_arguments(
    reading: SourceReading, entity: str, *, settings: Mapping[str, str]
) -> Mapping[str, str] | None:
    """The first page's arguments: the connection's own first route for a routed reading."""
    if isinstance(reading, RoutedReading):
        return reading.first_route(entity, settings=settings)
    return reading.first_page(entity)


# ------------------------------------------------------------------ the token a key file buys


class SourcePoster(Protocol):
    """One POST to an address the rule checked, with these headers and this body, never following.

    Beside `SourceCaller` rather than inside it, because only a source whose key is exchanged for a
    token, or whose figures are asked for with a body, ever posts, and every other source's caller
    owes nothing here.
    """

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        """The answer, or a timeout or a failed connection. Never raises for the network."""
        ...


def mint_token(
    key_file: str,
    scopes: tuple[str, ...],
    *,
    poster: SourcePoster,
    resolver: Resolver,
    now: datetime,
) -> AccessToken:
    """A token for one read, from Google's token endpoint, with the key file the lease holds.

    The address is Google's own constant, checked by the address rule like any source's, and the
    answer is read by `brain.connectors.google_token.token_from`, which raises
    `TokenNotIssuedError` with the kind of failure and nothing from the reply.
    """
    asked = exchange(key_file, scopes, now=int(now.timestamp()))
    checked = assert_fetchable(asked.url, resolver)
    answer = poster.post(
        checked.url,
        address=checked.address,
        headers=dict(asked.headers),
        body=asked.body,
        max_bytes=MAX_TOKEN_ANSWER_BYTES,
    )
    return token_from(
        status=answer.status,
        body=answer.body,
        timed_out=answer.timed_out,
        connection_failed=answer.connection_failed,
    )


@dataclass(frozen=True)
class Consenting:
    """What renewing a consented source's access needs besides its client secret (M11.8.6).

    The source's name, which names the slot its refresh token is kept in; the connection's settings,
    one of which is the client id; and the keys the attempt leases from, which lease the refresh
    token and, where they can, write a rotated one back. Built by whoever holds the attempt's lease.
    `principal_id` names the person whose own consent is renewed, for a source each person consents
    to for themselves, and is empty for a source's own consent; `personal_access` is the one place
    that sets it, with keys that admit that person's slot alone.
    """

    connector: str
    settings: Mapping[str, str]
    keys: ConnectorKeys
    principal_id: str = ""

    def refresh(self) -> SecretRef:
        """Where the refresh token this renewal posts is kept: the source's, or the person's."""
        if self.principal_id:
            return person_refresh_reference(self.connector, self.principal_id)
        return refresh_reference(self.connector)


@runtime_checkable
class RotatesRefreshTokens(Protocol):
    """Keys that can write a refresh token a vendor rotated back to its slot (M11.8.6).

    Optional, and asked with `isinstance`, so a `ConnectorKeys` that only leases owes nothing; a
    rotation it cannot keep fails the read with `ROTATED_REFRESH_NOT_KEPT`.
    """

    def rotate(self, ref: SecretRef, token: str, *, now: datetime) -> None:
        """Write `token` over the refresh token at `ref`, or raise `SecretsUnavailableError`."""
        ...


def renewed_access(
    consent: OAuthConsent,
    client_secret: str,
    *,
    consenting: Consenting,
    poster: SourcePoster,
    resolver: Resolver,
    now: datetime,
) -> AccessToken:
    """An access token for one read, renewed from the kept refresh token, rotation kept.

    The refresh token is leased from its own slot and the lease given back before anything is
    posted, so no run token outlives the read of one value. Raises `ConsentNotHeldError` when there
    is no refresh token, `ConsentWithdrawnError` when the vendor refused the renewal,
    `TokenNotIssuedError` for the endpoint's ill health, `RotatedTokenNotKeptError` when a rotated
    token could not be written back, `SecretsUnavailableError` when the vault would not lease, and
    `UnsafeAddressError` when the token endpoint resolved inside this network. See
    `brain.connectors.oauth.ACCESS_IS_RENEWED_BY_THE_READ_THAT_NEEDS_IT`.
    """
    ref = consenting.refresh()
    lease = consenting.keys.lease(ref, now=now)
    try:
        refresh = lease.key()
    except ConnectorKeyAbsentError:
        raise ConsentNotHeldError from None
    finally:
        lease.close(now)
    try:
        asked = refresh_exchange(
            consent,
            client_id=consenting.settings.get(consent.client_id_setting, ""),
            client_secret=client_secret,
            refresh_token=refresh,
        )
    except ConnectorContractError:
        # A refresh token or a secret this cannot send is one no vendor would renew with.
        raise ConsentWithdrawnError from None
    checked = assert_fetchable(asked.url, resolver)
    answer = poster.post(
        checked.url,
        address=checked.address,
        headers=dict(asked.headers),
        body=asked.body,
        max_bytes=MAX_TOKEN_ANSWER_BYTES,
    )
    try:
        tokens = tokens_from(
            status=answer.status,
            body=answer.body,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed,
        )
    except TokenNotIssuedError as refused:
        if refused.call is CallOutcome.REJECTED:
            raise ConsentWithdrawnError from None
        raise
    if tokens.refresh is not None and tokens.refresh != refresh:
        keys = consenting.keys
        if not isinstance(keys, RotatesRefreshTokens):
            raise RotatedTokenNotKeptError
        try:
            keys.rotate(ref, tokens.refresh, now=now)
        except SecretsUnavailableError:
            raise RotatedTokenNotKeptError from None
    return tokens.access


def presented(
    reading: SourceReading,
    key: str,
    *,
    poster: SourcePoster | None,
    resolver: Resolver,
    now: datetime,
    consenting: Consenting | None = None,
) -> str | AccessToken:
    """What this reading's calls present: the key as it is, or the token its key file or its
    consent buys.

    Raises `TokenNotIssuedError` when a token was needed and not issued, and when this process was
    given no way to post for one; `UnsafeAddressError` when the token endpoint resolved inside this
    network; `SecretsUnavailableError` when a consented source's refresh token could not be leased.
    A reading naming the Google scheme and no scope, or the OAuth scheme and no consent, is refused
    before anything is sent. See `brain.connectors.declaration.
    A_READING_NAMES_THE_SCOPE_ITS_KEY_FILE_IS_EXCHANGED_FOR` and `renewed_access`.
    """
    match reading.key_scheme():
        case KeyScheme.BEARER | KeyScheme.BASIC_KEY_AS_USER | KeyScheme.NONE:
            return key
        case KeyScheme.GOOGLE_SERVICE_ACCOUNT:
            if not isinstance(reading, ScopedReading):
                raise TokenNotIssuedError(CallOutcome.REJECTED)
            if poster is None:
                raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
            return mint_token(
                key, reading.token_scopes(), poster=poster, resolver=resolver, now=now
            )
        case KeyScheme.OAUTH_REFRESH:
            if not isinstance(reading, ConsentedReading):
                raise TokenNotIssuedError(CallOutcome.REJECTED)
            if poster is None or consenting is None:
                raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
            return renewed_access(
                reading.consent(),
                key,
                consenting=consenting,
                poster=poster,
                resolver=resolver,
                now=now,
            )


# ------------------------------------------------------------------ a person's own consent
#: The refresh token directory a person's own slots sit under, one segment below each source's.
_REFRESH_DIRECTORY: Final = f"{CONNECTOR_KEY_PREFIX}{OAUTH_REFRESH_DIRECTORY}/"


def is_person_slot(path: str) -> bool:
    """Whether a path is a person's own refresh token slot: two segments under the directory."""
    if not path.startswith(_REFRESH_DIRECTORY):
        return False
    parts = path.removeprefix(_REFRESH_DIRECTORY).split("/")
    return len(parts) == 2 and all(parts)


class PersonalKeys:
    """`ConnectorKeys` for one person's read of one source: its client secret and their own slot.

    The only keys a read made for a person's question is handed, so the one reference to a person's
    refresh token any such read can lease is the one built from that person. Every other path, a
    second person's slot or the source's own refresh token among them, is refused before the vault
    is asked, as a lease that holds its refusal; a rotation is written back to their slot alone. See
    `brain.connectors.oauth.A_PERSONS_CONSENT_READS_ONLY_FOR_THAT_PERSON`. The vault's half is that
    only the application may mint the role a person's slot is read under:
    `brain.ops.connector_lease.NOTHING_RUNNING_WITH_NOBODY_PRESENT_READS_A_PERSONS_CONSENT`.
    """

    def __init__(self, keys: ConnectorKeys, *, connector: str, principal_id: str) -> None:
        self._keys = keys
        self._admitted = frozenset(
            {
                key_reference(connector).path,
                person_refresh_reference(connector, principal_id).path,
            }
        )

    def __repr__(self) -> str:
        return "PersonalKeys()"

    __str__ = __repr__

    def lease(self, ref: SecretRef, *, now: datetime) -> KeyLease:
        if ref.path not in self._admitted:
            return _Held(failure=SecretsUnavailableError(NOT_THIS_PERSONS_SLOT))
        return self._keys.lease(ref, now=now)

    def rotate(self, ref: SecretRef, token: str, *, now: datetime) -> None:
        """Write a rotated refresh token back to this person's own slot, and to no other."""
        if ref.path not in self._admitted or not is_person_slot(ref.path):
            raise SecretsUnavailableError(NOT_THIS_PERSONS_SLOT)
        if not isinstance(self._keys, RotatesRefreshTokens):
            raise SecretsUnavailableError(NOT_THIS_PERSONS_SLOT)
        self._keys.rotate(ref, token, now=now)


#: What a lease of any slot but the asker's own says. Names neither the slot nor whose it is.
NOT_THIS_PERSONS_SLOT: Final = (
    "a read made for one person's question leases that person's own refresh token and the "
    "source's client secret, and nothing else"
)


def personal_access(
    consent: OAuthConsent,
    *,
    connector: str,
    principal_id: str,
    settings: Mapping[str, str],
    keys: ConnectorKeys,
    poster: SourcePoster,
    resolver: Resolver,
    now: datetime,
) -> AccessToken:
    """Access for one person's own read, renewed from the refresh token their consent bought.

    The source's client secret and the person's refresh token are each leased through
    `PersonalKeys` built from `principal_id`, and given back before anything is posted; a rotated
    token is written back to their slot. Raises what `renewed_access` raises, and
    `SecretsUnavailableError` when the client secret could not be leased. Nothing here touches the
    source's own health: a withdrawn personal consent is that person's reads down, said in
    `brain.connectors.oauth.YOUR_CONSENT_WITHDRAWN` by `personal_words`, and nobody else's.
    """
    own = PersonalKeys(keys, connector=connector, principal_id=principal_id)
    lease = own.lease(key_reference(connector), now=now)
    try:
        secret = lease.key()
    finally:
        lease.close(now)
    return renewed_access(
        consent,
        secret,
        consenting=Consenting(connector, settings, own, principal_id=principal_id),
        poster=poster,
        resolver=resolver,
        now=now,
    )


def personal_words(refused: Exception) -> str:
    """What a person is told when their own read could not be made, by kind and never by value.

    Their consent refused at the vendor, and no consent of theirs, are each said to them in words;
    anything else is the vendor or the vault not answering, said as a refused key is.
    """
    if isinstance(refused, ConsentWithdrawnError):
        return YOUR_CONSENT_WITHDRAWN
    if isinstance(refused, ConsentNotHeldError):
        return NOT_CONNECTED_FOR_YOU
    if isinstance(refused, TokenNotIssuedError):
        return failure_detail(refused.call, timed_out=refused.timed_out)
    if isinstance(refused, SecretsUnavailableError):
        return key_detail(refused)
    return ADDRESS_REFUSED


def presenting_detail(refused: TokenNotIssuedError, *, poster: SourcePoster | None) -> str:
    """The sentence a read whose credential could not be presented leaves, by kind only.

    One function for the scheduled read and the test, so a refused consent says
    `CONSENT_WITHDRAWN` on both. A process given no way to post says so before anything else,
    because no answer was asked for.
    """
    if poster is None:
        return NO_KEY_FILE_EXCHANGE
    if isinstance(refused, ConsentWithdrawnError):
        return CONSENT_WITHDRAWN
    if isinstance(refused, ConsentNotHeldError):
        return NOT_CONSENTED
    if isinstance(refused, RotatedTokenNotKeptError):
        return ROTATED_REFRESH_NOT_KEPT
    return failure_detail(refused.call, timed_out=refused.timed_out)


# ------------------------------------------------------------------------ the key


class KeyLease(Protocol):
    """One attempt's hold on a source's key: the key, or why there is none, and its ending."""

    def key(self) -> str:
        """The key, or the `SecretsUnavailableError` saying why this attempt has none."""
        ...

    def user(self) -> str:
        """The user name a database user's slot keeps beside its password, which is the key.

        Raises the `SecretsUnavailableError` `key` would, or `ConnectorKeyAbsentError` for a slot
        that keeps no user, which is every source whose credential is one key (M11.6.1).
        """
        ...

    def close(self, now: datetime) -> LeaseOutcome:
        """Give the lease back and say how that went. A second call answers the first's outcome."""
        ...


class ConnectorKeys(Protocol):
    """Whatever hands the worker one source's key for one attempt, leased for that attempt."""

    def lease(self, ref: SecretRef, *, now: datetime) -> KeyLease:
        """A lease on the key at this reference. Never raises: a failure is held for `key`."""
        ...


class RunKeyReader(Protocol):
    """The vault as a run token presents to it: read one slot, and revoke the token."""

    def read_static_kv(self, path: str) -> dict[str, Any]:
        """The slot's fields, or a `SecretsUnavailableError`."""
        ...

    def revoke_self(self) -> None:
        """Revoke the token presented, or raise a `SecretsUnavailableError`."""
        ...


class RunTokenVault(Protocol):
    """The vault as the worker's own token presents to it: mint a run token, and hold one."""

    def mint_role_token(self, role: str, *, ttl: timedelta, meta: Mapping[str, str]) -> RoleToken:
        """A child token against the named token role, or a `SecretsUnavailableError`."""
        ...

    def holding(self, token: RoleToken) -> RunKeyReader:
        """A client presenting the child token. Contacts nothing."""
        ...


class _Held:
    """`KeyLease` over a run token, or over none. Private, and its representation names nothing."""

    def __init__(
        self,
        *,
        failure: SecretsUnavailableError | None,
        reader: RunKeyReader | None = None,
        expires_at: datetime | None = None,
        key: SealedSecret | None = None,
        user: str = "",
    ) -> None:
        self._failure = failure
        self._reader = reader
        self._expires_at = expires_at
        self._key = key
        self._user = user
        self._ended: LeaseOutcome | None = None

    def __repr__(self) -> str:
        return f"KeyLease(held={self._reader is not None}, ended={self._ended})"

    __str__ = __repr__

    def key(self) -> str:
        if self._failure is not None:
            raise self._failure
        if self._key is None:
            # Asked after `close`, which forgets the key with the token.
            raise ConnectorKeyAbsentError(NO_KEY)
        return self._key.reveal()

    def user(self) -> str:
        if self._failure is not None:
            raise self._failure
        if self._key is None or not self._user:
            # A slot holding one key keeps no user, and `close` forgets the user with the key.
            raise ConnectorKeyAbsentError(NO_KEY)
        return self._user

    def close(self, now: datetime) -> LeaseOutcome:
        if self._ended is not None:
            return self._ended
        reader, self._reader, self._key, self._user = self._reader, None, None, ""
        if reader is None:
            self._ended = LeaseOutcome.NONE
            return self._ended
        try:
            reader.revoke_self()
        except SecretsUnavailableError:
            # Refused or silent, the token was not confirmed taken back. Past its TTL there was
            # nothing to take back; inside it, it lives until the TTL, and the row says so.
            lapsed = self._expires_at is not None and now >= self._expires_at
            self._ended = LeaseOutcome.EXPIRED if lapsed else LeaseOutcome.NOT_REVOKED
            return self._ended
        self._ended = LeaseOutcome.REVOKED
        return self._ended


class WorkerConnectorKeys:
    """`ConnectorKeys` over the worker's vault, or over no vault at all.

    See `THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES` and
    `brain.ops.connector_lease`. The representation names whether a vault is configured and nothing
    else, so a traceback holding this object prints no address, token or key.
    """

    def __init__(self, vault: RunTokenVault | None) -> None:
        self._vault = vault

    def __repr__(self) -> str:
        return f"WorkerConnectorKeys(configured={self._vault is not None})"

    __str__ = __repr__

    def lease(self, ref: SecretRef, *, now: datetime) -> KeyLease:
        if not ref.path.startswith(CONNECTOR_KEY_PREFIX) or ref.path == CONNECTOR_KEY_PREFIX:
            msg = (
                f"a source's key is read from {CONNECTOR_KEY_PREFIX} and nowhere else, and this "
                f"reference names the {ref.path.split('/', 1)[0]} engine. "
                f"{THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES}"
            )
            return _Held(failure=SecretsUnavailableError(msg))
        if ref.role is not READING_ROLE:
            msg = (
                f"this reference was made for the {ref.role.value} role and the worker reads "
                f"only references made for {READING_ROLE.value}"
            )
            return _Held(failure=SecretsUnavailableError(msg))
        if self._vault is None:
            return _Held(failure=SecretsUnavailableError(NO_VAULT))
        # A person's own refresh token is read under the role only the application may mint, and
        # the person is never named in the token's metadata. See `brain.ops.connector_lease.
        # NOTHING_RUNNING_WITH_NOBODY_PRESENT_READS_A_PERSONS_CONSENT`.
        personal = is_person_slot(ref.path)
        role, policy, ttl = (
            (PERSON_TOKEN_ROLE, PERSON_POLICY, PERSON_LEASE_TTL)
            if personal
            else (RUN_TOKEN_ROLE, RUN_POLICY, RUN_LEASE_TTL)
        )
        slot_name = ref.path.removeprefix(CONNECTOR_KEY_PREFIX)
        try:
            minted = self._vault.mint_role_token(
                role,
                ttl=ttl,
                meta={"connector": slot_name.rsplit("/", 1)[0] if personal else slot_name},
            )
        except SecretsUnavailableError as unavailable:
            return _Held(failure=unavailable)
        reader = self._vault.holding(minted)
        expires_at = now + timedelta(seconds=minted.lease_seconds)
        verdict = judge_minted(
            renewable=minted.renewable,
            policies=minted.policies,
            lease_seconds=minted.lease_seconds,
            asked=ttl,
            policy=policy,
        )
        if verdict:
            # Held so `close` revokes it at the attempt's end like any other, and never read with.
            refused = VaultRefusedError(verdict, status=http.client.FORBIDDEN)
            return _Held(failure=refused, reader=reader, expires_at=expires_at)
        try:
            fields = reader.read_static_kv(ref.path)
        except VaultRefusedError as refused_read:
            absent = refused_read.status == http.client.NOT_FOUND
            failure: SecretsUnavailableError = (
                ConnectorKeyAbsentError(NO_KEY) if absent else refused_read
            )
            return _Held(failure=failure, reader=reader, expires_at=expires_at)
        except SecretsUnavailableError as unavailable:
            return _Held(failure=unavailable, reader=reader, expires_at=expires_at)
        value = fields.get(KEY_FIELD)
        if not isinstance(value, str) or not value.strip():
            absent_key = ConnectorKeyAbsentError(NO_KEY)
            return _Held(failure=absent_key, reader=reader, expires_at=expires_at)
        # A database user's slot keeps the user beside the password (M11.6.1); every other slot
        # keeps none, and `user` then says so rather than handing over an empty name.
        named = fields.get(USER_FIELD)
        return _Held(
            failure=None,
            reader=reader,
            expires_at=expires_at,
            key=SealedSecret(value),
            user=named.strip() if isinstance(named, str) else "",
        )

    def rotate(self, ref: SecretRef, token: str, *, now: datetime) -> None:
        """Write a rotated refresh token back under a token minted for that write alone (M11.8.6).

        Refuses a reference outside the refresh token directory before the vault is asked, mints a
        child against `ROTATE_TOKEN_ROLE`, refuses one the vault widened, patches the one field and
        revokes the token whatever the patch came to. See
        `brain.ops.connector_lease.A_ROTATED_GRANT_IS_WRITTEN_BACK_BY_A_ROLE_THAT_CANNOT_READ_IT`.
        """
        del now  # the rotation token's end is its TTL or its revocation, never this instant
        directory = f"{CONNECTOR_KEY_PREFIX}{OAUTH_REFRESH_DIRECTORY}/"
        if not ref.path.startswith(directory) or ref.path == directory:
            msg = f"a rotated refresh token is written under {directory} and nowhere else"
            raise SecretsUnavailableError(msg)
        if self._vault is None:
            raise SecretsUnavailableError(NO_VAULT)
        minted = self._vault.mint_role_token(
            ROTATE_TOKEN_ROLE,
            ttl=ROTATE_LEASE_TTL,
            meta={"connector": ref.path.removeprefix(directory).split("/", 1)[0]},
        )
        writer = self._vault.holding(minted)
        try:
            verdict = judge_minted(
                renewable=minted.renewable,
                policies=minted.policies,
                lease_seconds=minted.lease_seconds,
                asked=ROTATE_LEASE_TTL,
                policy=ROTATE_POLICY,
            )
            if verdict:
                raise VaultRefusedError(verdict, status=http.client.FORBIDDEN)
            if not isinstance(writer, PatchesSlots):
                msg = "this vault client cannot patch a slot, so a rotated token cannot be kept"
                raise SecretsUnavailableError(msg)
            writer.patch_static_kv(ref.path, {KEY_FIELD: token})
        finally:
            # Not confirmed taken back, it lives until its TTL of five minutes and no longer.
            with contextlib.suppress(SecretsUnavailableError):
                writer.revoke_self()


@runtime_checkable
class PatchesSlots(Protocol):
    """A vault client presenting a rotation token: patch one slot, and revoke the token."""

    def patch_static_kv(self, path: str, fields: Mapping[str, str]) -> None:
        """Merge the fields into the slot, or raise a `SecretsUnavailableError`."""
        ...

    def revoke_self(self) -> None:
        """Revoke the token presented, or raise a `SecretsUnavailableError`."""
        ...


def worker_connector_keys(address: str, token: str) -> WorkerConnectorKeys:
    """The worker's reader, from the two settings the worker's environment carries.

    Both must be set, and an address that is not a URL is no vault, for
    `brain.ops.webhook_delivery.worker_signing_keys`' reasons.
    """
    if not address or not token:
        return WorkerConnectorKeys(None)
    try:
        return WorkerConnectorKeys(OpenBaoVault(address, token, role=VaultRole.WORKER))
    except ValueError:
        return WorkerConnectorKeys(None)


def key_detail(failure: SecretsUnavailableError) -> str:
    """The sentence a key that could not be read leaves, by the kind of failure only."""
    if isinstance(failure, ConnectorKeyAbsentError):
        return NO_KEY
    if isinstance(failure, VaultRefusedError):
        return VAULT_REFUSED
    if isinstance(failure, VaultUnreachableError):
        return VAULT_UNREACHABLE
    return NO_VAULT


# ----------------------------------------------------------------------- the call


@dataclass(frozen=True)
class SourceAnswer:
    """What one call came back with: a status, headers and a body, or that it came back not at all.

    No field for the request, so an answer kept for a moment longer than it should be still holds
    no header that was sent.
    """

    status: int | None = None
    headers: Mapping[str, str] | None = None
    body: bytes = b""
    timed_out: bool = False
    connection_failed: bool = False


class SourceCaller(Protocol):
    """One GET to a source, to the address the rule checked, with these headers, never following."""

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        """The answer, or a timeout or a failed connection. Never raises for the network."""
        ...


class HttpsSourceCaller:
    """`SourceCaller` over `http.client`, pinned to the checked address, reading a bounded body.

    A redirect is an answer with a 3xx status and nothing is followed, for
    `brain.ops.outbox_store.A_REDIRECT_IS_NOT_A_DELIVERY`'s reason turned round: a source that
    moved is a source whose new address has not passed the rule.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = CALL_TIMEOUT_SECONDS,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._context = context if context is not None else ssl.create_default_context()

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        return self._send("GET", url, address=address, headers=headers, max_bytes=max_bytes)

    def send(
        self,
        method: str,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        """One approved change, with its body, to the checked address (M11.7.3). See
        `brain.ops.connector_write_run`, the only caller, which sends a change a person approved."""
        return self._send(
            method, url, address=address, headers=headers, max_bytes=max_bytes, body=body
        )

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        return self._send(
            "POST", url, address=address, headers=headers, max_bytes=max_bytes, body=body
        )

    def _send(
        self,
        method: str,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        max_bytes: int,
        body: bytes | None = None,
    ) -> SourceAnswer:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "https" or not host:
            return SourceAnswer(connection_failed=True)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection = _PinnedHTTPSConnection(
            host,
            parts.port or HTTPS_PORT,
            address=address,
            timeout=self._timeout,
            context=self._context,
        )
        try:
            connection.request(
                method, path, body=body, headers={**headers, "User-Agent": USER_AGENT}
            )
            answer = connection.getresponse()
            read = answer.read(max_bytes + 1)
            if len(read) > max_bytes:
                # A body past the bound is not parsed as a truncated one, which would read as a
                # shorter list; it is a source that did not answer in a shape this reads.
                return SourceAnswer(status=answer.status, headers={}, body=b"")
            return SourceAnswer(
                status=answer.status,
                headers={key.lower(): value for key, value in answer.getheaders()},
                body=read,
            )
        except TimeoutError:
            return SourceAnswer(timed_out=True)
        except (OSError, http.client.HTTPException):
            return SourceAnswer(connection_failed=True)
        finally:
            connection.close()


# ------------------------------------------------------------------------- one run


@dataclass(frozen=True)
class SyncRun:
    """What one run did, as counts. No source is named: a control run's detail has other readers."""

    read: int
    waiting: int
    failed: int
    not_due: int
    cannot_be_read: int
    #: What the switched-on Lark Base's index run did, or empty with no Base switched on. See
    #: `brain.ops.lark_base_index.IndexRun.summary`, which names no Base and no table.
    base: str = ""
    #: Sources a halt stopped, which are not read and keep their place. See `brain.ops.halt_store`.
    held: int = 0

    def summary(self) -> str:
        after = f"; {self.base}" if self.base else ""
        if not (
            self.read
            or self.waiting
            or self.failed
            or self.not_due
            or self.cannot_be_read
            or self.held
        ):
            return f"no source is connected{after}"
        stopped = f", {self.held} stopped by a halt" if self.held else ""
        return (
            f"{self.read} read, {self.waiting} waiting for a source's allowance, "
            f"{self.failed} failed, {self.not_due} not yet due, "
            f"{self.cannot_be_read} that cannot be read{stopped}{after}"
        )


@dataclass
class _Reading:
    """One attempt in progress. Private, and never handed to anything that could keep it."""

    plan: SyncPlan
    started_at: datetime
    #: The read this attempt makes or carries on, moved on page by page.
    read: ReadPass
    #: Where reading stood before this attempt, from the newest attempt that recorded it.
    before: ReadState | None = None
    records: int = 0
    cut_short: bool = False
    #: Whether the walk left part of the source out at a bound of its own. See
    #: `brain.connectors.declaration.BoundedWalk`.
    left_out: bool = False
    waited: float = 0.0


def _state_after(one: _Reading, entities: Sequence[str]) -> ReadState | None:
    """What this attempt leaves as the read's place: moved on, or as it found it.

    An attempt that read no page and carried on nothing, a key the vault would not give, leaves the
    state it found rather than a read begun at its own instant, so the cursor a later read of
    changes asks from is never moved by an attempt that asked the source nothing.
    """
    carried = one.before is not None and one.before.walking is not None
    if not one.read.walks and not carried:
        return one.before
    return after_the_read(one.before, one.read, entities)


def _finish(
    one: _Reading,
    *,
    clock: Callable[[], datetime],
    outcome: SyncOutcome,
    detail: str,
    previous: SyncState | None,
    call: CallOutcome | None = None,
    retry_after_seconds: float | None = None,
) -> Attempt:
    reading = one.plan.reading
    assert reading is not None  # a plan that may run carries its reading; SyncPlan holds that
    return after_attempt(
        connector=one.plan.connector,
        started_at=one.started_at,
        finished_at=clock(),
        outcome=outcome,
        detail=detail,
        interval=reading.refresh_interval(),
        previous=previous,
        call=call,
        retry_after_seconds=retry_after_seconds,
        records=one.records,
        cut_short=one.cut_short,
        read_state=_state_after(one, reading.entities()),
    )


async def _write_page(
    sessions: async_sessionmaker[AsyncSession],
    source: str,
    entity: str,
    kept: Sequence[tuple[ProjectedRecord, Mapping[str, StoredValue]]],
) -> bool:
    """Write one page's index rows, and advance the source's epoch if that changed any.

    One transaction: the live rows the page names are read, the page is written over them, and
    the epoch moves with them or not at all. See
    `brain.ops.connector_sync.A_CHANGED_READ_ADVANCES_ITS_SOURCE_S_EPOCH`.
    """
    if not kept:
        return False
    async with sessions() as session, session.begin():
        found = await session.execute(
            live_fields(source, entity, [record.source_id for record, _ in kept])
        )
        held = {str(source_id): dict(fields) for source_id, fields in found.all()}
        for record, fields in kept:
            await session.execute(record_upsert(record, fields))
        moved = changed(held, kept)
        if moved:
            await session.execute(advance_epoch(source))
    return moved


async def _parents(
    sessions: async_sessionmaker[AsyncSession],
    source: str,
    under: ListedUnder,
    read: ReadPass,
    kept_ids: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    """Every record of `under.parent` this read kept, in this attempt or an earlier one of it.

    A read begun in this attempt kept its parents in this attempt's memory; one carried on kept
    some of them in an attempt that has ended, and those are the live index rows of the parent
    seen since the read began. See
    `brain.ops.connector_sync.A_WALK_CUT_SHORT_IS_CARRIED_ON_IN_EVERY_SHAPE`.
    """
    here = tuple(kept_ids.get(under.parent, ()))
    async with sessions() as session:
        found = await session.execute(seen_since(source, under.parent, read.started_at))
        earlier = tuple(str(one) for one in found.scalars().all())
    return tuple(sorted({*here, *earlier}))


async def _retire(
    sessions: async_sessionmaker[AsyncSession],
    source: str,
    entities: Sequence[str],
    before: datetime,
) -> int:
    """Retire what a complete read of everything did not see, and advance the epoch if it did.

    See `brain.ops.connector_sync.WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED`.
    """
    retired = 0
    async with sessions() as session, session.begin():
        for entity in entities:
            # One row back per row retired: see `retire_unseen` for why it is not a row count.
            retired += len((await session.execute(retire_unseen(source, entity, before))).all())
        if retired:
            await session.execute(advance_epoch(source))
    return retired


async def attempt(
    live: LiveConnection,
    plan: SyncPlan,
    *,
    previous: SyncState | None,
    sessions: async_sessionmaker[AsyncSession],
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[object]],
    poster: SourcePoster | None = None,
    runner: ScriptRunner | None = None,
) -> Attempt:
    """Read one connection under a lease taken for this attempt, and give it back at the end.

    The lease is closed in a `finally`, so an attempt that raised, or was cancelled, still gives its
    run token back, and the row records how that went. See `brain.ops.connector_lease`. `poster` is
    how a Google source's key file is exchanged for a token (`presented`); a source whose key is
    sent as it is never uses it. `runner` is the sandbox a custom-code source's code runs in
    (`brain.ops.custom_code_run.installed_runner`); every other source never uses it.
    """
    manifest, reading = plan.manifest, plan.reading
    assert manifest is not None and reading is not None  # SyncPlan holds this for a runnable plan
    lease = borrowed(keys, reading, manifest.credential.ref, now=clock())
    try:
        done = await _read_under(
            live,
            plan,
            lease,
            previous=previous,
            sessions=sessions,
            caller=caller,
            resolver=resolver,
            clock=clock,
            sleep=sleep,
            poster=poster,
            runner=runner,
            consenting=Consenting(plan.connector, live.connection.settings, keys),
        )
    finally:
        ended = lease.close(clock())
    return replace(done, lease=ended)


async def _read_under(
    live: LiveConnection,
    plan: SyncPlan,
    lease: KeyLease,
    *,
    previous: SyncState | None,
    sessions: async_sessionmaker[AsyncSession],
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[object]],
    poster: SourcePoster | None,
    runner: ScriptRunner | None = None,
    consenting: Consenting | None = None,
) -> Attempt:
    """Read one connection to the end, or as far as it can be read, and say what that came to."""
    manifest, reading = plan.manifest, plan.reading
    assert manifest is not None and reading is not None  # SyncPlan holds this for a runnable plan
    started_at = clock()
    before = None if previous is None else previous.read_state
    try:
        # A database's views keep no place: see `A_VIEW_READ_IS_ONE_BOUNDED_READ`. Neither do an
        # MCP server's tools or custom code, which are read whole on every attempt.
        read = (
            ReadPass(started_at=started_at)
            if isinstance(reading, ViewReading | ToolReading | CodeReading)
            else next_read(reading, before, now=started_at)
        )
    except Exception:
        # A subscription the reading could not build: everything is read, which asks for at
        # least what any cursor would have and loses nothing.
        read = ReadPass(started_at=started_at)
    one = _Reading(plan=plan, started_at=started_at, read=read, before=before)

    def finish(
        outcome: SyncOutcome,
        detail: str,
        *,
        call: CallOutcome | None = None,
        retry_after_seconds: float | None = None,
    ) -> Attempt:
        return _finish(
            one,
            clock=clock,
            outcome=outcome,
            detail=detail,
            previous=previous,
            call=call,
            retry_after_seconds=retry_after_seconds,
        )

    try:
        key = lease.key()
    except SecretsUnavailableError as unavailable:
        return finish(SyncOutcome.FAILED, key_detail(unavailable))
    if isinstance(reading, ViewReading):
        # A database's views: one bounded read per entity, as the user the slot keeps. See
        # `brain.connectors.declaration.A_DATABASE_IS_READ_BY_THE_SAME_LOOP`.
        try:
            login = DatabaseLogin(lease.user(), SealedSecret(key))
        except SecretsUnavailableError as unavailable:
            return finish(SyncOutcome.FAILED, key_detail(unavailable))
        return await _read_views(
            live,
            one,
            reading,
            login,
            finish=finish,
            sessions=sessions,
            resolver=resolver,
            clock=clock,
            sleep=sleep,
        )
    if isinstance(reading, ToolReading | CodeReading):
        # An MCP server's tools, or custom code in a sandbox: one read per entity, each call
        # admitted by the ceiling. See `_read_by_calls`.
        return await _read_by_calls(
            live,
            one,
            reading,
            key,
            finish=finish,
            sessions=sessions,
            caller=caller,
            poster=poster,
            runner=runner,
            resolver=resolver,
            clock=clock,
        )
    try:
        shown = presented(
            reading,
            key,
            poster=poster,
            resolver=resolver,
            now=clock(),
            consenting=consenting,
        )
    except UnsafeAddressError:
        return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
    except TokenNotIssuedError as refused:
        detail = presenting_detail(refused, poster=poster)
        return finish(SyncOutcome.FAILED, detail, call=refused.call)
    except SecretsUnavailableError as unavailable:
        return finish(SyncOutcome.FAILED, key_detail(unavailable))
    headers = call_headers(reading, live.connection.settings, shown)
    limiter = LimiterState()
    # The ids kept in this run, by entity, for an entity listed under each of them (M11.7.3).
    kept_ids: dict[str, list[str]] = {}

    settings = live.connection.settings
    routed = isinstance(reading, RoutedReading)
    entities = reading.entities()
    for entity in entities:
        walk = one.read.walk(plan.connector, entity)
        if walk.exhausted:
            # Read to its last page by an earlier attempt of this read.
            continue
        under = listed_under(reading, entity)
        if isinstance(reading, RoutedReading) and not walk.cursor:
            # What no server publishes is kept as that, without a call. See
            # A_PAGE_MAY_BE_READ_FROM_ITS_OWN_SERVER. Once a read, at the start of its walk.
            unrouted = reading.unrouted(entity, settings=settings, seen_at=clock())
            await _write_page(
                sessions,
                plan.connector,
                entity,
                [(record, kept_fields(record, manifest)) for record in unrouted],
            )
            one.records += len(unrouted)
        try:
            parents: Sequence[str] = ()
            if under is not None:
                parents = await _parents(sessions, plan.connector, under, one.read, kept_ids)
            starts = walks(
                reading, entity, under, parents, read=one.read, walk=walk, settings=settings
            )
        except UnsafeAddressError:
            return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
        except Exception:
            return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
        if not starts:
            # Nothing to list: no route, or no parent kept. The entity is read to its end.
            one.read = one.read.advanced(replace(walk, cursor="", exhausted=True))
            continue
        stopped = False
        for index, (parent_id, first) in enumerate(starts):
            # Where the walk goes once this one ends: the next parent's first page, or nowhere.
            then = starts[index + 1][1] if index + 1 < len(starts) else None
            arguments: Mapping[str, str] | None = first
            pages = 0
            while arguments is not None:
                try:
                    operation = page_operation(
                        reading, entity, arguments, settings=settings, resolver=resolver
                    )
                except UnsafeAddressError:
                    # The specification's own server is checked when it is loaded, before any
                    # path is built, so a source whose name answers inside the network is
                    # refused here first.
                    return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
                except Exception:
                    return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
                if pages >= MAX_PAGES_PER_ENTITY:
                    # The walk's place is the page not asked, so the next attempt asks it. See
                    # A_WALK_CUT_SHORT_IS_CARRIED_ON_IN_EVERY_SHAPE.
                    one.cut_short = True
                    stopped = True
                    break
                decision = check(now=clock(), limits=plan.limits, state=limiter)
                if not decision.allowed:
                    if one.waited + decision.retry_after_seconds > MAX_SECONDS_WAITING_IN_A_RUN:
                        return finish(
                            SyncOutcome.QUOTA,
                            OWN_SHARE_SPENT,
                            retry_after_seconds=decision.retry_after_seconds,
                        )
                    one.waited += decision.retry_after_seconds
                    await sleep(decision.retry_after_seconds)
                    continue
                limiter = limiter.record(clock(), plan.limits)
                try:
                    checked = operation.prepare(arguments, resolver=resolver)
                except UnsafeAddressError:
                    return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
                except Exception:
                    return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
                answer = caller.get(
                    checked.url,
                    address=checked.address,
                    headers=headers,
                    max_bytes=MAX_RESPONSE_BYTES,
                )
                read_at = clock()
                call = classify(
                    status=answer.status,
                    timed_out=answer.timed_out,
                    connection_failed=answer.connection_failed or answer.status is None,
                )
                said = answer.headers or {}
                if call is CallOutcome.QUOTA:
                    return finish(
                        SyncOutcome.QUOTA,
                        SOURCE_ALLOWANCE_REFUSED,
                        retry_after_seconds=reading.retry_after(said),
                    )
                if call in (CallOutcome.REJECTED, CallOutcome.UNAVAILABLE):
                    if routed and isinstance(reading, RoutedReading):
                        # One server failing is one page, not the source: the rest are still
                        # read, the record keeps what an earlier read kept, and the run says it
                        # stopped short of the whole list. The read is partial, so it retires
                        # nothing: the record that server publishes was not asked for.
                        one.cut_short = True
                        try:
                            following = reading.next_route(entity, arguments, settings=settings)
                            after = following if following is not None else then
                            walk = walk.advance(
                                cursor="" if after is None else page_cursor(after),
                                returned=0,
                                exhausted=after is None,
                            )
                        except Exception:
                            return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
                        one.read = replace(one.read.advanced(walk), partial=True)
                        arguments = following
                        continue
                    return finish(
                        SyncOutcome.FAILED,
                        failure_detail(call, timed_out=answer.timed_out),
                        call=call,
                    )
                try:
                    body = json.loads(answer.body)
                    reply = reading.interpret(
                        operation,
                        status=answer.status or 0,
                        body=body,
                        fetched_at=read_at.isoformat(),
                    )
                    if reply.call in REFUSED_INSIDE_AN_ANSWER:
                        # A source that refuses inside an answered call, as Slack's `ok: false`
                        # does, is read as the refusal it is and never as a page with no rows.
                        return finish(
                            SyncOutcome.FAILED, failure_detail(reply.call), call=reply.call
                        )
                    found = reply.rows
                    if found is not None and under is not None and parent_id is not None:
                        # Named by its parent's id and its own. See `A_RECORD_LISTED_UNDER_...`.
                        found = under.named(found, parent_id)
                    rows = [] if found is None else [r.model_dump() for r in found.records]
                    kept: list[tuple[ProjectedRecord, Mapping[str, StoredValue]]] = []
                    for row in rows:
                        projected = reading.projected(entity, row, seen_at=read_at)
                        if projected is not None:
                            kept.append((projected, kept_fields(projected, manifest)))
                            kept_ids.setdefault(entity, []).append(projected.source_id)
                    returned = len(operation.project(body))
                    following = (
                        reading.next_route(entity, arguments, settings=settings)
                        if isinstance(reading, RoutedReading)
                        else reading.next_page(entity, arguments, body, returned)
                    )
                    after = following if following is not None else then
                    # Refuses a next page that is the page just read, which is a loop.
                    walk = walk.advance(
                        cursor="" if after is None else page_cursor(after),
                        returned=returned,
                        exhausted=after is None,
                    )
                    skipped = isinstance(reading, BoundedWalk) and reading.left_out(
                        entity, arguments, body
                    )
                except Exception:
                    # Broad on purpose, and the type is not kept either: a refusal raised while
                    # reading a row can quote the row. Nothing from this page was written.
                    return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
                await _write_page(sessions, plan.connector, entity, kept)
                one.records += len(kept)
                one.read = one.read.advanced(walk)
                if skipped:
                    # The walk reached a bound of its own and left part of the source out. See
                    # `brain.connectors.declaration.BoundedWalk`.
                    one.cut_short = True
                    one.left_out = True
                    one.read = replace(one.read, partial=True)
                pages += 1
                arguments = following
                if after is not None and reading.allowance_spent(said):
                    return finish(SyncOutcome.QUOTA, SOURCE_ALLOWANCE_REFUSED)
            if stopped:
                break

    if one.read.retires(entities):
        await _retire(sessions, plan.connector, entities, one.read.started_at)
    detail = READ_BUT_CUT_SHORT if one.cut_short else READ_TO_THE_END
    if one.left_out and one.read.complete(entities):
        # A walk that ended having left part of the source out is not carried on by the next
        # run, so it says what was left out rather than that the next run carries on.
        detail = READ_BUT_PART_LEFT_OUT
    return finish(SyncOutcome.SYNCED, detail)


async def _read_views(
    live: LiveConnection,
    one: _Reading,
    reading: ViewReading,
    login: DatabaseLogin,
    *,
    finish: Callable[..., Attempt],
    sessions: async_sessionmaker[AsyncSession],
    resolver: Resolver,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[object]],
) -> Attempt:
    """Each view read once, bounded, admitted by the ceiling, and its index written (M11.6.1).

    The REST loop's admission, write and outcome, with one read where that loop has pages: a
    database does not page, and a read that reached its row cap is cut short, which the next run
    reads again from the start. Every failure leaves one of `brain.ops.connector_sync`'s constant
    sentences and never the database's own words, which can quote the statement.
    """
    manifest = one.plan.manifest
    assert manifest is not None  # SyncPlan holds this for a runnable plan
    limiter = LimiterState()
    for entity in reading.entities():
        decision = check(now=clock(), limits=one.plan.limits, state=limiter)
        while not decision.allowed:
            if one.waited + decision.retry_after_seconds > MAX_SECONDS_WAITING_IN_A_RUN:
                return finish(
                    SyncOutcome.QUOTA,
                    OWN_SHARE_SPENT,
                    retry_after_seconds=decision.retry_after_seconds,
                )
            one.waited += decision.retry_after_seconds
            await sleep(decision.retry_after_seconds)
            decision = check(now=clock(), limits=one.plan.limits, state=limiter)
        limiter = limiter.record(clock(), one.plan.limits)
        read_at = clock()
        try:
            page = reading.read(
                FetchRequest(entity=entity),
                settings=live.connection.settings,
                login=login,
                resolver=resolver,
                fetched_at=read_at.isoformat(),
            )
        except UnsafeAddressError:
            return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
        except Exception:
            # Broad and typeless, for the REST loop's reason: a refusal can quote the settings.
            return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
        if page.call is CallOutcome.QUOTA:
            # A database has no allowance to refuse; only an application's own answer can say so.
            return finish(SyncOutcome.QUOTA, SOURCE_ALLOWANCE_REFUSED)
        if page.call in (CallOutcome.REJECTED, CallOutcome.UNAVAILABLE):
            return finish(SyncOutcome.FAILED, database_failure_detail(page.call), call=page.call)
        try:
            rows = [] if page.rows is None else [r.model_dump() for r in page.rows.records]
            kept: list[tuple[ProjectedRecord, Mapping[str, StoredValue]]] = []
            for row in rows:
                projected = reading.projected(entity, row, seen_at=read_at)
                if projected is not None:
                    kept.append((projected, kept_fields(projected, manifest)))
        except Exception:
            return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
        await _write_page(sessions, one.plan.connector, entity, kept)
        one.records += len(kept)
        one.cut_short = one.cut_short or page.call is CallOutcome.TRUNCATED
    detail = READ_BUT_CUT_SHORT if one.cut_short else READ_TO_THE_END
    return finish(SyncOutcome.SYNCED, detail)


def bare_headers(scheme: KeyScheme, key: str) -> dict[str, str]:
    """The headers an MCP or custom-code source's call carries: JSON, and the key in its scheme.

    Their readings name a scheme sent as it is (`declaration.SCHEMES_SENT_AS_THEY_ARE`), so the
    key is never exchanged first; a source taking no key is sent no `Authorization` at all.
    """
    if scheme is KeyScheme.NONE:
        return {"Accept": "application/json"}
    return {"Accept": "application/json", "Authorization": authorization(scheme, key)}


class _Admission:
    """The source's ceiling, asked before each call of a run that cannot wait inside itself.

    An MCP session and a custom connector's planned calls are made in one synchronous step each,
    so a call the ceiling does not admit is not waited for: the attempt ends as this install's
    share spent, with the wait the ceiling named, and the next run reads the source again.
    """

    def __init__(self, limits: tuple[Limit, ...], clock: Callable[[], datetime]) -> None:
        self._limits = limits
        self._clock = clock
        self._state = LimiterState()
        self.retry_after: float | None = None

    def __call__(self) -> bool:
        decision = check(now=self._clock(), limits=self._limits, state=self._state)
        if not decision.allowed:
            self.retry_after = decision.retry_after_seconds
            return False
        self._state = self._state.record(self._clock(), self._limits)
        return True


async def _read_by_calls(
    live: LiveConnection,
    one: _Reading,
    reading: ToolReading | CodeReading,
    key: str,
    *,
    finish: Callable[..., Attempt],
    sessions: async_sessionmaker[AsyncSession],
    caller: SourceCaller,
    poster: SourcePoster | None,
    runner: ScriptRunner | None,
    resolver: Resolver,
    clock: Callable[[], datetime],
) -> Attempt:
    """Each entity of an MCP server's tools or of custom code, read once and written (M11.1.2).

    The views loop's write and outcome, with the calls each read makes admitted one by one by the
    source's ceiling (`_Admission`). An MCP source opens one session for the attempt and calls one
    declared tool per entity (`brain.ops.mcp_session`); a custom-code source plans, is called and
    is read per entity (`brain.ops.custom_code_run.read_once`, M11.1.5). Every failure leaves one
    of `brain.ops.connector_sync`'s constant sentences and never the source's or the code's words.
    """
    manifest = one.plan.manifest
    assert manifest is not None  # SyncPlan holds this for a runnable plan
    if poster is None and isinstance(reading, ToolReading):
        return finish(SyncOutcome.FAILED, NO_WAY_TO_POST)
    if runner is None and isinstance(reading, CodeReading):
        return finish(SyncOutcome.FAILED, NO_SANDBOX)
    settings = live.connection.settings
    headers = bare_headers(reading.key_scheme(), key)
    admit = _Admission(one.plan.limits, clock)
    try:
        session = None
        if isinstance(reading, ToolReading):
            assert poster is not None  # refused above
            session = open_session(
                reading,
                settings=settings,
                headers=headers,
                poster=poster,
                resolver=resolver,
                admit=admit,
            )
        for entity in reading.entities():
            read_at = clock()
            page: PageReply
            if session is not None and isinstance(reading, ToolReading):
                page = read_entity(session, reading, entity, None, fetched_at=read_at.isoformat())
            else:
                assert isinstance(reading, CodeReading) and runner is not None  # refused above
                page = read_once(
                    reading,
                    entity,
                    None,
                    settings=settings,
                    headers=headers,
                    secret=key,
                    runner=runner,
                    caller=caller,
                    poster=poster,
                    resolver=resolver,
                    admit=admit,
                    fetched_at=read_at.isoformat(),
                )
            if page.call is not CallOutcome.OK or page.rows is None:
                # Answered, and said it failed: never a page with no rows, and not a refused key.
                return finish(SyncOutcome.FAILED, TOOL_SAID_IT_FAILED, call=page.call)
            kept: list[tuple[ProjectedRecord, Mapping[str, StoredValue]]] = []
            for row in (r.model_dump() for r in page.rows.records):
                projected = reading.projected(entity, row, seen_at=read_at)
                if projected is not None:
                    kept.append((projected, kept_fields(projected, manifest)))
            await _write_page(sessions, one.plan.connector, entity, kept)
            one.records += len(kept)
    except CallNotAdmittedError:
        return finish(SyncOutcome.QUOTA, OWN_SHARE_SPENT, retry_after_seconds=admit.retry_after)
    except CallNotAnsweredError as failed:
        if failed.call is CallOutcome.QUOTA:
            return finish(
                SyncOutcome.QUOTA, SOURCE_ALLOWANCE_REFUSED, retry_after_seconds=failed.retry_after
            )
        detail = failure_detail(failed.call, timed_out=failed.timed_out)
        return finish(SyncOutcome.FAILED, detail, call=failed.call)
    except UnsafeAddressError:
        return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
    except McpToolNotAsReviewedError:
        return finish(SyncOutcome.FAILED, TOOL_NOT_AS_REVIEWED)
    except KeyInSandboxError:
        return finish(SyncOutcome.FAILED, KEY_KEPT_OUT)
    except CodeRunFailedError:
        return finish(SyncOutcome.FAILED, CODE_DID_NOT_COMPLETE)
    except CustomCodeError:
        return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
    except Exception:
        # Broad and typeless, for the REST loop's reason: a refusal can quote what was answered.
        return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
    return finish(SyncOutcome.SYNCED, READ_TO_THE_END)


#: What a connector's own `interpret` may read an answered call as instead of a page: the body said
#: the key was refused, or the source was not able to answer. `TRUNCATED` is a page and is not here.
REFUSED_INSIDE_AN_ANSWER: Final = frozenset(
    {CallOutcome.REJECTED, CallOutcome.UNAVAILABLE, CallOutcome.QUOTA}
)


async def sync_on(
    *,
    sessions: async_sessionmaker[AsyncSession],
    now: datetime,
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    readings: Mapping[str, Reading] = READINGS,
    poster: SourcePoster | None = None,
    runner: ScriptRunner | None = None,
) -> SyncRun:
    """Every live connection that may be read and is due, read once, and each attempt recorded.

    A source a halt stops, on itself or on everything, or every source when the halts cannot be
    read, is not read and records no attempt, so it is due again the moment the halt is lifted.

    The connectors reviewed on this install are read first, so a definition approved since the last
    cycle is read in this one and one changed since is not (M11.7.8). See
    `brain.ops.connector_catalogue.A_REVIEWED_CONNECTOR_IS_READ_BEFORE_IT_IS_SERVED`.
    """
    await refresh(sessions)
    halts = await read_state(sessions)
    async with sessions() as session, session.begin():
        live = await read_live(session)
        states = await read_states(session)
    read = waiting = failed = not_due = cannot = held = 0
    for one in live:
        if refusal_in(halts, Work(connector=one.connection.connector)):
            held += 1
            continue
        previous = states.get(one.id)
        plan = plan_for(one.connection, last=previous, now=now, readings=readings, runner=runner)
        if plan.refused:
            cannot += 1
            continue
        if not plan.due:
            not_due += 1
            continue
        done = await attempt(
            one,
            plan,
            previous=previous,
            sessions=sessions,
            keys=keys,
            caller=caller,
            resolver=resolver,
            clock=clock,
            sleep=sleep,
            poster=poster,
            runner=runner,
        )
        async with sessions() as session, session.begin():
            await session.execute(attempt_row(one.id, done))
        if done.outcome is SyncOutcome.SYNCED:
            read += 1
        elif done.outcome is SyncOutcome.QUOTA:
            waiting += 1
        else:
            failed += 1
    return SyncRun(
        read=read,
        waiting=waiting,
        failed=failed,
        not_due=not_due,
        cannot_be_read=cannot,
        held=held,
    )


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def run_connector_sync_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> SyncRun:
    """`sync_on`, from a thread with no event loop of its own, with the worker's real parts.

    The shape `brain.ops.webhook_delivery.run_dispatch_now` takes, for its reasons. The records and
    the attempts are written through sessions over the worker's own login; see
    `brain.ops.connector_sync_store`.
    """
    from brain.session import make_app_engine, make_session_factory

    async def go() -> SyncRun:
        engine = make_app_engine(database_url)
        sessions = make_session_factory(engine)
        keys = worker_connector_keys(vault_address, vault_token)
        caller, resolver = HttpsSourceCaller(), SystemResolver()
        try:
            done = await sync_on(
                sessions=sessions,
                now=now,
                keys=keys,
                caller=caller,
                resolver=resolver,
                clock=_utc_now,
                poster=caller,
                runner=installed_runner(),
            )
            # The switched-on Lark Base's minimal index, on the same schedule and under the same
            # keys; it has no connection row, for `brain.ops.lark_base_index`'s reason.
            base = await index_if_due(
                sessions,
                now=now,
                keys=keys,
                caller=caller,
                resolver=resolver,
                issuer=HttpsTokenIssuer(),
            )
            return done if base is None else replace(done, base=base.summary())
        finally:
            await engine.dispose()

    return asyncio.run(go(), loop_factory=loop_factory)
