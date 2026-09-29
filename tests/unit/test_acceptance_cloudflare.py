"""The Cloudflare acceptance checks: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs both checks as the worker would: a Cloudflare
account made up for the run is connected and read, a record's content is asked about through the
answer route's own functions, and a DNS change is prepared, queued, approved through the decision
route's own function and sent, or not, as the install allowed; every table the checks write holds
afterwards what it held before. Then each is run against the product broken where it proves, and
each break fails with its own sentence.

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
HELD = "cloudflare_is_read_live_and_a_dns_change_waits_for_a_person"
SENT = "an_allowed_dns_change_is_sent_once_and_read_back"

#: Every table the checks write to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "ops.connector_connection", "ops.connector_sync", "gate.suspension")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


def test_the_cloudflare_checks_are_registered_with_the_leaf_they_prove() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        HELD: ("M11.7.3",),
        SENT: ("M11.7.3",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= leaves


@pytest.mark.needs_db
def test_on_a_real_database_cloudflare_is_read_live_and_a_change_is_held_or_sent_once() -> None:
    """**Both checks as the worker runs them, against PostgreSQL at head.** They pass, and the
    projection, the connection, the attempt, the approval queue and the ledger hold what they held
    before. Delete this and the path from a connected Cloudflare account to Ask, or from a
    prepared change to a person and to Cloudflare, can break with nothing on the install saying
    so."""
    with at_head("brain_acceptance_cloudflare") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {HELD: (PASSED, ""), SENT: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("name", "broken", "reason"),
    [
        (HELD, "questions", "a connected Cloudflare account contributed no question to Ask"),
        (HELD, "live", "a DNS record's content was not read live for a reader granted it"),
        (HELD, "withheld", "a DNS record's content was told to a reader not granted it"),
        (HELD, "held", "a DNS change was sent"),
        (HELD, "unsent", "an approver was not told this install has not allowed DNS changes"),
        (
            HELD,
            "readkey",
            "an approved DNS change was sent on an install that had not allowed it",
        ),
        (SENT, "readkey", "an allowed DNS change was not sent with the grant's own key"),
        (SENT, "twice", "an approved DNS change was sent twice"),
        (SENT, "readback", "an allowed DNS change was not sent and read back as approved"),
    ],
)
def test_the_cloudflare_checks_fail_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, name: str, broken: str, reason: str
) -> None:
    """One break per property: Cloudflare's records given no question shape, the live read no
    longer taking a record's content, a policy telling the content to anybody who reaches the
    record, the sensitive-effect cap lifted so an Autonomous leash runs the change, the card not
    saying the install has not allowed DNS changes, a change sent with the read key, an approval
    that runs every time it is resumed, and a read-back that never finds what was sent. Each fails
    its check with its own sentence. Delete this and a check can pass with its property gone."""
    import brain.api_routes as api_routes
    import brain.connectors.cloudflare as cloudflare
    import brain.gate.leash as leash
    import brain.knowledge.connector_rows as connector_rows
    import brain.ops.connector_write_run as connector_write_run
    from brain.core.field_policy import Classification, FieldPolicy, FieldRule
    from brain.gate.injection import AutonomyTier
    from brain.ops.connectable import READING_ROLE
    from brain.ops.credentials import connector_key_slot
    from brain.ops.secrets import SecretRef

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
    elif broken == "unsent":
        monkeypatch.setattr(connector_write_run, "unsent_because", lambda tool, held: "")
    elif broken == "readkey":
        read = SecretRef(path=connector_key_slot("cloudflare").path, role=READING_ROLE)
        monkeypatch.setattr(connector_write_run, "write_key", lambda connector, grant: read)
    elif broken == "twice":

        def always(action: Any, *, execute: Any, ledger: Any, intent: Any) -> Any:
            del ledger, intent
            return execute(action)

        monkeypatch.setattr(leash, "run_real", always)
    else:
        monkeypatch.setattr(
            cloudflare.DnsChangeWrites, "differs", lambda self, action, found: ("content",)
        )
    with at_head(f"brain_acceptance_cloudflare_{broken}_{name[:4]}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[name],))
        after = written(url)
    assert outcome[name] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_cloudflare_checks_step_aside_where_the_install_has_cloudflare_connected() -> None:
    """`A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY`. Delete this and a check could move the owner's
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
        outcome = run_checks(url, tuple(mine().values()))
    assert outcome == {
        HELD: (NOT_RUN, A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY),
        SENT: (NOT_RUN, A_CLOUDFLARE_IS_CONNECTED_HERE_ALREADY),
    }
