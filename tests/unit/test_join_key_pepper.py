"""The join-key pepper: created once into a write-once slot, never replaced, never said, and the
value every join key is hashed with in both processes.

The vault is `PepperSlot`, one kv version 2 slot answering as OpenBao answers the application's
policy in `ops/openbao/policies/application.hcl`: read and create, and no update, so a write to a
slot that already holds a version is refused before the check-and-set is even read. What the
policy files grant is held in `tests/unit/test_vault_policies.py`, and that the release's vault
script never touches the slot in `tests/unit/test_vault_setup.py`; that `OpenBaoVault` sends the
check-and-set and refuses the ordinary write is held here against the real class with its one
network call replaced.

Task ids: M14.7.3
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import urllib.error
from collections.abc import Mapping
from email.message import Message
from typing import Any, Final

import pytest
from structlog.testing import capture_logs

from brain.deployment.installer import (
    PEPPER_COMMAND,
    PEPPER_HELD_FLAG,
    PLAN,
    step_named,
)
from brain.ops import join_key_pepper
from brain.ops.join_key_pepper import (
    HELD_FLAG,
    PEPPER_BYTES,
    PEPPER_CHARS,
    PEPPER_FIELD,
    PEPPER_SAYS,
    PEPPER_SLOT,
    PepperProblem,
    PepperUnavailableError,
    keep_pepper,
    mint_pepper,
    pepper_at_start,
    pepper_vault,
    read_pepper,
)
from brain.ops.leases import SealedSecret
from brain.ops.openbao import (
    CREATE_ONLY_VERSION,
    RESOLUTION_PREFIX,
    OpenBaoVault,
    VaultRefusedError,
    VaultUnreachableError,
)
from brain.ops.secrets import SecretsUnavailableError, VaultRole
from brain.resolution.canonical import IdentifierKind, identifier_hash

#: Two peppers in the one accepted shape, so a check on the shape cannot be what refuses them.
FIRST: Final = "a1" * 32
SECOND: Final = "b2" * 32

KEEP_STEP: Final = "keep this install's join-key pepper"


class PepperSlot:
    """One kv version 2 slot under the application's policy: read, create, and no update.

    `policy_loaded=False` is a vault still enforcing the policy from before this release, which
    refuses every call on the path. `engine=False` is a loaded policy over an engine nobody enabled.
    `removed=True` is a slot whose version somebody with a root token deleted. `racing` is a pepper
    another process creates between this one's read and its create. `forgetful` accepts the create
    and still answers 404 afterwards. `refuse_create` refuses the create with that status.
    """

    def __init__(
        self,
        fields: Mapping[str, object] | None = None,
        *,
        policy_loaded: bool = True,
        engine: bool = True,
        removed: bool = False,
        racing: str | None = None,
        forgetful: bool = False,
        refuse_create: int | None = None,
        cas_answers_false: bool = False,
    ) -> None:
        self.versions: list[dict[str, object]] = [] if fields is None else [dict(fields)]
        self.policy_loaded = policy_loaded
        self.engine = engine
        self.removed = removed
        self.racing = racing
        self.forgetful = forgetful
        self.refuse_create = refuse_create
        self.cas_answers_false = cas_answers_false
        self.created: list[str] = []

    def _refuse_if_closed(self) -> None:
        if not self.policy_loaded:
            raise VaultRefusedError("vault refused on a resolution path: HTTP 403", status=403)
        if not self.engine:
            raise VaultRefusedError("vault refused on a resolution path: HTTP 404", status=404)

    def read_static_kv(self, path: str) -> dict[str, object]:
        assert path == PEPPER_SLOT
        self._refuse_if_closed()
        if not self.versions or self.removed or self.forgetful:
            raise VaultRefusedError("vault refused GET on a resolution path: HTTP 404", status=404)
        return dict(self.versions[-1])

    def create_static_kv_once(self, path: str, fields: Mapping[str, str]) -> bool:
        assert path == PEPPER_SLOT
        self._refuse_if_closed()
        if self.refuse_create is not None:
            raise VaultRefusedError(
                "vault refused POST on a resolution path", status=self.refuse_create
            )
        if self.racing is not None:
            self.versions.append({PEPPER_FIELD: self.racing})
            self.racing = None
        if self.versions and self.cas_answers_false:
            return False
        if self.versions:
            # The policy grants no update, and a write to a slot with a version is an update.
            raise VaultRefusedError("vault refused POST on a resolution path: HTTP 403", status=403)
        self.created.append(fields[PEPPER_FIELD])
        self.versions.append(dict(fields))
        return True


class Silent:
    """A vault that did not answer, or answered in a shape nothing could read."""

    def __init__(self, error: SecretsUnavailableError) -> None:
        self.error = error

    def read_static_kv(self, path: str) -> dict[str, object]:
        raise self.error

    def create_static_kv_once(self, path: str, fields: Mapping[str, str]) -> bool:
        raise self.error


class SilentOnCreate(PepperSlot):
    """Answers the read with an empty slot and falls silent on the create."""

    def create_static_kv_once(self, path: str, fields: Mapping[str, str]) -> bool:
        raise VaultUnreachableError("vault at http://vault:8200 did not answer within 5.0s")


def minting(*values: str) -> Any:
    """A mint that hands out `values` in order, and fails the test if asked once more."""
    queue = list(values)

    def mint() -> str:
        assert queue, "a pepper was minted that nothing should have asked for"
        return queue.pop(0)

    return mint


def problem_of(call: Any) -> PepperProblem:
    """The problem a call raised, failing the test if it raised nothing."""
    with pytest.raises(PepperUnavailableError) as raised:
        call()
    return raised.value.problem


# ------------------------------------------------------------------------- the reader
def test_a_held_pepper_is_read_sealed_and_hashes_a_join_key() -> None:
    """The positive case for every refusal below: a slot holding a pepper of the one shape is read,
    handed back sealed, and once revealed is the value `identifier_hash` keys a join key with, so
    the digest is the one a process holding the same pepper computes. Delete this and a reader that
    refuses everything passes every other test in this file."""
    found = read_pepper(PepperSlot({PEPPER_FIELD: FIRST}))

    assert isinstance(found, SealedSecret)
    assert found.reveal() == FIRST
    assert identifier_hash(
        IdentifierKind.UEN, "201912345K", pepper=found.reveal()
    ) == identifier_hash(IdentifierKind.UEN, "201912345K", pepper=FIRST)


def test_the_reader_names_why_there_is_no_pepper_and_never_hands_one_back() -> None:
    """Each way a slot can fail to hand back a pepper is its own named problem: no vault, a slot
    never written, a vault that refused, and one that was silent or unreadable. Delete this and a
    refusal can read as an empty slot, which sends somebody to create a pepper that already exists
    behind a policy that was never loaded, or a silence can read as a refusal and send them to the
    policy files when the vault is sealed."""
    assert problem_of(lambda: read_pepper(None)) is PepperProblem.NO_VAULT
    assert problem_of(lambda: read_pepper(PepperSlot())) is PepperProblem.ABSENT
    assert problem_of(lambda: read_pepper(PepperSlot(engine=False))) is PepperProblem.ABSENT
    assert problem_of(lambda: read_pepper(PepperSlot(policy_loaded=False))) is (
        PepperProblem.REFUSED
    )
    sealed = VaultRefusedError("vault refused GET on a resolution path: HTTP 503", status=503)
    assert problem_of(lambda: read_pepper(Silent(sealed))) is PepperProblem.REFUSED
    unreachable = VaultUnreachableError("vault at http://vault:8200 did not answer within 5.0s")
    assert problem_of(lambda: read_pepper(Silent(unreachable))) is PepperProblem.UNREACHABLE
    garbled = SecretsUnavailableError("vault returned something that is not JSON")
    assert problem_of(lambda: read_pepper(Silent(garbled))) is PepperProblem.UNREACHABLE


def test_an_empty_answer_is_an_absent_pepper_and_not_a_malformed_one() -> None:
    """kv answers a slot with no current data as an empty mapping through `read_static_kv`. Delete
    this and that answer reads as a value somebody wrote, which tells an operator the slot holds
    something it does not."""
    empty = PepperSlot()
    empty.versions.append({})

    assert problem_of(lambda: read_pepper(empty)) is PepperProblem.ABSENT


@pytest.mark.parametrize(
    "held",
    [
        FIRST[:-1],
        FIRST + "a",
        FIRST.upper(),
        "g" + FIRST[1:],
        " " + FIRST[1:],
        FIRST[:-1] + "\n",
        64,
        int("1" * PEPPER_CHARS),
        None,
    ],
    ids=[
        "short",
        "long",
        "upper case",
        "not hex",
        "leading space",
        "newline",
        "a number",
        "a number of 64 digits",
        "null",
    ],
)
def test_a_value_that_is_not_64_lowercase_hex_characters_is_refused_and_never_said(
    held: object,
) -> None:
    """Only this module writes the slot and it writes exactly one shape, so anything else was put
    there by somebody holding a root token, and hashing with it would bind every stored digest to a
    value nobody here chose. Upper case is refused because the HMAC keys on the characters, so the
    same bytes in upper case are another pepper. A JSON number of 64 digits is refused although its
    decimal form has the shape, because the value is not text and whatever renders it decides the
    characters. The refusal carries no detail: its message is the fixed sentence, and it has no
    cause or context that could hold the value.

    Delete this and a pepper of the wrong length, case or alphabet is hashed with, or the refusal
    quotes the value it refused into a log line."""
    with pytest.raises(PepperUnavailableError) as raised:
        read_pepper(PepperSlot({PEPPER_FIELD: held}))

    assert raised.value.problem is PepperProblem.MALFORMED
    assert str(raised.value) == PEPPER_SAYS[PepperProblem.MALFORMED]
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_a_slot_holding_another_field_is_refused_as_malformed() -> None:
    """The pepper is kept under `value` and nowhere else. Delete this and a slot somebody filled by
    hand under another name reads as a pepper of nothing."""
    assert problem_of(lambda: read_pepper(PepperSlot({"key": FIRST}))) is PepperProblem.MALFORMED


def test_every_problem_says_a_fixed_sentence_that_names_the_pepper_and_no_value() -> None:
    """The message of every refusal is a sentence from the table, and the table has one for every
    problem. Delete this and a problem can be added with no sentence, which raises a KeyError from
    inside the refusal at the moment somebody most needs to read why."""
    assert set(PEPPER_SAYS) == set(PepperProblem)
    for problem in PepperProblem:
        error = PepperUnavailableError(problem)
        assert str(error) == PEPPER_SAYS[problem]
        assert PEPPER_SAYS[problem].startswith("Join-key pepper: ")


# ------------------------------------------------------------------------- the keeper
def test_an_empty_slot_is_filled_once_and_every_later_keep_reads_and_writes_nothing() -> None:
    """The first keep creates the pepper, and the second, the third and a re-run of the installer
    find it held and write nothing, because the mint is asked only once. Delete this and a re-run
    can mint again and, through a wider token, replace the pepper every digest was made with."""
    slot = PepperSlot()

    assert keep_pepper(slot, mint=minting(FIRST)) is True
    assert keep_pepper(slot, mint=minting()) is False
    assert keep_pepper(slot, mint=minting()) is False

    assert slot.created == [FIRST]
    assert read_pepper(slot).reveal() == FIRST


def test_a_process_that_loses_the_race_uses_the_pepper_the_vault_kept() -> None:
    """Two processes find the slot empty together; the vault keeps one value and refuses the other.
    Delete this and the loser can report that it created the pepper, or carry on as if its own
    value were the one stored, hashing join keys nothing else will ever match."""
    slot = PepperSlot(racing=SECOND)

    assert keep_pepper(slot, mint=minting(FIRST)) is False
    assert slot.created == []
    assert read_pepper(slot).reveal() == SECOND


def test_a_removed_pepper_is_never_created_again() -> None:
    """A slot whose pepper somebody holding a root token deleted has a version history, so the
    vault refuses the create (the missing update, 403) or the check-and-set says no (False); either
    way the slot stays empty and the problem is `REMOVED`, not `ABSENT`. Delete this and the
    problem reads as "not created yet", whose sentence tells somebody to create it, which is a
    rotation by another route."""
    refused = PepperSlot({PEPPER_FIELD: FIRST}, removed=True)
    assert problem_of(lambda: keep_pepper(refused, mint=minting(SECOND))) is PepperProblem.REMOVED

    said_no = PepperSlot({PEPPER_FIELD: FIRST}, removed=True, cas_answers_false=True)
    assert problem_of(lambda: keep_pepper(said_no, mint=minting(SECOND))) is PepperProblem.REMOVED


def test_a_slot_filled_by_somebody_else_mid_create_is_named_for_what_it_holds() -> None:
    """Between this process's read and its create, something else filled the slot with a value
    this product did not make. The read after the create finds that value and says `MALFORMED`,
    which is what the slot holds, rather than being folded into the reasons a slot is still
    empty, which would call it `REMOVED`. Delete this and an operator is told a pepper was deleted
    when one that nothing will hash with is sitting in the slot."""
    slot = PepperSlot(racing=FIRST.upper())

    assert problem_of(lambda: keep_pepper(slot, mint=minting(SECOND))) is PepperProblem.MALFORMED
    assert slot.created == []


def test_an_engine_nobody_enabled_is_a_refusal_and_not_a_removed_pepper() -> None:
    """A 404 on the create is an engine that is not mounted, which is this release's vault changes
    not being in force, and the sentence for that sends somebody to the release's runbook. Delete
    this and it reads as `REMOVED`, which says nothing here will ever create the pepper, on an
    install that only needs its release applied."""
    slot = PepperSlot(refuse_create=404)

    assert problem_of(lambda: keep_pepper(slot, mint=minting(FIRST))) is PepperProblem.REFUSED


def test_a_create_accepted_and_then_unread_or_refused_otherwise_is_a_silence() -> None:
    """The vault answered one call and not the next: it accepted the create and still says the slot
    is empty, or it refused the create with a status that is not about the slot. Delete this and
    either reads as a removed pepper, the one state this module never recovers from."""
    forgetful = PepperSlot(forgetful=True)
    assert problem_of(lambda: keep_pepper(forgetful, mint=minting(FIRST))) is (
        PepperProblem.UNREACHABLE
    )
    erroring = PepperSlot(refuse_create=500)
    assert problem_of(lambda: keep_pepper(erroring, mint=minting(FIRST))) is (
        PepperProblem.UNREACHABLE
    )
    silent = SilentOnCreate()
    assert problem_of(lambda: keep_pepper(silent, mint=minting(FIRST))) is (
        PepperProblem.UNREACHABLE
    )


def test_the_keeper_creates_nothing_unless_the_slot_was_read_as_empty() -> None:
    """A policy not loaded, a malformed value and no vault are each raised before any create, so
    the mint is never asked. Delete this and a keeper that cannot read the slot creates into it
    anyway, which on a slot holding a malformed value is an attempt to replace it."""
    assert problem_of(lambda: keep_pepper(None, mint=minting())) is PepperProblem.NO_VAULT
    refused = PepperSlot(policy_loaded=False)
    assert problem_of(lambda: keep_pepper(refused, mint=minting())) is PepperProblem.REFUSED
    malformed = PepperSlot({PEPPER_FIELD: FIRST.upper()})
    assert problem_of(lambda: keep_pepper(malformed, mint=minting())) is PepperProblem.MALFORMED
    assert refused.created == malformed.created == []


def test_a_minted_pepper_is_32_random_bytes_in_the_one_shape_the_reader_accepts() -> None:
    """The mint and the reader agree: everything minted is read back, and 32 bytes is the size of
    the SHA-256 output the HMAC keys, measured from hashlib rather than restated. Delete this and
    the mint can make a value the reader refuses, so every install's pepper is created and then
    refused for ever."""
    assert hashlib.sha256().digest_size == PEPPER_BYTES
    assert 2 * hashlib.sha256().digest_size == PEPPER_CHARS
    minted = {mint_pepper() for _ in range(8)}

    assert len(minted) == 8
    for value in minted:
        assert read_pepper(PepperSlot({PEPPER_FIELD: value})).reveal() == value


# ------------------------------------------------------------------- the client and the roles
def test_only_the_application_and_the_worker_are_given_a_pepper_reader() -> None:
    """The two processes that hash join keys get a client under their own role; a browser runner
    asking is refused; and an install naming no vault gets None, which the reader says in words.
    Delete this and a process that hashes nothing can be built a client that presents its token at
    the pepper's slot."""
    for role in (VaultRole.APPLICATION, VaultRole.WORKER):
        vault = pepper_vault("http://vault:8200", "a-token", role)
        assert isinstance(vault, OpenBaoVault)
        assert f"role=<VaultRole.{role.name}" in repr(vault)
        assert pepper_vault("", "a-token", role) is None
        assert pepper_vault("http://vault:8200", "", role) is None
    with pytest.raises(ValueError, match="does not hash join keys"):
        pepper_vault("http://vault:8200", "a-token", VaultRole.BROWSER_RUNNER)


class Recorded:
    """`urllib.request.urlopen` standing in for a vault holding an empty `resolution` engine."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, Any] | None]] = []
        self.held: dict[str, dict[str, str]] = {}

    def urlopen(self, request: Any, timeout: float = 0) -> Any:
        method, url = request.get_method(), request.full_url
        path = url.split("/v1/", 1)[1]
        body = json.loads(request.data) if request.data else None
        self.sent.append((method, path, body))
        if method == "POST" and body is not None:
            self.held[path] = dict(body["data"])
            answer: dict[str, Any] = {"data": {"version": 1}}
        elif method == "GET" and path in self.held:
            answer = {"data": {"data": self.held[path], "metadata": {"version": 1}}}
        else:
            raise urllib.error.HTTPError(url, 404, "not found", Message(), None)
        return io.BytesIO(json.dumps(answer).encode())


def test_the_real_client_creates_the_pepper_with_the_create_only_check_and_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Against `OpenBaoVault` with only its network call replaced: the keeper reads
    `resolution/data/pepper`, finds nothing, posts the pepper with `options.cas` at 0, and reads it
    back. Delete this and the check-and-set can be dropped from the one write, leaving the policy's
    missing update as the only thing between a second create and a replaced pepper."""
    vault = Recorded()
    monkeypatch.setattr("urllib.request.urlopen", vault.urlopen)
    client = pepper_vault("http://vault:8200", "a-token", VaultRole.APPLICATION)

    assert keep_pepper(client, mint=minting(FIRST)) is True

    data_path = f"{RESOLUTION_PREFIX}data/pepper"
    assert vault.sent == [
        ("GET", data_path, None),
        ("POST", data_path, {"options": {"cas": CREATE_ONLY_VERSION}, "data": {"value": FIRST}}),
        ("GET", data_path, None),
    ]
    assert read_pepper(client).reveal() == FIRST


def test_the_ordinary_write_refuses_the_pepper_and_the_static_rule_admits_its_read() -> None:
    """`write_static_kv` is the write every console credential goes through, and it refuses the
    pepper's prefix before anything is sent, while `assert_static_path` admits the prefix so the
    reader can read it at all. Delete this and a console form pointed at the slot can replace the
    pepper with a value somebody typed, or the prefix can be dropped from the admitted list and
    every read refused as a leased path."""
    from brain.ops.openbao import WRITE_ONCE_PREFIXES, assert_static_path

    client = OpenBaoVault("http://vault:8200", "a-token", role=VaultRole.APPLICATION)
    assert RESOLUTION_PREFIX in WRITE_ONCE_PREFIXES
    with pytest.raises(SecretsUnavailableError, match="written once"):
        client.write_static_kv(PEPPER_SLOT, {PEPPER_FIELD: FIRST})
    assert_static_path(PEPPER_SLOT)


# ------------------------------------------------------------------------- the start
def test_the_start_creates_the_pepper_logs_without_it_and_never_raises(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str], monkeypatch: Any
) -> None:
    """The application's start makes sure of the pepper and says only whether it is held: a
    created pepper returns None, a held one returns None and creates nothing, and no rendering,
    log line or printed output carries the value. Delete this and the start can raise into the
    lifespan and stop the application, or log the pepper it created."""
    caplog.set_level(logging.DEBUG)
    slot = PepperSlot()
    monkeypatch.setattr(join_key_pepper, "pepper_vault", lambda _a, _t, _r: slot)

    with capture_logs() as logs:
        assert pepper_at_start("http://vault:8200", "a-token") is None
        assert pepper_at_start("http://vault:8200", "a-token") is None

    assert len(slot.created) == 1
    created = slot.created[0]
    assert read_pepper(slot).reveal() == created
    assert [one["created_here"] for one in logs] == [True, False]
    written = capsys.readouterr()
    assert created not in "\n".join([repr(logs), caplog.text, written.out, written.err])


@pytest.mark.parametrize(
    ("slot", "problem", "level"),
    [
        (None, PepperProblem.NO_VAULT, "info"),
        (PepperSlot(policy_loaded=False), PepperProblem.REFUSED, "warning"),
        (PepperSlot({PEPPER_FIELD: "x"}), PepperProblem.MALFORMED, "warning"),
    ],
    ids=["no vault", "refused", "malformed"],
)
def test_the_start_returns_the_problem_and_warns_unless_the_install_chose_no_vault(
    monkeypatch: pytest.MonkeyPatch,
    slot: PepperSlot | None,
    problem: PepperProblem,
    level: str,
) -> None:
    """A start that holds no pepper returns why, and warns, except on an install that declined the
    vault, where no pepper is the configured state and a warning on every start is noise somebody
    learns to ignore. Delete this and a refused or malformed pepper is logged at the level of a
    healthy start, which is where nobody looks."""
    monkeypatch.setattr(join_key_pepper, "pepper_vault", lambda _a, _t, _r: slot)

    with capture_logs() as logs:
        assert pepper_at_start("http://vault:8200", "a-token") is problem

    assert [(one["log_level"], one["problem"]) for one in logs] == [(level, problem.value)]


def test_an_address_that_is_not_a_url_is_unreachable_at_start_and_does_not_raise() -> None:
    """The client refuses an address that is not a URL with ValueError, which the start must not
    let reach the lifespan. Delete this and a typing mistake in the vault address stops the
    application starting at all, rather than leaving readiness to name it."""
    with capture_logs() as logs:
        assert pepper_at_start("vault:8200", "a-token") is PepperProblem.UNREACHABLE
    assert [one["log_level"] for one in logs] == ["warning"]


# ------------------------------------------------------------------------- the command
def test_the_command_creates_once_its_held_flag_only_reads_and_neither_prints_the_pepper(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--held` is the installer's done test: it reads, prints nothing and exits 0 only when a
    pepper is held. The bare command creates it once and says so. A usage mistake exits 2. Delete
    this and the done test can create, so a re-run of the installer writes, or the command can
    print the value into the installer's output, which a terminal recording keeps."""
    slot = PepperSlot()
    monkeypatch.setattr(join_key_pepper, "pepper_vault", lambda _a, _t, _r: slot)
    capsys.readouterr()

    assert join_key_pepper.main([HELD_FLAG]) == 1
    assert slot.created == []
    held_out = capsys.readouterr()
    assert held_out.out == held_out.err == ""

    assert join_key_pepper.main([]) == 0
    assert join_key_pepper.main([]) == 0
    assert join_key_pepper.main([HELD_FLAG]) == 0
    assert join_key_pepper.main(["--rotate"]) == 2
    written = capsys.readouterr()

    assert len(slot.created) == 1
    assert slot.created[0] not in written.out + written.err
    assert written.out.splitlines() == [
        "Join-key pepper: created in its vault slot, once, and never written over.",
        "Join-key pepper: held. Nothing was written.",
    ]
    assert "usage" in written.err


def test_the_command_says_why_when_no_pepper_is_held(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refused keep prints the problem's sentence and exits 1, and an install with an address
    that is not a URL is read as no vault rather than a crash. Delete this and the installer's step
    fails with a traceback instead of the sentence its on-failure text tells somebody to read."""
    monkeypatch.setattr(
        join_key_pepper, "pepper_vault", lambda _a, _t, _r: PepperSlot(policy_loaded=False)
    )
    assert join_key_pepper.main([]) == 1
    assert capsys.readouterr().out.strip() == PEPPER_SAYS[PepperProblem.REFUSED]

    def not_a_url(_a: str, _t: str, _r: VaultRole) -> None:
        raise ValueError("vault address 'vault' is not a URL")

    monkeypatch.setattr(join_key_pepper, "pepper_vault", not_a_url)
    assert join_key_pepper.main([]) == 1
    assert capsys.readouterr().out.strip() == PEPPER_SAYS[PepperProblem.NO_VAULT]


# ----------------------------------------------------------------- the installer's step
def test_the_installer_step_creates_after_readiness_and_its_done_test_only_reads() -> None:
    """The owner's decision (b): the installer creates the pepper. The step runs the module's
    command in the application container once readiness and furnishing are done, before the
    template key's step, and it is skipped when the pepper is held or the install declined the
    vault. The command and flag are held equal to the module's own rather than imported by the
    installer. Delete this and the done test can be the creating command, so a re-run of the
    installer writes, or the step can run before the application exists."""
    step = step_named(KEEP_STEP)
    names = [one.name for one in PLAN]

    assert join_key_pepper.__name__ == PEPPER_COMMAND
    assert PEPPER_HELD_FLAG == HELD_FLAG
    assert step.changes and not step.presents_once
    assert step.run == f"docker compose $BRAIN_COMPOSE_FILES exec -T app python -m {PEPPER_COMMAND}"
    assert step.already_done == (
        'test "${BRAIN_VAULT:-yes}" = "no" || docker compose $BRAIN_COMPOSE_FILES exec -T app '
        f"python -m {PEPPER_COMMAND} {HELD_FLAG}"
    )
    assert names.index("wait for the application to report ready") < names.index(KEEP_STEP)
    assert names.index("furnish the install") < names.index(KEEP_STEP)
    assert names.index(KEEP_STEP) < names.index("keep this install's template signing key")
