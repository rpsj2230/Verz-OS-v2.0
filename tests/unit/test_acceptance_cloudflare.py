"""The Cloudflare acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a Cloudflare
account made up for the run is connected, its zones and records read from recorded answers, a
record's content asked about through the answer route's own functions, and a DNS change prepared,
queued for approval and resumed; every table the check writes holds afterwards what it held
before. Then it is run against the product broken where it proves, and each break fails with its
own sentence.

Task ids: M11.7.3
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_cloudflare"
NAME = "cloudflare_is_read_live_and_a_dns_change_waits_for_a_person"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "ops.connector_connection", "ops.connector_sync", "gate.suspension")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


def test_the_cloudflare_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.3",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


@pytest.mark.needs_db
def test_on_a_real_database_cloudflare_is_read_live_and_a_change_is_held_leaving_nothing() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the
    projection, the connection, the attempt, the approval queue and the ledger hold what they held
    before. Delete this and the path from a connected Cloudflare account to Ask, or the one from a
    prepared change to an approver, can break with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_cloudflare") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("questions", "a connected Cloudflare account contributed no question to Ask"),
        ("live", "a DNS record's content was not read live for a reader granted it"),
        ("withheld", "a DNS record's content was told to a reader not granted it"),
        ("held", "a DNS change was sent"),
        ("sent", "an approved DNS change was run before the owner decided"),
    ],
)
def test_the_cloudflare_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Five breaks, one per property: Cloudflare's records given no question shape, the live read
    no longer taking a record's content, a policy telling the content to anybody who reaches the
    record, the sensitive-effect cap lifted so an Autonomous leash runs the change, and a change
    that runs when approved. Each fails the check with its own sentence. Delete this and the check
    can pass with the property gone."""
    import brain.api_routes as api_routes
    import brain.connectors.cloudflare as cloudflare
    import brain.gate.leash as leash
    import brain.knowledge.connector_rows as connector_rows
    from brain.core.envelope import TypedResult
    from brain.core.field_policy import Classification, FieldPolicy, FieldRule
    from brain.gate.injection import AutonomyTier

    if broken == "questions":
        monkeypatch.setattr(
            connector_rows,
            "NAMED_BY",
            {key: one for key, one in connector_rows.NAMED_BY.items() if key[0] != "cloudflare"},
        )
    elif broken == "live":
        monkeypatch.setattr(cloudflare, "DNS_LIVE_MAPPING", cloudflare.DNS_LIST_MAPPING)
    elif broken == "withheld":
        loose = FieldPolicy(
            rules=tuple(
                FieldRule.of("dns_record", one, "read:dns_record", Classification.INTERNAL)
                for one in ("name", "type", "content", "zone_id", "department")
            )
        )
        policies = api_routes.source_field_policies

        def loosened(registry: Any) -> Any:
            return {**policies(registry), ("cloudflare", "dns_record"): loose}

        monkeypatch.setattr(api_routes, "source_field_policies", loosened)
    elif broken == "held":
        monkeypatch.setattr(leash, "SENSITIVE_EFFECT_RUNG", AutonomyTier.AUTONOMOUS)
    else:

        def ran(action: Any) -> Any:
            del action
            return TypedResult(records=(), source="cloudflare", fetched_at="")

        monkeypatch.setattr(cloudflare, "execute_dns_change", ran)
    with at_head(f"brain_acceptance_cloudflare_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_cloudflare_check_steps_aside_where_the_install_has_cloudflare_connected() -> None:
    """`A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY`. Delete this and the check could move the owner's
    real connection aside, or fail on an install whose Cloudflare is connected."""
    from brain.ops.acceptance_checks_cloudflare import A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_cloudflare_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('cloudflare', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY)
