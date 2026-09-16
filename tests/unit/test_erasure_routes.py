"""What the Retention and erasure screen needs beside the report, over HTTP.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py`. What is under test is who is told they may act, what each act is
said to do, who is shown which erasure request and which export, and who may file a request. The
report's own routes are `tests/unit/test_retention_routes.py`'s, and the store's statements are
`tests/unit/test_erasure_store.py`'s against a server.

**The authorities are spelled out here rather than imported**, so a repointed capability in
`brain.retention_routes` or `brain.erasure_routes` is a failure in this file rather than a constant
compared with itself.

Task ids: M27.7.24
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditAction
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.erasure_routes import (
    ERASING,
    ERASURES_ARE_LISTED,
    EXPORT_LOG_NOT_YOURS,
    EXPORTS_ARE_LISTED,
    HOLDING,
    LIFTING,
    RELEASING,
    WITHDRAWING,
)
from brain.identity.bearer import TokenAuthority
from brain.ops import erasure
from brain.ops.data_export_store import TakenExport
from brain.ops.erasure_store import (
    ALREADY_REQUESTED,
    ErasureRecord,
    ErasureRefusedError,
    PostgresEraser,
)
from brain.ops.export import ExportReason
from brain.ops.retention import HORIZONS
from brain.tables.data_export import ExportDataSet
from brain.tables.erasure import ErasureOutcome
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

CONTROLS = f"{API_PREFIX}/govern/retention/controls"
QUEUE = f"{API_PREFIX}/govern/erasures"
EXPORTS = f"{API_PREFIX}/govern/retention/exports"

RETENTION_READ = Capability(value="read:retention_policy")
EXPORT_READ = Capability(value="read:export")
RELEASE = Capability(value="admin:retention")
HOLD = Capability(value="admin:legal_hold")
ERASE = Capability(value="admin:erasure")
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
WEB = Scope.department("web")

#: Far outside any wall clock. See CLAUDE.md on dates in fixtures.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def _everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


def _in_web(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=WEB) for one in capabilities)


#: `u_admin` may read and do everything. `u_narrow` may read and release. `u_wide` may read, hold
#: and read exports. `u_elsewhere` may open the screen in one department only and do nothing, and
#: is the person one request is about. `u_prefix` holds every authority over one department only,
#: which is not an authority over everything. `u_none` holds every authority and not the screen,
#: and must learn nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": _everywhere(RETENTION_READ, CONFIGURATION, RELEASE, HOLD, ERASE, EXPORT_READ),
    "u_narrow": _everywhere(RETENTION_READ, CONFIGURATION, RELEASE),
    "u_wide": _everywhere(RETENTION_READ, CONFIGURATION, HOLD, EXPORT_READ),
    "u_elsewhere": _in_web(RETENTION_READ, CONFIGURATION),
    "u_prefix": (
        *_everywhere(RETENTION_READ, CONFIGURATION),
        *_in_web(RELEASE, HOLD, ERASE, EXPORT_READ),
    ),
    "u_none": _everywhere(RELEASE, HOLD, ERASE, EXPORT_READ),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def a_request(request_id: str, subject_id: str, *, finished: bool = False) -> ErasureRecord:
    return ErasureRecord(
        request_id=request_id,
        subject_id=subject_id,
        reason_reference="DSAR-1",
        requested_by="u_admin",
        requested_at=LONG_AGO,
        finished_at=LONG_AGO if finished else None,
        outcome=ErasureOutcome.INCOMPLETE if finished else None,
        stores=(
            (
                {
                    "store": "recording",
                    "disposition": "erase",
                    "reached": False,
                    "removed": 0,
                    "retired": 0,
                    "kept": 0,
                    "because": "no object-store eraser is attached",
                },
            )
            if finished
            else ()
        ),
        holds=(),
    )


class Erasures:
    """`ErasureRecords` in memory: two requests, and a record of every request filed."""

    def __init__(self) -> None:
        self.held = [
            a_request("r-about-elsewhere", "u_elsewhere", finished=True),
            a_request("r-about-somebody", "p_somebody"),
        ]
        self.filed: list[dict[str, object]] = []

    async def file(
        self,
        *,
        subject_id: str,
        reason_reference: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> ErasureRecord:
        if subject_id == "p_already":
            raise ErasureRefusedError(ALREADY_REQUESTED)
        self.filed.append(
            {"subject_id": subject_id, "reason_reference": reason_reference, "actor": actor}
        )
        return ErasureRecord(
            request_id="r-new",
            subject_id=subject_id,
            reason_reference=reason_reference,
            requested_by=actor,
            requested_at=at,
            finished_at=None,
            outcome=None,
            stores=(),
            holds=(),
        )

    async def requests(self, *, limit: int) -> tuple[ErasureRecord, ...]:
        return tuple(self.held[:limit])


def an_export(export_id: str, by: str) -> TakenExport:
    return TakenExport(
        export_id=export_id,
        data_set=ExportDataSet.AUDIT_TRAIL,
        requested_by=by,
        reason=ExportReason.REGULATORY_REQUEST,
        reason_reference="MATTER-1",
        produced_at=LONG_AGO,
        first_seq=0,
        last_seq=1,
        entries=2,
        verified=True,
        document_digest="d" * 64,
    )


class Exports:
    """`ExportLog` in memory."""

    async def recent(self, *, limit: int) -> tuple[TakenExport, ...]:
        return (an_export("e-1", "u_admin"), an_export("e-2", "u_wide"))


@pytest.fixture
def erasures() -> Erasures:
    return Erasures()


@pytest.fixture
def client(erasures: Erasures) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.erasure_records = erasures
        app.state.export_log = Exports()
        yield c


#: A session with a second factor. `brain.gate.admission` withholds every `admin:` capability
#: from a password-only sign-in, so without it no authority here would ever be held.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


def headers(pid: str, *, second_factor: bool = True) -> dict[str, str]:
    token = token_for(pid, claims=SECOND_FACTOR if second_factor else None)
    return {"authorization": f"Bearer {token}"}


def get(c: TestClient, pid: str, path: str = CONTROLS, *, second_factor: bool = True) -> Response:
    response: Response = c.get(path, headers=headers(pid, second_factor=second_factor))
    return response


def file(c: TestClient, pid: str, body: object) -> Response:
    response: Response = c.post(QUEUE, headers=headers(pid), json=body)
    return response


def without_trace(response: Response) -> dict[str, object]:
    found = dict(response.json())
    found.pop("trace_id", None)
    return found


# ------------------------------------------------------------------------ the controls
def test_each_authority_draws_its_own_controls_and_none_draws_another(client: TestClient) -> None:
    """Releasing, holding, erasing and reading the export log are four authorities, each held over
    everything, and each flag follows its own. A department-scoped grant of all four is none.

    Delete this and one flag could follow another authority, drawing a request form for somebody
    who may only place holds, or a department's grant could draw a control over every store."""
    flags = {
        pid: tuple(
            get(client, pid).json()[flag]
            for flag in ("may_release", "may_hold", "may_erase", "may_read_exports")
        )
        for pid in ("u_admin", "u_narrow", "u_wide", "u_elsewhere", "u_prefix")
    }

    assert flags == {
        "u_admin": (True, True, True, True),
        "u_narrow": (True, False, False, False),
        "u_wide": (False, True, False, True),
        "u_elsewhere": (False, False, False, False),
        "u_prefix": (False, False, False, False),
    }


def test_a_password_only_session_is_drawn_no_retention_control(client: TestClient) -> None:
    """The flags are the authorities as the gate admitted them, and the gate withholds an `admin:`
    capability from a sign-in with no second factor. Delete this and a flag computed from the raw
    grants would draw a request form the write route then refuses."""
    body = get(client, "u_admin", second_factor=False).json()

    assert (body["may_release"], body["may_hold"], body["may_erase"]) == (False, False, False)


def test_a_caller_who_may_not_open_the_screen_learns_nothing_on_any_route(
    client: TestClient, erasures: Erasures
) -> None:
    """Holding every authority without the screen is refused like holding nothing, on the controls,
    the queue, the export log and the write alike, and the write reaches no store.

    Delete this and a caller could learn which retention powers they hold, read the queue of who
    asked to be erased, or file an erasure, on a screen they may not open."""
    refused = [
        get(client, "u_none"),
        get(client, "u_none", QUEUE),
        get(client, "u_none", EXPORTS),
        file(client, "u_none", {"subject_id": "p_somebody", "reason_reference": "DSAR-2"}),
    ]

    assert [one.status_code for one in refused] == [404, 404, 404, 404]
    assert all(without_trace(one) == {"message": Absent.public_message} for one in refused)
    assert erasures.filed == []
    assert get(client, "u_elsewhere").status_code == 200


def test_every_act_is_described_in_the_words_a_confirmation_shows(client: TestClient) -> None:
    """The five sentences travel, each about its own act, and the erasure's names every limit an
    administrator would otherwise read as a promise: the hold, the retirement that leaves rows
    stored, the rows kept, and the stores not reached.

    Delete this and a confirmation could be drawn with no consequence, which `docs/admin-console.md`
    refuses for a destructive action, or an erasure confirmed on a sentence that promised more."""
    body = get(client, "u_admin").json()

    assert body["releasing"] == RELEASING
    assert body["withdrawing"] == WITHDRAWING
    assert body["holding"] == HOLDING
    assert body["lifting"] == LIFTING
    assert body["erasing"] == ERASING
    assert "removes" in RELEASING and "hold" in RELEASING
    assert "removes nothing" in WITHDRAWING
    assert "lifted" in HOLDING and "lifted" in LIFTING
    for limit in ("legal hold", "retired", "leaves them stored", "kept", "not reached", "backup"):
        assert limit in ERASING


def test_the_export_log_and_the_queue_are_lists_now_that_both_are_recorded(
    client: TestClient,
) -> None:
    """Held against the facts outside this module that made the old sentences false: the ledger
    records an erasure, `ops.data_export` records an export, and an executor implements the eraser.
    The day any of them stops being true this goes red, which is the day the page is wrong.

    Delete this and the sentences can drift from the records behind them, telling an administrator
    something is listed on the day it stopped being."""
    body = get(client, "u_admin").json()

    assert (body["exports"], body["erasures"], body["exports_not_yours"]) == (
        EXPORTS_ARE_LISTED,
        ERASURES_ARE_LISTED,
        EXPORT_LOG_NOT_YOURS,
    )
    assert AuditAction.ERASURE.value == "erasure"
    implemented: erasure.StoreEraser = PostgresEraser.__new__(PostgresEraser)
    assert callable(implemented.erase) and callable(implemented.count_for)


def test_how_long_each_kind_of_thing_is_kept_is_every_declared_horizon(client: TestClient) -> None:
    """Delete this and the table could drop a class, and a report line naming that class would
    have nothing on the page saying what it means."""
    kept = get(client, "u_elsewhere").json()["kept"]

    assert [one["data_class"] for one in kept] == [one.data_class.value for one in HORIZONS]
    assert all(one["because"].strip() for one in kept)


# --------------------------------------------------------------------------- the queue
def test_the_queue_is_shown_whole_to_a_company_wide_reader_and_to_a_person_only_their_own(
    client: TestClient,
) -> None:
    """A company-wide grant of the screen reads every request; a reader whose grant is one
    department's reads only the request about themselves, because every request sits nowhere; and
    what a request did in each store travels with it.

    Delete this and a department reader could read the list of everybody who asked to be erased,
    or a person could be refused the one request they have every right to follow up."""
    whole = get(client, "u_admin", QUEUE).json()["requests"]
    own = get(client, "u_elsewhere", QUEUE).json()["requests"]

    assert [one["request_id"] for one in whole] == ["r-about-elsewhere", "r-about-somebody"]
    assert [one["request_id"] for one in own] == ["r-about-elsewhere"]
    assert own[0]["outcome"] == "incomplete"
    assert own[0]["stores"] == [
        {
            "store": "recording",
            "disposition": "erase",
            "reached": False,
            "removed": 0,
            "retired": 0,
            "kept": 0,
            "because": "no object-store eraser is attached",
        }
    ]
    assert whole[1]["outcome"] is None and whole[1]["finished_at"] is None


def test_a_request_is_filed_only_with_the_authority_over_everything_and_in_the_callers_name(
    client: TestClient, erasures: Erasures
) -> None:
    """The authority over everything files a request in the caller's own name, at the request's own
    instant; a department's grant of it, or the screen alone, is refused in the one sentence and
    reaches no store.

    Delete this and a department admin could erase somebody outside their department, or a request
    could be filed in a name the body chose."""
    body = {"subject_id": "p_somebody", "reason_reference": "DSAR-2"}

    filed = file(client, "u_admin", body)
    refused = [file(client, pid, body) for pid in ("u_prefix", "u_narrow", "u_elsewhere")]

    assert filed.status_code == 200
    assert (filed.json()["request_id"], filed.json()["subject_id"]) == ("r-new", "p_somebody")
    assert erasures.filed == [
        {"subject_id": "p_somebody", "reason_reference": "DSAR-2", "actor": "u_admin"}
    ]
    assert [one.status_code for one in refused] == [404, 404, 404]
    assert all(without_trace(one) == {"message": Absent.public_message} for one in refused)


def test_a_second_open_request_for_one_person_is_refused_by_name_to_somebody_who_may_file(
    client: TestClient,
) -> None:
    """A caller holding the authority is told why, because they already read the whole queue and
    the reason is what they need to fix. Delete this and the refusal could arrive as a server
    error, or as the anonymous refusal, and the administrator files again and again."""
    refused = file(client, "u_admin", {"subject_id": "p_already", "reason_reference": "DSAR-3"})

    assert refused.status_code == 404
    assert without_trace(refused) == {
        "message": f"that erasure request was not filed: {ALREADY_REQUESTED}"
    }


def test_a_request_naming_somebody_or_a_reference_the_ledger_cannot_hold_is_refused_before_filing(
    client: TestClient, erasures: Erasures
) -> None:
    """The person is a reference and the reason a token, as the table's own constraints hold them,
    and a body that is neither is refused before the store. The positive sibling is the filed
    request above. Delete this and a sentence can be filed as the reason, which is where the
    reason somebody left ends up."""
    for body in (
        {"subject_id": "p somebody", "reason_reference": "DSAR-4"},
        {"subject_id": "p_somebody", "reason_reference": "because she left"},
        {"subject_id": "p_somebody", "reason_reference": "DSAR-4", "requested_by": "u_other"},
    ):
        assert file(client, "u_admin", body).status_code == 422
    assert erasures.filed == []


# ---------------------------------------------------------------------- the export log
def test_the_export_log_is_shown_to_a_company_wide_reader_of_exports_and_to_nobody_else(
    client: TestClient,
) -> None:
    """An audit trail export covers everybody, so it is read under the Exports screen's own
    capability over everything, whoever took it; a reader of the Retention screen without it, or
    with it over one department, is shown no export.

    Delete this and every administrator who may open the Retention screen reads what left the
    building and who took it, which is the log following the screen rather than its own grant."""
    shown = {
        pid: [one["export_id"] for one in get(client, pid, EXPORTS).json()["exports"]]
        for pid in ("u_admin", "u_wide", "u_narrow", "u_prefix", "u_elsewhere")
    }

    assert shown == {
        "u_admin": ["e-1", "e-2"],
        "u_wide": ["e-1", "e-2"],
        "u_narrow": [],
        "u_prefix": [],
        "u_elsewhere": [],
    }
    first = get(client, "u_admin", EXPORTS).json()["exports"][0]
    assert (first["requested_by"], first["reason"], first["entries"], first["document_digest"]) == (
        "u_admin",
        "regulatory_request",
        2,
        "d" * 64,
    )
