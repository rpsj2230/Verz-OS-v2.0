"""What kind of thing a knowledge item is: one word from a closed list, chosen when it is added.

A company's knowledge is not one pile. A standard operating procedure, a pricing note and a
piece of training material answer different questions, age at different rates and are trusted
for different reasons, and a person asking "what is our process for a site handover" wants the
procedure and not the slide deck that once mentioned it. The kind is how that difference is
recorded, shown in the library and used to narrow what a search or an agent reads.

**A closed list, and the list is the owner's.** Twelve kinds, in the order his requirement names
them (M7.6.1). Closed because the kind is a filter, and a filter over free text is a filter over
spelling: "SOP", "sop", "S.O.P." and "procedure" would be four kinds that mean one, and a search
narrowed to one of them silently misses the other three. Adding a kind is a reviewed change to
this enum, to `KIND_LABELS` and to the check constraint migration 0115 writes, and
`tests/unit/test_knowledge_kinds.py` holds the three together.

**Exactly one, set when the item is added, and stored on the item rather than inferred.** A
model guessing the kind from the words was rejected: it would be a classification nobody chose
and nobody is answerable for, and it would move whenever the model did. The person adding the
item chooses, the upload door refuses an upload that names none, and the chunk rows carry a copy
so a narrowed search is one query over one table, in the way `know.chunk` already carries the
title and state it copies from the item.

**A pricing note never holds the price rows themselves.** Prices are rows with a sell price, a
cost and a margin, and M7.5 keeps them as classified table rows so the cost and the margin can be
withheld while the sell price is shown. A price table pasted into a note would be those same
numbers as text, readable by everybody the note reaches, with no column for the redactor to
test. So a pricing note that holds a table is refused, and one uploaded in a format whose tables
this path cannot see is refused too, because the claim that it holds none could not be checked.
See `A_PRICING_NOTE_NEVER_HOLDS_THE_PRICE_ROWS`.

**An approved solution is approved, never uploaded.** M7.6.2 makes a solution company knowledge
only after a named person approves it, and the item records who and when. An upload naming that
kind would be the badge without the approval. See
`AN_APPROVED_SOLUTION_IS_APPROVED_AND_NEVER_UPLOADED`.

Nothing here reads a clock, opens a connection or imports the rest of the knowledge package, so
`brain.knowledge.item` can import it without a cycle through the chunker.

Task ids: M7.6.1
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

# ------------------------------------------------------------------ written-down reasons
#: Why a pricing note is refused when it holds a table, or when its tables cannot be seen.
A_PRICING_NOTE_NEVER_HOLDS_THE_PRICE_ROWS: Final = (
    "Prices are kept as classified table rows so that cost and margin can be withheld while the "
    "sell price is shown. A price table inside a pricing note would be those numbers as text, "
    "readable by everybody the note reaches and with no column the redactor could test, so a "
    "pricing note holding a table is refused. A pricing note in a format whose tables this path "
    "cannot see is refused as well, because its claim to hold none could not be checked."
)

#: Why an upload may not name the approved-solution kind.
AN_APPROVED_SOLUTION_IS_APPROVED_AND_NEVER_UPLOADED: Final = (
    "A solution becomes company knowledge only after a named person approves it, and the item "
    "records what it solved, who approved it and when. An upload naming that kind would carry "
    "the label with none of the approval behind it, so the kind is set by approving a solution "
    "and never by uploading a file."
)


class KindError(Exception):
    """An item whose kind cannot be what it was declared as.

    Outside the `brain.core.errors` taxonomy like every refusal in this package: those outcomes
    describe an answer to a person, and this describes a refusal to write a row. The person
    refused is the person who chose the kind and the file, so the message may say why.
    """


class KnowledgeKind(enum.StrEnum):
    """The closed list. Values are the words stored in `know.item.kind`; see `KIND_LABELS`."""

    SOP = "sop"
    POLICY = "policy"
    FAQ = "faq"
    PRICING_NOTE = "pricing_note"
    SERVICE_INFORMATION = "service_information"
    SERVICE_PACKAGE = "service_package"
    BRAND_GUIDELINES = "brand_guidelines"
    COMPANY_RULE = "company_rule"
    BEST_PRACTICE = "best_practice"
    TEMPLATE = "template"
    TRAINING_MATERIAL = "training_material"
    APPROVED_SOLUTION = "approved_solution"


#: The order the kinds are offered in, which is the order the owner's requirement lists them.
#: Written out rather than taken from declaration order, for the reason
#: `brain.knowledge.visibility.VISIBILITY_ORDER` is: declaration order is not part of an enum's
#: contract, and a list a person picks from should not reorder itself in a merge.
KIND_ORDER: Final[tuple[KnowledgeKind, ...]] = (
    KnowledgeKind.SOP,
    KnowledgeKind.POLICY,
    KnowledgeKind.FAQ,
    KnowledgeKind.PRICING_NOTE,
    KnowledgeKind.SERVICE_INFORMATION,
    KnowledgeKind.SERVICE_PACKAGE,
    KnowledgeKind.BRAND_GUIDELINES,
    KnowledgeKind.COMPANY_RULE,
    KnowledgeKind.BEST_PRACTICE,
    KnowledgeKind.TEMPLATE,
    KnowledgeKind.TRAINING_MATERIAL,
    KnowledgeKind.APPROVED_SOLUTION,
)

#: What a person reads for each kind, in the console and in a library row.
KIND_LABELS: Final[Mapping[KnowledgeKind, str]] = MappingProxyType(
    {
        KnowledgeKind.SOP: "SOP",
        KnowledgeKind.POLICY: "Policy",
        KnowledgeKind.FAQ: "FAQ",
        KnowledgeKind.PRICING_NOTE: "Pricing note",
        KnowledgeKind.SERVICE_INFORMATION: "Service information",
        KnowledgeKind.SERVICE_PACKAGE: "Service package",
        KnowledgeKind.BRAND_GUIDELINES: "Brand guidelines",
        KnowledgeKind.COMPANY_RULE: "Company rule",
        KnowledgeKind.BEST_PRACTICE: "Best practice",
        KnowledgeKind.TEMPLATE: "Template",
        KnowledgeKind.TRAINING_MATERIAL: "Training material",
        KnowledgeKind.APPROVED_SOLUTION: "Approved solution",
    }
)

#: The width of the column a kind is stored in, on `know.item` and on `know.chunk`. The longest
#: value is nineteen characters; the margin is for a kind the owner adds, not for free text.
KIND_CHARS: Final = 32

#: The kinds no upload may name. One today, and a set so the door asks one question.
NOT_UPLOADED: Final[frozenset[KnowledgeKind]] = frozenset({KnowledgeKind.APPROVED_SOLUTION})


def uploadable_kinds() -> tuple[KnowledgeKind, ...]:
    """The kinds the upload door offers, in `KIND_ORDER`."""
    return tuple(kind for kind in KIND_ORDER if kind not in NOT_UPLOADED)


def assert_uploadable(kind: KnowledgeKind) -> None:
    """Refuse a kind that is set by another path. See the module docstring."""
    if kind in NOT_UPLOADED:
        msg = (
            f"{KIND_LABELS[kind]} is not a kind an upload can carry. "
            f"{AN_APPROVED_SOLUTION_IS_APPROVED_AND_NEVER_UPLOADED}"
        )
        raise KindError(msg)


def assert_kind_holds(
    kind: KnowledgeKind, *, holds_a_table: bool, tables_are_visible: bool
) -> None:
    """Refuse an item whose content contradicts its kind (M7.6.1).

    Two facts about the parsed content rather than the content itself, so this module never
    holds a document and cannot import the chunker: whether a table was found, and whether the
    format's tables could have been found at all. See `A_PRICING_NOTE_NEVER_HOLDS_THE_PRICE_ROWS`.
    """
    if kind is not KnowledgeKind.PRICING_NOTE:
        return
    if holds_a_table:
        msg = (
            "this pricing note holds a table. Keep the price rows in a price list and upload "
            f"the note without them. {A_PRICING_NOTE_NEVER_HOLDS_THE_PRICE_ROWS}"
        )
        raise KindError(msg)
    if not tables_are_visible:
        msg = (
            "a pricing note is accepted as plain text, Markdown or Word, where a table can be "
            "seen and refused; in this format it cannot, so upload the note as one of those. "
            f"{A_PRICING_NOTE_NEVER_HOLDS_THE_PRICE_ROWS}"
        )
        raise KindError(msg)
