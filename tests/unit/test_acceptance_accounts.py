"""The Install page's rows for `brain.ops.acceptance_checks_accounts`, in their order.

The module's checks are run on PostgreSQL by `tests/unit/test_acceptance.py`'s whole-suite run;
this file holds what the module registers, so a package adding a check to it edits this file only,
and the Forgot password mail check's three outcomes, which need a relay and a record that run has
not got.

Task ids: M38.5.1, M40.7.1, M1.10.3
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops import acceptance_checks_accounts as accounts
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_automation import run_check
from tests.unit.test_acceptance_channels import save_relay

MODULE = "brain.ops.acceptance_checks_accounts"
MAIL = "forgot_password_is_sent_through_the_relay_on_notifications"


def test_the_accounts_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_accounts") == [
        "the_staff_sync_gives_the_active_an_account_and_closes_a_leaver_s",
        "the_staff_list_keeps_out_whom_it_names_and_lets_back_its_own",
        MAIL,
        "the_staff_list_puts_every_active_person_on_people",
    ]


def mail_check() -> Check:
    (found,) = [one for one in registered((MODULE,)) if one.name == MAIL]
    return found


def test_the_mail_check_proves_the_leaf_that_gives_the_sign_in_service_the_relay() -> None:
    """Delete this and the check can close a leaf it does not exercise."""
    assert mail_check().leaves == ("M40.7.1",)


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    from tests.unit.test_acceptance import INSTALL

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    with at_head("brain_acceptance_accounts") as url:
        yield url


def given(url: str, host: str) -> None:
    """What `python -m brain.ops.sign_in_mail --read-back` leaves after a release gave the relay."""
    from tests.fixtures.scratch_postgres import sql

    for name, value in (("version", '"v-acceptance"'), ("host", f'"{host}"')):
        sql(
            url,
            "INSERT INTO ops.setting (key, value_type, value, description, updated_by)"
            " VALUES (%s, 'string', %s::jsonb, 'given', 'release.sign-in-mail')",
            f"sign_in_mail.{name}",
            value,
        )


@pytest.mark.needs_db
def test_the_mail_check_is_not_run_until_there_is_a_relay_and_a_release_has_given_it(
    install: str,
) -> None:
    """Delete this and an install with no relay, or one no release has reached yet, could show
    Forgot password's mail as proved, or as failed when nothing is wrong."""
    before = counts(install)
    assert run_check(install, (mail_check(),)) == {
        MAIL: (NOT_RUN, accounts.NO_RELAY_FOR_THE_RESET_EMAIL)
    }
    assert counts(install) == before
    save_relay(install)
    before = counts(install)
    assert run_check(install, (mail_check(),)) == {
        MAIL: (NOT_RUN, accounts.NOT_GIVEN_TO_THE_SIGN_IN_SERVICE_YET)
    }
    assert counts(install) == before


@pytest.mark.needs_db
def test_the_mail_check_passes_on_the_relay_s_host_and_fails_on_another(install: str) -> None:
    """**The positive case and its sibling.** The host the sign-in service reported is the
    relay's: passed. Another host: failed, in words that name neither.

    Delete this and a check satisfied by anything recorded at all, or refusing everything, goes
    on the Install page."""
    save_relay(install)
    given(install, "smtp.acceptance.invalid")
    assert run_check(install, (mail_check(),)) == {MAIL: (PASSED, "")}


@pytest.mark.needs_db
def test_the_mail_check_fails_when_the_sign_in_service_reported_another_host(
    install: str,
) -> None:
    """Delete this and a realm sending with some other relay would read as the one saved."""
    save_relay(install)
    given(install, "smtp.elsewhere.invalid")
    outcome, reason = run_check(install, (mail_check(),))[MAIL]
    assert outcome == FAILED
    assert "not the relay saved on Notifications" in reason
    assert "elsewhere" not in reason
