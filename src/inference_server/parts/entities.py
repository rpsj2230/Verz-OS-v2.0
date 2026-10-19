"""The entity part: GLiNER, asked for the names and details no pattern describes.

**Never run against the real library or the real weights.** Nothing in this repository has
installed `gliner` or downloaded a checkpoint, so the calls into the library
(`GLiNER.from_pretrained`, `predict_entities`) are written from its published interface and have
not been executed. The request it reads, the windows it cuts long text into, the spans it keeps and
the answer it writes are this program's own and are tested through a stand-in for the one object
that touches the library.

**It answers what it was asked and nothing else.** The request carries the labels to look for
(`brain.ops.pii.GLINER_LABELS`) and the text, and the answer is the spans of those labels and no
other: a span of a label nobody asked for is dropped here as well as refused by the application's
decoder, because the label becomes the token a model reads in place of a value and an unasked one
is a token nobody chose. Offsets are into the text as sent. A span that is empty, inverted or past
the end is dropped and not repaired, because a span one character out is the half-redacted name the
scrub exists to prevent, and a guess at which character was meant is the same fault.

**Long text is read in overlapping windows.** The model reads a few hundred tokens at a time and
silently ignores the rest, which for a scrub is the worst way to fail: the first paragraph is
cleaned and the second is not. So the text is cut into windows of `WINDOW_CHARS` that overlap by
`OVERLAP_CHARS`, each window is read, the spans are moved back to the text's own offsets, and where
two windows found the same name the higher score is kept. The overlap is longer than any name is
expected to be, so a name cut by one window's edge is whole in the next.

**A model may only add to a scrub** (`brain.ops.pii.A_MODEL_MAY_ONLY_EVER_ADD_TO_A_SCRUB`). That is
the application's guarantee and this part's own failure mode is chosen to keep it: an exception
is an outage, the application reads it as no answer, and the rules' scrub goes ahead alone. Nothing
here refuses a text for what is in it.

Task ids: M32.2.1.2
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from inference_server.config import ServerConfig
from inference_server.parts.documents import BadRequest, bad_request
from inference_server.worker import Answer

#: The name the part reports having loaded, and the directory its weights are in. The name is the
#: one the application declares for the model (`brain.ops.pii.GLINER_MODEL_NAME`).
LABEL: Final = "gliner"
WEIGHTS_DIRECTORY: Final = "gliner"

#: The keys one request and one span carry, spelled as `brain.ops.pii.ENTITY_REQUEST_KEYS`,
#: `ENTITY_SPANS_KEY` and `ENTITY_SPAN_KEYS`, which a test holds equal.
REQUEST_KEYS: Final = ("model", "labels", "text")
SPANS_KEY: Final = "spans"
SPAN_KEYS: Final = ("label", "start", "end", "score")

#: How long a window is and how much it shares with the next, in characters. A judgement: about the
#: three hundred tokens the model reads at a time for English prose, with an overlap longer than a
#: name.
WINDOW_CHARS: Final = 1200
OVERLAP_CHARS: Final = 200

#: The most labels one request may name, and the longest one, so the labels are not a place to put
#: a document.
MOST_LABELS: Final = 20
LABEL_CHARS: Final = 64

#: The lowest score the part will return. The application holds each label to a threshold of its
#: own and this is only the floor under all of them, so a model that scores everything is not
#: allowed to send everything.
FLOOR_SCORE: Final = 0.05


@dataclass(frozen=True)
class Span:
    """One entity found: which label, where in the text, and how sure the model said it was."""

    label: str
    start: int
    end: int
    score: float


class Finder(Protocol):
    """What finds spans in one window of text. The real one is GLiNER's; a test supplies its own."""

    def find(self, text: str, labels: Sequence[str]) -> Sequence[Span]: ...


def windows(text: str, size: int = WINDOW_CHARS, overlap: int = OVERLAP_CHARS) -> list[int]:
    """The offsets at which windows of `size` characters start, each overlapping the one before.

    One window for text no longer than `size`. The last window is the one that reaches the end, and
    no window is shorter than the overlap, so the tail is never a sliver that cuts a name in two
    without a neighbour to hold it whole.
    """
    if len(text) <= size:
        return [0]
    # Every start below `len(text) - overlap`, a step of `size - overlap` apart. The last of them is
    # at least `len(text) - size`, so its window reaches the end and nothing needs adding for the
    # tail: a branch that did was measured unreachable (a mutation removing it survived), which is
    # why there is none.
    return list(range(0, len(text) - overlap, size - overlap))


def find_in_text(finder: Finder, text: str, labels: Sequence[str]) -> list[Span]:
    """Every span in `text`, found window by window, given back in the text's own offsets.

    Spans from different windows that cover the same characters under the same label are one, and
    the one that scored higher is kept. A span of a label that was not asked for, one that is empty
    or inverted, one past the end of the text and one under the floor are dropped.
    """
    asked = set(labels)
    best: dict[tuple[str, int, int], Span] = {}
    for offset in windows(text):
        window = text[offset : offset + WINDOW_CHARS]
        for span in finder.find(window, labels):
            moved = Span(span.label, span.start + offset, span.end + offset, span.score)
            valid = (
                moved.label in asked
                and 0 <= moved.start < moved.end <= len(text)
                and FLOOR_SCORE <= moved.score <= 1.0
            )
            if not valid:
                continue
            key = (moved.label, moved.start, moved.end)
            if key not in best or moved.score > best[key].score:
                best[key] = moved
    return sorted(best.values(), key=lambda one: (one.start, one.end, one.label))


def read_request(body: bytes) -> tuple[list[str], str]:
    """The labels and the text of a request, or `BadRequest` saying which part is wrong."""
    try:
        request = json.loads(body)
    except ValueError as error:
        msg = "the body is not JSON"
        raise BadRequest(msg) from error
    if not isinstance(request, dict):
        msg = "the request is not an object"
        raise BadRequest(msg)
    labels, text = request.get("labels"), request.get("text")
    if (
        not isinstance(labels, list)
        or not 0 < len(labels) <= MOST_LABELS
        or not all(isinstance(one, str) and 0 < len(one.strip()) <= LABEL_CHARS for one in labels)
    ):
        msg = "the request names no labels, or too many, or one that is not a name"
        raise BadRequest(msg)
    if not isinstance(text, str) or not text.strip():
        msg = "the request carries no text"
        raise BadRequest(msg)
    return [one.strip() for one in labels], text


class EntitiesBackend:
    """`Backend`: the spans of the labels asked for in the text sent, and no others."""

    def __init__(self, finder: Finder, label: str = LABEL) -> None:
        self._finder = finder
        self.label = label

    def handle(self, body: bytes) -> Answer:
        try:
            labels, text = read_request(body)
        except BadRequest as error:
            return bad_request(error)
        spans = find_in_text(self._finder, text, labels)
        payload: list[dict[str, object]] = [
            {"label": one.label, "start": one.start, "end": one.end, "score": one.score}
            for one in spans
        ]
        return Answer(200, {SPANS_KEY: payload}, items=len(spans))


class GlinerFinder:
    """The one object that touches GLiNER. Imported only when an entity part is loaded."""

    #: What the library is asked to keep, before the application applies each label's own threshold.
    THRESHOLD: Final = FLOOR_SCORE

    def __init__(self, weights: Path) -> None:
        from gliner import GLiNER

        # Offline: the weights are in the read-only volume and the container has no route out.
        self._model: Any = GLiNER.from_pretrained(str(weights), local_files_only=True)

    def find(self, text: str, labels: Sequence[str]) -> list[Span]:
        found = self._model.predict_entities(text, list(labels), threshold=self.THRESHOLD)
        return [
            Span(str(one["label"]), int(one["start"]), int(one["end"]), float(one["score"]))
            for one in found
        ]


def load(
    config: ServerConfig, *, finder: Callable[[Path], Finder] | None = None
) -> EntitiesBackend:
    """The entity backend, with GLiNER loaded from the weights volume unless a finder is given."""
    return EntitiesBackend((finder or GlinerFinder)(config.model_dir / WEIGHTS_DIRECTORY))
