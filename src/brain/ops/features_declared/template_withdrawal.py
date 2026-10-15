"""Withdrawing a template version, and moving a template to another install (needs-rupash 236).

Off because a new capability ships switched off on every install, and because both change what an
install offers its people and what leaves it. A withdrawal hides a published version from every new
install on one administrator's say-so, and an export puts a signed template into somebody's hands
to carry elsewhere. `brain.template_withdrawal_routes` asks the switch before a
withdrawal, an export or an import, and never before an undo or a read: a switch turned off must not
leave a version hidden with no way to bring it back.

Task ids: M27.15.35
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

TEMPLATE_WITHDRAWAL: Final = Feature(
    name="template_withdrawal",
    title="Withdraw a template version, and move a template to another install",
    what=(
        "An administrator can withdraw a published template version so it is no longer offered "
        "for a new install, with a reason, and undo that. An agent already installed from it "
        "keeps running and stays on that version. A template version can be exported as a "
        "document and a document from another install can be imported, after it is read for "
        "company details; an imported template is signed again by this install, because only the "
        "install that made a signature can check it."
    ),
    while_off=(
        "No version can be withdrawn and no template can be exported or imported. A version that "
        "was withdrawn while this was on stays withdrawn, can still be seen by the people who "
        "withdrew it, and the withdrawal can still be undone."
    ),
    read_by=("brain.template_withdrawal_routes:withdrawal_is_on",),
)
