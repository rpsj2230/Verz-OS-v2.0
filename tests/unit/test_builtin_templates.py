"""The shipped templates, signed with the install's key at start: what is signed, what is kept, and
how the gallery still tells them from a company's own.

Three halves. Without a server: every built-in template is signed under the product's name and
verifies with the key that signed it and no other, a document is built in only when it is exactly
the shipped one, and the gallery labels a signed built-in as built in. With a server at head: a
start holding a key puts every template on file once, each append reaching the ledger as a publish
by first run, a second start writes nothing, and a version already on file under a built-in's
number is kept. And the start itself: the application hands the key it read to the signing and
is never taken down by it.

Task ids: M13.8.10
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain.agent_routes import Origin, gallery, origin_of
from brain.agents.catalogue import CATALOGUE
from brain.agents.template import (
    SYSTEM_PUBLISHER,
    SignedManifest,
    TemplateError,
    content_digest,
    publish,
    verify,
)
from brain.firstrun import GRANTED_BY
from brain.identity.administration_reconciliation import TRACE_PREFIX as START_TRACE
from brain.ops.builtin_templates import (
    NO_KEY_SIGNS_NOTHING,
    is_built_in,
    sign_built_ins,
    signed_built_ins,
)
from brain.ops.leases import SealedSecret
from brain.ops.template_key import TemplateKeyReading, TemplateKeyState
from tests.unit.test_app_wiring import realm as realm  # the fixture, by its name

#: Far outside any plausible wall clock, for CLAUDE.md's reason about fixtures with dates.
AT = datetime(2999, 1, 1, tzinfo=UTC)

KEY = "k" * 64
OTHER_KEY = "o" * 64


# ------------------------------------------------------------------------ without a server
def test_every_built_in_template_is_signed_under_the_product_s_name_and_verifies_with_its_key() -> (
    None
):
    """One signed version per shipped template, at the shipped version, signed by the product, each
    verifying with the key that signed it and refused under any other. Delete this and a start
    could sign some templates, sign them as a person, or sign with a key the install does not
    verify with, and every install of a standard agent would fail at the signature."""
    signed = signed_built_ins(KEY, AT)
    assert [
        (one.manifest.identity.template_id, one.manifest.identity.version) for one in signed
    ] == [(one.identity.template_id, one.identity.version) for one in CATALOGUE]
    assert {one.signed_by for one in signed} == {SYSTEM_PUBLISHER}
    for one in signed:
        verify(one, key=KEY)
        with pytest.raises(TemplateError):
            verify(one, key=OTHER_KEY)


def test_a_document_is_built_in_only_when_it_is_exactly_the_shipped_one() -> None:
    """The shipped manifest is built in; the same id at another version, or at the same version
    with other words, is somebody's own. Delete this and a template a company published under a
    built-in's id would wear the product's label in the gallery."""
    shipped = CATALOGUE[0]
    later = shipped.model_copy(
        update={"identity": shipped.identity.model_copy(update={"version": 99})}
    )
    reworded = shipped.model_copy(
        update={"identity": shipped.identity.model_copy(update={"display_name": "Ours"})}
    )
    assert is_built_in(shipped)
    assert not is_built_in(later)
    assert content_digest(reworded) != content_digest(shipped)
    assert not is_built_in(reworded)


def test_the_gallery_labels_a_signed_built_in_as_built_in_and_a_company_s_own_as_published() -> (
    None
):
    """A built-in template on file after signing is still one card per id and says built in, and a
    company's own version under the same id says published. Delete this and signing the shipped
    templates would turn every card in the gallery into something the install appears to have
    made."""
    shipped = CATALOGUE[0]
    ours = shipped.model_copy(
        update={"identity": shipped.identity.model_copy(update={"version": 2})}
    )
    on_file = gallery([one.manifest for one in signed_built_ins(KEY, AT)]).items
    assert len(on_file) == len(CATALOGUE)
    assert {one.origin for one in on_file} == {Origin.BUILT_IN.value}
    assert origin_of(ours) is Origin.PUBLISHED
    assert {
        one.origin
        for one in gallery([ours]).items
        if one.template_id == shipped.identity.template_id
    } == {Origin.PUBLISHED.value}


def test_a_process_holding_no_key_signs_nothing_and_opens_no_connection() -> None:
    """`NO_KEY_SIGNS_NOTHING`: no key, no transaction, the reason logged. Delete this and a process
    with no vault could sign with an empty key, which `publish` refuses at the first template and
    turns into a warning on every start, or open a transaction for nothing."""

    def no_sessions() -> Any:
        raise AssertionError("a process with no key opened a session")

    with capture_logs() as logged:
        written = asyncio.run(
            sign_built_ins(no_sessions, key=None, at=AT, actor=GRANTED_BY, trace_id="t")  # type: ignore[arg-type]
        )
    assert written == ()
    assert [one["why"] for one in logged if one["event"] == "built-in templates not signed"] == [
        NO_KEY_SIGNS_NOTHING
    ]


# ------------------------------------------------------------------------- with a server
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_builtin_templates") as url:
        yield url


def _sessions(url: str) -> Any:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_application_sessions

    return make_application_sessions(make_app_engine(normalise_database_url(url)))


def _versions(url: str) -> dict[tuple[str, int], tuple[str, str, str]]:
    from tests.fixtures.scratch_postgres import sql

    return {
        (str(template), int(version)): (str(digest), str(signature), str(by))
        for template, version, digest, signature, by in sql(
            url,
            "SELECT template_id, version, content_digest, signature, signed_by"
            " FROM agent.template_version",
        )
    }


@pytest.mark.needs_db
def test_a_start_puts_every_template_on_file_once_and_keeps_what_is_there(head: str) -> None:
    """At head: a version already on file under a built-in's number is kept as it was; every other
    template is written once, signed with the key, each append a publish in the ledger by first
    run under the start's trace; a second start writes nothing. Delete this and a start could
    replace a version an agent is pinned to, append a publish on every start, or write nothing on
    a real schema while the pure tests stay green."""
    from sqlalchemy import insert

    from brain.agents.install_store import version_values
    from brain.tables.template import TemplateVersionRow
    from tests.fixtures.scratch_postgres import run, sql

    kept = publish(CATALOGUE[0], key=OTHER_KEY, signed_by="u_someone", at=AT)
    sessions = _sessions(head)

    async def on_file(signed: SignedManifest) -> None:
        async with sessions() as session, session.begin():
            await session.execute(insert(TemplateVersionRow).values(**version_values(signed)))

    run(lambda: on_file(kept))
    before = int(sql(head, "SELECT count(*) FROM obs.audit_entry WHERE action = 'publish'")[0][0])
    trace = f"{START_TRACE}0123456789abcdef"
    first = run(lambda: sign_built_ins(sessions, key=KEY, at=AT, actor=GRANTED_BY, trace_id=trace))
    second = run(lambda: sign_built_ins(sessions, key=KEY, at=AT, actor=GRANTED_BY, trace_id=trace))
    versions = _versions(head)
    entries = sql(
        head,
        "SELECT actor_id, trace_id FROM obs.audit_entry WHERE action = 'publish' ORDER BY seq",
    )[before:]

    shipped = {one.identity.template_id for one in CATALOGUE}
    assert set(first) == shipped - {CATALOGUE[0].identity.template_id}
    assert second == ()
    ours = CATALOGUE[0].identity
    assert versions[(ours.template_id, ours.version)] == (
        kept.content_digest,
        kept.signature,
        "u_someone",
    )
    for signed in signed_built_ins(KEY, AT)[1:]:
        identity = signed.manifest.identity
        assert versions[(identity.template_id, identity.version)] == (
            signed.content_digest,
            signed.signature,
            SYSTEM_PUBLISHER,
        )
    assert entries == [(GRANTED_BY, trace)] * len(first)


# ------------------------------------------------------------------------------- the start
class SigningRefusedError(Exception):
    """What the database answers the signing with in the failing start, whatever it is."""


def test_the_start_hands_the_key_it_holds_to_the_signing_and_survives_a_refusal(
    realm: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The key the application read is the key the templates are signed with, and signing is
    never the reason an install is down.** The start reads a held key, calls the signing once with
    that key as first run under the start's trace, and when the signing is refused it still serves
    and logs the class alone. Delete this and the start could sign with no key, with another key,
    or stop the process over a template."""
    del realm
    from tests.unit.test_app_wiring import wired_app

    asked: list[dict[str, Any]] = []

    def held(*_: object) -> TemplateKeyReading:
        return TemplateKeyReading(TemplateKeyState.HELD, SealedSecret(KEY))

    async def refused(sessions: object, **kwargs: Any) -> tuple[str, ...]:
        asked.append(kwargs)
        raise SigningRefusedError("password=never-logged")

    monkeypatch.setattr("brain.app.template_key_at_start", held)
    monkeypatch.setattr("brain.app.sign_built_ins", refused)
    with capture_logs() as logged, TestClient(wired_app()) as client:
        live = client.get("/health/live").status_code

    assert live == 200
    [call] = asked
    assert call["key"] == KEY
    assert call["actor"] == GRANTED_BY
    assert str(call["trace_id"]).startswith(START_TRACE)
    warned = [one for one in logged if one.get("event") == "built-in templates could not be signed"]
    assert warned == [
        {
            "event": "built-in templates could not be signed",
            "error": SigningRefusedError.__name__,
            "log_level": "warning",
        }
    ]
    assert not [one for one in logged if "never-logged" in repr(one)]
