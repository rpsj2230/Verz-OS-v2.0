"""What kinds of the company's data each model provider has been sent, counted from the attempts.

M5.6.4 asks that the console list the categories of data each provider has been sent, with
counts, beside its terms, so a company can show what left for where. The attempt row is written
once per try by the executor that sent it (`brain.models.calls`), so the categories are recorded
on that row at the moment of sending, and the counts are a group-by over rows nobody overwrites.

**A category is a kind, never content.** The closed list below names what the prompt carried,
chosen by the caller that built the prompt (`brain.gate.model_lane` knows whether passages or skill
descriptions went in). Nothing here reads a prompt to classify it: a classifier reading the text
would be a second place the text is kept, and a guess about content stated as a disclosure record.

**Counted per attempt, not per request.** A request that fell back sent the same text to two
providers, and both were sent it; a count per request would leave the second one out of its
provider's record.

Scope: pure. The rows are a parameter.

Task ids: M5.6.4
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Final


class DataCategory(enum.StrEnum):
    """What a prompt sent to a provider carried. Closed: a new kind is a decision, not a string."""

    #: The question a person asked, in their words.
    QUESTION = "question"
    #: Passages from the company's documents, redacted at the asker's reach.
    DOCUMENT_PASSAGES = "document_passages"
    #: The descriptions of the skills an agent may use.
    SKILL_DESCRIPTIONS = "skill_descriptions"
    #: The fixed sentence an administrator's provider check sends. No company data.
    CHECK_SENTENCE = "check_sentence"
    #: A golden question the matrix gate asks before a routing change takes traffic.
    GOLDEN_QUESTION = "golden_question"


#: What each category is called on the console and in the exported record.
TOLD: Final[Mapping[DataCategory, str]] = MappingProxyType(
    {
        DataCategory.QUESTION: "Questions people asked",
        DataCategory.DOCUMENT_PASSAGES: "Passages from company documents, redacted per asker",
        DataCategory.SKILL_DESCRIPTIONS: "Descriptions of an agent's skills",
        DataCategory.CHECK_SENTENCE: "The fixed provider-check sentence (no company data)",
        DataCategory.GOLDEN_QUESTION: "Golden questions asked before a routing change",
    }
)


def categories_of(values: Iterable[str]) -> tuple[DataCategory, ...]:
    """Stored values as categories, in the enum's order, dropping any this release does not know.

    Dropped rather than raised: a row written by a later release is still a row, and refusing to
    count the rest of it would lose a disclosure over a word.
    """
    known = {one.value for one in DataCategory}
    present = {value for value in values if value in known}
    return tuple(one for one in DataCategory if one.value in present)


def counted(rows: Iterable[tuple[str, Iterable[str]]]) -> Mapping[str, Mapping[DataCategory, int]]:
    """Per provider, how many attempts carried each category. From (provider, categories) rows."""
    found: dict[str, dict[DataCategory, int]] = {}
    for provider, values in rows:
        per = found.setdefault(provider, {})
        for category in categories_of(values):
            per[category] = per.get(category, 0) + 1
    return MappingProxyType({key: MappingProxyType(value) for key, value in found.items()})
