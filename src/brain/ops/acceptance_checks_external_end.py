"""Install acceptance check for an external person's end date (M1.8.1).

A contractor cannot be saved without an end date: the form's body refuses one, and the database
refuses a row that has none. One with an end date is saved, is given a grant, and holds it until
the date. At the first instant after the date they hold nothing, a session cannot be opened for
them, and the principal a chat binding would resolve to is no longer active, so nothing they held
reaches anything.

**The date is judged at an instant the check chooses, not at the clock.** The reach is read through
the resolver every request reads it through (`gate.entitlements_with_lapse`) at the end date and at
one second after it, and a session is opened at each of those instants. A check that waited for the
date to pass would take as long as the engagement; one that changed the stored date would be
proving that a past date refuses, which is a different claim.

**What this proves and what it does not.** Grants and sessions are asked through the functions a
request runs. A channel binding is asked as far as the principal it resolves to: the chat route's
own refusal of an inactive person (`brain.chat_answer`) is not driven here, because it needs a
channel adapter and a message, and it reads the same `Principal.is_active`. The check says so
rather than claiming the whole sentence of the leaf.

**The rows are written by the check and rolled back with it.** Nothing reaches a staff source: the
person is added with the statement the console's add-person route runs, so the check passes on an
install that reads a staff list, where the route itself refuses a person added by hand.

Task ids: M1.8.1
"""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before the roll-ups that read it (2800).
CHECK_ORDER: Final = 1820

A, _ = RESERVED_DEPARTMENTS

#: What the contractor is granted, and for how long their engagement runs.
GRANTED: Final = "read:document"
ENGAGEMENT: Final = timedelta(minutes=30)


def _claims(subject: str) -> Any:
    """Verified claims for an interactive session, as `open_session` takes them."""
    from datetime import datetime
    from types import MappingProxyType

    from brain.identity.oidc import VerifiedClaims

    now = datetime.now(UTC)
    return VerifiedClaims(
        issuer="acceptance",
        subject=subject,
        audience=(),
        issued_at=now,
        expires_at=now,
        session_id="acceptance",
        key_id="acceptance",
        algorithm="RS256",
        verified_at=now,
        claims=MappingProxyType({}),
    )


@check(
    leaves=("M1.8.1",),
    sentence=(
        "A contractor cannot be saved without an end date, by the form or by the database; one "
        "saved with a date holds their grant until it, and at the first instant after it holds "
        "nothing, cannot open a session, and is no longer an active person for a chat binding to "
        "resolve to."
    ),
)
async def an_external_person_stops_on_their_end_date(h: Harness) -> None:
    from pydantic import ValidationError

    from brain.core.entitlement import Capability
    from brain.core.principal import Employment
    from brain.core.scope import Scope
    from brain.directory_routes import PersonAdding, adding_person
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.oidc import TokenRefusedError
    from brain.identity.principal_store import StoredPrincipals
    from brain.identity.sessions import open_session

    await h.found_departments()
    ends = h.now + ENGAGEMENT
    person = h.principal(A, "contractor")

    try:
        PersonAdding(display_name="Acceptance contractor", employment=Employment.CONTRACTOR)
    except ValidationError:
        pass
    else:
        raise CheckFailedError("the form took a contractor with no end date")
    body = PersonAdding(
        display_name="Acceptance contractor",
        department=A,
        employment=Employment.CONTRACTOR,
        not_after=ends,
    )

    async def kept_by_the_database(*, bound: bool) -> bool:
        """Whether the install's own table keeps a contractor row, in a savepoint then undone."""
        async with h.sessions() as session:
            nested = await session.begin_nested()
            try:
                await session.execute(
                    text(
                        "INSERT INTO auth.principal "
                        "(id, kind, employment, display_name, not_after) "
                        "VALUES (:id, 'human', 'contractor', 'Acceptance contractor', :ends)"
                    ),
                    {"id": f"{person}.probe", "ends": ends if bound else None},
                )
            except DBAPIError:
                return False
            finally:
                await nested.rollback()
        return True

    try:
        unbounded_kept = await kept_by_the_database(bound=False)
        bounded_kept = await kept_by_the_database(bound=True)
        await h.execute(*h.attributed(), adding_person(person, body))
        await h.grant(person, GRANTED, Scope.unrestricted())
    except DBAPIError:
        raise CheckFailedError("the database refused the step that saves the contractor") from None
    if unbounded_kept:
        raise CheckFailedError("the database kept a contractor with no end date")
    if not bounded_kept:
        raise CheckFailedError("the database refused a contractor with an end date")

    try:
        store = StoredEntitlements(h.sessions)
        during = await store.load(person, ends - timedelta(minutes=1))
        after = await store.load(person, ends + timedelta(seconds=1))
        stored = await StoredPrincipals(h.sessions).live_principal(person)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that reads the reach") from None
    before = ends - timedelta(minutes=1)
    gone = ends + timedelta(seconds=1)
    if not during.holds(Capability(value=GRANTED), before):
        raise CheckFailedError("a contractor held nothing before their end date")
    if after.holds(Capability(value=GRANTED), gone):
        raise CheckFailedError("a contractor still held a grant after their end date")
    if stored is None or stored.not_after != ends:
        raise CheckFailedError("a contractor's end date was not the one they were saved with")

    if not stored.is_active(ends - timedelta(minutes=1)) or stored.is_active(
        ends + timedelta(seconds=1)
    ):
        raise CheckFailedError("a contractor was active after their end date or not before it")

    session = open_session(
        claims=_claims(person), principal=stored, now=ends - timedelta(minutes=5)
    )
    if session.absolute_expiry != ends:
        raise CheckFailedError("a contractor's session outlived their end date")
    try:
        open_session(claims=_claims(person), principal=stored, now=ends + timedelta(seconds=1))
    except TokenRefusedError:
        pass
    else:
        raise CheckFailedError("a session was opened for a contractor after their end date")
