"""Roll-ups naming the clauses of a composite leaf no check shows yet, and a check that cannot run.

Three leaves are sentences of several clauses, and some of those clauses are shown by a check
written for a narrower leaf while others have no check at all. A roll-up over only the clauses
with checks would close the leaf on less than it says, which `brain.ops.acceptance_roll_up`
refuses. One that read every clause and said only "not run" would leave the Install page with
nothing about what was missing. **These roll-ups name the clauses with no check**, in the reason
the helper gives (`brain.ops.acceptance_roll_up.A_CLAUSE_WITH_NO_CHECK_IS_NOT_DEMONSTRATED`), so
the page and the next builder both read what is left, and each clause is mapped to the leaf that
would carry its check when one is written.

**The gaps are pinned.** `tests/unit/test_acceptance_proof_gaps.py` lists exactly which clauses have
no check today, so the day one is written that test goes red and says to move the clause, and a
clause cannot be quietly dropped from a roll-up to make it pass.

**M1.8.5, identity.** Clauses with a check: the single-use binding code, the unbound sender told
how to bind, the same reach on web and chat, a password-only sign-in refused administration, and
Forgot password sent through the relay. Without one: a person signing in through the company
identity provider and receiving a product id (the owner's own sign-in, needs-rupash 91 check 1),
the session's idle and absolute limits, and the account bound to nobody being told once who can
link it.

**M11.8.3, live reading.** Clauses with a check: a question over a connected ticket source answered
live, a canary from a ticket body found in no table, and deny-listed fields never projected.
Without one: a question spanning many records answered from projected headers (the fast lane has no
question shape that filters a source's records, so only one record by name is asked today). The
clause on document embeddings computed with no outbound call has a check of its own (M7.3.3, in
the knowledge-models module), which says NOT_RUN where the local inference server is not
delivered (needs-rupash item 25), and this roll-up reads what it says.

**M1.6.18 and M1.1.9 are checks that cannot run, and say why.** Making an account for a reserved
person at the owner's own sign-in service and pressing Forgot password for it needs a mailbox
somebody reads, and the earlier decision for the staff accounts check stands: it never calls the
install's sign-in service with a reserved person, because that would make a real account there.
The plan and the closing of a leaver are shown by
`the_staff_sync_gives_the_active_an_account_and_closes_a_leaver_s` against a stand-in sign-in
service; the email and the second factor are the owner doing it once (needs-rupash 91, check 1).
Signing a reserved person in with Lark (M1.1.9) needs a real Lark account and the owner's real
sign-in service, so it is the owner signing in once and a leaver being refused, recorded on the
Requirement checks screen (needs-rupash 197); the application's own half of it is
`brain.ops.acceptance_checks_lark_sign_in`.

Task ids: M1.8.5, M11.8.3, M1.6.18, M1.1.9
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import CheckNotRunError, check
from brain.ops.acceptance_roll_up import clauses_demonstrated
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, after every module they read.
CHECK_ORDER: Final = 1291

#: Said by the check that cannot run. Held here and not imported, because a reason is held to a
#: literal in the file that raises it (`tests/unit/test_acceptance.py`).
A_REAL_ACCOUNT_AND_A_REAL_MAILBOX_ARE_NEEDED: Final = (
    "pressing Forgot password for a reserved person needs a mailbox somebody reads, and a check "
    "never makes a real account at the sign-in service; the owner does it once and records it"
)

#: Said by the check that cannot sign a person in with Lark, for the same reason.
A_REAL_LARK_ACCOUNT_AND_A_REAL_SIGN_IN_ARE_NEEDED: Final = (
    "signing a person in with Lark needs a real Lark account and the sign-in service itself, and "
    "a check never makes either; the owner signs in once, and a leaver is refused, and records it"
)

#: The clauses of M1.8.5, each with the leaf whose checks show it. A leaf named by no check is a
#: clause that has none yet.
IDENTITY_CLAUSES: Final = {
    "signs in through the identity provider": ("M1.8.5",),
    "binds a chat identity by a single-use code": ("M10.3.1",),
    "an unbound chat identity is told how to bind": ("M10.2.1",),
    "the same reach on web and chat": ("M13.7.5",),
    "idle and absolute session limits": ("M1.1.6",),
    "a password-only sign-in is refused administration": ("M27.9.1",),
    "an account bound to nobody is told once": ("M1.8.5",),
    "a forgotten password is reset by email": ("M40.7.1",),
}

#: The clauses of M11.8.3, with the same rule.
LIVE_READING_CLAUSES: Final = {
    "a ticket question is answered live": ("M11.6.2",),
    "a canary is found in no table": ("M11.4.5", "M11.8.2"),
    "deny-listed fields are never projected": ("M11.4.2", "M11.8.1"),
    "a question spanning many records": ("M11.8.3",),
    "embeddings need no outbound call": ("M7.3.3",),
}


@check(
    leaves=("M1.8.5",),
    sentence=(
        "Every clause of identity's install proof was shown in this run: a person signing in "
        "through the identity provider, a single-use binding code, an unbound sender told how to "
        "bind, the same reach on web and chat, session limits, administration refused to a "
        "password alone, an account bound to nobody told once, and a password reset by email."
    ),
)
async def identity_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, IDENTITY_CLAUSES, own="identity_is_shown_clause_by_clause_in_this_run"
    )


@check(
    leaves=("M11.8.3",),
    sentence=(
        "Every clause of live reading's install proof was shown in this run: a ticket question "
        "answered live, a canary found in no table, deny-listed fields never projected, a "
        "question spanning many records answered from projected headers, and embeddings made "
        "with no outbound call."
    ),
)
async def live_reading_is_shown_clause_by_clause_in_this_run(h: Harness) -> None:
    await clauses_demonstrated(
        h, LIVE_READING_CLAUSES, own="live_reading_is_shown_clause_by_clause_in_this_run"
    )


@check(
    leaves=("M1.6.18",),
    sentence=(
        "A reserved person's account is made with no email sent, Forgot password sets their "
        "password and then their second factor, and a reserved leaver's account is closed on the "
        "next sync, at the sign-in service itself. Not asked here: it needs a mailbox read by a "
        "person."
    ),
)
async def a_reserved_person_resets_their_password_and_sets_a_second_factor(h: Harness) -> None:
    del h
    raise CheckNotRunError(A_REAL_ACCOUNT_AND_A_REAL_MAILBOX_ARE_NEEDED)


@check(
    leaves=("M1.1.9",),
    sentence=(
        "A reserved person on the Lark staff list signs in with Lark and lands in the console as "
        "themselves, and a reserved leaver cannot. Not asked here: it needs a real Lark account "
        "and the owner's own sign-in service."
    ),
)
async def a_reserved_person_signs_in_with_lark_and_a_leaver_cannot(h: Harness) -> None:
    del h
    raise CheckNotRunError(A_REAL_LARK_ACCOUNT_AND_A_REAL_SIGN_IN_ARE_NEEDED)
