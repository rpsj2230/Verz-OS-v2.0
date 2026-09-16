"""Sessions and sign-in links over HTTP: what each screen lists, what each control refuses, and
that a control reaches the store only through the decision it is meant to ask.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py`, and with a store in memory standing where the database is. The
store decides nothing of its own: the sessions store asks the route's `may` under what would be the
row's lock, exactly as `brain.identity.session_store.StoredSessions.end` does, and the links store
decides with `brain.identity.sign_in_binding.decide_unlink`, the store's own rule. What reaches the
database, the ledger entries the triggers write and the refusal of the next request are proved in
`tests/unit/test_session_store.py` and `tests/unit/test_sign_in_links.py`, against PostgreSQL.

**Every refusal has a sibling proving the permitted case is answered**, which is CLAUDE.md's rule
about a guard tested only by its refusals.

Task ids: M27.7.10, M27.7.11
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import session_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.govern import SESSION_CONTROL
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.sign_in_links import (
    THE_ACCOUNT_IS_KEPT_AT_THE_IDENTITY_PROVIDER_AND_NOT_HERE,
    THE_LAST_ADMINISTRATOR_KEEPS_THEIR_LINK,
    UNLINKING_TAKES_EFFECT_ON_THE_NEXT_REQUEST,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.identity.first_administrator import SIGN_IN_AUTHORITY
from brain.identity.session_store import EndedSession, StoredSession
from brain.identity.sign_in_binding import SignInLink, Unlinked, decide_unlink
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from tests.fixtures.http_client import Response
from tests.fixtures.no_database import as_if_ci_had_a_database
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SUBJECTS,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

SESSIONS = f"{API_PREFIX}/govern/sessions"
END = f"{API_PREFIX}/govern/sessions/end"
LINKS = f"{API_PREFIX}/govern/sign-ins"
UNLINK = f"{API_PREFIX}/govern/sign-ins/unlink"

#: A literal rather than read off `bearer.SECOND_FACTOR_METHODS`, for the reason
#: `test_classification_routes` gives about its own copy.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock. The
#: routes read the real clock, so a session's window is built around it rather than around this.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

SESSION_READ = screen("sessions").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
EXISTENCE = plane_capability(Plane.EXISTENCE)
EVERYWHERE = Scope.unrestricted()
WEB = Scope.department("web")

#: Who sits where, by the subjects `test_api_routes` mints tokens for.
DEPARTMENTS: Mapping[str, str | None] = {
    "u_narrow": "web",
    "u_wide": "sales",
    "u_prefix": "web",
    "u_none": None,
    "u_admin": "web",
    "u_elsewhere": "finance",
}


def grant(capability: Capability | str, scope: Scope = EVERYWHERE) -> Grant:
    value = capability if isinstance(capability, Capability) else Capability(value=capability)
    return Grant(capability=value, scope=scope)


#: `u_admin` reads sessions and may end one everywhere and holds the sign-in authority.
#: `u_narrow` reads sessions in web only and may end them there. `u_wide` reads everywhere and
#: holds no control. `u_prefix` holds the read on the existence plane only, which a bare
#: capability check would let in. `u_elsewhere` holds the sign-in authority in finance only, which
#: is not held. `u_none` holds nothing.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (
        grant(SESSION_READ),
        grant(CONFIGURATION),
        grant(SESSION_CONTROL),
        grant(SIGN_IN_AUTHORITY),
    ),
    "u_narrow": (grant(SESSION_READ, WEB), grant(CONFIGURATION), grant(SESSION_CONTROL, WEB)),
    "u_wide": (grant(SESSION_READ), grant(CONFIGURATION)),
    "u_prefix": (grant(SESSION_READ), grant(EXISTENCE), grant(SESSION_CONTROL)),
    "u_elsewhere": (grant(SIGN_IN_AUTHORITY, Scope.department("finance")),),
    "u_none": (),
}


def person(pid: str) -> Principal:
    return Principal(
        id=pid,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {pid}",
        primary_department=DEPARTMENTS[pid],
    )


class Directory:
    """A `PrincipalDirectory` that keeps no ledger of sessions, as every test double does."""

    async def principal_for_subject(self, issuer: str, subject: str) -> Principal | None:
        for pid, sub in SUBJECTS.items():
            if issuer == ISSUER and sub == subject:
                return person(pid)
        return None


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def a_session(
    session_id: str, principal_id: str, department: str | None, *, lapsed: bool = False
) -> StoredSession:
    now = datetime.now(UTC)
    started = now - timedelta(hours=11 if lapsed else 1)
    return StoredSession(
        session_id=session_id,
        principal_id=principal_id,
        display_name=f"Person {principal_id}",
        department=department,
        channel="console",
        second_factor=False,
        started_at=started,
        expires_at=started + timedelta(hours=10),
    )


@dataclass
class Sessions:
    """A `session_routes.SessionStore` in memory. `end` asks `may` as the real store does."""

    live: dict[str, StoredSession] = field(default_factory=dict)
    ended: dict[str, EndedSession] = field(default_factory=dict)
    full: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def open_sessions(
        self, *, now: datetime, limit: int
    ) -> tuple[tuple[StoredSession, ...], bool]:
        self.calls.append({"open": limit})
        return tuple(one for one in self.live.values() if one.is_live(now)), self.full

    async def end(
        self,
        session_id: str,
        *,
        may: Callable[[StoredSession], bool],
        ended_by: str,
        ent_hash: str,
        trace_id: str,
        now: datetime,
    ) -> EndedSession | None:
        self.calls.append({"end": session_id, "ended_by": ended_by, "ent_hash": ent_hash})
        found = self.live.get(session_id)
        if found is None or not found.is_live(now) or not may(found):
            return None
        del self.live[session_id]
        ended = EndedSession(session_id=session_id, principal_id=found.principal_id, ended_at=now)
        self.ended[session_id] = ended
        return ended


@dataclass
class Links:
    """A `session_routes.SignInLinkStore` in memory, deciding with `decide_unlink`."""

    linked: dict[str, SignInLink] = field(default_factory=dict)
    administrators: set[str] = field(default_factory=set)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def links(self, *, limit: int) -> tuple[tuple[SignInLink, ...], bool]:
        self.calls.append({"links": limit})
        return tuple(self.linked.values()), False

    async def administrators_linked(self, now: datetime) -> frozenset[str]:
        return frozenset(self.administrators & set(self.linked))

    async def unlink(
        self,
        principal_id: str,
        *,
        unlinked_by: str,
        now: datetime,
        ent_hash: str = "",
        trace_id: str = "",
    ) -> Unlinked:
        self.calls.append({"unlink": principal_id, "unlinked_by": unlinked_by})
        outcome = decide_unlink(
            principal_id,
            linked=self.linked,
            administrators=self.administrators & set(self.linked),
        )
        if outcome is Unlinked.UNLINKED:
            del self.linked[principal_id]
        return outcome


def a_link(principal_id: str) -> SignInLink:
    return SignInLink(
        principal_id=principal_id,
        display_name=f"Person {principal_id}",
        department=DEPARTMENTS.get(principal_id),
        bound_at=LONG_AGO,
    )


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@pytest.fixture
def sessions() -> Sessions:
    return Sessions()


@pytest.fixture
def links() -> Links:
    return Links()


def an_app() -> FastAPI:
    """The real application with this router mounted, as `brain.app` mounts it.

    Included here as well, which is `tests/unit/test_sign_in_routes.py`' arrangement: a route
    registered twice answers from the first registration, which is the same function, and this
    file then tests the router whether or not the line in `brain.app` is in the tree it runs in.

    **With no database, named rather than inherited.** `Settings` reads `DATABASE_URL`, and CI's
    unit job sets it, so an app built from the environment has a session factory there and none
    here. `session_routes.session_store_of` falls back to that factory, which made the no-store
    test below answer 200 in CI and 500 on every laptop. The store in memory is what stands where
    the database is in this file, so the database is switched off here and not left to the host.
    """
    app = create_app(Settings(env="development", database_url=""))
    app.include_router(session_routes.router)
    return app


@pytest.fixture
def client(sessions: Sessions, links: Links) -> Iterator[TestClient]:
    app = an_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.session_store = sessions
        app.state.sign_in_bindings = links
        yield c


def auth(pid: str, *, strong: bool = True, sid: str = "sess-1") -> dict[str, str]:
    claims: dict[str, object] = {"sid": sid, **(SECOND_FACTOR if strong else {})}
    return {"authorization": f"Bearer {token_for(pid, claims=claims)}"}


def refusal(answer: Response) -> dict[str, Any]:
    """One refusal body with the per-request trace id taken out, its presence asserted."""
    body = dict(answer.json())
    assert "trace_id" in body
    body["trace_id"] = "<per request>"
    return body


# ------------------------------------------------------------------- the listing


def test_a_reader_of_the_sessions_screen_sees_every_live_session_and_nothing_lapsed(
    client: TestClient, sessions: Sessions
) -> None:
    """The positive case for every refusal below. Delete this and each refusal is satisfied by a
    route that lists nothing, and a lapsed session listed with a control beside it reads as
    somebody working now."""
    sessions.live["s-web"] = a_session("s-web", "u_narrow", "web")
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")
    sessions.live["s-old"] = a_session("s-old", "u_wide", "sales", lapsed=True)

    answer = client.get(SESSIONS, headers=auth("u_wide"))

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert sorted(one["session_id"] for one in body["items"]) == ["s-sales", "s-web"]
    assert body["ending"] == session_routes.ENDING_A_SESSION_IS_ONE_SITTING_AND_NOT_THE_PERSON
    assert body["appears"] == session_routes.A_SESSION_APPEARS_FROM_ITS_FIRST_REQUEST


def test_a_department_reader_sees_their_departments_sessions_and_nothing_of_the_rest(
    client: TestClient, sessions: Sessions
) -> None:
    """`govern.open_sessions` over the row the person sits in. Delete this and the route can list
    what it loaded, which is an attendance register of the whole company handed to a department
    reader; and a person with no department listed to a scoped reader, which fails open."""
    sessions.live["s-web"] = a_session("s-web", "u_narrow", "web")
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")
    sessions.live["s-nowhere"] = a_session("s-nowhere", "u_none", None)

    narrow = client.get(SESSIONS, headers=auth("u_narrow")).json()
    wide = client.get(SESSIONS, headers=auth("u_wide")).json()

    assert [one["session_id"] for one in narrow["items"]] == ["s-web"]
    assert sorted(one["session_id"] for one in wide["items"]) == ["s-nowhere", "s-sales", "s-web"]


def test_the_control_is_offered_only_where_may_end_says_so_and_the_readers_own_session_is_marked(
    client: TestClient, sessions: Sessions
) -> None:
    """Delete this and `endable` can be drawn from the listing capability, so every reader of the
    screen is shown a button to sign everybody out; or `yours` can mark every row, and an
    administrator ends the session they are reading the screen on."""
    sessions.live["sess-1"] = a_session("sess-1", "u_admin", "web")
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")

    admin = client.get(SESSIONS, headers=auth("u_admin", sid="sess-1")).json()["items"]
    reader = client.get(SESSIONS, headers=auth("u_wide", sid="other")).json()["items"]

    assert {(one["session_id"], one["endable"], one["yours"]) for one in admin} == {
        ("sess-1", True, True),
        ("s-sales", True, False),
    }
    assert {(one["session_id"], one["endable"], one["yours"]) for one in reader} == {
        ("sess-1", False, False),
        ("s-sales", False, False),
    }


def test_a_caller_without_the_screen_or_on_the_existence_plane_is_refused_before_any_store(
    client: TestClient, sessions: Sessions
) -> None:
    """`permitted` asks the capability and the plane together. Delete this and a bare capability
    check lets an existence-only reader open a configuration screen, or the store is reached for
    before the refusal, so a caller with nothing learns whether this process has a database."""
    stranger = client.get(SESSIONS, headers=auth("u_none"))
    existence = client.get(SESSIONS, headers=auth("u_prefix"))

    assert stranger.status_code == existence.status_code == 404
    assert refusal(stranger) == refusal(existence)
    assert sessions.calls == []


def test_a_full_load_says_so_and_no_answer_carries_a_count(
    client: TestClient, sessions: Sessions
) -> None:
    """Delete this and `truncated` can be dropped, so a full page reads as everybody; or a field
    named for a hidden count can join the answer, which on a listing filtered per reader is the
    subtraction CLAUDE.md forbids. Asked of every model on both screens."""
    sessions.live["s-web"] = a_session("s-web", "u_narrow", "web")
    sessions.full = True

    body = client.get(SESSIONS, headers=auth("u_narrow")).json()

    assert body["truncated"] is True
    for model in (
        session_routes.SessionsPage,
        session_routes.SessionView,
        session_routes.SignInLinksPage,
        session_routes.SignInLinkView,
        session_routes.UnlinkView,
        session_routes.SessionEnded,
    ):
        assert not set(model.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, model


# ------------------------------------------------------------------- the control


def test_an_administrator_ends_a_session_they_may_see_and_the_store_is_told_who_did_it(
    client: TestClient, sessions: Sessions
) -> None:
    """The positive case for the control. Delete this and every refusal below is satisfied by a
    control that ends nothing, and the actor or reach passed to the store, which the ledger entry
    is written from, can be anybody."""
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")

    answer = client.post(END, headers=auth("u_admin"), json={"session_id": "s-sales"})

    assert answer.status_code == 200, answer.text
    assert answer.json()["principal_id"] == "u_wide"
    assert "s-sales" in sessions.ended and "s-sales" not in sessions.live
    [call] = [one for one in sessions.calls if "end" in one]
    reach = EntitlementSet(principal_id="u_admin", grants=GRANTS["u_admin"])
    assert (call["ended_by"], call["ent_hash"]) == ("u_admin", reach.ent_hash())


def test_a_reader_without_the_control_a_password_only_session_and_a_stranger_are_refused_alike(
    client: TestClient, sessions: Sessions
) -> None:
    """`admin:session` is withheld by admission without a second factor. Delete this and the
    control can be repointed at a verb a stolen password exercises, or the route can reach the
    store for a caller holding nothing, which tells them whether the session exists."""
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")

    reader = client.post(END, headers=auth("u_wide"), json={"session_id": "s-sales"})
    weak = client.post(END, headers=auth("u_admin", strong=False), json={"session_id": "s-sales"})
    stranger = client.post(END, headers=auth("u_none"), json={"session_id": "s-sales"})

    assert reader.status_code == weak.status_code == stranger.status_code == 404
    assert refusal(reader) == refusal(weak) == refusal(stranger)
    assert [one for one in sessions.calls if "end" in one] == []
    assert "s-sales" in sessions.live


def test_a_session_out_of_reach_and_a_session_that_is_not_there_are_one_refusal(
    client: TestClient, sessions: Sessions
) -> None:
    """`may` is `open_sessions` and `may_end` over the locked row. Delete this and a department
    administrator ends a session in another department by guessing its id, or the two refusals
    differ and the control becomes a way of asking which sessions exist."""
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")
    sessions.live["s-web"] = a_session("s-web", "u_prefix", "web")

    out_of_reach = client.post(END, headers=auth("u_narrow"), json={"session_id": "s-sales"})
    missing = client.post(END, headers=auth("u_narrow"), json={"session_id": "s-nothing"})
    within = client.post(END, headers=auth("u_narrow"), json={"session_id": "s-web"})

    assert out_of_reach.status_code == missing.status_code == 404
    assert refusal(out_of_reach) == refusal(missing)
    assert "s-sales" in sessions.live
    assert within.status_code == 200, within.text


def test_a_control_that_may_see_but_not_end_is_refused_under_the_lock(
    client: TestClient, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`may` asks both halves. Delete this and `may` can be `open_sessions` alone, so a reader who
    may list a department's sessions and holds the control for another department ends them."""
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")
    reach = (
        grant(SESSION_READ),
        grant(CONFIGURATION),
        grant(SESSION_CONTROL, Scope.department("finance")),
    )
    monkeypatch.setitem(GRANTS, "u_elsewhere", reach)

    answer = client.post(END, headers=auth("u_elsewhere"), json={"session_id": "s-sales"})

    assert answer.status_code == 404
    assert "s-sales" in sessions.live


def test_a_control_held_everywhere_does_not_end_a_session_the_reader_may_not_see(
    client: TestClient, sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of `may`. Delete this and `may` can be `may_end` alone, so a reader who may
    list one department's sessions and holds the control everywhere ends a session in a department
    the screen never showed them, by posting an id they learned somewhere else."""
    sessions.live["s-sales"] = a_session("s-sales", "u_wide", "sales")
    sessions.live["s-web"] = a_session("s-web", "u_prefix", "web")
    reach = (grant(SESSION_READ, WEB), grant(CONFIGURATION), grant(SESSION_CONTROL))
    monkeypatch.setitem(GRANTS, "u_elsewhere", reach)

    unseen = client.post(END, headers=auth("u_elsewhere"), json={"session_id": "s-sales"})
    seen = client.post(END, headers=auth("u_elsewhere"), json={"session_id": "s-web"})

    assert unseen.status_code == 404
    assert "s-sales" in sessions.live
    assert seen.status_code == 200, seen.text


def test_a_session_id_the_ledger_could_not_record_is_refused_before_anything_is_asked(
    client: TestClient, sessions: Sessions
) -> None:
    """Delete this and the body can carry any string into a statement and into a log line."""
    answer = client.post(END, headers=auth("u_admin"), json={"session_id": "not a session id"})

    assert answer.status_code == 422
    assert [one for one in sessions.calls if "end" in one] == []


# ------------------------------------------------------------------- sign-in links


def test_an_administrator_over_everything_sees_every_link_and_the_last_administrators_is_marked(
    client: TestClient, links: Links
) -> None:
    """The positive case for the links screen. Delete this and the listing can come back empty
    for everybody, or the mark can be drawn from something other than the store's own rule."""
    links.linked = {pid: a_link(pid) for pid in ("u_admin", "u_wide")}
    links.administrators = {"u_admin"}

    answer = client.get(LINKS, headers=auth("u_admin"))

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert {
        (one["principal_id"], one["last_administrator"], one["yours"]) for one in body["items"]
    } == {
        ("u_admin", True, True),
        ("u_wide", False, False),
    }
    assert body["account"] == THE_ACCOUNT_IS_KEPT_AT_THE_IDENTITY_PROVIDER_AND_NOT_HERE
    assert body["unlinking"] == UNLINKING_TAKES_EFFECT_ON_THE_NEXT_REQUEST
    assert body["last_administrator"] == THE_LAST_ADMINISTRATOR_KEEPS_THEIR_LINK


def test_a_link_carries_no_account_and_no_digest(client: TestClient, links: Links) -> None:
    """Delete this and a row can grow the subject or its digest, which is the account identifier
    `brain.tables.identity` refuses to hold, arriving on a screen instead."""
    links.linked = {"u_wide": a_link("u_wide")}

    [row] = client.get(LINKS, headers=auth("u_admin")).json()["items"]

    assert set(row) == {
        "principal_id",
        "display_name",
        "department",
        "linked_at",
        "last_administrator",
        "yours",
    }
    assert SUBJECTS["u_wide"] not in client.get(LINKS, headers=auth("u_admin")).text


def test_the_links_screen_is_refused_to_anybody_not_holding_the_authority_over_everything(
    client: TestClient, links: Links
) -> None:
    """Held in one department is not held. Delete this and a department administrator reads who
    across the company can be signed in as, which is the map a link is made on."""
    links.linked = {"u_wide": a_link("u_wide")}

    partial = client.get(LINKS, headers=auth("u_elsewhere"))
    weak = client.get(LINKS, headers=auth("u_admin", strong=False))
    stranger = client.get(LINKS, headers=auth("u_none"))

    assert partial.status_code == weak.status_code == stranger.status_code == 404
    assert refusal(partial) == refusal(weak) == refusal(stranger)
    assert links.calls == []


def test_unlinking_retires_the_link_names_the_administrator_and_says_what_follows(
    client: TestClient, links: Links
) -> None:
    """The positive case for the unlink. Delete this and every refusal below is satisfied by an
    unlink that does nothing, or the store is told a different actor than the one the ledger must
    name."""
    links.linked = {pid: a_link(pid) for pid in ("u_admin", "u_wide")}
    links.administrators = {"u_admin"}

    answer = client.post(UNLINK, headers=auth("u_admin"), json={"principal_id": "u_wide"})

    assert answer.status_code == 200, answer.text
    assert answer.json() == {
        "principal_id": "u_wide",
        "outcome": "unlinked",
        "sentence": UNLINKING_TAKES_EFFECT_ON_THE_NEXT_REQUEST,
    }
    assert "u_wide" not in links.linked
    assert links.calls[-1] == {"unlink": "u_wide", "unlinked_by": "u_admin"}


def test_unlinking_the_last_administrators_own_link_is_refused_with_the_sentence_saying_why(
    client: TestClient, links: Links
) -> None:
    """M27.7.11's refusal. Delete this and the last administrator unlinks their own sign-in and
    nobody can ever sign in to link anybody again; or the refusal comes back as the one 404, and
    the administrator is told nothing they can act on."""
    links.linked = {pid: a_link(pid) for pid in ("u_admin", "u_wide")}
    links.administrators = {"u_admin"}

    answer = client.post(UNLINK, headers=auth("u_admin"), json={"principal_id": "u_admin"})

    assert answer.status_code == 409
    assert answer.json() == {
        "principal_id": "u_admin",
        "outcome": "last_administrator",
        "sentence": THE_LAST_ADMINISTRATOR_KEEPS_THEIR_LINK,
    }
    assert "u_admin" in links.linked


def test_a_second_administrator_linked_lets_the_first_unlink_their_own(
    client: TestClient, links: Links
) -> None:
    """The sibling. Delete this and the refusal can fire for any administrator unlinking their own
    link, which is an administrator who can never move to a new account."""
    links.linked = {pid: a_link(pid) for pid in ("u_admin", "u_wide")}
    links.administrators = {"u_admin", "u_wide"}

    answer = client.post(UNLINK, headers=auth("u_admin"), json={"principal_id": "u_admin"})

    assert answer.status_code == 200, answer.text
    assert "u_admin" not in links.linked


def test_an_unlink_by_somebody_without_the_authority_and_of_nobody_linked_are_one_refusal(
    client: TestClient, links: Links
) -> None:
    """Delete this and the unlink becomes a way of asking who can sign in: a principal with no
    link answered differently from a caller who may not ask."""
    links.linked = {"u_admin": a_link("u_admin")}
    links.administrators = {"u_admin"}

    nobody = client.post(UNLINK, headers=auth("u_admin"), json={"principal_id": "u_never"})
    partial = client.post(UNLINK, headers=auth("u_elsewhere"), json={"principal_id": "u_admin"})

    assert nobody.status_code == partial.status_code == 404
    assert refusal(nobody) == refusal(partial)
    assert [one for one in links.calls if one.get("unlinked_by") == "u_elsewhere"] == []


def test_a_process_with_no_store_refuses_a_permitted_caller_and_nobody_else_differently(
    sessions: Sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a caller with no grant learns whether this process has a database: the
    screen's question must come before the store is reached for.

    `DATABASE_URL` is set to an address nothing listens on, which is CI's environment without
    CI's server, and the premise is asserted before anything is asked. Until 2026-09-17 this
    read the host's environment, so in CI the process had a database and the permitted caller
    was answered 200; asserting the premise is what makes that fail here as well as there."""
    as_if_ci_had_a_database(monkeypatch)
    app = an_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        assert app.state.db_sessions is None
        assert getattr(app.state, "session_store", None) is None
        app.state.gate = _wiring()
        stranger = c.get(SESSIONS, headers=auth("u_none"))
        permitted_caller = c.get(SESSIONS, headers=auth("u_wide"))
        links_stranger = c.get(LINKS, headers=auth("u_none"))
        links_admin = c.get(LINKS, headers=auth("u_admin"))

    assert stranger.status_code == links_stranger.status_code == 404
    assert permitted_caller.status_code == links_admin.status_code == 500
