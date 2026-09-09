"""The accumulated learning: why it does not come across, and what does."""

from __future__ import annotations

import pytest

from brain.memory.tiers import BLAST_RADIUS, CHANGES_WHAT_ANYBODY_MAY_SEE, Change, Tier
from brain.migration.learning import (
    THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING,
    Derivation,
    ForeignMemory,
    LearningError,
    derived_twice,
    learning_note,
    re_derive,
)


def a_memory(source_file: str = "memories/priya.md") -> ForeignMemory:
    return ForeignMemory(
        source_file=source_file,
        text="Priya wants project answers as a table with the hours column first",
    )


def a_derivation(
    source_file: str = "memories/priya.md",
    change: Change = Change.PREFERENCE,
    derived_by: str = "u_priya",
) -> Derivation:
    return re_derive(
        a_memory(source_file),
        change=change,
        subject=f"answer shape for {derived_by}",
        derived_by=derived_by,
        because="the file says it three times and she confirmed it in the workshop",
    )


# ------------------------------------------------------- there is no mapping (M37.2.4.1)
def test_a_memory_file_with_no_name_is_refused() -> None:
    """A derivation names the file it came from, so a file with no name is evidence nothing
    can be checked against.

    Delete this and the blank branch is unreachable, and a derivation can cite nothing."""
    with pytest.raises(LearningError, match="names no file"):
        ForeignMemory(source_file="  ", text="something")


def test_a_memory_file_with_nothing_in_it_is_refused() -> None:
    """An empty file is not evidence, and it is what an export produces for a memory the old
    platform had already forgotten.

    Delete this and the note counts files nobody could have read."""
    with pytest.raises(LearningError, match="holds nothing to read"):
        ForeignMemory(source_file="memories/empty.md", text="\n  \n")


# --------------------------------------------- only tier one comes back (M37.2.4.2, .3)
def test_a_preference_re_derived_from_a_file_is_proposed_at_the_tier_its_reach_requires() -> None:
    """**M37.2.4.2, and the tier is not the migrator's to choose.** The proposal is built by
    `brain.memory.tiers.propose`, so the tier comes from the blast radius of the change rather
    than from whoever is running the migration.

    Compared against `BLAST_RADIUS` rather than against `Tier.AUTOMATIC` written here, so
    lowering a change's tier over there moves this too rather than leaving two documents
    disagreeing.

    Delete this and a `tier` parameter can be added to `re_derive`, which is the whole of
    what this module refuses."""
    derivation = a_derivation()

    assert derivation.proposal.change is Change.PREFERENCE
    assert derivation.proposal.tier is BLAST_RADIUS[Change.PREFERENCE]
    assert derivation.source_file == "memories/priya.md"


@pytest.mark.parametrize("change", sorted(CHANGES_WHAT_ANYBODY_MAY_SEE))
def test_no_change_that_alters_who_may_see_what_can_be_re_derived(change: Change) -> None:
    """**M37.2.4.3: discard anything that would widen a scope, because nobody here approved
    it.** A gated change is decided by a person under these rules and nothing on the old
    platform was, so carrying one across is an access decision taken by whoever configured a
    system the company is leaving.

    Parametrised over `CHANGES_WHAT_ANYBODY_MAY_SEE` rather than over a list written here, so
    a change that becomes gated later is refused here on the same day without anybody editing
    this file. There are five today and the parametrisation names them all.

    Delete this and the refusal can be narrowed to `SCOPE_WIDENING`, which leaves capability
    additions and leash increases arriving from a store nobody reviewed."""
    with pytest.raises(LearningError, match="changes who may see what"):
        a_derivation(change=change)


def test_a_tier_two_change_cannot_be_re_derived_because_these_are_not_independent() -> None:
    """**Tier two is promoted once enough independent occurrences agree, and everything here
    comes out of one store.** Derive four from one file and the promotion machinery sees four
    agreeing signals where there is one, which is a promotion built on a single source wearing
    the shape of corroboration.

    Delete this and a migration can seed the promotion queue with corroboration that does not
    exist."""
    with pytest.raises(LearningError, match="promoted rather than proposed"):
        a_derivation(change=Change.FAST_PATH_RULE)


def test_session_context_cannot_be_re_derived_because_that_conversation_ended() -> None:
    """The third refusal and the third argument. Tier zero is true of one conversation, and
    the conversation it was true of ended on another system.

    Delete this and the check can be written as "tier one or two", which admits session
    context and fills the new system with facts about conversations nobody had here."""
    with pytest.raises(LearningError, match="ended on another system"):
        a_derivation(change=Change.SESSION_CONTEXT)


def test_every_tier_one_change_can_be_re_derived() -> None:
    """The positive case, and it is the whole of tier one rather than one member of it,
    because a guard suite made only of refusals is satisfied by a function that refuses
    everything.

    Read from `BLAST_RADIUS` so a new tier-one change is covered the day it is added.

    Delete this and `re_derive` can be tightened to `PREFERENCE` alone, and every retrieval
    demotion in the old store is thrown away with no argument."""
    tier_one = [one for one, tier in BLAST_RADIUS.items() if tier is Tier.AUTOMATIC]

    assert len(tier_one) > 1
    for change in tier_one:
        assert a_derivation(change=change).proposal.change is change


def test_a_change_nothing_classifies_is_refused_rather_than_defaulted() -> None:
    """A change with no blast radius has no tier, and defaulting it would make the tier the
    migrator's choice by another route.

    Built by name rather than by member, because every declared `Change` has a blast radius by
    test and the case only exists for one that stops having one.

    Delete this and a change removed from `BLAST_RADIUS` becomes a silently tier-zero
    migration."""
    unclassified = "not_a_change"

    with pytest.raises(LearningError, match="has no blast radius"):
        re_derive(
            a_memory(),
            change=unclassified,  # type: ignore[arg-type]
            subject="whatever",
            derived_by="u_priya",
            because="testing the miss",
        )


# ------------------------------------------------------------- the derivation is attributed
def test_a_derivation_that_names_nobody_is_refused() -> None:
    """**"Re-derived by the team" is not a fact anybody can check**, and the person is who
    somebody asks about it in six months.

    Delete this and the handover note lists a count of preferences with nobody behind them."""
    with pytest.raises(LearningError, match="names nobody"):
        a_derivation(derived_by="  ")


def test_a_derivation_with_no_reasoning_is_refused() -> None:
    """The file is what makes it evidence and the reasoning is what makes it a derivation.
    Without it the record says a preference came out of a file and not how.

    Delete this and the reasoning column fills itself in from a template."""
    with pytest.raises(LearningError, match="records no reasoning"):
        Derivation(
            proposal=a_derivation().proposal,
            source_file="memories/priya.md",
            derived_by="u_priya",
            because="",
        )


def test_two_people_reading_one_file_is_reported_as_two_opinions_and_not_two_occurrences() -> None:
    """Worth having and worth saying out loud before anybody counts them. The promotion
    machinery counts independent occurrences, and two readings of one file are one occurrence
    read twice.

    Delete this and the one thing that would tell somebody these are not corroboration is
    gone."""
    findings = derived_twice(
        (
            a_derivation(derived_by="u_priya"),
            a_derivation(derived_by="u_sam"),
            a_derivation(source_file="memories/sam.md", derived_by="u_sam"),
        )
    )

    assert findings == (
        "memories/priya.md: read by u_priya and u_sam, which is two opinions and not two "
        "occurrences",
    )


def test_one_reader_per_file_is_not_a_finding() -> None:
    """The positive case.

    Delete this and `derived_twice` can be written to report every file."""
    assert derived_twice((a_derivation(), a_derivation(source_file="memories/sam.md"))) == ()


# ------------------------------------------------------------------ the handover (M37.2.4.4)
def test_the_handover_note_says_plainly_that_the_learning_does_not_come_across() -> None:
    """**M37.2.4.4, and the temptation is to soften it because it reads as a loss.** It is a
    loss and it is the right trade, and the note says both.

    Delete this and the sentence can be rewritten into something that implies the learning
    was migrated, which is the sentence a client remembers."""
    note = learning_note((a_derivation(),), (a_memory(),))

    assert note.sentence == THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING
    assert "starts without the learning" in note.sentence
    assert "the right trade" in note.sentence


def test_every_figure_in_the_note_is_read_off_the_work() -> None:
    """There is no parameter for a count, so a note claiming more than was re-derived cannot
    be written. The readers are named because a note saying how many and not by whom is a note
    nobody can follow up.

    Delete this and the figures become arguments, and the first person to write the handover
    rounds them up."""
    memories = (a_memory(), a_memory("memories/sam.md"), a_memory("memories/unread.md"))
    derivations = (
        a_derivation(derived_by="u_priya"),
        a_derivation(source_file="memories/sam.md", derived_by="u_sam"),
        a_derivation(source_file="memories/sam.md", derived_by="u_priya"),
    )

    note = learning_note(derivations, memories)

    assert note.derived == 3
    assert note.files_read == 2
    assert note.readers == ("u_priya", "u_sam")


def test_a_note_counting_a_file_nobody_exported_is_refused() -> None:
    """A derivation citing a file that is not among the memories handed over is a derivation
    from something nobody can go back to, and the note would count it.

    Delete this and the note's file count can exceed the export, which is a figure in a
    handover document that nothing supports."""
    with pytest.raises(LearningError, match="not among the memory files handed over"):
        learning_note((a_derivation(source_file="memories/ghost.md"),), (a_memory(),))


def test_a_note_with_nothing_re_derived_is_a_real_note() -> None:
    """Zero is the honest answer for a migration where nobody had time to read the old files,
    and the sentence is the same one. Refusing to render it would leave the handover silent
    about the learning, which is the outcome M37.2.4.4 exists to prevent.

    Delete this and the obvious tightening is to require at least one derivation, and a
    migration that carried nothing says nothing about it."""
    note = learning_note((), ())

    assert note.derived == 0
    assert note.readers == ()
    assert note.sentence == THE_SYSTEM_STARTS_WITHOUT_THEIR_ACCUMULATED_LEARNING
