"""The switch on recording who owns knowledge, grants and connectors, and when the review is.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off because it is a new place an administrator writes the handover into the install: the named
client owners and the date the first review is booked. Reading the handover pack (the service
level statement and why it is or is not ready, the model providers named as subprocessors, who
owns what, and the sentence that the new system starts without the old one's learning) is not
behind it, since reading changes nothing. What it holds back is the two writes. Turning it off
again leaves what was recorded in place and stops anybody changing it.

Task ids: M37.4.3.3, M37.4.3.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

HANDOVER_PACK: Final = Feature(
    name="handover_pack",
    title="Record the named owners and the review date in the handover pack",
    what=(
        "An administrator holding the install authority may name, for knowledge, grants and "
        "connectors, who at the company owns each and how to reach them, and book the review "
        "that happens thirty days after launch. The handover pack then lists them and says what "
        "is still missing."
    ),
    while_off=(
        "The handover pack is still read: the service level statement or the reason it cannot "
        "be written, the subprocessors, and what is missing. Owners and the review date already "
        "recorded stay as they are and nobody can change them."
    ),
    read_by=(
        "brain.handover_routes:_page",
        "brain.handover_routes:save_owners",
        "brain.handover_routes:book_review",
    ),
)
