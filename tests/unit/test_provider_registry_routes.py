"""The provider registry from the console: terms, an added provider, and the exported register.

Driven through the real application with the estate `tests.unit.test_provider_routes` builds, a
session that records every statement, and an in-memory vault, so the order of the writes and
what reaches a response are inspected without a server.

Task ids: M5.6.4, M5.7.2, M5.1.3, M5.5.3
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.app import Settings, create_app
from brain.core.lane import Lane
from brain.models.calls import LadderState
from brain.models.disclosure import DataCategory
from brain.models.driver import LaneOverride
from brain.models.registry import ProviderKind, ProviderRecord
from brain.models.routing import ResidencyClass
from brain.ops.credentials import Credentials
from brain.ops.model_service import PROVIDER_NAMESPACE
from brain.ops.openbao import VaultUnreachableError
from brain.ops.provider_keys import AddedProviderSlots
from brain.provider_registry_routes import REGISTER_PATH, register_document
from tests.unit.test_credentials import KEY, Vault
from tests.unit.test_provider_routes import (
    PROVIDERS,
    Estate,
    Ledger,
    Questions,
    _service,
    _wiring,
    call,
)


@dataclass
class RegistryEstate(Estate):
    """The provider routes' estate, with registry rows and a log of every write statement."""

    providers: tuple[ProviderRecord, ...] = ()
    writes: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    async def current(self, now: datetime) -> LadderState:
        state = await super().current(now)
        return LadderState(
            rungs=state.rungs,
            switched_off=state.switched_off,
            attempts=state.attempts,
            providers=self.providers,
        )


_REGISTRY = RegistryEstate()


class RecordingSession(AsyncSession):
    """Records the INSERTs and UPDATEs a registry write makes; answers every read with nothing."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        table = getattr(getattr(statement, "table", None), "fullname", "")
        if getattr(statement, "is_insert", False) or getattr(statement, "is_update", False):
            verb = "insert" if statement.is_insert else "update"
            _REGISTRY.writes.append((verb, table, dict(statement.compile().params)))
            return None
        return _Empty()

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _Empty:
    def all(self) -> list[Any]:
        return []

    def scalars(self) -> _Empty:
        return self


@pytest.fixture
def registry() -> Iterator[RegistryEstate]:
    global _REGISTRY
    _REGISTRY = RegistryEstate()
    yield _REGISTRY


@pytest.fixture
def vault() -> Vault:
    return Vault()


@pytest.fixture
def client(registry: RegistryEstate, vault: Vault) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=RecordingSession)
        app.state.models.close()
        app.state.models = _service(registry)
        app.state.request_recorders = (Questions(), Ledger())
        app.state.credentials = Credentials(vault, environ={}, added=AddedProviderSlots())
        yield c


ADDED = {
    "slug": "acme_llm",
    "label": "Acme LLM",
    "base_url": "https://llm.example.test/v1",
    "models": ["acme-large", "acme-small"],
    "key": KEY,
}

TERMS = {
    "processing_region": "eu-west-1",
    "residency_class": "region_pinned",
    "storage_location": "Ireland, under the provider's EU data boundary",
    "retention_terms": "Zero retention of prompts and completions",
    "training_terms": "Not used for training",
    "agreement_url": "https://contracts.example.test/dpa.pdf",
    "lane_overrides": {"answer": {"timeout_seconds": 10}},
}


# ---------------------------------------------------------------- adding a provider (M5.7.2)
def test_an_added_provider_has_its_key_kept_in_its_own_slot_before_its_row_is_written(
    client: TestClient, registry: RegistryEstate, vault: Vault
) -> None:
    """M5.7.2: the address, the model names and the key, and no release.

    The key goes to `providers/acme_llm` and nowhere else, before the row; the row carries the
    address and models and no key; the response carries no key.

    Delete this and the row can be written with no key behind it, or the key can arrive in a row
    or a response."""
    response = call(client, "POST", "u_admin", PROVIDERS, ADDED)

    assert response.status_code == 200, response.text
    assert [path for path, _ in vault.written] == ["providers/acme_llm"]
    ((verb, table, row),) = registry.writes
    assert (verb, table) == ("insert", "ops.model_provider")
    assert row["kind"] == ProviderKind.OPENAI_COMPATIBLE.value
    assert row["base_url"] == ADDED["base_url"]
    assert row["models"] == ADDED["models"]
    assert KEY not in str(row)
    assert KEY not in response.text


def test_a_key_the_vault_could_not_keep_leaves_no_provider_behind(
    client: TestClient, registry: RegistryEstate, vault: Vault
) -> None:
    """`THE_KEY_IS_KEPT_BEFORE_THE_PROVIDER_EXISTS`: a silent vault is a 503 and no row.

    Delete this and a provider can be listed whose every call is refused for want of its key."""
    client.app.state.credentials = Credentials(  # type: ignore[attr-defined]
        Vault(fail=VaultUnreachableError("silent")), environ={}, added=AddedProviderSlots()
    )

    response = call(client, "POST", "u_admin", PROVIDERS, ADDED)

    assert response.status_code == 503
    assert registry.writes == []
    assert KEY not in response.text


def test_adding_a_provider_needs_both_the_matrix_write_and_the_credential_authority(
    client: TestClient, registry: RegistryEstate, vault: Vault
) -> None:
    """`ADDING_A_PROVIDER_IS_A_ROUTE_CHANGE_AND_A_KEY_WRITE`. `u_wide` holds the matrix write
    and not the credential authority; `u_elsewhere` holds the write over one department.

    Delete this and somebody who may switch providers can write a key every question goes out
    with, or a department's editor can add a provider for everybody."""
    for pid in ("u_wide", "u_elsewhere", "u_narrow", "u_none"):
        assert call(client, "POST", pid, PROVIDERS, ADDED).status_code == 404, pid
    assert vault.written == []
    assert registry.writes == []


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("slug", "anthropic"),
        ("slug", "local"),
        ("slug", "Bad Name"),
        ("base_url", "http://llm.example.test/v1"),
        ("base_url", "https://user:pw@llm.example.test"),
        ("base_url", "https://llm.example.test/v1?x=1"),
    ],
)
def test_a_provider_that_would_take_a_built_in_name_or_a_non_https_address_is_refused(
    client: TestClient, registry: RegistryEstate, vault: Vault, change: str, value: str
) -> None:
    """A built-in slug would be a second writer of that provider's key; an address that is not
    plain https would send a bearer key in the clear or smuggle a credential.

    Delete this and `openai` can be added at an address a person typed."""
    response = call(client, "POST", "u_admin", PROVIDERS, {**ADDED, change: value})

    assert response.status_code == 422
    assert vault.written == []
    assert registry.writes == []
    assert KEY not in response.text


def test_the_added_provider_is_listed_with_its_address_and_can_be_switched(
    client: TestClient, registry: RegistryEstate
) -> None:
    """Listed, switched and checked like a built-in one. Delete this and an added provider is
    in the database and invisible on the Models screen."""
    registry.providers = (
        ProviderRecord(
            slug="acme_llm",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            label="Acme LLM",
            base_url="https://llm.example.test/v1",
            models=("acme-large",),
        ),
    )

    view = call(client, "GET", "u_narrow", PROVIDERS).json()
    listed = [one["provider"] for one in view["providers"]]
    added = next(one for one in view["providers"] if one["provider"] == "acme_llm")

    assert listed[-2:] == ["acme_llm", "local"]
    assert added["registered"]["base_url"] == "https://llm.example.test/v1"
    assert added["description"] == "Acme LLM"
    switched = call(client, "PUT", "u_wide", f"{PROVIDERS}/acme_llm", {"on": False})
    assert switched.status_code == 200
    keys = [row.get("key") for _, table, row in registry.writes if table == "ops.setting"]
    assert keys == [f"{PROVIDER_NAMESPACE}.acme_llm"]


# ------------------------------------------------------------------ recording terms (M5.6.4)
def test_terms_recorded_for_a_built_in_provider_write_its_first_registry_row(
    client: TestClient, registry: RegistryEstate
) -> None:
    """M5.6.4 and M5.5.3: region, residency, storage, retention, training, the agreement and the
    lane overrides, on the provider's own row.

    Delete this and the terms screen saves nothing a register could export."""
    response = call(client, "PUT", "u_wide", f"{PROVIDERS}/anthropic/terms", TERMS)

    assert response.status_code == 200, response.text
    ((verb, table, row),) = registry.writes
    assert (verb, table) == ("insert", "ops.model_provider")
    assert row["kind"] == ProviderKind.BUILTIN.value
    assert row["processing_region"] == "eu-west-1"
    assert row["residency_class"] == "region_pinned"
    assert row["agreement_url"] == TERMS["agreement_url"]
    assert row["lane_overrides"] == {"answer": {"timeout_seconds": 10.0}}
    assert "base_url" not in row


def test_a_lane_override_past_the_answer_lanes_budget_is_refused_before_it_is_written(
    client: TestClient, registry: RegistryEstate
) -> None:
    """M5.1.3: `driver.check_answer_lane_budget`, called when configuration changes.

    Delete this and an override can take a person's wait to minutes with nothing refusing it."""
    over = {**TERMS, "lane_overrides": {"answer": {"timeout_seconds": 600, "attempts": 5}}}

    response = call(client, "PUT", "u_wide", f"{PROVIDERS}/anthropic/terms", over)

    assert response.status_code == 422
    assert "budget" in response.text
    assert registry.writes == []


def test_a_pinned_residency_that_names_no_region_is_refused(
    client: TestClient, registry: RegistryEstate
) -> None:
    """A claim of residency always says where. Delete this and a provider can be recorded as
    region-pinned with no region, which no request could ever be routed to."""
    response = call(
        client,
        "PUT",
        "u_wide",
        f"{PROVIDERS}/anthropic/terms",
        {**TERMS, "processing_region": "global"},
    )

    assert response.status_code == 422
    assert registry.writes == []


def test_terms_are_the_matrix_write_over_everything_and_nothing_less(
    client: TestClient, registry: RegistryEstate
) -> None:
    """Delete this and a reader of the Models screen can rewrite what the company agreed."""
    for pid in ("u_narrow", "u_elsewhere", "u_none"):
        response = call(client, "PUT", pid, f"{PROVIDERS}/anthropic/terms", TERMS)
        assert response.status_code == 404, pid
    assert registry.writes == []


def test_a_provider_shows_what_it_was_sent_by_category_with_counts() -> None:
    """M5.6.4's list, from the attempt counts. Delete this and the screen draws terms and no
    record of what left for where."""
    from brain.provider_routes import providers_view
    from tests.unit.test_model_calls import Ladder, Scripted, executor, ok
    from tests.unit.test_model_calls import rung as calls_rung

    calls, _ = executor(Ladder((calls_rung("anthropic"),)), {"anthropic": Scripted(ok())})
    import asyncio

    from brain.core.entitlement import EntitlementSet

    plan = asyncio.run(calls.planned())
    view = providers_view(
        plan,
        switches={},
        reach=EntitlementSet(principal_id="u_x", grants=()),
        now=datetime(2999, 1, 1, tzinfo=UTC),
        vault=None,
        disclosed={"anthropic": {DataCategory.QUESTION: 7, DataCategory.DOCUMENT_PASSAGES: 3}},
    )
    anthropic = next(one for one in view.providers if one.provider == "anthropic")

    assert {one.category: one.attempts for one in anthropic.disclosed} == {
        DataCategory.QUESTION: 7,
        DataCategory.DOCUMENT_PASSAGES: 3,
    }


# ---------------------------------------------------------------------- the export (M5.6.4)
def test_the_register_exports_as_one_document_with_every_providers_terms_and_counts(
    client: TestClient, registry: RegistryEstate
) -> None:
    """One Markdown document a company can show, with the name the console saves it under.

    Delete this and the register lives only on a screen."""
    registry.providers = (
        ProviderRecord(
            slug="anthropic",
            kind=ProviderKind.BUILTIN,
            label="Claude",
            processing_region="eu-west-1",
            residency_class=ResidencyClass.REGION_PINNED,
            retention_terms="Zero retention",
            training_terms="Not used for training",
            agreement_url="https://contracts.example.test/dpa.pdf",
        ),
    )

    response = call(client, "GET", "u_narrow", f"/api/v1{REGISTER_PATH}")

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "model-provider-register.md"
    document = body["document"]
    assert "## Claude (anthropic)" in document
    assert "- Retention terms: Zero retention" in document
    assert "- Signed agreement: https://contracts.example.test/dpa.pdf" in document
    assert "## moonshot" in document


def test_the_register_document_lists_the_counts_and_says_when_nothing_was_recorded() -> None:
    """Delete this and a provider with no terms reads as one whose terms are blank."""
    document = register_document(
        [],
        {"openai": {DataCategory.CHECK_SENTENCE: 2}},
        listed=("openai", "local"),
        at=datetime(2999, 1, 1, tzinfo=UTC),
    )

    assert "- No terms recorded." in document
    assert "The fixed provider-check sentence (no company data): 2 calls" in document
    assert "- Data sent: none recorded." in document


def test_the_register_is_not_served_to_somebody_who_cannot_read_the_models_screen(
    client: TestClient,
) -> None:
    """Delete this and the export is the screen's refusal with a side door."""
    assert call(client, "GET", "u_none", f"/api/v1{REGISTER_PATH}").status_code == 404


def test_a_lane_override_on_a_record_is_the_client_the_executor_applies() -> None:
    """The record's overrides are `driver.ProviderClient`'s, unchanged. Delete this and the
    Models screen and the executor can read the same row two ways."""
    record = ProviderRecord(
        slug="anthropic",
        kind=ProviderKind.BUILTIN,
        label="Claude",
        lane_overrides={Lane.ANSWER: LaneOverride(timeout_seconds=9.0)},
    )

    assert record.client.lanes[Lane.ANSWER].timeout_seconds == 9.0
    assert record.client.provider == "anthropic"


def test_an_added_provider_is_retired_and_a_built_in_one_cannot_be(
    client: TestClient, registry: RegistryEstate
) -> None:
    """Retiring is how an added provider's address is changed; a built-in provider is the
    product's and has no retirement. Delete this and `openai` can be retired from a screen, or an
    added provider can never be taken out."""
    registry.providers = (
        ProviderRecord(
            slug="acme_llm",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            label="Acme LLM",
            base_url="https://llm.example.test/v1",
            models=("acme-large",),
        ),
    )

    builtin = call(client, "POST", "u_wide", f"{PROVIDERS}/openai/retire")
    added = call(client, "POST", "u_wide", f"{PROVIDERS}/acme_llm/retire")

    assert builtin.status_code == 404
    assert added.status_code == 200
    ((verb, table, row),) = registry.writes
    assert (verb, table) == ("update", "ops.model_provider")
    assert row["updated_by"] == "u_wide"
