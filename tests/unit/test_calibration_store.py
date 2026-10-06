"""The weekly fit's store: what is fitted, what is carried, when a fit is kept, and what promoting
one does, over a real schema as the application role.

Task ids: M14.3.5, M14.4.2, M14.4.4, M14.8.3
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from brain.resolution.calibration import PatternCount
from brain.resolution.calibration_store import (
    FITS_NAMESPACE,
    IN_FORCE_NAMESPACE,
    KEPT,
    NOT_DUE,
    agrees_with_reviewers,
    fitted,
)
from brain.resolution.canonical import ResolutionError
from brain.resolution.cascade import DECLARED_WEIGHTS, Feature

#: Far from any wall clock, for the reason `tests/unit/test_scope_and_capability.py` gives.
AT = datetime(2019, 3, 4, 12, tzinfo=UTC)
FIVE = (Feature.UEN, Feature.DOMAIN, Feature.NAME_EXACT, Feature.COUNTRY, Feature.POSTCODE)
SRC = Path(__file__).resolve().parents[2] / "src" / "brain"


def extract_of(strong_pairs: int = 40) -> list[PatternCount]:
    """Every subset of five features, many pairs agreeing on two strong ones, and many on none."""
    counts = []
    for size in range(1, len(FIVE) + 1):
        for subset in combinations(FIVE, size):
            pattern = frozenset(subset)
            strong = len(pattern & {Feature.UEN, Feature.DOMAIN, Feature.NAME_EXACT})
            pairs = strong_pairs if strong >= 2 else (5 if strong == 1 else 60)
            counts.append(PatternCount(pattern=pattern, pairs=pairs))
    return counts


# ------------------------------------------------------------------------ the pure half
def test_only_what_agreed_is_fitted_and_everything_else_carries_the_weight_in_force() -> None:
    """The five features some pair agreed on are fitted and named; the six nothing agreed on keep
    the declared weight and are named as carried.

    Delete this and either every install is refused a fit for lacking registration numbers, or a
    carried weight is read as a measured one."""
    fit = fitted(extract_of(), now=AT, previous=DECLARED_WEIGHTS)

    assert fit.fitted == frozenset(FIVE)
    assert fit.carried == frozenset(Feature) - frozenset(FIVE)
    for one in fit.carried:
        assert fit.weights[one] == DECLARED_WEIGHTS.weight_for(one)
    assert fit.weights[Feature.UEN] > DECLARED_WEIGHTS.weight_for(Feature.COUNTRY)
    assert fit.version == "fit_20190304t120000"


def test_an_extract_where_nothing_agreed_is_refused() -> None:
    """Delete this and a run over an install with no candidate pair keeps a fit of nothing."""
    with pytest.raises(ResolutionError, match="nothing to fit"):
        fitted([PatternCount(pattern=frozenset(), pairs=3)], now=AT, previous=DECLARED_WEIGHTS)


def test_a_fit_agrees_with_reviewers_who_merged_what_it_weighs_higher_and_not_otherwise() -> None:
    """Merged pairs scoring above the pairs people kept apart agree; the reverse disagrees; a
    sample with only one kind of decision says nothing.

    Delete this and a fit that learnt the opposite of the reviewers' decisions can be kept."""
    fit = fitted(extract_of(), now=AT, previous=DECLARED_WEIGHTS)
    strong = frozenset({Feature.UEN, Feature.DOMAIN})
    weak = frozenset({Feature.COUNTRY})

    assert agrees_with_reviewers(fit, [(strong, True), (weak, False)]) is True
    assert agrees_with_reviewers(fit, [(strong, False), (weak, True)]) is False
    assert agrees_with_reviewers(fit, [(strong, True)]) is None


def test_no_module_but_the_store_names_the_fits_namespaces() -> None:
    """The fits are read by namespace, so they stay out of every other settings reader as long as
    no other module names them.

    Delete this and a settings screen could start listing how much each agreement counts to a
    reader without the reviewer's capability."""
    named = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in (
                FITS_NAMESPACE,
                IN_FORCE_NAMESPACE,
            ):
                named.add(str(path.relative_to(SRC)))
    assert named == {"resolution/calibration_store.py"}


# ------------------------------------------------------------------ on a real schema
@pytest.fixture
def schema() -> Iterator[tuple[str, Callable[..., Any]]]:
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head

    with at_head("brain_calibration_store") as url:
        yield url, sql


def as_app(url: str, act: Callable[[Any], Any]) -> Any:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_session_factory

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await act(make_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.mark.needs_db
def test_a_run_keeps_a_fit_nobody_scores_with_until_a_reviewer_promotes_it(
    schema: tuple[str, Callable[..., Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run keeps its fit as a setting and the declared weights stay in force; a run within the
    week fits nothing; the reviewer's promote puts the fit in force with their name on it and on
    the ledger.

    Delete this and a weekly run could change how pairs are scored with nobody having looked."""
    import brain.resolution.calibration_store as store

    url, sql = schema

    async def planted(sessions: Any, **kwargs: Any) -> list[PatternCount]:
        return extract_of()

    monkeypatch.setattr(store, "extract", planted)

    first = as_app(url, lambda sessions: store.calibrate(sessions, now=AT))
    assert first.summary() == KEPT
    assert as_app(url, store.weights_in_force) is DECLARED_WEIGHTS
    waiting = as_app(url, store.candidate)
    assert waiting is not None and waiting.version == "fit_20190304t120000"

    again = as_app(url, lambda sessions: store.calibrate(sessions, now=AT + timedelta(days=2)))
    assert again.summary() == NOT_DUE

    as_app(
        url,
        lambda sessions: store.promote_fit(
            sessions, waiting.version, reviewer_id="u_reviewer", ent_hash="0" * 32, trace_id="t"
        ),
    )
    in_force = as_app(url, store.weights_in_force)
    assert in_force.calibration_ref == waiting.ref
    assert in_force.calibrated
    assert as_app(url, store.candidate) is None
    [(document,)] = sql(
        url, "SELECT value FROM ops.setting WHERE key = %s", f"{FITS_NAMESPACE}.{waiting.version}"
    )
    assert document["reviewed_by"] == "u_reviewer"
    assert sql(
        url,
        "SELECT count(*) FROM obs.audit_entry WHERE action = 'setting' AND actor_id = 'u_reviewer'",
    ) == [(2,)]


@pytest.mark.needs_db
def test_a_fit_the_reviewers_disagree_with_is_not_kept(
    schema: tuple[str, Callable[..., Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewers merged the pairs that agreed on a country and kept apart the ones that agreed on
    a registration number, which the fit weighs the other way, so nothing is kept.

    Delete this and a fit can be kept that ranks the pairs people rejected above the ones they
    merged."""
    import brain.resolution.calibration_store as store

    url, sql = schema

    async def planted(sessions: Any, **kwargs: Any) -> list[PatternCount]:
        return extract_of()

    monkeypatch.setattr(store, "extract", planted)
    for n, (state, field) in enumerate((("merged", "country"), ("rejected", "uen"))):
        sql(
            url,
            "INSERT INTO er.review_item (item_id, entity_type, left_source, left_entity,"
            " left_source_id, right_source, right_entity, right_source_id, left_entity_id,"
            " right_entity_id, origin, stage, reason, evidence, state, decided_by, decided_at)"
            " VALUES (%s, 'company', 's', 'e', %s, 's', 'e', %s, 'a', 'b', 'cascade', 4, 'r',"
            " %s::jsonb, %s, 'u_r', %s)",
            f"rev_{n}",
            f"{n}a",
            f"{n}b",
            json.dumps([{"field": field, "weight": 1.0}]),
            state,
            AT,
        )

    said = as_app(url, lambda sessions: store.calibrate(sessions, now=AT))

    assert said.summary().startswith("no fit was kept")
    assert as_app(url, store.candidate) is None


@pytest.mark.needs_db
def test_the_extract_counts_each_candidate_pair_by_what_agreed(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """Two companies sharing a domain and nothing else are one pair agreeing on the domain alone.

    Delete this and the fit could be measured on agreements the score never sums."""
    from types import MappingProxyType

    from brain.connectors.resolves import ResolvesAs
    from brain.resolution.calibration_store import extract
    from brain.resolution.canonical import EntityType, SourceRef
    from brain.resolution.registry_store import StoredRegistry
    from brain.resolution.sources import resolved_entities

    url, sql = schema
    entity = ("hubspot", "calibration_company")
    declared = MappingProxyType(
        {
            **resolved_entities(),
            entity: ResolvesAs(
                entity=entity[1],
                entity_type=EntityType.COMPANY,
                fields={"name": "name", "domain": "domain"},
            ),
        }
    )
    refs = []
    for n, name in enumerate(("Northwind Trading", "Fabrikam Studio")):
        sql(
            url,
            "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at)"
            " VALUES (%s, %s, %s, %s::jsonb, %s)",
            entity[0],
            entity[1],
            str(n),
            json.dumps({"name": name, "domain": "shared.example"}),
            AT,
        )
        refs.append(SourceRef(entity[0], entity[1], str(n)))

    async def go(sessions: Any) -> Any:
        await StoredRegistry(sessions, declared=declared).register(refs, pepper="ab" * 32, now=AT)
        return await extract(sessions, touching=refs)

    assert as_app(url, go) == (PatternCount(pattern=frozenset({Feature.DOMAIN}), pairs=1),)


@pytest.mark.needs_db
def test_only_the_fit_waiting_can_be_promoted_and_any_other_version_changes_nothing(
    schema: tuple[str, Callable[..., Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A promote naming a version that is not the fit waiting is a 409 and the weights stay as
    they were; naming the one waiting puts it in force.

    Delete this and a stale screen could put an older fit, or one a reviewer never saw, in force."""
    from types import SimpleNamespace

    from fastapi import FastAPI
    from starlette.requests import Request

    import brain.resolution.calibration_store as store
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.resolution_routes import ENTITY_MERGE_CAPABILITY, PromoteAsked, promote_weights

    url, _ = schema

    async def planted(sessions: Any, **kwargs: Any) -> list[PatternCount]:
        return extract_of()

    monkeypatch.setattr(store, "extract", planted)
    as_app(url, lambda sessions: store.calibrate(sessions, now=AT))
    reach = EntitlementSet(
        principal_id="u_reviewer",
        grants=(
            Grant(
                capability=Capability(value=ENTITY_MERGE_CAPABILITY.value),
                scope=Scope.unrestricted(),
            ),
        ),
    )
    asked: Any = SimpleNamespace(
        caller=SimpleNamespace(principal=SimpleNamespace(id="u_reviewer")),
        reach=reach,
        now=AT,
    )

    async def promote(sessions: Any, version: str) -> Any:
        app = FastAPI()
        app.state.db_sessions = sessions
        request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
        return await promote_weights(request, PromoteAsked(version=version), asked)

    stale = as_app(url, lambda sessions: promote(sessions, "fit_20000101t000000"))
    assert stale.status_code == 409
    assert as_app(url, store.weights_in_force) is DECLARED_WEIGHTS

    taken = as_app(url, lambda sessions: promote(sessions, "fit_20190304t120000"))
    assert taken.in_force == "fit_20190304t120000"
