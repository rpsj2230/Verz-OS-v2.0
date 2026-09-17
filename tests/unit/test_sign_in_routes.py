"""A sign-in is bound by an administrator over everything or by the finishing screen once, and the
ledger names who did it.

The first half drives the real application with the router mounted beside it, a gate built from
`test_api_routes`' key source and verifier, and an in-memory writer that decides with the real
`sign_in_binding.decide`. The second builds the database through `0047` and proves the trigger:
the entry, its actor, its digest agreeing with Python's, the refusal of an unattributed binding,
and the finishing screen against the real store. It skips when there is no server.

Task ids: M42.5.14, M1.2.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import NOT_DONE_AS_THINGS_STAND
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, SignInChange
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.firstrun import GRANTED_BY, digest_of, open_enrolment
from brain.gate.admission import SECOND_FACTOR_NEEDED_MESSAGE
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.bearer import TokenAuthority
from brain.identity.oidc import KeySet, SigningKey, VerifiedClaims
from brain.identity.principal_directory import StoredDirectory
from brain.identity.sign_in_binding import (
    Binding,
    SignInBindings,
    decide,
    sign_in_bindings,
)
from brain.ops.leases import SealedSecret
from brain.session import make_session_factory
from brain.sign_in_routes import (
    FINISH_PATH,
    SIGN_IN_AUTHORITY,
    SIGN_INS_PATH,
    finish_sign_in,
    router,
)
from tests.fixtures.http_client import Response
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_api_routes import (
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    principal,
    signing_key,
    token_for,
    verifier,
)
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_grant, a_principal
from tests.unit.test_setup_wizard import SECRET, WRONG

#: The subject the installer's own Keycloak account carries. Opaque, as a `sub` is.
INSTALLER = "9a8b7c6d-0000-4000-8000-0000000000aa"

#: A literal rather than read off `bearer.SECOND_FACTOR_METHODS`, for the reason
#: `test_classification_routes` gives about its own copy.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}

EVERYWHERE = Scope.unrestricted()
FINANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))

#: Who holds the capability, and where. `u_narrow` holds it over one department only.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=SIGN_IN_AUTHORITY, scope=EVERYWHERE),),
    "u_narrow": (Grant(capability=SIGN_IN_AUTHORITY, scope=FINANCE),),
    #: A second administrator with no sign-in, so a second use is refused by the screen and not
    #: by the binder finding the first administrator already signing in.
    "u_later": (Grant(capability=SIGN_IN_AUTHORITY, scope=EVERYWHERE),),
    #: Still holds the grant and is not live, so only the binder can refuse them.
    "u_gone": (Grant(capability=SIGN_IN_AUTHORITY, scope=EVERYWHERE),),
}

#: The principals the writer finds live. `u_ghost` and `u_gone` are deliberately absent.
LIVE: frozenset[str] = frozenset(
    {"u_admin", "u_later", "u_narrow", "u_none", "u_joiner", "u_other"}
)


class Store:
    """A `brain.gate.resolve.EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


@dataclass
class Writer:
    """A `SignInWriter` in memory, deciding with the binder's own `decide`."""

    issuer: str = ISSUER
    held: dict[str, str] = field(default_factory=dict)
    calls: list[dict[str, str]] = field(default_factory=list)

    async def sign_ins(self) -> int:
        return len(self.held)

    async def bind(
        self,
        subject: str,
        *,
        principal_id: str,
        bound_by: str,
        now: datetime,
        ent_hash: str = "",
        trace_id: str = "",
    ) -> Binding:
        self.calls.append(
            {"subject": subject, "principal_id": principal_id, "bound_by": bound_by}
            | {"ent_hash": ent_hash, "trace_id": trace_id}
        )
        outcome = decide(
            subject,
            principal_id=principal_id,
            bound_by=bound_by,
            principal=principal(principal_id) if principal_id in LIVE else None,
            subject_holder=self.held.get(subject),
            principal_signs_in=principal_id in self.held.values(),
            now=now,
        )
        if outcome is Binding.BOUND:
            self.held[subject] = principal_id
        return outcome


def wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience="brain-api", keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


def an_app(*, with_code: bool = True) -> FastAPI:
    """The real application with this router mounted, as the lifespan hunk would mount it.

    The setup code was minted five minutes ago by the real clock, because the finishing screen
    reads the wall clock and the window is an hour.
    """
    minted = datetime.now(UTC) - timedelta(minutes=5)
    settings = (
        Settings(env="development", setup_secret=SealedSecret(SECRET), setup_issued_at=minted)
        if with_code
        else Settings(env="development")
    )
    app = create_app(settings)
    app.include_router(router)
    return app


@contextmanager
def serving(writer: Writer, *, with_code: bool = True) -> Iterator[TestClient]:
    app = an_app(with_code=with_code)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.sign_in_bindings = writer
        yield c


@pytest.fixture
def writer() -> Writer:
    return Writer()


@pytest.fixture
def client(writer: Writer) -> Iterator[TestClient]:
    with serving(writer) as c:
        yield c


def refusal(answer: Response) -> dict[str, Any]:
    """One refusal body with the per-request trace id taken out, its presence asserted."""
    body = dict(answer.json())
    assert "trace_id" in body
    body["trace_id"] = "<per request>"
    return body


def bind(
    c: TestClient,
    pid: str,
    *,
    subject: str = "s-joiner",
    principal_id: str = "u_joiner",
    claims: Mapping[str, object] = SECOND_FACTOR,
) -> Response:
    response: Response = c.post(
        SIGN_INS_PATH,
        headers={"authorization": f"Bearer {token_for(pid, claims=claims)}"},
        json={"subject": subject, "principal_id": principal_id},
    )
    return response


def finishing(
    c: TestClient,
    *,
    code: str = SECRET,
    principal_id: str = "u_admin",
    subject: str = INSTALLER,
    claims: Mapping[str, object] | None = None,
    signed_by: str | None = None,
) -> Response:
    token = token_for("u_none", claims={"sub": subject, **(claims or {})}, signed_by=signed_by)
    response: Response = c.post(
        FINISH_PATH,
        headers={"authorization": f"Bearer {token}"},
        json={"setup_code": code, "principal_id": principal_id},
    )
    return response


# ----------------------------------------------------------------- the administrator's route


def test_an_administrator_binds_a_subject_and_is_named_as_the_binder(
    client: TestClient, writer: Writer
) -> None:
    """The positive case for every refusal below. Delete it and a route refusing everybody passes
    them all, and no administrator can ever give anybody a sign-in."""
    answer = bind(client, "u_admin")

    assert (answer.status_code, answer.json()) == (
        200,
        {"principal_id": "u_joiner", "outcome": "bound"},
    )
    [call] = writer.calls
    assert (call["subject"], call["principal_id"], call["bound_by"]) == (
        "s-joiner",
        "u_joiner",
        "u_admin",
    )
    assert len(call["ent_hash"]) == 32
    assert call["trace_id"]


def test_a_non_administrator_is_refused_exactly_as_a_principal_who_is_not_here(
    client: TestClient, writer: Writer
) -> None:
    """See `A_BINDING_YOU_MAY_NOT_MAKE_AND_A_PRINCIPAL_NOT_HERE_ARE_ONE_ANSWER`. Delete this and
    the two can diverge, and a caller trying ids learns which principals exist; or the capability
    check can go, and anybody signed in binds their own account to anybody."""
    stranger = bind(client, "u_none")
    ghost = bind(client, "u_admin", principal_id="u_ghost")

    assert stranger.status_code == ghost.status_code == 404
    assert refusal(stranger) == refusal(ghost)
    assert [call["bound_by"] for call in writer.calls] == ["u_admin"]


def test_an_administrator_over_one_department_is_refused_as_a_non_administrator(
    client: TestClient, writer: Writer
) -> None:
    """See `A_SIGN_IN_IS_BOUND_BY_AN_ADMINISTRATOR_OVER_EVERYTHING`. Delete this and a department
    administrator binds an account to a principal outside their department in one request."""
    narrow = bind(client, "u_narrow")
    stranger = bind(client, "u_none")

    assert narrow.status_code == 404
    assert refusal(narrow) == refusal(stranger)
    assert writer.calls == []


def test_a_password_only_session_cannot_bind_a_sign_in(client: TestClient, writer: Writer) -> None:
    """The capability is an `admin:` verb, which admission withholds without a second factor, and
    the refusal says what the sign-in lacks rather than what it asked for. Delete this and the
    capability can be renamed out of the admin verbs, and a stolen password alone binds accounts."""
    weak = bind(client, "u_admin", claims={})
    stranger = bind(client, "u_none")

    assert weak.status_code == stranger.status_code == 404
    assert refusal(weak)["message"] == SECOND_FACTOR_NEEDED_MESSAGE
    assert refusal(stranger)["message"] == "I could not find that."
    assert writer.calls == []


def test_a_subject_held_elsewhere_is_told_to_the_administrator_without_saying_by_whom(
    client: TestClient, writer: Writer
) -> None:
    """Delete this and a held subject can come back as the one 404, so the administrator cannot
    tell a typo from an account already in use, or as a body naming whoever holds it."""
    writer.held["s-held"] = "u_other"

    answer = bind(client, "u_admin", subject="s-held")

    assert (answer.status_code, refusal(answer)) == (
        409,
        {
            "principal_id": "u_joiner",
            "outcome": "subject_bound_elsewhere",
            "message": NOT_DONE_AS_THINGS_STAND,
            "trace_id": "<per request>",
        },
    )
    assert "u_other" not in answer.text
    assert writer.held == {"s-held": "u_other"}


def test_the_same_binding_asked_again_is_already_bound_and_not_a_refusal(
    client: TestClient, writer: Writer
) -> None:
    """Delete this and the success check can narrow to `bound`, and a retried request that already
    landed is reported to the administrator as refused."""
    writer.held["s-joiner"] = "u_joiner"

    answer = bind(client, "u_admin")

    assert (answer.status_code, answer.json()) == (
        200,
        {"principal_id": "u_joiner", "outcome": "already_bound"},
    )


def test_a_process_with_no_bindings_store_refuses_every_caller_alike(writer: Writer) -> None:
    """Delete this and a process built without the store fails differently for an administrator
    and a stranger, which says who the administrators are."""
    with serving(writer) as c:
        c.app.state.sign_in_bindings = None  # type: ignore[attr-defined]
        admin = bind(c, "u_admin")
        stranger = bind(c, "u_none")

    assert admin.status_code == stranger.status_code == 500
    assert refusal(admin) == refusal(stranger)


# ----------------------------------------------------------------------- the finishing screen


def test_the_finishing_screen_binds_the_installers_sign_in_to_the_first_administrator(
    client: TestClient, writer: Writer
) -> None:
    """The positive case for every refusal below. Delete it and a screen refusing everything
    passes them all, and no install can ever have anybody sign in."""
    answer = finishing(client)

    assert (answer.status_code, answer.json()) == (
        200,
        {"principal_id": "u_admin", "outcome": "bound"},
    )
    assert writer.held == {INSTALLER: "u_admin"}
    assert writer.calls[0]["bound_by"] == GRANTED_BY


def test_the_finishing_screen_refuses_a_second_use_and_says_nothing_about_who(
    client: TestClient, writer: Writer
) -> None:
    """See `THE_FINISHING_SCREEN_SIGNS_IN_ONE_ADMINISTRATOR_ONCE`. Delete this and anybody still
    holding the setup code inside its hour binds a second account as an administrator, or learns
    from the refusal who the first one was."""
    finishing(client)
    second = finishing(client, subject="s-second", principal_id="u_later")
    wrong = finishing(client, code=WRONG)

    assert second.status_code == 404
    assert refusal(second) == refusal(wrong)
    assert INSTALLER not in second.text
    assert "u_admin" not in second.text
    assert writer.held == {INSTALLER: "u_admin"}


def test_a_wrong_setup_code_is_refused_and_binds_nothing(
    client: TestClient, writer: Writer
) -> None:
    """Delete this and the finishing screen is the one screen reachable without the setup code,
    and it is the screen that hands out a sign-in to the widest role."""
    answer = finishing(client, code=WRONG)

    assert answer.status_code == 404
    assert writer.calls == []


@pytest.mark.parametrize(
    ("claims", "signed_by"),
    [({}, "k-forged"), ({"iss": "https://id.elsewhere.example/realms/brain"}, None)],
    ids=["unverified signature", "foreign issuer"],
)
def test_an_unverified_or_foreign_token_is_refused_before_anything_is_asked(
    client: TestClient, writer: Writer, claims: Mapping[str, object], signed_by: str | None
) -> None:
    """The token is held to the real authority. Delete this and `verified_claims` can stop
    validating, and a token anybody typed becomes the first administrator's sign-in."""
    answer = finishing(client, claims=claims, signed_by=signed_by)

    assert answer.status_code == 401
    assert writer.calls == []


def test_a_token_with_no_session_is_not_the_first_administrators_sign_in(
    client: TestClient, writer: Writer
) -> None:
    """See `A_CALLER_WITH_NO_SESSION_IS_NOT_A_SIGN_IN`. Delete this and a client credential in a
    configuration file becomes the widest role's way in."""
    answer = finishing(client, claims={"sid": ""})
    wrong = finishing(client, code=WRONG)

    assert answer.status_code == 404
    assert refusal(answer) == refusal(wrong)
    assert writer.calls == []


def test_a_principal_who_is_not_an_administrator_cannot_take_the_first_sign_in(
    client: TestClient, writer: Writer
) -> None:
    """Delete this and the first sign-in can be bound to anybody, which closes the screen with no
    administrator able to sign in and bind the next."""
    plain = finishing(client, principal_id="u_none")
    narrow = finishing(client, principal_id="u_narrow")
    wrong = finishing(client, code=WRONG)

    assert plain.status_code == narrow.status_code == 404
    assert refusal(plain) == refusal(wrong) == refusal(narrow)
    assert writer.calls == []


def test_a_token_from_an_issuer_bindings_are_not_written_at_is_refused(writer: Writer) -> None:
    """Delete this and a wiring fault binds the first administrator at an issuer no token will ever
    be looked up at, which closes the screen with nobody able to sign in."""
    writer.issuer = "https://id.other.example/realms/brain"
    with serving(writer) as c:
        answer = finishing(c)

    assert answer.status_code == 404
    assert writer.calls == []


def test_an_install_with_no_setup_code_has_no_finishing_screen(writer: Writer) -> None:
    """`Settings.setup_enrolment` is None on a development machine and on an install long past
    first run. Delete this and a missing enrolment could be read as an open one."""
    with serving(writer, with_code=False) as c:
        answer = finishing(c)

    assert answer.status_code == 404
    assert writer.calls == []


def test_a_process_with_no_token_authority_refuses_the_finishing_screen(writer: Writer) -> None:
    """`bearer.AN_UNCONFIGURED_AUTHORITY_ACCEPTS_NOTHING`. Delete this and a process with no gate
    reads the token without checking it."""
    with serving(writer) as c:
        c.app.state.gate = None  # type: ignore[attr-defined]
        answer = finishing(c)

    assert answer.status_code == 401
    assert writer.calls == []


class RotatedKeys:
    """A key source that knows the token's key only once asked for it by id, which is what
    `oidc.JwksCache` does after a rotation: the cached set is old until an unknown kid refetches."""

    def __init__(self) -> None:
        self.warmed = False

    def keys_for(self, issuer: str, now: datetime) -> KeySet:
        kid = "k1" if self.warmed else "k-before-rotation"
        return KeySet(issuer=ISSUER, keys=(signing_key(kid),), fetched_at=now)

    def key_for(self, issuer: str, kid: str, now: datetime) -> SigningKey:
        self.warmed = True
        return signing_key(kid)


def test_a_key_rotated_since_the_cache_was_filled_still_verifies_the_finishing_screen(
    writer: Writer,
) -> None:
    """`verified_claims` warms the key source for the token's kid, as `authenticate` does. Delete
    this and the warm can go, and an install whose realm rotated its key during the install
    refuses the one sign-in that lets anybody in, until a cache expires."""
    with serving(writer) as c:
        c.app.state.gate = GateWiring(  # type: ignore[attr-defined]
            authority=TokenAuthority(
                issuer=ISSUER,
                audience="brain-api",
                keys=RotatedKeys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        answer = finishing(c)

    assert answer.status_code == 200
    assert writer.held == {INSTALLER: "u_admin"}


def test_a_first_administrator_who_is_no_longer_live_is_refused_as_everything_else_is(
    client: TestClient, writer: Writer
) -> None:
    """The binder's own refusal on the finishing screen is the one answer too. Delete this and it
    can surface as success or as a different status, telling a holder of the code that the
    administrator it named exists and has been disabled."""
    gone = finishing(client, principal_id="u_gone")
    wrong = finishing(client, code=WRONG)

    assert gone.status_code == 404
    assert refusal(gone) == refusal(wrong)
    assert writer.held == {}


# ----------------------------------------------------------------------- the database


@contextmanager
def audited(database: str) -> Iterator[str]:
    """The soft-deleted tables with `0047` applied. Where the server has no pgvector, `retirable`
    stops at `0045`; `0046` touches only `know.chunk`, so it is stamped and `0047` is run."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "stamp", "0046")
            migrate(database, "upgrade", "0047")
        yield url


def with_writer[T](url: str, work: Callable[[SignInBindings], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(
                sign_in_bindings(make_session_factory(engine), env={"INSTALL_OIDC_ISSUER": ISSUER})
            )
        finally:
            await engine.dispose()

    return run(go)


def sign_in_entries(url: str) -> list[AuditEntry]:
    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry WHERE action = 'sign_in' ORDER BY seq",
    )
    names = ("seq", "at", "actor_id", "action", "subject", "ent_hash", "trace_id", "details")
    return [
        AuditEntry(**dict(zip((*names, "prev_hash", "entry_hash"), row, strict=True)))
        for row in rows
    ]


def recorded(principal_id: str, change: SignInChange) -> Mapping[str, str]:
    """What `AuditRecorder.sign_in` writes as details, in a chain held in memory."""
    recorder = AuditRecorder(
        AuditChain(),
        actor_id="u_admin",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: datetime.now(UTC),
    )
    return recorder.sign_in(principal_id=principal_id, change=change).details


def test_an_administrators_binding_is_in_the_ledger_naming_them_their_reach_and_the_request() -> (
    None
):
    """See `A_WAY_IN_NAMES_WHO_MADE_IT`. The digest the database computed agrees with Python's, and
    the details are the recorder's. Delete this and the trigger, or the settings the binder sets
    for it, can go, and nobody can say who gave an account a way in."""
    with audited("brain_sir_ledger") as url:
        a_principal(url, "u_joiner")
        outcome = with_writer(
            url,
            lambda w: w.bind(
                "s-joiner",
                principal_id="u_joiner",
                bound_by="u_admin",
                now=datetime.now(UTC),
                ent_hash="ab" * 16,
                trace_id="trace-bind-1",
            ),
        )
        entries = sign_in_entries(url)

    assert outcome is Binding.BOUND
    [entry] = entries
    assert (entry.actor_id, entry.subject, entry.ent_hash, entry.trace_id) == (
        "u_admin",
        "principal:u_joiner",
        "ab" * 16,
        "trace-bind-1",
    )
    assert entry.details == dict(recorded("u_joiner", SignInChange.BOUND)) == {"change": "bound"}
    assert entry.recompute_hash() == entry.entry_hash


def test_a_sign_in_binding_nobody_is_named_for_is_refused_and_a_chat_binding_is_not_a_sign_in() -> (
    None
):
    """See `A_WAY_IN_NAMES_WHO_MADE_IT`. Delete this and the refusal can become an unattributed
    entry, or the channel check can go and every Lark binding is recorded as a sign-in."""
    with audited("brain_sir_nobody") as url:
        a_principal(url, "u_joiner")
        insert = (
            "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at)"
            " VALUES (%s, %s, 'u_joiner', now())"
        )
        with pytest.raises(psycopg.errors.RestrictViolation, match="names nobody"):
            sql(url, insert, "console", "c" * 64)
        sql(url, insert, "lark", "d" * 64)
        # Already retired when written: no way in is made, so nothing is refused or recorded.
        sql(
            url,
            "INSERT INTO auth.principal_identity"
            " (channel, identity_hash, principal_id, bound_at, deleted_at)"
            " VALUES ('console', %s, 'u_joiner', now(), now())",
            "e" * 64,
        )
        rows = sql(url, "SELECT channel FROM auth.principal_identity ORDER BY channel")
        entries = sign_in_entries(url)

    assert rows == [("console",), ("lark",)]
    assert entries == []


def test_a_retirement_is_recorded_with_its_retirer_or_as_unattributed_and_never_refused() -> None:
    """See `A_WAY_OUT_IS_NEVER_REFUSED_FOR_WANT_OF_A_NAME`. Delete this and `retire` can stop naming
    the retirer, or the trigger can refuse an operator's offboarding at midnight."""
    now = datetime.now(UTC)
    with audited("brain_sir_retire") as url:
        a_principal(url, "u_one")
        a_principal(url, "u_two")

        async def both(w: SignInBindings) -> bool:
            await w.bind("s-one", principal_id="u_one", bound_by="u_admin", now=now)
            await w.bind("s-two", principal_id="u_two", bound_by="u_admin", now=now)
            return await w.retire("u_one", retired_by="u_offboarder")

        retired = with_writer(url, both)
        # Neither update retires anything: one touches a live row, one a row already retired.
        touch = "UPDATE auth.principal_identity SET bound_at = bound_at WHERE principal_id = %s"
        sql(url, touch, "u_two")
        sql(url, touch, "u_one")
        sql(
            url,
            "UPDATE auth.principal_identity SET deleted_at = now()"
            " WHERE principal_id = 'u_two' AND deleted_at IS NULL",
        )
        entries = sign_in_entries(url)

    assert retired is True
    assert [(e.actor_id, e.subject, dict(e.details)) for e in entries] == [
        ("u_admin", "principal:u_one", {"change": "bound"}),
        ("u_admin", "principal:u_two", {"change": "bound"}),
        ("u_offboarder", "principal:u_one", dict(recorded("u_one", SignInChange.RETIRED))),
        ("unattributed", "principal:u_two", {"change": "retired", "actor": "unattributed"}),
    ]
    assert all(e.recompute_hash() == e.entry_hash for e in entries)


def claims_for(subject: str, now: datetime) -> VerifiedClaims:
    """Claims as `validate_token` returns them. The route tests above hold how they are produced;
    this half is about what the store does with a subject it is handed."""
    return VerifiedClaims(
        issuer=ISSUER,
        subject=subject,
        audience=("brain-api",),
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        session_id="sess-1",
        key_id="k1",
        algorithm="RS256",
        verified_at=now,
        claims={"sub": subject},
    )


def test_the_finishing_screen_binds_the_first_administrator_once_against_the_database() -> None:
    """The finishing screen over the real store, the real resolver and the trigger. Delete this and
    `sign_ins` can count the wrong rows, or the administrator check can read nothing, with every
    in-memory test above still green."""
    now = datetime.now(UTC)
    enrolment = open_enrolment(digest=digest_of(SECRET), issued_at=now - timedelta(minutes=5))
    with audited("brain_sir_finish") as url:
        for pid in ("u_admin", "u_later", "u_plain"):
            a_principal(url, pid)
        a_grant(url, "u_admin", SIGN_IN_AUTHORITY.value)
        a_grant(url, "u_later", SIGN_IN_AUTHORITY.value)
        # A chat binding and a retired sign-in are not somebody signing in, so neither closes it.
        sql(
            url,
            "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at,"
            " deleted_at) VALUES ('lark', %s, 'u_plain', now(), NULL),"
            " ('console', %s, 'u_later', now(), now())",
            "f" * 64,
            "a" * 64,
        )

        async def attempt(w: SignInBindings, subject: str, pid: str) -> Binding | str:
            engine = app_engine(url)
            try:
                return await finish_sign_in(
                    w,
                    StoredEntitlements(make_session_factory(engine)),
                    enrolment=enrolment,
                    presented=SECRET,
                    claims=claims_for(subject, now),
                    principal_id=pid,
                    trace_id="trace-finish",
                    now=now,
                )
            except Absent:
                return "refused"
            finally:
                await engine.dispose()

        plain = with_writer(url, lambda w: attempt(w, "s-plain", "u_plain"))
        first = with_writer(url, lambda w: attempt(w, INSTALLER, "u_admin"))
        second = with_writer(url, lambda w: attempt(w, "s-later", "u_later"))

        async def who(subject: str) -> str | None:
            engine = app_engine(url)
            try:
                found = await StoredDirectory(make_session_factory(engine)).principal_for_subject(
                    ISSUER, subject
                )
                return None if found is None else found.id
            finally:
                await engine.dispose()

        installer, later = run(lambda: who(INSTALLER)), run(lambda: who("s-later"))
        entries = sign_in_entries(url)

    assert (plain, first, second) == ("refused", Binding.BOUND, "refused")
    assert (installer, later) == ("u_admin", None)
    assert [(e.actor_id, e.subject) for e in entries] == [(GRANTED_BY, "principal:u_admin")]
