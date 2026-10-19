"""Withdrawing a template version, undoing it, and moving a template between installs (M27.15.35).

Five parts. The domain, over values: what a withdrawal and its undo may be, which versions are
withdrawn and which ids are gone, a document read back from what an export wrote and refused where
it was changed, what counts as a company's detail, and what name an import may take. The recorder
and `0261`, rendered and held to the model and to each other with no server. The routes, driven
through the real application over a store in memory, with a reader holding the install authority
over the company, one holding it over a department, and one holding nothing. The page the gallery
draws is `tests/unit/test_agent_routes.py`'s, and the rows, the policies and the ledger on a real
database are `tests/unit/test_acceptance_template_withdrawal.py`'s and the install check's.

**Every refusal has a sibling proving the permitted case is answered**, because a route that refused
everybody would satisfy every refusal.

Task ids: M27.15.35
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.schema import CreateTable

from brain.agents.catalogue import CATALOGUE
from brain.agents.template import (
    SignedManifest,
    publish,
    verify,
)
from brain.agents.template_withdrawal import (
    ALREADY_WITHDRAWN,
    COMPANY_DETAILS_IN_THE_DOCUMENT,
    DOCUMENT_WAS_CHANGED,
    EXPORT_SCHEMA,
    NO_REASON_GIVEN,
    NOT_A_NAME_THIS_INSTALL_MAY_TAKE,
    NOT_A_TEMPLATE_DOCUMENT,
    NOT_WITHDRAWN,
    REASON_CHARS,
    REASON_TOO_LONG,
    TemplateWithdrawalError,
    Withdrawal,
    arrival,
    company_details,
    export_document,
    fully_withdrawn,
    may_take_the_name,
    read_export,
    reason_of,
    same_body,
    withdrawing,
    withdrawn_keys,
)
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import IDENTIFIER, AuditChain
from brain.audit.record import AuditRecorder, TemplateVersionChange
from brain.console.reads import plane_capability_for
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.db import Base
from brain.identity.bearer import TokenAuthority
from brain.ops.template_withdrawal_store import StoredTemplateWithdrawals
from brain.tables import template_withdrawal as table_module
from brain.tables.template import TemplateVersionRow
from tests.fixtures.http_client import Response
from tests.fixtures.no_database import as_if_ci_had_a_database
from tests.unit.test_agent_routes import KEY, SIGNED_AT, manifest, published_row
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
from tests.unit.test_tables import DIALECT, VERSIONS, as_amended, migration_module, rendered, squash

MIGRATION = VERSIONS / "0261_template_withdrawal.py"
REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)

VERSION = f"{API_PREFIX}/agent-templates/pricing_desk/versions/1"
WITHDRAWAL = f"{VERSION}/withdrawal"
UNDO = f"{WITHDRAWAL}/undo"
EXPORT = f"{VERSION}/export"
WITHDRAWN = f"{API_PREFIX}/agent-template-withdrawals"
IMPORT = f"{API_PREFIX}/agent-template-imports"
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


# ------------------------------------------------------------------------------ the domain
def a_change(withdrawn: bool, *, version: int = 1, reason: str = "Superseded.") -> Withdrawal:
    return Withdrawal(
        template_id="pricing_desk",
        version=version,
        withdrawn=withdrawn,
        set_by="u_admin",
        at=NOW,
        reason=reason if withdrawn else "",
    )


def test_a_change_that_changes_nothing_is_refused_and_one_that_changes_something_is_not() -> None:
    """Withdrawing what is withdrawn and undoing what is not are refused in their own sentences;
    withdrawing a version nobody withdrew, undoing a withdrawal, and withdrawing a version whose
    withdrawal was undone are each let through.

    Delete this and the history reads a version withdrawn twice, and an undo of nothing writes a
    row that says a withdrawal ended which never began."""
    with pytest.raises(TemplateWithdrawalError, match=ALREADY_WITHDRAWN):
        withdrawing(a_change(True), withdraw=True)
    with pytest.raises(TemplateWithdrawalError, match=NOT_WITHDRAWN):
        withdrawing(None, withdraw=False)
    with pytest.raises(TemplateWithdrawalError, match=NOT_WITHDRAWN):
        withdrawing(a_change(False), withdraw=False)
    withdrawing(None, withdraw=True)
    withdrawing(a_change(True), withdraw=False)
    withdrawing(a_change(False), withdraw=True)


def test_a_reason_is_one_sentence_of_a_bounded_length_with_nothing_unprintable_in_it() -> None:
    """Blank is refused with the sentence that asks for one, one over the bound is refused rather
    than cut, a control character is made a space, and a plain reason is kept as written.

    Delete this and a withdrawal can say nothing, or be cut to words its writer did not write, or
    carry a line break that a page draws as nothing and a log as the start of another entry."""
    with pytest.raises(TemplateWithdrawalError, match=NO_REASON_GIVEN):
        reason_of("   \n ")
    with pytest.raises(TemplateWithdrawalError, match=REASON_TOO_LONG):
        reason_of("x" * (REASON_CHARS + 1))
    assert reason_of("x" * REASON_CHARS) == "x" * REASON_CHARS
    assert reason_of(" Unsafe\ninstruction\x07 ") == "Unsafe instruction"
    assert reason_of("Superseded by version two.") == "Superseded by version two."


def test_a_version_is_withdrawn_by_its_newest_row_and_an_id_is_gone_when_all_are() -> None:
    """A version is withdrawn when its newest row is a withdrawal, and an id is gone from the
    gallery only when every version stored under it is. An id with a version left, or with nothing
    stored at all, is not gone.

    Delete this and withdrawing the old version of a template hides the template, or a shipped
    template nobody ever signed here is treated as withdrawn."""
    newest = {
        ("alpha", 1): Withdrawal(
            template_id="alpha", version=1, withdrawn=True, set_by="u", at=NOW, reason="r"
        ),
        ("alpha", 2): Withdrawal(
            template_id="alpha", version=2, withdrawn=True, set_by="u", at=NOW, reason="r"
        ),
        ("beta", 1): Withdrawal(
            template_id="beta", version=1, withdrawn=True, set_by="u", at=NOW, reason="r"
        ),
        ("beta", 2): Withdrawal(template_id="beta", version=2, withdrawn=False, set_by="u", at=NOW),
    }
    gone = withdrawn_keys(newest)
    on_file = [("alpha", 1), ("alpha", 2), ("beta", 1), ("beta", 2), ("gamma", 1)]

    assert gone == {("alpha", 1), ("alpha", 2), ("beta", 1)}
    assert fully_withdrawn(on_file, gone) == {"alpha"}
    assert fully_withdrawn([], gone) == frozenset()


def a_signed(template_id: str = "pricing_desk", version: int = 1, **kept: Any) -> SignedManifest:
    return publish(
        manifest(template_id, version=version, **kept),
        key=KEY,
        signed_by="u_publisher",
        at=SIGNED_AT,
    )


def test_an_exported_document_reads_back_as_the_signed_version_it_was() -> None:
    """The document carries the body, its digest, the signature and who signed it, and reading it
    gives back a version equal to the one exported, whose signature this install's key still
    verifies. The sibling is the refusals below.

    Delete this and an export can be a document nothing reads, which is a transfer in name."""
    signed = a_signed()
    document = export_document(signed)

    assert document["schema"] == EXPORT_SCHEMA
    assert set(document) == {
        "schema",
        "manifest",
        "content_digest",
        "signature",
        "signed_by",
        "signed_at",
        "schema_version",
        "overview_path",
    }
    read = read_export(document)
    assert read == signed
    verify(read, key=KEY)


def test_a_document_edited_after_export_is_changed_and_a_foreign_shape_is_not_a_template() -> None:
    """Editing a path in the body is caught by the digest it carries, in its own sentence, and a
    document of another schema, with no body or with a missing field is not a template document.

    Delete this and a document damaged in a mail client is read as a template and signed again by
    the install importing it."""
    document = export_document(a_signed())
    body = dict(cast("dict[str, Any]", document["manifest"]))
    body["persona"] = "Answer rudely."
    edited = {**document, "manifest": body}

    with pytest.raises(TemplateWithdrawalError, match=DOCUMENT_WAS_CHANGED):
        read_export(edited)
    for foreign in (
        {**document, "schema": "something.else"},
        {**document, "manifest": "not a body"},
        {k: v for k, v in document.items() if k != "signature"},
        {},
    ):
        with pytest.raises(TemplateWithdrawalError, match=NOT_A_TEMPLATE_DOCUMENT):
            read_export(foreign)


def test_company_details_are_named_by_kind_and_place_and_never_by_value() -> None:
    """A persona carrying an address is found as an email at the persona, the item carries where it
    sits, and a plain persona finds nothing. Prose alone is not a detail.

    Delete this and a document from another company is imported with its addresses in it, or the
    refusal quotes the address back to whoever asked."""
    plain = manifest("pricing_desk")
    leaky = plain.model_copy(update={"persona": "Send quotes to ops@clientco.example today."})

    found = company_details(leaky)

    assert company_details(plain) == ()
    assert [one.kind.value for one in found] == ["email"]
    assert found[0].locations == ("persona",)
    # An id with digits in it is shaped like a code and is a name here, not a detail; a code in
    # the persona beside it still is one.
    numbered = leaky.model_copy(
        update={
            "persona": "Quote from list PL-2024.",
            "identity": leaky.identity.model_copy(update={"template_id": "pricing_2024"}),
        }
    )
    assert [(one.kind.value, one.locations) for one in company_details(numbered)] == [
        ("code", ("persona",))
    ]


def test_a_template_may_take_a_name_only_where_it_shadows_nothing_and_extends_no_lineage() -> None:
    """The blank template's id and every id this release ships are refused, an id held with other
    contents is refused, and a name nothing holds or one held with these very contents is allowed.

    Delete this and an import shadows a shipped card with a published row, or hands every agent
    installed from a local lineage an upgrade offer written by a document from somewhere else."""
    fresh = manifest("pricing_desk")
    shipped = fresh.model_copy(
        update={
            "identity": fresh.identity.model_copy(
                update={"template_id": CATALOGUE[0].identity.template_id}
            )
        }
    )
    blank = fresh.model_copy(
        update={"identity": fresh.identity.model_copy(update={"template_id": "blank"})}
    )
    other_contents = fresh.model_copy(update={"persona": "Answer at length."})

    assert may_take_the_name(fresh, None)
    assert may_take_the_name(fresh, {1: fresh})
    assert not may_take_the_name(shipped, None)
    assert not may_take_the_name(blank, None)
    assert not may_take_the_name(fresh, {1: other_contents})


def test_an_arrival_is_version_one_published_by_the_importer_and_changes_nothing_else() -> None:
    """The identity is the one thing that changes, which is what `same_body` ignores; a persona, a
    ceiling and a leash are the document's. The version a lineage here starts at is one whatever
    the document said.

    Delete this and an import keeps the exporter's version number and publisher, which are facts
    about another install."""
    received = a_signed(version=7)

    made = arrival(received, by="u_importer")

    assert (made.identity.version, made.identity.published_by) == (1, "u_importer")
    assert same_body(made, received.manifest)
    assert made.persona == received.manifest.persona
    assert not same_body(made, received.manifest.model_copy(update={"persona": "Different."}))


# ------------------------------------------------------------------- the recorder and 0261
def test_0261_copies_the_grammars_and_widths_the_model_holds() -> None:
    """Delete this and one side can change alone: a reason the table refuses after the press, or a
    principal grammar the trigger's actor no longer matches."""
    migration = migration_module(MIGRATION)

    assert migration.TABLES == ("agent.template_withdrawal",)
    assert migration.IDENTIFIER == IDENTIFIER
    assert migration.REASON_CHARS == table_module.REASON_CHARS == REASON_CHARS
    assert migration.AGENT_ID_CHARS == 60
    assert TemplateVersionChange.WITHDRAWN.value == migration.WITHDRAWN_WORD
    assert TemplateVersionChange.WITHDRAWAL_UNDONE.value == migration.UNDONE_WORD
    assert migration.down_revision == "0250"


def test_0261_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Compared as rendered DDL, for `test_tables`' reason. Delete this and the model can gain a
    column or lose the key to the version, with the database built the old way."""
    expected = squash(
        str(CreateTable(Base.metadata.tables["agent.template_withdrawal"]).compile(dialect=DIALECT))
    )

    assert expected in as_amended(rendered("upgrade", MIGRATION))


def test_0261_reads_and_writes_in_the_sessions_name_and_never_edits_or_removes() -> None:
    """Row-level security on, SELECT and INSERT only, the insert in the session's own name, a
    trigger after every insert, and a downgrade that drops what the upgrade made.

    Delete this and an UPDATE grant, or a policy admitting a withdrawal in somebody else's name,
    ships with every other test here green."""
    emitted = squash(rendered("upgrade", MIGRATION))
    principal = "current_setting('app.principal_id', true)"

    assert "ALTER TABLE agent.template_withdrawal ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON agent.template_withdrawal TO brain_app" in emitted
    assert "UPDATE ON agent.template_withdrawal" not in emitted
    assert "DELETE ON agent.template_withdrawal" not in emitted
    assert f"FOR INSERT TO brain_app WITH CHECK (set_by = {principal})" in emitted
    assert (
        "CREATE TRIGGER template_withdrawal_is_audited AFTER INSERT ON agent.template_withdrawal "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_template_withdrawal()"
    ) in emitted
    down = squash(rendered("downgrade", MIGRATION))
    assert "DROP TABLE agent.template_withdrawal" in down
    assert "DROP FUNCTION agent.record_template_withdrawal()" in down


def test_0261_s_trigger_writes_what_the_recorder_writes() -> None:
    """A withdrawal and its undoing are `publish` entries about `artifact:<template>.v<n>` whose
    details say `withdrawn` or `withdrawal_undone`, by the row's actor.

    Delete this and the entry a deployed database keeps can drift from the recorder's, and the
    audit screen reads the two differently."""
    migration = migration_module(MIGRATION)
    recorder = AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    withdrawn = recorder.publish(
        artifact_id="pricing_desk.v2", change=TemplateVersionChange.WITHDRAWN
    )
    undone = recorder.publish(
        artifact_id="pricing_desk.v2", change=TemplateVersionChange.WITHDRAWAL_UNDONE
    )
    arrival_entry = recorder.publish(artifact_id="pricing_desk.v2")
    body = " ".join(migration.TEMPLATE_WITHDRAWAL_TRIGGER_FUNCTION.split())

    assert withdrawn.action == undone.action == arrival_entry.action == "publish"
    assert withdrawn.subject == "artifact:pricing_desk.v2"
    assert dict(withdrawn.details) == {"change": "withdrawn"}
    assert dict(undone.details) == {"change": "withdrawal_undone"}
    assert dict(arrival_entry.details) == {}
    assert "'change', CASE WHEN NEW.withdrawn THEN 'withdrawn' ELSE 'withdrawal_undone' END" in body
    assert "'artifact:' || NEW.template_id || '.v' || NEW.version::text" in body
    assert "v_seq, v_at, NEW.set_by, 'publish', v_subject" in body


def test_nothing_that_withdraws_a_version_reads_or_writes_an_installed_agent() -> None:
    """**Installed agents stay pinned, structurally.** None of the four modules that decide, keep
    and serve a withdrawal names the instance table, the agent table or the pin, so no withdrawal
    can move an agent. The sibling is the one module that does name them for another reason.

    Delete this and a later edit can make a withdrawal re-pin or disable the agents it was for,
    which the pin exists to prevent."""
    forbidden = {"TemplateInstanceRow", "AgentRow", "UpgradeDeclineRow", "agent.template_instance"}
    for relative in (
        "src/brain/agents/template_withdrawal.py",
        "src/brain/ops/template_withdrawal_store.py",
        "src/brain/template_withdrawal_routes.py",
        "src/brain/tables/template_withdrawal.py",
    ):
        tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        strings = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert not (names | strings) & forbidden, relative
    install_store = ast.parse((REPO / "src/brain/agents/install_store.py").read_text("utf-8"))
    assert "TemplateInstanceRow" in {
        node.id for node in ast.walk(install_store) if isinstance(node, ast.Name)
    }


# ------------------------------------------------------------------------------ the routes
def _everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


INSTALL = Capability(value="admin:agent_install")
GALLERY = screen("skills").read
GALLERY_READ = (GALLERY.requires, plane_capability_for(GALLERY, GALLERY.plane))

#: `u_admin` holds the gallery and the install authority over the company. `u_narrow` holds
#: the authority over one department only. `u_wide` holds the gallery and no authority. `u_none`
#: holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": _everywhere(*GALLERY_READ, INSTALL),
    "u_narrow": (
        *_everywhere(*GALLERY_READ),
        Grant(capability=INSTALL, scope=Scope.department("web")),
    ),
    "u_wide": _everywhere(*GALLERY_READ),
    "u_none": (),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


class Held(StoredTemplateWithdrawals):
    """The withdrawal store over a list in memory, deciding as the real one does."""

    def __init__(self) -> None:
        super().__init__(cast(Any, None))
        self.versions: dict[tuple[str, int], TemplateVersionRow] = {}
        self.changes: list[Withdrawal] = []
        self.kept: list[SignedManifest] = []

    async def row_of(self, template_id: str, version: int) -> TemplateVersionRow | None:
        return self.versions.get((template_id, version))

    async def rows_of(self, template_id: str) -> Sequence[TemplateVersionRow]:
        return [row for (one, _), row in sorted(self.versions.items()) if one == template_id]

    async def rows_named(self, keys: Sequence[tuple[str, int]]) -> Sequence[TemplateVersionRow]:
        return [row for key, row in self.versions.items() if key in keys]

    async def history(self, template_id: str, version: int) -> tuple[Withdrawal, ...]:
        return tuple(
            one for one in self.changes if (one.template_id, one.version) == (template_id, version)
        )

    async def newest(self) -> Mapping[tuple[str, int], Withdrawal]:
        return {(one.template_id, one.version): one for one in self.changes}

    async def change(
        self,
        template_id: str,
        version: int,
        *,
        withdraw: bool,
        reason: str,
        by: str,
        ent_hash: str,
        trace_id: str,
    ) -> Withdrawal | None:
        if (template_id, version) not in self.versions:
            return None
        history = await self.history(template_id, version)
        withdrawing(history[-1] if history else None, withdraw=withdraw)
        made = Withdrawal(
            template_id=template_id,
            version=version,
            withdrawn=withdraw,
            set_by=by,
            at=NOW + timedelta(minutes=len(self.changes)),
            reason=reason,
        )
        self.changes.append(made)
        return made

    async def keep_version(
        self, signed: SignedManifest, *, by: str, ent_hash: str, trace_id: str
    ) -> bool:
        identity = signed.manifest.identity
        if (identity.template_id, identity.version) in self.versions:
            return False
        self.versions[(identity.template_id, identity.version)] = TemplateVersionRow(
            template_id=identity.template_id,
            version=identity.version,
            content_digest=signed.content_digest,
            signature=signed.signature,
            signed_by=signed.signed_by,
            signed_at=signed.signed_at,
            document=signed.manifest.document(),
        )
        self.kept.append(signed)
        return True


class Served:
    """An application, the store it reads and the switches a test turns."""

    def __init__(self, app: FastAPI, client: TestClient, held: Held) -> None:
        self.app, self.client, self.held = app, client, held

    def on(self, value: bool) -> None:
        self.app.state.template_withdrawal_on = value

    def key(self, value: str | None) -> None:
        self.app.state.template_key = value

    def get(self, pid: str, path: str) -> Response:
        out: Response = self.client.get(
            path, headers={"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}
        )
        return out

    def post(self, pid: str, path: str, body: Mapping[str, Any] | None = None) -> Response:
        out: Response = self.client.post(
            path,
            headers={"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"},
            json=dict(body or {}),
        )
        return out


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> Iterator[Served]:
    """A process with no database, a store in memory holding one published version, the switch on
    and this test's signing key held. Pinned off the database for `tests.fixtures.no_database`'s
    reason."""
    as_if_ci_had_a_database(monkeypatch)
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    held = Held()
    held.versions[("pricing_desk", 1)] = published_row(
        "pricing_desk", 1, display_name="Pricing desk"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = _wiring()
        app.state.template_withdrawals = held
        app.state.template_withdrawal_on = True
        app.state.template_key = KEY
        yield Served(app, client, held)


def test_withdrawing_and_undoing_are_each_an_inserted_row_in_the_callers_name(
    served: Served,
) -> None:
    """The reason is kept, the version reads withdrawn with the change in its history, and the undo
    reads offered with both rows; nothing is edited, so there are two rows after two presses. A
    second withdrawal and a second undo are each refused in their own sentence.

    Delete this and a withdrawal can overwrite its own history, or be pressed twice into a log
    that says it happened twice."""
    first = served.post("u_admin", WITHDRAWAL, {"reason": "Superseded by version two."})
    again = served.post("u_admin", WITHDRAWAL, {"reason": "Pressed twice."})
    undone = served.post("u_admin", UNDO)
    twice = served.post("u_admin", UNDO)

    assert first.status_code == 200, first.text
    assert first.json()["withdrawn"] is True and first.json()["may_undo"] is True
    assert [
        (one["withdrawn"], one["set_by"], one["reason"]) for one in first.json()["changes"]
    ] == [(True, "u_admin", "Superseded by version two.")]
    assert again.status_code == twice.status_code == 409
    assert again.json()["sentence"] == ALREADY_WITHDRAWN
    assert twice.json()["sentence"] == NOT_WITHDRAWN
    assert undone.status_code == 200 and undone.json()["withdrawn"] is False
    assert [one.withdrawn for one in served.held.changes] == [True, False]


def test_a_withdrawal_with_no_reason_is_refused_and_one_with_a_reason_is_not(
    served: Served,
) -> None:
    """A reason of only white space is the sentence that asks for one, an empty or over-long one is
    a request the shape refuses, and nothing is written for any of them.

    Delete this and a version is hidden with nothing said about why."""
    spaced = served.post("u_admin", WITHDRAWAL, {"reason": "   "})
    empty = served.post("u_admin", WITHDRAWAL, {"reason": ""})
    long = served.post("u_admin", WITHDRAWAL, {"reason": "x" * (REASON_CHARS + 1)})
    assert spaced.status_code == 409 and spaced.json()["sentence"] == NO_REASON_GIVEN
    assert empty.status_code == long.status_code == 422
    assert served.held.changes == []

    assert served.post("u_admin", WITHDRAWAL, {"reason": "Unsafe wording."}).status_code == 200


def test_a_caller_without_the_authority_over_the_company_is_refused_as_a_missing_version_is(
    served: Served,
) -> None:
    """The install authority over one department, the gallery alone and nothing at all each get the
    answer a version nobody published gets, status and message, for the state, the withdrawal and
    its undo; the administrator is the sibling who is answered. Nothing is written.

    Delete this and a department's installer hides a version from every other department, or the
    address tells somebody which versions exist."""
    missing = served.get(
        "u_admin", f"{API_PREFIX}/agent-templates/nobody_desk/versions/1/withdrawal"
    )
    assert missing.status_code == 404
    for pid in ("u_narrow", "u_wide", "u_none"):
        for answered in (
            served.get(pid, WITHDRAWAL),
            served.post(pid, WITHDRAWAL, {"reason": "Because."}),
            served.post(pid, UNDO),
            served.get(pid, WITHDRAWN),
            served.get(pid, EXPORT),
        ):
            assert answered.status_code == 404, (pid, answered.text)
            assert answered.json()["message"] == missing.json()["message"]
    assert served.held.changes == []
    assert served.get("u_admin", WITHDRAWAL).status_code == 200


def test_with_the_switch_off_withdrawing_exporting_and_importing_are_refused_and_an_undo_is_not(
    served: Served,
) -> None:
    """**The switch gates the door and never traps what it opened.** A version withdrawn while it
    was on can be put back with it off, and its state is still read, saying why Withdraw is not
    pressable; a new withdrawal, an export and an import are refused in the one sentence.

    Delete this and turning the switch off leaves a version hidden for ever, or a switch that
    gates nothing."""
    served.post("u_admin", WITHDRAWAL, {"reason": "Superseded."})
    served.on(False)

    state = served.get("u_admin", WITHDRAWAL).json()
    refused = [
        served.post("u_admin", UNDO),
        served.post("u_admin", WITHDRAWAL, {"reason": "Again."}),
        served.get("u_admin", EXPORT),
        served.post("u_admin", IMPORT, {"document": {}}),
    ]

    assert (state["may_undo"], state["may_withdraw"]) == (True, False)
    assert state["unavailable"]
    assert refused[0].status_code == 200 and refused[0].json()["withdrawn"] is False
    for answer in refused[1:]:
        assert answer.status_code == 409
        assert answer.json()["sentence"] == state["unavailable"]
    assert [one.withdrawn for one in served.held.changes] == [True, False]


def test_the_people_who_may_undo_are_told_what_is_withdrawn_and_why_and_nothing_else(
    served: Served,
) -> None:
    """The withdrawn list carries the version, its name, the reason, who and when, and a version
    whose withdrawal was undone is not on it. Delete this and the page has nowhere to undo from,
    since the gallery no longer lists what was withdrawn."""
    served.post("u_admin", WITHDRAWAL, {"reason": "Wrong tone."})
    listed = served.get("u_admin", WITHDRAWN).json()["versions"]
    served.post("u_admin", UNDO)
    after = served.get("u_admin", WITHDRAWN).json()["versions"]

    assert [
        (one["template_id"], one["version"], one["reason"], one["set_by"]) for one in listed
    ] == [("pricing_desk", 1, "Wrong tone.", "u_admin")]
    assert listed[0]["display_name"] == "Pricing desk"
    assert after == []


def another_install_holds(*documents: SignedManifest) -> Held:
    held = Held()
    for one in documents:
        identity = one.manifest.identity
        held.versions[(identity.template_id, identity.version)] = TemplateVersionRow(
            template_id=identity.template_id,
            version=identity.version,
            content_digest=one.content_digest,
            signature=one.signature,
            signed_by=one.signed_by,
            signed_at=one.signed_at,
            document=one.manifest.document(),
        )
    return held


def test_an_exported_template_is_imported_by_reading_it_then_confirming_the_digest_shown(
    served: Served,
) -> None:
    """**The round trip.** The export is the signed version; the first call of the import writes
    nothing and says what it read and that this install's own key made the signature; the second,
    naming the digest, writes version one under this install's key with the importer as publisher;
    a third finds the template already held and writes nothing.

    Delete this and an import either writes on a reading or trusts a signature only the exporter
    could check."""
    exported = served.get("u_admin", EXPORT)
    document = exported.json()["document"]
    receiver = Held()
    served.app.state.template_withdrawals = receiver

    read = served.post("u_admin", IMPORT, {"document": document})
    written = served.post(
        "u_admin", IMPORT, {"document": document, "expected_digest": document["content_digest"]}
    )
    again = served.post(
        "u_admin", IMPORT, {"document": document, "expected_digest": document["content_digest"]}
    )

    assert exported.status_code == 200 and document["schema"] == EXPORT_SCHEMA
    assert read.json()["imported"] is False and read.json()["signed_by_this_install"] is True
    assert read.json()["company_details"] == []
    assert written.status_code == 200, written.text
    assert (written.json()["imported"], written.json()["created"]) == (True, True)
    [signed] = receiver.kept
    assert (signed.manifest.identity.version, signed.manifest.identity.published_by) == (
        1,
        "u_admin",
    )
    verify(signed, key=KEY)
    assert signed.signed_by == "u_admin"
    assert (again.json()["imported"], again.json()["created"]) == (True, False)
    assert len(receiver.kept) == 1


def test_a_signature_made_elsewhere_is_reported_as_unchecked_and_the_import_is_signed_here(
    served: Served,
) -> None:
    """A document exported under another install's key reads as not signed by this install, and a
    confirmed import is still signed with this install's own key: what the exporter's signature
    said is reported and relied on for nothing.

    Delete this and a document is imported verbatim with a signature this install cannot verify,
    which `verify` then refuses at the first install."""
    foreign = publish(
        manifest("pricing_desk", version=4),
        key="a-different-install",
        signed_by="u_far",
        at=SIGNED_AT,
    )
    document = export_document(foreign)
    receiver = Held()
    served.app.state.template_withdrawals = receiver

    read = served.post("u_admin", IMPORT, {"document": document})
    written = served.post(
        "u_admin", IMPORT, {"document": document, "expected_digest": foreign.content_digest}
    )

    assert read.json()["signed_by_this_install"] is False
    assert written.json()["created"] is True
    [kept] = receiver.kept
    verify(kept, key=KEY)
    assert kept.signature != foreign.signature
    assert kept.manifest.identity.version == 1


def test_an_import_is_refused_where_the_document_is_not_the_one_shown_or_not_what_it_says(
    served: Served,
) -> None:
    """The wrong digest, a body edited after export, a foreign document, a company's address in the
    persona, a shipped template's id, an id held with other contents and a process with no key are
    each refused in their own sentence, write nothing, and the refusal about an address names its
    kind and place and never the address.

    Delete this and an import writes a document it was not shown, or quotes an address back."""
    receiver = Held()
    served.app.state.template_withdrawals = receiver
    good = export_document(a_signed("fresh_desk"))
    leaky = a_signed("leaky_desk")
    leaky = publish(
        leaky.manifest.model_copy(update={"persona": "Send quotes to ops@clientco.example."}),
        key=KEY,
        signed_by="u_x",
        at=SIGNED_AT,
    )
    shipped = a_signed(CATALOGUE[0].identity.template_id)
    held_other = a_signed("held_desk")
    receiver.versions[("held_desk", 1)] = TemplateVersionRow(
        template_id="held_desk",
        version=1,
        content_digest=held_other.content_digest,
        signature=held_other.signature,
        signed_by=held_other.signed_by,
        signed_at=held_other.signed_at,
        document=held_other.manifest.document(),
    )
    changed = publish(
        held_other.manifest.model_copy(update={"persona": "Answer at length."}),
        key=KEY,
        signed_by="u_x",
        at=SIGNED_AT,
    )
    edited = {
        **good,
        "manifest": {**cast("dict[str, Any]", good["manifest"]), "persona": "Rude."},
    }

    def confirm(document: Mapping[str, Any]) -> Response:
        return served.post(
            "u_admin",
            IMPORT,
            {"document": dict(document), "expected_digest": str(document.get("content_digest"))},
        )

    wrong = served.post("u_admin", IMPORT, {"document": good, "expected_digest": "0" * 64})
    changed_body = confirm(edited)
    foreign = served.post(
        "u_admin", IMPORT, {"document": {"schema": "x"}, "expected_digest": "0" * 64}
    )
    leak = confirm(export_document(leaky))
    preview = served.post("u_admin", IMPORT, {"document": export_document(leaky)})
    ships = confirm(export_document(shipped))
    clash = confirm(export_document(changed))

    assert (
        wrong.status_code == 409 and "not the document you were shown" in wrong.json()["sentence"]
    )
    assert changed_body.json()["sentence"] == DOCUMENT_WAS_CHANGED
    assert foreign.json()["sentence"] == NOT_A_TEMPLATE_DOCUMENT
    assert leak.json()["sentence"] == COMPANY_DETAILS_IN_THE_DOCUMENT
    assert [(one["kind"], one["places"]) for one in preview.json()["company_details"]] == [
        ("email", ["persona"])
    ]
    assert "clientco" not in preview.text and "clientco" not in leak.text
    assert ships.json()["sentence"] == NOT_A_NAME_THIS_INSTALL_MAY_TAKE
    assert clash.json()["sentence"] == NOT_A_NAME_THIS_INSTALL_MAY_TAKE
    assert receiver.kept == []
    served.key(None)
    assert "signing key" in confirm(good).json()["sentence"]
    assert receiver.kept == []
    served.key(KEY)
    assert confirm(good).status_code == 200 and len(receiver.kept) == 1
