"""Who may see which account signs in as whom, and what the Sign-in links screen may say.

`brain.identity.sign_in_binding` writes a sign-in link and retires one, and until M27.7.11 the
only way to learn which people could sign in at all was a statement against
`auth.principal_identity`. The screen that answers it needed a read decision, and there was none
to serve: the screen registry has a Sessions screen and no screen for links, and nothing under
`brain.console` decided who may be told that a principal can sign in. This is that decision, and
it is deliberately almost nothing.

**Seeing the links is the authority to make one, and nothing narrower.** A link is a way into a
principal, and `brain.sign_in_routes` already argues that the authority to make one is
`SIGN_IN_AUTHORITY` held over everything, because a principal who cannot yet sign in has no
attributes a scope could be matched against. The listing is the same fact from the other side:
which principals have a way in is the map of who can be signed in as, and a department-scoped
reader shown part of it has been handed the part a scope cannot describe. So the question is
`first_administrator.holds_everywhere`, asked here and not restated, and there is no partial
answer. See `WHO_CAN_SIGN_IN_IS_THE_MAP_A_LINK_IS_MADE_ON`.

**The account is never shown, because it is not held.** `auth.principal_identity` stores a
digest of the issuer and the subject and not the subject, which is `brain.tables.identity`'s
first rule. The digest is not shown either: it is not something a person can compare with
anything, and a column of hex under a heading about accounts reads as though it were the
account. The screen says in words where the account is kept. See
`THE_ACCOUNT_IS_KEPT_AT_THE_IDENTITY_PROVIDER_AND_NOT_HERE`.

**Which row is the last administrator's is the store's own rule, asked once for the page.**
`sign_in_binding.decide_unlink` refuses to retire the last link held by an administrator, and the
screen marks that row so the control beside it can say why before anybody presses it. The mark
comes from the same function over the same answer, rather than from a second reading of what
last means, and the refusal is still the store's, taken under its lock, whatever the page showed.

Scope: domain logic. Nothing here opens a connection or reads a clock.

Task ids: M27.7.11
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.core.entitlement import EntitlementSet
from brain.identity.first_administrator import SIGN_IN_AUTHORITY, holds_everywhere
from brain.identity.sign_in_binding import SignInLink, Unlinked, decide_unlink

# ------------------------------------------------------------ written-down reasons

#: Why the listing needs the authority to link over everything.
WHO_CAN_SIGN_IN_IS_THE_MAP_A_LINK_IS_MADE_ON: Final = (
    "A sign-in link is a way into a principal, and the list of them is the list of everybody "
    "who can be signed in as. brain.sign_in_routes requires SIGN_IN_AUTHORITY over everything "
    "to make one, because a principal who cannot sign in yet has nothing a scope can be checked "
    "against, and the same is true of showing one. A reader holding it in part of the company "
    "does not hold it, and is refused the screen rather than shown a slice of it."
)

#: What the screen says about the account, which it cannot show.
THE_ACCOUNT_IS_KEPT_AT_THE_IDENTITY_PROVIDER_AND_NOT_HERE: Final = (
    "The identity provider account a person signs in with is not stored here, only a one-way "
    "fingerprint of it, so this screen can say who can sign in and since when but not which "
    "account they use. The identity provider's own user list shows the account."
)

#: What unlinking does, said before the control is pressed.
UNLINKING_TAKES_EFFECT_ON_THE_NEXT_REQUEST: Final = (
    "Unlinking stops that account signing in as this person from their next request: every "
    "request asks who an account is, and an unlinked account is nobody. It removes no grant, "
    "does not delete the person, and the account can be linked again."
)

#: Why the last administrator's link is kept, as the refusal and the row say it.
THE_LAST_ADMINISTRATOR_KEEPS_THEIR_LINK: Final = (
    "This is the last administrator who can sign in. Unlinking it would leave nobody able to "
    "sign in to link anybody, this administrator included. Link another administrator first."
)

#: The capability the screen is read and written with. Imported rather than written out: the
#: route that makes a link and this screen are one authority, and a second spelling of it would
#: be two answers to who may make a way in.
LINK_AUTHORITY: Final = SIGN_IN_AUTHORITY


@dataclass(frozen=True)
class LinkRow:
    """One link as the screen shows it. No account, no digest and no count of anything."""

    principal_id: str
    display_name: str
    department: str | None
    linked_at: datetime
    #: Unlinking this one would be refused as the last administrator's.
    last_administrator: bool


def may_see_links(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reader may open the Sign-in links screen. See
    `WHO_CAN_SIGN_IN_IS_THE_MAP_A_LINK_IS_MADE_ON`."""
    return holds_everywhere(reach, now)


def link_rows(links: Iterable[SignInLink], *, administrators: Iterable[str]) -> tuple[LinkRow, ...]:
    """The links as rows, each marked where the store would refuse to unlink it.

    `administrators` is `SignInBindings.administrators_linked`, which is complete where the
    listing may be bounded: whether a row is the last administrator's depends on every linked
    administrator, not on the ones that fitted on the page.
    """
    held = frozenset(administrators)
    listed = tuple(links)
    return tuple(
        LinkRow(
            principal_id=one.principal_id,
            display_name=one.display_name,
            department=one.department,
            linked_at=one.bound_at,
            last_administrator=decide_unlink(
                one.principal_id, linked={one.principal_id}, administrators=held
            )
            is Unlinked.LAST_ADMINISTRATOR,
        )
        for one in listed
    )
