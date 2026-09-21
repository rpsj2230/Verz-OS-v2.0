"""The scheduled staff sync: read the chosen staff list with the kept credential and apply it.

`brain.identity.staff_source` chose the source, `brain.identity.staff_adapters` parses it,
`brain.connectors.staff_directories` walks a directory's pages, `brain.identity.staff_sync` makes
the dry run and `brain.identity.staff_roster` decides what it writes. Every one of them said that
nothing ran them on a schedule, and `brain.ops.schedule_runner` said the `directory_sync` control
needed "a roster source". This is the run, and `run_staff_sync_now` is what the worker's schedule
starts as that control.

**The credential is read by the worker alone, through a lease for this one run.** The staff
source's secret is kept at `connector_keys/staff_source`, written from the setup wizard and the
Staff sources screen and never read back by the application; the worker reads it with a run token
minted against the `connector-run` role and revoked when the run ends, exactly as
`brain.ops.connector_sync_run` reads a connected source's key. No vault policy changes for it. See
`THE_STAFF_SOURCE_CREDENTIAL_IS_A_CONNECTOR_KEY`.

**A run that cannot read changes nobody, and says so.** A missing credential, one the source
refused, a source that did not answer and a configuration the checks refuse each append a run row
with a sentence and write no member, and the table's own check refuses a failed run that names
anybody. So a refused credential is a line on the Staff sources screen rather than a night on
which everybody appeared to leave. See `A_RUN_THAT_COULD_NOT_READ_CHANGED_NOBODY`.

**What each source is read with, and the three that are not read on a schedule.** Lark and
Microsoft Entra take the application's own identifier and secret, kept as one value
`<id>:<secret>`, and exchange them for a tenant token, which is the shape a schedule needs: no
person is signed in at two in the morning. A Google Sheet takes an API key. A hand-kept
spreadsheet is read when somebody uploads it and there is nothing to read on a schedule; Google
Workspace needs a signed service-account assertion and LDAP a directory client, neither of which
this product carries, and each says so on its run. See `WHAT_EACH_SOURCE_IS_READ_WITH`.

Rejected: reading the directory from the application process when somebody opens the screen. The
application holds no read on a connector key by policy, and a roster read on page load would
contact the company's directory every time anybody looked.

**After the roster, each department head's audit reach, in a transaction of its own.**
`brain.ops.head_audit_store.rewrite_head_audit_reach` writes the grants Needs Rupash item 48's
Option A names, from the same roster, once the roster's transaction has committed. A failure there
is logged and changes nothing the roster wrote, for that module's reason (M1.8.3).

Task ids: M1.6.1, M1.6.2, M1.6.4, M1.6.12, M1.8.6, M1.8.3
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol
from urllib.parse import quote, urlencode

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.staff_directories import (
    GOOGLE_SHEETS_URL,
    LARK_PLATFORMS,
    MICROSOFT_LOGIN_HOST,
    Answer,
    DirectorySignInError,
    Fetch,
    Outbound,
    location_problem,
    pull,
)
from brain.identity.staff_adapters import (
    GOOGLE_SHEET,
    GOOGLE_WORKSPACE,
    LARK,
    LDAP,
    MICROSOFT_ENTRA,
    SPREADSHEET,
    GoogleSheetSource,
    RosterUnavailableError,
)
from brain.identity.staff_roster import RunOutcome, application_for
from brain.identity.staff_source import (
    STAFF_SOURCE_LOCATION_SETTING,
    Roster,
    StaffSource,
    StaffSourceError,
    roster_from,
    selected_source,
)
from brain.install import value_of
from brain.ops.connectable import key_reference
from brain.ops.connector_sync_run import (
    ConnectorKeys,
    KeyLease,
    key_detail,
    worker_connector_keys,
)
from brain.ops.head_audit_store import rewrite_head_audit_reach
from brain.ops.openbao import VaultUnreachableError
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.staff_sync_store import (
    RunRecord,
    read_last_applied,
    read_members,
    run_row,
    write_application,
)

# ------------------------------------------------------------------ written-down reasons
log = structlog.get_logger()

#: Why the staff source's secret sits beside the connected sources' keys.
THE_STAFF_SOURCE_CREDENTIAL_IS_A_CONNECTOR_KEY: Final = (
    "A staff list is read the way a connected source is read: by the worker, on a schedule, with "
    "a secret a vendor issued and nothing can mint per request. So it is kept where those keys "
    "are, at connector_keys/staff_source, which the application may write and never read and the "
    "worker reads only through a run lease revoked when the run ends."
)

#: Why a failed run writes a row and no member.
A_RUN_THAT_COULD_NOT_READ_CHANGED_NOBODY: Final = (
    "A source that could not be read has said nothing about who works here. Applying that "
    "silence would mark every person as having left, so a run that could not read appends one "
    "row with a sentence saying why and writes no member, and the table refuses a failed run "
    "that names anybody."
)

#: Why each source is read the way it is, and why three are not read on a schedule.
WHAT_EACH_SOURCE_IS_READ_WITH: Final = (
    "A schedule runs with nobody signed in, so a directory is read with the application's own "
    "credential rather than a person's session: Lark and Microsoft exchange an application's "
    "identifier and secret for a tenant token, and a Google Sheet takes an API key. A hand-kept "
    "spreadsheet is read when uploaded, and Google Workspace and LDAP need a signer and a "
    "directory client this product does not carry, so their runs say so and change nobody."
)

#: The slot the staff source's credential is kept in, as `connector_key_slot` builds it.
STAFF_SOURCE_SLOT: Final = "staff_source"

#: How the application identifier and its secret are kept in one value.
CLIENT_CREDENTIAL_SEPARATOR: Final = ":"

#: How long one call to a vendor may take.
CALL_TIMEOUT_SECONDS: Final = 30.0

#: The largest answer a vendor call may send back. A page of fifty people is far under it.
MAX_ANSWER_BYTES: Final = 5_000_000

#: Microsoft's scope for an application token, which is every permission granted to it.
MICROSOFT_APPLICATION_SCOPE: Final = "https://graph.microsoft.com/.default"

#: The range a Google Sheet is read over. Unbounded, which the adapter reads as the whole sheet.
GOOGLE_SHEET_RANGE: Final = "A:Z"

#: What a Google Sheet's identifier looks like. Refused otherwise, because it is part of a URL path.
SHEET_ID: Final = re.compile(r"^[A-Za-z0-9_-]{20,100}$")

# The sentences a run leaves. Constant, so nothing a vendor or a setting said reaches the table
# except through `DirectorySignInError`, whose words `staff_directories` already shortens.
NOT_READ_ON_A_SCHEDULE: Final[Mapping[str, str]] = {
    SPREADSHEET: (
        "A hand-kept spreadsheet is read when somebody uploads it, so there is nothing to read on "
        "a schedule. Nobody was changed."
    ),
    GOOGLE_WORKSPACE: (
        "Google Workspace is not read on a schedule yet: it needs a service account with "
        "domain-wide delegation, which this product cannot sign for. Nobody was changed."
    ),
    LDAP: (
        "An LDAP directory is not read on a schedule yet: this product carries no directory "
        "client. Nobody was changed."
    ),
}
CREDENTIAL_SHAPE: Final = (
    "The kept credential is not in the form this source needs: the application's identifier, "
    "a colon, then its secret. Replace it on the Staff sources screen. Nobody was changed."
)
CREDENTIAL_REFUSED_PREFIX: Final = "The staff source refused the kept credential"
NOBODY_CHANGED: Final = "Nobody was changed."


class CredentialRefusedError(Exception):
    """The source refused the credential. The message is the vendor's words, shortened."""


class Reader(Protocol):
    """Reads one kind of source with a credential and a location, into a parsed source."""

    def __call__(self, fetch: Fetch, credential: str, location: str) -> Awaitable[StaffSource]: ...


@dataclass(frozen=True)
class StaffSyncRun:
    """What one run of the control came to, as the worker's control record reads it."""

    outcome: RunOutcome | None
    detail: str

    def summary(self) -> str:
        """One line for `ops.control_run`."""
        return self.detail if self.outcome is None else f"{self.outcome.value}: {self.detail}"


# -------------------------------------------------------------------------- the readers
def _client_credential(credential: str) -> tuple[str, str]:
    """The identifier and the secret, split at the first separator, or a refusal."""
    ident, separator, secret = credential.strip().partition(CLIENT_CREDENTIAL_SEPARATOR)
    if not separator or not ident.strip() or not secret.strip():
        raise CredentialRefusedError(CREDENTIAL_SHAPE)
    return ident.strip(), secret.strip()


def _token_or_refusal(answer: Answer, field: str) -> str:
    """The token an exchange answered with, or the vendor's refusal of the credential."""
    token = answer.body.get(field)
    refused = answer.status != 200 or answer.body.get("code", 0) not in (0, None)
    if refused or not isinstance(token, str) or not token:
        said = (
            answer.body.get("error_description")
            or answer.body.get("msg")
            or answer.body.get("error")
            or "it gave no reason"
        )
        words = " ".join(str(said).split())[:300]
        raise CredentialRefusedError(f"{CREDENTIAL_REFUSED_PREFIX}: {words}. {NOBODY_CHANGED}")
    return token


async def read_lark(fetch: Fetch, credential: str, location: str) -> StaffSource:
    """Exchange the app's identifier and secret for a tenant token, then walk the directory."""
    app_id, app_secret = _client_credential(credential)
    platform = location.strip().lower()
    problem = location_problem(LARK, platform)
    if problem:
        raise StaffSourceError(f"{problem} {NOBODY_CHANGED}")
    _, open_host = LARK_PLATFORMS[platform]
    url = f"https://{open_host}/open-apis/auth/v3/tenant_access_token/internal"
    answer = await fetch(
        Outbound("POST", url, json_body={"app_id": app_id, "app_secret": app_secret})
    )
    token = _token_or_refusal(answer, "tenant_access_token")
    return await pull(fetch, LARK, token=token, location=platform)


async def read_microsoft(fetch: Fetch, credential: str, location: str) -> StaffSource:
    """Exchange the application's identifier and secret for a Graph token, then walk the users."""
    client_id, client_secret = _client_credential(credential)
    tenant = location.strip().lower()
    problem = location_problem(MICROSOFT_ENTRA, tenant)
    if problem:
        raise StaffSourceError(f"{problem} {NOBODY_CHANGED}")
    url = f"https://{MICROSOFT_LOGIN_HOST}/{tenant}/oauth2/v2.0/token"
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": MICROSOFT_APPLICATION_SCOPE,
    }
    token = _token_or_refusal(await fetch(Outbound("POST", url, form=form)), "access_token")
    return await pull(fetch, MICROSOFT_ENTRA, token=token, location=tenant)


async def read_google_sheet(fetch: Fetch, credential: str, location: str) -> StaffSource:
    """Read the sheet's first twenty-six columns with an API key."""
    sheet = location.strip()
    if not SHEET_ID.match(sheet):
        msg = "The staff list location is not a Google Sheet identifier. Nobody was changed."
        raise StaffSourceError(msg)
    query = urlencode({"key": credential.strip()})
    url = f"{GOOGLE_SHEETS_URL}/{sheet}/values/{quote(GOOGLE_SHEET_RANGE)}?{query}"
    answer = await fetch(Outbound("GET", url, {"Accept": "application/json"}))
    if answer.status in (401, 403):
        _token_or_refusal(answer, "values")
    if answer.status != 200:
        msg = f"Reading the Google Sheet was refused with status {answer.status}. {NOBODY_CHANGED}"
        raise DirectorySignInError(msg)
    return GoogleSheetSource(payload=answer.body)


#: The sources read on a schedule, by the name `INSTALL_STAFF_SOURCE` takes.
READERS: Final[Mapping[str, Reader]] = {
    LARK: read_lark,
    MICROSOFT_ENTRA: read_microsoft,
    GOOGLE_SHEET: read_google_sheet,
}


async def http_fetch(outbound: Outbound) -> Answer:
    """Send one request to a vendor, following no redirect, for `setup_staff_routes`' reason."""
    try:
        async with httpx.AsyncClient(
            timeout=CALL_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            response = await client.request(
                outbound.method,
                outbound.url,
                headers=dict(outbound.headers),
                data=dict(outbound.form) if outbound.form is not None else None,
                json=dict(outbound.json_body) if outbound.json_body is not None else None,
            )
    except httpx.HTTPError as failed:
        host = httpx.URL(outbound.url).host
        msg = f"This server could not reach {host}. {NOBODY_CHANGED}"
        raise DirectorySignInError(msg) from failed
    if len(response.content) > MAX_ANSWER_BYTES:
        return Answer(status=502, body={"error": "the answer was larger than a directory sends"})
    try:
        body = response.json()
    except ValueError:
        body = {}
    return Answer(status=response.status_code, body=body if isinstance(body, Mapping) else {})


# ----------------------------------------------------------------------------- the run
async def sync_staff_on(
    *,
    sessions: async_sessionmaker[AsyncSession],
    now: datetime,
    env: Mapping[str, str] | None,
    keys: ConnectorKeys,
    fetch: Fetch,
    clock: Callable[[], datetime],
    readers: Mapping[str, Reader] = READERS,
) -> StaffSyncRun:
    """One scheduled run: choose, lease, read, check, plan, apply, record, in that order.

    `none` records nothing, because an install that reads no staff list has no run to show and
    a row every night saying so would bury the runs of an install that does. Every other path
    appends exactly one run row, and only a plan `dry_run` marks safe writes a member.
    """
    try:
        chosen = selected_source(env)
    except StaffSourceError as refused:
        # No source name to record against beyond what was typed, so nothing is appended: the
        # Staff sources screen already shows this refusal from the same function.
        return StaffSyncRun(outcome=None, detail=str(refused))
    if not chosen.reads_a_list:
        return StaffSyncRun(outcome=None, detail="No staff list is chosen, so nothing was read.")

    reader = readers.get(chosen.name)
    if reader is None:
        detail = NOT_READ_ON_A_SCHEDULE.get(
            chosen.name, f"{chosen.name!r} has no scheduled reader. {NOBODY_CHANGED}"
        )
        outcome = RunOutcome.NOT_SCHEDULABLE
        return await _record_failure(sessions, chosen.name, now, clock, outcome, detail)

    lease: KeyLease = keys.lease(key_reference(STAFF_SOURCE_SLOT), now=now)
    try:
        try:
            credential = lease.key()
        except SecretsUnavailableError as unavailable:
            detail = f"{key_detail(unavailable)} {NOBODY_CHANGED}"
            outcome = (
                RunOutcome.UNREACHABLE
                if isinstance(unavailable, VaultUnreachableError)
                else RunOutcome.NO_CREDENTIAL
            )
            return await _record_failure(sessions, chosen.name, now, clock, outcome, detail)
        location = value_of(STAFF_SOURCE_LOCATION_SETTING, env)
        try:
            source = await reader(fetch, credential, location)
            roster = roster_from(source, chosen)
        except CredentialRefusedError as refused:
            return await _record_failure(
                sessions, chosen.name, now, clock, RunOutcome.CREDENTIAL_REFUSED, str(refused)
            )
        except (DirectorySignInError, RosterUnavailableError) as unread:
            detail = _sentence(str(unread))
            return await _record_failure(
                sessions, chosen.name, now, clock, RunOutcome.UNREACHABLE, detail
            )
        except (StaffSourceError, ValueError) as refused:
            detail = _sentence(str(refused))
            return await _record_failure(
                sessions, chosen.name, now, clock, RunOutcome.MISCONFIGURED, detail
            )
    finally:
        lease.close(now)

    reading = getattr(source, "reading", None)
    stable_ids: Mapping[str, str] = {}
    aliases: Mapping[str, tuple[str, ...]] = {}
    if callable(reading):
        read = reading()
        stable_ids, aliases = read.stable_ids, read.aliases

    async with sessions() as session, session.begin():
        members = await read_members(session, chosen.name)
        last_applied = await read_last_applied(session, chosen.name)
        application = application_for(
            roster,
            stable_ids=stable_ids,
            aliases=aliases,
            members=members,
            last_applied=last_applied,
        )
        if not application.plan.safe_to_apply:
            detail = _sentence(" ".join(application.plan.refusals))
            record = RunRecord(
                source=chosen.name,
                started_at=now,
                finished_at=max(clock(), now),
                outcome=RunOutcome.MISCONFIGURED,
                detail=detail,
            )
            await session.execute(run_row(record))
            return StaffSyncRun(outcome=record.outcome, detail=detail)
        outcome = application.outcome
        detail = (
            f"Read the staff list from {chosen.name} and applied it."
            if outcome is RunOutcome.APPLIED
            else f"Read {chosen.name}; nobody joined, left or moved."
        )
        record = RunRecord(
            source=chosen.name,
            started_at=now,
            finished_at=max(clock(), now),
            outcome=outcome,
            detail=detail,
            added=application.added,
            marked_left=application.marked_left,
            renamed=application.renamed,
            withheld=application.withheld,
        )
        await write_application(session, application, record)
    await _rewrite_heads(sessions, roster, now)
    return StaffSyncRun(outcome=outcome, detail=detail)


#: Why a head's reach that cannot be written does not fail the run.
A_HEADS_REACH_NEVER_UNDOES_THE_ROSTER: Final = (
    "The roster is committed before the heads' reach is computed, so a reach that cannot be "
    "written leaves every joiner and leaver applied and the reach one run stale, which is the "
    "staleness a head's audit reach already has between runs. One transaction for both would let "
    "a race on one head's grant roll back the whole staff list."
)


async def _rewrite_heads(
    sessions: async_sessionmaker[AsyncSession], roster: Roster, now: datetime
) -> None:
    """Each department head's audit reach, after the roster. See
    `A_HEADS_REACH_NEVER_UNDOES_THE_ROSTER`."""
    try:
        async with sessions() as session, session.begin():
            await rewrite_head_audit_reach(session, roster, read_at=now)
    except Exception as exc:
        # Broad on purpose, and named in the constant above.
        log.warning("staff_sync.head_audit_reach_unwritten", error=type(exc).__name__)


def _sentence(said: str) -> str:
    """A refusal cut to the run row's width, ending by saying nobody changed."""
    text = " ".join(said.split())
    if NOBODY_CHANGED not in text:
        text = f"{text.rstrip('.')}. {NOBODY_CHANGED}"
    return text if len(text) <= 500 else f"{text[:480].rstrip()}... {NOBODY_CHANGED}"


async def _record_failure(
    sessions: async_sessionmaker[AsyncSession],
    source: str,
    now: datetime,
    clock: Callable[[], datetime],
    outcome: RunOutcome,
    detail: str,
) -> StaffSyncRun:
    """Append a run that changed nobody. See `A_RUN_THAT_COULD_NOT_READ_CHANGED_NOBODY`."""
    record = RunRecord(
        source=source,
        started_at=now,
        finished_at=max(clock(), now),
        outcome=outcome,
        detail=_sentence(detail),
    )
    async with sessions() as session, session.begin():
        await session.execute(run_row(record))
    return StaffSyncRun(outcome=outcome, detail=record.detail)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def run_staff_sync_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> StaffSyncRun:
    """`sync_staff_on`, from a thread with no event loop, with the worker's real parts.

    The shape `brain.ops.connector_sync_run.run_connector_sync_now` takes, for its reasons.
    """
    from brain.session import make_app_engine, make_session_factory
    from brain.settings import process_environment

    async def go() -> StaffSyncRun:
        engine = make_app_engine(database_url)
        try:
            return await sync_staff_on(
                sessions=make_session_factory(engine),
                now=now,
                env=process_environment(),
                keys=worker_connector_keys(vault_address, vault_token),
                fetch=http_fetch,
                clock=_utc_now,
            )
        finally:
            await engine.dispose()

    return asyncio.run(go(), loop_factory=loop_factory)
