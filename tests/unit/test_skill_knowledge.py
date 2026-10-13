"""A skill names the knowledge it needs, and an assignment the agent cannot serve is refused.

The field is a list of department slugs, held in the digest only when declared. The check against an
agent is `missing_for`, and `assignment` asks it only when handed a registry, which the route does
when `brain.ops.features.SKILL_NEEDS` is on. Each refusal here has the sibling that proves the
thing still works.

Task ids: M12.3.3, M12.4.10
"""

from __future__ import annotations

import pytest

from brain.agents.model import AgentRecord
from brain.agents.template import (
    ManifestAuthority,
    ManifestGuardrails,
    ManifestIdentity,
    SignedManifest,
    TemplateInstance,
    TemplateManifest,
    install,
    materialise,
    publish,
)
from brain.audit.ledger import AuditChain
from brain.console.skill_library import (
    SKILL_AUTHORITY,
    Missing,
    SkillLibraryError,
    assignment,
    missing_for,
)
from brain.core.entitlement import Capability
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.core.scope import Scope
from brain.tools.registry import ToolRegistry
from brain.tools.skills import (
    Skill,
    SkillError,
    markdown_of,
    skill_from_markdown,
)
from tests.unit.test_skill_library import (
    AUDIENCE,
    KEY,
    LONG_AGO,
    NOW,
    _tickets,
    a_recorder,
    a_registry,
    an_approved_skill,
    reach,
    text_with,
)

#: A department no fixture elsewhere names, so a collision cannot make a test pass by accident.
FINANCE = "finance_notes"


def an_agent(
    *, scope: Scope, allowed: tuple[str, ...] = ("crm.read_client",), effect: str = "none"
) -> tuple[SignedManifest, TemplateInstance, AgentRecord]:
    """An installed agent with this scope, these tools and this side-effect ceiling."""
    signed = publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id="pricing_desk",
                version=3,
                published_by="u_publisher",
                display_name="Pricing desk",
                summary="Drafts a first answer to a pricing question.",
            ),
            persona="Answer briefly.",
            authority=ManifestAuthority(
                scope=scope,
                capabilities=(Capability(value="read:client.name"),),
                allowed_tools=allowed,
            ),
            guardrails=ManifestGuardrails(max_side_effect=SideEffect(effect)),
        ),
        key=KEY,
        signed_by="u_publisher",
        at=LONG_AGO,
    )
    instance = install(
        signed,
        key=KEY,
        instance_id="pricing_desk",
        created_by="u_installer",
        at=LONG_AGO,
        overlay={},
    )
    return signed, instance, materialise(signed, instance, audience=AUDIENCE).record


def test_a_skill_that_names_knowledge_reads_back_from_its_file_and_a_bad_name_is_refused() -> None:
    """The file keeps the departments, sorted, and a name that is not a department slug is refused
    by the parser rather than dropped.

    Delete this and a skill's declared need is lost between the file and the library, or a
    misspelt one is read as a need nothing can ever meet."""
    skill = skill_from_markdown(text_with(knowledge=f"[{FINANCE}, accounts]"))
    assert skill.knowledge == ("accounts", FINANCE)
    assert skill_from_markdown(markdown_of(skill)) == skill
    assert f"knowledge: [accounts, {FINANCE}]" in markdown_of(skill)
    with pytest.raises(SkillError):
        skill_from_markdown(text_with(knowledge="[Finance Notes]"))


def test_a_declared_need_is_in_the_digest_and_an_undeclared_one_leaves_it_as_it_was() -> None:
    """A skill with no knowledge digests as it did before the field existed, so no approval is
    voided; one that declares a need digests differently, whatever order the names are given in.

    Delete this and either every approval already granted is voided by a release, or a skill can
    gain a need after its approval and still be the bytes somebody approved."""
    plain = skill_from_markdown(text_with())
    needing = skill_from_markdown(text_with(knowledge=f"[{FINANCE}]"))
    reordered = skill_from_markdown(text_with(knowledge="[b_dept, a_dept]"))
    again = skill_from_markdown(text_with(knowledge="[a_dept, b_dept]"))
    assert plain.knowledge == ()
    assert plain.digest() == Skill.model_validate(plain.model_dump()).digest()
    assert needing.digest() != plain.digest()
    assert reordered.digest() == again.digest()
    assert again.digest() != plain.digest()


def test_a_tool_outside_the_agents_tools_or_above_its_side_effect_ceiling_is_missing() -> None:
    """A skill's tool is missing for an agent that does not name it, for one whose side-effect
    ceiling is below the tool's, and when no registry holds it; the agent that has it is missing
    nothing.

    Delete this and `missing_for` answers nothing for an agent that could never run the skill."""
    registry = a_registry()
    registry.register(
        ToolDefinition(
            name="desk.draft_reply",
            description="Drafts a reply",
            entity="ticket",
            required_capability="write:ticket.status",
            identity_mode=IdentityMode.DELEGATED,
            side_effect=SideEffect.DRAFT,
        ),
        _tickets,
    )
    skill = skill_from_markdown(
        text_with(tools="[crm.read_client, desk.draft_reply, desk.read_ticket, nowhere.read_x]")
    )
    _, _, record = an_agent(
        scope=Scope.unrestricted(), allowed=("crm.read_client", "desk.draft_reply")
    )

    lacks = missing_for(skill, record, registry)

    assert lacks == Missing(tools=("desk.draft_reply", "desk.read_ticket", "nowhere.read_x"))
    _, _, drafting = an_agent(
        scope=Scope.unrestricted(),
        allowed=("crm.read_client", "desk.draft_reply", "desk.read_ticket"),
        effect="draft",
    )
    assert (
        missing_for(
            skill_from_markdown(
                text_with(tools="[crm.read_client, desk.draft_reply, desk.read_ticket]")
            ),
            drafting,
            registry,
        )
        == Missing()
    )


def test_a_department_the_agents_scope_does_not_cover_is_missing_and_no_scope_covers_all() -> None:
    """A skill needing finance is missing for an agent scoped to sales and for none scoped to
    finance, and an unrestricted agent, which narrows nothing, covers every department.

    Delete this and the knowledge half of the refusal is never reached, and a scoped agent is
    given a skill whose documents it cannot read."""
    skill = skill_from_markdown(text_with(knowledge=f"[{FINANCE}]", tools="[crm.read_client]"))
    registry = a_registry()
    for scope, expected in (
        (Scope.department("sales"), Missing(departments=(FINANCE,))),
        (Scope.department(FINANCE), Missing()),
        (Scope.unrestricted(), Missing()),
    ):
        _, _, record = an_agent(scope=scope)
        assert missing_for(skill, record, registry) == expected


def test_an_assignment_the_agent_cannot_serve_is_refused_naming_what_is_missing() -> None:
    """With the registry handed in, a skill whose department the agent lacks is refused with the
    department and the tool in the sentence, and nothing is recorded; the same skill goes to an
    agent that has both, and without a registry the assignment is the one it always was.

    Delete this and the refusal M12.3.3 and M12.4.10 name is a function nobody calls."""
    one = an_approved_skill(text_with(knowledge=f"[{FINANCE}]", tools="[crm.read_client]"))
    registry = a_registry()
    signed, instance, record = an_agent(scope=Scope.department("sales"), allowed=())
    chain = AuditChain()

    with pytest.raises(SkillLibraryError) as refused:
        assignment(
            one,
            record=record,
            signed=signed,
            instance=instance,
            library=(one,),
            by=reach(SKILL_AUTHORITY.value),
            recorder=a_recorder(chain),
            now=NOW,
            needs_registry=registry,
        )
    assert "nothing was assigned" in str(refused.value)
    assert "crm.read_client" in str(refused.value) and FINANCE in str(refused.value)
    assert chain.entries == ()

    # The same skill, with the switch off: assigned as before.
    made = assignment(
        one,
        record=record,
        signed=signed,
        instance=instance,
        library=(one,),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(AuditChain()),
        now=NOW,
    )
    assert made.skill_name == "hosting-expiry"

    # And an agent that has everything it needs is given it with the switch on.
    signed, instance, serving = an_agent(scope=Scope.department(FINANCE))
    served = assignment(
        one,
        record=serving,
        signed=signed,
        instance=instance,
        library=(one,),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(AuditChain()),
        now=NOW,
        needs_registry=registry,
    )
    assert served.agent_id == "pricing_desk"


def test_a_skill_that_needs_nothing_is_never_refused() -> None:
    """A skill naming no knowledge and only tools the agent holds is missing nothing, so switching
    the rule on refuses no skill that was fine.

    Delete this and `Missing` can be truthy for the empty case, refusing every skill once the
    switch is on."""
    needing_nothing = skill_from_markdown(text_with(tools="[]"))
    holding = skill_from_markdown(text_with(tools="[crm.read_client]"))
    _, _, record = an_agent(scope=Scope.department("sales"))
    assert not missing_for(needing_nothing, record, ToolRegistry())
    assert not missing_for(holding, record, a_registry())
    assert missing_for(holding, record, ToolRegistry()).tools == ("crm.read_client",)


# ----------------------------------------------------------- the library keeps the need (0214)
def test_the_need_is_written_with_the_skill_and_read_back_with_it() -> None:
    """`skill_values` writes the departments the file named, and a row read back digests to the
    key it was stored under, so an approval of a skill with a need still holds after a round trip.

    Delete this and a need is dropped between the file and the table, or kept in a form that no
    longer digests to the approved key and the skill stops being executable."""
    from brain.ops.skill_store import library_skill_of, skill_values
    from brain.tables.skill import SkillRow
    from tests.unit.test_skill_library import a_library_skill

    one = a_library_skill(text_with(knowledge=f"[{FINANCE}, accounts]"))
    values = skill_values(one)
    assert values["knowledge"] == ["accounts", FINANCE]
    read = library_skill_of(SkillRow(**values, created_at=NOW), None)
    assert read is not None
    assert read.imported.skill.knowledge == ("accounts", FINANCE)
    assert not read.moved
    assert skill_values(a_library_skill())["knowledge"] == []


def test_0214_emits_the_amendment_the_model_comparison_believes() -> None:
    """`AMENDS_CREATE_TABLE` is a claim the DDL comparison in `tests/unit/test_skill_store.py`
    trusts. The column is emitted with its default and `NOT NULL`, and the check the model declares
    is emitted under the model's name with the model's predicate.

    Delete this and `0214` can say it added a column while its upgrade does not, and every
    comparison built on the claim stays green."""
    from brain.db import Base
    from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

    path = VERSIONS / "0214_skill_knowledge_needs.py"
    emitted = squash(rendered("upgrade", path))
    model = {
        str(one.name): str(one.sqltext)
        for one in Base.metadata.tables["agent.skill"].constraints
        if hasattr(one, "sqltext")
    }
    assert "ALTER TABLE agent.skill ADD COLUMN knowledge JSONB DEFAULT '[]'::jsonb NOT NULL" in (
        emitted
    )
    assert (
        "ALTER TABLE agent.skill ADD CONSTRAINT ck_skill_knowledge_is_a_list "
        f"CHECK ({model['ck_skill_knowledge_is_a_list']})"
    ) in emitted
    assert migration_module(path).TABLES == ()
