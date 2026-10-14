"""The figures a document of record states are worked out when it is served, and the source
files hold none.

`brain.docs_derived` exists because the sentence that said how many questions were open was a
line every pull request that opened or answered one had to edit, so two of them could not merge
and a conflicted pull request gets no CI. These tests hold both halves: that the generated text
is right, and that nobody can type a figure back into the source, which would bring the conflict
back without any test going red.

Task ids: M0.6.4
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from brain.docs_derived import (
    OPEN_ITEMS_MARKER,
    UNMEASURED,
    ZERO_WORD,
    derived_words,
    in_words,
    open_items,
    open_summary,
    render_architecture,
    render_needs,
)

DOCS = Path(__file__).resolve().parents[2] / "docs"

SAMPLE = """# Needs Rupash

Intro.

<!-- derived: open-items -->

# Open

## 12. Should the first thing happen?

body of twelve

## 7. Which of the two is it?

body of seven

# Answered

## 3. Already decided?

body of three
"""


def test_the_summary_lists_the_open_items_in_the_order_the_document_holds_them() -> None:
    """The list is the headings under Open and nothing from under Answered. Delete this and a
    summary that also listed decided items would state a count nobody could reconcile with the
    page, which is the failure the generated sentence exists to end."""
    assert open_items(SAMPLE) == (
        (12, "Should the first thing happen?"),
        (7, "Which of the two is it?"),
    )


def test_the_summary_states_how_many_are_open_in_the_wording_the_status_test_reads() -> None:
    """`N items are open`, `1 item is open` and `Nothing is open` are the three forms
    `tests/unit/test_status.py` accepts. Delete this and a grammar fix to the plural makes that
    test fail on a wording nobody meant to change, which teaches whoever meets it to bend the
    prose to the pattern."""
    many = open_summary(((12, "a?"), (7, "b?")))
    one = open_summary(((12, "a?"),))
    none = open_summary(())

    assert re.search(r"\*\*2 items are open\.\*\*", many)
    assert re.search(r"\*\*1 item is open\.\*\*", one)
    assert none.startswith("**Nothing is open.**")
    assert "- **12.** a?" in many
    assert "- **7.** b?" in many


def test_the_marker_is_replaced_by_the_summary_and_nothing_else_moves() -> None:
    """The positive case: the sentence appears where the marker was, the marker is gone, and the
    items below are untouched. Delete this and a renderer that dropped the marker without
    writing the sentence passes every other test here."""
    rendered = render_needs(SAMPLE)

    assert OPEN_ITEMS_MARKER not in rendered
    assert "**2 items are open.**" in rendered
    assert "## 12. Should the first thing happen?" in rendered
    assert "body of three" in rendered
    assert rendered.index("**2 items are open.**") < rendered.index("# Open")


def test_a_document_with_no_marker_is_returned_as_it_is() -> None:
    """An old copy of the file must still render. Delete this and a document that predates the
    marker raises or is blanked; the real file losing its marker is caught separately below."""
    plain = "# Needs\n\n# Open\n\n## 1. Only?\n"

    assert render_needs(plain) == plain


def test_the_summary_lists_exactly_what_the_count_counts() -> None:
    """The real document: the number the summary states is the number the status page shows, so
    the badge and the sentence are one fact asked twice. Delete this and a numbered-heading rule
    in one that the other does not share lets them disagree, as they did when the count was a
    running total."""
    from brain.docs_routes import _needs_count

    text = (DOCS / "needs-rupash.md").read_text(encoding="utf-8")

    assert len(open_items(text)) == _needs_count() > 0
    assert f"**{_needs_count()} items are open.**" in render_needs(text)


def test_every_open_item_is_listed_in_the_served_page() -> None:
    """Through the route, not the function: the page a person opens names each open item by its
    number. Delete this and the summary can be computed correctly and never reach the page."""
    from fastapi.testclient import TestClient

    from brain.app import create_app

    text = (DOCS / "needs-rupash.md").read_text(encoding="utf-8")
    page = TestClient(create_app()).get("/build/needs-rupash").text

    assert OPEN_ITEMS_MARKER not in page
    for number, _title in open_items(text):
        assert f"<strong>{number}.</strong>" in page, f"item {number} is open and not listed"


def test_the_needs_source_carries_one_marker_and_no_typed_count() -> None:
    """**The guard on the conflict itself.** Source with the sentence typed back in is green on
    every other test in this repository, because the generated one is correct too, and the lines
    two pull requests edit are back. Asserted on lines rather than substrings: the marker must be
    a line to itself, and no line may open with a bold count of open items. Delete this and the
    next author who finds the page's header bare types a sentence into it."""
    lines = (DOCS / "needs-rupash.md").read_text(encoding="utf-8").splitlines()

    assert len([one for one in lines if one.strip() == OPEN_ITEMS_MARKER]) == 1
    typed = [
        one
        for one in lines
        if re.match(r"\*\*(\d+ items? (are|is) open|Nothing is open)", one.strip())
    ]
    assert typed == [], "a count of open items is typed into the needs document"


def test_every_derived_marker_in_the_architecture_source_is_empty() -> None:
    """A figure typed between the tags would be overwritten by nothing and go stale, and it is
    the line two pull requests would conflict on. Each derived attribute must appear once and
    hold nothing. Delete this and a hand-typed word goes in beside a marker that no longer
    fills it, and the page shows a number the code never worked out."""
    html = (DOCS / "architecture.html").read_text(encoding="utf-8")

    for attribute in derived_words(0):
        found = re.findall(rf'<span data-{attribute}="">([^<]*)</span>', html)
        assert found == [""], f"data-{attribute} is not one empty marker in the source: {found!r}"


def test_the_architecture_fills_each_marker_with_the_figure_the_code_gives() -> None:
    """Rendered with a count handed in, so the open-question word is exactly that count's. The
    other three are compared with the registries the document is about. Delete this and a marker
    that is filled with another's figure passes, because each only has to be some word."""
    from brain.console.screens import SCREEN_COUNT
    from brain.console.workspace import Part
    from brain.ops.controls import orphans

    source = (DOCS / "architecture.html").read_text(encoding="utf-8")
    page = render_architecture(source, 41)

    def stated(attribute: str) -> str:
        found = re.search(rf'<span data-{attribute}="">([^<]*)</span>', page)
        assert found is not None
        return found.group(1)

    assert stated("open-questions") == in_words(41) == "forty-one"
    assert stated("screen-count") == in_words(SCREEN_COUNT)
    assert stated("part-count") == in_words(len(Part))
    assert stated("unwired-controls") == in_words(len(orphans()))


def test_an_open_question_count_of_none_reads_as_none() -> None:
    """The boundary the words have to carry, because the day the last item is answered the page
    must say none and not an empty phrase. Delete this and a zero that renders as nothing reads as
    a missing figure rather than as the best answer."""
    page = render_architecture('<span data-open-questions=""></span>', 0)

    assert page == f'<span data-open-questions="">{ZERO_WORD}</span>'


def test_a_span_with_words_in_it_is_somebodys_prose_and_is_left_alone() -> None:
    """Only an empty span is a marker. Delete this and the renderer overwrites a sentence that
    happens to carry the attribute, which would hide a hand-typed figure from every reader while
    the source test above is what says it is wrong."""
    typed = '<span data-open-questions="">seven</span>'

    assert render_architecture(typed, 3) == typed


def test_a_figure_that_cannot_be_measured_is_said_so_and_not_shown_as_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the controls register cannot be read on a server, the span reads `UNMEASURED` and the
    page still serves. Delete this and an unreadable register becomes either a 500 on the
    architecture page or a silent zero, which in this sentence means every control has a caller."""
    import brain.docs_derived as derived

    def broken() -> str:
        raise OSError("source tree not present")

    monkeypatch.setattr(derived, "derived_words", lambda open_count: {"unwired-controls": broken})
    page = derived.render_architecture('<span data-unwired-controls=""></span>', 5)

    assert page == f'<span data-unwired-controls="">{UNMEASURED}</span>'
    assert "none" not in page


@pytest.mark.parametrize(
    ("n", "words"),
    [(0, "none"), (1, "one"), (56, "fifty-six"), (231, "two hundred and thirty-one")],
)
def test_a_count_is_written_in_words(n: int, words: str) -> None:
    """The words the architecture uses for a count, worked out and not looked up. Delete this and
    a lost hyphen or an off-by-one in the tens is found on the day the count reaches it."""
    assert in_words(n) == words


def test_a_count_outside_what_the_document_writes_in_words_is_refused() -> None:
    """A thousand is outside the range, and the failure names the number rather than printing a
    wrong word. Delete this and an out-of-range count is shown as an empty string."""
    with pytest.raises(ValueError, match="1000"):
        in_words(1000)
