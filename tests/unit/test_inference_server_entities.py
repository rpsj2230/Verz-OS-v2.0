"""The entity part of the model server and the leg of the egress scrub that asks it.

Held here: the part cuts long text into overlapping windows and gives every span back in the text's
own offsets; it answers the labels it was asked and no others; the application's own decoder reads
what it says and the application's own scrub removes the name; and the egress leg degrades to the
rules' scrub whenever the part is down, slow or unreadable, which is the whole of how a model is
allowed to fail here. The library is a stand-in: **nothing here has loaded GLiNER or a checkpoint.**

Task ids: M32.2.1.2
"""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

from brain.ops import egress, pii
from brain.ops.egress import (
    ENTITIES_PATH,
    AnalyserUnavailableError,
    Detectors,
    detector_for,
    entities,
    scrub_for_egress,
)
from brain.ops.model_server import PATH_OF_PART, Part
from brain.ops.model_server_client import entity_endpoint
from brain.ops.pii import GLINER_LABELS, GLINER_MODEL_NAME, Detection, EntityKind, PiiError
from inference_server.parts import entities as server
from inference_server.parts.entities import EntitiesBackend, Span
from tests.unit.test_inference_server import server_config

PERSON = GLINER_LABELS[0].label
NAME = "Aloysius Tan Wei Ming"
TEXT = f"Please email {NAME} about the lease."
START = TEXT.index(NAME)


class _Finder:
    """Finds `NAME` wherever it is, as a span of the label, and records what it was shown."""

    def __init__(self, score: float = 0.9, extra: list[Span] | None = None) -> None:
        self.score = score
        self.extra = extra or []
        self.shown: list[tuple[str, tuple[str, ...]]] = []

    def find(self, text: str, labels: Sequence[str]) -> list[Span]:
        self.shown.append((text, tuple(labels)))
        at = text.find(NAME)
        found = [] if at < 0 else [Span(PERSON, at, at + len(NAME), self.score)]
        return [*found, *self.extra]


def request(text: str = TEXT, labels: object = None) -> bytes:
    body = dict(pii.entity_request(text))
    body["labels"] = list(body["labels"]) if labels is None else labels  # type: ignore[call-overload]
    return json.dumps(body).encode("utf-8")


# ------------------------------------------------------------------ the wire, held equal
def test_the_wire_the_entity_part_speaks_is_the_one_the_application_writes() -> None:
    """The keys of a request and of a span, the key the spans are under, the model's name and the
    path the part is served at are read from both programs and compared.

    Delete this and a renamed key is an answer the application refuses for every text, and the
    leg is silently the rules' alone."""
    assert server.REQUEST_KEYS == pii.ENTITY_REQUEST_KEYS
    assert server.SPANS_KEY == pii.ENTITY_SPANS_KEY
    assert server.SPAN_KEYS == pii.ENTITY_SPAN_KEYS
    assert server.LABEL == GLINER_MODEL_NAME
    assert PATH_OF_PART[Part.ENTITIES] == ENTITIES_PATH


def test_the_name_the_part_finds_is_scrubbed_by_the_applications_own_decoder_and_scrub() -> None:
    """The producer's answer is fed to the consumer: the application reads the span, merges it with
    the rules' findings and removes the three-word name no pattern describes.

    Delete this and the part is tested against its own idea of what the application reads."""
    answer = EntitiesBackend(_Finder()).handle(request())

    scrubbed = pii.scrub(TEXT, pii.detect_with_model(TEXT, answer.payload))

    assert answer.status == 200 and answer.items == 1
    assert NAME not in scrubbed and "lease" in scrubbed


# ------------------------------------------------------------------ what the part keeps
def test_windows_cover_the_whole_text_overlap_by_the_stated_amount_and_never_exceed_the_size() -> (
    None
):
    """For lengths either side of every boundary the windows start at 0, end at the end of the text,
    are no longer than the size and each starts inside the one before it by the overlap.

    Delete this and the tail of a long text is never read, which for a scrub is a clean first
    paragraph and an unscrubbed second."""
    size, overlap = server.WINDOW_CHARS, server.OVERLAP_CHARS
    for length in (1, size - 1, size, size + 1, 2 * size - overlap, 2 * size - overlap + 1, 5000):
        starts = server.windows("x" * length)
        ends = [min(start + size, length) for start in starts]
        assert starts[0] == 0 and ends[-1] == length, length
        for after, last_end in zip(starts[1:], ends, strict=False):
            assert after < last_end and last_end - after >= overlap, length
        assert all(end - start <= size for start, end in zip(starts, ends, strict=True)), length


def test_a_name_in_the_second_window_is_found_in_the_texts_own_offsets_and_once() -> None:
    """A name past the first window, and one in the overlap that two windows both find, come back
    at their place in the whole text, the second only once with the higher score.

    Delete this and offsets are the window's, so the scrub removes other characters, or a name in
    the overlap is returned twice."""
    filler = "The quarterly lease report was agreed. " * 40
    text = f"{filler}{NAME} signed it.{filler}"
    finder = _Finder()

    spans = server.find_in_text(finder, text, [PERSON])

    assert len(finder.shown) > 1
    at = text.index(NAME)
    assert [(one.start, one.end) for one in spans] == [(at, at + len(NAME))]
    assert text[spans[0].start : spans[0].end] == NAME


def test_a_name_both_windows_found_keeps_the_higher_score() -> None:
    """The same span found by two overlapping windows is one span, with the score of whichever
    window was surer.

    Delete this and the lower score is kept, and a name the model was sure of falls under its
    label's threshold in the application and is not scrubbed."""

    class Windowed:
        def find(self, text: str, labels: Sequence[str]) -> list[Span]:
            at = text.find(NAME)
            if at < 0:
                return []
            return [Span(PERSON, at, at + len(NAME), 0.55 if text.startswith("a") else 0.95)]

    # The name sits in the overlap of the first two windows, which start with different letters.
    head = "a" * (server.WINDOW_CHARS - server.OVERLAP_CHARS) + "c" * 20
    text = f"{head}{NAME}{'b' * 400}"
    spans = server.find_in_text(Windowed(), text, [PERSON])

    assert [(one.start, one.score) for one in spans] == [(len(head), 0.95)]


def test_a_span_of_a_label_nobody_asked_for_or_that_is_not_a_span_is_dropped() -> None:
    """An unasked label, an empty or inverted span, one past the end and one under the floor are
    all dropped, never repaired.

    Delete this and the part sends the application spans it must refuse, and the refusal costs the
    whole answer."""
    junk = [
        Span("organisation", 0, 5, 0.9),
        Span(PERSON, 4, 4, 0.9),
        Span(PERSON, 6, 2, 0.9),
        Span(PERSON, 0, 10_000, 0.9),
        Span(PERSON, 0, 3, 0.01),
        Span(PERSON, 0, 3, 1.5),
    ]

    assert server.find_in_text(_Finder(extra=junk), "no name here at all", [PERSON]) == []


@pytest.mark.parametrize(
    "body",
    [
        b"nope",
        b"[]",
        b'{"text": "x"}',
        b'{"labels": [], "text": "x"}',
        b'{"labels": [1], "text": "x"}',
        b'{"labels": ["person"], "text": "  "}',
        b'{"labels": ["person"]}',
        json.dumps({"labels": ["l" * 65], "text": "x"}).encode(),
        json.dumps({"labels": [f"l{n}" for n in range(21)], "text": "x"}).encode(),
    ],
)
def test_a_request_with_no_text_or_no_sensible_labels_is_a_bad_request(body: bytes) -> None:
    """No text, no labels, too many, one too long and one that is not a name are the application's
    mistake.

    Delete this and the labels are a place to put a document."""
    assert EntitiesBackend(_Finder()).handle(body).status == 400


# ------------------------------------------------------------------ the object that touches GLiNER
def test_the_library_is_loaded_offline_and_its_answer_is_reduced_to_spans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GLiNER is loaded from the volume with no route to a hub, asked at the floor score, and each
    of its dicts becomes a span with whole-number offsets.

    Delete this and the part reaches for a hub it cannot reach, or the library's score is kept as
    the application's threshold and a name it was only half sure of is lost."""
    module = types.ModuleType("gliner")
    loaded: list[dict[str, Any]] = []

    class GLiNER:
        @classmethod
        def from_pretrained(cls, path: str, **kwargs: Any) -> GLiNER:
            loaded.append({"path": path, **kwargs})
            return cls()

        def predict_entities(self, text: str, labels: list[str], threshold: float) -> list[Any]:
            loaded.append({"threshold": threshold, "labels": labels})
            return [{"label": PERSON, "start": 1, "end": 4, "score": 0.7, "text": text[1:4]}]

    module.GLiNER = GLiNER  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gliner", module)

    found = server.GlinerFinder(tmp_path).find("abcdef", [PERSON])

    assert found == [Span(PERSON, 1, 4, 0.7)]
    assert loaded[0] == {"path": str(tmp_path), "local_files_only": True}
    assert loaded[1] == {"threshold": server.FLOOR_SCORE, "labels": [PERSON]}


def test_the_entity_weights_are_where_the_fetch_puts_them_and_the_part_is_in_the_image() -> None:
    """The directory the readiness check looks for is the one the fetch fills, and the part's
    module is where `NEEDS` says.

    Delete this and a renamed directory leaves a part the fetch filled and readiness says is
    missing, for ever."""
    import importlib.util

    from inference_server import fetch
    from inference_server.parts import NEEDS

    config = server_config(INFERENCE_PARTS="entities", INFERENCE_NEED_ENTITIES_MIB="1408")

    assert fetch.DIRECTORIES["entities"] == server.WEIGHTS_DIRECTORY
    assert fetch.DOWNLOADERS[server.WEIGHTS_DIRECTORY] is fetch.fetch_entity_weights
    assert [str(one) for one in NEEDS["entities"].files(config)] == [
        str(config.model_dir / server.WEIGHTS_DIRECTORY)
    ]
    assert importlib.util.find_spec(f"inference_server.parts.{NEEDS['entities'].module}")


# ------------------------------------------------------------------ the egress leg
def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _unwell_with_spans() -> Callable[[httpx.Request], httpx.Response]:
    body = {"spans": [{"label": PERSON, "start": START, "end": START + len(NAME), "score": 0.9}]}
    return lambda request: httpx.Response(503, json=body)


def _spans_answer(
    start: int = START, end: int = START + len(NAME), score: float = 0.9
) -> Callable[[httpx.Request], httpx.Response]:
    body = {"spans": [{"label": PERSON, "start": start, "end": end, "score": score}]}
    return lambda request: httpx.Response(200, json=body)


def test_the_entity_leg_posts_the_applications_request_and_reads_the_spans_it_gets() -> None:
    """The request is `pii.entity_request` as JSON, posted to the part's path, and the span comes
    back as a detection of the declared kind.

    Delete this and the leg posts something the part cannot read and degrades silently."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _spans_answer()(request)

    found = entities("http://inference:8080", _client(handler))(TEXT, timeout_seconds=1.0)

    assert [(one.kind, one.start, one.end) for one in found] == [
        (EntityKind.UNPATTERNED_NAME, START, START + len(NAME))
    ]
    [one] = seen
    assert str(one.url) == f"http://inference:8080{ENTITIES_PATH}"
    body = json.loads(one.content)
    assert tuple(body) == pii.ENTITY_REQUEST_KEYS
    assert body["labels"] == [label.label for label in GLINER_LABELS] and body["text"] == TEXT


@pytest.mark.parametrize(
    ("handler", "failure"),
    [
        (lambda request: httpx.Response(503), AnalyserUnavailableError),
        (_unwell_with_spans(), AnalyserUnavailableError),
        (lambda request: httpx.Response(200, content=b"<html>"), AnalyserUnavailableError),
        (lambda request: httpx.Response(200, json=["not", "an", "object"]), PiiError),
        (
            lambda request: httpx.Response(200, json={"spans": [{"label": "organisation"}]}),
            PiiError,
        ),
    ],
    ids=["unwell", "unwell-with-spans", "not-json", "not-an-object", "a-span-nobody-asked-for"],
)
def test_a_part_that_is_unwell_or_unreadable_is_a_leg_that_adds_nothing(
    handler: Any, failure: type[Exception]
) -> None:
    """An outage and an unreadable answer are the two refusals the egress catches, and neither is
    read as a text the model found no names in.

    Delete this and a part that is loading is a scrub that raises, or a garbled answer is a clean
    one."""
    with pytest.raises(failure):
        entities("http://inference:8080", _client(handler))(TEXT, timeout_seconds=1.0)


def test_a_server_that_does_not_answer_at_all_is_unavailable() -> None:
    """A refused connection is an outage.

    Delete this and a part that is down raises past the egress's guard."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AnalyserUnavailableError):
        entities("http://inference:8080", _client(refuse))(TEXT, timeout_seconds=1.0)


def test_the_name_is_replaced_in_what_leaves_and_put_back_when_the_leg_answers() -> None:
    """Through `scrub_for_egress`: the rules find nothing in the text, the entity leg finds the
    name, and what is sent carries a placeholder where it was, which the answer is given back.

    Delete this and the leg is built and never changes what a third party is sent."""
    detector = detector_for(
        analyser_detector=None,
        entity_detector=entities("http://inference:8080", _client(_spans_answer())),
    )

    scrubbed = scrub_for_egress([TEXT], detector=detector)

    assert NAME not in scrubbed.texts[0] and scrubbed.detector == "analyser"
    assert scrubbed.put_back(scrubbed.texts[0]) == TEXT


def test_with_the_part_down_the_text_is_scrubbed_by_the_rules_and_never_sent_unscrubbed() -> None:
    """The leg raises, the rules' scrub goes ahead, and the report says the rules did it.

    Delete this and a part that is loading stops every question or lets one through unscrubbed."""
    text = "Her NRIC is S1234567D and she is Aloysius Tan Wei Ming."

    scrubbed = scrub_for_egress(
        [text],
        detector=detector_for(
            analyser_detector=None,
            entity_detector=entities(
                "http://inference:8080", _client(lambda request: httpx.Response(503))
            ),
        ),
    )

    assert "S1234567D" not in scrubbed.texts[0] and scrubbed.detector == "rules"


# ------------------------------------------------------------------ several legs
def _leg(spans: Sequence[Detection] | None = None, fail: Exception | None = None) -> Any:
    calls: list[float] = []

    def ask(text: str, *, timeout_seconds: float) -> Sequence[Detection]:
        calls.append(timeout_seconds)
        if fail is not None:
            raise fail
        return spans or ()

    ask.calls = calls  # type: ignore[attr-defined]
    return ask


def _name() -> Detection:
    return Detection(
        kind=EntityKind.UNPATTERNED_NAME, start=START, end=START + len(NAME), confidence=0.9
    )


def test_the_first_legs_spans_are_kept_whole_and_the_next_only_adds() -> None:
    """Two legs finding overlapping spans give the first's extent and label for the characters it
    reached, and the second's for the rest.

    Delete this and a model's extent can move a pattern's."""
    pattern = Detection(kind=EntityKind.EMAIL, start=START, end=START + 5, confidence=1.0)

    found = Detectors((_leg([pattern]), _leg([_name()])))(TEXT, timeout_seconds=1.0)

    assert (found[0].kind, found[0].start, found[0].end) == (EntityKind.EMAIL, START, START + 5)
    assert max(one.end for one in found) == START + len(NAME)


def test_one_leg_down_costs_only_its_own_additions_and_every_leg_down_is_unavailable() -> None:
    """A leg that fails is passed over and the other is heard; with none answering the call fails
    the way a single analyser's does.

    Delete this and the analyser being down discards the entity model's names, or the other way
    round."""
    down = _leg(fail=AnalyserUnavailableError())
    unreadable = _leg(fail=PiiError("x"))

    assert Detectors((down, _leg([_name()])))(TEXT, timeout_seconds=1.0)
    assert Detectors((_leg([_name()]), unreadable))(TEXT, timeout_seconds=1.0)
    with pytest.raises(AnalyserUnavailableError):
        Detectors((down, unreadable))(TEXT, timeout_seconds=1.0)


def test_a_leg_is_asked_within_what_is_left_and_not_asked_when_nothing_is() -> None:
    """The second leg gets the time the first left over, and when the first used it all the second
    is not asked.

    Delete this and two legs spend twice the budget a person waits for."""
    times = iter([0.0, 0.0, 0.6, 1.5, 1.5])
    first, second = _leg([_name()]), _leg([_name()])

    Detectors((first, second), clock=lambda: next(times))(TEXT, timeout_seconds=1.0)

    assert first.calls == [pytest.approx(1.0)] and second.calls == [pytest.approx(0.4)]
    never = _leg([_name()])
    late = iter([0.0, 0.0, 2.0, 2.0])
    Detectors((_leg([_name()]), never), clock=lambda: next(late))(TEXT, timeout_seconds=1.0)
    assert never.calls == []


def test_the_entity_model_gets_the_longer_budget_and_the_analyser_alone_keeps_its_own() -> None:
    """An install with the entity model, alone or beside the analyser, scrubs within six seconds;
    one with only the analyser is exactly what it was.

    Delete this and a model that reads a window a second is given up on in two."""
    analyser_leg, entity_leg = _leg(), _leg()

    alone = detector_for(analyser_detector=analyser_leg, entity_detector=None)
    both = detector_for(analyser_detector=analyser_leg, entity_detector=entity_leg)
    only = detector_for(analyser_detector=None, entity_detector=entity_leg)
    none = detector_for(analyser_detector=None, entity_detector=None)

    assert alone is analyser_leg and none is None
    assert isinstance(both, Detectors) and isinstance(only, Detectors)
    assert both.budget_seconds == only.budget_seconds == egress.ENTITY_BUDGET_SECONDS == 6.0
    assert egress.ENTITY_BUDGET_SECONDS > egress.ANALYSER_BUDGET_SECONDS == 2.0


def test_the_budget_a_detector_declares_is_the_one_the_scrub_is_held_to() -> None:
    """With a detector that declares a budget the scrub's deadline is that, and without one it is
    the analyser's.

    Delete this and the six seconds are declared and never applied."""
    times = iter([0.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    answered = Detectors((_leg([_name()]),), budget_seconds=6.0)

    first = scrub_for_egress([TEXT], detector=answered, clock=lambda: next(times))
    plain = iter([0.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    second = scrub_for_egress([TEXT], detector=_leg([_name()]), clock=lambda: next(plain))

    assert first.detector == "analyser" and NAME not in first.texts[0]
    assert second.detector == "rules" and NAME in second.texts[0]


# ------------------------------------------------------------------ whether there is one to ask
def test_an_install_has_an_entity_model_only_when_it_runs_the_server_and_chose_the_part() -> None:
    """Both settings are things a person set on purpose, so the default is no entity model, the
    server without the part is none, the part without the server is none, and a setting that
    cannot be read is none.

    Delete this and every install sends text to a server it does not run, or an install that chose
    the part is never scrubbed by it."""
    on = {"INSTALL_SERVICES": "modelserver", "INSTALL_MODEL_PARTS": "embedding,entities"}

    assert entity_endpoint({}, {}) is None
    assert entity_endpoint({"INSTALL_SERVICES": "modelserver"}, {}) is None
    assert entity_endpoint({"INSTALL_MODEL_PARTS": "entities"}, {}) is None
    assert entity_endpoint({**on, "INSTALL_MODEL_PARTS": "embedding"}, {}) is None
    assert entity_endpoint({**on, "INSTALL_MODEL_PARTS": "telepathy"}, {}) is None
    assert entity_endpoint({**on, "INSTALL_MODEL_ENDPOINT": "ftp://x"}, {}) is None
    assert entity_endpoint(on, {}) == "http://inference-server:8080"
