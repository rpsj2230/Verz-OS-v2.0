"""The skill lifecycle leaf is closed by exactly the checks that show each of its clauses.

M12.4.9 is a composite: a skill created in the console and another imported at a pinned commit,
neither running until reviewed against a diff, a self-approval recorded as one, an edit waiting for
review while agents keep their pinned version, approval waiting for rehearsed examples, and an
exported skill landing unreviewed. Each clause already had an install check under its own leaf, and
the leaf is named on each of them, so it closes when every one has passed on the install and not
before. This file holds that list, so the composition cannot shrink without a test saying so.

The landing of an exported skill on a second install is not an install check: the owner decided on
2026-09-28 (needs-rupash 103) that a scratch install built in CI shows it, and
`tests/unit/test_skill_export.py` is that proof.

Task ids: M12.4.9
"""

from __future__ import annotations

from brain.ops.acceptance import registered

#: The checks that show the clauses, held as words and not read back from the registry so that a
#: check dropped or renamed fails here. In order: created in the console and unread until reviewed;
#: imported at a pinned commit and not executable before review; self-approval recorded, an edit
#: waiting for review against a diff and agents keeping their pin; approval waiting for rehearsed
#: examples; an export reading back as an unreviewed submission.
THE_CHECKS_THAT_SHOW_THE_LIFECYCLE = (
    "a_pasted_or_uploaded_skill_waits_undecided_and_unread",
    "a_skill_is_imported_from_a_github_commit_and_from_an_address",
    "an_edit_is_a_new_version_and_moves_no_agent_until_reassigned",
    "a_version_with_examples_is_approved_only_once_rehearsed",
    "an_approved_skill_is_exported_and_a_changed_package_is_refused",
)


def test_the_skill_lifecycle_leaf_is_named_on_exactly_the_checks_that_show_its_clauses() -> None:
    """Delete this and a clause check can lose the leaf, or a check showing nothing of the
    lifecycle can gain it, and M12.4.9 closes on a different set of evidence than the sentence
    says without anybody being told."""
    naming = {one.name for one in registered() if "M12.4.9" in one.leaves}
    assert naming == set(THE_CHECKS_THAT_SHOW_THE_LIFECYCLE)


def test_every_check_showing_a_clause_still_names_its_own_leaf_beside_the_lifecycle() -> None:
    """The positive case: naming the composite on a check does not take its own leaf away. Delete
    this and the leaf could be moved off a clause check instead of added to it, which would stop
    the leaf it first proved from closing."""
    by_name = {one.name: one.leaves for one in registered()}
    for name in THE_CHECKS_THAT_SHOW_THE_LIFECYCLE:
        assert len(by_name[name]) >= 2
