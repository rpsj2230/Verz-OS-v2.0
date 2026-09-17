"""The sequence a chunk takes to become a vector, and the list of what nothing runs yet.

Three of these are written a particular way and the reason is worth reading before the rest.

**The wiring list is asserted against the source, not against itself.** `EMBED_PATH` is a
declaration: a symbol, a sentence, and whether anything calls it. A test comparing that list
against the sentences in it would be green whatever the code did, which is exactly the failure
the list exists to prevent one layer down. So every entry is put to
`brain.ops.controls.call_sites`, which reads `ast.Call` nodes out of `src/brain`, and the
disagreement is asserted in both directions: a step declared as an orphan that has gained a
caller is a finding, and so is a step declared as wired that has lost one.

**The width refusal is asserted by moving the column, not by moving the constant.** Asserting
that `embed_units` refuses when `dimension_gaps` returns something, with `dimension_gaps`
patched, would test the `if`. Patching the column's declared width instead exercises the real
comparison and the real call site, and the service's call count is what says the refusal
happened before anything left the process rather than after.

**The service counts its calls.** A run that refused and a run that sent one batch and threw
the answer away produce the same `EmbedRun` fields, and only the call count separates them.

Task ids: none
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from brain.install import BY_NAME
from brain.knowledge.chunking import Block, BlockKind, Chunk, ChunkBounds, chunk_document
from brain.knowledge.embed import (
    EMBED_PATH,
    EXIT_REFUSED,
    Piece,
    WiringError,
    embed_question,
    embed_units,
    main,
    wiring_gaps,
)
from brain.knowledge.embed_policy import (
    COLUMN_DIMENSIONS,
    ENDPOINT_SETTING,
    QUESTION_UNIT_ID,
    REVISION_SETTING,
    dimension_gaps,
    served_embedding_model,
)
from brain.knowledge.embed_queue import Embedded, EmbeddingBatch, EmbeddingUnit, units_for
from brain.knowledge.embedding import EmbeddedVector, EmbeddingError
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.controls import call_sites
from brain.ops.inference import InferenceRefused

A_REVISION = "v1.0.0"

#: An address in the documentation range; see the note beside the one in `test_embed_policy`.
AN_ENDPOINT = "http://192.0.2.9:8080"


def _chunks(text: str = "Deployments go out on a Tuesday.") -> tuple[Chunk, ...]:
    """Real chunks, from the one function that makes them.

    Built rather than faked because `Chunk` refuses to be constructed anywhere else, which is
    the guard that makes `units_for` safe to take a chunk from at all.
    """
    item = KnowledgeItem(
        item_id="k_sop",
        content=text,
        title="SOP",
        visibility=KnowledgeVisibility.of_department("web"),
        owner_id="p_wei_ling",
    )
    return chunk_document(
        item, [Block(kind=BlockKind.PROSE, text=text, start=0)], bounds=ChunkBounds()
    )


def _units(text: str = "Deployments go out on a Tuesday.") -> tuple[EmbeddingUnit, ...]:
    """The passages a worker reads back, as units of chunks the one function made."""
    return units_for(_chunks(text))


@dataclass
class FakeService:
    """An `EmbeddingService` that answers every id it was asked about, and counts being asked."""

    calls: int = 0

    @staticmethod
    def values() -> tuple[float, ...]:
        return tuple([1.0 / (COLUMN_DIMENSIONS**0.5)] * COLUMN_DIMENSIONS)

    def embed(self, batch: EmbeddingBatch) -> tuple[Embedded, ...]:
        self.calls += 1
        vector = EmbeddedVector(model=batch.model, values=self.values())
        return tuple(Embedded(chunk_id=unit.chunk_id, vector=vector) for unit in batch.units)


# ------------------------------------------------------ the sequence, in one place


def test_passages_become_writes_carrying_the_vector_and_the_model_that_produced_it() -> None:
    """The positive case, and the only test that says the calls are in an order that works at
    all. Every refusal below is satisfied by a function that refuses everything.

    The write's columns are asserted rather than its existence, because the property the
    sequence has to preserve is that a vector and the identity recorded beside it are filled
    from one object.

    Delete this and `embed_units` can be reordered into something that never produces a
    write, with every refusal test still green."""
    units = _units()
    service = FakeService()
    run = embed_units(units, service=service, revision=A_REVISION)

    assert run.is_complete
    assert service.calls == 1
    assert [write.chunk_id for write in run.writes] == [one.chunk_id for one in units]
    assert run.writes[0].vector.model.revision == A_REVISION


def test_nothing_is_sent_when_this_install_cannot_store_what_its_model_produces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decision this module exists for, and the call site the mutation has to reach.
    `brain.ops.worker.advisories` prints the same finding and starts the worker anyway, which
    is right for the process and is not a reason to let the leg run: every batch would post the
    text of a client's documents for vectors PostgreSQL refuses at the insert.

    The width `dimension_gaps` defaults to is moved rather than the function being replaced, so
    what runs is the real comparison reached through the real call. Its keyword default is
    bound when the module is imported, which is why the module attribute cannot be patched: it
    is read once, at definition, and `COLUMN_DIMENSIONS` is itself read off the column's type
    object. Substituting the name at the call site would have left the default that every real
    caller uses untested. The call count is what says nothing left the process.

    Delete this and the refusal can be removed with the advisory still printing, and an install
    whose column and model disagree pays the whole cost of a corpus-wide embed to produce
    nothing."""
    assert dimension_gaps.__kwdefaults__ is not None
    monkeypatch.setitem(dimension_gaps.__kwdefaults__, "column_dimensions", COLUMN_DIMENSIONS + 8)
    service = FakeService()

    with pytest.raises(EmbeddingError, match="nothing was sent"):
        embed_units(_units(), service=service, revision=A_REVISION)
    assert service.calls == 0


def test_an_install_whose_column_holds_what_its_model_produces_is_not_refused() -> None:
    """The positive sibling of the refusal above. A guard tested only by what it stops is
    satisfied by one that stops everything, and this one sits in front of every embedding run
    the product will ever do.

    Delete this and the width refusal can be made unconditional, which is an embedding leg
    that never runs on any install and a test suite that says so nowhere."""
    assert embed_units(_units(), service=FakeService(), revision=A_REVISION).is_complete


def test_a_request_to_embed_no_chunks_is_refused_rather_than_reported_as_complete() -> None:
    """A run over nothing plans no batches, completes all of them, and `is_complete` is true,
    so a caller advancing a cursor on it moves past whatever window named no rows.
    `embed_job` refuses an empty window for this reason at the other end of the same pipeline.

    Delete this and a scan that found nothing is indistinguishable from work that was done."""
    with pytest.raises(EmbeddingError, match="report success"):
        embed_units((), service=FakeService(), revision=A_REVISION)


def test_a_run_is_cut_into_as_many_batches_as_the_bound_allows() -> None:
    """That `max_chunks` reaches `plan_batches` rather than being accepted and dropped. A
    parameter that is taken and ignored reads as a bound and is not one, and the symptom is a
    single request carrying whatever the caller had.

    The call count is the assertion, because two batches and one batch produce the same writes
    in the same order.

    Delete this and the batching parameters can stop being passed on, and the failure radius
    of one interrupted request becomes the whole job."""
    units = _units("One. Two. Three. " * 400)
    service = FakeService()
    run = embed_units(units, service=service, revision=A_REVISION, max_chunks=1)

    assert len(units) > 1
    assert service.calls == len(units)
    assert run.is_complete


# ------------------------------------------------------ a question, which is not a passage


@dataclass
class Answering:
    """An `EmbeddingService` answering every batch with what it was told to, and keeping them."""

    answer: tuple[Embedded, ...] = ()
    asked: list[EmbeddingBatch] = field(default_factory=list)

    def embed(self, batch: EmbeddingBatch) -> tuple[Embedded, ...]:
        self.asked.append(batch)
        return self.answer


def test_a_question_travels_as_one_input_under_the_served_model_and_comes_back_a_vector() -> None:
    """The query leg's positive case. The question is sent as a batch of one whose id no chunk
    can hold, under the model identity a passage is written with, and what comes back is the
    vector alone.

    Delete this and `embed_question` can send the question under a model the corpus was not
    written with, which `vector_query` answers by finding nothing, for every question."""
    model = served_embedding_model(revision=A_REVISION)
    vector = EmbeddedVector(model=model, values=FakeService.values())
    service = Answering(answer=(Embedded(chunk_id=QUESTION_UNIT_ID, vector=vector),))

    found = embed_question("When do deployments go out?", service=service, revision=A_REVISION)

    assert found == vector
    [batch] = service.asked
    assert [(unit.chunk_id, unit.text) for unit in batch.units] == [
        (QUESTION_UNIT_ID, "When do deployments go out?")
    ]
    assert batch.model.identity == model.identity


def test_a_question_answered_with_a_vector_for_something_else_is_refused() -> None:
    """The refusal beside it, reached through the real call. A server answering a batch of one
    with a vector for another id is answering another question.

    Delete this and `embed_question` can take whatever vector came back first."""
    model = served_embedding_model(revision=A_REVISION)
    vector = EmbeddedVector(model=model, values=FakeService.values())
    service = Answering(answer=(Embedded(chunk_id="k_sop.0000", vector=vector),))

    with pytest.raises(InferenceRefused):
        embed_question("When?", service=service, revision=A_REVISION)


# ------------------------------------------------------ what is written and what runs it


def test_every_step_on_this_path_is_listed_with_the_state_the_source_is_actually_in() -> None:
    """The list held to the code rather than to itself, in both directions.

    `call_sites` reads `ast.Call` nodes out of `src/brain` and deliberately does not record a
    module calling its own function, which is why a step called only by the command at the
    bottom of `brain.knowledge.embed` is correctly listed as reached by nothing: nothing
    schedules it.

    Delete this and `EMBED_PATH` becomes prose in a tuple. A step that gains a caller goes on
    being reported as missing for as long as nobody re-reads the sentence, which is the exact
    defect the list was written to replace."""
    for piece in EMBED_PATH:
        callers = call_sites(piece.symbol)
        if piece.needs:
            assert callers == (), f"{piece.symbol} is listed as an orphan and {callers} calls it"
        else:
            assert callers, f"{piece.symbol} is listed as wired and nothing calls it"


def test_the_sequence_is_assembled_here_and_run_from_the_store_the_worker_and_the_tool() -> None:
    """Where each piece of the path is called from, read out of the source. The run, the width
    check and the question's reader are called from this module alone, so the order they run in
    is decided in one place; the store calls that order for a stored window, the worker calls
    the store, and the search tool embeds a question.

    Asserted from `call_sites` rather than from `EMBED_PATH`, so this cannot pass by the
    declaration being edited.

    Delete this and the assembly can be inlined back into whichever caller arrives first, and
    the pieces go back to being reachable only by reading five files."""
    assert call_sites("brain.knowledge.embed_policy:embed_all") == ("brain.knowledge.embed",)
    assert call_sites("brain.knowledge.embed_policy:dimension_gaps") == ("brain.knowledge.embed",)
    assert call_sites("brain.knowledge.embed_policy:question_vector") == ("brain.knowledge.embed",)
    assert call_sites("brain.knowledge.embed:embed_units") == ("brain.knowledge.chunk_store",)
    assert call_sites("brain.knowledge.chunk_store:run_embed_job") == ("brain.ops.worker",)
    assert call_sites("brain.knowledge.embed:embed_question") == ("brain.knowledge.document_tools",)


def test_the_report_names_a_step_and_what_it_needs_rather_than_counting_them() -> None:
    """A count tells an operator how far off this is and nothing they can pick up. Each line
    has to carry the symbol and the sentence, which is what turns "the embedding leg is not
    wired" into a list of named pieces of work.

    Delete this and the report can become a number, which is the shape somebody optimises."""
    findings = wiring_gaps()
    orphans = [one for one in EMBED_PATH if one.needs]

    assert len(findings) == len(orphans)
    for piece, finding in zip(orphans, findings, strict=True):
        assert piece.symbol in finding
        assert piece.needs in finding


def test_a_step_that_is_reached_produces_no_finding() -> None:
    """The positive case for the report. Without it `wiring_gaps` could return a line per step
    and every assertion above would still pass, which is a report that says the whole path is
    missing on the day it is finished.

    Delete this and the list stops being able to shrink."""
    reached = Piece(symbol="brain.knowledge.embed:embed_units", step="it runs")

    assert wiring_gaps((reached,)) == ()


def test_a_step_cannot_be_declared_reached_and_waiting_at_the_same_time() -> None:
    """The invariant is at construction rather than left to a reader, because the failure being
    closed is a reader believing the wrong half. `brain.ops.schedule_runner.Runner` refuses the
    same contradiction.

    Delete this and a row can say both, and the report and the code disagree with nobody able
    to say which is true."""
    with pytest.raises(WiringError, match="does not say what it does"):
        Piece(symbol="brain.knowledge.embed:embed_units", step="  ")


def test_a_step_whose_symbol_nothing_could_be_asked_about_is_refused() -> None:
    """A symbol `call_sites` cannot parse is a row that passes the check above by being
    unaskable: no callers are found for a name that does not exist either, so it would be
    reported as an orphan and believed, because most of this path is one.
    `brain.ops.controls.missing_symbols` exists for the same reason.

    Delete this and a mistyped module path reads as a step nothing calls."""
    with pytest.raises(WiringError, match="module:function"):
        Piece(symbol="brain.knowledge.embed.embed_units", step="it runs")


def test_the_address_this_product_ships_resolves_to_the_service_this_product_ships() -> None:
    """The two ends of the default, compared across the files that own them. `brain.install`
    declares where the inference server answers and `docker-compose.inference.yml` declares
    what answers there, and nothing else compares them: an install that changes neither is the
    commonest install there will ever be, and a default naming a service or a port this
    repository does not ship would work on every machine somebody had configured by hand.

    Parsed as YAML rather than searched for as text, because a regex over this file finds
    numbers inside its own header comments, which is exactly what a half-finished edit leaves
    behind.

    Delete this and the compose service can be renamed, or its exposed port moved, and the
    default endpoint goes on naming the old one with the only symptom being that a fresh
    install cannot embed."""
    compose = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "docker-compose.inference.yml").read_text(
            encoding="utf-8"
        )
    )
    service, *rest = compose["services"]
    exposed = [str(port) for port in compose["services"][service]["expose"]]
    parts = urlsplit(BY_NAME[ENDPOINT_SETTING].default)

    assert not rest
    assert parts.hostname == service
    assert str(parts.port) in exposed


# ------------------------------------------------------------------ the command


def test_the_check_prints_the_one_address_this_installs_text_is_sent_to(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """What an operator is really asking when they run this. The address is on the first line
    and the sentence says it is the only one, because the question behind the question is
    whether anything else could receive a client's documents.

    Delete this and the command can report the state of the leg without ever saying where the
    text would go, which is the one fact somebody signing a client agreement needs."""
    code = main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT})
    printed = capsys.readouterr().out

    assert code == 0
    assert AN_ENDPOINT in printed
    assert "nowhere else" in printed


def test_an_install_that_cannot_say_where_its_server_is_refuses_rather_than_reporting(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A command that printed the missing pieces and said nothing about a broken address would
    send somebody to the queue when the fault is one environment variable. The exit code is its
    own, matching `brain.knowledge.embedding`: a refusal is a value retyped.

    A provider's API base rather than an empty value, and the difference is worth knowing:
    `brain.install.value_of` substitutes the declared default for a setting that is blank, so
    an emptied endpoint is not reachable from here at all and the empty refusal in
    `endpoint_refusals` fires only for a caller that builds an address by hand. What is
    reachable from a client's environment file is this: an address that is somebody else's.

    Delete this and an endpoint pointed at a hosted provider reads as an install with nothing
    wrong but plenty missing."""
    code = main(["--check"], {ENDPOINT_SETTING: "https://192.0.2.55/v1"})

    assert code == EXIT_REFUSED
    assert "refused" in capsys.readouterr().err


def test_the_check_reports_the_second_setting_when_it_names_another_host(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`endpoint_conflicts` is written and this is the only thing that calls it. Without this
    the two settings can disagree on a real install with nothing anywhere saying so.

    Delete this and the conflict check joins the list of things this repository writes and
    never runs."""
    main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT, "BRAIN_INFERENCE_URL": "http://192.0.2.55"})

    assert "two different hosts" in capsys.readouterr().out


def test_a_finding_about_this_install_is_printed_under_a_heading_that_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The two lists this command prints answer different questions and a reader has to be able
    to tell them apart: one is a value in this install's environment file and the other is work
    nobody has done. A heading that said "not built yet" over a misconfiguration would send
    somebody to wait for a release.

    The finding is arranged rather than read off the install, for the reason
    `tests/unit/test_worker.py` gives about the same check: a test whose subject is one
    install's misconfiguration goes green or red on somebody else's decision.

    Delete this and the two headings can be swapped, and a width somebody can fix reads as a
    feature that is not finished."""
    monkeypatch.setattr("brain.knowledge.embed.policy_gaps", lambda: ("the column is 16 wide",))
    main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT})
    printed = capsys.readouterr().out

    assert "wrong with this install and not fixed by starting:" in printed
    assert "the column is 16 wide" in printed


def test_an_install_with_nothing_wrong_is_told_so_rather_than_shown_an_empty_heading(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive sibling, and it is not cosmetic: a heading introducing a list, followed by
    no list, reads as output that was cut off. The command has to say the answer is none.

    Delete this and the heading can be printed unconditionally, and every correct install looks
    like one whose report failed halfway."""
    monkeypatch.setattr("brain.knowledge.embed.policy_gaps", tuple)
    main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT})

    assert "nothing wrong with this install" in capsys.readouterr().out


def test_the_check_says_nothing_is_embedded_while_the_revision_is_unset(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An install that has not said which weights its server holds has no vector leg, and the
    operator asking whether this install embeds is owed that sentence rather than an address
    that reads as though text is being sent there.

    Delete this and the check can print a healthy report for an install that embeds nothing."""
    main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT})

    assert f"nothing is embedded on this install: {REVISION_SETTING} is unset" in (
        capsys.readouterr().out
    )


def test_the_check_names_the_identity_vectors_are_recorded_under_once_a_revision_is_declared(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The positive sibling. Delete this and the unset sentence can be printed for every
    install, which tells an operator who set the revision that it did nothing."""
    main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT, REVISION_SETTING: A_REVISION})
    printed = capsys.readouterr().out

    assert served_embedding_model(revision=A_REVISION).identity in printed
    assert "nothing is embedded" not in printed


def test_a_revision_the_corpus_cannot_record_is_refused_by_the_check(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A value somebody wrote that is not a revision is refused, not read as unset. Delete this
    and a typo in the setting switches the vector leg off with the check calling it a choice."""
    code = main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT, REVISION_SETTING: "not a revision"})

    assert code == EXIT_REFUSED
    assert REVISION_SETTING in capsys.readouterr().err


def test_the_check_prints_what_is_missing_as_a_fraction_of_the_whole_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The denominator is the point. "Six steps are missing" is a number somebody can read as
    nearly done or barely started; six of eleven is a position on the path.

    Delete this and the report loses the only thing that makes its size meaningful."""
    main(["--check"], {ENDPOINT_SETTING: AN_ENDPOINT})
    printed = capsys.readouterr().out

    assert f"{len(wiring_gaps())} of {len(EMBED_PATH)} steps" in printed
