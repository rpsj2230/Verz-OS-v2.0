"""A card says what changed since the last approved run, and says nothing it did not look up.

Pure: the previous envelope is the sealed parts a row would hold (`envelope_store.sealed_parts`),
and the current one is compiled from a plan. What reads the previous row from the database is the
install check (`test_acceptance_checks_browser_changes.py`).

Task ids: M19.7.2, M19.9.2
"""

from __future__ import annotations

from datetime import UTC, datetime

from brain.browsing.approval import (
    CHANGES_ARGUMENT,
    FIRST_APPROVAL,
    MAX_CHANGES_CHARS,
    NOTHING_CHANGED,
    Previous,
    approval_action,
    envelope_changes,
    raise_approval,
)
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.envelope_store import sealed_parts
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, BROWSE_SURFACE
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
ORIGIN = "https://books.example"
OTHER = "https://filing.example"


def books(*, filing: tuple[Verb, ...] = (Verb.OPEN, Verb.SUBMIT)) -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN, OTHER}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=BROWSE_SURFACE,
                reads=("number",),
            ),
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset(filing),
                capability=ACT_ON_SURFACE_CAPABILITY,
            ),
            Surface(
                name="payroll",
                origin=OTHER,
                path="/payroll",
                verbs=frozenset({Verb.OPEN, Verb.CLICK}),
                capability=ACT_ON_SURFACE_CAPABILITY,
            ),
        ),
    )


def reach() -> EntitlementSet:
    return EntitlementSet(
        principal_id="alex",
        grants=(
            Grant(capability=BROWSE_SURFACE, scope=Scope.unrestricted()),
            Grant(capability=ACT_ON_SURFACE_CAPABILITY, scope=Scope.unrestricted()),
        ),
    )


def compiled(*surfaces: str) -> Envelope:
    target = books()
    return compile_envelope(
        plan(
            PlanRequest(
                goal=Goal(text="File the return", asked_by="alex"),
                target="books",
                surfaces=surfaces,
            ),
            TargetRegistry(targets=(target,)),
        ),
        target,
        run_id="run-1",
        reach=reach(),
        ceiling=AutonomyTier.AUTONOMOUS,
    )


def last(*surfaces: str) -> Previous:
    return Previous(sealed_parts(compiled(*surfaces)))


def test_a_first_approval_says_so_and_a_repeat_says_nothing_differs() -> None:
    """The two ends. Delete this and a card for a repeated run reads like a new one, which is the
    list the person has stopped reading."""
    assert envelope_changes(Previous(None), compiled("invoices", "filing")) == FIRST_APPROVAL
    assert envelope_changes(last("invoices", "filing"), compiled("invoices", "filing")) == (
        NOTHING_CHANGED
    )


def test_a_write_that_is_new_is_added_and_one_that_is_gone_is_dropped() -> None:
    """Delete this and the card lists writes without saying which are new."""
    added = envelope_changes(last("invoices"), compiled("invoices", "filing"))
    dropped = envelope_changes(last("invoices", "filing"), compiled("invoices"))

    assert "adds filing submit x1" in added and "drops" not in added
    assert "drops filing submit x1" in dropped and "adds" not in dropped


def test_a_write_done_fewer_times_than_before_is_dropped_and_not_added() -> None:
    """Counts, not names: a write kept but done twice before and once now is a drop. A plan names a
    surface once, so the count before is built here from sealed parts. Delete this and the sentence
    only notices a write appearing or going, or reports a lowered count as an addition."""
    twice = dict(sealed_parts(compiled("filing")))
    twice["steps"] = [*twice["steps"], ["filing", "submit"]]

    said = envelope_changes(Previous(twice), compiled("filing"))

    assert "drops filing submit x1" in said and "adds" not in said


def test_a_read_that_is_new_is_not_mentioned() -> None:
    """Reads never wait, so a card about reads teaches approvers to stop reading. Delete this and
    a new read step is reported as a change."""
    assert envelope_changes(last("filing"), compiled("invoices", "filing")) == NOTHING_CHANGED


def test_an_origin_that_is_new_or_gone_is_named() -> None:
    """An envelope allows the target's origins, so a difference is a target that was widened or
    narrowed between the two runs. Delete this and a run that now reaches another website says
    only that nothing was added to the writes."""
    parts = dict(sealed_parts(compiled("filing")))
    wider_before = {**parts, "origins": [ORIGIN]}
    narrower_before = {**parts, "origins": [ORIGIN, OTHER, "https://gone.example"]}

    wider = envelope_changes(Previous(wider_before), compiled("filing"))
    narrower = envelope_changes(Previous(narrower_before), compiled("filing"))

    assert OTHER in wider and "as well" in wider
    assert "gone.example" in narrower and "no longer reaches" in narrower


def test_a_write_that_ran_unattended_before_is_not_one_that_waited() -> None:
    """The previous run's writes that a signed exception let through were never on a card. Delete
    this and they are reported as dropped, as though the person had approved them."""
    parts = dict(sealed_parts(compiled("filing")))
    parts["unattended"] = [["filing", "submit"]]

    assert "adds filing submit x1" in envelope_changes(Previous(parts), compiled("filing"))


def test_the_sentence_is_cut_to_the_most_a_card_line_holds() -> None:
    """Delete this and an envelope with a hundred origins writes a card nobody can read."""
    many = dict(sealed_parts(compiled("filing")))
    many["origins"] = [f"https://site-{n}.example" for n in range(200)]

    said = envelope_changes(Previous(many), compiled("filing"))

    assert len(said) <= MAX_CHANGES_CHARS and said.endswith("...")


def test_a_card_says_what_changed_only_when_a_previous_was_looked_up() -> None:
    """Delete this and a card for a caller that never looked says it is a first approval, which
    would be false."""
    envelope = compiled("filing")

    assert CHANGES_ARGUMENT not in approval_action(envelope, books(), agent_id="a").args
    looked = approval_action(envelope, books(), agent_id="a", previous=Previous(None))
    assert looked.args[CHANGES_ARGUMENT] == FIRST_APPROVAL


def test_the_difference_is_in_the_digest_the_approval_binds_to_and_on_the_card() -> None:
    """Delete this and a card whose difference was edited after it was shown is the same action,
    or the difference is computed and never shown."""
    envelope = compiled("filing")
    unseen = approval_action(envelope, books(), agent_id="a", previous=Previous(None))
    seen = approval_action(envelope, books(), agent_id="a", previous=last("filing"))

    assert unseen.digest() != seen.digest()
    suspension = raise_approval(
        envelope, books(), agent_id="a", reach=reach(), trace_id="t", now=NOW,
        previous=last("invoices"),
    )  # fmt: skip
    assert "changes: since the last approved run it adds filing submit x1" in suspension.artefact
