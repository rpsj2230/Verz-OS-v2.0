"""What the agent taught itself: marked, listed, given back, and never over a person's own value.

Task ids: M16.7.1
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain.agents.learned import (
    LEARNABLE_PATHS,
    NotLearnableError,
    give_back_learned,
    learn_field,
    learned_changes,
)
from brain.agents.model import AgentAudience
from brain.agents.template import (
    MANIFEST_PATHS,
    SEALED_PATHS,
    SETTABLE_PATHS,
    FieldSource,
    ManifestIdentity,
    SignedManifest,
    TemplateInstance,
    TemplateManifest,
    install,
    materialise,
    ownership,
    publish,
    set_field,
)
from brain.agents.upgrade import Declines, Resolution, VersionShelf, accept, review
from brain.builder.publish import REACH_PATHS
from brain.connectors.registry import ConnectorRegistry
from brain.knowledge.visibility import Visibility
from brain.tools.registry import ToolRegistry

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT = datetime(2019, 4, 1, 9, 0, tzinfo=UTC)
LATER = datetime(2019, 4, 2, 9, 0, tzinfo=UTC)
KEY = "a-key-for-learned-changes"
TEMPLATE_WORDS = "Answer from the price list and name the document you read."
LEARNED_WORDS = "Answer from the price list, name the document you read and its date."
ADMIN_WORDS = "Answer from the price list and never quote a discount."
ADMIN = "u_admin"
REVIEWER = "u_reviewer"
SRC = Path(__file__).resolve().parents[2] / "src" / "brain"


def _signed(version: int = 1, persona: str = TEMPLATE_WORDS) -> SignedManifest:
    return publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id="learning_target",
                version=version,
                published_by="system",
                display_name="Learning target",
            ),
            persona=persona,
        ),
        key=KEY,
        signed_by="system",
        at=AT,
    )


def _instance(signed: SignedManifest | None = None) -> TemplateInstance:
    return install(signed or _signed(), key=KEY, instance_id="learner", created_by=ADMIN, at=AT)


def test_a_learned_change_is_marked_as_the_agents_own_learning_and_owned_by_who_approved_it() -> (
    None
):
    """The owner of a learned path says a machine wrote it and names the person who agreed, and
    the value in force is the learned one.

    Delete this and a learned change is indistinguishable from an administrator's edit, so
    nothing can list it."""
    signed = _signed()
    changed = learn_field(
        _instance(signed), "persona", LEARNED_WORDS, approved_by=REVIEWER, at=LATER
    )

    owner = ownership(signed, changed)["persona"]
    assert owner.source is FieldSource.LEARNED
    assert (owner.set_by, owner.set_at) == (REVIEWER, LATER)
    effective = materialise(
        signed, changed, audience=AgentAudience(level=Visibility.COMPANY, owner_id=ADMIN)
    )
    assert effective.record.persona == LEARNED_WORDS


@pytest.mark.parametrize("path", [one for one in MANIFEST_PATHS if one not in LEARNABLE_PATHS])
def test_learning_may_change_the_instructions_and_nothing_else_of_what_an_agent_is(
    path: str,
) -> None:
    """Every other manifest path, the reach and the supervision among them, is refused in words.

    Delete this and a learned change can widen a ceiling or loosen a leash, with the instructions
    as the only thing anybody checks."""
    with pytest.raises(NotLearnableError, match="not something learning may change"):
        learn_field(_instance(), path, "x", approved_by=REVIEWER, at=LATER)


def test_the_learnable_paths_are_settable_never_reach_and_never_sealed() -> None:
    """The tuple is the instructions, inside the paths an install may set and outside the ones that
    decide what an agent may reach and every sealed one.

    Delete this and a path is added to what learning may change without anybody asking whether it
    can reach more than the agent did, or whether the ledger names who approved it."""
    assert LEARNABLE_PATHS == ("persona",)
    assert set(LEARNABLE_PATHS) <= set(SETTABLE_PATHS)
    assert not set(LEARNABLE_PATHS) & REACH_PATHS
    assert not set(LEARNABLE_PATHS) & set(SEALED_PATHS)


def test_a_learned_change_never_replaces_what_a_person_set() -> None:
    """Instructions an administrator set are refused, in words, and stay as they were. The path
    the administrator never touched, and a value learning wrote earlier, are accepted.

    Delete this and giving a learned change back can destroy an administrator's decision, or the
    old value has to be kept beneath it as a second record of the agent."""
    signed = _signed()
    by_a_person = set_field(_instance(signed), "persona", ADMIN_WORDS, by=ADMIN, at=AT)

    with pytest.raises(NotLearnableError, match="set by a person"):
        learn_field(by_a_person, "persona", LEARNED_WORDS, approved_by=REVIEWER, at=LATER)
    assert by_a_person.overlay["persona"] == ADMIN_WORDS

    first = learn_field(_instance(signed), "persona", LEARNED_WORDS, approved_by=REVIEWER, at=AT)
    again = learn_field(
        first, "persona", LEARNED_WORDS + " Again.", approved_by="u_second", at=LATER
    )
    assert again.overlay["persona"] == LEARNED_WORDS + " Again."
    assert ownership(signed, again)["persona"].set_by == "u_second"


def test_what_the_agent_taught_itself_is_listed_apart_from_what_an_administrator_set() -> None:
    """The list holds the learned path and its approver and time, and a path an administrator set
    is never on it. An agent that learned nothing lists nothing.

    Delete this and a person cannot see what the agent taught itself without reading every
    overridden field, or is shown an administrator's edit as the machine's."""
    signed = _signed()
    taught = learn_field(
        _instance(signed), "persona", LEARNED_WORDS, approved_by=REVIEWER, at=LATER
    )
    set_by_a_person = set_field(_instance(signed), "persona", ADMIN_WORDS, by=ADMIN, at=AT)

    [change] = learned_changes(taught)
    assert (change.path, change.value, change.approved_by, change.approved_at) == (
        "persona",
        LEARNED_WORDS,
        REVIEWER,
        LATER,
    )
    assert learned_changes(set_by_a_person) == ()
    assert learned_changes(_instance(signed)) == ()


def test_a_learned_owner_with_no_value_behind_it_lists_nothing() -> None:
    """A forged owner row for a path that is not overlaid is not a learned change, because what
    the agent holds is read from the overlay and the owner only says whose it is.

    Delete this and a stray owner row makes the list claim a change the agent does not hold."""
    forged = _instance().model_copy(
        update={
            "overlay_owners": {
                "persona": ownership(
                    _signed(),
                    learn_field(_instance(), "persona", LEARNED_WORDS, approved_by=REVIEWER, at=AT),
                )["persona"]
            }
        }
    )

    assert learned_changes(forged) == ()


def test_giving_back_a_learned_change_returns_the_template_and_nothing_else() -> None:
    """The learned path goes back to the template's words and owner. A path somebody set, and a path
    nobody changed, are refused rather than quietly given back.

    Delete this and the revert that is about learning can take an administrator's value away."""
    signed = _signed()
    taught = learn_field(
        _instance(signed), "persona", LEARNED_WORDS, approved_by=REVIEWER, at=LATER
    )

    reverted = give_back_learned(taught, "persona")
    effective = materialise(
        signed, reverted, audience=AgentAudience(level=Visibility.COMPANY, owner_id=ADMIN)
    )
    assert effective.record.persona == TEMPLATE_WORDS
    assert ownership(signed, reverted)["persona"].source is FieldSource.TEMPLATE
    assert learned_changes(reverted) == ()

    by_a_person = set_field(_instance(signed), "persona", ADMIN_WORDS, by=ADMIN, at=AT)
    with pytest.raises(NotLearnableError, match="taught itself"):
        give_back_learned(by_a_person, "persona")
    with pytest.raises(NotLearnableError):
        give_back_learned(_instance(signed), "persona")


def test_a_learned_value_kept_through_an_upgrade_stays_learned() -> None:
    """Keeping a learned local value on an upgrade keeps its owner, so it is still listed after
    the agent moves to a new version; taking the template's gives it back.

    Delete this and an upgrade quietly turns what the agent taught itself into something nobody
    can list."""
    first = _signed()
    second = _signed(version=2, persona="Answer from the price list, briefly.")
    taught = learn_field(_instance(first), "persona", LEARNED_WORDS, approved_by=REVIEWER, at=LATER)
    shelf = VersionShelf()
    shelf.publish(first)
    shelf.publish(second)
    reviewed = review(taught, shelf=shelf, declines=Declines())

    def accepted(how: Resolution) -> TemplateInstance:
        return accept(
            reviewed,
            resolutions={"persona": how},
            key=KEY,
            audience=AgentAudience(level=Visibility.COMPANY, owner_id=ADMIN),
            registry=ConnectorRegistry(),
            tools=ToolRegistry(),
            by=ADMIN,
            at=LATER,
        ).instance

    assert [one.path for one in learned_changes(accepted(Resolution.KEEP_LOCAL))] == ["persona"]
    assert learned_changes(accepted(Resolution.TAKE_TEMPLATE)) == ()


def test_the_only_source_that_writes_a_learned_owner_is_the_learning_door() -> None:
    """Parsed from the source: the one call that names `FieldSource.LEARNED` as a value's source is
    `brain.agents.learned.learn_field`'s, so a learning that wrote an agent any other way would be a
    person's edit as far as anybody could tell.

    Delete this and a second writer is added that marks nothing, or marks what a person set."""
    allowed = {SRC / "agents" / "learned.py"}
    found: set[Path] = set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                value = keyword.value
                if (
                    keyword.arg == "source"
                    and isinstance(value, ast.Attribute)
                    and value.attr == "LEARNED"
                ):
                    found.add(path)

    assert found == allowed


def test_the_prompts_screens_view_says_who_wrote_the_instructions_and_whether_a_machine_did() -> (
    None
):
    """The view of the instructions in force carries the source of the value and whether it was the
    agent's own learning: the template's words are neither, an administrator's are an instance's and
    not a machine's, a learned change is a machine's, and the person named is the one who set it
    or approved it.

    Delete this and the Prompts screen can show a learned change as an administrator's edit, or an
    administrator's as the agent's, with every other test green."""
    from brain.prompt_routes import instructions_view

    signed = _signed()
    audience = AgentAudience(level=Visibility.COMPANY, owner_id=ADMIN)

    def seen(instance: TemplateInstance) -> tuple[str, bool, str]:
        record = materialise(signed, instance, audience=audience).record
        view = instructions_view(record, (signed, instance), effective_hash="h", editable=True)
        return view.source or "", view.machine_authored, view.set_by or ""

    template = seen(_instance(signed))
    by_a_person = seen(set_field(_instance(signed), "persona", ADMIN_WORDS, by=ADMIN, at=LATER))
    learned = seen(
        learn_field(_instance(signed), "persona", LEARNED_WORDS, approved_by=REVIEWER, at=LATER)
    )

    assert template[:2] == ("template", False)
    assert by_a_person == ("instance", False, ADMIN)
    assert learned == ("learned", True, REVIEWER)
