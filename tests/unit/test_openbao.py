"""Issuing and revoking a lease against OpenBao. Every test is a way a credential outlives
the run that borrowed it, or a way a secret reaches somewhere it should not.

No real vault is contacted. The HTTP call is replaced at the one seam that makes it, so
these test what this module does with an answer rather than testing that OpenBao works.

Task ids: M31.3.2.3, M31.3.2.4, M27.8.7
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import Message
from typing import Any

import pytest

from brain.ops.openbao import (
    OpenBaoVault,
    SealStatus,
    VaultRefusedError,
    VaultUnreachableError,
    _instant,
)
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole, borrow

REF = SecretRef(path="database/creds/xero-reader", role=VaultRole.APPLICATION)


class FakeVault(OpenBaoVault):
    """The real class with its one network call replaced.

    A subclass rather than an assignment to `_call` on an instance: the override is then a
    normal method with a normal signature, so a change to the real one's arguments breaks
    this at type-check time instead of at run time in one test.
    """

    def __init__(
        self,
        responses: list[dict[str, Any]] | dict[str, Any] | None = None,
        *,
        fail: Exception | None = None,
    ) -> None:
        super().__init__("http://vault:8200", "a-token")
        self.calls: list[tuple[str, str]] = []
        self._queue = list(responses) if isinstance(responses, list) else [responses or {}]
        self._fail = fail

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path))
        if self._fail is not None:
            raise self._fail
        return self._queue.pop(0) if self._queue else {}


def _good_response(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "lease_id": "database/creds/xero-reader/abc123",
        "lease_duration": 3600,
        "data": {"username": "v-token-xero-9f", "password": "A1-secret-value"},
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------- construction
def test_a_vault_with_no_token_is_refused_at_construction() -> None:
    """An empty token produces a 403 on the first credential request, which reads as a
    policy problem and sends somebody to look at the wrong file. Refusing here says what is
    actually wrong."""
    with pytest.raises(ValueError, match="no vault token"):
        OpenBaoVault("http://vault:8200", "")


def test_an_address_that_is_not_a_url_is_refused() -> None:
    with pytest.raises(ValueError, match="not a URL"):
        OpenBaoVault("vault:8200", "a-token")


def test_the_token_never_appears_in_the_repr() -> None:
    """The commonest way a credential reaches a log is an exception handler formatting the
    object that was holding it. `Lease` overrides its repr for the same reason; this is the
    other object in the path that holds one."""
    text = repr(OpenBaoVault("http://vault:8200", "s.SUPERSECRETTOKEN"))
    assert "SUPERSECRET" not in text
    assert "vault:8200" in text


# --------------------------------------------------------------------- issuing
def test_a_lease_carries_the_credential_and_an_expiry() -> None:
    """The happy path. If this fails nothing else here is testing a vault that works."""
    v = FakeVault(_good_response())
    lease = v.issue(REF, timedelta(minutes=30))
    assert lease.lease_id == "database/creds/xero-reader/abc123"
    assert lease.expires_at - lease.issued_at == timedelta(hours=1)


def test_the_expiry_comes_from_the_vault_and_not_from_what_we_asked_for() -> None:
    """The two differ whenever the mount's maximum is shorter than the request. Taking our
    own number means the application believes it holds a working credential after the server
    has already withdrawn it, and credentials then fail while the code is certain they
    should not.

    Asked for thirty minutes, told five. Five wins."""
    v = FakeVault(_good_response(lease_duration=300))
    lease = v.issue(REF, timedelta(minutes=30))
    assert lease.expires_at - lease.issued_at == timedelta(minutes=5)


def test_a_static_engine_is_refused_before_the_call_is_made() -> None:
    """`kv` stores a value you wrote and returns it forever. A lease over that is a promise
    nothing keeps: the caller believes the credential stops working and it does not.

    Refused before the request, so a misconfigured connector cannot even read the value."""
    v = FakeVault(_good_response())
    with pytest.raises(SecretsUnavailableError, match="not a dynamic engine"):
        v.issue(SecretRef(path="secret/data/xero", role=VaultRole.APPLICATION), timedelta(hours=1))
    assert v.calls == [], "a static path was fetched before being refused"


def test_a_response_with_no_lease_id_is_refused() -> None:
    """A credential that cannot be revoked is a credential that lives until it expires on
    its own, whatever the run does. That is what a static engine looks like from here even
    when it is mounted under a dynamic-sounding path."""
    v = FakeVault(_good_response(lease_id=""))
    with pytest.raises(SecretsUnavailableError, match="no lease id"):
        v.issue(REF, timedelta(hours=1))


def test_a_response_with_no_duration_is_refused_rather_than_given_a_default() -> None:
    """An invented expiry is worse than no expiry: the caller believes the credential stops
    working at a time nothing enforces. Deleting this makes the safest-looking failure mode
    the most dangerous one."""
    v = FakeVault(_good_response(lease_duration=None))
    with pytest.raises(SecretsUnavailableError, match="refusing to invent"):
        v.issue(REF, timedelta(hours=1))


@pytest.mark.parametrize("duration", [0, -1])
def test_a_duration_of_zero_or_less_is_refused_as_a_secrets_problem(duration: int) -> None:
    """Not left to blow up further in. Without this guard a zero reaches `Lease`, which
    refuses it with a `ValueError` - a real error, but the wrong type: every caller here
    catches `SecretsUnavailableError`, so the one that does not is the one that crashes the
    request instead of degrading it.

    Found by mutation. The `is not an int` half of the check was tested and the `<= 0` half
    was not, and the two fail differently."""
    v = FakeVault(_good_response(lease_duration=duration))
    with pytest.raises(SecretsUnavailableError, match="refusing to invent"):
        v.issue(REF, timedelta(hours=1))


def test_a_username_and_password_pair_becomes_one_secret() -> None:
    """`Lease.secret` is one string. Widening it to a mapping would mean every caller
    decides which field is the secret, and the one that picks wrong picks the username -
    which is not secret, and logs it."""
    v = FakeVault(_good_response())
    lease = v.issue(REF, timedelta(hours=1))
    from datetime import UTC, datetime

    assert lease.reveal(datetime.now(UTC)) == "v-token-xero-9f:A1-secret-value"


def test_fields_this_does_not_recognise_are_refused() -> None:
    """Guessing which field is the credential is how the wrong string gets sent to a source
    as a password, producing an authentication error that looks like a permission problem."""
    v = FakeVault(_good_response(data={"something_else": "x"}))
    with pytest.raises(SecretsUnavailableError, match="does not recognise"):
        v.issue(REF, timedelta(hours=1))


# ---------------------------------------------------------------- what leaks
def test_an_http_error_never_quotes_the_path_that_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenBao's error bodies quote the path, and a path names which credential was being
    borrowed. That is exactly the fact the audit log takes care to hash, so repeating it in
    an exception message - which ends up in a log, a trace and possibly a response - would
    undo that at the first failure."""
    import urllib.error

    def boom(*_a: object, **_k: object) -> None:
        # Built the way urllib really builds one, with the URL in it, because that URL is
        # precisely what must not survive into the message.
        raise urllib.error.HTTPError(
            "http://vault:8200/v1/database/creds/xero-reader", 403, "Forbidden", Message(), None
        )

    monkeypatch.setattr("urllib.request.urlopen", boom)
    v = OpenBaoVault("http://vault:8200", "a-token")
    with pytest.raises(SecretsUnavailableError) as caught:
        v.issue(REF, timedelta(hours=1))

    message = str(caught.value)
    assert "xero-reader" not in message
    assert "creds" not in message
    assert "database" in message, "the engine is named, so the message is still useful"


# --------------------------------------------------------------- revoking
def test_a_revocation_is_retried() -> None:
    """A failed revocation leaves a live credential. One network blip must not turn into a
    key that outlives the run that borrowed it."""

    class Flaky(FakeVault):
        """Fails twice, then works. The shape of a real network blip."""

        def _call(
            self, method: str, path: str, body: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            self.calls.append((method, path))
            if len(self.calls) < 3:
                raise SecretsUnavailableError("blip")
            return {}

    v = Flaky()
    v.revoke("some/lease/id")
    assert len(v.calls) == 3


def test_a_revocation_that_never_succeeds_raises() -> None:
    """Swallowing it would leave a live credential and a clean log, which is the pairing
    that makes this class of bug survive for months."""
    v = FakeVault(fail=SecretsUnavailableError("gone"))
    with pytest.raises(SecretsUnavailableError):
        v.revoke("some/lease/id")


def test_issuing_is_not_retried() -> None:
    """Deliberately different from revoking. A credential request that failed may still have
    minted something on the far side, and the id needed to revoke it came back only on the
    response that never arrived - so a retry can leave orphaned credentials nobody will ever
    give back."""
    v = FakeVault(fail=SecretsUnavailableError("blip"))
    with pytest.raises(SecretsUnavailableError):
        v.issue(REF, timedelta(hours=1))
    assert len(v.calls) == 1


def test_borrowing_revokes_even_when_the_body_raises() -> None:
    """The property the whole module exists for, exercised through the real context manager
    rather than asserted about it. A credential that outlives its run is a credential nobody
    is watching."""
    from datetime import UTC, datetime

    v = FakeVault([_good_response(), {}])
    with pytest.raises(RuntimeError), borrow(v, REF, now=datetime.now(UTC), ttl=timedelta(hours=1)):
        raise RuntimeError("the work failed")
    methods = [m for m, _ in v.calls]
    assert methods == ["GET", "PUT"], v.calls


# ------------------------------------------------- writing a slot, and reading its metadata
KEY = "sk-OPENBAO-SENTINEL-0123456789"


class Recording(OpenBaoVault):
    """The real class with its one network call replaced, keeping every body it was handed.

    A second fake beside `FakeVault` because a write's body is the thing under test and
    `FakeVault` records a method and a path. Answers are keyed by path, and a path with no
    answer raises what `fail` says, so a test states exactly what the vault would do.
    """

    def __init__(
        self, answers: dict[str, dict[str, Any]] | None = None, *, fail: Exception | None = None
    ) -> None:
        super().__init__("http://vault:8200", "a-token")
        self.sent: list[tuple[str, str, dict[str, Any] | None]] = []
        self._answers = answers or {}
        self._fail = fail

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.sent.append((method, path, body))
        if path in self._answers:
            return self._answers[path]
        if self._fail is not None:
            raise self._fail
        return {}


def _metadata(current: int, versions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """kv v2's metadata answer, with the versions keyed by their number as strings."""
    return {"data": {"current_version": current, "versions": versions}}


def test_a_write_goes_to_the_kv_data_path_wrapped_once_and_answers_the_version_time() -> None:
    """kv version 2 takes a write on `<mount>/data/<rest>` with the fields under `data`, which is
    the shape `read_static_kv` unwraps. A write to the logical path is a 404 that reads as a
    missing engine, and fields not wrapped are stored one level off, which start-up then reads as
    a slot holding nothing it recognises.

    Delete this and either mistake ships, and the first install to set a key from the console
    finds it gone after its next restart."""
    stamped = "2026-09-16T08:30:05.123456789Z"
    v = Recording({"providers/data/anthropic": {"data": {"created_time": stamped, "version": 3}}})

    written = v.write_static_kv("providers/anthropic", {"api_key": KEY})

    assert v.sent == [("POST", "providers/data/anthropic", {"data": {"api_key": KEY}})]
    assert written == datetime(2026, 9, 16, 8, 30, 5, 123456, tzinfo=UTC)


def test_a_write_outside_the_provider_prefix_is_refused_before_anything_is_sent() -> None:
    """The write has the read's refusal, on the same object. A writer that could put a value at
    `connectors/creds/xero` would be storing a standing credential over a path the leasing design
    says the vault mints per run. Delete this and the one guard that keeps the new write narrow is
    gone, with every provider test still green."""
    v = Recording()
    with pytest.raises(SecretsUnavailableError, match="leased"):
        v.write_static_kv("connectors/creds/xero", {"api_key": KEY})
    assert v.sent == []


@pytest.mark.parametrize(
    "answer", [{}, {"data": "not a mapping"}, {"data": {"created_time": "yesterday"}}]
)
def test_a_write_the_vault_accepted_without_a_readable_time_still_returns(
    answer: dict[str, Any],
) -> None:
    """The value is already written when the answer is read, so an answer with no time, or one
    that does not parse, is None rather than an exception. Delete this and a key that is held is
    reported as a failed write, and the person pastes it again into a second version."""
    v = Recording({"providers/data/openai": answer})
    assert v.write_static_kv("providers/openai", {"api_key": KEY}) is None


def test_a_slot_s_metadata_says_when_its_current_version_was_written() -> None:
    """The positive case the refusals below need. Two versions, and the current one is the second:
    a reader taking the first would report when the old key was set.

    Delete this and `static_kv_version` can answer for every slot from a metadata shape nobody
    checked, which is the only way the console can say a key is held."""
    versions = {
        "1": {"created_time": "2026-01-01T00:00:00Z", "deletion_time": ""},
        "2": {"created_time": "2026-09-16T09:00:00Z", "deletion_time": ""},
    }
    v = Recording({"providers/metadata/anthropic": _metadata(2, versions)})

    version = v.static_kv_version("providers/anthropic")

    assert v.sent == [("GET", "providers/metadata/anthropic", None)]
    assert version is not None
    assert version.written_at == datetime(2026, 9, 16, 9, 0, tzinfo=UTC)


def test_a_slot_never_written_holds_nothing_and_any_other_refusal_is_raised() -> None:
    """A kv slot nobody wrote answers 404, which is an empty slot and not a failure. Anything else
    is a failure: 403 is a token or a policy, and reading it as "not held" would send somebody to
    paste a key into a vault that will refuse it again. Both directions, so neither half can be
    satisfied by treating every refusal the same way."""
    empty = Recording(fail=VaultRefusedError("vault refused GET", status=404))
    forbidden = Recording(fail=VaultRefusedError("vault refused GET", status=403))

    assert empty.static_kv_version("providers/moonshot") is None
    with pytest.raises(VaultRefusedError) as refused:
        forbidden.static_kv_version("providers/moonshot")
    assert refused.value.status == 403


@pytest.mark.parametrize("gone", [{"deletion_time": "2026-09-01T00:00:00Z"}, {"destroyed": True}])
def test_a_deleted_or_destroyed_current_version_is_not_a_held_key(gone: dict[str, Any]) -> None:
    """kv keeps a deleted version's metadata. A console that said such a slot was held would be
    reporting a key nothing can read, and the provider calls would fail as unauthenticated with
    the screen saying all is well. Delete this and that is what a deleted key looks like."""
    held = {"created_time": "2026-08-01T00:00:00Z", "deletion_time": "", "destroyed": False}
    v = Recording({"providers/metadata/openai": _metadata(1, {"1": {**held, **gone}})})
    assert v.static_kv_version("providers/openai") is None


def test_a_current_version_whose_time_does_not_parse_is_still_held() -> None:
    """Held with no time, rather than not held. Saying a written key is absent would send
    somebody to write it again. Delete this and an unparseable stamp becomes a missing key."""
    v = Recording({"providers/metadata/openai": _metadata(1, {"1": {"created_time": "soon"}})})
    version = v.static_kv_version("providers/openai")
    assert version is not None
    assert version.written_at is None


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"data": "not a mapping"},
        {"data": {"current_version": 1}},
        _metadata(2, {"1": {"created_time": "2026-01-01T00:00:00Z"}}),
        {"data": {"current_version": 1, "versions": {"1": "not a mapping"}}},
    ],
)
def test_metadata_this_does_not_recognise_holds_nothing(answer: dict[str, Any]) -> None:
    """A shape with no current version this can find is not a held key. Each row removes one thing
    the positive test relies on, so a reader that skipped a check still answers None for the right
    reason. Delete this and a malformed answer raises inside a console read."""
    v = Recording({"providers/metadata/openai": answer})
    assert v.static_kv_version("providers/openai") is None


def test_reading_metadata_outside_the_provider_prefix_is_refused_before_anything_is_sent() -> None:
    """The metadata read carries the prefix refusal too, so it cannot become a way to learn which
    connector credentials exist. Delete this and the one method the console calls on every visit
    can be pointed anywhere in the vault."""
    v = Recording()
    with pytest.raises(SecretsUnavailableError, match="leased"):
        v.static_kv_version("connectors/creds/xero")
    assert v.sent == []


def test_a_refusal_and_a_silence_are_two_types_and_both_still_a_secrets_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What a person is told to do differs: a silent vault is sealed, stopped or unreachable, and
    a refusing one is a token, a policy or an engine. Both stay `SecretsUnavailableError`, so every
    handler written before the split still catches them. Delete this and the split can collapse
    back into one type with every existing test green."""
    import urllib.error

    def refused(*_a: object, **_k: object) -> None:
        raise urllib.error.HTTPError(
            "http://vault:8200/v1/providers/data/anthropic", 403, "Forbidden", Message(), None
        )

    def silent(*_a: object, **_k: object) -> None:
        raise urllib.error.URLError("connection refused")

    v = OpenBaoVault("http://vault:8200", "a-token")
    monkeypatch.setattr("urllib.request.urlopen", refused)
    with pytest.raises(VaultRefusedError) as no:
        v.write_static_kv("providers/anthropic", {"api_key": KEY})
    monkeypatch.setattr("urllib.request.urlopen", silent)
    with pytest.raises(VaultUnreachableError) as nothing:
        v.write_static_kv("providers/anthropic", {"api_key": KEY})

    assert no.value.status == 403
    assert isinstance(no.value, SecretsUnavailableError)
    assert isinstance(nothing.value, SecretsUnavailableError)
    assert not isinstance(nothing.value, VaultRefusedError)
    assert KEY not in f"{no.value} {nothing.value}"


def test_a_vault_time_is_read_with_its_zone_and_anything_else_is_none() -> None:
    """kv stamps nanoseconds and a `Z`. A time with no zone is read as UTC rather than as the
    server's local time, and anything that is not a time is None. Delete this and a stamp read as
    naive compares wrongly against every aware time in the system."""
    assert _instant("2026-09-16T08:30:05.123456789Z") == datetime(
        2026, 9, 16, 8, 30, 5, 123456, tzinfo=UTC
    )
    assert _instant("2026-09-16T08:30:05") == datetime(2026, 9, 16, 8, 30, 5, tzinfo=UTC)
    assert _instant("2026-09-16T08:30:05+08:00") == datetime(2026, 9, 16, 0, 30, 5, tzinfo=UTC)
    assert [_instant(None), _instant(""), _instant(20260916), _instant("soon")] == [None] * 4


# ------------------------------------------------ a run token, the seal, a defined slot (M31.3.2.4)
RUN_TOKEN = "s.RUN-TOKEN-SENTINEL-77c1"


def _minted(**overrides: Any) -> dict[str, Any]:
    auth: dict[str, Any] = {
        "client_token": RUN_TOKEN,
        "accessor": "accessor-of-the-run-token",
        "lease_duration": 900,
        "renewable": False,
        "policies": ["connector-run"],
    }
    auth.update(overrides)
    return {"auth": auth}


def test_a_run_token_is_asked_for_with_its_ttl_no_renewal_and_no_default_policy() -> None:
    """The request fixes the lease's shape, and the answer is sealed so no rendering prints it.
    Delete this and a run token can be minted renewable, or carry the default policy, and the
    token's value reaches a traceback through the dataclass's repr."""
    v = Recording({"auth/token/create/connector-run": _minted()})

    minted = v.mint_role_token(
        "connector-run", ttl=timedelta(minutes=15), meta={"connector": "xero"}
    )

    assert v.sent == [
        (
            "POST",
            "auth/token/create/connector-run",
            {
                "ttl": "900s",
                "explicit_max_ttl": "900s",
                "renewable": False,
                "no_default_policy": True,
                "meta": {"connector": "xero"},
            },
        )
    ]
    assert (minted.lease_seconds, minted.renewable, minted.policies) == (
        900,
        False,
        ("connector-run",),
    )
    assert minted.token.reveal() == RUN_TOKEN
    assert RUN_TOKEN not in f"{minted!r} {minted}"


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"auth": None},
        _minted(client_token=""),
        _minted(lease_duration=0),
        _minted(lease_duration=None),
        _minted(renewable="no"),
        _minted(policies="connector-run"),
    ],
)
def test_a_run_token_answer_missing_its_token_duration_or_policies_is_refused(
    answer: dict[str, Any],
) -> None:
    """A lease whose end this process cannot state is not a lease. Delete this and a token with no
    stated TTL is used as if it had the one asked for."""
    v = Recording({"auth/token/create/connector-run": answer})
    with pytest.raises(SecretsUnavailableError) as raised:
        v.mint_role_token("connector-run", ttl=timedelta(minutes=15), meta={})
    assert RUN_TOKEN not in str(raised.value)


def test_holding_presents_the_run_token_and_revoke_self_gives_it_back() -> None:
    """The child client presents the minted token, not the worker's; revoking is a POST to
    revoke-self, retried through a silence and raised at once on a refusal. Delete this and the
    worker revokes its own token at the end of every run, or never revokes the run's."""
    v = Recording({"auth/token/create/connector-run": _minted()})
    held = v.holding(v.mint_role_token("connector-run", ttl=timedelta(minutes=15), meta={}))
    assert held._token == RUN_TOKEN  # the one attribute the request header is built from

    class Flaky(OpenBaoVault):
        def __init__(self, failures: list[Exception]) -> None:
            super().__init__("http://vault:8200", RUN_TOKEN)
            self.calls: list[str] = []
            self._failures = failures

        def _call(
            self, method: str, path: str, body: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            self.calls.append(path)
            if self._failures:
                raise self._failures.pop(0)
            return {}

    once_silent = Flaky([VaultUnreachableError("timeout")])
    once_silent.revoke_self()
    assert once_silent.calls == ["auth/token/revoke-self"] * 2

    refused = Flaky([VaultRefusedError("gone", status=403)])
    with pytest.raises(VaultRefusedError):
        refused.revoke_self()
    assert refused.calls == ["auth/token/revoke-self"]

    silent = Flaky([VaultUnreachableError("timeout")] * 3)
    with pytest.raises(VaultUnreachableError):
        silent.revoke_self()


def test_the_seal_is_read_as_two_booleans_and_anything_else_is_refused() -> None:
    """Delete this and a vault answering a proxy's HTML page reads as open and unsealed."""
    assert Recording({"sys/seal-status": {"initialized": True, "sealed": True}}).seal_status() == (
        SealStatus(initialized=True, sealed=True)
    )
    with pytest.raises(SecretsUnavailableError):
        Recording({"sys/seal-status": {"initialized": "yes", "sealed": False}}).seal_status()


def test_a_slot_the_installer_defined_is_told_from_one_that_does_not_exist() -> None:
    """Metadata that answers is a defined slot; a 404 is none; any other refusal is raised. Delete
    this and a missing installer step reads as a defined, empty slot."""
    defined = Recording({"connector_keys/metadata/xero": {"data": {"current_version": 0}}})
    assert defined.static_kv_defined("connector_keys/xero") is True
    assert defined.sent == [("GET", "connector_keys/metadata/xero", None)]
    missing = Recording(fail=VaultRefusedError("none", status=404))
    assert missing.static_kv_defined("connector_keys/xero") is False
    with pytest.raises(VaultRefusedError):
        Recording(fail=VaultRefusedError("no", status=403)).static_kv_defined("connector_keys/xero")
    with pytest.raises(SecretsUnavailableError):
        defined.static_kv_defined("database/creds/xero")
