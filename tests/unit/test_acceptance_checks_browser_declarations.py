"""The declaration install check: what it names, passing on PostgreSQL and leaving nothing, and
made to fail with the product broken where each statement of its sentence rests.

The database half builds PostgreSQL at head and runs the module as the worker does. Each failure
is a single product defect, injected by replacing one function the check's readers call, and the
check must fail with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops import acceptance_checks_browser_declarations as module
from brain.ops.acceptance import FAILED, PASSED, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_cards import INSTALL, run_checks

MODULE = "brain.ops.acceptance_checks_browser_declarations"
CHECK = "a_website_is_declared_and_permissions_signed_for_it_are_read"
TABLES = ("agent.browser_target", "agent.browser_grant")


def test_the_module_declares_the_check_and_the_leaves_it_closes() -> None:
    """Delete this and a check can lose a leaf with the page showing the same row, or sit outside
    the keys this package was given."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (CHECK, ("M19.2.4", "M19.6.7", "M19.7.3", "M19.9.7"))
    ]
    assert checks_in(MODULE) == [CHECK]
    assert 2300 <= module.CHECK_ORDER <= 2399


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_browser_declarations") as url:
        yield url


@pytest.fixture(autouse=True)
def _install_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def outcome(url: str) -> tuple[str, str]:
    return run_checks(url, registered((MODULE,)))[CHECK]


def rows(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in TABLES}  # noqa: S608


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing_it_wrote(install: str) -> None:
    """**The module as the worker runs it.** It passes, and neither table, nor any table the suite
    counts, holds a row it wrote. Delete this and a check that cannot pass on the real schema, or
    one that commits a declaration or a signature to a client's install, reaches the owner first."""
    before, before_rows = counts(install), rows(install)

    assert outcome(install) == (PASSED, "")
    assert counts(install) == before and rows(install) == before_rows


def fails_with(install: str, words: str) -> None:
    result = outcome(install)
    assert result[0] == FAILED and words in result[1], result


@pytest.mark.needs_db
def test_a_codec_that_keeps_a_key_it_should_refuse_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a closed document that quietly stops being closed is not noticed."""
    from brain.browsing import declared

    real = declared.declared_from

    def lenient(document: Any) -> Any:
        return real({key: value for key, value in document.items() if key != "selector"})

    monkeypatch.setattr(declared, "declared_from", lenient)

    fails_with(install, "carrying a key the codec does not take")


@pytest.mark.needs_db
def test_a_compiler_that_never_reads_the_exceptions_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the stored exceptions never read, a signed exception changes nothing. Delete this and
    the permission is a row nothing consults."""
    from brain.browsing import declared

    async def none(session: Any, now: Any, *, target: Any = None) -> tuple[()]:
        return ()

    monkeypatch.setattr(declared, "live_exceptions", none)

    fails_with(install, "still waited for a person")


@pytest.mark.needs_db
def test_a_reader_that_ignores_the_end_of_an_exception_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end is held twice, by the query that reads the exceptions in force and by the exception
    itself, so both are blinded here. Delete this and an exception that lapsed is read as in force
    for ever, and nothing at the level of the install notices."""
    from datetime import timedelta

    from brain.browsing import declared
    from brain.browsing.autonomy import SurfaceException

    real = declared.live_exceptions

    async def long_ago(session: Any, now: Any, *, target: Any = None) -> Any:
        return await real(session, now - timedelta(days=30), target=target)

    monkeypatch.setattr(declared, "live_exceptions", long_ago)
    monkeypatch.setattr(
        SurfaceException,
        "covers",
        lambda self, target, surface, now: (self.target, self.surface) == (target, surface),
    )

    fails_with(install, "after its exception had lapsed")


@pytest.mark.needs_db
def test_a_reader_that_ignores_a_revocation_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a revoked exception is still in force: a permission with no way back."""
    from brain.browsing import declared

    async def not_revoking(session: Any, seq: int, **_: Any) -> bool:
        return True

    monkeypatch.setattr(declared, "revoke", not_revoking)

    fails_with(install, "still listed")


@pytest.mark.needs_db
def test_a_skill_rule_that_never_refuses_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a browser skill is allowed over a website that has an API."""
    from brain.console import skill_library

    monkeypatch.setattr(skill_library, "browser_refusals", lambda *a, **k: ())

    fails_with(install, "browser skill was allowed")


@pytest.mark.needs_db
def test_a_skill_rule_that_ignores_the_exemptions_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and an exemption is a row, and the skill is refused whatever was signed."""
    from brain.browsing import declared

    async def none(session: Any, now: Any) -> tuple[()]:
        return ()

    monkeypatch.setattr(declared, "live_exemptions", none)

    fails_with(install, "live exemption was still refused")


@pytest.mark.needs_db
def test_a_signature_that_leaves_no_ledger_entry_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the ledger entry's subject moved off the target, the check finds none. Delete this and
    the audit half of M19.9.7 rests on a trigger nobody looks at."""
    from brain.ops import acceptance_checks_browser_declarations as check_module

    async def none(h: Any, target: str) -> list[tuple[str, str]]:
        return []

    monkeypatch.setattr(check_module, "_ledger_entries", none)

    fails_with(install, "leave a leash change in the ledger")


@pytest.mark.needs_db
def test_a_page_that_shows_the_screen_to_anybody_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the first thing the check asks of the screen is never failed."""
    from brain import browser_routes

    monkeypatch.setattr(browser_routes, "may_administer", lambda reach, now: True)

    fails_with(install, "without the authority over browsers was shown")


@pytest.mark.needs_db
def test_a_switch_that_is_on_whatever_it_says_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a declaration accepted with the switch off, on every install, is not
    noticed."""
    from brain import browser_routes

    async def always(session: Any) -> bool:
        return True

    monkeypatch.setattr(browser_routes, "declarations_are_on", always)

    fails_with(install, "while the switch was off")


@pytest.mark.needs_db
def test_a_compiler_that_never_waits_for_a_person_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check's 'before' half, which says a write waits until somebody signs, is
    only ever true."""
    from brain.browsing.envelope import Envelope

    monkeypatch.setattr(Envelope, "awaits_approval", lambda self: False)

    fails_with(install, "nobody signed an exception for was compiled")


@pytest.mark.needs_db
def test_exemptions_that_are_live_before_anybody_signs_them_fail_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a skill rule that never refuses in the first place is not told apart from
    one that refuses and is then exempted."""
    from brain.browsing import declared

    async def always(session: Any, now: Any) -> tuple[Any, ...]:
        return (_COVERS_EVERYTHING,)

    monkeypatch.setattr(declared, "live_exemptions", always)

    fails_with(install, "no exemption")


#: An exemption that covers whatever it is asked about, standing in for one signed before anybody
#: signed anything.
_COVERS_EVERYTHING = SimpleNamespace(covers=lambda skill, target, now: True)


@pytest.mark.needs_db
def test_an_exception_signable_for_a_page_that_does_not_write_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the signer-must-be-able-to-write rule, which `autonomy.sign` holds, is not
    something the install ever checks."""
    from brain.browsing import declared
    from brain.browsing.autonomy import SurfaceException

    def lenient(
        target: Any, surface: str, *, signer: Any, expires_at: Any, reason: str, now: Any
    ) -> Any:
        return SurfaceException(
            target=target.name,
            surface=surface,
            signed_by=signer.principal_id,
            expires_at=expires_at,
            reason=reason,
        )

    monkeypatch.setattr(declared, "sign", lenient)

    fails_with(install, "does not write")


@pytest.mark.needs_db
def test_an_exemption_that_covers_every_skill_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and an exemption signed for one skill that quietly covers all of them is not
    noticed, which is the exemption the loader was written to prevent."""
    from brain.browsing.skill_gate import Exemption

    monkeypatch.setattr(
        Exemption,
        "covers",
        lambda self, skill, target, now: self.target == target and self.is_live(now),
    )

    fails_with(install, "browser skill was allowed")


@pytest.mark.needs_db
def test_a_revocation_that_the_compiler_forgets_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listing hides a revoked exception but the compiler still reads it. Delete this and the
    check's last look at the compiler is never failed."""
    from datetime import UTC, datetime

    from brain.browsing import declared
    from brain.browsing.autonomy import SurfaceException

    real = declared.live_exceptions
    seen = {"calls": 0}

    async def forgetful(session: Any, now: Any, *, target: Any = None) -> Any:
        seen["calls"] += 1
        if seen["calls"] in (2, 4):
            return (
                SurfaceException(
                    target=target,
                    surface="filing",
                    signed_by="p",
                    expires_at=datetime(2999, 1, 1, tzinfo=UTC),
                    reason="a reason that is long enough",
                ),
            )
        return await real(session, now, target=target)

    monkeypatch.setattr(declared, "live_exceptions", forgetful)

    fails_with(install, "after its exception was revoked")


@pytest.mark.needs_db
def test_an_exemption_the_loader_forgets_to_end_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check's last look at the skill rule is never failed."""
    from brain.browsing import declared

    real = declared.live_exemptions
    seen = {"calls": 0}

    async def forgetful(session: Any, now: Any) -> Any:
        seen["calls"] += 1
        if seen["calls"] == 4:
            return (_COVERS_EVERYTHING,)
        return await real(session, now)

    monkeypatch.setattr(declared, "live_exemptions", forgetful)

    fails_with(install, "after its exemption was revoked")


@pytest.mark.needs_db
def test_a_retirement_that_changes_nothing_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a retire button that does nothing is not noticed."""
    from brain.browsing import declared

    async def nothing(session: Any, name: str, *, by: str) -> bool:
        return True

    monkeypatch.setattr(declared, "retire", nothing)

    fails_with(install, "retired website was still declared")
