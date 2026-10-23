"""The install acceptance checks for two screens the first-run walk uses: the staff list and the
finishing sign-in, each through the function its route calls.

`brain.ops.acceptance_checks_first_run` proves the wizard's own validators and says so: once an
administrator exists the wizard cannot be posted to, and what a person typed on a real server is for
the fresh-install walk. These two screens were built, wired and tested over HTTP with stand-ins and
named by no check, so the next acceptance run could not say they still work. They are proved here
the same way and with the same limit.

**The staff list screen is read, never driven to a vendor.** A directory is signed in to by a person
at the vendor's page, so the check cannot sign in to one and does not try. It asks what the screen
asks of this process: what each directory needs registering, the address a person would be sent to,
one list read through the route's own `trial_for` from a spreadsheet and from a directory whose
answers are written in the check, and the refusals a person meets. The directory is a function in
the check that answers the shape Microsoft documents for its users, so the product's own sign-in
exchange and page walk run unchanged in front of it and nothing opens a socket. See
`A_STAND_IN_DIRECTORY_IS_NEVER_A_CALL`.

**The gate is asked as the route asks it.** `assert_setup_open` is handed an application state
holding the check's own setup code and a store with no administrator, and must refuse a wrong code
in the words it refuses an install that has no code at all. That is the property the route's module
argues, that nothing leaves this server before the code is accepted, and it is shown here by the
refusal and not by reading the order of the statements.

**The finishing sign-in is run with a token the check signs.** The check holds a realm key of its
own, the install's gate verifies a token signed with it exactly as it verifies every request, and
`finish_setup_sign_in` binds that token's subject to a person holding the first administrator's
grants. That person then signs in with the same token and is the person the grants name. The one
stand-in is the count of people already signed in: this install may have some, and the screen is
open only while there are none, which a rolled-back transaction cannot make true on an install that
is finished. So the writer the route is handed reports none and writes through the install's own
store, and the closed half is asked of the real store afterwards, when the binding the check has
just written is there to close it. See `THE_COUNT_OF_SIGN_INS_IS_THE_ONLY_STAND_IN`.

Rejected: posting to the running application. The check runs in the worker, which serves nothing,
and an HTTP client from a worker to its own application is a second thing to be down.

Task ids: M42.5.7, M42.5.14
"""

from __future__ import annotations

import contextlib
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.connectors.staff_directories import Answer, Outbound
    from brain.identity.sign_in_binding import Binding

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1835

A, _B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why no part of the staff list check reaches a vendor.
A_STAND_IN_DIRECTORY_IS_NEVER_A_CALL: Final = (
    "The staff list check reads a list from answers written in the check, in the shape the vendor "
    "documents, through the function the route calls and the product's own sign-in exchange and "
    "page walk. It opens no connection, signs in to nothing and holds no client secret that any "
    "directory has seen, so it says the screen works and nothing about a vendor."
)

#: Why the finishing check writes through the real store but counts for itself.
THE_COUNT_OF_SIGN_INS_IS_THE_ONLY_STAND_IN: Final = (
    "The finishing screen is open only while no sign-in is bound anywhere on the install, and an "
    "install that is finished has some. The check cannot unbind them inside a transaction it "
    "rolls back, so the writer it hands the route reports none yet and passes every bind to the "
    "install's own store. The closed half is asked of the store itself afterwards."
)

#: Why the trial reads are made with nothing saved.
THE_TRIAL_JUDGES_THE_CHOICE_IT_IS_HANDED: Final = (
    "The staff list trial is handed the source a person is choosing and judges that, but the "
    "installation values read for the choice put what an install has saved before what is handed "
    "in. On a fresh install nothing is saved, which is the only install the trial is for; on a "
    "finished one the saved source outranks the choice, so the check sets what is saved aside "
    "for the length of its reads and puts it back, and a read of the owner's list is not made."
)

# ------------------------------------------------------------------------ the figures
#: The tenant, application and return address the sign-in is built from, made up for the check.
TENANT: Final = "8f1a0e5c-0000-4000-8000-00000000000a"
CLIENT_ID: Final = "acceptance-client-id"
RETURN_ADDRESS: Final = "https://brain.example.invalid/first-run/staff-list"
#: The state and challenge the browser makes, at the lengths the product accepts.
STATE: Final = "S" * 32
CHALLENGE: Final = "C" * 43
VERIFIER: Final = "v" * 64

#: A staff list as a person saves one from a spreadsheet, two people working here.
SHEET: Final = (
    "Work Email,Full Name,Department,Groups,Left?\n"
    "ada@acceptance.example.invalid,Ada One,engineering,,\n"
    "grace@acceptance.example.invalid,Grace Two,engineering,,\n"
)


# ------------------------------------------------------------------------ the helpers
class _Directory:
    """Microsoft's sign-in and users page, in memory, for one right secret and code.

    Answers a token for the right exchange, one page of two people for the right token, and the
    vendor's own refusal for anything else. Records what it was sent so the check can say where the
    secret went.
    """

    def __init__(self, secret: str, token: str) -> None:
        self.secret = secret
        self.token = token
        self.sent: list[Outbound] = []

    async def __call__(self, outbound: Outbound) -> Answer:
        from brain.connectors.staff_directories import Answer

        self.sent.append(outbound)
        if outbound.url.startswith("https://login.microsoftonline.com/"):
            form = outbound.form or {}
            if form.get("client_secret") != self.secret or form.get("code") != "RETURNED-CODE":
                return Answer(400, {"error_description": "AADSTS70008: the code has expired"})
            return Answer(200, {"access_token": self.token, "token_type": "Bearer"})
        if outbound.headers.get("Authorization") != f"Bearer {self.token}":
            return Answer(401, {"error": {"message": "no token"}})
        return Answer(
            200, {"value": [_person(1, "Ada One", "ada"), _person(2, "Grace Two", "grace")]}
        )


def _person(number: int, name: str, local: str) -> dict[str, Any]:
    """One user as Microsoft's directory lists one."""
    address = f"{local}@acceptance.example.invalid"
    return {
        "id": f"8f1a0e5c-0000-4000-8000-00000000000{number}",
        "displayName": name,
        "userPrincipalName": address,
        "mail": address,
        "accountEnabled": True,
        "department": "Engineering",
    }


async def _nothing_is_called(outbound: Outbound) -> Answer:
    """A directory client for a trial that must not reach one."""
    del outbound
    raise CheckFailedError("a trial that needs no directory called one")


def _told_in_words(why: str) -> bool:
    """Whether a refusal is a sentence a person can read, and not a type or a code."""
    return len(why.split()) >= 4 and why.rstrip().endswith((".", "?"))


@contextlib.contextmanager
def _saved_values_set_aside() -> Iterator[None]:
    """This process's saved installation values emptied for a block, and put back after it.

    The reads inside make no network call and wait on nothing, so no other task runs while the
    values are away. See `THE_TRIAL_JUDGES_THE_CHOICE_IT_IS_HANDED`.
    """
    from brain.install import hold_saved

    before = hold_saved({})
    try:
        yield
    finally:
        hold_saved(before)


# ------------------------------------------------ 1. the staff list screen
@check(
    leaves=("M42.5.7",),
    sentence=(
        "The staff list screen offers Google Workspace, Microsoft Entra and Lark with the path "
        "the return address ends in, builds the vendor's own sign-in address, reads a list from "
        "a spreadsheet and from a directory without writing it, refuses a bad secret in words, "
        "and sends nothing to a directory before the setup code is accepted."
    ),
)
async def the_staff_list_screen_reads_a_list_and_writes_nothing(
    h: Harness,
) -> None:
    from brain.connectors.staff_directories import DirectorySignInError, authorisation_address
    from brain.core.errors import Absent, to_public
    from brain.ops.leases import SealedSecret
    from brain.settings import Settings
    from brain.setup_staff_routes import (
        StaffTrialAsked,
        assert_setup_open,
        staff_source_registration,
        trial_for,
    )

    # What is offered, and where the return address ends.
    offered = await staff_source_registration()
    if {one.source for one in offered.sources} != {"google_workspace", "microsoft_entra", "lark"}:
        raise CheckFailedError("the staff list screen did not offer exactly the three directories")
    if offered.return_path != "/first-run/staff-list":
        raise CheckFailedError("the return address did not end in the staff list screen's path")
    if any(not one.where.strip() or not one.grant.strip() for one in offered.sources):
        raise CheckFailedError("a directory was offered with nothing said about registering it")

    # The page a person is sent to is the vendor's own, with a proof key and the return address.
    address = authorisation_address(
        "microsoft_entra",
        location=TENANT,
        client_id=CLIENT_ID,
        redirect_uri=RETURN_ADDRESS,
        state=STATE,
        challenge=CHALLENGE,
    )
    opening = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize?"
    if not address.startswith(opening) or "code_challenge_method=S256" not in address:
        raise CheckFailedError("the sign-in address was not the vendor's own page with a proof key")

    try:
        authorisation_address(
            "microsoft_entra",
            location=TENANT,
            client_id=CLIENT_ID,
            redirect_uri="https://brain.example.invalid/somewhere-else",
            state=STATE,
            challenge=CHALLENGE,
        )
    except DirectorySignInError:
        pass
    else:
        raise CheckFailedError("a return address that did not end in the screen's path was built")

    # A spreadsheet is read from the text the person chose and nobody signs in to one.
    # The trial judges the choice it is handed, so what this install has saved is set aside for
    # the length of the reads. See `THE_TRIAL_JUDGES_THE_CHOICE_IT_IS_HANDED`.
    with _saved_values_set_aside():
        sheet = await trial_for(
            StaffTrialAsked(setup_code="unused", staff_source="spreadsheet", sheet=SHEET),
            _nothing_is_called,
        )
    if sheet.plan is None or sheet.refusals:
        raise CheckFailedError("a staff list pasted from a spreadsheet was not read")

    if not sheet.plan.safe_to_apply:
        raise CheckFailedError("a staff list pasted from a spreadsheet was not safe to apply")
    added = {one.work_address for one in sheet.plan.would_add}
    if added != {"ada@acceptance.example.invalid", "grace@acceptance.example.invalid"}:
        raise CheckFailedError("the spreadsheet trial did not name the two people it holds")
    if sheet.plan.would_remove:
        raise CheckFailedError("a first run was shown removing somebody from an empty install")
    if sheet.plan.would_deactivate:
        raise CheckFailedError("a first run was shown deactivating somebody on an empty install")

    # A directory is signed in to once with the secret, walked, and the plan is the same shape.
    secret, token = f"acceptance-{secrets.token_hex(12)}", f"token-{secrets.token_hex(12)}"
    fetch = _Directory(secret, token)
    asked = StaffTrialAsked(
        setup_code="unused",
        staff_source="microsoft_entra",
        location=TENANT,
        client_id=CLIENT_ID,
        client_secret=secret,
        code="RETURNED-CODE",
        verifier=VERIFIER,
        redirect_uri=RETURN_ADDRESS,
    )
    with _saved_values_set_aside():
        read = await trial_for(asked, fetch)
    if read.plan is None or read.refusals:
        raise CheckFailedError("a directory that answered was not read")

    if len(read.plan.would_add) != 2:
        raise CheckFailedError("a directory that answered was not read to the two people it holds")
    exchanges = [one for one in fetch.sent if one.form is not None]
    if len(exchanges) != 1:
        raise CheckFailedError("the client secret was not sent exactly once")
    if any(secret in str(one.url) for one in fetch.sent):
        raise CheckFailedError("the client secret was sent in a request address")

    # The refusals are sentences, and the vendor's own words stand for the vendor.
    # A directory that would accept the secret as typed is not reached with one that has a space.
    spaced_secret = f"{secret} with a space"
    open_directory = _Directory(spaced_secret, token)
    with _saved_values_set_aside():
        spaced = await trial_for(
            asked.model_copy(update={"client_secret": spaced_secret}), open_directory
        )
    if spaced.plan is not None or not spaced.refusals:
        raise CheckFailedError("a client secret with a space still gave a plan")

    if open_directory.sent:
        raise CheckFailedError("a client secret with a space was sent to the directory")
    if not all(_told_in_words(one) for one in spaced.refusals):
        raise CheckFailedError("a client secret with a space was refused but not in words")
    with _saved_values_set_aside():
        wrong = await trial_for(asked.model_copy(update={"code": "ANOTHER-CODE"}), fetch)
    if wrong.plan is not None or not wrong.refusals:
        raise CheckFailedError("a directory's refusal still gave a plan")

    if any(secret in why for why in wrong.refusals):
        raise CheckFailedError("a refusal repeated the client secret it was sent")

    # Nothing leaves the server before the code is accepted, and a wrong code is the one refusal.
    code = secrets.token_urlsafe(48)

    class _Nobody:
        async def administrators(self, now: datetime) -> int:
            del now
            return 0

        async def appoint(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("a staff list trial must not appoint anybody")

    def request_with(settings: Settings) -> Any:
        state = SimpleNamespace(first_administrators=_Nobody(), settings=settings)
        return SimpleNamespace(app=SimpleNamespace(state=state))

    with_code = Settings(
        env="development",
        setup_secret=SealedSecret(code),
        setup_issued_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    now = datetime.now(UTC)
    await assert_setup_open(request_with(with_code), code, now)
    told: list[str] = []
    for settings, presented in (
        (with_code, secrets.token_urlsafe(48)),
        (Settings(env="development"), code),
    ):
        try:
            await assert_setup_open(request_with(settings), presented, now)
        except Absent as nothing:
            told.append(to_public(nothing))
        else:
            raise CheckFailedError("a staff list trial was allowed without the right setup code")
    if told[0] != told[1]:
        raise CheckFailedError("a wrong setup code was answered unlike an install with none")


# ------------------------------------------------ 2. the finishing sign-in
@dataclass
class _NobodyIsSignedInYet:
    """The install's bindings store, reporting no sign-in so the finishing screen is open.

    Every bind goes to the real store. See `THE_COUNT_OF_SIGN_INS_IS_THE_ONLY_STAND_IN`.
    """

    real: Any

    @property
    def issuer(self) -> str:
        return str(self.real.issuer)

    async def sign_ins(self) -> int:
        return 0

    async def bind(self, subject: str, **kwargs: Any) -> Binding:
        return cast("Binding", await self.real.bind(subject, **kwargs))


@check(
    leaves=("M42.5.14",),
    sentence=(
        "The finishing screen binds a token signed by the realm's key to the person holding the "
        "first administrator's grants when the setup code is right, and that token then signs "
        "them in; a wrong code, a person who is no administrator and an install with a sign-in "
        "already bound are refused in the same words."
    ),
)
async def the_first_administrator_is_bound_and_signed_in_at_the_end(
    h: Harness,
) -> None:
    from brain.core.errors import Absent, to_public
    from brain.ops.acceptance_people_signed_in import administrator, console, everywhere
    from brain.ops.leases import SealedSecret
    from brain.settings import Settings
    from brain.sign_in_routes import FinishAsked, SignInOutcome, finish_setup_sign_in

    await h.found_departments()
    first, stranger = h.principal(A, "finishing"), h.principal(A, "unfinished")
    second = h.principal(A, "finishing_later")
    await h.person(first, department=A, grants=everywhere(*administrator()))
    await h.person(second, department=A, grants=everywhere(*administrator()))
    await h.person(stranger, department=A)
    walk = await console(h)
    code = secrets.token_urlsafe(48)
    walk.app.state.settings = Settings(
        env="development",
        setup_secret=SealedSecret(code),
        setup_issued_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    real = walk.app.state.sign_in_bindings
    walk.app.state.sign_in_bindings = _NobodyIsSignedInYet(real)
    token = walk.token(f"acceptance-{h.run}-finishing", session=walk.session())

    async def finishing(who: str, presented: str, bearer: str) -> Any:
        with walk.as_route():
            return await finish_setup_sign_in(
                walk.request(bearer), FinishAsked(setup_code=presented, principal_id=who)
            )

    told: list[str] = []

    async def refused_with(who: str, presented: str, bearer: str) -> None:
        try:
            await finishing(who, presented, bearer)
        except Absent as nothing:
            told.append(to_public(nothing))
        else:
            raise CheckFailedError("a finishing request that must be refused was answered")

    other = walk.token(f"acceptance-{h.run}-other", session=walk.session())
    await refused_with(first, secrets.token_urlsafe(48), other)
    await refused_with(stranger, code, other)

    done = await finishing(first, code, token)
    if done.principal_id != first or done.outcome is not SignInOutcome.BOUND:
        raise CheckFailedError("the right code and a verified token did not bind the first person")

    signed_in = await walk.asked(first, bearer=token)
    if signed_in.caller.principal.id != first:
        raise CheckFailedError("the bound token did not sign in the person it was bound to")

    # The install now has a sign-in bound, so the real store closes the screen to everybody.
    walk.app.state.sign_in_bindings = real
    late = walk.token(f"acceptance-{h.run}-late", session=walk.session())
    await refused_with(second, code, late)
    if len(set(told)) != 1:
        raise CheckFailedError("the finishing screen refused in more than one way")
