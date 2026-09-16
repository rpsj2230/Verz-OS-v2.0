"""The object store, spoken to: one S3-compatible client built at start from settings and the vault.

`brain.ops.storage` declared the buckets, their lifecycles, which backends a client may choose and
where each backend's credential lives, and ended with a `StorageBackend` protocol nothing
implemented. So nothing on an install asked the store anything: the Storage screen described
buckets it could not see, the recovery screen said nobody had looked in the backup bucket, and an
artifact had nowhere to be put. This is the implementation, the one function that builds it when
the process starts, and the one reader of the backup bucket.

**Signed by hand over `httpx`, and the reason is the credential rather than the size of the
dependency.** boto3 is the obvious client and it brings a credential chain that looks for a key
on its own: `AWS_ACCESS_KEY_ID` in the process environment, `~/.aws/credentials`, an instance
metadata address. On a server where the backup script's key is exported for the host, that chain
authenticates the application as the backup job without a line here saying so, which is
`brain.settings.NOTHING_ELSE_READS_THE_ENVIRONMENT` broken by a library. `httpx` is already a
dependency, a request here carries exactly the key this module was handed, and the signature is
AWS Signature Version 4, which is short and specified. It is checked against the four examples
AWS publishes for S3, with their own keys and expected signatures, so an error in the canonical
form fails a test rather than presenting as a 403 that reads as a bad key. See
`A_CLIENT_THAT_FINDS_ITS_OWN_CREDENTIAL_IS_READING_THE_ENVIRONMENT`.

**Built once at start, and every way it is not built is a sentence.** No vault, an empty slot, a
vault that did not answer, a backend value nobody recognises, an address `config_for` refuses, or
AWS S3, whose credential is a lease from a dynamic engine that nothing here renews for a client
held for the life of the process. Each of those is `ObjectStore.unconnected`, read by the screens
in words, and none of them stops the process: a store that cannot be reached is a screen that says
so, and a process that will not start is every screen. See
`A_LEASE_NOBODY_RENEWS_IS_A_CREDENTIAL_THAT_STOPS_WORKING_ON_A_SCHEDULE`.

**The credential is read from the backend's own vault slot and nowhere else.** `credential_path`
already names it, `providers/seaweedfs` or `providers/cloudflare-r2`, and the application policy
already reads `providers/data/+`. The two fields are named here, `access_key_id` and
`secret_access_key`, and the secret is held in a field `repr` does not render, for the reason
`brain.ops.openbao.OpenBaoVault` keeps its token out of its own.

**Usage is counted where the names are, and only the figures leave.** S3 has no call that says
how much a bucket holds, so the count is a listing, and a listing is a list of names. `usage`
walks the pages and returns `BucketUsage`, which has no field a name could arrive in, and it stops
at `USAGE_CEILING_OBJECTS` and says the figure is a floor. See `A_COUNT_IS_TAKEN_BESIDE_THE_NAMES`.

**The backup bucket is read for its descriptions and never for its copies.** `backup_objects`
fetches the objects whose names end in a manifest's or a drill record's suffix and nothing else:
a nightly dump is the whole database, and a reader that fetched every object to find the small
ones would load that into the web process on each opening of the recovery screen. See
`A_READER_OF_THE_BACKUP_BUCKET_NEVER_FETCHES_A_COPY`. Read at the bucket's root, because that is
where `ops/backup/brain-backup` writes, which is a fact about the taker rather than a choice here.

**An answer the store gives that is not a success is an error naming the call and the S3 code,
never the body's message.** A refusal body quotes the bucket and the key, and a key can say what a
file is about; the code (`SignatureDoesNotMatch`, `NoSuchKey`) is what a person acts on.

Rejected: retrying here. `brain.ops.effects` classifies a put by key as the same result when
repeated, so a caller may retry, and one that does knows why it failed; a retry loop inside the
client would put a second timeout in front of every screen that reads the store.

Rejected: presigned URLs, for `brain.ops.storage.StorageBackend`'s reason.

Task ids: M32.3.1.4, M32.3.2.1, M32.3.2.2
"""

from __future__ import annotations

import hashlib
import hmac
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from urllib.parse import quote, urlsplit

import httpx
import structlog

from brain.install import InstallError, value_of
from brain.ops.backup_manifest import DRILL_SUFFIX, MANIFEST_SUFFIX
from brain.ops.openbao import (
    DYNAMIC_MOUNTS,
    OpenBaoVault,
    VaultRefusedError,
    VaultUnreachableError,
)
from brain.ops.secrets import SecretsUnavailableError, VaultRole
from brain.ops.storage import (
    Addressing,
    Backend,
    BackendConfig,
    BucketUsage,
    ObjectKind,
    StorageBackend,
    StorageError,
    StoreUnansweredError,
    bucket_for,
    config_for,
    credential_path,
)

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why the client is written here rather than taken from boto3.
A_CLIENT_THAT_FINDS_ITS_OWN_CREDENTIAL_IS_READING_THE_ENVIRONMENT: Final = (
    "A client library with a default credential chain looks for a key in the process "
    "environment, in a file under the home directory and at an instance metadata address, and "
    "uses the first it finds. On a host where the backup job's key is exported, that "
    "authenticates the application as the backup job with nothing in this repository saying so. "
    "So a request here is signed with exactly the credential this module was handed from the "
    "vault, and the signature is checked against the examples AWS publishes."
)

#: Why AWS S3 is not connected at start.
A_LEASE_NOBODY_RENEWS_IS_A_CREDENTIAL_THAT_STOPS_WORKING_ON_A_SCHEDULE: Final = (
    "AWS S3's credential comes from a dynamic engine as a lease with an expiry, and this client "
    "is built once and held for the life of the process. Nothing here renews a lease, so a client "
    "built from one would work until the lease ran out and then refuse every request with a "
    "message about the key. It is not built, and the screens say why."
)

#: Why usage is a method of the backend and returns no names.
A_COUNT_IS_TAKEN_BESIDE_THE_NAMES: Final = (
    "No S3 call says how much a bucket holds, so a count is a listing and a listing is names. "
    "The names stay inside the client that fetched them and only the two figures leave, with a "
    "flag saying whether counting stopped at the ceiling, because a floor drawn as a total is "
    "the one reading worse than no figure."
)

#: Why the backup bucket reader filters before it fetches.
A_READER_OF_THE_BACKUP_BUCKET_NEVER_FETCHES_A_COPY: Final = (
    "The backup bucket holds the copies and their descriptions side by side, and a copy is the "
    "whole database. The recovery screen needs the descriptions, so only objects whose names end "
    "in a manifest's or a drill record's suffix are fetched; fetching everything to find them "
    "would pull every nightly copy into the web process each time the screen is opened."
)

# ------------------------------------------------------------ what is not connected, in words

#: With no vault named, there is nowhere a store credential could come from.
NO_VAULT_SO_NO_STORE_CREDENTIAL: Final = (
    "This install names no secrets vault, and the object store's key is kept only in one, so "
    "nothing here connects to the store. Set the vault's address and token, and put the store's "
    "access key id and secret access key in its slot."
)

#: A slot that has never been written.
THE_STORE_SLOT_HOLDS_NO_KEY: Final = (
    "The vault holds no key for the object store in its slot, so nothing here connects to the "
    "store. Put the store's access key id and secret access key in the slot the install guide "
    "names for this backend."
)

#: A slot written with something other than the two fields.
THE_STORE_SLOT_IS_NOT_A_KEY_PAIR: Final = (
    "The vault's slot for the object store does not hold both an access_key_id and a "
    "secret_access_key, so nothing here connects to the store."
)

#: The vault refused or did not answer.
THE_VAULT_DID_NOT_HAND_OVER_THE_STORE_KEY: Final = (
    "The vault did not hand over the object store's key when this process started, because it "
    "refused or did not answer, so nothing here connects to the store. The application log says "
    "which; the key is read again when the application restarts."
)

#: The backend setting names nothing this release supports.
THE_BACKEND_SETTING_NAMES_NO_BACKEND: Final = (
    "The object store backend this install is set to is not one this release can reach, so "
    "nothing here connects to the store. It is one of: "
    + ", ".join(one.value for one in Backend)
    + "."
)

#: The address, region or prefix is refused before anything is asked.
THE_STORE_SETTINGS_ARE_REFUSED: Final = (
    "The object store's address or prefix is not one a request can be built from, so nothing here "
    "connects to the store. The address is an http or https URL and the prefix is one word of "
    "letters, digits, dots, hyphens and underscores."
)

# ----------------------------------------------------------------------- the figures

#: The installation settings read at start. The first two are declared in `brain.install` and
#: were already read by the Storage screen; the third is the one this module added.
ENDPOINT_SETTING: Final = "INSTALL_OBJECT_STORE_URL"
PREFIX_SETTING: Final = "INSTALL_OBJECT_STORE_PREFIX"
BACKEND_SETTING: Final = "INSTALL_OBJECT_STORE_BACKEND"

#: The two fields a store slot holds.
ACCESS_KEY_FIELD: Final = "access_key_id"
SECRET_KEY_FIELD: Final = "secret_access_key"  # noqa: S105  a field name, never a value

#: How long a request to the store may take. The store is on the container network for the
#: default backend, so a slow answer is a store that is down, and a screen is waiting on it.
TIMEOUT_SECONDS: Final = 10.0

#: Objects asked for per page, which is S3's own maximum.
LIST_PAGE: Final = 1000

#: How many objects `usage` counts before it stops and says the figure is a floor. Ten pages.
USAGE_CEILING_OBJECTS: Final = 10 * LIST_PAGE

#: The signing algorithm, and the service name signed into the scope.
ALGORITHM: Final = "AWS4-HMAC-SHA256"
SERVICE: Final = "s3"

#: Where `ops/backup/brain-backup` writes its copies and manifests inside the backup bucket: the
#: root. A fact about the taker, read here so the reader and the writer agree.
BACKUP_KEY_PREFIX: Final = ""

#: What a prefix may be: one path segment, so a key built under it cannot climb out of it.
PREFIX_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


# ------------------------------------------------------------------------ signing


@dataclass(frozen=True)
class StoreCredential:
    """One static key pair for the store. The secret is never rendered by `repr`."""

    access_key_id: str
    secret_access_key: str = field(repr=False)

    def __post_init__(self) -> None:
        for name, value in (
            (ACCESS_KEY_FIELD, self.access_key_id),
            (SECRET_KEY_FIELD, self.secret_access_key),
        ):
            if not value or value != value.strip() or any(ch.isspace() for ch in value):
                msg = f"a store credential's {name} is empty or holds whitespace"
                raise StorageError(msg)


def _uri_encode(value: str, *, keep_slash: bool) -> str:
    """S3's encoding: every byte but the unreserved characters, and the slash only in a path."""
    return quote(value, safe="-_.~/" if keep_slash else "-_.~")


def canonical_query(query: Sequence[tuple[str, str]]) -> str:
    """The query as it is signed and as it is sent: each side encoded, sorted, `key=value`."""
    pairs = sorted(
        (_uri_encode(name, keep_slash=False), _uri_encode(value, keep_slash=False))
        for name, value in query
    )
    return "&".join(f"{name}={value}" for name, value in pairs)


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def authorization(
    *,
    method: str,
    path: str,
    query: Sequence[tuple[str, str]],
    headers: Mapping[str, str],
    payload_sha256: str,
    credential: StoreCredential,
    region: str,
    at: datetime,
) -> str:
    """The `Authorization` header for one request, signed with AWS Signature Version 4.

    Every header handed in is signed, so the caller decides what is covered and cannot send a
    signed header this did not see. `at` must carry a timezone and is rendered in UTC; it has to be
    the instant in the request's `x-amz-date`, which the caller also sets from it.
    """
    if at.tzinfo is None:
        msg = "a request signed at a naive instant is signed at whatever offset the host is at"
        raise StorageError(msg)
    stamp = at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    day = stamp[:8]
    folded = {name.lower(): " ".join(value.strip().split()) for name, value in headers.items()}
    names = sorted(folded)
    signed = ";".join(names)
    canonical = "\n".join(
        (
            method,
            _uri_encode(path, keep_slash=True),
            canonical_query(query),
            "".join(f"{name}:{folded[name]}\n" for name in names),
            signed,
            payload_sha256,
        )
    )
    scope = f"{day}/{region}/{SERVICE}/aws4_request"
    to_sign = "\n".join(
        (ALGORITHM, stamp, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    )
    key = _hmac(f"AWS4{credential.secret_access_key}".encode(), day)
    for part in (region, SERVICE, "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return (
        f"{ALGORITHM} Credential={credential.access_key_id}/{scope}, "
        f"SignedHeaders={signed}, Signature={signature}"
    )


def _stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _local(tag: str) -> str:
    """An XML tag without its namespace, whichever one the store wrote or none.

    Stripped rather than matched against S3's own namespace, because a compatible store that
    omits it or spells it differently is still answering the same question.
    """
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ElementTree.Element, name: str) -> str:
    for child in element:
        if _local(child.tag) == name:
            return child.text or ""
    return ""


def _now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------------ the client


class S3Backend:
    """`StorageBackend` over the S3 API, for SeaweedFS's gateway, R2 or any compatible store."""

    def __init__(
        self,
        config: BackendConfig,
        credential: StoreCredential,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        parts = urlsplit(config.endpoint_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            msg = "the store's endpoint is not an http or https address"
            raise StorageError(msg)
        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        # Host and port only. `config_for` accepts any URL, and one written with a user name and
        # password in it would otherwise put them in every Host header this client sends.
        self._scheme = parts.scheme
        self._netloc = host if parts.port is None else f"{host}:{parts.port}"
        self._config = config
        self._credential = credential
        self._clock = clock
        self._client = httpx.Client(
            transport=transport, timeout=TIMEOUT_SECONDS, follow_redirects=False
        )

    def __repr__(self) -> str:
        return f"S3Backend(backend={self._config.backend.value!r}, host={self._netloc!r})"

    __str__ = __repr__

    def close(self) -> None:
        self._client.close()

    def _where(self, bucket_name: str, key: str) -> tuple[str, str]:
        """The host and the path a request for this bucket and key goes to."""
        if self._config.addressing is Addressing.VIRTUAL_HOST:
            return f"{bucket_name}.{self._netloc}", f"/{key}"
        return self._netloc, f"/{bucket_name}/{key}" if key else f"/{bucket_name}"

    def _send(
        self,
        method: str,
        bucket_name: str,
        key: str = "",
        *,
        query: Sequence[tuple[str, str]] = (),
        body: bytes = b"",
        content_type: str = "",
    ) -> httpx.Response:
        at = self._clock()
        host, path = self._where(bucket_name, key)
        payload = hashlib.sha256(body).hexdigest()
        headers = {"host": host, "x-amz-content-sha256": payload, "x-amz-date": _stamp(at)}
        if content_type:
            headers["content-type"] = content_type
        headers["authorization"] = authorization(
            method=method,
            path=path,
            query=query,
            headers=headers,
            payload_sha256=payload,
            credential=self._credential,
            region=self._config.region,
            at=at,
        )
        encoded = canonical_query(query)
        url = f"{self._scheme}://{host}{_uri_encode(path, keep_slash=True)}"
        try:
            response = self._client.request(
                method,
                f"{url}?{encoded}" if encoded else url,
                headers=headers,
                content=body if method == "PUT" else None,
            )
        except httpx.HTTPError as exc:
            msg = (
                f"the object store did not answer {method} in bucket {bucket_name!r} "
                f"({type(exc).__name__})"
            )
            raise StoreUnansweredError(msg) from exc
        if response.is_success:
            return response
        msg = (
            f"the object store answered {response.status_code} ({_error_code(response)}) to "
            f"{method} in bucket {bucket_name!r}"
        )
        raise StoreUnansweredError(msg)

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self._send("PUT", bucket_name, key, body=body, content_type=content_type)

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self._send("GET", bucket_name, key).content

    def delete_object(self, bucket_name: str, key: str) -> None:
        self._send("DELETE", bucket_name, key)

    def _pages(self, bucket_name: str, prefix: str) -> Iterator[tuple[list[tuple[str, int]], bool]]:
        """Each page of a listing as names with sizes, and whether another page follows."""
        token = ""
        while True:
            query = [("list-type", "2"), ("max-keys", str(LIST_PAGE)), ("prefix", prefix)]
            if token:
                query.append(("continuation-token", token))
            response = self._send("GET", bucket_name, query=query)
            try:
                root = ElementTree.fromstring(response.content)  # noqa: S314  the configured store's own answer; ElementTree resolves no external entity
            except ElementTree.ParseError as exc:
                msg = f"the object store's listing of bucket {bucket_name!r} is not XML"
                raise StoreUnansweredError(msg) from exc
            page: list[tuple[str, int]] = []
            for element in root:
                if _local(element.tag) != "Contents":
                    continue
                size = _child_text(element, "Size")
                if not size.isdigit():
                    msg = f"the object store listed an object in {bucket_name!r} with no size"
                    raise StoreUnansweredError(msg)
                page.append((_child_text(element, "Key"), int(size)))
            token = _child_text(root, "NextContinuationToken")
            more = _child_text(root, "IsTruncated") == "true" and bool(token)
            yield page, more
            if not more:
                return

    def list_objects(self, bucket_name: str, prefix: str) -> Iterator[str]:
        for page, _ in self._pages(bucket_name, prefix):
            yield from (name for name, _ in page)

    def usage(self, bucket_name: str, prefix: str) -> BucketUsage:
        """What the bucket holds under the prefix, stopping at `USAGE_CEILING_OBJECTS`.

        See `A_COUNT_IS_TAKEN_BESIDE_THE_NAMES`. The names are read off each page and dropped
        there; only the running figures cross this method's boundary.
        """
        objects = size = 0
        for page, more in self._pages(bucket_name, prefix):
            objects += len(page)
            size += sum(bytes_ for _, bytes_ in page)
            if more and objects >= USAGE_CEILING_OBJECTS:
                return BucketUsage(objects=objects, bytes_stored=size, complete=False)
        return BucketUsage(objects=objects, bytes_stored=size, complete=True)


def _error_code(response: httpx.Response) -> str:
    """The S3 error code out of a refusal, or the status's own phrase. Never the message."""
    try:
        root = ElementTree.fromstring(response.content)  # noqa: S314  as above
    except ElementTree.ParseError:
        return response.reason_phrase or "no code"
    return _child_text(root, "Code") or response.reason_phrase or "no code"


# ------------------------------------------------------------------ built at start


@dataclass(frozen=True)
class ObjectStore:
    """This process's object store: a client and the prefix its keys go under, or why neither.

    `backend` is the S3 client itself rather than one of the protocols it satisfies, because the
    holders of this value need two of them: the recovery screen and the artifact store put, get
    and list, and the Storage screen counts.

    Exactly one of `backend` and `unconnected` is set, refused at construction, for
    `brain.install_routes.RecoveryView`'s reason: a screen handed neither draws a blank that
    reads as a store with nothing in it.
    """

    backend: S3Backend | None
    prefix: str
    unconnected: str = ""

    def __post_init__(self) -> None:
        if (self.backend is None) == (not self.unconnected):
            msg = "an object store is connected or says why it is not, and never both or neither"
            raise StorageError(msg)


def unconnected(reason: str) -> ObjectStore:
    return ObjectStore(backend=None, prefix="", unconnected=reason)


class StaticKvReader(Protocol):
    """The one thing asked of the vault here: a slot's fields, under the static prefix.

    `brain.ops.openbao.OpenBaoVault.read_static_kv`, whose prefix refusal is the reason this is a
    stored key rather than a borrowed one; see that method and `credential_path`.
    """

    def read_static_kv(self, path: str) -> dict[str, Any]: ...


def _application_vault(address: str, token: str) -> StaticKvReader:
    return OpenBaoVault(address, token, role=VaultRole.APPLICATION)


def object_store_at_start(
    vault_address: str,
    vault_token: str,
    *,
    env: Mapping[str, str] | None = None,
    saved: Mapping[str, str] | None = None,
    make_vault: Callable[[str, str], StaticKvReader] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ObjectStore:
    """The store this process talks to, or the sentence saying why it talks to none.

    Never raises, for `brain.ops.credentials.credentials_at_start`'s reason. The settings first,
    so a refused address is reported without asking the vault for a key it would not use, and the
    backend's credential kind among them, because a leased one is not built at all whatever else
    is set; then the vault.
    """
    try:
        chosen = value_of(BACKEND_SETTING, env=env, saved=saved)
        endpoint = value_of(ENDPOINT_SETTING, env=env, saved=saved)
        prefix = value_of(PREFIX_SETTING, env=env, saved=saved)
    except InstallError:
        return unconnected(THE_STORE_SETTINGS_ARE_REFUSED)
    try:
        backend = Backend(chosen)
    except ValueError:
        log.warning("object store backend not recognised", setting=BACKEND_SETTING)
        return unconnected(THE_BACKEND_SETTING_NAMES_NO_BACKEND)
    if credential_path(backend).startswith(DYNAMIC_MOUNTS):
        return unconnected(A_LEASE_NOBODY_RENEWS_IS_A_CREDENTIAL_THAT_STOPS_WORKING_ON_A_SCHEDULE)
    if not PREFIX_PATTERN.fullmatch(prefix):
        return unconnected(THE_STORE_SETTINGS_ARE_REFUSED)
    try:
        config = config_for(backend, endpoint_url=endpoint)
    except StorageError:
        return unconnected(THE_STORE_SETTINGS_ARE_REFUSED)
    if not vault_address or not vault_token:
        return unconnected(NO_VAULT_SO_NO_STORE_CREDENTIAL)
    build = make_vault if make_vault is not None else _application_vault
    try:
        fields = build(vault_address, vault_token).read_static_kv(config.credential_path)
    except VaultRefusedError as refused:
        if refused.status == 404:
            return unconnected(THE_STORE_SLOT_HOLDS_NO_KEY)
        log.warning("vault refused the object store key", status=refused.status)
        return unconnected(THE_VAULT_DID_NOT_HAND_OVER_THE_STORE_KEY)
    except VaultUnreachableError:
        log.warning("vault did not answer for the object store key")
        return unconnected(THE_VAULT_DID_NOT_HAND_OVER_THE_STORE_KEY)
    except (SecretsUnavailableError, ValueError) as exc:
        log.warning("object store key not read", error=type(exc).__name__)
        return unconnected(THE_VAULT_DID_NOT_HAND_OVER_THE_STORE_KEY)
    if not fields:
        return unconnected(THE_STORE_SLOT_HOLDS_NO_KEY)
    access, secret = fields.get(ACCESS_KEY_FIELD), fields.get(SECRET_KEY_FIELD)
    if not isinstance(access, str) or not isinstance(secret, str):
        return unconnected(THE_STORE_SLOT_IS_NOT_A_KEY_PAIR)
    try:
        credential = StoreCredential(access_key_id=access, secret_access_key=secret)
    except StorageError:
        return unconnected(THE_STORE_SLOT_IS_NOT_A_KEY_PAIR)
    made = S3Backend(config, credential, transport=transport)
    log.info("object store connected", backend=backend.value, store=repr(made), prefix=prefix)
    return ObjectStore(backend=made, prefix=prefix)


# ------------------------------------------------------------------ the backup bucket


def key_prefix(bucket_name: str, prefix: str) -> str:
    """Where this install's objects are inside a bucket: under its prefix, or the backup root.

    One function for the writer and the counter, so an object this install put somewhere is
    counted where it was put. The backup bucket is the exception because its writer is
    `ops/backup/brain-backup`, which writes at the root; see `BACKUP_KEY_PREFIX`.
    """
    if bucket_name == bucket_for(ObjectKind.DATABASE_DUMP).name:
        return BACKUP_KEY_PREFIX
    return f"{prefix}/"


def backup_objects(backend: StorageBackend) -> Callable[[], tuple[tuple[str, str], ...]]:
    """A reader of the backup bucket in the shape `brain.install_routes.BackupObjects` names.

    Only manifests and drill records are fetched; see
    `A_READER_OF_THE_BACKUP_BUCKET_NEVER_FETCHES_A_COPY`. Bytes that are not UTF-8 are passed on
    with the fault replaced rather than skipped, so `read_manifests` reports the file as
    unreadable, which is `brain.ops.backup_manifest`'s rule that an unreadable manifest is the one
    most likely to matter.
    """
    bucket_name = bucket_for(ObjectKind.DATABASE_DUMP).name

    def read() -> tuple[tuple[str, str], ...]:
        return tuple(
            (key, backend.get_object(bucket_name, key).decode("utf-8", errors="replace"))
            for key in backend.list_objects(bucket_name, BACKUP_KEY_PREFIX)
            if key.endswith((MANIFEST_SUFFIX, DRILL_SUFFIX))
        )

    return read
