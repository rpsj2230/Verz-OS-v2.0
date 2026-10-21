"""Choosing which agent answers, in a fixed order, without asking a model.

Four stages, tried in order, and the order encodes who decided.

0. **The agent the person addressed.** Somebody named an agent they may use, in the web
   application or by mention in a chat. That is the asker deciding about this one question,
   and nothing configured for the conversation can overrule it.
1. **A channel binding.** Somebody configured this chat to talk to this agent. That is an
   explicit human decision about this exact conversation and it outranks everything below.
2. **A rule.** A pattern an administrator wrote once, covering many conversations.
3. **A cheap classifier.** Nobody decided; the system is guessing, deterministically.

Each stage is more specific than the one below it, so a more specific decision always wins.
Reversing that would mean a broad rule silently overriding the binding somebody set for one
team, and the person who set it would have no way to see why it stopped working.

**Visibility is checked at every stage, and a failure to see is silent.** An agent the
caller cannot see is skipped, and selection falls through as though the binding or rule were
not there. Saying "that agent is not available to you" would confirm it exists, which is the
same mistake as a refusal that explains itself. The real reason goes in the trace.

**An agent the person may not use, addressed by name, answers as one that does not exist.**
Both fall through to the binding, the rules and the classifier by the same line, so the
selection is identical whichever it was, and the reason never repeats the name.

**No model is called here.** Same reasoning as lane classification: a round trip on every
request, and text inside a retrieved document could otherwise choose which agent, and
therefore which tools, handle the question.

**A task started with no agent named is matched to what each agent is for (M40.7.5).** Stage 3
also reads the words an agent was given, its name and its instruction, which are the agent's own
statement of what it is for and are chosen by whoever built it. The question picks the visible
agent it shares the most distinct words with, and only if it shares at least `MIN_SHARED_WORDS`
and no other agent shares as many. A tie, or nothing shared, falls through to the fixed keywords
and then the default, because two equally good guesses is nobody deciding. Rejected: asking a model
which agent fits, for the reason this module gives about the classifier, and a tie broken on the
agent id, which would make one agent win every question two of them fit and nobody could see why.
It reads only agents already in `visible_agents`, so it can never choose one the person may not
call, and it is handed the words by the caller rather than reading any store.

Task ids: M3.6.2, M40.7.5
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from brain.gate.context import Channel


class SelectionStage(StrEnum):
    """Which stage chose, recorded so a trace can say who decided rather than what ran."""

    #: The person named an agent they may use (M3.6.2, M3.9.8).
    ADDRESSED = "addressed"
    BINDING = "binding"
    RULE = "rule"
    CLASSIFIER = "classifier"
    DEFAULT = "default"


@dataclass(frozen=True)
class AgentBinding:
    """A conversation wired to an agent by a person.

    `conversation_id` is optional so a binding can cover a whole channel or one group chat.
    A binding naming a conversation is more specific than one naming only a channel, and
    beats it.
    """

    channel: Channel
    agent_id: str
    conversation_id: str | None = None

    @property
    def specificity(self) -> int:
        return 1 if self.conversation_id is None else 2


@dataclass(frozen=True)
class SelectionRule:
    """A pattern an administrator wrote, mapping a question shape to an agent.

    `priority` breaks ties explicitly. Relying on list order works until someone reorders
    the list for readability and changes behaviour without meaning to.
    """

    pattern: re.Pattern[str]
    agent_id: str
    priority: int = 0


@dataclass(frozen=True)
class AgentSelection:
    """Which agent, which stage chose it, and why, in words.

    The reason is written here rather than reconstructed later, for the same reason the lane
    decision is: re-deriving it means re-running a selector that may have changed since, and
    the trace would then explain a decision that was never made.
    """

    agent_id: str
    stage: SelectionStage
    reason: str


#: Entity keywords the cheap classifier knows. Deliberately small: a classifier that tries
#: to cover everything becomes a thing nobody can predict, and the default is a perfectly
#: good answer for a question that matches nothing.
CLASSIFIER_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "support": ("ticket", "tickets", "support", "sla", "complaint"),
    "finance": ("invoice", "invoiced", "billing", "payment", "overdue", "quote"),
    "delivery": ("hosting", "domain", "renewal", "expiry", "deploy", "launch"),
}


def _visible(agent_id: str, visible_agents: frozenset[str]) -> bool:
    return agent_id in visible_agents


#: The fewest distinct words an agent's description must share with a question to be chosen for
#: it. One shared word is how "invoice" matches an agent that happens to mention invoices once.
MIN_SHARED_WORDS: Final = 2

#: Words too common to say what anything is for. A short list on purpose: a longer one is a
#: second vocabulary to keep, and the length floor below already drops most small words.
COMMON_WORDS: Final[frozenset[str]] = frozenset(
    {
        "about",
        "after",
        "again",
        "also",
        "answer",
        "answers",
        "because",
        "been",
        "before",
        "could",
        "does",
        "each",
        "from",
        "have",
        "help",
        "into",
        "just",
        "like",
        "make",
        "more",
        "much",
        "need",
        "only",
        "other",
        "please",
        "should",
        "some",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "what",
        "when",
        "where",
        "which",
        "will",
        "with",
        "would",
        "your",
    }
)

#: Words shorter than this say too little to match on.
SHORTEST_WORD: Final = 4


def _purpose_words(text: str) -> frozenset[str]:
    """The distinct words of a text that can say what something is for."""
    return frozenset(
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) >= SHORTEST_WORD and word not in COMMON_WORDS
    )


def purpose_match(
    question: str, profiles: Mapping[str, str], visible_agents: frozenset[str]
) -> tuple[str, int] | None:
    """The one visible agent whose words the question shares most, and how many, or None.

    None when no agent shares `MIN_SHARED_WORDS`, and None when two share the same most: see the
    module docstring. Only visible agents are read, so the result is never one the person may not
    call, and nothing about the others is said.
    """
    asked = _purpose_words(question)
    scored = sorted(
        (
            (len(asked & _purpose_words(text)), agent_id)
            for agent_id, text in profiles.items()
            if _visible(agent_id, visible_agents)
        ),
        key=lambda pair: (-pair[0], pair[1]),
    )
    if not scored or scored[0][0] < MIN_SHARED_WORDS:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1], scored[0][0]


def select_agent(
    question: str,
    channel: Channel,
    *,
    visible_agents: frozenset[str],
    default_agent: str,
    bindings: Iterable[AgentBinding] = (),
    rules: Iterable[SelectionRule] = (),
    conversation_id: str | None = None,
    keywords: Mapping[str, tuple[str, ...]] = CLASSIFIER_KEYWORDS,
    addressed: str | None = None,
    profiles: Mapping[str, str] | None = None,
) -> AgentSelection:
    """Pick an agent. Deterministic, and never a model call.

    `default_agent` is required rather than defaulted, because a selector that can return
    "no agent" pushes the empty case onto every caller, and the caller that forgets it
    produces a request with no agent and no error.

    `addressed` is the id of the agent the person named, already resolved from what they
    typed. Resolving a name to an id is the channel's job; deciding whether they may use it
    is this function's, and it decides with the same `visible_agents` every stage uses.
    """
    # 0. The agent the person addressed, when they may use it. One they may not use and one
    # that does not exist both fall through here, so nothing below can tell the two apart.
    if addressed is not None and _visible(addressed, visible_agents):
        return AgentSelection(
            agent_id=addressed,
            stage=SelectionStage.ADDRESSED,
            reason=f"the person addressed {addressed}",
        )

    # 1. Bindings, most specific first. A conversation binding beats a channel binding, and
    # ties break on the agent id so the result cannot depend on iteration order.
    for binding in sorted(
        (b for b in bindings if b.channel is channel),
        key=lambda b: (-b.specificity, b.agent_id),
    ):
        if binding.conversation_id is not None and binding.conversation_id != conversation_id:
            continue
        if not _visible(binding.agent_id, visible_agents):
            # Skipped in silence. Saying so would confirm the agent exists.
            continue
        where = "this conversation" if binding.conversation_id else f"the {channel} channel"
        return AgentSelection(
            agent_id=binding.agent_id,
            stage=SelectionStage.BINDING,
            reason=f"{where} is bound to {binding.agent_id}",
        )

    # 2. Rules, by explicit priority then by pattern text, so two rules of equal priority
    # resolve the same way on every run.
    for rule in sorted(rules, key=lambda r: (-r.priority, r.pattern.pattern)):
        if not rule.pattern.search(question):
            continue
        if not _visible(rule.agent_id, visible_agents):
            continue
        return AgentSelection(
            agent_id=rule.agent_id,
            stage=SelectionStage.RULE,
            reason=f"matched the rule {rule.pattern.pattern!r}",
        )

    # 3a. What each visible agent says it is for, when the caller handed those words over (M40.7.5).
    matched = purpose_match(question, profiles or {}, visible_agents)
    if matched is not None:
        agent_id, shared = matched
        return AgentSelection(
            agent_id=agent_id,
            stage=SelectionStage.CLASSIFIER,
            reason=f"{shared} distinct word(s) of the question are what {agent_id} is for",
        )

    # 3. The cheap classifier. Sorted so the result does not depend on mapping order, and
    # scored rather than first-match so a question mentioning one word from one area and
    # three from another lands in the second.
    words = set(re.findall(r"[a-z]+", question.lower()))
    scored = sorted(
        ((sum(1 for k in terms if k in words), agent) for agent, terms in keywords.items()),
        key=lambda pair: (-pair[0], pair[1]),
    )
    if scored and scored[0][0] > 0:
        score, agent_id = scored[0]
        if _visible(agent_id, visible_agents):
            return AgentSelection(
                agent_id=agent_id,
                stage=SelectionStage.CLASSIFIER,
                reason=f"{score} keyword match(es) for {agent_id}",
            )

    return AgentSelection(
        agent_id=default_agent,
        stage=SelectionStage.DEFAULT,
        reason="nothing more specific applied",
    )
