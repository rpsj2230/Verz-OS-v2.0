"""The Google sources' acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a Google
Analytics property made up for the run is connected, its name read by the worker with a token its
key file bought, and asked about through the answer route's own functions, and every table the
check writes holds afterwards what it held before. Then it is run against the product broken where
it proves: a token exchange that names a person, a figure that is never read live, a figure kept in
the index, and a property told to a reader without it. Each fails with its own sentence.

Task ids: M11.7.1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.core.scope import Scope
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_sources import run_checks, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_google"
NAME = "an_analytics_property_answers_its_figures_live_and_keeps_none"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_google_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.1",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_check_s_key_file_is_one_the_exchange_reads_and_names_no_real_account() -> None:
    """The key file the check generates is a service account's in the shape Google downloads, so
    the token exchange really signs with it, and its address is made up for the run.

    Delete this and the check could pass by never reaching the exchange at all."""
    from brain.connectors.google_service_account import key_of
    from brain.ops.acceptance_checks_google import a_key_file

    email, key = key_of(a_key_file())
    assert email.startswith("acceptance-") and key.key_size >= 2048


@pytest.mark.needs_db
def test_on_a_real_database_a_property_answers_its_figure_live_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the
    projection, the connections, the attempts and the ledger hold what they held before. Delete
    this and the path from a connected property to a figure on Ask can break with nothing on the
    owner's install saying so, or a check that commits a connection can reach his server."""
    with at_head("brain_acceptance_google") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("subject", "the worker's read was not one token for the account and no report"),
        ("live", "a connected property's figure was not told to a reader granted it"),
        ("kept", "a figure read live was found in a table"),
        ("reach", "a property's figure was told to a reader not granted it"),
        ("range", "the figure tool did not ask Google for the range it was given"),
    ],
)
def test_the_google_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Five breaks, one per property: the account made to act as a person, a live reader that never
    reads, the figure kept beside the property in the index, the property's department rule moved,
    and the figure tool's range dropped for the last 28 days. Each fails the check with its own
    sentence. Delete this and the check can pass with the property gone."""
    import brain.connectors.google_analytics as google_analytics
    import brain.connectors.google_service_account as google_service_account
    import brain.ops.live_records as live_records

    if broken == "subject":
        signed = google_service_account.signed_assertion

        def as_a_person(**kwargs: Any) -> str:
            return signed(**{**kwargs, "subject": "someone@example.com"})

        monkeypatch.setattr(google_service_account, "signed_assertion", as_a_person)
        monkeypatch.setattr("brain.connectors.google_token.signed_assertion", as_a_person)
    elif broken == "live":

        async def never(self: Any, result: Any, **kwargs: Any) -> Any:
            del self, result, kwargs
            return None

        monkeypatch.setattr(live_records.SourceRecords, "refresh", never)
    elif broken == "kept":
        # A figure read live copied onto the property's index row, as a cache of the last answer
        # would keep it: the refresh is the product's own, and the copy is written through the
        # sessions the connection was made with.
        from sqlalchemy import text

        import brain.ops.connector_store as connector_store

        held: dict[str, Any] = {}
        connect = connector_store.StoredConnections.connect
        refresh = live_records.SourceRecords.refresh

        async def remembering(self: Any, **kwargs: Any) -> Any:
            held["sessions"] = self._sessions
            return await connect(self, **kwargs)

        async def copying(self: Any, result: Any, **kwargs: Any) -> Any:
            done = await refresh(self, result, **kwargs)
            if done is None or done.result is None:
                return done
            async with held["sessions"]() as session, session.begin():
                for one in done.result.records:
                    figure = one.model_dump().get("sessions_last_28_days")
                    if figure is not None:
                        await session.execute(
                            text(
                                "UPDATE proj.record SET fields = fields || "
                                "jsonb_build_object('copied', CAST(:figure AS text)) "
                                "WHERE source = 'google_analytics'"
                            ),
                            {"figure": figure},
                        )
            return done

        monkeypatch.setattr(connector_store.StoredConnections, "connect", remembering)
        monkeypatch.setattr(live_records.SourceRecords, "refresh", copying)
    elif broken == "range":
        # The tool's range dropped on the way, and the last 28 days asked for instead.
        from brain.connectors.date_range import RangeRequest, window_of

        monkeypatch.setattr(
            RangeRequest, "window", lambda self, *, today: window_of("last 28 days", today=today)
        )
    else:
        monkeypatch.setattr(
            google_analytics.AnalyticsConnection,
            "visibility",
            lambda self: Scope.department("acceptance_b"),
        )
    with at_head(f"brain_acceptance_google_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_google_check_steps_aside_where_the_install_has_the_property_connected() -> None:
    """`A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`. Delete this and the check could move the
    owner's real connection aside, or fail on an install whose Analytics is connected."""
    from brain.ops.acceptance_checks_google import ANALYTICS_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_google_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('google_analytics', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, ANALYTICS_IS_CONNECTED_HERE_ALREADY)
