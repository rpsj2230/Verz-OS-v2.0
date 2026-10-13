"""The model-server install checks: registered, passing over their stand-ins and able to fail.

Five of the six bodies need no database, so each runs here against a stub harness, passes, and is
shown failing with the product broken where it proves something; the sixth is run as the worker
runs it, against PostgreSQL at head, and leaves what it found. The worker's start-up advisory,
which one check reads, is tested here beside them because the check cannot tell a removed call
from a finding that was never owed.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.2.6, M7.3.3, M7.3.4, M7.7.11, M32.2.1.2
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops import acceptance_checks_knowledge_models as module
from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    REASON_CHARS,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_hubspot import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_knowledge_models"

ROUTE = "a_routed_read_records_its_path_and_an_outage_never_falls_back"
BUDGET = "the_parse_worker_refuses_an_oversize_file_before_opening_it"
BATCHES = "a_document_is_embedded_in_batches_each_vector_names_its_model"
SERVER = "the_install_s_inference_server_embeds_a_sentence_as_declared"
ADVISORY = "the_worker_says_at_start_what_the_door_admits_beyond_the_server"
NAMES = "a_name_only_the_model_finds_is_scrubbed_and_its_absence_is_free"

LEAVES = {
    ROUTE: ("M7.2.1", "M7.2.3", "M7.2.4"),
    BUDGET: ("M7.2.6",),
    BATCHES: ("M7.3.4",),
    SERVER: ("M7.3.3",),
    ADVISORY: ("M7.7.11",),
    NAMES: ("M32.2.1.2",),
}

#: Leaves whose pass is over something the check made, which the proof sweep must hold.
HELD = ("M7.2.1", "M7.2.3", "M7.2.4", "M7.3.4", "M7.7.11", "M32.2.1.2")


def body(name: str) -> Any:
    return next(one for one in registered((MODULE,)) if one.name == name).run


def run(name: str) -> None:
    asyncio.run(body(name)(SimpleNamespace(run="abc123def456")))


def test_the_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Delete this and the check that asks the real server can lose M7.3.3, or a check over a
    stand-in can be given a leaf only a real server proves, so the leaf closes on a made-up pass."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == LEAVES
    assert checks_in(MODULE) == list(LEAVES)
    assert 740 <= module.CHECK_ORDER <= 759


def test_every_leaf_that_passes_over_something_made_up_is_held() -> None:
    """The stand-in checks name six leaves and every one is in the holds file with a reason, while
    M7.2.6 and M7.3.3 (which read the install's own declaration and its own server) are not.
    Delete this and a leaf closes on a pass over a reader, an engine or a transport the check
    invented, which is what the holds file exists to stop."""
    held = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text())["held"]
    for leaf in HELD:
        assert held.get(leaf, "").strip(), leaf
    assert "M7.2.6" not in held
    assert "M7.3.3" not in held


def test_every_reason_the_module_ends_a_check_with_fits_the_result() -> None:
    """Stored whole. Delete this and why a check was not run is cut short on the Install page."""
    assert len(module.NO_EMBEDDING_REVISION_IS_DECLARED) <= REASON_CHARS
    assert len(module.NO_EMBEDDING_SERVER_ANSWERED) <= REASON_CHARS


# ------------------------------------------------------------------ 1. the route
def test_the_route_check_passes_on_the_product_as_it_stands() -> None:
    """The positive case. Delete this and a check that refuses everything passes the rest."""
    run(ROUTE)


def test_the_route_check_fails_where_an_outage_may_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`PARSER_UNAVAILABLE` added to the causes that may try another path, the most tempting entry
    in the enum. Delete this and an hour of downtime puts every document uploaded in it on the
    weaker reader for good, with the check green."""
    from brain.knowledge import parse_paths
    from brain.knowledge.ingest import ParseCause

    monkeypatch.setattr(
        parse_paths,
        "MAY_TRY_ANOTHER_PATH",
        parse_paths.MAY_TRY_ANOTHER_PATH | {ParseCause.PARSER_UNAVAILABLE},
    )
    with pytest.raises(CheckFailedError, match="outage"):
        run(ROUTE)


def test_the_route_check_fails_where_a_scan_under_the_floor_is_indexed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The OCR floor moved to nothing, so every garbled scan is indexed. Delete this and the floor
    can be set to zero with the check green."""
    from brain.knowledge import parse_ocr

    monkeypatch.setattr(parse_ocr, "OCR_FLOOR_CONFIDENCE", 0.0)
    with pytest.raises(CheckFailedError, match="confidence floor"):
        run(ROUTE)


# ------------------------------------------------------------------ 2. the parse worker
def test_the_budget_check_passes_on_the_product_as_it_stands() -> None:
    """The positive case, over the sizing the product declares for the container that parses.
    Delete this and a check that refuses everything passes the rest."""
    run(BUDGET)


def test_the_budget_check_fails_where_the_parser_is_opened_on_an_oversize_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The budget question answered yes for every file. Delete this and a file over the budget can
    reach a parser, which is the out-of-memory kill the bound exists to prevent. The check fails at
    the refusal, before it counts how often the parser was opened."""
    from brain.knowledge import scanning

    monkeypatch.setattr(scanning, "fits_parse_budget", lambda *_a, **_k: True)
    with pytest.raises(CheckFailedError, match="refused as too large"):
        run(BUDGET)


def test_the_budget_check_fails_where_a_second_slot_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The container's own sizing check going quiet. Delete this and a parse container can be
    given two slots, each promised the whole of one container's memory."""
    from brain.knowledge import parse_budget

    monkeypatch.setattr(parse_budget, "parse_worker_gaps", lambda *_a, **_k: ())
    with pytest.raises(CheckFailedError, match="second parse slot"):
        run(BUDGET)


# ------------------------------------------------------------------ 4. the real server
class _Silent:
    """A transport that never reaches a server, as the install's own is when none is running."""

    def post(self, url: str, *, json: Any, timeout: float) -> Any:
        from brain.ops.inference_client import TransportError

        raise TransportError("ConnectError")


def serve_with(monkeypatch: pytest.MonkeyPatch, transport: Any, revision: str | None) -> None:
    from brain.knowledge import embed_policy
    from brain.ops import inference_client

    monkeypatch.setattr(embed_policy, "embedding_revision", lambda _env=None: revision)
    monkeypatch.setattr(
        inference_client,
        "make_client",
        lambda **_k: inference_client.InferenceEmbeddingClient(
            transport=transport, url="http://inference.invalid/embed"
        ),
    )


def test_the_server_check_is_not_run_where_no_revision_is_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An install that has said nothing has no server to ask. Delete this and such an install is
    recorded as failing a check that was never asked."""
    serve_with(monkeypatch, _Silent(), None)
    with pytest.raises(CheckNotRunError, match="declares no embedding revision"):
        run(SERVER)


def test_the_server_check_is_not_run_where_the_declared_server_does_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revision declared and nothing answering is not a pass and is not a verdict on the product.
    Delete this and the leaf could close with no server ever having embedded a word."""
    serve_with(monkeypatch, _Silent(), "acceptance-rev")
    with pytest.raises(CheckNotRunError, match="no model server answered"):
        run(SERVER)


def test_the_server_check_passes_when_a_server_answers_in_the_declared_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case, over a transport that answers as the contract says. Delete this and a
    check that is always not run, or always failing, passes the rest."""
    serve_with(monkeypatch, module._Server(), "acceptance-rev")
    run(SERVER)


def test_the_server_check_fails_where_the_server_answers_in_another_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server whose weights are not the ones declared. Delete this and vectors from the wrong
    model are recorded as the declared one, which is the change that has no symptom."""

    class Other(module._Server):
        def post(self, url: str, *, json: Any, timeout: float) -> Any:
            answered = super().post(url, json=json, timeout=timeout).json()
            assert isinstance(answered, dict)
            return module._Answer({**answered, "model": {**answered["model"], "revision": "other"}})

    serve_with(monkeypatch, Other(), "acceptance-rev")
    with pytest.raises(CheckFailedError, match="other than the one"):
        run(SERVER)


# ------------------------------------------------------------------ 5. what the worker says
def test_the_advisory_check_passes_on_the_product_as_it_stands() -> None:
    """The positive case. Delete this and a check that refuses everything passes the rest."""
    run(ADVISORY)


def test_the_worker_prints_the_finding_only_once_an_install_declares_a_model_server() -> None:
    """The wiring the check reads, asked directly: the finding the parse layer reports is the one
    the worker prints for a declared revision, and none for an undeclared one. Delete this and the
    call in `advisories` can be removed with nothing red, or the finding printed on installs that
    have no server to be told about."""
    from brain.knowledge.embed_policy import REVISION_SETTING
    from brain.knowledge.parse_layout import layout_request_gaps
    from brain.ops.worker import advisories, model_server_advisory

    assert layout_request_gaps(), "the door and the request ceiling agree; the premise has gone"
    declared = advisories({REVISION_SETTING: "rev-1"}, worker_component="brain-parse-worker")
    assert set(layout_request_gaps()) <= set(declared)
    assert model_server_advisory(None) == ()
    assert model_server_advisory("rev-1") == layout_request_gaps()
    undeclared = advisories({}, worker_component="brain-parse-worker")
    assert not set(layout_request_gaps()) & set(undeclared)


def test_a_revision_the_system_cannot_record_does_not_stop_the_worker_starting() -> None:
    """An unusable value reads as undeclared in an advisory, which is printed and never refuses.
    Delete this and a typo in one setting takes the worker down before it reads a queue."""
    from brain.knowledge.embed_policy import REVISION_SETTING
    from brain.ops.worker import advisories

    advisories({REVISION_SETTING: "not a revision!"}, worker_component="brain-parse-worker")


def test_the_advisory_check_fails_where_the_worker_stops_printing_the_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The call removed from `advisories`. Delete this and an install that declares a model server
    can lose the one line that tells its owner the door admits a file the server will refuse."""
    from brain.ops import worker

    monkeypatch.setattr(worker, "model_server_advisory", lambda _revision: ())
    with pytest.raises(CheckFailedError, match="did not print"):
        run(ADVISORY)


def test_the_advisory_check_fails_where_a_file_over_the_ceiling_reaches_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ceiling test answering yes for every file. Delete this and a document too large for one
    request is sent anyway and comes back as a status read as this system's own fault."""
    from brain.knowledge import parse_layout

    monkeypatch.setattr(parse_layout, "fits_request_ceiling", lambda *_a, **_k: True)
    with pytest.raises(CheckFailedError, match="request ceiling"):
        run(ADVISORY)


# ------------------------------------------------------------------ 6. the names
def test_the_names_check_passes_on_the_product_as_it_stands() -> None:
    """The positive case. Delete this and a check that refuses everything passes the rest."""
    run(NAMES)


def test_the_names_check_fails_where_the_model_replaces_what_the_patterns_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The merge handing the model's spans back alone. Delete this and an install running the
    model can send an address to an outside provider that the patterns had found."""
    from brain.ops import pii

    monkeypatch.setattr(pii, "merge_detections", lambda _floor, model: tuple(model))
    with pytest.raises(CheckFailedError):
        run(NAMES)


def test_the_names_check_fails_where_the_declared_threshold_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A span the model is unsure of scrubbed anyway. Delete this and the threshold can be
    removed, which redacts a question's words on a guess nobody can read back."""
    from brain.ops import pii

    monkeypatch.setattr(
        pii,
        "GLINER_LABELS",
        tuple(
            pii.GlinerLabel(
                label=one.label,
                kind=one.kind,
                score_threshold=0.01,
                why_the_default_recognisers_miss_it=one.why_the_default_recognisers_miss_it,
            )
            for one in pii.GLINER_LABELS
        ),
    )
    with pytest.raises(CheckFailedError, match="threshold"):
        run(NAMES)


# ------------------------------------------------------------------ 3. the database half
@pytest.mark.needs_db
def test_on_a_real_database_a_document_is_embedded_and_nothing_is_left() -> None:
    """**The batches check as the worker runs it, against PostgreSQL at head.** It passes, and
    every table a check writes holds afterwards what it held before. Delete this and the worker's
    embedding function can stop recording the model, or write a vector the install's column
    refuses, with nothing on the owner's install saying so."""

    with at_head("brain_acceptance_knowledge_models") as url:
        before = counts(url)
        outcome = run_checks(
            url, tuple(one for one in registered((MODULE,)) if one.name == BATCHES)
        )
        after = counts(url)
    assert outcome == {BATCHES: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
def test_on_a_real_database_every_check_of_the_module_is_passed_or_not_run() -> None:
    """The module as the run makes it: five checks pass, the server check is not run for a reason
    in words, none fails. Delete this and the module can fail on an install while each body passes
    alone over a stub."""
    with at_head("brain_acceptance_knowledge_models_all") as url:
        outcome = run_checks(url, registered((MODULE,)))
    assert {name: state for name, (state, _) in outcome.items()} == {
        ROUTE: PASSED,
        BUDGET: PASSED,
        BATCHES: PASSED,
        SERVER: NOT_RUN,
        ADVISORY: PASSED,
        NAMES: PASSED,
    }
    assert FAILED not in {state for state, _ in outcome.values()}
