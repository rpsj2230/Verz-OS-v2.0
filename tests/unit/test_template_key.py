"""This install's template signing key: minted once into a write-once slot, never replaced, never
said, and the key `publish` signs with and `install` verifies with.

The vault is `KvSlot`, one kv version 2 slot answering as OpenBao answers the application's policy
in `ops/openbao/policies/application.hcl`: read and create, and no update, so a write to a slot that
already holds a version is refused before the check-and-set is even read. What the policy file
grants is held in `tests/unit/test_vault_policies.py`; that `OpenBaoVault` sends the check-and-set
is held here against the real class with its one network call replaced.

Task ids: M13.8.10, M13.8.18
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from brain.agent_lifecycle_routes import NO_SIGNING_KEY_HERE, template_key_of, version_unavailable
from brain.agents.catalogue import CATALOGUE
from brain.agents.template import TemplateError, install, publish, verify
from brain.app import Settings, create_app
from brain.deployment.installer import (
    PLAN,
    TEMPLATE_KEY_COMMAND,
    TEMPLATE_KEY_HELD_FLAG,
    step_named,
)
from brain.ops import template_key
from brain.ops.leases import SealedSecret
from brain.ops.openbao import (
    CREATE_ONLY_VERSION,
    TEMPLATE_KEY_PREFIX,
    OpenBaoVault,
    VaultRefusedError,
    VaultUnreachableError,
)
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.template_key import (
    HELD_FLAG,
    MIN_KEY_CHARS,
    TEMPLATE_KEY_FIELD,
    TEMPLATE_KEY_SAYS,
    TEMPLATE_KEY_SLOT,
    TemplateKeyReading,
    TemplateKeyState,
    keep_trying,
    look,
    mint_key,
    obtain,
)

#: Two keys as the module mints them, and a marker a leak search looks for. Each is a real key's
#: shape, so a check on the length cannot be what refuses them.
FIRST: Final = "a1" * 32
SECOND: Final = "b2" * 32
MARKER: Final = "5ec2e7" + "c0ffee" * 9 + "0d0d"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT: Final = datetime(2019, 3, 4, 5, 6, 7, tzinfo=UTC)

KEEP_STEP: Final = "keep this install's template signing key"


class KvSlot:
    """One kv version 2 slot under the application's policy: read, create, and no update.

    `policy_loaded=False` is a vault still enforcing the policy from before this release, which
    refuses every call on the path. `engine=False` is a loaded policy over an engine nobody enabled.
    `removed=True` is a slot whose version somebody with the unseal pieces deleted. `racing` is a
    key another process creates between this one's read and its create.
    """

    def __init__(
        self,
        value: str | None = None,
        *,
        policy_loaded: bool = True,
        engine: bool = True,
        removed: bool = False,
        sealed: bool = False,
        racing: str | None = None,
    ) -> None:
        self.versions: list[str] = [] if value is None else [value]
        self.policy_loaded = policy_loaded
        self.engine = engine
        self.removed = removed
        self.sealed = sealed
        self.racing = racing
        self.created: list[str] = []
        self.reads = 0

    def _refuse_if_closed(self) -> None:
        if self.sealed:
            raise VaultRefusedError("vault refused GET on a template_signing path: 503", status=503)
        if not self.policy_loaded:
            raise VaultRefusedError("vault refused on a template_signing path: 403", status=403)
        if not self.engine:
            raise VaultRefusedError("vault refused on a template_signing path: 404", status=404)

    def read_static_kv(self, path: str) -> dict[str, object]:
        assert path == TEMPLATE_KEY_SLOT
        self.reads += 1
        self._refuse_if_closed()
        if not self.versions or self.removed:
            raise VaultRefusedError("vault refused GET on a template_signing path: 404", status=404)
        return {TEMPLATE_KEY_FIELD: self.versions[-1]}

    def create_static_kv_once(self, path: str, fields: Mapping[str, str]) -> bool:
        assert path == TEMPLATE_KEY_SLOT
        self._refuse_if_closed()
        if self.racing is not None:
            self.versions.append(self.racing)
            self.racing = None
        if self.versions:
            # The policy grants no update, and a write to a slot with a version is an update.
            raise VaultRefusedError(
                "vault refused POST on a template_signing path: 403", status=403
            )
        self.created.append(fields[TEMPLATE_KEY_FIELD])
        self.versions.append(fields[TEMPLATE_KEY_FIELD])
        return True


def minting(*values: str) -> Any:
    """A mint that hands out `values` in order, and fails the test if asked once more."""
    queue = list(values)

    def mint() -> str:
        assert queue, "a key was minted that nothing should have asked for"
        return queue.pop(0)

    return mint


def revealed(found: TemplateKeyReading) -> str:
    assert found.key is not None, found.state
    return found.key.reveal()


# ----------------------------------------------------------- minted once, never replaced
def test_an_empty_slot_is_minted_once_and_every_later_start_reads_the_same_key() -> None:
    """The first start mints; every start after reads, and never mints again. Delete this and a
    second start that mints over the first key passes, and every template version the first key
    signed stops installing on that install."""
    slot = KvSlot()

    first = obtain(slot, mint=minting(FIRST))
    later = obtain(slot, mint=minting())
    again = obtain(slot, mint=minting())

    assert (first.state, later.state, again.state) == (TemplateKeyState.HELD,) * 3
    assert revealed(first) == revealed(later) == revealed(again) == FIRST
    assert slot.created == [FIRST]
    assert slot.versions == [FIRST]


def test_a_key_already_held_is_used_and_nothing_is_written() -> None:
    """The sibling from the other side: a slot that holds a key is read, and no create is even
    attempted. Delete this and a start that always tries a create passes, leaving a refused write
    in the vault's audit log on every start of every process."""
    slot = KvSlot(SECOND)

    found = obtain(slot, mint=minting())

    assert revealed(found) == SECOND
    assert slot.created == []


def test_two_processes_starting_together_both_use_the_key_the_vault_kept() -> None:
    """Several application processes start at once. The one whose create lands second is refused,
    and it must sign with the key the vault kept and not the one it minted. Delete this and a
    process can hold a key the vault does not, and sign versions no other process can verify."""
    slot = KvSlot(racing=FIRST)

    found = obtain(slot, mint=minting(SECOND))

    assert revealed(found) == FIRST
    assert slot.versions == [FIRST]
    assert slot.created == []


def test_a_slot_whose_key_was_removed_is_not_filled_again() -> None:
    """Only somebody with the unseal pieces can delete a version, and minting again after that
    would replace the key by another route. Delete this and removing the key and restarting the
    application is a way to swap the key every signed version is verified with."""
    slot = KvSlot(FIRST, removed=True)

    found = obtain(slot, mint=minting(SECOND))

    assert (found.state, found.key) == (TemplateKeyState.UNUSABLE, None)
    assert slot.versions == [FIRST]


def test_a_value_in_the_slot_that_is_not_a_key_this_product_made_is_not_used() -> None:
    """A short value is not one `mint_key` made, and signing with it would be signing with a weaker
    key than the product promises. Delete this and whatever somebody typed into the slot by hand
    signs templates."""
    short = obtain(KvSlot("x" * (MIN_KEY_CHARS - 1)), mint=minting())
    exact = obtain(KvSlot("x" * MIN_KEY_CHARS), mint=minting())

    assert (short.state, short.key) == (TemplateKeyState.UNUSABLE, None)
    assert exact.state is TemplateKeyState.HELD
    assert len(mint_key()) == MIN_KEY_CHARS
    assert mint_key() != mint_key()


# ------------------------------------------------- the vault's own create-only semantics
class Recording(OpenBaoVault):
    """The real client with its one network call replaced, keeping every body and answering 400
    when the check-and-set does not match, as kv version 2 does."""

    def __init__(self, *, holds: bool = False, status: int | None = None) -> None:
        super().__init__("http://vault:8200", "a-token")
        self.sent: list[tuple[str, str, dict[str, Any] | None]] = []
        self.holds = holds
        self.status = status

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.sent.append((method, path, body))
        if self.status is not None:
            raise VaultRefusedError(
                f"vault refused {method}: HTTP {self.status}", status=self.status
            )
        if self.holds:
            raise VaultRefusedError(f"vault refused {method}: HTTP 400", status=400)
        return {"data": {"version": 1}}


def test_the_create_sends_the_vaults_check_and_set_at_version_zero() -> None:
    """kv version 2 accepts a write carrying `cas: 0` only while the slot has never held a version,
    and answers 400 otherwise, which this reads as "already held" and never as a failure. Delete
    this and the create is an ordinary write, and a caller holding a wider token than the
    application's (the installer's, or somebody's pasted root token) replaces the key."""
    fresh = Recording()
    held = Recording(holds=True)

    assert fresh.create_static_kv_once(TEMPLATE_KEY_SLOT, {TEMPLATE_KEY_FIELD: FIRST}) is True
    assert held.create_static_kv_once(TEMPLATE_KEY_SLOT, {TEMPLATE_KEY_FIELD: SECOND}) is False

    assert CREATE_ONLY_VERSION == 0
    assert fresh.sent == [
        (
            "POST",
            "template_signing/data/key",
            {"options": {"cas": 0}, "data": {TEMPLATE_KEY_FIELD: FIRST}},
        )
    ]
    with pytest.raises(VaultRefusedError) as refused:
        Recording(status=403).create_static_kv_once(TEMPLATE_KEY_SLOT, {TEMPLATE_KEY_FIELD: FIRST})
    assert refused.value.status == 403


def test_the_ordinary_write_refuses_the_template_key_and_still_writes_a_provider_key() -> None:
    """`write_static_kv` is what every console credential goes through, and it carries no
    check-and-set. Delete this and a route that reached it with the template key's path would
    replace the key under the application's own token wherever the policy were ever widened."""
    vault = Recording()

    with pytest.raises(SecretsUnavailableError, match="never written over"):
        vault.write_static_kv(TEMPLATE_KEY_SLOT, {TEMPLATE_KEY_FIELD: SECOND})
    vault.write_static_kv("providers/anthropic", {"api_key": "sk-something"})

    assert TEMPLATE_KEY_SLOT.startswith(TEMPLATE_KEY_PREFIX)
    assert [path for _, path, _ in vault.sent] == ["providers/data/anthropic"]


# --------------------------------------------------------- a vault that cannot give one
def test_a_vault_still_on_the_old_policy_leaves_no_key_and_says_it_waits_for_the_reload() -> None:
    """The owner's install until he loads this release's policies: the vault refuses the read, and
    no create is attempted, because every refusal is a line in the vault's audit log. Delete this
    and the screen says nothing while every publish and install is refused."""
    old = KvSlot(policy_loaded=False)
    unmounted = KvSlot(engine=False)

    waiting = obtain(old, mint=minting())
    no_engine = obtain(unmounted, mint=minting(FIRST))

    assert (waiting.state, waiting.key) == (TemplateKeyState.WAITING, None)
    assert (no_engine.state, no_engine.key) == (TemplateKeyState.WAITING, None)
    assert old.created == [] and unmounted.created == []
    assert "waiting for the vault policy reload" in waiting.told
    assert look(old).state is TemplateKeyState.WAITING


def test_no_vault_holds_no_key_anywhere_and_a_sealed_one_is_not_read_yet() -> None:
    """M13.8.18: an install with no vault keeps the key nowhere else. A sealed vault is the other
    way to hold none, and says it will be asked again. Delete this and either reads as held."""
    none = obtain(None)
    sealed = obtain(KvSlot(FIRST, sealed=True), mint=minting())

    assert (none.state, none.key) == (TemplateKeyState.NO_VAULT, None)
    assert (sealed.state, sealed.key) == (TemplateKeyState.UNREAD, None)
    assert "kept nowhere else" in none.told
    assert set(TEMPLATE_KEY_SAYS) == set(TemplateKeyState)
    with pytest.raises(ValueError, match="exactly when"):
        TemplateKeyReading(TemplateKeyState.WAITING, SealedSecret(FIRST))
    with pytest.raises(ValueError, match="exactly when"):
        TemplateKeyReading(TemplateKeyState.HELD)


def test_a_process_whose_vault_was_sealed_at_start_asks_again_until_it_answers() -> None:
    """A server that rebooted starts the application before anybody opens the vault. Delete this and
    publishing stays unavailable until somebody restarts the application, with the vault open and
    every other key back in use. The sibling: a refusal is not asked again."""
    answers = [
        TemplateKeyReading(TemplateKeyState.UNREAD),
        TemplateKeyReading(TemplateKeyState.HELD, SealedSecret(FIRST)),
    ]
    held: list[TemplateKeyState] = []
    slept: list[float] = []

    async def attempt() -> TemplateKeyReading:
        return answers.pop(0)

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    final = asyncio.run(
        keep_trying(attempt, lambda found: held.append(found.state), every=60.0, sleep=sleep)
    )

    assert final.state is TemplateKeyState.HELD
    assert held == [TemplateKeyState.UNREAD, TemplateKeyState.HELD]
    assert slept == [60.0, 60.0]

    refused = [TemplateKeyReading(TemplateKeyState.WAITING)]

    async def refusing() -> TemplateKeyReading:
        return refused.pop(0)

    stopped = asyncio.run(keep_trying(refusing, lambda _found: None, every=1.0, sleep=sleep))
    assert stopped.state is TemplateKeyState.WAITING and refused == []


# ------------------------------------------------------------ the application holds it
def test_the_application_holds_at_start_the_key_the_vault_gave_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`app.state.template_key` is the one place every agent route reads the key, and until this
    module nothing set it. Delete this and the lifespan can read the key and put it nowhere, and
    every install and publish on a real install says the key is missing."""
    slot = KvSlot()
    monkeypatch.setattr(
        "brain.app.template_key_at_start", lambda _a, _t: obtain(slot, mint=minting(FIRST))
    )
    app = create_app(Settings(env="development", database_url=""))

    with TestClient(app):
        request = Request({"type": "http", "app": app})
        assert template_key_of(request) == FIRST
        assert app.state.template_key_state is TemplateKeyState.HELD
    assert slot.created == [FIRST]


def test_with_no_key_readable_installing_keeps_its_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sibling: a vault that refuses leaves the key unset, and a version's page answers
    `NO_SIGNING_KEY_HERE`, the sentence the inert Publish, Install and Duplicate controls draw.
    Delete this and a refusal could leave an empty string where the routes read a key. The
    install with no vault at all, the development settings, holds none either."""
    signed = publish(CATALOGUE[0], key=FIRST, signed_by="system", at=AT)
    plain = create_app(Settings(env="development", database_url=""))
    with TestClient(plain):
        assert plain.state.template_key is None
        assert plain.state.template_key_state is TemplateKeyState.NO_VAULT

    monkeypatch.setattr(
        "brain.app.template_key_at_start", lambda _a, _t: obtain(KvSlot(policy_loaded=False))
    )
    app = create_app(Settings(env="development", database_url=""))
    with TestClient(app):
        request = Request({"type": "http", "app": app})
        assert app.state.template_key is None
        assert app.state.template_key_state is TemplateKeyState.WAITING
        assert version_unavailable(signed, template_key_of(request)) == NO_SIGNING_KEY_HERE


def test_publish_signs_with_the_install_key_and_install_verifies_with_it() -> None:
    """The point of the whole module: a version signed with the key this install holds installs
    here, and one signed by another install's key is refused. Delete this and a key that reached
    the routes but was not the one publish used would pass every other test here."""
    ours = revealed(obtain(KvSlot(), mint=minting(FIRST)))
    theirs = revealed(obtain(KvSlot(), mint=minting(SECOND)))
    manifest = CATALOGUE[0]

    signed = publish(manifest, key=ours, signed_by="u_admin", at=AT)
    verify(signed, key=ours)
    instance = install(signed, key=ours, instance_id="agent_one", created_by="u_admin", at=AT)

    assert instance.content_digest == signed.content_digest
    with pytest.raises(TemplateError, match="not made by this installation's key"):
        verify(signed, key=theirs)
    with pytest.raises(TemplateError, match="not made by this installation's key"):
        install(
            publish(manifest, key=theirs, signed_by="u_admin", at=AT),
            key=ours,
            instance_id="agent_two",
            created_by="u_admin",
            at=AT,
        )


# ---------------------------------------------------------------- the key is never said
def test_the_key_never_appears_in_a_reading_a_log_line_or_the_commands_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A marker minted into the slot and read back, through every rendering a reading has, every
    log line the module writes and the command the installer runs. **The positive half:** the
    vault holds the marker and the reading reveals it, so a module that held nothing could not
    pass. Delete this and the key can reach a log line, which is kept for a month and read by
    whoever holds the log."""
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    slot = KvSlot()

    minted = obtain(slot, mint=minting(MARKER))
    read = obtain(slot, mint=minting())
    monkeypatch.setattr(template_key, "vault_for", lambda _a, _t: slot)
    assert template_key.main([]) == 0
    assert template_key.main([HELD_FLAG]) == 0

    written = capsys.readouterr()
    rendered = [repr(minted), str(minted), f"{minted}", repr(read), repr(minted.key)]
    everything = "\n".join([*rendered, written.out, written.err, caplog.text])
    assert MARKER not in everything
    assert revealed(minted) == revealed(read) == MARKER
    assert slot.versions == [MARKER]
    assert TEMPLATE_KEY_SAYS[TemplateKeyState.HELD] in written.out


# ----------------------------------------------------------------- the installer's step
def test_the_installer_step_mints_after_readiness_and_its_done_test_writes_nothing() -> None:
    """The step runs the module's command in the application container once readiness and
    furnishing are done and before the setup code is shown, and it is skipped when the key is held
    or the install declined the vault. Delete this and the done test can be the minting command,
    so a re-run of the installer writes, or the step can run before the application exists."""
    step = step_named(KEEP_STEP)
    names = [one.name for one in PLAN]

    assert template_key.__name__ == TEMPLATE_KEY_COMMAND
    assert TEMPLATE_KEY_HELD_FLAG == HELD_FLAG
    assert step.changes and not step.presents_once
    assert step.run == (
        f"docker compose $BRAIN_COMPOSE_FILES exec -T app python -m {TEMPLATE_KEY_COMMAND}"
    )
    assert step.already_done == (
        'test "${BRAIN_VAULT:-yes}" = "no" || docker compose $BRAIN_COMPOSE_FILES exec -T app '
        f"python -m {TEMPLATE_KEY_COMMAND} {HELD_FLAG}"
    )
    assert names.index("wait for the application to report ready") < names.index(KEEP_STEP)
    assert names.index("furnish the install") < names.index(KEEP_STEP)
    assert names.index(KEEP_STEP) == names.index("present the setup code, once") - 1


def test_the_installer_step_is_idempotent_and_its_done_test_only_reads() -> None:
    """Run twice, the step's command mints once and then finds the key held, and the done test is
    true exactly when it is held and never creates. Delete this and a second run of the installer
    on a half-finished install replaces the key the first run kept."""
    slot = KvSlot()

    assert look(slot).state is TemplateKeyState.WAITING
    assert slot.created == []
    first = obtain(slot, mint=minting(FIRST))
    second = obtain(slot, mint=minting())

    assert revealed(first) == revealed(second) == FIRST
    assert look(slot).state is TemplateKeyState.HELD
    assert slot.created == [FIRST]
    assert look(None).state is TemplateKeyState.NO_VAULT


def test_the_command_refuses_other_arguments_and_fails_when_the_vault_refuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The installer reads the command's exit status. Delete this and a refusing vault can report
    success, and the install finishes with publishing silently unavailable."""
    monkeypatch.setattr(template_key, "vault_for", lambda _a, _t: KvSlot(policy_loaded=False))

    assert template_key.main(["--force"]) == 2
    assert template_key.main([]) == 1
    assert template_key.main([HELD_FLAG]) == 1
    assert TEMPLATE_KEY_SAYS[TemplateKeyState.WAITING] in capsys.readouterr().out

    def silent(_a: str, _t: str) -> Any:
        class Silent:
            def read_static_kv(self, _path: str) -> dict[str, object]:
                raise VaultUnreachableError("did not answer")

        return Silent()

    monkeypatch.setattr(template_key, "vault_for", silent)
    assert template_key.main([]) == 1
