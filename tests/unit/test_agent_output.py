"""An agent's artifacts held to the rules that stop a produced file outliving its permissions.

An artifact is the one thing on an agent's workspace that is a copy rather than a view. A
composition, a capability row and a memory item are all read through the gate every time
somebody looks at them; a deck in a bucket was read through the gate once, at production, and
after that it is bytes. Every leaf claimed here is a consequence of that: what may go into the
file (M39.5.1.4), what the record of it must say (M39.5.1.2), how long it may sit there
(M39.5.1.3), who may fetch it back (M39.5.1.5), and what a reader may be told about the ones
that are not theirs (all of M39.5.2).

Real `EntitlementSet`s, a real `FieldPolicy`, real `AgentRecord`s and the real retention
tables throughout, because every one of these rules is about how two real modules meet. The
retention cases in particular are asserted against `brain.ops.retention`'s own horizons rather
than against numbers written here: a test that invented a thirty would pass on a day when the
payload window moved and the artifact outlived its trace.

Task ids: M39.5.1.1, M39.5.1.2, M39.5.1.4, M39.5.1.5
Task ids: M39.5.2.1, M39.5.2.2, M39.5.2.3, M39.5.2.4, M39.5.2.5
"""

from __future__ import annotations

import enum
import inspect
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.audit.ledger import ENT_HASH
from brain.console import agent_output as output_module
from brain.console.agent_output import (
    ARTIFACT_CAPABILITY,
    ARTIFACT_STORE,
    ARTIFACT_SURFACE,
    ARTIFACTS_SCREEN,
    NO_PROVENANCE,
    Artifact,
    ArtifactError,
    ArtifactInput,
    ArtifactKind,
    ArtifactState,
    Provenance,
    StorageSummary,
    archive,
    artifact_gaps,
    basis_over,
    may_download,
    may_see,
    producible_fields,
    provenance_for,
    record,
    retention_class_for,
    retention_enforcement_gaps,
    storage_summary,
    supersede,
    visible_artifacts,
)
from brain.console.screens import screen
from brain.console.workspace import SPEND_OF_OTHERS_SCREEN, Basis, basis_for, intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification, FieldPolicy, policy_from_rows
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.visibility import Visibility
from brain.ops.jobs import hidden_count_fields
from brain.ops.retention import DataClass, facts_for, horizon_for
from brain.ops.storage import bucket

AGENT = "support_triage"
READER = "p_reader"
OTHER = "p_colleague"
NOW = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)

#: A real policy, so a classification and a required capability are the pair the redactor
#: reads. One field is deliberately left unclassified, because withholding it is what
#: `FieldPolicy.rule_for` requires of every caller and it is the case a producer gets wrong.
#:
#: No field here is called `id`. `brain.core.redaction.RESERVED_KEYS` holds `id` as well as
#: `@id`, so a business field of that name is the record's own tag as far as the walker is
#: concerned and is kept whatever the policy says. Naming one here would make this fixture
#: quietly test the tag rather than the rule.
POLICY: FieldPolicy = policy_from_rows(
    [
        ("client", "reference", "read:client.name", Classification.INTERNAL),
        ("client", "display_name", "read:client.name", Classification.INTERNAL),
        ("client", "contract_value", "read:client.contract_value", Classification.RESTRICTED),
    ]
)

#: One client record as it exists before anything is withheld, which is what `compute_mask`
#: evaluates a grant's scope against.
ROW: dict[str, str] = {
    "@entity": "client",
    "@id": "c_1",
    "reference": "c_1",
    "display_name": "a client",
    "contract_value": "40000",
    "lifecycle": "active",
}


def holding(*capabilities: str, principal: str = READER) -> EntitlementSet:
    """A caller holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
        ),
    )


def holding_over_agent(agent_id: str, *, principal: str = READER) -> EntitlementSet:
    """A reader whose artifact grant is scoped to one agent, and who may open the console."""
    return EntitlementSet(
        principal_id=principal,
        grants=(
            Grant(
                capability=ARTIFACT_CAPABILITY,
                scope=Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value=agent_id),)),
            ),
            Grant(capability=Capability(value="read:console.existence"), scope=Scope(clauses=())),
        ),
    )


def a_record(*capabilities: str) -> AgentRecord:
    """One real agent whose ceiling admits exactly these capabilities."""
    return AgentRecord(
        agent_id=AGENT,
        display_name="Support triage",
        persona="Answers support questions in the house voice.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=READER),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by=READER,
    )


def an_artifact(
    artifact_id: str,
    *,
    agent_id: str = AGENT,
    caller: str = READER,
    kind: ArtifactKind = ArtifactKind.REPORT,
    at: datetime = NOW,
    data_class: DataClass = DataClass.BUSINESS_RECORD,
    bytes_stored: int = 100,
    provenance: Provenance = NO_PROVENANCE,
) -> Artifact:
    """One artifact, produced by a caller holding one capability."""
    return Artifact(
        artifact_id=artifact_id,
        agent_id=agent_id,
        kind=kind,
        run_id=f"run_{artifact_id}",
        agent_version="4.2.0",
        caller_id=caller,
        entitlement_hash=holding("read:client.name", principal=caller).ent_hash(),
        at=at,
        data_class=data_class,
        bytes_stored=bytes_stored,
        provenance=provenance,
    )


# --- the store: what an artifact is and what it must say (M39.5.1.1, M39.5.1.2) --------------


def test_every_produced_thing_the_breakdown_names_has_a_kind_to_record_it_under() -> None:
    """**M39.5.1.1.** "Every produced document, deck, report, export and image" is a claim
    about coverage, and coverage is only checkable against a closed vocabulary: a produced
    thing whose kind cannot be named is a produced thing that reaches a bucket with no run
    behind it, no caller attributed to it and no retention class decided for it.

    The five values are asserted as literals rather than against the enum's own members,
    because comparing `ArtifactKind` against itself is green for every set it could hold.

    Delete this and a sixth kind arrives as a string, or one of the five quietly leaves.
    """
    assert {one.value for one in ArtifactKind} == {
        "document",
        "deck",
        "report",
        "export",
        "image",
    }

    produced = [
        record(
            artifact_id=f"a_{one.value}",
            agent_id=AGENT,
            kind=one,
            run_id="run_1",
            agent_version="4.2.0",
            caller_id=READER,
            reach=holding("read:client.name"),
            at=NOW,
            inputs=[
                ArtifactInput(
                    label="ticket",
                    data_class=DataClass.BUSINESS_RECORD,
                    classification=Classification.INTERNAL,
                )
            ],
        )
        for one in ArtifactKind
    ]

    assert [one.kind for one in produced] == list(ArtifactKind)
    assert all(one.state is ArtifactState.CURRENT for one in produced)


def test_an_artifact_names_the_run_the_version_the_caller_and_the_reach_that_made_it() -> None:
    """**M39.5.1.2.** Five things, and each of them answers a question asked after the fact:
    which run produced this, which version of the agent, on whose behalf, at what reach, and
    when. A record missing any one of them is a file whose provenance is a guess.

    The entitlement hash is asserted against `brain.audit.ledger.ENT_HASH`, which is the
    grammar the ledger and `brain.ops.telemetry` both hold it to, rather than against this
    module's own pattern: a private spelling that drifted would admit a value neither of those
    would ever store.

    Delete this and an artifact can be recorded with a version reading "latest", which
    resolves to whatever is installed on the day somebody asks, and the record says nothing
    about what actually built the file."""
    reach = holding("read:client.name", "read:client.contract_value")

    made = record(
        artifact_id="a_1",
        agent_id=AGENT,
        kind=ArtifactKind.DECK,
        run_id="run_77",
        agent_version="4.2.0",
        caller_id=READER,
        reach=reach,
        at=NOW,
        inputs=[
            ArtifactInput(
                label="ticket",
                data_class=DataClass.BUSINESS_RECORD,
                classification=Classification.INTERNAL,
            )
        ],
        bytes_stored=2048,
    )

    assert (made.run_id, made.agent_version, made.caller_id, made.at) == (
        "run_77",
        "4.2.0",
        READER,
        NOW,
    )
    assert made.entitlement_hash == reach.ent_hash()
    assert ENT_HASH == r"^[0-9a-f]{32}$"
    assert output_module._ENT_HASH_RE.pattern == ENT_HASH

    with pytest.raises(ArtifactError, match="agent version"):
        an_artifact_with(agent_version="latest")
    with pytest.raises(ArtifactError, match="agent version"):
        an_artifact_with(agent_version="")
    with pytest.raises(ArtifactError, match="entitlement hash"):
        an_artifact_with(entitlement_hash="not-a-hash")
    with pytest.raises(ArtifactError, match="no run_id"):
        an_artifact_with(run_id="")
    with pytest.raises(ArtifactError, match="no timezone"):
        an_artifact_with(at=datetime(2026, 3, 10, 9, 0))


def an_artifact_with(
    *,
    run_id: str = "run_1",
    agent_version: str = "4.2.0",
    entitlement_hash: str | None = None,
    at: datetime = NOW,
    state: ArtifactState = ArtifactState.CURRENT,
    superseded_by: str = "",
) -> Artifact:
    """One artifact with a single field replaced, for the refusals above.

    Explicit parameters rather than a keyword splat, because a splat into a frozen dataclass
    is untyped at the call site and the refusals here are about the types as much as the
    values."""
    return Artifact(
        artifact_id="a_1",
        agent_id=AGENT,
        kind=ArtifactKind.REPORT,
        run_id=run_id,
        agent_version=agent_version,
        caller_id=READER,
        entitlement_hash=(
            holding("read:client.name").ent_hash() if entitlement_hash is None else entitlement_hash
        ),
        at=at,
        data_class=DataClass.BUSINESS_RECORD,
        state=state,
        superseded_by=superseded_by,
    )


def test_an_artifact_record_has_no_field_the_produced_bytes_could_arrive_in() -> None:
    """A record carrying its own content is a second copy of the file under the console's
    retention rather than the bucket's, where no field policy reaches it and no lifecycle rule
    removes it.

    Checked through `artifact_gaps` with a constructed type as well as against the real one,
    because a diagnostic that can only read the healthy class is one nobody has seen fire.

    Delete this and `Artifact.body` arrives with the next screen that wanted a preview."""

    @dataclass(frozen=True)
    class WithABody:
        artifact_id: str
        body: str

    assert artifact_gaps(artifact_type=WithABody) != ()
    assert any("body" in one for one in artifact_gaps(artifact_type=WithABody))
    assert artifact_gaps() == ()
    assert not {one.name for one in dataclass_fields(Artifact)} & {
        "body",
        "content",
        "payload",
        "document",
    }


def test_a_retention_window_arriving_on_the_artifact_row_itself_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Written because a mutation of this check survived the whole file.** `Artifact` carries
    none of the four field names it looks for, so the branch could not fire and could have been
    deleted with everything green.

    What it exists to refuse is a per-row retention window. The class decides how long an
    artifact is kept, decided from its inputs by `retention_class_for`, and
    `brain.ops.retention.THE_CLASS_DECIDES_AND_A_ROW_CANNOT_ARGUE` is that rule stated where it
    is enforced. A `keep_until` on the record is the row arguing: the file then outlives the
    class it was classified under, which is the disclosure `retention_enforcement_gaps` already
    says nothing is sweeping for.

    The class is patched rather than passed, and that is worth knowing rather than hiding:
    unlike the check above it, this one reads the module's own `Artifact` rather than the
    `artifact_type` parameter, so no argument reaches it. Patching the name it reads is how it
    becomes watchable, exactly as `brain.console.reads`' field scan is made watchable in
    `tests/unit/test_console_reads.py`.

    **The first version of this had to patch the module global**, because the check read
    `fields(Artifact)` while the parameter that exists to make it reachable sat unused thirty
    lines below its sibling. That was a defect rather than an untested guard: no caller could
    reach the branch at all. The module reads the parameter now and this hands one in.

    Delete this and a per-row window arrives with the next screen that wanted to pin one
    artifact for a client meeting."""
    assert artifact_gaps() == ()

    @dataclass(frozen=True)
    class WithAKeepUntil:
        artifact_id: str
        keep_until: datetime

    assert any("per-row window" in one for one in artifact_gaps(artifact_type=WithAKeepUntil))


# --- the store: how long it is kept (M39.5.1.3) ----------------------------------------------


def test_an_artifact_is_kept_under_its_most_sensitive_input_and_never_past_its_shortest() -> None:
    """**M39.5.1.3, and the case the leaf's own wording misses.** The most sensitive input is
    the right one to classify by. It is not always the shortest-lived one, and when it is not,
    classifying by sensitivity alone keeps the artifact after the run it was drawn from is
    gone: the file becomes the oldest copy of that content in the estate with nothing pointing
    at it.

    Four cases, and the third is the discriminating one. A restricted export beside an
    internal payload is the arrangement where the sensitive input has the longer window, so a
    function taking the most sensitive input alone answers `export` and this answers
    `payload`.

    The windows are read from `brain.ops.retention.horizon_for` rather than written here, so
    the assertion stays true on the day one of them moves, and the relation between them is
    asserted first: two classes with the same window would make the case below vacuous.

    The last two assertions are about `record` rather than about the function: a producer
    that chose its own class would be a producer choosing how long its output is kept, which
    is `brain.ops.retention.THE_CLASS_DECIDES_AND_A_ROW_CANNOT_ARGUE` at the point of
    production, so the class on the record has to be this function's answer and not a
    parameter.

    Delete this and an artifact built from a payload is kept for as long as the business
    record beside it, which is for ever."""
    payload_days = horizon_for(DataClass.PAYLOAD).days
    export_days = horizon_for(DataClass.EXPORT).days
    assert payload_days is not None
    assert export_days is not None
    assert payload_days < export_days
    assert horizon_for(DataClass.BUSINESS_RECORD).days is None

    restricted_record = ArtifactInput(
        label="contract",
        data_class=DataClass.BUSINESS_RECORD,
        classification=Classification.RESTRICTED,
    )
    internal_payload = ArtifactInput(
        label="answer",
        data_class=DataClass.PAYLOAD,
        classification=Classification.INTERNAL,
    )
    restricted_export = ArtifactInput(
        label="handover",
        data_class=DataClass.EXPORT,
        classification=Classification.RESTRICTED,
    )

    internal_learned = ArtifactInput(
        label="memory",
        data_class=DataClass.LEARNED,
        classification=Classification.INTERNAL,
    )

    # The plain case: one input, and its own class is the answer.
    assert retention_class_for([restricted_record]) is DataClass.BUSINESS_RECORD
    # A clockless class beside one with a window: the window wins.
    assert retention_class_for([restricted_record, internal_payload]) is DataClass.PAYLOAD
    # The discriminating case: the sensitive input is the longer-lived one.
    assert retention_class_for([restricted_export, internal_payload]) is DataClass.PAYLOAD
    # And where no input has a clock, sensitivity is the only thing deciding. This is the
    # case that proves the first half of the rule is doing anything at all: with a window
    # anywhere in the set the narrowing step reaches the same answer whichever input the
    # sort put first, so the sensitivity ordering is only observable between clockless
    # classes.
    assert retention_class_for([restricted_record, internal_learned]) is DataClass.BUSINESS_RECORD
    assert retention_class_for([internal_learned, restricted_record]) is DataClass.BUSINESS_RECORD

    # And the class a producer records is this answer rather than one it chose.
    made = record(
        artifact_id="a_1",
        agent_id=AGENT,
        kind=ArtifactKind.REPORT,
        run_id="run_1",
        agent_version="4.2.0",
        caller_id=READER,
        reach=holding("read:client.name"),
        at=NOW,
        inputs=[restricted_record, internal_payload],
    )

    assert made.data_class is DataClass.PAYLOAD
    assert made.expiry() == NOW + timedelta(days=payload_days)
    assert "data_class" not in inspect.signature(record).parameters
    # And nothing is narrowed when the sensitive input is already the shortest.
    assert (
        retention_class_for(
            [
                ArtifactInput(
                    label="answer",
                    data_class=DataClass.PAYLOAD,
                    classification=Classification.RESTRICTED,
                ),
                ArtifactInput(
                    label="handover",
                    data_class=DataClass.EXPORT,
                    classification=Classification.INTERNAL,
                ),
            ]
        )
        is DataClass.PAYLOAD
    )


def test_two_runs_over_the_same_inputs_choose_the_same_class_whatever_order_they_arrive() -> None:
    """A tie on sensitivity broken by whichever input the caller iterated first is a retention
    class that depends on a loop order, which means two artifacts built from the same material
    are kept for different lengths of time and nothing anywhere says why.

    **Both inputs are clockless on purpose.** A tie between two classes with windows would
    converge anyway, because the narrowing step picks the shorter one whatever order the sort
    left them in, and the test would be green with the sort deleted. Two classes that age out
    of nothing leave the sort as the only thing deciding, and the answer is asserted rather
    than only compared against itself.

    The positive half is the empty case, refused rather than defaulted: a lookup with a
    default would hand an artifact built from nothing the longest window in the system.

    Delete this and the tie-break disappears, and the failure only shows up as a bill."""
    first = ArtifactInput(
        label="alpha", data_class=DataClass.LEARNED, classification=Classification.CONFIDENTIAL
    )
    second = ArtifactInput(
        label="beta",
        data_class=DataClass.BUSINESS_RECORD,
        classification=Classification.CONFIDENTIAL,
    )
    assert horizon_for(DataClass.LEARNED).days is None
    assert horizon_for(DataClass.BUSINESS_RECORD).days is None

    assert retention_class_for([first, second]) is DataClass.LEARNED
    assert retention_class_for([second, first]) is DataClass.LEARNED

    with pytest.raises(ArtifactError, match="no declared inputs"):
        retention_class_for([])


def test_an_input_with_no_label_is_refused() -> None:
    """**Written because a mutation of this guard survived the whole file.** Every input built
    anywhere here was labelled, so the refusal could be deleted with nothing red.

    The label is what the run has to say which input was which, and two things read it. A
    provenance panel names it, and a sweep looking for where an artifact's material came from
    matches on it. Less obviously, it is the tie-break in `retention_class_for`: the test above
    asserts that two runs over the same inputs in a different order are kept for the same
    length of time, and the only thing making that true is the sort on this field. Unlabelled
    inputs all compare equal, the sort collapses to the caller's iteration order, and the
    property that test pins is gone while that test stays green.

    Empty and blank both, because an input assembled from anything that trims nothing arrives
    with a space where the name should be.

    Delete this and a produced file records that something fed it and cannot say what."""
    for missing in ("", "   "):
        with pytest.raises(ArtifactError, match="no label"):
            ArtifactInput(
                label=missing,
                data_class=DataClass.BUSINESS_RECORD,
                classification=Classification.INTERNAL,
            )

    assert (
        ArtifactInput(
            label="ticket",
            data_class=DataClass.BUSINESS_RECORD,
            classification=Classification.INTERNAL,
        ).label
        == "ticket"
    )


def test_an_artifact_occupying_a_negative_amount_of_the_bucket_is_refused() -> None:
    """**Written because a mutation of this guard survived the whole file.** Every artifact
    built here carried a positive size, so the refusal could be deleted with nothing red.

    `bytes_stored` is the one field on this surface that is added up: `storage_summary` sums it
    over the rows a reader may see, and the whole construction of that figure is that it counts
    what was shown and can therefore say nothing about what was not. A negative row breaks that
    in the only way it can be broken from inside, because the total then stops being a count of
    the visible rows: adding a row makes the figure smaller, which is a subtraction reaching
    the screen through the arithmetic rather than through a field.

    Zero is the sibling and is a real state. An artifact whose bytes have already gone from the
    bucket still has a record, and refusing that would be refusing the row that explains an
    answer somebody was given.

    Delete this and a storage figure can be talked downwards by a row."""
    with pytest.raises(ArtifactError, match="negative amount"):
        an_artifact("a_1", bytes_stored=-1)

    assert an_artifact("a_1", bytes_stored=0).bytes_stored == 0


def test_the_bucket_artifacts_live_in_has_no_lifecycle_rule_and_this_surface_says_so() -> None:
    """The half of M39.5.1.3 that is decided here and enforced nowhere. A retention class is
    per artifact and a bucket has exactly one lifecycle rule, which is why
    `brain.ops.retention.store_gaps` insists a bucket is claimed by exactly one store. So an
    artifact classified at the payload window sits in a bucket that keeps everything until
    somebody deletes it, and only a per-object sweep could apply the difference.

    Reported by its own function rather than by `artifact_gaps`, because a deployment check
    that is red on the day it lands is a check somebody switches off.

    Delete this and M39.5.1.3 reads as done while the bytes are kept for ever."""
    buckets = facts_for(ARTIFACT_STORE).buckets

    assert buckets
    assert all(bucket(name).retention_days is None for name in buckets)
    assert retention_enforcement_gaps() != ()
    assert all("per-object sweep" in one for one in retention_enforcement_gaps())


# --- the store: redaction at production time (M39.5.1.4) -------------------------------------


def test_the_fields_that_reach_an_artifact_are_the_runs_and_never_the_callers() -> None:
    """**M39.5.1.4.** An artifact never exceeds its caller, and the way to guarantee that is
    to build it at the run's reach rather than the caller's: the ceiling can only narrow, so
    what reaches the file is a subset of what the person asking could have read on the record
    screen.

    Three cases in one. A caller holding a capability the agent's ceiling excludes does not
    get that field in the file, which is the whole leaf. A field the policy does not classify
    is dropped whatever anybody holds, because `FieldPolicy.rule_for` returns `None` for the
    absence of a decision rather than the absence of a restriction. And the order is the
    record's own, so a report's columns are where its author put them.

    Delete this and a deck built for somebody who may read a contract value contains it,
    through an agent that was never allowed near one."""
    caller = holding("read:client.name", "read:client.contract_value")
    narrow_agent = a_record("read:client.name")
    wide_agent = a_record("read:client.name", "read:client.contract_value")
    present = ["@entity", "@id", "contract_value", "reference", "display_name", "lifecycle"]

    through_narrow = producible_fields(
        "client", present, caller=caller, agent=narrow_agent, policy=POLICY, row=ROW
    )
    through_wide = producible_fields(
        "client", present, caller=caller, agent=wide_agent, policy=POLICY, row=ROW
    )

    assert through_narrow == ("reference", "display_name")
    assert through_wide == ("contract_value", "reference", "display_name")
    assert set(through_narrow) < set(through_wide)
    assert "lifecycle" not in through_wide
    assert not set(through_wide) & {"@entity", "@id"}


def test_an_artifact_built_for_somebody_holding_nothing_carries_nothing() -> None:
    """The floor, and the positive case's mirror. A run whose caller holds no grant over any
    field of the entity produces a file with no columns in it, rather than a file with the
    entity's columns and a lock rendered beside them: a lock is a rendering of a record on a
    screen, and there is nothing to render in a bucket.

    Delete this and an empty reach falls through to the manifest's field list."""
    assert (
        producible_fields(
            "client",
            ["reference", "display_name"],
            caller=holding("read:ticket.internal_note"),
            agent=a_record("read:client.name"),
            policy=POLICY,
            row=ROW,
        )
        == ()
    )


# --- the store: re-download (M39.5.1.5) ------------------------------------------------------


def test_a_download_is_checked_against_the_requester_now_and_never_against_the_record() -> None:
    """**M39.5.1.5.** The link is not the authority and neither is the hash on the record. An
    artifact produced at a wide reach is fetched by whoever asks for it, at whatever they hold
    at the moment they ask, and the producing run's entitlement hash is provenance rather than
    permission.

    The discriminating case is the third: a requester holding exactly the grants the producer
    held, whose hash therefore matches the record's, and who still gets nothing because they
    hold no artifact grant and it is not their artifact. A check written against the hash
    would let them through and would look correct doing it.

    Delete this and a signed URL becomes a grant anybody can forward."""
    produced_at = holding("read:client.name", "read:client.contract_value", principal=OTHER)
    made = record(
        artifact_id="a_1",
        agent_id=AGENT,
        kind=ArtifactKind.EXPORT,
        run_id="run_1",
        agent_version="4.2.0",
        caller_id=OTHER,
        reach=produced_at,
        at=NOW,
        inputs=[
            ArtifactInput(
                label="ticket",
                data_class=DataClass.BUSINESS_RECORD,
                classification=Classification.INTERNAL,
            )
        ],
    )
    same_grants = holding("read:client.name", "read:client.contract_value", principal="p_stranger")

    assert may_download(made, produced_at, NOW) is True
    assert may_download(made, holding_over_agent(AGENT), NOW) is True
    assert same_grants.ent_hash() == made.entitlement_hash
    assert may_download(made, same_grants, NOW) is False
    assert may_download(made, holding(principal="p_nobody"), NOW) is False


def test_an_artifact_past_its_horizon_is_not_downloadable_by_the_person_who_made_it() -> None:
    """Retention is not a permission and it outranks one. An artifact whose class has expired
    is gone from the store, so a link to it resolves to nothing whoever follows it, and the
    surface must say so before it says anything about grants.

    The window is `brain.ops.retention`'s own rather than a number here, and the positive half
    is the same artifact one day inside it, so this is not passing because everything expires.

    Delete this and the console offers a download of a file the sweep removed."""
    window = horizon_for(DataClass.PAYLOAD).days
    assert window is not None
    made = an_artifact("a_1", data_class=DataClass.PAYLOAD, at=NOW)
    mine = holding(principal=READER)

    assert may_download(made, mine, NOW + timedelta(days=window - 1)) is True
    assert may_download(made, mine, NOW + timedelta(days=window)) is False
    assert may_download(made, holding_over_agent(AGENT), NOW + timedelta(days=window)) is False


def test_the_download_check_has_no_parameter_a_link_could_arrive_through() -> None:
    """The structural half. A rule that a download is re-checked holds until somebody adds a
    convenience taking a signed URL and short-circuiting on it, at which point the check is
    whatever the link says.

    Asserted through `artifact_gaps` against a constructed signature as well as against the
    real one, following `brain.console.workspace_capabilities.capabilities_gaps`: a scan that
    can only be pointed at code known to be clean is a scan nobody has seen produce a finding.

    Delete this and `may_download(artifact, requester, now, token=...)` reads as an
    optimisation."""

    def with_a_token(one: object, requester: object, now: object, token: str = "") -> bool:
        return bool(token)

    assert artifact_gaps(download=with_a_token) != ()
    assert any("token" in one for one in artifact_gaps(download=with_a_token))
    assert artifact_gaps() == ()
    assert set(inspect.signature(may_download).parameters) == {"one", "requester", "now"}


# --- the surface: the listing (M39.5.2.1) ----------------------------------------------------


def test_the_artifacts_tab_lists_what_this_agent_produced_newest_first() -> None:
    """**M39.5.2.1.** Newest first, this agent only, and stable. The order is the feature: an
    artifacts tab is read to find the thing that was just made.

    Ties are broken by id so two readings of an unchanged store are the same list, which is
    what makes a diff between two mornings readable, and it is asserted with two artifacts
    written at the same instant rather than left to chance.

    Delete this and the list arrives in whatever order the store iterated, and an agent's tab
    shows another agent's output."""
    older = an_artifact("a_older", at=NOW - timedelta(days=2))
    newer = an_artifact("a_newer", at=NOW - timedelta(days=1))
    tied = an_artifact("a_tied", at=NOW - timedelta(days=1))
    elsewhere = an_artifact("a_other_agent", agent_id="another_agent")

    listed = visible_artifacts(
        [older, elsewhere, newer, tied], holding(principal=READER), NOW, agent_id=AGENT
    )

    assert [one.artifact_id for one in listed] == ["a_tied", "a_newer", "a_older"]


def test_an_artifact_somebody_else_produced_is_absent_rather_than_hidden() -> None:
    """The strong form of the rule, and the only version worth having: the list a reader gets
    is byte for byte the list they would get from a store that never held the other artifacts.
    A placeholder, a gap in an ordering, or a count that differs by one all reconstruct exactly
    what was withheld.

    `brain.ops.jobs.visible_dead_letters` asserts the same property in the same words, and it
    is the shape this surface has to match because the two are read on the same console.

    Delete this and a greyed-out row appears, and it names a colleague."""
    mine = an_artifact("a_mine", caller=READER)
    theirs = an_artifact("a_theirs", caller=OTHER)
    reader = holding(principal=READER)

    with_theirs = visible_artifacts([mine, theirs], reader, NOW, agent_id=AGENT)
    without_theirs = visible_artifacts([mine], reader, NOW, agent_id=AGENT)

    assert with_theirs == without_theirs
    assert [one.artifact_id for one in with_theirs] == ["a_mine"]
    # The positive half: a reader holding an artifact grant over this agent sees both, so the
    # filter is a narrowing rather than a refusal of everything that is not the reader's.
    granted = visible_artifacts([mine, theirs], holding_over_agent(AGENT), NOW, agent_id=AGENT)
    assert len(granted) == 2


def test_an_artifact_that_has_aged_out_is_indistinguishable_from_one_never_produced() -> None:
    """`brain.ops.retention` decides when an artifact stops existing, and the surface has to
    agree without saying so. A row reading expired tells the reader this agent produced
    something they can no longer have, and beside a filter by caller it tells them who
    produced it.

    The ordering is the mechanism and is asserted directly: expiring happens before the
    filters, so no filter can produce a count that moved on the day a horizon passed.

    Delete this and the tab grows a greyed-out history of everything the sweep took."""
    window = horizon_for(DataClass.PAYLOAD).days
    assert window is not None
    gone = an_artifact("a_gone", data_class=DataClass.PAYLOAD, at=NOW - timedelta(days=window))
    kept = an_artifact("a_kept", data_class=DataClass.PAYLOAD, at=NOW)
    reader = holding(principal=READER)

    today = visible_artifacts([gone, kept], reader, NOW, agent_id=AGENT)
    yesterday = visible_artifacts([gone, kept], reader, NOW - timedelta(days=1), agent_id=AGENT)

    assert today == visible_artifacts([kept], reader, NOW, agent_id=AGENT)
    assert [one.artifact_id for one in today] == ["a_kept"]
    # And it was there yesterday, so this is a horizon rather than a filter that never matches.
    assert len(yesterday) == 2


def test_a_listing_cannot_be_asked_for_without_naming_an_agent() -> None:
    """**M39.5.2.1 read as a shape.** A listing with an optional agent filter is the global
    pile with a filter on it, and the filter is the part that gets omitted. `agent_id` is a
    required keyword, so the estate-wide list is not a thing this module can produce.

    Delete this and a default of "" arrives with the next caller who found it convenient."""
    parameter = inspect.signature(visible_artifacts).parameters["agent_id"]

    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


# --- the surface: filters (M39.5.2.2) --------------------------------------------------------


def test_a_filter_runs_after_the_visibility_check_and_never_before() -> None:
    """**M39.5.2.2, and the reason the filters are arguments rather than a second function.**
    Filtering by a caller the reader may not see must answer exactly what filtering by a
    caller who produced nothing answers, and that is only true if the visibility check has
    already happened.

    The positive half is the same call by a reader who does hold the grant, which returns the
    colleague's row: the filter works, and it is the visibility that decides.

    Delete this and `filter_by(artifacts, caller=...)` appears, gets called first somewhere,
    and the artifacts tab becomes a way of asking who has been using the agent."""
    mine = an_artifact("a_mine", caller=READER, kind=ArtifactKind.REPORT)
    theirs = an_artifact("a_theirs", caller=OTHER, kind=ArtifactKind.DECK)
    reader = holding(principal=READER)

    unseen_colleague = visible_artifacts(
        [mine, theirs], reader, NOW, agent_id=AGENT, caller_id=OTHER
    )
    nobody_at_all = visible_artifacts(
        [mine, theirs], reader, NOW, agent_id=AGENT, caller_id="p_never_used_it"
    )

    assert unseen_colleague == nobody_at_all == ()
    assert [
        one.artifact_id
        for one in visible_artifacts(
            [mine, theirs], holding_over_agent(AGENT), NOW, agent_id=AGENT, caller_id=OTHER
        )
    ] == ["a_theirs"]


def test_the_type_and_date_filters_narrow_within_what_the_reader_may_see() -> None:
    """The other two filters M39.5.2.2 asks for, proved to work rather than merely to be
    accepted. A filter that silently ignored its argument would pass every test written about
    what it must not disclose.

    Delete this and `kinds=` becomes decoration."""
    deck = an_artifact("a_deck", kind=ArtifactKind.DECK, at=NOW - timedelta(days=5))
    report = an_artifact("a_report", kind=ArtifactKind.REPORT, at=NOW - timedelta(days=1))
    reader = holding(principal=READER)
    everything = [deck, report]

    only_decks = visible_artifacts(
        everything, reader, NOW, agent_id=AGENT, kinds=[ArtifactKind.DECK]
    )

    assert [one.artifact_id for one in only_decks] == ["a_deck"]
    assert [
        one.artifact_id
        for one in visible_artifacts(
            everything, reader, NOW, agent_id=AGENT, since=NOW - timedelta(days=2)
        )
    ] == ["a_report"]
    assert [
        one.artifact_id
        for one in visible_artifacts(
            everything, reader, NOW, agent_id=AGENT, until=NOW - timedelta(days=2)
        )
    ] == ["a_deck"]
    assert len(visible_artifacts(everything, reader, NOW, agent_id=AGENT)) == 2


# --- the surface: provenance (M39.5.2.3) -----------------------------------------------------


def test_the_provenance_panel_is_narrowed_to_what_this_reader_can_already_see() -> None:
    """**M39.5.2.3.** What fed an artifact is a description of the producing run's access,
    printed on a panel read by somebody else. A source named there is a source the reader
    learns is installed here; a knowledge item named there is a document they learn somebody
    holds.

    The order is the run's own, so a reader tracing an unexpected figure follows the sequence
    the artifact was built in, and there is no remainder: six sources of which two are visible
    show two and say nothing about four.

    Delete this and the panel prints the manifest to whoever can open the tab."""
    made = an_artifact(
        "a_1",
        provenance=Provenance(
            sources=("xero", "freshdesk", "hubspot"),
            knowledge_items=("k_house_style", "k_pricing"),
        ),
    )

    narrowed = provenance_for(
        made, visible_sources=["freshdesk", "xero"], visible_items=["k_house_style"]
    )

    assert narrowed.sources == ("xero", "freshdesk")
    assert narrowed.knowledge_items == ("k_house_style",)
    assert {one.name for one in dataclass_fields(Provenance)} == {"sources", "knowledge_items"}
    # The floor: a reader who can see none of it gets an empty panel rather than a count.
    assert provenance_for(made, visible_sources=[], visible_items=[]) == Provenance()


# --- the surface: supersede and archive (M39.5.2.4) ------------------------------------------


def test_an_artifact_is_superseded_or_archived_and_never_removed() -> None:
    """**M39.5.2.4.** An artifact is the evidence for something somebody was told, so deleting
    the version that was sent leaves a decision on file whose basis is gone.

    Supersede points at a replacement and archive points at nothing, which is
    `brain.knowledge.item.KnowledgeState`'s distinction: a reader who finds nothing must not
    be told a successor exists. Both keep the row, and the constructor refuses a state and a
    successor that disagree, so a screen cannot render a link to a replacement that was never
    named.

    Delete this and archive becomes delete, because it is one line shorter."""
    made = an_artifact("a_1")

    replaced = supersede(made, by="a_2")
    withdrawn = archive(made)

    assert replaced.state is ArtifactState.SUPERSEDED
    assert replaced.superseded_by == "a_2"
    assert withdrawn.state is ArtifactState.ARCHIVED
    assert withdrawn.superseded_by == ""
    assert (replaced.artifact_id, replaced.run_id, replaced.at) == (
        made.artifact_id,
        made.run_id,
        made.at,
    )

    with pytest.raises(ArtifactError, match="one of those is not true"):
        an_artifact_with(state=ArtifactState.SUPERSEDED)
    with pytest.raises(ArtifactError, match="one of those is not true"):
        an_artifact_with(superseded_by="a_2")


def test_no_state_on_this_surface_means_the_artifact_is_gone() -> None:
    """The vocabulary half. A `DELETED` member arrives from somebody making a screen tidier,
    and the row it hides is the one an explanation needed a quarter later.

    Checked with a constructed enum as well as the real one, so the refusal has been seen to
    fire rather than merely never having been provoked.

    Delete this and the third state grows a fourth."""

    class WithADeletion(enum.StrEnum):
        CURRENT = "current"
        DELETED = "deleted"

    assert {one.value for one in ArtifactState} == {"current", "superseded", "archived"}
    assert artifact_gaps(states=tuple(WithADeletion)) != ()
    assert artifact_gaps() == ()
    assert not [name for name in dir(output_module) if name in {"delete", "remove", "purge"}]


def test_superseding_twice_and_archiving_twice_are_both_refused() -> None:
    """Two histories that read as though something happened twice. An artifact with two
    successors leaves a reader following whichever the renderer trusted, and a second
    withdrawal puts an act in a history that only had one.

    The positive half is above: both operations work once. This is the sibling that stops the
    guard being satisfied by a function that refuses everything.

    Delete this and a retry loop rewrites the row."""
    made = an_artifact("a_1")

    with pytest.raises(ArtifactError, match="already superseded"):
        supersede(supersede(made, by="a_2"), by="a_3")
    with pytest.raises(ArtifactError, match="already archived"):
        archive(archive(made))
    with pytest.raises(ArtifactError, match="superseded by nothing"):
        supersede(made, by="  ")
    with pytest.raises(ArtifactError, match="cannot supersede itself"):
        supersede(made, by="a_1")


# --- the surface: count and storage (M39.5.2.5) ----------------------------------------------


def test_the_storage_figures_are_computed_over_the_rows_the_reader_may_see() -> None:
    """**M39.5.2.5.** The summary of an agent holding other people's output is identical to
    the summary of an agent that never produced any. Filtering happens first and the
    arithmetic happens on what is left, so there is no point in the function at which a total
    exists to be returned by accident.

    The soonest horizon is the "against the retention policy" half, and it is read from the
    artifact's own class rather than computed here, so a figure and the sweep that acts on it
    cannot disagree.

    **The wider basis is the discriminating case and it is asked of a reader who holds
    nothing.** On the narrower basis the arithmetic filters by principal anyway, so a summary
    computed over every row in the store would produce the same figures and a mutation
    removing the visibility filter survived. Asked at `Basis.EVERYONE` by somebody with no
    grant, the filter is the only thing standing between the reader and a colleague's
    storage, and an artifact of another agent tests the other half of the same call.

    Delete this and the tab reports the bucket's size, which is everybody's."""
    window = horizon_for(DataClass.PAYLOAD).days
    assert window is not None
    mine = an_artifact("a_mine", caller=READER, bytes_stored=100, data_class=DataClass.PAYLOAD)
    theirs = an_artifact("a_theirs", caller=OTHER, bytes_stored=900)
    elsewhere = an_artifact("a_elsewhere", agent_id="another_agent", caller=READER, bytes_stored=7)
    reader = holding(principal=READER)

    with_theirs = storage_summary(AGENT, [mine, theirs], reader, basis=Basis.OWN, now=NOW)
    without_theirs = storage_summary(AGENT, [mine], reader, basis=Basis.OWN, now=NOW)
    ungranted_wide = storage_summary(
        AGENT, [mine, theirs, elsewhere], reader, basis=Basis.EVERYONE, now=NOW
    )

    assert with_theirs == without_theirs
    assert (with_theirs.count, with_theirs.bytes_stored) == (1, 100)
    assert with_theirs.oldest_at == NOW
    assert with_theirs.expires_soonest_at == NOW + timedelta(days=window)
    assert (ungranted_wide.count, ungranted_wide.bytes_stored) == (1, 100)


def test_the_basis_decides_whose_storage_the_figure_is_and_the_label_says_which() -> None:
    """A figure whose meaning is unstated is read as the total, which is
    `brain.console.workspace.Headline`'s argument: a reader shown their own storage with no
    label reads it as the agent's.

    Both bases are asserted over the same rows, so this is a narrowing rather than two
    different queries, and the label is asserted alongside the figure because the number
    without it is the disclosure.

    Delete this and the wider basis becomes the default, and the count on a shared agent's tab
    is a statement about how much the department has been producing."""
    mine = an_artifact("a_mine", caller=READER, bytes_stored=100)
    theirs = an_artifact("a_theirs", caller=OTHER, bytes_stored=900)
    reader = holding_over_agent(AGENT)
    rows = [mine, theirs]

    everyone = storage_summary(AGENT, rows, reader, basis=Basis.EVERYONE, now=NOW)
    own = storage_summary(AGENT, rows, reader, basis=Basis.OWN, now=NOW)

    assert (everyone.count, everyone.bytes_stored, everyone.basis) == (2, 1000, Basis.EVERYONE)
    assert (own.count, own.bytes_stored, own.basis) == (1, 100, Basis.OWN)


def test_no_figure_on_this_surface_could_be_a_count_of_what_was_withheld() -> None:
    """The field-name check `brain.ops.jobs.hidden_count_fields` exists for, asked of every
    type this surface hands a reader. The failure arrives as a field somebody adds to make a
    screen more useful, and it arrives with one of a small set of names on it.

    The field list is pinned as a literal as well, because `hidden_count_fields` only knows
    the names it was told about and a new one called `not_shown` would pass it.

    **And the check is exercised with a type that has one**, which the first version of this
    test did not do: asking `artifact_gaps` about a clean surface passes whether or not it
    asks `hidden_count_fields` anything, and a mutation removing that call survived exactly
    because of it.

    Delete this and `StorageSummary.total` reads like an improvement."""

    @dataclass(frozen=True)
    class WithATotal:
        count: int
        total: int

    assert hidden_count_fields(ARTIFACT_SURFACE) == ()
    assert {one.name for one in dataclass_fields(StorageSummary)} == {
        "agent_id",
        "basis",
        "count",
        "bytes_stored",
        "oldest_at",
        "expires_soonest_at",
    }
    assert any("not shown" in one for one in artifact_gaps(surface=[WithATotal]))
    assert artifact_gaps() == ()


# --- the rules this surface shares with its siblings -----------------------------------------


def test_this_surface_intersects_no_entitlement_sets_of_its_own() -> None:
    """The invariant's structural half, the same check `brain.console.workspace` and
    `brain.console.workspace_capabilities` make of themselves. Every reach used here arrives
    as an argument or comes from `run_reach`, which is the console's one call into
    `EntitlementSet.intersect`.

    Delete this and a helper on the artifacts tab starts narrowing a reach, and the copy that
    is subtly wrong is the one deciding what went into a file that has already been sent."""
    assert intersections_in(inspect.getsource(output_module)) == ()


def test_the_basis_helper_is_the_workspaces_own_rule_with_the_screen_as_a_parameter() -> None:
    """`brain.console.workspace.basis_for` is this rule pinned to the budget screen. Pointed
    at that same screen, `basis_over` must answer identically for every reach, or there are
    two rules on one console and the permissive one wins the day they disagree.

    Asserted over three reaches, including the one that holds the capability and not the
    plane, because that is where a check written as one condition rather than two diverges.

    Delete this and the two drift, and the front page shows figures the budget screen would
    have refused."""
    for reach in (
        holding(),
        holding("read:budget"),
        holding("read:budget", "read:console.configuration"),
        holding("read:console.content"),
    ):
        assert basis_over(SPEND_OF_OTHERS_SCREEN, reach) is basis_for(reach)


def test_the_artifacts_grant_is_the_screens_own_and_not_a_second_one() -> None:
    """A capability spelled again in a module is a grant an administrator reviewing the
    screen registry would never see, and the two spellings stop agreeing the day one moves.

    `artifact_gaps` is given a read requiring something else, so the refusal has been seen to
    fire, and the real registry entry is asserted alongside it.

    Delete this and `read:artifact.download` appears, granted by nobody and checked by
    this."""
    assert screen(ARTIFACTS_SCREEN).read.requires == ARTIFACT_CAPABILITY
    assert ARTIFACT_CAPABILITY.value == "read:artifact"
    assert artifact_gaps(reads=[screen(ARTIFACTS_SCREEN).read]) == ()
    assert artifact_gaps(reads=[screen("exports").read]) != ()


def test_a_reader_holding_the_grant_sees_the_artifact_and_one_holding_neither_does_not() -> None:
    """`may_see`'s two branches, each on its own, because a function returning True for its
    own caller would pass every test about what it hides.

    The scoped grant is the interesting one: it matches this agent's rows and not another
    agent's, which is what makes an artifact grant reviewable rather than total.

    Delete this and the scope stops being evaluated, and an artifact grant over one agent
    reads every agent's output."""
    here = an_artifact("a_1", agent_id=AGENT, caller=OTHER)
    elsewhere = an_artifact("a_2", agent_id="another_agent", caller=OTHER)
    scoped = holding_over_agent(AGENT)

    assert may_see(here, scoped) is True
    assert may_see(elsewhere, scoped) is False
    assert may_see(here, holding(principal=OTHER)) is True
    assert may_see(here, holding(principal=READER)) is False
