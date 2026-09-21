"""The provider registry's rules, the disclosure counts, and how an added provider is reached.

Pure where the modules are pure; the key slot, the wire and the refresh are driven with an
in-memory environment and vault.

Task ids: M5.6.4, M5.5.3, M5.1.3, M5.7.1, M5.7.2, M5.3.2
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from brain.core.lane import Lane
from brain.models.disclosure import DataCategory, categories_of, counted
from brain.models.registry import (
    HTTPS_ADDRESS_PATTERN,
    SLUG_PATTERN,
    ModelPin,
    ProviderKind,
    ProviderRecord,
    RegistryError,
    check_added,
    parse_lane_overrides,
    record_of,
)
from brain.models.routing import ResidencyClass
from brain.models.wire import PROVIDER_WIRES, Wire, added_wire
from brain.ops.model_service import AddedProviderDrivers, disclosure_counts
from brain.ops.provider_keys import (
    PROVIDER_SLOTS,
    SLUG_RE,
    AddedProviderSlots,
    added_slot,
    put_into_environment,
)
from brain.tables.model_registry import ModelProviderRow

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations" / "versions" / "0097_model_registry_and_matrix_gate.py"


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0097", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- the patterns
def test_the_slug_and_address_rules_are_one_rule_in_python_in_the_model_and_in_the_migration() -> (
    None
):
    """Three copies held equal: the registry's regex, the key slot's, and the migration's SQL.

    Delete this and a slug the console accepts can be one the database or the vault path refuses,
    which arrives as a 500 after the key was already written."""
    assert SLUG_RE.pattern == SLUG_PATTERN
    assert migration().PROVIDER_SLUG_PATTERN == SLUG_PATTERN
    assert migration().HTTPS_ADDRESS_PATTERN == HTTPS_ADDRESS_PATTERN
    table: Any = ModelProviderRow.__table__
    checks = {str(c.name): str(c.sqltext) for c in table.constraints if hasattr(c, "sqltext")}
    assert checks["ck_model_provider_address_shape"] == (
        f"base_url IS NULL OR base_url ~ '{HTTPS_ADDRESS_PATTERN}'"
    )


@pytest.mark.parametrize(
    "address",
    [
        "https://llm.example.test",
        "https://llm.example.test/v1",
        "https://llm.example.test:8443/openai/v1",
    ],
)
def test_an_https_address_with_an_optional_path_is_admitted(address: str) -> None:
    """The positive half of the address rule. Delete this and a rule refusing everything passes."""
    assert re.fullmatch(HTTPS_ADDRESS_PATTERN, address)
    check_added("acme_llm", address, ("m",), taken=())


@pytest.mark.parametrize(
    "address",
    [
        "http://llm.example.test",
        "https://user:pw@llm.example.test",
        "https://llm.example.test/v1?key=x",
        "https://llm.example.test/#frag",
        "ftp://llm.example.test",
    ],
)
def test_an_address_that_is_not_plain_https_is_refused(address: str) -> None:
    """A bearer key goes to this address with every request. Delete this and it can go in the
    clear, or carry a credential or a query nobody reviewed."""
    with pytest.raises(RegistryError):
        check_added("acme_llm", address, ("m",), taken=())


def test_a_built_in_or_taken_name_and_bad_model_lists_are_refused() -> None:
    """Delete this and an added provider can be named `openai`, list no model, or list one
    twice."""
    builtin = tuple(one.slug for one in PROVIDER_SLOTS)
    with pytest.raises(RegistryError, match="already a provider"):
        check_added("openai", "https://x.example.test", ("m",), taken=builtin)
    with pytest.raises(RegistryError, match="between 1 and"):
        check_added("acme_llm", "https://x.example.test", (), taken=())
    with pytest.raises(RegistryError, match="twice"):
        check_added("acme_llm", "https://x.example.test", ("m", "m"), taken=())
    with pytest.raises(RegistryError, match="not a model name"):
        check_added("acme_llm", "https://x.example.test", ("bad model",), taken=())


# ----------------------------------------------------------------------- the record
def test_a_record_documented_as_pinned_carries_its_region_and_a_global_one_carries_none() -> None:
    """M5.5.3: the region a rung is assembled with is the documented one, and only when pinned.

    Delete this and a region typed beside a global class makes a rung satisfy a constraint the
    agreement never promised."""
    pinned = ProviderRecord(
        slug="moonshot",
        kind=ProviderKind.BUILTIN,
        label="Moonshot",
        processing_region="eu-west-1",
        residency_class=ResidencyClass.REGION_PINNED,
    )
    loose = ProviderRecord(
        slug="openai", kind=ProviderKind.BUILTIN, label="OpenAI", processing_region="eu-west-1"
    )

    assert pinned.region == "eu-west-1"
    assert loose.region == "global"
    with pytest.raises(RegistryError, match="names the region"):
        ProviderRecord(
            slug="x1",
            kind=ProviderKind.BUILTIN,
            label="x",
            residency_class=ResidencyClass.REGION_PINNED,
        )


def test_an_added_provider_has_an_address_and_a_built_in_one_never_does() -> None:
    """Delete this and a built-in provider's row can carry an address, which is the redirection
    `wire.A_PROVIDER_IS_REACHED_AT_ITS_OWN_ADDRESS_AND_NEVER_ONE_A_PERSON_TYPED` refuses."""
    with pytest.raises(RegistryError):
        ProviderRecord(
            slug="openai", kind=ProviderKind.BUILTIN, label="x", base_url="https://x.test"
        )
    with pytest.raises(RegistryError):
        ProviderRecord(slug="acme_llm", kind=ProviderKind.OPENAI_COMPATIBLE, label="x")


def test_a_stored_row_reads_back_into_the_record_the_executor_uses() -> None:
    """Delete this and the row and the record can disagree about a field the executor reads."""
    record = record_of(
        {
            "slug": "acme_llm",
            "kind": "openai_compatible",
            "label": "Acme",
            "base_url": "https://llm.example.test/v1",
            "models": ["a", "b"],
            "processing_region": "eu-west-1",
            "residency_class": "region_pinned",
            "lane_overrides": {"answer": {"timeout_seconds": 9, "attempts": 2}},
        }
    )

    assert record.models == ("a", "b")
    assert record.region == "eu-west-1"
    assert record.client.lanes[Lane.ANSWER].timeout_seconds == 9.0
    assert record.client.lanes[Lane.ANSWER].attempts == 2


@pytest.mark.parametrize(
    "raw",
    [
        {"fast": {"timeout_seconds": 5}},
        {"answer": {"timeout_seconds": 0}},
        {"answer": {"timeout_seconds": 601}},
        {"answer": {"attempts": 0}},
        {"answer": {"attempts": 6}},
        {"answer": {"attempts": True}},
        {"answer": {"max_concurrency": 3}},
        {"nonsense": {}},
    ],
)
def test_a_lane_override_the_executor_could_not_apply_is_refused(raw: dict[str, Any]) -> None:
    """M5.1.3's overrides are bounded where they are parsed. Delete this and a stored override is
    one the screen shows and `ProviderClient.policy_for` raises on at the first call."""
    with pytest.raises(RegistryError):
        parse_lane_overrides(raw)


def test_a_pin_is_a_provider_name_and_a_model_name() -> None:
    """Delete this and a pin can name anything, which no rung serves."""
    assert ModelPin(provider="moonshot", model="kimi-k2").model == "kimi-k2"
    with pytest.raises(RegistryError):
        ModelPin(provider="Moon Shot", model="kimi-k2")
    with pytest.raises(RegistryError):
        ModelPin(provider="moonshot", model="kimi k2")


# ------------------------------------------------------------------ the providers (M5.7.1)
def test_the_four_providers_the_owner_named_each_have_a_key_slot_and_a_wire() -> None:
    """M5.7.1: OpenAI, Anthropic, Moonshot and DeepSeek, each switched on with a key.

    Delete this and one of the four can be dropped from the product with every other test green."""
    assert {one.slug for one in PROVIDER_SLOTS} >= {"openai", "anthropic", "moonshot", "deepseek"}
    assert PROVIDER_WIRES["deepseek"].wire is Wire.CHAT_COMPLETIONS
    assert PROVIDER_WIRES["deepseek"].url == "https://api.deepseek.com/chat/completions"


def test_an_added_providers_slot_is_its_own_and_never_a_built_in_ones() -> None:
    """M5.7.2: `providers/<slug>`, which the application policy admits, and a variable no built-in
    provider uses.

    Delete this and an added provider named like a built-in one writes that provider's key."""
    slot = added_slot("acme_llm")

    assert slot.path == "providers/acme_llm"
    assert slot.env_var == "BRAIN_PROVIDER_ACME_LLM_KEY"
    assert slot.env_var not in {one.env_var for one in PROVIDER_SLOTS}
    with pytest.raises(ValueError, match="built-in"):
        added_slot("openai")


def test_an_added_wire_is_chat_completions_at_its_address_and_only_over_https() -> None:
    """Delete this and an added provider's bearer key can be sent over plain http."""
    wire = added_wire("acme_llm", "https://llm.example.test/v1", added_slot("acme_llm"))

    assert wire.url == "https://llm.example.test/v1/chat/completions"
    with pytest.raises(ValueError, match="https"):
        added_wire("acme_llm", "http://llm.example.test/v1", added_slot("acme_llm"))


def test_added_drivers_are_built_once_per_address_and_teach_the_refresh_their_slots() -> None:
    """The driver is kept while the address is unchanged, and the process learns the slot so the
    minute's key refresh loads its key.

    Delete this and every call builds a transport, or an added provider's key is never loaded."""
    built: list[str] = []

    def make(wire: Any, *, client: httpx.Client) -> Any:
        built.append(wire.url)
        return lambda request: None

    slots = AddedProviderSlots()
    drivers = AddedProviderDrivers(httpx.Client(), slots=slots, make_transport=make)
    added = ProviderRecord(
        slug="acme_llm",
        kind=ProviderKind.OPENAI_COMPATIBLE,
        label="Acme",
        base_url="https://llm.example.test/v1",
        models=("m",),
    )
    builtin = ProviderRecord(slug="openai", kind=ProviderKind.BUILTIN, label="OpenAI")

    assert set(drivers.drivers((added, builtin))) == {"acme_llm"}
    drivers.drivers((added,))
    assert built == ["https://llm.example.test/v1/chat/completions"]
    assert [one.slug for one in slots.slots()] == ["acme_llm"]


def test_an_added_providers_key_is_held_when_its_variable_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an added provider with a key is left out as holding none."""
    env: dict[str, str] = {}
    monkeypatch.setattr("brain.ops.provider_keys.process_environment", lambda: env)
    drivers = AddedProviderDrivers(httpx.Client(), slots=AddedProviderSlots())
    added = ProviderRecord(
        slug="acme_llm",
        kind=ProviderKind.OPENAI_COMPATIBLE,
        label="Acme",
        base_url="https://llm.example.test/v1",
        models=("m",),
    )

    assert drivers.held((added,)) == frozenset()
    put_into_environment(added_slot("acme_llm"), "k" * 24, environ=env)
    assert drivers.held((added,)) == frozenset({"acme_llm"})


# ------------------------------------------------------------------ disclosure (M5.6.4)
def test_counts_are_per_provider_and_category_and_an_unknown_category_is_dropped() -> None:
    """Delete this and a row written by a later release stops the register counting the rest."""
    found = counted(
        [
            ("anthropic", ["question", "document_passages"]),
            ("anthropic", ["question"]),
            ("moonshot", ["question", "a_future_kind"]),
        ]
    )

    assert found["anthropic"] == {DataCategory.QUESTION: 2, DataCategory.DOCUMENT_PASSAGES: 1}
    assert found["moonshot"] == {DataCategory.QUESTION: 1}
    assert categories_of(["a_future_kind"]) == ()
    assert disclosure_counts([("openai", "question", 4), ("openai", "nope", 9)]) == {
        "openai": {DataCategory.QUESTION: 4}
    }


def test_the_role_trigger_derives_what_the_chain_derives() -> None:
    """M5.3.2: the migration's trigger function is `RoutingChain.role_of` in SQL: the lowest
    live position is the primary, the same provider is a same-provider failover, any other is
    cross-provider. Read off the function's text beside the chain's own answers.

    Delete this and the database and the chain can call the same rung two different things."""
    function = migration().ROLE_FUNCTION
    assert "ORDER BY r.position" in function
    assert "NEW.position < v_position THEN\n        NEW.role := 'primary'" in function
    assert "v_provider = NEW.provider THEN\n        NEW.role := 'same_provider_failover'" in (
        function
    )
    assert "NEW.role := 'cross_provider_failover'" in function
    assert "BEFORE INSERT OR UPDATE ON ops.routing_rung" in migration().ROLE_TRIGGER
