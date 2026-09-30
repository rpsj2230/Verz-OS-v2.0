"""The Install page's rows for `brain.ops.acceptance_checks_accounts`, in their order.

The module's checks are run on PostgreSQL by `tests/unit/test_acceptance.py`'s whole-suite run;
this file holds what the module registers, so a package adding a check to it edits this file only.

Task ids: M38.5.1
"""

from __future__ import annotations

from tests.unit.test_acceptance import checks_in


def test_the_accounts_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_accounts") == [
        "the_staff_sync_gives_the_active_an_account_and_closes_a_leaver_s",
    ]
