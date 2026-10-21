"""A website is declared as a closed document, kept as rows, and what is signed for it ends.

The pure half holds the codec: every refusal it makes and the round trip it must make. The database
half builds PostgreSQL at head and drives `brain.browsing.declared` as `brain_app`, reading back the
ledger entries `0275`'s trigger appends and holding them to the details a leash change carries;
it skips when `DATABASE_URL` is unset. The clock is 2999, for the reason CLAUDE.md records
about fixtures that go off.

Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
"""

from __future__ import annotations

import asyncio
import copy
import enum
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder
from brain.browsing import declared
from brain.browsing.declared import DeclarationError, declared_from, document_of
from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE
from brain.browsing.targets import TargetRegistry, Verb
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.tables.browsing import BrowserTargetRow

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
ORIGIN = "https://books.example"
ENT_HASH = "a" * 32

DOCUMENT: dict[str, Any] = {
    "name": "books",
    "origins": [ORIGIN],
    "api_tools": ["ledger.list_invoices"],
    "surfaces": [
        {
            "name": "login",
            "origin": ORIGIN,
            "path": "/login",
            "verbs": ["open", "type", "submit"],
            "reads": [],
            "read_back": "",
            "controls": [
                {
                    "verb": "type",
                    "role": "textbox",
                    "label": "Password",
                    "placeholder": "{{secret:login}}",
                },
                {"verb": "submit", "role": "button", "label": "Sign in"},
            ],
        },
        {
            "name": "invoices",
            "origin": ORIGIN,
            "path": "/invoices",
            "verbs": ["open", "read"],
            "reads": ["number"],
        },
    ],
    "bindings": [
        {
            "placeholder": "{{secret:login}}",
            "path": "browser/creds/books",
            "origin": ORIGIN,
            "kind": "password",
        }
    ],
}


def edited(change: Any) -> dict[str, Any]:
    """The document with one edit made to a copy of it."""
    document = copy.deepcopy(DOCUMENT)
    change(document)
    return document


def refused(document: Any) -> str:
    with pytest.raises(DeclarationError) as why:
        declared_from(document)
    return str(why.value)


# ------------------------------------------------------------------------------- the codec
def test_a_document_reads_into_the_target_and_back_into_the_same_document() -> None:
    """The positive case, and the round trip. Delete this and a codec that refuses everything, or
    one whose output reads back as another target, passes every refusal test below."""
    read = declared_from(DOCUMENT)

    assert read.target.name == "books" and read.target.origins == {ORIGIN}
    assert read.target.api_tools == ("ledger.list_invoices",)
    assert [one.name for one in read.target.surfaces] == ["login", "invoices"]
    assert read.bindings.placeholders() == {"{{secret:login}}"}
    again = document_of(read)
    assert declared_from(again) == read
    assert document_of(declared_from(again)) == again


def test_a_reading_surface_gets_the_browse_capability_and_a_writing_one_the_write_one() -> None:
    """The capability is derived from the verbs and never asked for. Delete this and a document
    that names a capability is a way to give a read a write's permission, or the reverse."""
    surfaces = {one.name: one for one in declared_from(DOCUMENT).target.surfaces}

    assert surfaces["invoices"].capability == BROWSE_SURFACE
    assert surfaces["login"].capability == ACT_ON_SURFACE_CAPABILITY
    assert "capability" in refused(
        edited(lambda d: d["surfaces"][1].update(capability="write:browser_surface"))
    )


@pytest.mark.parametrize(
    ("change", "words"),
    [
        (lambda d: d.update(colour="blue"), "colour"),
        (lambda d: d["surfaces"][0].update(selector="#go"), "selector"),
        (lambda d: d["surfaces"][0]["controls"][0].update(css="x"), "css"),
        (lambda d: d["bindings"][0].update(value="hunter2hunter2"), "value"),
        (lambda d: d.update(name="Books Ltd"), "lowercase"),
        (lambda d: d.update(origins=[]), "allows no origin"),
        (lambda d: d["surfaces"][0].update(verbs=["open", "teleport"]), "teleport"),
        (lambda d: d["surfaces"][1].update(reads=[]), "declares no fields"),
        (lambda d: d["surfaces"][0]["controls"][1].update(verb="click"), "does not admit"),
        (lambda d: d["surfaces"][0]["controls"][1].update(verb="read"), "only reads"),
        (
            lambda d: d["surfaces"][0]["controls"][0].update(placeholder="", text=""),
            "text it enters",
        ),
        (
            lambda d: d["surfaces"][0]["controls"][0].update(text="a value"),
            "text it enters",
        ),
        (lambda d: d["surfaces"][0]["controls"][1].update(text="x"), "enters nothing"),
        (lambda d: d["surfaces"][0]["controls"][0].update(placeholder="hunter2"), "secret"),
        (lambda d: d["bindings"][0].update(path="providers/anthropic"), "browser/creds"),
        (lambda d: d["bindings"][0].update(path="browser/creds/a/b"), "browser/creds"),
        (lambda d: d["bindings"][0].update(origin="https://elsewhere.example"), "does not allow"),
        (lambda d: d["bindings"][0].update(placeholder="login"), "placeholder"),
        (lambda d: d["bindings"][0].update(kind="biometric"), "biometric"),
        (lambda d: d["bindings"].append(copy.deepcopy(d["bindings"][0])), "share a placeholder"),
        (lambda d: d["bindings"].clear(), "binds"),
        (lambda d: d["surfaces"][1].update(origin="https://other.example"), "does not allow"),
    ],
)
def test_each_way_a_document_could_widen_or_break_a_declaration_is_refused_in_words(
    change: Any, words: str
) -> None:
    """One edit at a time. Delete this and a document that smuggles in a key, a credential value, a
    vault path the runner cannot read or a control for a verb the surface lacks is kept, and the
    fault shows in a run."""
    assert words in refused(edited(change))


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(origins="https://books.example"),
        lambda d: d.update(surfaces={"login": {}}),
        lambda d: d.update(bindings="none"),
        lambda d: d.update(api_tools="ledger.list_invoices"),
        lambda d: d["surfaces"][0].update(verbs="open"),
        lambda d: d["surfaces"][0].update(controls="click"),
    ],
)
def test_a_field_that_is_a_list_must_be_a_list(change: Any) -> None:
    """A string would be iterated a character at a time. Delete this and an origin written as one
    string is read as a set of letters, each of which the target then refuses in words nobody can
    connect to the mistake."""
    assert "not a list" in refused(edited(change))


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(name=5),
        lambda d: d.update(name="  "),
        lambda d: d["surfaces"][0].update(path=None),
        lambda d: d["surfaces"][0]["controls"][1].update(label=""),
        lambda d: d["surfaces"][0]["controls"][1].update(role="   "),
        lambda d: d["surfaces"][1].update(read_back=3),
        lambda d: d["bindings"][0].update(origin=None),
    ],
)
def test_a_text_field_must_be_text_and_the_required_ones_must_say_something(change: Any) -> None:
    """Delete this and a number is kept as a name, or a blank label is kept as a control that is
    then found by guessing."""
    assert "as text" in refused(edited(change))


def test_a_control_with_no_role_or_no_name_is_refused_by_its_own_type_too() -> None:
    """The codec refuses a blank one first, so only the type itself is asked here. Delete this and
    a `Control` built by anything but the codec can be found in a snapshot by guessing."""
    from brain.browsing.targets import Control, TargetError

    with pytest.raises(TargetError, match="no role or no name"):
        Control(verb=Verb.CLICK, role=" ", label="Go")
    with pytest.raises(TargetError, match="no role or no name"):
        Control(verb=Verb.CLICK, role="button", label="")


def test_an_exemption_that_ended_or_runs_past_a_quarter_is_refused_before_the_table() -> None:
    """Delete this and the length of an exemption is left to a check constraint, which a client
    that wrote through another path would meet only as a database error."""

    async def attempt(ends: datetime) -> None:
        await declared.sign_exemption(
            None,  # type: ignore[arg-type]
            skill="a-skill",
            target="books",
            approver="approver",
            expires_at=ends,
            reason="a reason that is long enough",
            now=NOW,
            ent_hash=ENT_HASH,
            trace_id="trace-sign",
        )

    for ends in (NOW, NOW - timedelta(days=1), NOW + timedelta(days=91)):
        with pytest.raises(DeclarationError, match="ends in the future and within"):
            asyncio.run(attempt(ends))


@pytest.mark.parametrize("not_an_object", [None, [], "books", 3])
def test_a_declaration_that_is_not_an_object_is_refused(not_an_object: Any) -> None:
    """Delete this and a list or a string reaches the key lookups and raises something else."""
    assert "is an object" in refused(not_an_object)


def test_a_totp_seed_binding_is_kept_as_a_seed_and_never_as_a_password() -> None:
    """The kind decides whether the control plane computes a code. Delete this and a seed binding
    reads back as a password, and the six-digit code is never produced."""
    document = edited(lambda d: d["bindings"][0].update(kind="totp_seed"))

    assert declared_from(document).bindings.bindings[0].kind.value == "totp_seed"


def test_a_binding_is_a_reference_and_never_a_value_when_it_is_written_back() -> None:
    """Delete this and a document that is written back carries more than the reference."""
    written = document_of(declared_from(DOCUMENT))["bindings"][0]

    assert set(written) == {"placeholder", "path", "origin", "kind"}


def test_every_write_verb_has_a_control_or_the_surface_still_reads_as_declared() -> None:
    """A write surface needs no control to be declared, so a declaration can be made before the
    controls are known. Delete this and declaring a surface demands controls it has not got."""
    document = edited(lambda d: d["surfaces"][0].update(controls=[]))

    surface = declared_from(document).target.surface("login")
    assert surface is not None and Verb.SUBMIT in surface.verbs


# ------------------------------------------------------------------------------- the database
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_browser_declarations") as url:
        yield url


def sessions(url: str) -> Any:
    from tests.unit.test_browser_session_store import _sessions

    return _sessions(url)


def administrator(who: str = "admin") -> EntitlementSet:
    return EntitlementSet(
        principal_id=who,
        grants=(
            Grant(capability=ACT_ON_SURFACE_CAPABILITY, scope=Scope.unrestricted()),
            Grant(capability=BROWSE_SURFACE, scope=Scope.unrestricted()),
        ),
    )


async def _declare(url: str, document: dict[str, Any], by: str = "admin") -> None:
    async with sessions(url)() as session:
        await declared.declare(session, declared_from(document), by=by)
        await session.commit()


async def _load(url: str) -> declared.Loaded:
    async with sessions(url)() as session:
        return await declared.load(session)


def entries(url: str, target: str) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(
        url,
        "SELECT action, actor_id, subject, details FROM obs.audit_entry "
        "WHERE subject = %s ORDER BY seq",
        f"connector:browser.{target}",
    )


@pytest.mark.needs_db
def test_the_newest_declaration_of_a_name_is_the_one_read_and_a_retired_one_is_not(
    head: str,
) -> None:
    """History is rows: a map edited after a run is a map with a past. Delete this and the oldest
    row wins, or a retirement is a deletion nobody can see."""
    asyncio.run(_declare(head, DOCUMENT, by="admin"))
    asyncio.run(_declare(head, edited(lambda d: d.update(api_tools=[])), by="second"))

    loaded = asyncio.run(_load(head))

    assert loaded.declared["books"].declared.target.api_tools == ()
    assert loaded.declared["books"].set_by == "second"
    assert loaded.registry().names() == ("books",)

    async def retire() -> bool:
        async with sessions(head)() as session:
            done = await declared.retire(session, "books", by="admin")
            await session.commit()
            return done

    assert asyncio.run(retire()) is True
    assert asyncio.run(_load(head)).declared == {}
    assert asyncio.run(retire()) is False

    from tests.fixtures.scratch_postgres import sql

    assert sql(head, "SELECT count(*) FROM agent.browser_target WHERE name = 'books'")[0][0] == 3


@pytest.mark.needs_db
def test_a_row_that_no_longer_reads_is_not_declared_and_is_named(head: str) -> None:
    """Delete this and a stored target the codec refuses is either dropped without a word or kept
    as a target it could not check."""
    from tests.fixtures.scratch_postgres import sql

    sql(
        head,
        "INSERT INTO agent.browser_target (name, definition, retired, set_by) "
        "VALUES ('stale', '{\"name\": \"stale\", \"selector\": 1}'::jsonb, false, 'admin')",
    )

    loaded = asyncio.run(_load(head))

    assert "stale" in loaded.unreadable and "stale" not in loaded.declared


@pytest.mark.needs_db
def test_a_declaration_is_written_in_the_sessions_own_name(head: str) -> None:
    """Delete this and one person's session can record a declaration as another's."""

    async def forged() -> None:
        async with sessions(head)() as session:
            await session.execute(text("SELECT set_config('app.principal_id', 'somebody', true)"))
            session.add(
                BrowserTargetRow(
                    name="forged", definition={}, retired=False, set_by="somebody_else"
                )
            )
            await session.flush()

    with pytest.raises(DBAPIError):
        asyncio.run(forged())


@pytest.mark.needs_db
def test_an_exception_is_signed_kept_listed_read_live_and_gone_at_its_end(head: str) -> None:
    """Delete this and a signature is kept for ever, or listed after it lapsed, or read by the
    compiler an instant after it ended."""
    target = declared_from(DOCUMENT).target
    ends = NOW + timedelta(days=30)

    async def sign() -> None:
        async with sessions(head)() as session:
            await declared.sign_exception(
                session,
                target,
                "login",
                signer=administrator("signer"),
                expires_at=ends,
                reason="the nightly filing runs unattended for a quarter",
                now=NOW,
                trace_id="trace-sign",
            )
            await session.commit()

    async def look(at: datetime) -> tuple[Any, Any]:
        async with sessions(head)() as session:
            return (
                await declared.live_exceptions(session, at, target="books"),
                await declared.listing(session, at),
            )

    asyncio.run(sign())
    live, listed = asyncio.run(look(NOW + timedelta(days=1)))
    assert [(one.target, one.surface, one.signed_by) for one in live] == [
        ("books", "login", "signer")
    ]
    assert [(one.kind, one.what) for one in listed] == [("exception", "login")]

    live, listed = asyncio.run(look(ends))
    assert live == () and listed == ()


@pytest.mark.needs_db
def test_the_signer_must_be_able_to_perform_the_write_and_the_surface_must_write(head: str) -> None:
    """Delete this and somebody who could not file the return signs for an agent to file it."""
    target = declared_from(DOCUMENT).target
    reader = EntitlementSet(
        principal_id="reader",
        grants=(Grant(capability=BROWSE_SURFACE, scope=Scope.unrestricted()),),
    )

    async def attempt(surface: str, signer: EntitlementSet) -> None:
        async with sessions(head)() as session:
            await declared.sign_exception(
                session,
                target,
                surface,
                signer=signer,
                expires_at=NOW + timedelta(days=5),
                reason="a long enough reason",
                now=NOW,
                trace_id="trace-sign",
            )

    with pytest.raises(DeclarationError, match="may not perform writes"):
        asyncio.run(attempt("login", reader))
    with pytest.raises(DeclarationError, match="declares no write"):
        asyncio.run(attempt("invoices", administrator()))
    with pytest.raises(DeclarationError, match="no surface"):
        asyncio.run(attempt("nowhere", administrator()))


@pytest.mark.needs_db
def test_an_exemption_is_kept_read_live_and_ends_when_it_is_revoked(head: str) -> None:
    """Delete this and an exemption cannot be taken back, or is still read after it was."""

    async def exempt() -> None:
        async with sessions(head)() as session:
            await declared.sign_exemption(
                session,
                skill="file-return",
                target="books",
                approver="approver",
                expires_at=NOW + timedelta(days=60),
                reason="the connector does not cover the filing page yet",
                now=NOW,
                ent_hash=ENT_HASH,
                trace_id="trace-sign",
            )
            await session.commit()

    async def live(at: datetime) -> tuple[Any, ...]:
        async with sessions(head)() as session:
            return await declared.live_exemptions(session, at)

    async def revoke(seq: int, at: datetime) -> bool:
        async with sessions(head)() as session:
            done = await declared.revoke(
                session, seq, by="admin", now=at, ent_hash=ENT_HASH, trace_id="trace-revoke"
            )
            await session.commit()
            return done

    asyncio.run(exempt())
    found = asyncio.run(live(NOW + timedelta(days=1)))
    assert [(one.skill, one.target, one.approver) for one in found] == [
        ("file-return", "books", "approver")
    ]

    async def seq_of_it() -> int:
        async with sessions(head)() as session:
            return next(
                one.seq for one in await declared.listing(session, NOW) if one.kind == "exemption"
            )

    seq = asyncio.run(seq_of_it())
    assert asyncio.run(revoke(seq, NOW + timedelta(days=2))) is True
    assert asyncio.run(revoke(seq, NOW + timedelta(days=2))) is False
    assert asyncio.run(live(NOW + timedelta(days=3))) == ()


@pytest.mark.needs_db
def test_a_grant_cannot_run_past_a_quarter_or_carry_a_short_reason_whoever_writes_it(
    head: str,
) -> None:
    """The table refuses what the two value types refuse, for a writer that is not this one. Delete
    this and the limit depends on which code path reached the table."""
    from tests.fixtures.scratch_postgres import sql

    insert = (
        "INSERT INTO agent.browser_grant (kind, target, skill, signed_by, reason, created_at, "
        "expires_at) VALUES ('exemption', 'books', 'a-skill', 'p', %s, %s, %s)"
    )
    with pytest.raises(Exception, match="a_grant_runs_at_most_a_quarter"):
        sql(head, insert, "a reason that is long enough", NOW, NOW + timedelta(days=91))
    with pytest.raises(Exception, match="a_reason_is_a_sentence"):
        sql(head, insert, "short", NOW, NOW + timedelta(days=5))
    with pytest.raises(Exception, match="a_grant_ends_after_it_begins"):
        sql(head, insert, "a reason that is long enough", NOW, NOW)
    sql(head, insert, "a reason that is long enough", NOW, NOW + timedelta(days=90))


@pytest.mark.needs_db
def test_the_application_can_revoke_a_grant_and_change_nothing_else_about_it(head: str) -> None:
    """The grant to `brain_app` is on two columns. Delete this and a signed reason or end can be
    edited after the fact by the application role."""

    async def edit(column: str) -> None:
        async with sessions(head)() as session:
            await session.execute(text("SELECT set_config('app.principal_id', 'x', true)"))
            await session.execute(
                text(f"UPDATE agent.browser_grant SET {column} = {column}")  # noqa: S608
            )

    for column in ("reason", "expires_at", "signed_by", "target", "kind"):
        with pytest.raises(DBAPIError, match="permission denied"):
            asyncio.run(edit(column))


class BrowserGrantChange(enum.StrEnum):
    """The four changes `0275`'s trigger writes, each a leash change about the target.

    Here and not in `brain.audit.record`: the trigger is the only writer, and the recorder pins one
    method per action (`ACTION_BY_METHOD`), so a method for these would be a second `leash_change`
    that nothing calls. An `exception` moves a surface from the assisted rung to the autonomous
    one; an `exemption` moves a skill from refused to exempted; a revocation moves it back.
    """

    EXCEPTION_SIGNED = "exception_signed"
    EXCEPTION_REVOKED = "exception_revoked"
    EXEMPTION_SIGNED = "exemption_signed"
    EXEMPTION_REVOKED = "exemption_revoked"


#: The two rungs each change moves between, `(from, to)`, as the trigger spells them.
BROWSER_GRANT_RUNGS: Final[dict[BrowserGrantChange, tuple[str, str]]] = {
    BrowserGrantChange.EXCEPTION_SIGNED: ("assisted", "autonomous"),
    BrowserGrantChange.EXCEPTION_REVOKED: ("autonomous", "assisted"),
    BrowserGrantChange.EXEMPTION_SIGNED: ("refused", "exempted"),
    BrowserGrantChange.EXEMPTION_REVOKED: ("exempted", "refused"),
}


def leash_details(target: str, what: str, change: BrowserGrantChange) -> dict[str, str]:
    """The details one change carries: a skill's hyphens are underscores, because the ledger keeps
    names (`brain.audit.ledger.FIELD_NAME`)."""
    before, after = BROWSER_GRANT_RUNGS[change]
    return {
        "target": f"browser.{target}.{what.replace('-', '_')}",
        "from_rung": before,
        "to_rung": after,
    }


@pytest.mark.needs_db
def test_signing_and_revoking_are_leash_changes_in_the_ledger(head: str) -> None:
    """The trigger writes a leash change in the shape the recorder's own `leash_change` does, for
    all four changes. Delete this and the entries drift from that shape, which the audit view and
    anyone reading the ledger for a leash change would then misread."""
    document = edited(lambda d: d.update(name="ledgered"))
    asyncio.run(_declare(head, document))
    target = declared_from(document).target

    async def run() -> None:
        async with sessions(head)() as session:
            await declared.sign_exception(
                session,
                target,
                "login",
                signer=administrator("signer"),
                expires_at=NOW + timedelta(days=10),
                reason="a reason that is long enough",
                now=NOW,
                trace_id="trace-sign",
            )
            await declared.sign_exemption(
                session,
                skill="a-skill",
                target="ledgered",
                approver="approver",
                expires_at=NOW + timedelta(days=10),
                reason="a reason that is long enough",
                now=NOW,
                ent_hash=ENT_HASH,
                trace_id="trace-sign",
            )
            await session.commit()
        async with sessions(head)() as session:
            for one in await declared.listing(session, NOW):
                if one.target == "ledgered":
                    await declared.revoke(
                        session,
                        one.seq,
                        by="revoker",
                        now=NOW,
                        ent_hash=ENT_HASH,
                        trace_id="trace-revoke",
                    )
            await session.commit()

    asyncio.run(run())
    found = entries(head, "ledgered")

    recorder = AuditRecorder(
        AuditChain(), actor_id="x", ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )

    def expected(what: str, change: BrowserGrantChange) -> dict[str, str]:
        return leash_details("ledgered", what, change)

    shape = recorder.leash_change(
        agent_id="a", target="t", from_rung=AutonomyTier.ASSISTED, to_rung=AutonomyTier.AUTONOMOUS
    ).details
    assert set(expected("login", BrowserGrantChange.EXCEPTION_SIGNED)) == set(shape)

    assert [(one[0], one[1], one[3]) for one in found] == [
        ("leash_change", "signer", expected("login", BrowserGrantChange.EXCEPTION_SIGNED)),
        ("leash_change", "approver", expected("a-skill", BrowserGrantChange.EXEMPTION_SIGNED)),
        ("leash_change", "revoker", expected("login", BrowserGrantChange.EXCEPTION_REVOKED)),
        ("leash_change", "revoker", expected("a-skill", BrowserGrantChange.EXEMPTION_REVOKED)),
    ]


def test_every_change_moves_between_two_different_rungs_and_a_revocation_reverses_a_signature() -> (
    None
):
    """Delete this and a change that moves nothing, or a revocation that does not undo what it
    revokes, passes."""
    for signed, revoked in (
        (BrowserGrantChange.EXCEPTION_SIGNED, BrowserGrantChange.EXCEPTION_REVOKED),
        (BrowserGrantChange.EXEMPTION_SIGNED, BrowserGrantChange.EXEMPTION_REVOKED),
    ):
        before, after = BROWSER_GRANT_RUNGS[signed]
        assert before != after
        assert BROWSER_GRANT_RUNGS[revoked] == (after, before)


def test_the_migration_and_the_model_agree_on_the_grammars_and_widths() -> None:
    """`0275` copies them rather than reading live code. Delete this and a width changed in the
    model is a width the migration still builds."""
    import importlib.util
    from pathlib import Path

    from brain.audit.ledger import IDENTIFIER
    from brain.browsing.targets import NAME_RE
    from brain.ops.halt import MINIMUM_REASON
    from brain.tables import browsing as model

    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "0275_browser_declarations.py"
    )
    spec = importlib.util.spec_from_file_location("m0275", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.IDENTIFIER == IDENTIFIER
    assert NAME_RE.pattern == migration.SLUG
    assert migration.REASON_CHARS == model.REASON_CHARS
    assert migration.SKILL_CHARS == model.SKILL_CHARS
    assert migration.TARGET_CHARS == model.TARGET_CHARS
    assert migration.MINIMUM_REASON_CHARS == model.MINIMUM_REASON_CHARS == MINIMUM_REASON
    assert tuple(migration.TABLES) == ("agent.browser_target", "agent.browser_grant")


def test_a_registry_built_from_the_stored_targets_plans_against_them() -> None:
    """The registry is the type a plan is made against. Delete this and the stored targets and the
    planner's registry are two shapes that nothing joins."""
    from brain.browsing.planning import Goal, PlanRequest, plan

    registry = TargetRegistry(targets=(declared_from(DOCUMENT).target,))

    made = plan(
        PlanRequest(
            goal=Goal(text="Read this month's invoices", asked_by="alex"),
            target="books",
            surfaces=("invoices",),
        ),
        registry,
    )

    assert [(one.surface, one.verb) for one in made.steps] == [
        ("invoices", Verb.OPEN),
        ("invoices", Verb.READ),
    ]


@pytest.mark.needs_db
def test_the_exceptions_read_are_exceptions_and_only_the_target_asked_for(head: str) -> None:
    """An exemption in the same table is not an exception, and one website's exception is not
    another's. Delete this and the compiler reads an exemption as a permission for writes to run
    unattended, or an exception for one website lets another's writes run."""
    second = declared_from(edited(lambda d: d.update(name="payroll"))).target
    first = declared_from(DOCUMENT).target

    async def run() -> tuple[Any, Any, Any]:
        async with sessions(head)() as session:
            for target in (first, second):
                await declared.sign_exception(
                    session,
                    target,
                    "login",
                    signer=administrator("signer"),
                    expires_at=NOW + timedelta(days=20),
                    reason="a reason that is long enough",
                    now=NOW,
                    trace_id="trace-sign",
                )
            await declared.sign_exemption(
                session,
                skill="a-skill",
                target="payroll",
                approver="approver",
                expires_at=NOW + timedelta(days=20),
                reason="a reason that is long enough",
                now=NOW,
                ent_hash=ENT_HASH,
                trace_id="trace-sign",
            )
            await session.commit()
        async with sessions(head)() as session:
            at = NOW + timedelta(days=1)
            return (
                await declared.live_exceptions(session, at, target="payroll"),
                await declared.live_exceptions(session, at, target="nowhere"),
                await declared.live_exemptions(session, at),
            )

    payroll, nowhere, exemptions = asyncio.run(run())

    assert [(one.target, one.surface) for one in payroll] == [("payroll", "login")]
    assert nowhere == ()
    assert [one.skill for one in exemptions if one.target == "payroll"] == ["a-skill"]


@pytest.mark.needs_db
def test_a_grant_that_has_lapsed_cannot_be_revoked(head: str) -> None:
    """Revoking what already ended would write a revocation and a ledger entry for nothing. Delete
    this and a lapsed permission can be revoked, which is an entry saying something was taken back
    that nobody held."""
    target = declared_from(edited(lambda d: d.update(name="lapsing"))).target

    async def run() -> bool:
        async with sessions(head)() as session:
            await declared.sign_exception(
                session,
                target,
                "login",
                signer=administrator("signer"),
                expires_at=NOW + timedelta(days=2),
                reason="a reason that is long enough",
                now=NOW,
                trace_id="trace-sign",
            )
            await session.commit()
        async with sessions(head)() as session:
            seq = next(
                one.seq for one in await declared.listing(session, NOW) if one.target == "lapsing"
            )
            done = await declared.revoke(
                session,
                seq,
                by="admin",
                now=NOW + timedelta(days=3),
                ent_hash=ENT_HASH,
                trace_id="trace-revoke",
            )
            await session.commit()
            return done

    assert asyncio.run(run()) is False
