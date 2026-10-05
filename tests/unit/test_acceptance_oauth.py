"""The OAuth consent check: registered, passing on a real schema, and able to fail where it proves.

The database half builds PostgreSQL to head and runs the check as the install runs it: a source
consented to by OAuth is stood up from Xero's declaration, consented to through the consent routes'
bodies, read by the worker with access renewed from the kept refresh token, and refused by the
vendor, and every table the check writes holds afterwards what it held before. Then it is run
against the product broken where it proves, and each break fails with its own sentence.

Task ids: M11.8.6
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_oauth"
NAME = "a_consented_source_is_renewed_by_its_read_and_a_refusal_is_said"
OWN = "a_persons_own_consent_is_read_for_them_alone"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_oauth_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        NAME: ("M11.8.6",),
        OWN: ("M11.8.6",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) | set(mine()[OWN].leaves) <= leaves


def test_the_oauth_checks_are_listed_in_their_page_order() -> None:
    """Two checks, the consented source from consent to refusal and then a person's own consent.
    Delete this and a check can drop out of the module with the page simply listing one fewer
    row."""
    assert checks_in(MODULE) == [NAME, OWN]


def test_the_check_says_no_shipped_source_authorises_by_oauth_yet() -> None:
    """The check stands a consented source up because none ships, and says so in the sentence the
    Install page shows, naming the first that will. Held against the shipped declarations, so the
    day one declares a consent this fails and the check is pointed at it instead.

    Delete this and the page can read as a shipped source proved working when none is."""
    from brain.connectors.declaration import shipped

    sentence = mine()[NAME].sentence
    assert "no shipped source uses OAuth yet" in sentence
    assert "Google Workspace will be the first" in sentence
    assert not [name for name, one in shipped().items() if one.oauth is not None]


def test_the_stood_up_declaration_is_one_the_platform_accepts_and_renews_by_its_consent() -> None:
    """The declaration the check builds passes every rule a shipped one meets (the consent asks for
    the client id through a setting of the form, the reading renews by the same consent), and its
    reading presents the OAuth scheme. Delete this and the check can be driving a declaration no
    connector module could ship."""
    from brain.connectors.declaration import ConsentedReading, KeyScheme
    from brain.ops.acceptance_checks_oauth import CLIENT_ID_SETTING, consented_xero

    declared, reading = consented_xero()
    assert declared.oauth is not None
    assert declared.console is not None
    assert CLIENT_ID_SETTING in {one.name for one in declared.console.settings}
    assert isinstance(reading, ConsentedReading) and reading.consent() == declared.oauth
    assert reading.key_scheme() is KeyScheme.OAUTH_REFRESH


@pytest.mark.needs_db
def test_on_a_real_database_a_consented_source_is_kept_renewed_and_refused_in_words() -> None:
    """**The check as the install runs it, against PostgreSQL at head.** It passes, and the
    projection, the connections, the attempts and the ledger hold what they held before. Delete
    this and the path from a consent to a renewed read can break with nothing on the owner's install
    saying so, or a check that commits a connection can reach his server."""
    with at_head("brain_acceptance_oauth") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, ""), OWN: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("replay", "a consent's state was used twice"),
        ("verifier", "the vendor's code was not exchanged and kept"),
        ("rotation", "the refresh token the vendor rotated was not written back"),
        ("withdrawn", "a refused renewal did not leave the source down, said in words"),
    ],
)
def test_the_oauth_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks, one per property: a consent's state that is not used up when it is taken, a
    code exchanged with a verifier other than the one its state sealed, a rotated refresh token
    that is not written back, and a refused renewal read as an ordinary declined key. Each fails
    the check with its own sentence. Delete this and the check can pass with any of them gone."""
    import brain.connector_routes as connector_routes
    import brain.ops.connector_consent as connector_consent
    import brain.ops.connector_sync_run as connector_sync_run

    if broken == "replay":
        take = connector_consent.StoredConsents.take
        seen: dict[str, Any] = {}

        async def again(self: Any, *, state: str, principal_id: str, now: Any) -> Any:
            # The real take, and then the same consent again for the same person: never used up.
            found = await take(self, state=state, principal_id=principal_id, now=now)
            if found is not None:
                seen[f"{principal_id} {state}"] = found
                return found
            return seen.get(f"{principal_id} {state}")

        monkeypatch.setattr(connector_consent.StoredConsents, "take", again)
    elif broken == "verifier":
        from brain.connectors.oauth import ConsentStart, code_exchange, new_consent

        exchange = code_exchange

        def another(consent: Any, **kwargs: Any) -> Any:
            fresh = new_consent()
            start = ConsentStart(state=kwargs["start"].state, verifier=fresh.verifier)
            return exchange(consent, **{**kwargs, "start": start})

        monkeypatch.setattr(connector_routes, "code_exchange", another)
    elif broken == "rotation":

        def forgets(self: Any, ref: Any, token: str, *, now: Any) -> None:
            del self, ref, token, now

        monkeypatch.setattr(connector_sync_run.WorkerConnectorKeys, "rotate", forgets)
    else:
        from brain.ops.connector_sync import failure_detail

        def as_any_refusal(refused: Any, *, poster: Any) -> str:
            del poster
            return failure_detail(refused.call, timed_out=refused.timed_out)

        monkeypatch.setattr(connector_sync_run, "presenting_detail", as_any_refusal)
    with at_head(f"brain_acceptance_oauth_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_oauth_check_steps_aside_where_the_install_has_xero_connected() -> None:
    """The check stands a consented copy of Xero up, so on an install with Xero connected it does
    not, rather than moving the real connection aside. Delete this and the check could disturb the
    owner's own Xero connection, or fail on every install that reads Xero."""
    from brain.ops.acceptance_checks_oauth import XERO_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_oauth_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('xero', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, XERO_IS_CONNECTED_HERE_ALREADY)


# ------------------------------------------------------------------ a person's own consent
def test_the_personal_declaration_is_one_the_platform_accepts_and_renews_no_scheduled_read() -> (
    None
):
    """The declaration the personal check builds passes every rule a shipped one meets: a personal
    consent naming its reader capability, the form asking for the client id and the department,
    and a scheduled reading that renews by no consent. Delete this and the check can be driving a
    declaration no connector module could ship."""
    from brain.connectors.declaration import PERSONAL_DEPARTMENT_SETTING, KeyScheme
    from brain.connectors.oauth import ConsentKind
    from brain.ops.acceptance_checks_oauth import (
        CLIENT_ID_SETTING,
        PERSONAL_READER,
        consented_personally,
    )

    declared = consented_personally()
    assert declared.oauth is not None and declared.console is not None
    assert (declared.oauth.kind, declared.oauth.reader) == (ConsentKind.PERSON, PERSONAL_READER)
    asked = {one.name for one in declared.console.settings}
    assert {CLIENT_ID_SETTING, PERSONAL_DEPARTMENT_SETTING} <= asked
    assert declared.reading is not None
    assert declared.reading.key_scheme() is not KeyScheme.OAUTH_REFRESH


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("source_slot", "a person's refresh token is not in their own slot"),
        ("other_slot", "a person's keys leased another person's slot"),
        ("withdrawn", "a withdrawn consent was not said in words"),
        ("erasure", "erasing a person did not remove their own token and only theirs"),
    ],
)
def test_the_personal_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks, one per property: a person's consent kept in the source's own slot, a person's
    keys that lease anybody's slot, a withdrawn consent said as the source's refusal rather than to
    the person, and an erasure that removes nothing. Each fails the check with its own sentence.
    Delete this and the check can pass with any of them gone."""
    import brain.connector_routes as connector_routes
    import brain.ops.connector_sync_run as connector_sync_run
    import brain.ops.erasure_store as erasure_store

    if broken == "source_slot":

        def the_sources(connector: str, principal_id: str) -> Any:
            del principal_id
            return connector_routes.connector_oauth_slot(connector)

        monkeypatch.setattr(connector_routes, "connector_person_oauth_slot", the_sources)
    elif broken == "other_slot":

        def anybodys(self: Any, ref: Any, *, now: Any) -> Any:
            return self._keys.lease(ref, now=now)

        monkeypatch.setattr(connector_sync_run.PersonalKeys, "lease", anybodys)
    elif broken == "withdrawn":
        from brain.connectors.oauth import CONSENT_WITHDRAWN, ConsentWithdrawnError

        words = connector_sync_run.personal_words

        def the_sources_words(refused: Exception) -> str:
            # A withdrawal said in the source's sentence, as if the source were down for everybody.
            if isinstance(refused, ConsentWithdrawnError):
                return CONSENT_WITHDRAWN
            return words(refused)

        monkeypatch.setattr(connector_sync_run, "personal_words", the_sources_words)
    else:

        def keeps(vault: Any, subject_id: str, connectors: Any) -> int:
            del vault, subject_id
            return len(connectors)

        monkeypatch.setattr(erasure_store, "erase_own_refresh_tokens", keeps)
    with at_head(f"brain_acceptance_own_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[OWN],))
        after = written(url)
    assert outcome[OWN] == (FAILED, reason)
    assert after == before
