"""The switch on a person asking, from their own page, for their data to be deleted.

Off because a new capability ships switched off on every install, and because it puts a request in
front of the retention owner that nobody on the install has agreed to be asked for: whoever holds
`admin:erasure` over everything is then asked to act on a person's own ask. It changes nothing a
person holds. The ask is a record and the erasure is still filed, by that administrator, through the
queue that carries it out. `brain.member_deletion_routes` asks the switch before an ask is taken and
never before a reading, so a person's earlier ask, and what became of it, stay readable with it off.

Task ids: M40.4.2.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

MEMBER_DELETION_REQUESTS: Final = Feature(
    name="member_deletion_requests",
    title="Let a person ask, from their own page, for their data to be deleted",
    what=(
        "A person can ask for their data to be deleted from My workspace. The page first shows "
        "which stores a deletion reaches, which it does not reach and rotates out with time, and "
        "which are kept deliberately. Their ask waits for whoever holds the erasure authority over "
        "everything, who files the erasure through the Retention screen; nothing is deleted by the "
        "ask itself."
    ),
    while_off=(
        "No new ask can be made. An ask already made stays readable on the person's page and on "
        "the Retention screen, and an administrator can still file the erasure it waits for."
    ),
    read_by=("brain.member_deletion_routes:deletion_requests_are_on",),
)
