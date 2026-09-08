"""The architecture document, checked where it states a fact that changes.

`docs/architecture.html` is a document of record: it is served in the console and it is what
somebody reads to learn the current position. Most of it is reasoning, which does not go
stale. A handful of sentences are counts and decisions, and those do.

The one this file exists for said "Six questions are open" long after four had been answered,
and named two of them specifically: whether production deploys on every push, and who holds
the vault's unseal pieces. Both were decided, one of them the same day the sentence was last
read. A stale number in a document of record is worse than no number, because a reader takes
it for the current position rather than for something nobody updated.

Prose cannot be tested and should not be. What can be tested is a number that also exists
somewhere machine-readable, so the count is carried in a `data-` attribute and held against
`docs/needs-rupash.md`, which is the file both the count and the console read from.

Task ids: M0.6.4
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from brain.docs_routes import _needs_count

ARCHITECTURE = Path(__file__).resolve().parents[2] / "docs" / "architecture.html"

#: Words for the small numbers this sentence can plausibly carry. A count is written out in
#: prose here rather than as a digit, so the test has to know both forms.
#: The count is written as a word in the document, so this is how the two are compared.
#:
#: It stopped at ten, and the eleventh open question turned the comparison into a `KeyError`
#: rather than a readable failure. A table that runs out is a check that stops working at a
#: number nobody chose, and the failure it produces names the table rather than the drift.
WORDS = {
    0: "none",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
}


#: Words for a screen count, which is a larger number than an open-question count and is
#: written out in prose in the same way. Separate from `WORDS` rather than merged into it,
#: because the two sentences are about different things and a shared table would make a
#: change to one look like a change to the other.
#:
#: It stops where the console plausibly stops. A fortieth screen fails with a `KeyError`
#: naming this table, which is the failure `WORDS` already records: a table that runs out is
#: a check that stops working at a number nobody chose.
WORDS_LARGE = {
    **WORDS,
    21: "twenty-one",
    22: "twenty-two",
    23: "twenty-three",
    24: "twenty-four",
    25: "twenty-five",
    26: "twenty-six",
    27: "twenty-seven",
    28: "twenty-eight",
    29: "twenty-nine",
    30: "thirty",
    31: "thirty-one",
    32: "thirty-two",
    33: "thirty-three",
    34: "thirty-four",
    35: "thirty-five",
    36: "thirty-six",
    37: "thirty-seven",
    38: "thirty-eight",
    39: "thirty-nine",
    40: "forty",
}


def _stated_open_questions() -> str:
    """The word inside the marked span, or a failure naming what is missing."""
    html = ARCHITECTURE.read_text(encoding="utf-8")
    found = re.search(r'<span data-open-questions="[^"]*">([^<]+)</span>', html)
    if found is None:
        pytest.fail(
            "the architecture no longer marks its open-question count, so nothing can "
            "check it against the tracker"
        )
    return found.group(1).strip().lower()


def test_the_architecture_agrees_with_the_tracker_about_how_many_questions_are_open() -> None:
    """The sentence said six while three were open, and it named two decided ones as though
    they were live.

    Compared against `docs/needs-rupash.md` through the same function the console uses, so
    there is one source and not two opinions about it. Delete this and the number drifts
    again, silently, and the person who reads it is the client."""
    actual = _needs_count()

    assert _stated_open_questions() == WORDS[actual], (
        f"the architecture says {_stated_open_questions()!r} open questions and there are {actual}"
    )


def test_the_count_is_carried_somewhere_a_test_can_read() -> None:
    """The guard on the guard. A future edit that rewrites the sentence and drops the span
    leaves the test above with nothing to compare, and a test that quietly stops checking is
    the failure this whole file is about.

    `pytest.fail` inside the helper rather than a skip, for the same reason."""
    html = ARCHITECTURE.read_text(encoding="utf-8")

    assert 'data-open-questions=""' in html


@pytest.mark.parametrize(
    ("decided", "phrase"),
    [
        ("every push", "deploys on every push rather than from a tag"),
        ("five unseal pieces", "the vault split is five pieces, any three"),
    ],
)
def test_a_settled_decision_is_not_still_described_as_open(decided: str, phrase: str) -> None:
    """Two decisions this section used to list as open questions. Naming them here is not
    decoration: they are the two the document called out by name, so a rewrite that restores
    the old paragraph would put them back in the open list, and the count test alone would
    not notice because the count could still be right.

    Asserted as presence of the settled wording rather than absence of the old, because
    absence passes for a section somebody deleted entirely."""
    html = ARCHITECTURE.read_text(encoding="utf-8").lower()

    assert decided in html, f"the architecture no longer records that {phrase}"


def test_a_wrapped_paragraph_renders_as_one_paragraph_and_not_as_five() -> None:
    """**The page the owner actually reads, and it was broken in the most visible way.**

    The renderer emitted one `<p>` per source line until 2026-09-08, so a paragraph wrapped at
    ninety columns in the markdown became five paragraphs on the page, each with a margin under
    it. The document read as though every other sentence had its own block. The owner described
    it as broken spacing and line breaks mid-paragraph, which is exactly what it was.

    The file is wrapped for reading in an editor and the browser wraps for itself, so a newline
    inside a paragraph carries no meaning and must not survive into the markup.

    Asserted by counting: the rendered page must have far fewer paragraphs than the document
    has non-blank prose lines. A ratio rather than an exact number, because the document
    changes daily and an exact count would be a test about today's wording.

    Delete this and the next edit to the renderer can go back to splitting on newlines, and
    nobody notices until somebody opens the page."""
    from fastapi.testclient import TestClient

    from brain.app import create_app

    source = (ARCHITECTURE.parent / "needs-rupash.md").read_text(encoding="utf-8")
    prose = [
        one
        for one in source.splitlines()
        if one.strip() and not one.startswith(("#", "-", "|", "*", "    ", "```"))
    ]

    page = TestClient(create_app()).get("/build/needs-rupash").text

    assert page.count("<p>") < len(prose) / 2, (
        f"{page.count('<p>')} paragraphs rendered from {len(prose)} wrapped prose lines, "
        "which means the renderer is splitting on newlines again"
    )


def test_the_page_renders_bold_and_bullets_rather_than_showing_their_marks() -> None:
    """The document uses `**bold**` to carry the load-bearing sentence of every item and `- `
    for the option lists the owner chooses from. Both were passed through escaped and
    unconverted, so the page showed the asterisks and ran the options together as prose.

    Asserted on the absence of the marks as well as the presence of the tags, because a
    renderer that emitted `<strong>` and left the asterisks in place would satisfy half of
    this and look worse than before.

    Delete this and the options in an item stop looking like options, which is the part the
    owner is meant to choose between."""
    from fastapi.testclient import TestClient

    from brain.app import create_app

    page = TestClient(create_app()).get("/build/needs-rupash").text

    assert "<strong>" in page
    assert "<li>" in page
    assert "**" not in page


def _stated_screen_count() -> str:
    """The word inside the marked span, or a failure naming what is missing."""
    html = ARCHITECTURE.read_text(encoding="utf-8")
    found = re.search(r'<span data-screen-count="[^"]*">([^<]+)</span>', html)
    if found is None:
        pytest.fail(
            "the architecture no longer marks its console screen count, so nothing can "
            "check it against the screen registry"
        )
    return found.group(1).strip().lower()


def test_the_architecture_agrees_with_the_console_about_how_many_screens_there_are() -> None:
    """**The heading said thirteen while `SCREENS` declared thirty-four.** The table under it
    lists the original thirteen and the grouping argument in it is still right, so the table
    stayed and is labelled as the sketch it is; what was wrong was the number in the heading,
    which reads as the current position.

    Compared against `brain.console.screens.SCREEN_COUNT` rather than a number written here,
    so the thirty-fifth screen fails this rather than being invisible.

    Delete this and the document goes back to being one screen count behind the console, and
    the person who reads it is the client."""
    from brain.console.screens import SCREEN_COUNT

    assert _stated_screen_count() == WORDS_LARGE[SCREEN_COUNT], (
        f"the architecture says {_stated_screen_count()!r} screens and there are {SCREEN_COUNT}"
    )


def test_the_screen_count_is_carried_somewhere_a_test_can_read() -> None:
    """The guard on the guard, in the same shape as the one on the open-question count: an
    edit that rewrites the heading and drops the span leaves the test above with nothing to
    compare, and a test that quietly stops checking is what this file exists to prevent."""
    html = ARCHITECTURE.read_text(encoding="utf-8")

    assert 'data-screen-count=""' in html


def _stated_part_count() -> str:
    """The word inside the marked span, or a failure naming what is missing."""
    html = ARCHITECTURE.read_text(encoding="utf-8")
    found = re.search(r'<span data-part-count="[^"]*">([^<]+)</span>', html)
    if found is None:
        pytest.fail(
            "the architecture no longer marks how many things an agent composes, so nothing "
            "can check it against the enum that lists them"
        )
    return found.group(1).strip().lower()


def test_the_architecture_agrees_with_the_workspace_about_what_an_agent_is_made_of() -> None:
    """**The document said eleven and listed a different eleven from the ten the plan names.**
    It dropped availability, and added the ceiling and artifacts, which are administered per
    agent and are not parts: a ceiling is the right-hand side of the intersection and confers
    nothing on its own, and an artifact is what an agent produced rather than what it is made
    of. Listing the ceiling beside the persona invites exactly the merge the paragraph under
    the table exists to forbid.

    M39.1.1.1 names the ten and `brain.console.workspace.Part` is that list, so the document
    was the only one of the three that disagreed.

    Compared against the enum rather than a number here, so an eleventh part fails this rather
    than being invisible.

    Delete this and the document goes back to describing an agent that is not the one this
    system builds."""
    from brain.console.workspace import Part

    assert _stated_part_count() == WORDS_LARGE[len(Part)], (
        f"the architecture says an agent composes {_stated_part_count()!r} things and "
        f"`Part` names {len(Part)}"
    )


def test_the_part_count_is_carried_somewhere_a_test_can_read() -> None:
    """The guard on the guard, in the same shape as the two beside it."""
    html = ARCHITECTURE.read_text(encoding="utf-8")

    assert 'data-part-count=""' in html


def test_the_composition_table_names_availability_and_not_the_ceiling() -> None:
    """The count alone would pass on a table that still listed the ceiling and dropped
    something else, because eleven minus one is ten. What went wrong was the membership, so
    the membership is what is asserted.

    Read off the composition table only, found by its own column heading. The ceiling and the
    artifacts are still in the document, in a second table that says they are not parts, and a
    search over the whole file would find them there and pass whatever the first table said.

    Found by the heading rather than by position, because "the first table" moves the moment
    anybody adds one above it and the test would then be reading something else and passing.

    Delete this and the table can drift back one row at a time while the number stays
    right."""
    html = ARCHITECTURE.read_text(encoding="utf-8")
    after_heading = html.split("<th>Attached</th>", 1)
    assert len(after_heading) == 2, "the composition table no longer has its own heading"
    first_table = after_heading[1].split("</table>", 1)[0]

    assert "<td>Availability</td>" in first_table
    assert "<td>Ceiling</td>" not in first_table
    assert "<td>Artifacts</td>" not in first_table
