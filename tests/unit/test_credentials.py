"""The credential store: a slot written once, said to be held, and never read back.

Every test here is one of three things: an order a person can act on (no vault before a bad
paste, a bad paste before a write), a way a value could come back out (a result type, a log line,
a representation), or which processes use a key once it is kept. The HTTP half is
`tests/unit/test_credential_routes.py` and the wizard's is `tests/unit/test_setup_routes.py`.

No vault is contacted. `Vault` below implements the store's protocol directly, and the start-up
tests subclass the real client with its one network call replaced, as `test_provider_keys` does.

Task ids: M27.8.7, M5.1.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import fields
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.audit.record import credential_subject_id
from brain.ops.credentials import (
    A_CREDENTIAL_WRITE_LEAVES_A_LEDGER_ENTRY_AND_NEVER_THE_VALUE,
    KEY_FIELD,
    MAX_CREDENTIAL_CHARS,
    SLOTS,
    THE_KEY_IS_KEPT_BEFORE_IT_IS_RECORDED_AND_A_LOST_RECORD_IS_LOUD,
    TOLD,
    CredentialProblemError,
    Credentials,
    CredentialSlot,
    CredentialsUnavailableError,
    Held,
    InUse,
    Kept,
    VaultState,
    _application_vault,
    connector_key_slot,
    credentials_at_start,
    problems_with,
    told_in_use,
)
from brain.ops.openbao import (
    CONNECTOR_KEY_PREFIX,
    OpenBaoVault,
    StaticVersion,
    VaultRefusedError,
    VaultUnreachableError,
)
from brain.ops.provider_keys import PROVIDER_SLOTS, read_static
from brain.ops.secrets import SecretsUnavailableError
from brain.settings import Settings
from brain.setup_wizard import MAX_KEY_CHARS

#: A value nothing else in any output could contain, so finding it anywhere is a leak.
KEY = "sk-CREDENTIAL-SENTINEL-7f3a9c"

#: When the fake vault says a version was written. Far from any wall clock, deliberately.
AT = datetime(2019, 3, 4, 5, 6, 7, tzinfo=UTC)

ANTHROPIC = SLOTS["providers/anthropic"]


class Vault:
    """The store's `CredentialVault` protocol in memory: what was written, what was asked."""

    def __init__(
        self, *, fail: Exception | None = None, version: StaticVersion | None = None
    ) -> None:
        self.written: list[tuple[str, dict[str, str]]] = []
        self.asked: list[str] = []
        self._fail = fail
        self._version = version

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        self.written.append((path, dict(fields)))
        if self._fail is not None:
            raise self._fail
        return AT

    def static_kv_version(self, path: str) -> StaticVersion | None:
        self.asked.append(path)
        if self._fail is not None:
            raise self._fail
        return self._version


class Stocked(OpenBaoVault):
    """The real client with its network call replaced, holding kv v2 slots by data path."""

    def __init__(self, held: dict[str, str] | None = None) -> None:
        super().__init__("http://vault:8200", "a-token")
        self.paths: list[str] = []
        self._held = held or {}

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.paths.append(path)
        if path in self._held:
            return {"data": {"data": {KEY_FIELD: self._held[path]}, "metadata": {"version": 1}}}
        raise VaultRefusedError("vault refused GET on a providers path: HTTP 404", status=404)


class Recorded:
    """The store's `CredentialWrites` protocol in memory: every record asked for, in order.

    `events` can be shared with a `Sequenced` vault, so a test reads one list for which of the
    two happened first. `fail` makes every record raise after it is noted.
    """

    def __init__(self, events: list[str] | None = None, *, fail: Exception | None = None) -> None:
        self.records: list[dict[str, str]] = []
        self.events = events if events is not None else []
        self._fail = fail

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        self.events.append("record")
        self.records.append(
            {"slot": slot, "written_by": written_by, "trace_id": trace_id, "ent_hash": ent_hash}
        )
        if self._fail is not None:
            raise self._fail


class Sequenced(Vault):
    """A `Vault` that notes its write on a list shared with a `Recorded`."""

    def __init__(self, events: list[str], *, fail: Exception | None = None) -> None:
        super().__init__(fail=fail)
        self.events = events

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        self.events.append("vault")
        return super().write_static_kv(path, fields)


def keeping(
    store: Credentials, value: str = KEY, *, trace_id: str = "t", ent_hash: str = ""
) -> Kept:
    """`Credentials.keep` into the Anthropic slot as `u_admin`, awaited to its end."""
    return asyncio.run(
        store.keep(ANTHROPIC, value, actor="u_admin", trace_id=trace_id, ent_hash=ent_hash)
    )


# ----------------------------------------------------------------------- the slots
def test_every_provider_is_a_slot_at_the_path_start_up_reads_it_from() -> None:
    """Built from `PROVIDER_SLOTS` rather than listed again. Delete this and a provider added
    there has no slot here, so the wizard accepts it and the store has nowhere to keep its key."""
    assert set(SLOTS) == {one.path for one in PROVIDER_SLOTS}
    for one in PROVIDER_SLOTS:
        assert SLOTS[one.path].provider is one
        assert SLOTS[one.path].description == one.description


def test_a_key_is_written_under_the_field_start_up_reads_it_back_from() -> None:
    """Held against `read_static`, the start-up reader, rather than against the constant. Delete
    this and `KEY_FIELD` can be renamed to a field start-up does not look for, and every key the
    console sets reads as a slot holding nothing it recognises after the next restart."""
    vault = Vault()
    keeping(Credentials(vault))
    [(path, written)] = vault.written
    data_path = path.replace("providers/", "providers/data/")
    assert read_static(Stocked({data_path: written[KEY_FIELD]}), path) == KEY
    assert written == {KEY_FIELD: KEY}


def test_the_ceiling_on_a_credential_is_the_wizard_s_ceiling_on_a_key() -> None:
    """Two statements of one limit, held equal. Delete this and the wizard accepts a key the store
    then refuses, which is a 409 at the end of the wizard for a paste the screen said was fine."""
    assert MAX_CREDENTIAL_CHARS == MAX_KEY_CHARS


# ----------------------------------------------------------------- judging a paste
@pytest.mark.parametrize("given", ["", "   ", "\n\t "])
def test_nothing_given_is_one_problem_and_says_what_to_paste(given: str) -> None:
    """Blank is one problem and nothing else: a length or a character complaint about an empty box
    buries the sentence the person can act on. Delete this and blank reaches the vault."""
    assert [one.code for one in problems_with(given)] == ["blank"]


def test_a_key_with_a_line_break_at_the_end_is_accepted_and_stored_without_it() -> None:
    """The commonest correct paste carries a trailing line break. Refusing it would refuse the
    right answer, and storing it would send a header with a newline in it. Delete this and either
    happens."""
    vault = Vault()
    assert problems_with(f"  {KEY}\n") == ()
    keeping(Credentials(vault), f"  {KEY}\n")
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]


def test_a_key_at_the_ceiling_is_accepted_and_one_character_over_is_not() -> None:
    """The boundary, both sides. Delete this and the comparison can move by one in either direction
    with every other test green."""
    assert problems_with("k" * MAX_CREDENTIAL_CHARS) == ()
    assert [one.code for one in problems_with("k" * (MAX_CREDENTIAL_CHARS + 1))] == ["too_long"]


@pytest.mark.parametrize("inside", [" ", "\n", "\t", "\x00", chr(0x200B)])
def test_a_key_with_a_space_or_a_character_a_key_cannot_hold_inside_it_is_refused(
    inside: str,
) -> None:
    """A space or a line break inside is a bad copy, and a control or zero-width character fails
    at the provider as an authentication error nobody can read. Delete this and such a key is
    stored, reported as held, and every question fails."""
    assert [one.code for one in problems_with(f"sk-{inside}rest")] == ["not_one_piece"]


def test_every_problem_is_told_at_once_and_each_says_what_to_do() -> None:
    """Two problems are two sentences, so fixing one does not uncover the other. Each sentence
    names an action, and none repeats the value. Delete this and the first problem found hides
    the second."""
    given = f"{KEY} {'k' * MAX_CREDENTIAL_CHARS}"
    found = problems_with(given)
    assert [one.code for one in found] == ["too_long", "not_one_piece"]
    assert all("paste it" in one.message for one in found)
    assert all(KEY not in one.message for one in found)


# --------------------------------------------------------------- keeping, in order
def test_an_install_with_no_vault_is_told_so_before_its_paste_is_judged() -> None:
    """A person told to fix a paste on an install that cannot keep one has been told the wrong
    thing to do. Delete this and a blank on a vaultless install says "paste the key", which they
    do, and are then told there is no vault."""
    with pytest.raises(CredentialsUnavailableError) as refused:
        keeping(Credentials(None), "")
    assert refused.value.state is VaultState.ABSENT
    assert str(refused.value) == TOLD[VaultState.ABSENT]


def test_a_bad_paste_is_refused_before_anything_is_sent_to_the_vault() -> None:
    """Validation before the write. Delete this and a malformed key is written, becomes the current
    version, and replaces the working one it was meant to rotate."""
    vault = Vault()
    with pytest.raises(CredentialProblemError) as refused:
        keeping(Credentials(vault), "sk- broken")
    assert [one.code for one in refused.value.problems] == ["not_one_piece"]
    assert vault.written == []
    assert "sk- broken" not in str(refused.value)


def test_a_good_key_is_written_and_answered_with_its_slot_and_time_alone() -> None:
    """The positive case every refusal above needs. `Kept` carries the slot and the vault's time
    and has no field that could carry more. Delete this and a store that refuses everything passes
    the rest of the file."""
    vault = Vault()
    kept = keeping(Credentials(vault))
    assert kept == Kept(slot="providers/anthropic", set_at=AT)
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]


@pytest.mark.parametrize(
    ("raised", "state"),
    [
        (VaultUnreachableError("did not answer"), VaultState.UNREACHABLE),
        (VaultRefusedError("refused", status=403), VaultState.REFUSED),
        (VaultRefusedError("refused", status=404), VaultState.REFUSED),
        (SecretsUnavailableError("some other refusal"), VaultState.REFUSED),
    ],
)
def test_a_silent_vault_and_a_refusing_one_are_told_apart(
    raised: Exception, state: VaultState
) -> None:
    """Silence is start or unseal the vault; refusal is a token, a policy or an engine. A 404 on a
    write is an engine not mounted, which is a refusal. Delete this and every failure reads as the
    same sentence and half the people reading it go to the wrong place."""
    with pytest.raises(CredentialsUnavailableError) as refused:
        keeping(Credentials(Vault(fail=raised)))
    assert refused.value.state is state
    assert str(refused.value) == TOLD[state]


def test_every_state_has_its_own_sentence_and_no_vault_names_the_two_settings_to_set() -> None:
    """The names are read off `Settings`, which is what actually reads them, rather than off the
    sentence. Delete this and a renamed setting leaves a sentence telling people to set a variable
    nothing reads."""
    assert set(TOLD) == set(VaultState)
    assert len(set(TOLD.values())) == len(VaultState)
    for field in ("vault_address", "vault_token"):
        assert field in Settings.model_fields
        assert f"BRAIN_{field.upper()}" in TOLD[VaultState.ABSENT]


# ----------------------------------------------------------- saying it is held
def test_a_slot_is_held_with_the_time_its_current_version_was_written() -> None:
    """The console's one question, answered from metadata. Both directions: a held slot with its
    time, an empty one with none. Delete this and a store answering "held" for every slot passes."""
    held = Credentials(Vault(version=StaticVersion(written_at=AT))).held(ANTHROPIC)
    empty = Credentials(Vault(version=None)).held(ANTHROPIC)
    untimed = Credentials(Vault(version=StaticVersion(written_at=None))).held(ANTHROPIC)

    assert held == Held(slot="providers/anthropic", held=True, set_at=AT)
    assert empty == Held(slot="providers/anthropic", held=False, set_at=None)
    assert untimed == Held(slot="providers/anthropic", held=True, set_at=None)


@pytest.mark.parametrize(
    ("vault", "state"),
    [
        (None, VaultState.ABSENT),
        (Vault(fail=VaultUnreachableError("did not answer")), VaultState.UNREACHABLE),
        (Vault(fail=VaultRefusedError("refused", status=403)), VaultState.REFUSED),
    ],
)
def test_a_slot_that_cannot_be_asked_about_is_not_reported_as_empty(
    vault: Vault | None, state: VaultState
) -> None:
    """Not known is not "not held". Delete this and an unreachable vault shows every slot empty,
    and somebody pastes a key into a vault that is down."""
    with pytest.raises(CredentialsUnavailableError) as refused:
        Credentials(vault).held(ANTHROPIC)
    assert refused.value.state is state


# ---------------------------------------------------- nothing comes back out
def test_nothing_this_store_answers_has_a_field_that_could_hold_a_value() -> None:
    """Structural, over the dataclasses rather than over one instance. Delete this and a field such
    as `value` or `preview` can be added to `Kept` for a screen, and the write route returns it."""
    assert {one.name for one in fields(Kept)} == {"slot", "set_at"}
    assert {one.name for one in fields(Held)} == {"slot", "held", "set_at"}
    assert {one.name for one in fields(StaticVersion)} == {"written_at"}


def test_the_log_names_the_slot_and_the_actor_and_never_the_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """**`capsys`, because structlog writes to standard output here**, which
    `test_answer_route` found the hard way. The positive half is asserted too, so a store that
    logged nothing would fail: the kept line names the slot, the actor and the trace id. Every
    path that logs is driven: kept, refused for its paste, and not kept. Delete this and the value
    is added to a log line to make an incident easier, and it is in the log for its retention."""
    capsys.readouterr()
    keeping(Credentials(Vault()), trace_id="trace-kept")
    with pytest.raises(CredentialProblemError):
        keeping(Credentials(Vault()), f"{KEY} x")
    with pytest.raises(CredentialsUnavailableError):
        keeping(Credentials(Vault(fail=VaultUnreachableError("x"))))
    with pytest.raises(CredentialsUnavailableError):
        keeping(Credentials(None))

    written = capsys.readouterr()
    logged = written.out + written.err
    # The kept line itself, because the refusals name the slot and the actor too, and a kept line
    # that dropped them would otherwise be covered by its neighbours. A mutation found that.
    [kept] = [line for line in logged.splitlines() if "credential kept" in line]
    assert "providers/anthropic" in kept, kept
    assert "u_admin" in kept
    assert "trace-kept" in kept
    assert "credential refused" in logged
    assert logged.count("credential not kept") == 2
    assert KEY not in logged


def test_the_store_s_representation_names_no_vault_token_and_no_key() -> None:
    """An exception handler formatting the object that held the vault is the commonest way a token
    reaches a log. Delete this and `Credentials` can grow a generated repr that walks into the
    vault client and whatever it holds."""
    shown = repr(Credentials(Stocked(), outranking=frozenset({"ANTHROPIC_API_KEY"})))
    assert "a-token" not in shown
    assert "configured=True" in shown
    assert str(Credentials(None)) == "Credentials(configured=False, outranking=[])"


# ------------------------------------------------------- recording a kept key
def test_a_kept_key_is_recorded_after_the_vault_write_with_its_writer_and_no_value() -> None:
    """`A_CREDENTIAL_WRITE_LEAVES_A_LEDGER_ENTRY_AND_NEVER_THE_VALUE`, the positive case. One
    list shared by the vault and the record says which came first; the record names the slot,
    the writer, the trace and the reach's digest, and nothing in it carries the key.

    Delete this and the record can be dropped from `keep`, so a key is replaced from the console
    with nothing in the ledger, or made before the vault answers, so a refused write is recorded
    as a key replaced, or handed the value to make the entry more useful."""
    events: list[str] = []
    writes = Recorded(events)
    kept = keeping(
        Credentials(Sequenced(events), writes=writes), trace_id="trace-kept", ent_hash="e" * 32
    )

    assert kept == Kept(slot="providers/anthropic", set_at=AT)
    assert events == ["vault", "record"]
    assert writes.records == [
        {
            "slot": "providers/anthropic",
            "written_by": "u_admin",
            "trace_id": "trace-kept",
            "ent_hash": "e" * 32,
        }
    ]
    assert all(KEY not in one for one in writes.records[0].values())
    assert "ledger" in A_CREDENTIAL_WRITE_LEAVES_A_LEDGER_ENTRY_AND_NEVER_THE_VALUE


@pytest.mark.parametrize(
    ("vault", "value"),
    [
        (None, KEY),
        (Vault(), f"{KEY} x"),
        (Vault(fail=VaultUnreachableError("did not answer")), KEY),
        (Vault(fail=VaultRefusedError("refused", status=403)), KEY),
    ],
)
def test_a_key_that_was_not_kept_is_not_recorded(vault: Vault | None, value: str) -> None:
    """No vault, a bad paste, a silent vault and a refusing one each replaced nothing, so each
    records nothing. Delete this and a write the vault refused leaves an entry saying the key was
    replaced, which is the one entry an auditor would act on and the ledger cannot take back."""
    writes = Recorded()
    with pytest.raises((CredentialsUnavailableError, CredentialProblemError)):
        keeping(Credentials(vault, writes=writes), value)
    assert writes.records == []


def test_a_record_that_fails_after_the_key_was_kept_is_an_error_in_the_log_and_the_key_is_kept(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`THE_KEY_IS_KEPT_BEFORE_IT_IS_RECORDED_AND_A_LOST_RECORD_IS_LOUD`. The vault holds the key
    whatever the database did, so the write is answered as kept, and the missing record is an
    error naming the slot, the writer, the trace and the exception's type, never the key or the
    exception's message, which is where a statement's parameters are quoted.

    Delete this and a database that refuses the insert either turns a saved key into a failure
    the person repeats, or loses the record with nothing in the log to say so."""
    capsys.readouterr()
    vault = Vault()
    writes = Recorded(fail=RuntimeError(f"insert failed with {KEY}"))
    kept = keeping(Credentials(vault, writes=writes), trace_id="trace-lost")
    written = capsys.readouterr()
    logged = written.out + written.err

    assert kept == Kept(slot="providers/anthropic", set_at=AT)
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    [lost] = [line for line in logged.splitlines() if "credential write not recorded" in line]
    assert "error" in lost.lower()
    assert all(one in lost for one in ("providers/anthropic", "u_admin", "trace-lost"))
    assert "RuntimeError" in lost
    assert KEY not in logged
    assert "second record" in THE_KEY_IS_KEPT_BEFORE_IT_IS_RECORDED_AND_A_LOST_RECORD_IS_LOUD


def test_a_store_with_nowhere_to_record_keeps_the_key_and_warns(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A store with no database has no ledger. It keeps the key, because no deployed route
    reaches it there, and it says so as a warning rather than silently. Delete this and a process
    wired without its record reads in the log exactly like one recording every write."""
    capsys.readouterr()
    kept = keeping(Credentials(Vault()), trace_id="trace-nowhere")
    logged = capsys.readouterr().out

    assert kept.slot == "providers/anthropic"
    [warned] = [line for line in logged.splitlines() if "no ledger to be recorded in" in line]
    assert "warning" in warned.lower()
    assert "trace-nowhere" in warned
    assert KEY not in logged


def test_recording_somewhere_keeps_the_vault_and_environment_and_nowhere_is_the_same() -> None:
    """The lifespan attaches the record after the database through `recording_to`. Delete this
    and the attached store can lose the vault, so every write after start answers "no vault", or
    lose the environment it loads keys into, so a key saved from the console is kept and never
    used, or nowhere can replace a working store with a new one."""
    env: dict[str, str] = {}
    vault = Vault()
    plain = Credentials(vault, outranking=frozenset({"OPENAI_API_KEY"}), environ=env)
    writes = Recorded()
    recording = plain.recording_to(writes)

    assert plain.recording_to(None) is plain
    assert recording is not plain
    keeping(recording)
    assert vault.written == [("providers/anthropic", {KEY_FIELD: KEY})]
    assert [one["slot"] for one in writes.records] == ["providers/anthropic"]
    assert recording.put_to_use(ANTHROPIC, KEY) is InUse.HERE
    assert env == {"ANTHROPIC_API_KEY": KEY}
    assert recording.put_to_use(SLOTS["providers/openai"], KEY) is InUse.OUTRANKED


# ------------------------------------------------ which processes use a key kept here
def test_a_key_kept_here_is_handed_to_this_process_unless_the_environment_outranks_it() -> None:
    """Both halves. Outranked means the environment set the variable before the vault was asked at
    start, and will again, so handing the new key over here would make this process disagree with
    every sibling and with itself after a restart. Delete this and one of the two is lost: the
    process that answered "saved" keeps the old key, or it quietly uses a key the next start
    reverts."""
    env: dict[str, str] = {}
    here = Credentials(Vault(), environ=env).put_to_use(ANTHROPIC, f"{KEY}\n")
    outranked_env = {"ANTHROPIC_API_KEY": "sk-from-the-file"}
    outranked = Credentials(
        Vault(), outranking=frozenset({"ANTHROPIC_API_KEY"}), environ=outranked_env
    ).put_to_use(ANTHROPIC, KEY)

    assert (here, env) == (InUse.HERE, {"ANTHROPIC_API_KEY": KEY})
    assert (outranked, outranked_env) == (
        InUse.OUTRANKED,
        {"ANTHROPIC_API_KEY": "sk-from-the-file"},
    )


def test_what_a_person_is_told_about_a_kept_key_says_what_to_do_next() -> None:
    """Outranked names the variable and says to remove it; in use says the others need a restart.
    Held against the slot's own variable rather than a literal. Delete this and the sentence can
    stop naming the line to remove, which is the one thing the person cannot find out otherwise."""
    outranked = told_in_use(ANTHROPIC, InUse.OUTRANKED)
    here = told_in_use(ANTHROPIC, InUse.HERE)
    assert f"Remove {ANTHROPIC.provider.env_var}" in outranked
    assert ANTHROPIC.provider.env_var not in here
    assert "next start" in here
    assert "restart the system" in here


# ------------------------------------------------------------------- at start
class NoVaultBuilt:
    """A vault factory that must never be called."""

    def __call__(self, address: str, token: str) -> OpenBaoVault:
        raise AssertionError("a vault was built")


def test_an_install_naming_no_vault_asks_nobody_and_keeps_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every install until its owner runs a vault, and it is said once as that and not as half a
    vault, which would send the owner of an install that chose not to run one looking for a
    missing setting. Delete this and start-up can build a client for an empty address and fail
    every request as a refusal that sends somebody to read a policy."""
    capsys.readouterr()
    store = credentials_at_start("", "", environ={}, make_vault=NoVaultBuilt())
    logged = capsys.readouterr().out
    assert store.configured is False
    assert "no secrets vault configured" in logged
    assert "half configured" not in logged


@pytest.mark.parametrize(
    ("address", "token", "missing"),
    [("http://vault:8200", "", "BRAIN_VAULT_TOKEN"), ("", "a-token", "BRAIN_VAULT_ADDRESS")],
)
def test_half_a_vault_is_no_vault_and_the_log_names_the_missing_half(
    address: str, token: str, missing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """One of the two set is a mistake somebody is about to spend an hour on, so the log names the
    half that is missing and never the half that is there. Delete this and a half-configured vault
    is tried anyway and refuses on its first request."""
    capsys.readouterr()
    store = credentials_at_start(address, token, environ={}, make_vault=NoVaultBuilt())
    logged = capsys.readouterr().out
    assert store.configured is False
    assert missing in logged
    assert "a-token" not in logged


def test_an_address_that_is_not_a_url_is_no_vault_rather_than_a_process_that_will_not_start() -> (
    None
):
    """The real client refuses the address. Start-up must not, because an install that answers
    without its keys is better than one that restarts in a loop. Delete this and a typo in the
    environment file takes the whole application down."""
    store = credentials_at_start("vault:8200", "a-token", environ={})
    assert store.configured is False


def test_start_up_loads_every_held_key_and_remembers_which_the_environment_already_set() -> None:
    """The names are taken before anything is loaded. A key the vault supplied is replaced in this
    process by the next write; a key the environment set is outranked. Delete this and the snapshot
    can move after the load, when every loaded name looks as though the environment set it."""
    env = {"OPENAI_API_KEY": "sk-from-the-file"}
    vault = Stocked({"providers/data/anthropic": KEY, "providers/data/openai": "sk-from-the-vault"})

    store = credentials_at_start(
        "http://vault:8200", "a-token", environ=env, make_vault=lambda a, t: vault
    )

    assert store.configured is True
    assert env == {"OPENAI_API_KEY": "sk-from-the-file", "ANTHROPIC_API_KEY": KEY}
    assert store.put_to_use(SLOTS["providers/anthropic"], "sk-next") is InUse.HERE
    assert store.put_to_use(SLOTS["providers/openai"], "sk-next") is InUse.OUTRANKED
    assert env["OPENAI_API_KEY"] == "sk-from-the-file"


def test_the_vault_start_up_builds_asks_as_the_application() -> None:
    """The role on the client is what its leases are checked against. Built by the default factory
    without being asked anything, because a unit test that dialled a vault would be a test of the
    network. Delete this and the factory can build a client with no role, which reads the same
    until a lease is refused."""
    built = _application_vault("http://vault:8200", "a-token")
    assert (
        repr(built)
        == "OpenBaoVault(address='http://vault:8200', role=<VaultRole.APPLICATION: 'application'>)"
    )


# ------------------------------------------------------------ a connected source's key


def test_a_connected_source_s_key_is_kept_by_the_same_write_at_its_own_slot_and_recorded() -> None:
    """`A_CONNECTED_SOURCE_S_KEY_IS_WRITTEN_BY_CONNECTING_IT`: one `keep` for both kinds of slot, so
    a source's key reaches the vault at `connector_keys/<source>` under the one field this module
    writes, is recorded exactly as a provider key is, and is never put into this process's
    environment. Delete this and the connector slot can grow a writer of its own that forgets the
    record."""
    vault, recorded = Vault(), Recorded()
    environ: dict[str, str] = {}
    store = Credentials(vault, environ=environ, writes=recorded)
    slot = connector_key_slot("xero")

    kept = asyncio.run(store.keep(slot, f" {KEY}\n", actor="u_admin", trace_id="t"))

    assert (kept.slot, kept.set_at) == ("connector_keys/xero", AT)
    assert vault.written == [("connector_keys/xero", {KEY_FIELD: KEY})]
    assert [one["slot"] for one in recorded.records] == ["connector_keys/xero"]
    assert environ == {}
    assert not isinstance(slot, CredentialSlot)


@pytest.mark.parametrize("name", ["", "Xero", "xero/../providers/anthropic", "x y", "a" * 64])
def test_a_source_name_that_is_not_one_lower_case_segment_makes_no_slot(name: str) -> None:
    """The name is the path, so a name that is not one segment could be walked into another slot:
    `xero/../providers/anthropic` is the key every question is sent with. Delete this and the slot
    rule can loosen to whatever a source's display name looks like. The positive half is the longest
    name the grammar admits, which is also a subject the ledger can hold."""
    with pytest.raises(ValueError, match="not a source name"):
        connector_key_slot(name)
    longest = connector_key_slot("a" * 63)
    assert credential_subject_id(longest.path) == "connector_keys." + "a" * 63


def test_the_console_s_credential_route_writes_no_connected_source_s_slot() -> None:
    """`SLOTS` is what `brain.credential_routes` admits under `admin:credential`, and it holds the
    provider keys and nothing under the connector prefix. Delete this and a source's key can be
    written without its settings under a different capability."""
    assert SLOTS
    assert not [path for path in SLOTS if path.startswith(CONNECTOR_KEY_PREFIX)]
