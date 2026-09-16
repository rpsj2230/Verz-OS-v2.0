"""What a reader may be told about a connector, and the four things this screen refuses to say.

The module under test decides what goes on `docs/screens.html`'s SCREEN 9, and the failures worth
writing tests for are not layout failures. They are the ways a connector screen reassures
somebody it should not have: a source named to a reader who holds nothing over it, a blank in the
ceiling column that reads as no ceiling, a vault path on a row, and a figure for today's use
composed out of nothing.

**Every refusal here has a sibling that reads.** A filter tested only by what it drops is
satisfied by a function that returns an empty tuple, and that function would pass half of this
file with the screen showing nothing to anybody.

**The sentence tables are asserted against their enumerations, not against themselves.** The
tables are read out of `AccessMode` and `PermissionSync` rather than listed here, because a test
that listed the members would be a second copy of the enumeration and would go green for a
member nobody had written a sentence for, which is the shape `CLAUDE.md` records three authors
getting wrong in one afternoon.

Task ids: M42.6.5
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest

from brain.connectors.contract import (
    AccessMode,
    ConnectorHealth,
    ConnectorScope,
    CredentialBinding,
    HealthState,
    TransportKind,
)
from brain.connectors.manifest import (
    ChangeSignal,
    ConnectorManifest,
    FieldShape,
    HotUse,
    PermissionSync,
    ProjectedEntity,
    ProjectedField,
    manifest_digest,
)
from brain.connectors.registry import ConnectorState, RegisteredConnector
from brain.console.connector_trust import (
    ACCESS_SAYS,
    COPY_POLICY,
    DECLARATION_AGREED,
    DECLARATION_CHANGED,
    DECLARATION_UNREADABLE,
    KEY_HELD,
    KEY_NOT_HELD,
    KEY_NOT_KNOWN,
    NEVER,
    PERMISSION_SYNC_SAYS,
    PROJECTED,
    THE_SCREEN,
    admitted_connections,
    assert_total,
    ceiling_in_words,
    connected_rows,
    connectors_reachable,
    credential_in_words,
    key_in_words,
    projected_field_count,
    scope_in_words,
    trust_rows,
)
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.projection import MAX_LABEL_CHARS, MAX_PROJECTED_FIELDS
from brain.core.scope import Clause, Op, Scope
from brain.ops.connectable import CONNECTABLE, manifest_for
from brain.ops.connector_store import Connection
from brain.ops.credentials import Held, VaultState
from brain.ops.limits import SOURCE_CEILINGS, connector_ceiling
from brain.ops.secrets import SecretRef, VaultRole

#: Far outside any plausible wall clock, because what these tests are about is not the present.
#: See `CLAUDE.md` on `test_memory_formation.py`: a fixture with a date near today is a clock.
NOW: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

READER: Final = "u_reader"

#: The vault path the fixture manifest is bound to. A sentinel tail rather than a realistic one,
#: so a test asserting that it never leaves the process cannot be satisfied by a word that also
#: appears as a transport name: `database/creds/ro` shares its first segment with the word
#: `database`, which is on every row of this screen legitimately.
VAULT_PATH: Final = "database/creds/sentinel_binding"

#: The capability this screen requires, read out of the registry rather than typed. Typing it
#: would compare a literal against a literal the day the registry moved.
CONNECTOR_READ: Final[Capability] = screen(THE_SCREEN).read.requires

#: A source with a verified ceiling and one whose name nobody has measured. The first is read
#: out of `brain.ops.limits` so the test moves with the table rather than pinning a name.
MEASURED: Final[str] = SOURCE_CEILINGS[0].name
UNMEASURED: Final = "a_source_nobody_measured"


def a_manifest(
    *,
    name: str = "laravel",
    ceiling: str = "",
    mode: AccessMode = AccessMode.READ_ONLY,
    permission_sync: PermissionSync = PermissionSync.NONE,
    fields: int = 1,
    selectors: tuple[str, ...] = ("portal.v_client",),
) -> ConnectorManifest:
    """One manifest, built out of the declarations a real one carries.

    Built rather than stubbed, so the row under test is assembled from the same document
    `manifest_digest` pins. A dataclass with the answers already on it would test the copy loop
    and nothing else.
    """
    granter = {"write_granted_by": "u_owner"} if mode is AccessMode.WRITE else {}
    return ConnectorManifest(
        name=name,
        version="1.0.0",
        transport=TransportKind.DATABASE,
        scope=ConnectorScope(resource_kind="view", selectors=selectors),
        credential=CredentialBinding(
            ref=SecretRef(path=VAULT_PATH, role=VaultRole.APPLICATION),
            mode=mode,
            **granter,
        ),
        projections=(
            ProjectedEntity(
                entity="client",
                fields=tuple(
                    ProjectedField(
                        name=f"id_{n}", shape=FieldShape.IDENTIFIER, uses=(HotUse.IDENTIFY,)
                    )
                    for n in range(fields)
                ),
                change_signal=ChangeSignal.UPDATED_SINCE,
                visibility=Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),)),
            ),
        ),
        ceiling=ceiling,
        permission_sync=permission_sync,
    )


def a_registered(
    name: str = "laravel",
    state: ConnectorState = ConnectorState.ENABLED,
    **manifest: object,
) -> RegisteredConnector:
    return RegisteredConnector(
        manifest=a_manifest(name=name, **manifest),  # type: ignore[arg-type]
        digest="d" * 64,
        state=state,
    )


def reader_of(*names: str, unrestricted: bool = False) -> EntitlementSet:
    """A reader holding the connectors screen's capability over those sources, or over all.

    The scope is written against the `connector` field because that is the axis the registry
    declares for this screen, and a grant written against any other field matches no row.
    """
    if unrestricted:
        scope = Scope.unrestricted()
    else:
        scope = Scope(
            clauses=tuple(Clause(field="connector", op=Op.EQ, value=one) for one in names)
        )
    return EntitlementSet(
        principal_id=READER, grants=(Grant(capability=CONNECTOR_READ, scope=scope),)
    )


# --- who may be told a source exists ----------------------------------------------------------


def test_a_reader_holding_nothing_over_connectors_is_told_no_source_exists() -> None:
    """Deleting this lets a missing grant compile to the unrestricted reach, which is the one
    mistake that turns this screen into a list of every outside system the company reads,
    handed to somebody with no grant over any of them."""
    nothing = EntitlementSet(principal_id=READER, grants=())

    assert connectors_reachable([MEASURED, "laravel"], nothing, NOW) == ()
    assert trust_rows([a_registered("laravel")], nothing, now=NOW) == ()


def test_a_reader_holding_the_capability_over_one_source_is_told_about_that_source() -> None:
    """The sibling of the refusal above, and the whole of what makes it mean anything: a filter
    tested only by what it drops is satisfied by one that returns nothing to everybody, and this
    screen would then be empty on every install while every refusal test stayed green."""
    registry = [a_registered("laravel"), a_registered("freshdesk")]

    assert connectors_reachable(["laravel", "freshdesk"], reader_of("laravel"), NOW) == ("laravel",)
    rows = trust_rows(registry, reader_of("laravel"), now=NOW)

    assert [one.name for one in rows] == ["laravel"]
    # The name of the source that was dropped appears nowhere, not even in a field saying how
    # many were. An absent source and one nobody installed are one answer.
    assert "freshdesk" not in repr(rows)


def test_no_row_and_no_return_value_carries_a_count_of_what_was_left_out() -> None:
    """Deleting this lets somebody add `hidden` or `total` to a row or to the tuple, and a
    reader holding one grant then learns how many outside systems this company reads, which is
    the disclosure by subtraction with every value on the screen correct."""
    rows = trust_rows(
        [a_registered("laravel"), a_registered("freshdesk"), a_registered("xero")],
        reader_of("laravel"),
        now=NOW,
    )

    assert len(rows) == 1
    fields = set(vars(rows[0]))
    assert fields & {"total", "hidden", "withheld", "of", "others"} == set()


# --- what a row says and what it refuses to say -------------------------------------------------


def test_a_scope_sentence_names_every_resource_it_reaches_and_no_figure_beside_them() -> None:
    """Deleting this lets the sentence become "3 views", which is the count of what the scope
    reaches sitting one subtraction away from the count of what the credential could have
    reached, on the one screen whose entire subject is reach."""
    # Three selectors and not two, because with two the manifest author's order reversed is the
    # sorted order for one of the two inputs, and a test that cannot tell sorted from reversed is
    # a test of nothing. Mutation testing on 2026-09-16 reported exactly that survivor.
    said = scope_in_words(ConnectorScope(resource_kind="view", selectors=("v_b", "v_a", "v_c")))

    for one in ("v_a", "v_b", "v_c"):
        assert one in said
    # Sorted, so two installs compared by a person are not being shown a diff of somebody's
    # typing order.
    assert said.index("v_a") < said.index("v_b") < said.index("v_c")
    assert not any(character.isdigit() for character in said)


def test_a_row_carries_no_vault_path_and_names_only_the_role_it_borrows_under() -> None:
    """Deleting this puts `database/creds/ro` on a console row. The reference is safe in a
    configuration row by `CredentialBinding`'s own argument and it is still the fact
    `brain.ops.openbao` keeps out of every error message it builds, because a path names which
    credential was being borrowed."""
    manifest = a_manifest()
    said = credential_in_words(manifest)

    assert VaultRole.APPLICATION.value in said
    assert manifest.credential.ref.path not in said
    row = trust_rows([a_registered()], reader_of(unrestricted=True), now=NOW)[0]
    assert manifest.credential.ref.path not in repr(row)


def test_a_source_with_no_verified_ceiling_says_so_rather_than_showing_nothing() -> None:
    """Deleting this leaves a blank in a column of rates, which reads as no limit, and the
    person reading it plans a backfill against a source that will start refusing at a figure
    nobody has written down. `brain.ops.limits` already refuses to invent the number; this is
    the same refusal said to a person."""
    assert connector_ceiling(UNMEASURED) is None
    said = ceiling_in_words(a_manifest(ceiling=UNMEASURED))

    assert said.strip() != ""
    assert "No verified ceiling" in said


def test_a_source_with_a_verified_ceiling_reports_that_ceilings_own_figures() -> None:
    """The sibling, and it is the half that catches a sentence builder wired to the wrong row:
    the figures are compared against `brain.ops.limits`' own table rather than against a number
    typed here, so a ceiling repointed at another source's measured row fails."""
    measured = connector_ceiling(MEASURED)
    assert measured is not None
    said = ceiling_in_words(a_manifest(ceiling=MEASURED))

    assert f"{measured.per_minute:,}" in said
    if measured.per_day is not None:
        assert f"{measured.per_day:,}" in said
    assert ("can be raised" in said) is measured.raisable


def test_a_ceiling_with_no_verified_daily_figure_says_so_rather_than_reporting_one() -> None:
    """Deleting this leaves the branch for a source whose vendor states a rate a minute and no
    daily total untested, and a sentence that invented a daily figure there would be a number
    somebody sizes a backfill against with nothing behind it. The source is found by asking
    `brain.ops.limits` which of its rows has no daily figure, rather than by naming one, so the
    test follows the table."""
    without = next(one for one in SOURCE_CEILINGS if one.per_day is None)
    with_daily = next(one for one in SOURCE_CEILINGS if one.per_day is not None)

    said = ceiling_in_words(a_manifest(ceiling=without.name))
    assert "no daily figure" in said
    assert not any(str(n) in said for n in (with_daily.per_day, f"{with_daily.per_day:,}"))
    # And the sibling, so the branch is not satisfied by a sentence that always says this.
    assert "no daily figure" not in ceiling_in_words(a_manifest(ceiling=with_daily.name))


def test_a_manifest_naming_no_ceiling_and_one_naming_an_unmeasured_source_answer_alike() -> None:
    """Deleting this lets an empty ceiling name fall through to a different sentence from a name
    with no row behind it, and a reader would then be shown two states they can do nothing
    different about, one of which looks like a configuration error."""
    assert ceiling_in_words(a_manifest(ceiling="")) == ceiling_in_words(
        a_manifest(ceiling=UNMEASURED)
    )


def test_the_projected_count_is_the_fields_copied_and_is_bounded_by_the_cap() -> None:
    """Deleting this lets the column become the source's own schema size, or a share of it,
    either of which is a statement about somebody else's system that this install cannot make.
    The figure is what the twelve-field cap is written against, which is why it may be shown."""
    assert projected_field_count(a_manifest(fields=3)) == 3
    assert projected_field_count(a_manifest(fields=MAX_PROJECTED_FIELDS)) == MAX_PROJECTED_FIELDS

    row = trust_rows([a_registered(fields=3)], reader_of(unrestricted=True), now=NOW)[0]
    assert row.projected_fields == 3


def test_a_source_nothing_has_probed_carries_no_health_and_no_time() -> None:
    """Deleting this makes a source nobody has reached look identical to one answering normally,
    which is the row an operator scans past when something is wrong. The lifecycle state is
    carried beside it, because a connector can be enabled and unreachable."""
    registry = [a_registered("laravel", ConnectorState.DISABLED)]
    unprobed = trust_rows(registry, reader_of(unrestricted=True), now=NOW)[0]

    assert unprobed.health == ""
    assert unprobed.checked_at is None
    assert unprobed.lifecycle == "disabled"
    assert unprobed.serving is False

    probed = trust_rows(
        registry,
        reader_of(unrestricted=True),
        now=NOW,
        checked={
            "laravel": ConnectorHealth(
                connector="laravel", state=HealthState.DEGRADED, checked_at=NOW
            )
        },
    )[0]
    assert probed.health == "degraded"
    assert probed.checked_at == NOW


# --- the sentence tables ------------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(AccessMode))
def test_every_access_mode_has_a_sentence_written_for_a_person(mode: AccessMode) -> None:
    """Deleting this lets a member arrive with no sentence, and the row then renders whatever a
    mapping's default is, which for a two-member enumeration is a coin toss between "reads only"
    and "reads and writes" on the field that says what a connector may do to a client's system.
    The enumeration is the parameter, so a third member is covered the day it is added."""
    said = ACCESS_SAYS[mode]

    assert len(said.split()) > 8
    row = trust_rows([a_registered(mode=mode)], reader_of(unrestricted=True), now=NOW)[0]
    assert row.access == said


@pytest.mark.parametrize("claim", list(PermissionSync))
def test_every_permission_sync_claim_has_a_sentence_written_for_a_person(
    claim: PermissionSync,
) -> None:
    """Deleting this is the same failure on the field that says whether the source contributes a
    second permission check, where the wrong default is the flattering one. A manifest is
    refused if it claims more than its declarations support, so the claims reachable here are
    the ones a manifest can actually carry."""
    said = PERMISSION_SYNC_SAYS[claim]

    assert len(said.split()) > 8
    if claim is PermissionSync.NONE:
        row = trust_rows([a_registered()], reader_of(unrestricted=True), now=NOW)[0]
        assert row.permission_sync == said


def test_the_copy_policy_quotes_the_caps_the_platform_actually_enforces() -> None:
    """Deleting this lets the card that answers a client's auditor drift from the code: it says
    twelve fields and a hundred and twenty characters, and both figures are read out of
    `brain.core.projection` here rather than typed, so moving a cap moves the card."""
    text = " ".join(one.what + " " + one.why for one in COPY_POLICY)

    # The whole phrase and not the digits. `MAX_PROJECTED_FIELDS` is 12 and `MAX_LABEL_CHARS` is
    # 120, so a bare `"12" in text` is satisfied by the second figure and the card could stop
    # quoting the field cap entirely with this test green. Mutation testing found that.
    assert f"At most {MAX_PROJECTED_FIELDS} fields" in text
    assert f"up to {MAX_LABEL_CHARS} characters" in text
    assert {one.verdict for one in COPY_POLICY} == {PROJECTED, NEVER}
    # Both halves are present. A card listing only what is copied is an advertisement, and one
    # listing only what is never copied is not the question anybody asked.
    assert any(one.verdict == PROJECTED for one in COPY_POLICY)
    assert any(one.verdict == NEVER for one in COPY_POLICY)


def test_a_sentence_table_with_a_member_missing_is_refused() -> None:
    """Deleting this leaves the only guard in this module untested, and it is untestable through
    the module's own tables because both are complete: mutation testing turned the check into
    `if False` and nothing noticed. The tables are a parameter for exactly this reason, so an
    incomplete one can be handed in, and both the refusal and its sibling are asserted here."""
    complete = dict.fromkeys(AccessMode, "a sentence written for a person")
    assert_total(((complete, AccessMode),))

    short = dict(complete)
    del short[AccessMode.WRITE]
    with pytest.raises(ValueError, match=r"WRITE|write"):
        assert_total(((short, AccessMode),))

    # And the module's own tables really are the ones checked at import, so this test is about
    # the guard the module runs rather than about a function nothing calls.
    assert_total(((ACCESS_SAYS, AccessMode), (PERMISSION_SYNC_SAYS, PermissionSync)))


# ------------------------------------------------------------ what this install connected


def a_connection(name: str = "xero", *, digest: str | None = None) -> Connection:
    """One connection of a source the console can connect, pinned to what its settings build."""
    settings = {CONNECTABLE[name].settings[0].name: "11111111"} if name in CONNECTABLE else {}
    pinned = digest if digest is not None else manifest_digest(manifest_for(name, settings))
    return Connection(
        connector=name, settings=settings, digest=pinned, connected_by="u_admin", connected_at=NOW
    )


def a_reader(scope: Scope) -> EntitlementSet:
    return EntitlementSet(
        principal_id=READER, grants=(Grant(capability=CONNECTOR_READ, scope=scope),)
    )


HELD: Final = {
    "xero": Held(slot="connector_keys/xero", held=True, set_at=NOW),
    "hubspot": Held(slot="connector_keys/hubspot", held=False, set_at=None),
}


def test_a_reader_is_told_of_the_connections_their_grant_reaches_and_of_no_other() -> None:
    """The same two narrowings `trust_rows` uses, applied to connections before anything is built
    from them, so a reader holding one source is told of that one, a reader holding nothing is told
    of none, and a connection whose manifest cannot be built is narrowed exactly the same way.
    Delete this and the vault is asked about, and the list names, a source the reader holds nothing
    over. The positive case is the reader holding every source."""
    every = (
        a_connection("xero"),
        a_connection("hubspot"),
        a_connection("laravel", digest="0" * 64),
    )
    one = Scope(clauses=(Clause(field="connector", op=Op.EQ, value="laravel"),))

    assert [
        c.connector for c in admitted_connections(every, a_reader(Scope.unrestricted()), NOW)
    ] == [
        "xero",
        "hubspot",
        "laravel",
    ]
    assert [c.connector for c in admitted_connections(every, a_reader(one), NOW)] == ["laravel"]
    assert admitted_connections(every, EntitlementSet(principal_id=READER), NOW) == ()
    rows = connected_rows(every, a_reader(one), now=NOW, held=HELD, vault=VaultState.READY)
    assert [row.name for row in rows] == ["laravel"]


def test_a_connected_row_says_what_the_vault_holds_and_never_how_a_lease_is_borrowed() -> None:
    """The key of a connected source is not leased by anything, so the credential column says
    whether the vault holds it, from the vault's own metadata, and says nothing is known when the
    vault could not be asked. Delete this and the row says "borrowed as worker for the length of
    one call" about a key nothing borrows, or a silent vault reads as a missing key."""
    reader = a_reader(Scope.unrestricted())
    connections = (a_connection("xero"), a_connection("hubspot"))

    ready = {
        row.name: row
        for row in connected_rows(connections, reader, now=NOW, held=HELD, vault=VaultState.READY)
    }
    silent = connected_rows(connections, reader, now=NOW, held=HELD, vault=VaultState.UNREACHABLE)

    assert ready["xero"].trust is not None and ready["xero"].trust.credential == KEY_HELD
    assert (ready["xero"].key_held, ready["xero"].key_written_at) == (True, NOW)
    assert ready["hubspot"].trust is not None and ready["hubspot"].trust.credential == KEY_NOT_HELD
    assert ready["hubspot"].key_held is False
    for row in silent:
        assert (row.key_held, row.key_written_at) == (None, None)
        assert row.trust is not None
        assert row.trust.credential == KEY_NOT_KNOWN[VaultState.UNREACHABLE]
        assert "borrowed" not in row.trust.credential
    assert key_in_words(None, VaultState.READY) == KEY_NOT_KNOWN[VaultState.READY]


def test_a_connection_says_whether_what_it_declares_is_what_was_agreed_to() -> None:
    """The digest pinned at connect is compared with the manifest its settings build today, and a
    connection whose manifest cannot be built at all is still a row. Delete this and a release that
    changes a connector's tools shows the new declaration as the one agreed to, or a connection
    nobody can rebuild drops off the list while its key stays in the vault."""
    reader = a_reader(Scope.unrestricted())
    rows = {
        row.name: row
        for row in connected_rows(
            (
                a_connection("xero"),
                a_connection("hubspot", digest="f" * 64),
                a_connection("laravel", digest="0" * 64),
            ),
            reader,
            now=NOW,
            held=HELD,
            vault=VaultState.READY,
        )
    }

    assert (rows["xero"].pinned, rows["xero"].declaration) == (True, DECLARATION_AGREED)
    assert (rows["hubspot"].pinned, rows["hubspot"].declaration) == (False, DECLARATION_CHANGED)
    assert rows["hubspot"].trust is not None
    assert (rows["laravel"].trust, rows["laravel"].declaration) == (None, DECLARATION_UNREADABLE)
    assert rows["xero"].trust is not None
    assert rows["xero"].trust.lifecycle == ConnectorState.REGISTERED.value
    assert rows["xero"].trust.serving is False
