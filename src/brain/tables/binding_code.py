"""`auth.binding_code`: the one-time codes that bind a chat account to a person, and whether each
has been used.

`brain.channels.binding` had the rules for binding a chat identity outward from a signed-in
session, single use and rebinding, and nowhere to keep a code between the moment a person was
shown it and the moment the bot received it. This is that place.

**A row holds a digest of the code, never the code.** `code_digest` is
`brain.channels.binding.code_digest` over the channel and the value the person was shown, and a
check pins it to sixty-four lowercase hex characters, so a raw code cannot be written here by a
hand-typed statement either. A table of live codes would be a table of ten-minute credentials:
anybody who could read it could present one from their own chat account and be answered as
somebody else. See `A_CODE_IS_KEPT_AS_A_DIGEST`.

**Single use is the database's, and the application cannot undo it.** A code is spent by one
`UPDATE ... WHERE used_at IS NULL`, so of two presentations racing each other exactly one finds
the row, and `0118`'s update policy admits no row whose `used_at` is set, so no statement the
application role can make brings a spent code back. See `A_SPENT_CODE_STAYS_SPENT`.

**The sign-in that minted it is kept, and asked again when it is used.** `session_id` is the
identity provider's session the code was shown in, the key of `auth.session`, so signing out,
or an administrator ending that session from the Sessions screen, stops the code working before
its ten minutes are up.

**No `deleted_at` and no DELETE.** A code is used, or it lapses; it is never retired and never
removed, and a newer code for the same channel shortens an older one's life to now rather than
deleting it. What is kept is a digest nobody can present, who it was for and four instants.

Task ids: M10.3.1, M10.3.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.gate.context import Channel
from brain.tables.channel import CHANNEL_CHARS
from brain.tables.identity import (
    IDENTITY_HASH_CHARS,
    IDENTITY_HASH_PATTERN,
    PRINCIPAL_ID_CHARS,
    SESSION_ID_CHARS,
    one_of,
)

#: Why the code is kept as a digest.
A_CODE_IS_KEPT_AS_A_DIGEST: Final = (
    "A code is a credential for ten minutes: whoever presents it from a chat account is bound as "
    "the person it was minted for. The table keeps a digest of the channel and the code, which is "
    "enough to find the row when the code arrives and useless to anybody reading the table."
)

#: Why a spent code cannot be brought back.
A_SPENT_CODE_STAYS_SPENT: Final = (
    "A code is spent by one update that finds it only while it is unspent, and the table's update "
    "policy admits no spent row, so two presentations racing each other bind once and no later "
    "statement the application can make spends it again."
)

#: The same digest shape as a channel identity: a sha256 hexdigest.
CODE_DIGEST_CHARS: Final = IDENTITY_HASH_CHARS
CODE_DIGEST_PATTERN: Final = IDENTITY_HASH_PATTERN


class BindingCodeRow(Base):
    """`auth.binding_code`. One code a signed-in person was shown, for one channel (M10.3.1)."""

    __tablename__ = "binding_code"

    #: `brain.channels.binding.code_digest(channel, value)`. Never the value.
    code_digest: Mapped[str] = mapped_column(String(CODE_DIGEST_CHARS), primary_key=True)
    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), nullable=False)
    #: Who the code binds a chat account to: the person signed in when it was minted.
    principal_id: Mapped[str] = mapped_column(
        String(PRINCIPAL_ID_CHARS),
        ForeignKey("auth.principal.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: The identity provider's session it was shown in, `auth.session.id`, as a value.
    session_id: Mapped[str] = mapped_column(String(SESSION_ID_CHARS), nullable=False)
    minted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Ten minutes after minting, or earlier when a newer code for the channel replaced it.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When the code bound somebody. Set once and never cleared.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"code_digest ~ '{CODE_DIGEST_PATTERN}'", name="digest_shape"),
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint("channel <> 'console'", name="not_the_sign_in_channel"),
        CheckConstraint("length(btrim(session_id)) > 0", name="session_present"),
        CheckConstraint("expires_at >= minted_at", name="expires_after_minting"),
        CheckConstraint("used_at IS NULL OR used_at >= minted_at", name="used_after_minting"),
        {"schema": "auth"},
    )
