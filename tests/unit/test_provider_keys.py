"""Provider API keys out of the vault. Every test is a way a key leaks or a way leasing
gets routed around.

Task ids: M5.1.2, M27.8.7
"""

from __future__ import annotations

from typing import Any

import pytest

from brain.ops.openbao import OpenBaoVault, VaultUnreachableError
from brain.ops.provider_keys import (
    PROVIDER_SLOTS,
    STATIC_PREFIX,
    ProviderSlot,
    assert_static_path,
    load_into_environment,
    names_in_environment,
    put_into_environment,
    read_static,
)
from brain.ops.secrets import SecretsUnavailableError

KEY = "sk-ant-a-real-looking-key-value"


class FakeVault(OpenBaoVault):
    """The real class with its one network call replaced, and a record of what was asked."""

    def __init__(self, values: dict[str, dict[str, Any]] | None = None) -> None:
        super().__init__("http://vault:8200", "a-token")
        self.paths: list[str] = []
        self._values = values if values is not None else {}

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.paths.append(path)
        if path in self._values:
            # kv v2's real shape, nested twice. Written out rather than flattened because
            # the un-nesting is the part most likely to be got wrong.
            return {"data": {"data": self._values[path], "metadata": {"version": 1}}}
        raise SecretsUnavailableError("no value there")


def _vault_with_anthropic() -> FakeVault:
    return FakeVault({"providers/data/anthropic": {"api_key": KEY}})


# --------------------------------------------------- the boundary with leasing
def test_a_path_outside_the_provider_prefix_is_refused() -> None:
    """The check that stops this becoming a general read-by-path.

    `providers/anthropic` is a key nobody can lease: there is no engine that mints a fresh
    OpenAI key per request. `connectors/creds/xero` is one somebody should, and reading it
    here would work perfectly and be invisible - a standing credential handed out with
    nothing to revoke and no record of which run held it.

    Deleting this quietly undoes the entire leasing design, and nothing else in the tree
    would notice."""
    with pytest.raises(SecretsUnavailableError, match="leased"):
        assert_static_path("connectors/creds/xero")
    with pytest.raises(SecretsUnavailableError):
        assert_static_path("database/creds/laravel")
    with pytest.raises(SecretsUnavailableError):
        assert_static_path("secret/data/anything")


def test_the_provider_prefix_itself_is_allowed() -> None:
    assert_static_path(f"{STATIC_PREFIX}anthropic")


def test_the_guard_lives_on_the_vault_and_not_only_on_the_caller() -> None:
    """A guard on the caller is a guard somebody bypasses by calling the other thing. This
    asserts the refusal happens inside `read_static_kv`, so there is no route to a connector
    credential through this object at all - not through this module, and not around it."""
    v = FakeVault({"connectors/data/creds/xero": {"api_key": "leaked"}})
    with pytest.raises(SecretsUnavailableError, match="leased"):
        v.read_static_kv("connectors/creds/xero")


def test_this_module_does_not_implement_the_vault_protocol() -> None:
    """Structural, and it is the point of the file existing separately. Somebody reaching
    for `borrow()` and finding it does not work here should have to notice why: a provider
    key has nothing to hand back, and wrapping one in a `Lease` with an invented expiry
    would make the caller believe it stops working at a time nothing enforces."""
    import brain.ops.provider_keys as mod

    assert not hasattr(mod, "issue")
    assert not hasattr(mod, "revoke")
    assert not hasattr(mod, "borrow")


# ------------------------------------------------------------------ reading
def test_a_key_is_read_out_of_the_kv_engine() -> None:
    """The happy path, and it goes through the real nesting: kv v2 wraps the value twice and
    a reader that unwrapped once would return the metadata block."""
    assert read_static(_vault_with_anthropic(), "providers/anthropic") == KEY


def test_the_kv_v2_data_path_is_used_and_not_the_logical_one() -> None:
    """`providers/anthropic` is the path a person writes; `providers/data/anthropic` is the
    one the API answers on. Getting this wrong returns a 404 that reads as "the slot is
    empty" rather than "the path is wrong", and somebody then puts the key in twice."""
    v = _vault_with_anthropic()
    read_static(v, "providers/anthropic")
    assert v.paths == ["providers/data/anthropic"]


def test_an_empty_slot_says_so_rather_than_returning_nothing() -> None:
    """Every slot is defined and empty before go-live. An empty string handed to an SDK
    produces an authentication error from the provider, which reads as a bad key rather
    than as no key."""
    v = FakeVault({"providers/data/anthropic": {"api_key": "   "}})
    with pytest.raises(SecretsUnavailableError, match="empty value"):
        read_static(v, "providers/anthropic")


def test_fields_this_does_not_recognise_are_refused() -> None:
    """Guessing is how the wrong string gets sent as a key, producing an authentication
    error nobody can explain."""
    v = FakeVault({"providers/data/anthropic": {"note": "put the key here"}})
    with pytest.raises(SecretsUnavailableError, match="does not recognise"):
        read_static(v, "providers/anthropic")


# ------------------------------------------------------- into the environment
def test_loading_returns_names_and_never_values() -> None:
    """A function handing back keys is a function whose return value must not be logged, and
    every caller would have to know that. Names are safe to print, which is what makes a
    startup line naming what was loaded possible at all.

    Deleting this invites a `return keys` that looks harmless in review."""
    env: dict[str, str] = {}
    loaded = load_into_environment(_vault_with_anthropic(), PROVIDER_SLOTS, environ=env)
    assert loaded == ("ANTHROPIC_API_KEY",)
    assert KEY not in str(loaded)
    # The key did reach the environment, which is where the SDK reads it and where the
    # adapter argues it should live: not in a request object, not in a trace.
    assert env["ANTHROPIC_API_KEY"] == KEY


def test_an_unconfigured_provider_is_skipped_rather_than_fatal() -> None:
    """Before go-live every slot is empty by design. Refusing to start would mean the system
    cannot run until every provider is configured, including the ones this deployment does
    not use."""
    env: dict[str, str] = {}
    loaded = load_into_environment(_vault_with_anthropic(), PROVIDER_SLOTS, environ=env)
    assert "OPENAI_API_KEY" not in env
    assert "OPENAI_API_KEY" not in loaded


def test_a_provider_this_deployment_requires_is_fatal_when_missing() -> None:
    """The other half. Starting without the key the system routes every question to means
    every question fails at the model call, one at a time, with an authentication error -
    rather than the process saying plainly at boot that a slot is empty."""
    with pytest.raises(SecretsUnavailableError, match="requires them"):
        load_into_environment(
            _vault_with_anthropic(), PROVIDER_SLOTS, environ={}, required=frozenset({"openai"})
        )


def test_a_key_already_in_the_environment_is_left_alone() -> None:
    """A developer running with a key in their shell means it. Overwriting it silently makes
    their explicit choice ineffective, which is a confusing hour spent on the wrong thing."""
    env = {"ANTHROPIC_API_KEY": "sk-ant-my-own-key"}
    load_into_environment(_vault_with_anthropic(), PROVIDER_SLOTS, environ=env)
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-my-own-key"


def test_an_already_set_key_still_counts_as_loaded() -> None:
    """Otherwise the startup line says a provider is unconfigured when it is configured, and
    somebody goes looking for a problem that does not exist."""
    env = {"ANTHROPIC_API_KEY": "sk-ant-my-own-key"}
    loaded = load_into_environment(_vault_with_anthropic(), PROVIDER_SLOTS, environ=env)
    assert "ANTHROPIC_API_KEY" in loaded


def test_the_vault_is_not_asked_for_a_key_that_is_already_set() -> None:
    """A read that is not needed is a read in the vault's audit log for no reason, and the
    log is read to spot unusual access."""
    v = _vault_with_anthropic()
    load_into_environment(v, PROVIDER_SLOTS, environ={"ANTHROPIC_API_KEY": "x"})
    assert "providers/data/anthropic" not in v.paths


# ------------------------------------------------------------------ the slots
def test_every_slot_declares_its_environment_variable_rather_than_deriving_it() -> None:
    """Upper-casing the slug and appending `_API_KEY` is right for three providers and wrong
    for the fourth, and being wrong means the SDK silently falls back to an unauthenticated
    call or to a key left over from something else."""
    for slot in PROVIDER_SLOTS:
        assert slot.env_var
        assert slot.description, f"{slot.slug} has no note saying what it is for"


@pytest.mark.parametrize("bad", ["Anthropic", "an-thropic", "", "a" * 40, "1provider"])
def test_a_slug_that_is_not_a_slug_is_refused(bad: str) -> None:
    """Interpolated into a vault path and used to build an environment variable name, so it
    is validated rather than trusted."""
    with pytest.raises(ValueError, match="provider slug"):
        ProviderSlot(slug=bad, env_var="X_API_KEY")


@pytest.mark.parametrize("bad", ["lowercase_key", "9_KEY", "X"])
def test_an_environment_variable_name_that_is_not_one_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="environment variable"):
        ProviderSlot(slug="anthropic", env_var=bad)


# ---------------------------------------------- a vault that is silent, and a key just written
class Silent(FakeVault):
    """A vault that never answers, counting how often it was asked."""

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.paths.append(path)
        raise VaultUnreachableError("vault at http://vault:8200 did not answer within 5.0s")


def test_a_silent_vault_is_asked_once_at_start_and_every_slot_is_then_missing() -> None:
    """Each asking costs the client's whole timeout, and a vault that did not answer for one slot
    will not answer for the next inside the same second, so start-up asks once. The slots after it
    are still counted as missing, so a required one still stops the process. Delete this and a
    stopped vault adds its timeout once per provider to every start."""
    v = Silent()
    env: dict[str, str] = {}

    loaded = load_into_environment(v, PROVIDER_SLOTS, environ=env)

    assert v.paths == ["providers/data/anthropic"]
    assert (loaded, env) == ((), {})
    with pytest.raises(SecretsUnavailableError, match="moonshot"):
        load_into_environment(
            Silent(), PROVIDER_SLOTS, environ={}, required=frozenset({"moonshot"})
        )


def test_a_refusing_vault_is_asked_about_every_slot() -> None:
    """The sibling: a refusal is about one slot, a policy or an empty path, and the next slot can
    still be there. Delete this and the short cut for silence can widen to every failure, and one
    empty slot hides every key after it."""
    v = FakeVault({"providers/data/moonshot": {"api_key": KEY}})
    env: dict[str, str] = {}

    loaded = load_into_environment(v, PROVIDER_SLOTS, environ=env)

    assert v.paths == [
        slot.path.replace("providers/", "providers/data/") for slot in PROVIDER_SLOTS
    ]
    assert loaded == ("MOONSHOT_API_KEY",)


def test_the_names_the_environment_sets_are_named_and_never_valued() -> None:
    """Asked before anything is loaded, so what it names is what outranks the vault on every start.
    A blank variable is not set. Delete this and a key written from the console into a slot the
    environment file also sets is reported as in use when the file's key is the one being used."""
    env = {"ANTHROPIC_API_KEY": KEY, "OPENAI_API_KEY": "", "UNRELATED": "x"}
    named = names_in_environment(PROVIDER_SLOTS, environ=env)
    assert named == frozenset({"ANTHROPIC_API_KEY"})
    assert KEY not in repr(named)


def test_a_key_just_written_is_handed_to_this_process_and_replaces_what_was_there() -> None:
    """Unlike the start-up load, which leaves an existing value alone, this overwrites: the value
    in hand is the one an administrator chose a moment ago. Whether it should be handed over at all
    is decided by the caller. Delete this and the process that answered "saved" keeps the old
    key."""
    slot = PROVIDER_SLOTS[0]
    env = {slot.env_var: "sk-the-old-one"}

    put_into_environment(slot, KEY, environ=env)
    assert env == {slot.env_var: KEY}


def test_an_empty_key_is_never_handed_to_a_provider_sdk() -> None:
    """An empty key reaches the provider as an unauthenticated call that reads as a bad key.
    Delete this and a blank written by mistake silently replaces a working key in this process."""
    env = {"ANTHROPIC_API_KEY": KEY}
    with pytest.raises(SecretsUnavailableError, match="empty"):
        put_into_environment(PROVIDER_SLOTS[0], "   ", environ=env)
    assert env == {"ANTHROPIC_API_KEY": KEY}
