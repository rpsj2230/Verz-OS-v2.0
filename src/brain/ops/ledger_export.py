"""Each run's masked trace graph, sent to the trace ledger an install switched on, and nowhere else.

The owner gave the trace ledger room on his server (`docs/needs-rupash.md` item 120, row 3) so
engineers can inspect each model call on its screen. Until this module nothing sent it a span:
`langfuse_host` and its two keys were settings with no reader, and the one trace store was the
masked graph `brain.ops.trace_store` keeps in PostgreSQL. This sends that same graph, as `mask`
left it, to the ledger, and decides where the ledger is.

**The install setting is the one source of where spans go.** `INSTALL_SERVICES` naming
`langfuse` is what starts the ledger (`brain.ops.overlays`), so it is also what makes it the
destination: `ledger_address` answers the product's own service by name when the ledger is
switched on or the profile runs it, and None otherwise, and
`brain.ops.wiring.trace_config_conflicts` accepts a destination on lite when the ledger is
switched on, because the service is declared.
Rejected: a destination setting of its own. Two settings that must agree are two settings that
one day do not, and the one that is wrong is the one sending a client's traces somewhere.

**Nothing is sent that `mask` did not leave.** `events_of` builds every field it sends from
`mask(step.span)`, the only way a span may leave this process (`brain.ops.tracing`), so the ledger
holds exactly the shapes the payload store holds and the database's own check would admit. A
model attempt is sent as a generation, which is what the ledger's screen lists as a model call;
everything else is a span under the run.

**The keys are the ledger's, minted on the server, and kept in the vault.** The release mints the
ledger's project keys with the ledger's other secrets (`ops/deploy/overlays/langfuse.prepare.sh`),
hands them to the ledger's own first start, and hands them to the application, which keeps them
at `providers/trace_ledger` with its own token, where the mail relay's password and the console's
provider keys already live (`keep_keys`, `python -m brain.ops.ledger_export keep`). A process
reads them from there when it first sends and keeps them a quarter of an hour, the time the worker
keeps a provider key. Rejected: a table, for
`brain.ops.credentials.NO_VAULT_IS_NOT_A_REASON_TO_USE_A_TABLE`.

**Sending never costs an answer anything.** A send runs beside the request, not in it, with a
two-second limit, and a ledger that is down, slow, refusing or misconfigured is a line in the
log and a run missing from its screen; the run's own trace is already in the payload store. See
`A_LEDGER_THAT_DOES_NOT_ANSWER_COSTS_A_RUN_NOTHING`.

Task ids: M32.1.2.6, M32.1.1.4
"""

from __future__ import annotations

import asyncio
import base64
import sys
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import httpx
import structlog

from brain.ops.credentials import CredentialVault
from brain.ops.leases import SealedSecret
from brain.ops.provider_keys import StaticKvReader
from brain.ops.tracing import StepKind, mask
from brain.ops.wiring import runs_trace_ledger

if TYPE_CHECKING:
    from brain.ops.trace_store import Step

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why a ledger that does not answer changes nothing about a run.
A_LEDGER_THAT_DOES_NOT_ANSWER_COSTS_A_RUN_NOTHING: Final = (
    "The trace ledger is a screen for engineers. The run's own masked trace is already in the "
    "payload store, and its metadata in the ledger the console reads, before anything is sent, "
    "so a send that fails loses one row from a diagnostic screen. A send that held the answer "
    "up would cost every person a delay for a screen most of them never open."
)

# --------------------------------------------------------------------------- the figures
#: The ledger's web service and port in `docker-compose.langfuse.yml`, which the deploy step joins
#: to the network the application is on (`ops/deploy/overlays/langfuse.attach.yml`).
LEDGER_SERVICE: Final = "langfuse-web"
LEDGER_PORT: Final = 3000

#: Where the ledger's project keys are kept, and the two fields.
LEDGER_KEY_SLOT: Final = "providers/trace_ledger"
PUBLIC_FIELD: Final = "public_key"
PRIVATE_FIELD: Final = "secret_key"

#: The shapes the ledger gives its keys, which the release mints in the same shape.
PUBLIC_PREFIX: Final = "pk-lf-"
PRIVATE_PREFIX: Final = "sk-lf-"

#: How long one send may take. Two seconds against a service on the same host.
SEND_TIMEOUT_SECONDS: Final = 2.0

#: How long a process keeps the keys it read before asking the vault again.
KEYS_KEPT_FOR: Final = timedelta(minutes=15)

#: The ledger's ingestion route.
INGESTION_PATH: Final = "/api/public/ingestion"


class LedgerError(Exception):
    """The keys handed to the application are not the ledger's shape, or none could be kept."""


def ledger_address(profile: str, configured: str, switched: Collection[str]) -> str | None:
    """Where this install sends spans, or None when it runs no trace ledger.

    `switched` is the containers its optional services run
    (`brain.ops.overlays.components_switched_on`). The configured value wins where there is one,
    which `brain.ops.wiring.trace_config_conflicts` refuses on an install that runs no ledger.
    """
    if not runs_trace_ledger(profile, switched):
        return None
    return configured.strip() or f"http://{LEDGER_SERVICE}:{LEDGER_PORT}"


def destination_here(profile: str, configured: str) -> str | None:
    """`ledger_address` for this process, reading the optional services through the one reader.

    A setting that names a service nobody declared sends nothing rather than raising inside a
    send, for `brain.ops.overlays.A_PLAN_THAT_CANNOT_BE_MADE_STOPS_NOTHING`'s reason turned
    round: an unreadable switch is not a reason to send a client's traces anywhere.
    """
    from brain.ops.overlays import OverlayError, components_switched_on, switched_on_here

    try:
        switched = components_switched_on(switched_on_here())
    except OverlayError:
        return None
    return ledger_address(profile, configured, switched)


# ------------------------------------------------------------------------------ the keys
@dataclass(frozen=True)
class LedgerKeys:
    """The ledger's project keys. The secret has no rendering (`brain.ops.leases.SealedSecret`)."""

    public: str
    secret: SealedSecret

    def authorisation(self) -> str:
        """The ledger's basic authorisation header value."""
        pair = f"{self.public}:{self.secret.reveal()}".encode()
        return "Basic " + base64.b64encode(pair).decode("ascii")


def keys_from(lines: Iterable[str]) -> LedgerKeys:
    """The two keys as the deploy step hands them over: the public line, then the secret line."""
    found = [one.strip() for one in lines if one.strip()]
    if len(found) != 2 or not found[0].startswith(PUBLIC_PREFIX):
        msg = "the deploy step handed over no public key in the ledger's shape"
        raise LedgerError(msg)
    if not found[1].startswith(PRIVATE_PREFIX) or len(found[1]) <= len(PRIVATE_PREFIX):
        msg = "the deploy step handed over no secret key in the ledger's shape"
        raise LedgerError(msg)
    return LedgerKeys(public=found[0], secret=SealedSecret(found[1]))


def keep_keys(vault: CredentialVault, keys: LedgerKeys) -> None:
    """Write the keys to their slot, with the application's own token."""
    vault.write_static_kv(
        LEDGER_KEY_SLOT, {PUBLIC_FIELD: keys.public, PRIVATE_FIELD: keys.secret.reveal()}
    )


def read_keys(vault: StaticKvReader) -> LedgerKeys | None:
    """The keys the slot holds, or None when it holds none in the ledger's shape."""
    fields = vault.read_static_kv(LEDGER_KEY_SLOT)
    public, secret = fields.get(PUBLIC_FIELD), fields.get(PRIVATE_FIELD)
    if not isinstance(public, str) or not isinstance(secret, str):
        return None
    try:
        return keys_from((public, secret))
    except LedgerError:
        return None


class KeptKeys:
    """The keys, read from the vault when first needed and kept for `KEYS_KEPT_FOR`."""

    def __init__(self, vault: StaticKvReader | None, *, clock: Callable[[], datetime]) -> None:
        self._vault = vault
        self._clock = clock
        self._held: LedgerKeys | None = None
        self._read_at: datetime | None = None

    def __call__(self) -> LedgerKeys | None:
        now = self._clock()
        if self._read_at is not None and now - self._read_at < KEYS_KEPT_FOR:
            return self._held
        if self._vault is None:
            return None
        try:
            self._held = read_keys(self._vault)
        except Exception as exc:
            log.warning("ledger.keys_unread", error=type(exc).__name__)
            self._held = None
        self._read_at = now
        return self._held


# ---------------------------------------------------------------------------- the events
def _observation_id(trace_id: str, step: int) -> str:
    return f"{trace_id}-{step}"


def events_of(trace_id: str, steps: Sequence[Step], *, at: datetime) -> list[dict[str, Any]]:
    """One run as the ledger's ingestion batch, every field from `mask(step.span)`.

    The run's first step is the trace; each step after it is an observation under it, a model
    attempt as a generation and anything else as a span, hung from its parent step when that is
    not the run itself. Event ids are derived from the trace and the step, so a send repeated is
    the same events again rather than a second copy of the run.
    """
    if not steps:
        return []
    stamp = at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    root = mask(steps[0].span)
    events: list[dict[str, Any]] = [
        {
            "id": f"{trace_id}-trace",
            "timestamp": stamp,
            "type": "trace-create",
            "body": {
                "id": trace_id,
                "timestamp": stamp,
                "name": root.name,
                "environment": root.environment,
                "metadata": dict(root.attributes),
                "input": root.payload_in,
                "output": root.payload_out,
            },
        }
    ]
    for one in steps[1:]:
        masked = mask(one.span)
        kind = "generation-create" if one.kind is StepKind.MODEL_ATTEMPT else "span-create"
        body: dict[str, Any] = {
            "id": _observation_id(trace_id, one.step),
            "traceId": trace_id,
            "name": masked.name,
            "startTime": stamp,
            "environment": masked.environment,
            "metadata": dict(masked.attributes),
            "input": masked.payload_in,
            "output": masked.payload_out,
        }
        if one.parent not in (None, 0):
            body["parentObservationId"] = _observation_id(trace_id, int(one.parent or 0))
        events.append({"id": f"{body['id']}-event", "timestamp": stamp, "type": kind, "body": body})
    return events


# ------------------------------------------------------------------------------ the send
Client = Callable[[], httpx.AsyncClient]


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS)


class LedgerShipper:
    """Sends a run's graph to the ledger, beside the request and never in its way.

    `destination` and `keys` are asked on every send, so a ledger switched on in the console, or
    keys handed over by a deploy, are used without a restart.
    """

    def __init__(
        self,
        *,
        destination: Callable[[], str | None],
        keys: Callable[[], LedgerKeys | None],
        clock: Callable[[], datetime],
        client: Client = _client,
    ) -> None:
        self._destination = destination
        self._keys = keys
        self._clock = clock
        self._client = client
        self._running: set[asyncio.Task[bool]] = set()

    def ship_beside(self, trace_id: str, steps: Sequence[Step]) -> None:
        """Start a send and return at once.

        See `A_LEDGER_THAT_DOES_NOT_ANSWER_COSTS_A_RUN_NOTHING`.
        """
        task = asyncio.get_running_loop().create_task(self.ship(trace_id, steps))
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def ship(self, trace_id: str, steps: Sequence[Step]) -> bool:
        """Send one run and say whether the ledger took every event. Never raises."""
        address = self._destination()
        if address is None or not steps:
            return False
        keys = self._keys()
        if keys is None:
            log.info("ledger.unsent", trace_id=trace_id, reason="no_keys")
            return False
        batch = events_of(trace_id, steps, at=self._clock())
        try:
            async with self._client() as client:
                answer = await client.post(
                    address.rstrip("/") + INGESTION_PATH,
                    json={"batch": batch},
                    headers={"Authorization": keys.authorisation()},
                )
        except httpx.HTTPError as exc:
            log.info("ledger.unsent", trace_id=trace_id, reason=type(exc).__name__)
            return False
        taken = answer.status_code in (200, 201, 207) and not _errors_in(answer)
        if not taken:
            log.info("ledger.refused", trace_id=trace_id, status=answer.status_code)
        return taken


def _errors_in(answer: httpx.Response) -> bool:
    """Whether a multi-status answer reports any event refused."""
    try:
        body = answer.json()
    except ValueError:
        return answer.status_code == 207
    return bool(isinstance(body, dict) and body.get("errors"))


# ------------------------------------------------------------------------------- the hand
def main(argv: Sequence[str] | None = None) -> int:
    """`keep`, with the two keys on standard input: what the deploy step runs in the application."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["keep"]:
        print("usage: python -m brain.ops.ledger_export keep < keys", file=sys.stderr)
        return 64
    try:
        from brain.ops.openbao import OpenBaoVault
        from brain.ops.secrets import VaultRole
        from brain.settings import Settings

        keys = keys_from(sys.stdin)
        settings = Settings()
        if not settings.vault_address or not settings.vault_token:
            msg = "this install names no vault, so the ledger's keys have nowhere to be kept"
            raise LedgerError(msg)
        vault = OpenBaoVault(
            settings.vault_address, settings.vault_token, role=VaultRole.APPLICATION
        )
        keep_keys(vault, keys)
    except Exception as error:
        from brain.ops.safe_error import describe

        print(f"SAY the trace ledger's keys were not kept: {describe(error)}")
        return 1
    print("SAY the trace ledger's keys are kept in the vault")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
