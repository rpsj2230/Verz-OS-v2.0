"""Counts a document of record states, worked out when the document is served and never typed.

**Why this module exists: a conflicted pull request gets no CI.** On 2026-10-14 three pull
requests went dirty on the same few lines, each costing thirty to sixty minutes to bring back:
the sentence at the top of `docs/needs-rupash.md` that says how many items are open and lists
them, and the word and the attribute in `docs/architecture.html` that say the same number again.
Every pull request that opened or answered a question edited those lines, so any two of them
conflicted, and none of those edits carried an idea: each was the arithmetic of somebody else's
change, redone by hand and checked by a test that only said the hand was wrong.

So the number is a fact the document is asked for, not a sentence somebody writes. The source
files carry a marker where the figure goes (an empty `<span data-...="">` in the architecture, a
comment line in the needs page) and the route that serves the page fills it from the same
functions the checks already used: `docs_routes._needs_count` for the open items, the screen
registry for the screens, the composition enum for what an agent is made of, the controls
register for how many have no caller.

**Worked out per request, not at build time, and that is a choice.** `deploy.yml` regenerates the
tracker, and the same step could have rewritten these two files. It was rejected for three reasons:
a build step that rewrites a committed file leaves the committed file stale between builds, so
the figure in the repository would still be wrong and still be read (on GitHub, in a clone, in a
review); the pull request that needs the figure right is the one that has not been built; and
a derived page that is also a committed one invites the next author to commit the rewrite and
bring the conflict back. A marker with nothing in it cannot go stale, and two tests in
`tests/unit/test_docs_derived.py` (one per document) fail the day somebody types a figure in.

**A figure that cannot be worked out is shown as such, never as a plausible number.** If the
controls register cannot be read on a server (it reads the source tree), the span says so in
words rather than printing zero, because "none of them has no caller" is a claim and an empty
figure would read as the best possible answer.

**What is not derived, and why.** `data-registered-tools` is a comparison in words, checked by a
test that fails when it stops being true, not a count. `SCREEN_COUNT` is pinned by hand on purpose
(see its own comment): a screen disappearing in a refactor is the failure it exists to catch,
so a derived count there would measure itself.

Rejected: a regular expression over the markdown that rewrites the sentence in place and is run by
a pre-commit hook. It produces the same diff in every pull request that touches an item, which is
exactly the conflict, now written by a tool rather than a person.

Task ids: M0.6.4
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Mapping
from typing import Final

#: What a count is called when the document says it in words. Nought is written as `ZERO_WORD`,
#: as the architecture says it.
ZERO_WORD: Final = "none"

#: Said in place of a figure that could not be worked out. See the module docstring.
UNMEASURED: Final = "an unmeasured number of"

#: The marker line in `docs/needs-rupash.md` that is replaced by the generated summary of what
#: is open. A line to itself, so the markdown renderer never sees it.
OPEN_ITEMS_MARKER: Final = "<!-- derived: open-items -->"

#: The heading that ends the open section. Everything after it has been decided.
ANSWERED_HEADING: Final = "# Answered"

#: An item heading: `## 58. Nine plug-in points ...`.
_ITEM: Final = re.compile(r"^## (\d+)\.\s*(.*?)\s*$")

_UNITS: Final = (
    "",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS: Final = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)


def in_words(n: int) -> str:
    """A count from 0 to 999 as the document writes it: "none", "seven", "thirty-one".

    Worked out rather than looked up. It was a table, and the table ran out three times, each
    time turning a comparison into a `KeyError` that named the table rather than the drift.
    """
    if n == 0:
        return ZERO_WORD
    if not 0 < n < 1000:
        raise ValueError(f"{n} is outside the counts this document writes in words")
    hundreds, rest = divmod(n, 100)
    if rest < 20:
        tail = _UNITS[rest]
    else:
        tens, units = divmod(rest, 10)
        tail = _TENS[tens] + (f"-{_UNITS[units]}" if units else "")
    if not hundreds:
        return tail
    head = f"{_UNITS[hundreds]} hundred"
    return f"{head} and {tail}" if tail else head


# ----------------------------------------------------------------- the needs document
def open_items(text: str) -> tuple[tuple[int, str], ...]:
    """The numbered items still waiting on a decision, in document order, as (number, title).

    Read up to `ANSWERED_HEADING` and no further, which is the rule `docs_routes._needs_count`
    follows and the reason it exists: counting every heading in the file gave the number of
    items ever raised, which could only go up. A `## ` heading with no number is not an item and
    is not listed, but `_needs_count` would count it, and the test that holds the two together
    (`the_summary_lists_exactly_what_the_count_counts`) is what notices if one is ever written.
    """
    found: list[tuple[int, str]] = []
    for line in text.splitlines():
        if line.startswith(ANSWERED_HEADING):
            break
        item = _ITEM.match(line)
        if item is not None:
            found.append((int(item.group(1)), item.group(2)))
    return tuple(found)


def open_summary(items: tuple[tuple[int, str], ...]) -> str:
    """The sentence and the list that open the needs page, from the items themselves.

    The sentence keeps the shape `tests/unit/test_status.py` has always looked for (`N items are
    open`, `1 item is open`, `Nothing is open`) so what a person reads and what a test reads are
    one wording. The list is the item numbers and the questions as the headings put them, in the
    order the document holds them, because a summary written separately from the headings is the
    paragraph that was edited by every pull request.
    """
    if not items:
        return "**Nothing is open.** Every question has been decided; the record is below."
    count = len(items)
    lead = f"**{count} item is open.**" if count == 1 else f"**{count} items are open.**"
    rows = "\n".join(f"- **{number}.** {title}" for number, title in items)
    return (
        f"{lead} Each says in plain terms what it is, what I recommend, and every step. "
        f"The questions, as each item asks them:\n\n{rows}"
    )


def render_needs(text: str) -> str:
    """The needs document with its marker replaced by the summary of what is open.

    A document with no marker is returned as it is, so a copy of the file that predates the
    marker still renders; `tests/unit/test_docs_derived.py` fails if the real one loses it.
    """
    summary = open_summary(open_items(text))
    return "\n".join(
        summary if line.strip() == OPEN_ITEMS_MARKER else line for line in text.split("\n")
    )


# ------------------------------------------------------------------ the architecture page
def _screens() -> str:
    from brain.console.screens import SCREEN_COUNT

    return in_words(SCREEN_COUNT)


def _parts() -> str:
    from brain.console.workspace import Part

    return in_words(len(Part))


@functools.cache
def _unwired() -> str:
    """How many registered controls have no caller of any kind. Cached: it parses the source."""
    from brain.ops.controls import orphans

    return in_words(len(orphans()))


def derived_words(open_count: int) -> Mapping[str, Callable[[], str]]:
    """Each span the architecture derives, by the attribute that marks it.

    The open-question count is passed in rather than read here, so the caller that already read
    the needs document does not read it twice and a test can hand in any number.
    """
    return {
        "open-questions": lambda: in_words(open_count),
        "screen-count": _screens,
        "part-count": _parts,
        "unwired-controls": _unwired,
    }


def _span(attribute: str) -> re.Pattern[str]:
    # Only an empty span is a marker. A span with words in it is somebody's prose, and the test
    # that holds the source to empty markers is what says so, rather than this overwriting it.
    return re.compile(rf'(<span data-{re.escape(attribute)}="">)(</span>)')


def render_architecture(html: str, open_count: int) -> str:
    """The architecture page with every derived span filled in from the code.

    A span whose figure cannot be worked out reads `UNMEASURED`, not zero and not nothing.
    """
    for attribute, work_out in derived_words(open_count).items():
        try:
            word = work_out()
        except Exception:  # a figure that cannot be measured must not take the page down
            word = UNMEASURED
        # A function and not a replacement string, so a word can never be read as a group
        # reference or an escape.
        html = _span(attribute).sub(_filled(word), html)
    return html


def _filled(word: str) -> Callable[[re.Match[str]], str]:
    def fill(found: re.Match[str]) -> str:
        return f"{found.group(1)}{word}{found.group(2)}"

    return fill
