"""Where the handover's two human facts are kept: who owns what, and when the review is.

`brain.launch` decides what a handover pack must say and refuses one that is incomplete. Two of its
inputs are facts nothing in the system can derive: the named person at the client who owns
knowledge, who owns grants and who owns connectors (`launch.Owner`), and the day the first review is
booked for (`launch.review_gaps`). Until this module they were arguments a test passed. They are
kept as two settings, `handover.owners` and `handover.review`, because each is one value that a
person writes and the next reader reads, which is the argument `brain.ops.backup_report_run` makes
for its own record; the settings table says who wrote it and when, and its trigger records the
change on the ledger. No table and no migration.

**What is read back goes through `launch`'s own constructors.** A stored owner with no contact is a
row somebody inserted by hand, and `Owner` refuses it again on the way out, so a screen cannot
show a handover that `launch` would have refused to write. A value that no longer reads is reported
as not recorded and never raised: the pack then says the owner is missing, which is the truth the
person needs.

**Names of people are the client's own data and are never put in this repository.** Nothing here
defaults an owner, and a fixture uses made-up names.

Task ids: M37.4.3.3, M37.4.3.5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.launch import LaunchError, Owner, Responsibility
from brain.ops.setting_store import SettingState, put, read_namespace
from brain.tables.config import SettingType

NAMESPACE: Final = "handover"
OWNERS_KEY: Final = "handover.owners"
REVIEW_KEY: Final = "handover.review"


@dataclass(frozen=True)
class Review:
    """The launch day and the day the first review is booked for."""

    launched_on: date
    review_booked_for: date


@dataclass(frozen=True)
class Recorded:
    """What the install holds, and the sentences for what it holds but cannot read."""

    owners: tuple[Owner, ...]
    review: Review | None
    unreadable: tuple[str, ...]


def owners_value(owners: tuple[Owner, ...]) -> dict[str, Any]:
    """The owners as a setting holds them: an object, since a setting's JSON is always one."""
    return {
        "owners": [
            {"responsibility": one.responsibility.value, "name": one.name, "contact": one.contact}
            for one in owners
        ]
    }


def owners_from(value: Any) -> tuple[Owner, ...]:
    """Owners from a stored value, refusing anything `launch.Owner` refuses."""
    listed = value.get("owners") if isinstance(value, dict) else None
    if not isinstance(listed, list):
        msg = "the stored owners are not a list"
        raise LaunchError(msg)
    found: list[Owner] = []
    for entry in listed:
        if not isinstance(entry, dict):
            msg = "a stored owner is not an object"
            raise LaunchError(msg)
        try:
            found.append(
                Owner(
                    responsibility=Responsibility(entry["responsibility"]),
                    name=str(entry["name"]),
                    contact=str(entry["contact"]),
                )
            )
        except (KeyError, ValueError) as error:
            msg = "a stored owner does not read"
            raise LaunchError(msg) from error
    return tuple(found)


def review_from(value: Any) -> Review:
    """The review from a stored value."""
    try:
        return Review(
            launched_on=date.fromisoformat(value["launched_on"]),
            review_booked_for=date.fromisoformat(value["review_booked_for"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        msg = "the stored review does not read"
        raise LaunchError(msg) from error


async def recorded(session: AsyncSession) -> Recorded:
    """The owners and the review the install holds. Unreadable values are said, not raised."""
    held = await read_namespace(session, NAMESPACE)
    unreadable: list[str] = []
    owners: tuple[Owner, ...] = ()
    review: Review | None = None
    row: SettingState | None = held.get(OWNERS_KEY)
    if row is not None:
        try:
            owners = owners_from(row.value)
        except LaunchError:
            unreadable.append("the recorded owners could not be read, so none is shown")
    row = held.get(REVIEW_KEY)
    if row is not None:
        try:
            review = review_from(row.value)
        except LaunchError:
            unreadable.append("the recorded review date could not be read, so none is shown")
    return Recorded(owners=owners, review=review, unreadable=tuple(unreadable))


async def save_owners(session: AsyncSession, owners: tuple[Owner, ...], *, by: str) -> None:
    """Keep the owners, replacing the earlier ones. The caller attributes and commits."""
    await put(
        session,
        OWNERS_KEY,
        value_type=SettingType.JSON,
        value=owners_value(owners),
        description="Who at the company owns knowledge, grants and connectors",
        updated_by=by,
    )


async def save_review(session: AsyncSession, review: Review, *, by: str) -> None:
    """Keep the booked review. The caller attributes and commits."""
    await put(
        session,
        REVIEW_KEY,
        value_type=SettingType.JSON,
        value={
            "launched_on": review.launched_on.isoformat(),
            "review_booked_for": review.review_booked_for.isoformat(),
        },
        description="The day the post-launch review is booked for",
        updated_by=by,
    )
