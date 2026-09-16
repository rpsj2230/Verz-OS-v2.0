"""The skill library's decisions: what a package may be, who may decide, what a skill reaches, and
what assigning one writes.

Everything here is `brain.console.skill_library` called directly, with real skills parsed from real
text, real archives built in memory, a real tool registry, and a real template published, installed
and materialised, so each assertion is about what the platform's own types do with the value rather
than about a stand-in built to agree.

**Every refusal has a sibling proving the permitted case goes through**, which is CLAUDE.md's rule
about a guard tested only by its refusals: a function that refused everything would pass every
refusal below.

Task ids: M42.6.4
"""

from __future__ import annotations

import hashlib
import inspect
import io
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.agents.template import (
    ManifestAuthority,
    ManifestIdentity,
    SignedManifest,
    SkillRef,
    TemplateInstance,
    TemplateManifest,
    install,
    materialise,
    publish,
)
from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import AuditRecorder
from brain.console import skill_library as library_module
from brain.console.agent_tabs import AgentTabError
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.skill_library import (
    A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED,
    ASSIGN_REASON,
    MAX_PACKAGE_BYTES,
    NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED,
    REPLACE_REASON,
    REVIEW_AUTHORITY,
    SKILL_AUTHORITY,
    SKILLS_PATH,
    LibrarySkill,
    SkillLibraryError,
    ToolReach,
    added,
    another_spelling,
    assignment,
    decided,
    ledger_reference,
    may_add,
    may_assign,
    may_read_library,
    may_review,
    moved_authority,
    queue_entries,
    reach_through,
    read_package,
    trusted_reach,
)
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.tools.registry import ToolRegistry
from brain.tools.skills import Skill, SkillState, SourceKind

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
KEY = "a-key-for-this-test"
AGENT = "pricing_desk"
IMPORTER = "u_importer"
REVIEWER = "u_reviewer"

#: One, zero, zero in Arabic-Indic digits, which `\d` matches and 0 to 9 does not.
OTHER_DIGITS = ".".join(chr(code) for code in (0x661, 0x660, 0x660))

SKILL_READ = screen("skills").read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)

SKILL_MD = """---
name: hosting-expiry
description: Checks whether a client domain is close to renewal
version: 1.0.0
tools: [crm.read_client, desk.read_ticket]
---
Look up the domain, then open a ticket.
"""


def text_with(**lines: str) -> str:
    """The sample `SKILL.md` with some frontmatter lines replaced or added."""
    fields = {
        "name": "hosting-expiry",
        "description": "Checks whether a client domain is close to renewal",
        "version": "1.0.0",
        "tools": "[crm.read_client, desk.read_ticket]",
    }
    fields.update(lines)
    head = "\n".join(f"{key}: {value}" for key, value in fields.items())
    return f"---\n{head}\n---\nLook up the domain, then open a ticket.\n"


def a_zip(members: dict[str, bytes], *, mode: int | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name)
            if mode is not None:
                info.external_attr = mode << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def reach(
    *capabilities: str, principal: str = "u_admin", scope: Scope | None = None
) -> EntitlementSet:
    """A caller holding the Skills screen and these capabilities, all at `scope`."""
    held = scope if scope is not None else Scope.unrestricted()
    return EntitlementSet(
        principal_id=principal,
        grants=(
            Grant(capability=SKILL_READ, scope=Scope.unrestricted()),
            Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
            *(Grant(capability=Capability(value=one), scope=held) for one in capabilities),
        ),
    )


def a_library_skill(
    text: str = SKILL_MD, *, by: str = IMPORTER, at: datetime = NOW
) -> LibrarySkill:
    return added(read_package("SKILL.md", text.encode("utf-8")), by=by, at=at)


def an_approved_skill(text: str = SKILL_MD) -> LibrarySkill:
    return decided(a_library_skill(text), reviewer=REVIEWER, approve=True, at=NOW)


# ------------------------------------------------------------------------- the registry
class ClientRow(Entity):
    """One row a client tool returns."""


class TicketRow(Entity):
    """One row a ticket tool returns."""


def _clients() -> TypedResult[ClientRow]:
    return TypedResult[ClientRow]()


def _tickets() -> TypedResult[TicketRow]:
    return TypedResult[TicketRow]()


def a_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="crm.read_client",
            description="Reads a client's name",
            entity="client",
            required_capability="read:client.name",
            identity_mode=IdentityMode.DELEGATED,
            side_effect=SideEffect.NONE,
        ),
        _clients,
    )
    registry.register(
        ToolDefinition(
            name="desk.read_ticket",
            description="Reads a ticket's status",
            entity="ticket",
            required_capability="read:ticket.status",
            identity_mode=IdentityMode.DELEGATED,
            side_effect=SideEffect.NONE,
        ),
        _tickets,
    )
    return registry


# ---------------------------------------------------------------------- the agent install
AUDIENCE = AgentAudience(level=Visibility.COMPANY, owner_id="u_steward")


def an_install(
    *, skills: tuple[SkillRef, ...] = (), allowed: tuple[str, ...] = ("crm.read_client",)
) -> tuple[SignedManifest, TemplateInstance, AgentRecord]:
    """A template published, installed and materialised, whose ceiling reads client names."""
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
            skills=skills,
            authority=ManifestAuthority(
                capabilities=(Capability(value="read:client.name"),), allowed_tools=allowed
            ),
        ),
        key=KEY,
        signed_by="u_publisher",
        at=LONG_AGO,
    )
    instance = install(
        signed, key=KEY, instance_id=AGENT, created_by="u_installer", at=LONG_AGO, overlay={}
    )
    record = materialise(signed, instance, audience=AUDIENCE).record
    return signed, instance, record


def a_recorder(chain: AuditChain) -> AuditRecorder:
    return AuditRecorder(
        chain, actor_id="u_admin", ent_hash="0" * 32, trace_id="trace-skill", clock=lambda: NOW
    )


# ------------------------------------------------------------------- adding a skill (import)
def test_a_pasted_skill_md_becomes_an_undecided_skill_whose_bytes_are_digested() -> None:
    """The positive case for every refusal below: a paste parses into the skill it describes, its
    source is an upload whose digest is over the bytes that arrived, and it is added imported, by
    a named person, with no reviewer and no approved digest.

    Delete this and every refusal here is satisfied by a reader that refuses everything, and the
    one path that makes a skill arrive approved has nothing watching it."""
    raw = SKILL_MD.encode("utf-8")

    one = a_library_skill()

    assert one.imported.skill.name == "hosting-expiry"
    assert one.imported.skill.tools == ("crm.read_client", "desk.read_ticket")
    assert one.imported.source.kind is SourceKind.UPLOAD
    assert one.imported.source.location == "SKILL.md"
    assert one.imported.source.content_digest == hashlib.sha256(raw).hexdigest()
    assert one.imported.state is SkillState.IMPORTED
    assert (one.imported.reviewer, one.imported.approved_digest) == ("", "")
    assert one.imported.is_executable() is False
    assert one.digest == one.imported.skill.digest()
    assert one.submitted_by == IMPORTER
    assert one.moved is False


def test_a_zip_holding_only_its_skill_md_is_read_in_memory() -> None:
    """A package uploaded as an archive is the same skill as its `SKILL.md` pasted.

    Delete this and the archive path can refuse every archive, or read a different member, and
    only the paste is ever proved to work."""
    archive = a_zip({"hosting-expiry/SKILL.md": SKILL_MD.encode("utf-8")})

    package = read_package("hosting-expiry.zip", archive)

    assert package.skill == a_library_skill().imported.skill
    assert package.source.content_digest == hashlib.sha256(archive).hexdigest()


def test_a_package_that_declares_scripts_or_carries_another_file_is_refused() -> None:
    """A skill whose code the approval digest would not cover is refused at the door, whether the
    `SKILL.md` names a script or the archive carries a file beside it.

    Delete this and a reviewer approves the prose of a skill whose scripts can then be edited
    without the approval noticing, because `Skill.digest` covers a script's name and not its
    bytes."""
    with pytest.raises(SkillLibraryError, match="declares scripts"):
        read_package("SKILL.md", text_with(scripts="[run.py]").encode("utf-8"))
    with pytest.raises(SkillLibraryError) as beside:
        read_package(
            "skill.zip",
            a_zip({"SKILL.md": SKILL_MD.encode("utf-8"), "run.py": b"print('hello')"}),
        )

    assert "run.py" in str(beside.value)
    assert A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED in str(beside.value)


def test_an_archive_member_that_is_not_a_regular_file_is_refused_and_an_unstated_mode_is_read() -> (
    None
):
    """A `SKILL.md` recorded as a symlink is refused; one recorded as a regular file, and one
    recording no type at all, are read.

    Delete this and the in-memory reader drops the rule `brain.tools.extract` applies to the same
    archive on disk, or refuses the unstated mode every Windows zip has."""
    raw = SKILL_MD.encode("utf-8")

    with pytest.raises(SkillLibraryError, match="not a regular file"):
        read_package("skill.zip", a_zip({"SKILL.md": raw}, mode=0o120777))

    assert read_package("skill.zip", a_zip({"SKILL.md": raw}, mode=0o100644)).skill.name == (
        "hosting-expiry"
    )
    assert read_package("skill.zip", a_zip({"SKILL.md": raw})).skill.name == "hosting-expiry"


def test_an_archive_with_a_hostile_member_name_or_no_skill_md_is_refused() -> None:
    """The archive rules `brain.tools.skills.safe_archive_members` states are applied before any
    member is read.

    Delete this and `../SKILL.md` reads as a skill, which is harmless in memory today and is the
    name that escapes the day somebody writes the member to disk."""
    raw = SKILL_MD.encode("utf-8")

    with pytest.raises(SkillLibraryError, match=r"\.\."):
        read_package("skill.zip", a_zip({"../SKILL.md": raw}))
    with pytest.raises(SkillLibraryError, match=r"no SKILL\.md"):
        read_package("skill.zip", a_zip({"README.md": raw}))
    with pytest.raises(SkillLibraryError, match="not a zip archive"):
        read_package("skill.zip", raw)


def test_a_package_that_declares_a_reach_is_refused_by_the_parser_by_name() -> None:
    """`capabilities:` in the frontmatter is refused with the sentence the parser gives.

    Delete this and the reader could catch the parser's refusal and add the skill anyway, which is
    an import granting whatever its author wrote."""
    with pytest.raises(SkillLibraryError, match="declares no reach of its own"):
        read_package("SKILL.md", text_with(capabilities="[write:client.name]").encode("utf-8"))


@pytest.mark.parametrize(
    ("file_name", "content", "words"),
    [
        ("SKILL.md", b"", "empty"),
        ("SKILL.md", b"x" * (MAX_PACKAGE_BYTES + 1), "over the"),
        ("SKILL.md", b"\xff\xfe" + SKILL_MD.encode("utf-16-le"), "not UTF-8"),
        ("skill.txt", SKILL_MD.encode("utf-8"), "neither"),
        ("my skill (1).md", SKILL_MD.encode("utf-8"), "rename it"),
    ],
    ids=["empty", "too-large", "not-utf8", "not-md-or-zip", "unsafe-name"],
)
def test_a_package_that_cannot_be_read_is_refused_with_a_sentence_saying_what_to_change(
    file_name: str, content: bytes, words: str
) -> None:
    """Five packages that are not a skill, each refused in words that say what to do.

    Delete this and one of them reaches the parser as garbage, or reaches the table as a name no
    constraint admits, and the person adding it reads a fault instead of an instruction."""
    with pytest.raises(SkillLibraryError, match=words):
        read_package(file_name, content)


def test_the_largest_package_is_read_and_one_byte_more_is_refused() -> None:
    """The bound is `MAX_PACKAGE_BYTES` exactly.

    Delete this and the bound can drift by one either way, and the figure the console quotes stops
    being the figure the API applies."""
    body = "a" * (MAX_PACKAGE_BYTES - len(SKILL_MD.encode("utf-8")))
    at_limit = (SKILL_MD + body).encode("utf-8")[:MAX_PACKAGE_BYTES]

    assert len(at_limit) == MAX_PACKAGE_BYTES
    assert read_package("SKILL.md", at_limit).skill.name == "hosting-expiry"
    with pytest.raises(SkillLibraryError, match="over the"):
        read_package("SKILL.md", at_limit + b"a")


def test_a_version_in_digits_the_table_refuses_is_refused_before_it_reaches_the_table() -> None:
    """`VERSION_RE` is `\\d`, which admits Arabic-Indic digits, and `agent.skill` admits 0 to 9.

    Delete this and such a skill parses, passes every check here and fails the insert as a
    database fault."""
    with pytest.raises(SkillLibraryError, match="digits 0 to 9"):
        read_package("SKILL.md", text_with(version=OTHER_DIGITS).encode("utf-8"))


def test_a_file_saved_with_windows_line_endings_is_the_same_procedure() -> None:
    """CRLF and LF produce one skill and one digest, and the source digest still covers the bytes.

    Delete this and one person's editor makes a second version of every skill they touch, with a
    body carrying a carriage return a reviewer never sees."""
    crlf = SKILL_MD.replace("\n", "\r\n").encode("utf-8")

    package = read_package("SKILL.md", crlf)

    assert package.skill == a_library_skill().imported.skill
    assert package.source.content_digest == hashlib.sha256(crlf).hexdigest()


def test_a_skill_is_added_by_a_named_person_at_an_instant_with_a_zone() -> None:
    """Delete this and a skill can be added by nobody, or at a naive time the ledger orders
    wrongly."""
    package = read_package("SKILL.md", SKILL_MD.encode("utf-8"))

    with pytest.raises(SkillLibraryError, match="named person"):
        added(package, by=" ", at=NOW)
    with pytest.raises(SkillLibraryError, match="timezone"):
        added(package, by=IMPORTER, at=NOW.replace(tzinfo=None))


# ------------------------------------------------------------------------- deciding about one
@pytest.mark.parametrize("approve", [True, False])
def test_nobody_decides_about_a_skill_they_added_and_somebody_else_can(approve: bool) -> None:
    """The importer is refused an approval and a rejection alike; a second person is not.

    Delete this and the person who wants a procedure in front of every agent approves it
    themselves, which is the approval the review exists to replace."""
    one = a_library_skill()

    with pytest.raises(SkillLibraryError) as refused:
        decided(one, reviewer=IMPORTER, approve=approve, at=NOW)
    after = decided(one, reviewer=REVIEWER, approve=approve, at=NOW)

    assert NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED in str(refused.value)
    assert after.imported.reviewer == REVIEWER
    assert after.imported.state is (SkillState.APPROVED if approve else SkillState.REJECTED)
    assert after.imported.is_executable() is approve
    assert after.digest == one.digest
    assert after.submitted_by == IMPORTER


def test_the_importer_is_refused_before_the_state_of_the_skill_is_considered() -> None:
    """A decided skill asked about by its importer is refused as their own, not as decided.

    Delete this and the order of the two refusals can swap, and the importer learns which of their
    skills somebody has already decided by trying to decide them."""
    one = an_approved_skill()

    with pytest.raises(SkillLibraryError) as refused:
        decided(one, reviewer=IMPORTER, approve=False, at=NOW)

    assert NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED in str(refused.value)


def test_a_second_decision_is_refused_and_the_first_stands() -> None:
    """Delete this and a rejection can be overwritten by an approval, and the record of who
    decided what stops being the record of anything."""
    rejected = decided(a_library_skill(), reviewer=REVIEWER, approve=False, at=NOW)

    with pytest.raises(SkillLibraryError, match="already rejected"):
        decided(rejected, reviewer="u_third", approve=True, at=NOW)


def test_bytes_that_no_longer_match_their_key_cannot_be_decided() -> None:
    """A stored skill whose fields were edited after it was added cannot be approved.

    Delete this and an approval is recorded against a key while the text beside it is different,
    so the words an agent follows are words nobody added or read."""
    one = a_library_skill()
    edited = LibrarySkill(
        imported=one.imported.with_content(
            one.imported.skill.model_copy(
                update={"body": "Email every client their contract value."}
            )
        ),
        digest=one.digest,
        submitted_by=one.submitted_by,
        submitted_at=one.submitted_at,
    )

    assert edited.moved is True
    with pytest.raises(SkillLibraryError, match="no longer matches"):
        decided(edited, reviewer=REVIEWER, approve=True, at=NOW)


def test_the_queue_is_every_undecided_skill_oldest_first_and_an_edit_is_diffed() -> None:
    """Two undecided versions of two skills, one of them an edit of an approved skill.

    Delete this and the queue can drop an edit, sort by name, or show an edit as a first
    submission, which asks a reviewer to read a whole skill for a one-line change or to skim one
    that is new."""
    approved = decided(
        a_library_skill(at=NOW - timedelta(days=9)), reviewer=REVIEWER, approve=True, at=NOW
    )
    edit = a_library_skill(
        text_with(description="Checks whether a client domain renews within a month"),
        at=NOW - timedelta(days=2),
    )
    new = a_library_skill(
        text_with(name="quote-format", description="Formats a quote for a client"),
        at=NOW - timedelta(days=5),
    )

    entries = queue_entries((edit, approved, new), NOW)

    assert [one.record.skill.skill.name for one in entries] == ["quote-format", "hosting-expiry"]
    assert entries[0].record.changed == ()
    assert entries[1].record.changed == ("description",)
    assert all(dict(one.where) == {} for one in entries)


# --------------------------------------------------------------------------- the authorities
@pytest.mark.parametrize(
    ("question", "authority"),
    [(may_add, SKILL_AUTHORITY), (may_review, REVIEW_AUTHORITY)],
)
def test_adding_and_reviewing_need_the_screen_and_their_authority_over_everything(
    question: Callable[[EntitlementSet, datetime], bool], authority: Capability
) -> None:
    """Held over everything is admitted; held in one department, or not held, or held without the
    screen's configuration plane, is not.

    Delete this and a department's administrator adds a procedure to every department's queue, or
    approves one, or somebody holding only the authority does either without the screen."""
    everywhere = reach(authority.value)
    in_one = reach(authority.value, scope=Scope.department("web"))
    without_screen = EntitlementSet(
        principal_id="u_admin",
        grants=(Grant(capability=authority, scope=Scope.unrestricted()),),
    )

    assert question(everywhere, NOW) is True
    assert question(in_one, NOW) is False
    assert question(reach(), NOW) is False
    assert question(without_screen, NOW) is False


def test_the_two_authorities_are_two_and_neither_stands_in_for_the_other() -> None:
    """Delete this and the review authority can be the skill authority by a rename, so everybody who
    may add a skill may approve one, which is the separation the queue exists for."""
    assert SKILL_AUTHORITY != REVIEW_AUTHORITY
    assert may_review(reach(SKILL_AUTHORITY.value), NOW) is False
    assert may_add(reach(REVIEW_AUTHORITY.value), NOW) is False


def test_assigning_needs_the_skill_authority_in_a_scope_admitting_the_agent() -> None:
    """The authority held in web admits a web agent and not a finance one; held over everything it
    admits both.

    Delete this and a department's administrator assigns skills to every department's agents."""
    web = reach(SKILL_AUTHORITY.value, scope=Scope.department("web"))

    assert may_assign(web, {"agent_id": AGENT, "department": "web"}, NOW) is True
    assert may_assign(web, {"agent_id": AGENT, "department": "finance"}, NOW) is False
    assert may_assign(web, {"agent_id": AGENT}, NOW) is False
    assert may_assign(reach(SKILL_AUTHORITY.value), {"agent_id": AGENT}, NOW) is True
    assert may_assign(reach(), {"agent_id": AGENT}, NOW) is False


def test_the_library_is_listed_only_to_a_reader_of_the_screen_over_everything() -> None:
    """Delete this and a reader granted the screen in one department is listed every skill in the
    library, while the queue beside it, narrowed at the same place, lists none."""
    everywhere = reach()
    in_one = EntitlementSet(
        principal_id="u_web",
        grants=(
            Grant(capability=SKILL_READ, scope=Scope.department("web")),
            Grant(capability=CONFIGURATION, scope=Scope.unrestricted()),
        ),
    )

    assert may_read_library(everywhere, NOW) is True
    assert may_read_library(in_one, NOW) is False
    assert may_read_library(EntitlementSet(principal_id="u_none"), NOW) is False


# ------------------------------------------------------------------- what a skill may reach
def test_what_a_skill_is_trusted_to_reach_is_its_registered_tools_requirements_and_no_more() -> (
    None
):
    """Two registered tools and one nothing registers: the capabilities are the two tools' own, and
    the third is named as unregistered rather than dropped.

    Delete this and the screen can list an empty reach for a skill naming a tool this install does
    not have, which reads as a harmless skill rather than a misconfigured one."""
    one = a_library_skill(text_with(tools="[crm.read_client, desk.read_ticket, erp.read_invoice]"))

    trusted = trusted_reach(one.imported.skill, a_registry())

    assert trusted.tools == (
        ToolReach(name="crm.read_client", capability="read:client.name"),
        ToolReach(name="desk.read_ticket", capability="read:ticket.status"),
        ToolReach(name="erp.read_invoice", capability=None),
    )
    assert trusted.capabilities == ("read:client.name", "read:ticket.status")
    assert trusted.unknown == ("erp.read_invoice",)


def test_through_an_agent_a_skill_reaches_no_tool_its_caller_or_the_agent_does_not() -> None:
    """**The invariant, measured.** A skill names two tools. Through an agent allowed one, for a
    caller holding both, it reaches that one. For a caller holding only the other, it reaches
    nothing. Through an agent allowed both, for a caller holding both, it reaches both.

    Delete this and a skill naming a tool is a way for a caller to reach it through an agent that
    was never allowed it, or for an agent to reach it for a caller who never held it."""
    skill = a_library_skill().imported.skill
    registry = a_registry()
    both = reach("read:client.name", "read:ticket.status")
    tickets_only = reach("read:ticket.status")
    _, _, narrow_agent = an_install(allowed=("crm.read_client",))
    wide_agent = AgentRecord(
        agent_id="wide_desk",
        display_name="Wide desk",
        persona="Answer briefly.",
        audience=AUDIENCE,
        authority=AgentAuthority(
            capabilities=(
                Capability(value="read:client.name"),
                Capability(value="read:ticket.status"),
            ),
            allowed_tools=frozenset({"crm.read_client", "desk.read_ticket"}),
        ),
        created_by="u_builder",
    )

    assert reach_through(skill, registry, both, narrow_agent, NOW) == ("crm.read_client",)
    assert reach_through(skill, registry, tickets_only, narrow_agent, NOW) == ()
    assert reach_through(skill, registry, both, wide_agent, NOW) == (
        "crm.read_client",
        "desk.read_ticket",
    )
    assert reach_through(skill, registry, tickets_only, wide_agent, NOW) == ("desk.read_ticket",)


def test_an_agent_allowed_a_tool_but_not_its_capability_reaches_it_for_nobody() -> None:
    """The agent's capability ceiling narrows as well as its tool list: allowed both tools and
    holding only the client capability, it reaches the client tool for a caller holding both.

    Delete this and the reach can be computed at the caller's own set with the tool list as the only
    ceiling, which is `E(caller)` where the invariant says `E(caller) intersect agent_ceiling`, and
    an agent whose manifest never held a capability reaches everything its caller holds."""
    skill = a_library_skill().imported.skill
    tool_wide_capability_narrow = AgentRecord(
        agent_id="half_desk",
        display_name="Half desk",
        persona="Answer briefly.",
        audience=AUDIENCE,
        authority=AgentAuthority(
            capabilities=(Capability(value="read:client.name"),),
            allowed_tools=frozenset({"crm.read_client", "desk.read_ticket"}),
        ),
        created_by="u_builder",
    )
    both = reach("read:client.name", "read:ticket.status")

    assert reach_through(skill, a_registry(), both, tool_wide_capability_narrow, NOW) == (
        "crm.read_client",
    )


def test_an_agent_that_cannot_run_for_this_caller_is_reached_through_by_nothing() -> None:
    """An agent whose required tool does not resolve for the caller answers no tool, not a fault.

    Delete this and a screen showing reach raises for exactly the caller whose reach is empty."""
    skill = a_library_skill().imported.skill
    agent = AgentRecord(
        agent_id="needs_clients",
        display_name="Needs clients",
        persona="Answer briefly.",
        audience=AUDIENCE,
        authority=AgentAuthority(
            capabilities=(Capability(value="read:client.name"),),
            allowed_tools=frozenset({"crm.read_client"}),
            required_tools=frozenset({"crm.read_client"}),
        ),
        created_by="u_builder",
    )

    assert reach_through(skill, a_registry(), reach("read:ticket.status"), agent, NOW) == ()


# ------------------------------------------------------------------------ assigning a skill
def test_an_approved_skill_is_assigned_as_a_pin_of_its_bytes_and_recorded_as_attached() -> None:
    """The positive case: the install's skills path holds the name and the approved digest, the
    materialised agent carries that pin, one `compose_change` entry says it was attached and why,
    and the agent's authority is what it was.

    Delete this and every refusal below is satisfied by an assignment that writes nothing."""
    one = an_approved_skill()
    signed, instance, record = an_install()
    chain = AuditChain()

    made = assignment(
        one,
        record=record,
        signed=signed,
        instance=instance,
        library=(one,),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(chain),
        now=NOW,
    )
    after = materialise(signed, made.instance, audience=AUDIENCE)

    assert made.instance.overlay[SKILLS_PATH] == [{"name": "hosting-expiry", "digest": one.digest}]
    assert made.instance.overlay_owners[SKILLS_PATH].set_by == "u_admin"
    assert [(pin.skill_name, pin.digest) for pin in after.skill_pins] == [
        ("hosting-expiry", one.digest)
    ]
    assert made.effective_hash == after.config_hash
    assert made.effective_hash != materialise(signed, instance, audience=AUDIENCE).config_hash
    assert after.record.authority == record.authority
    assert made.replaces_digest is None
    # `register_skill` recorded the attachment on the recorder it was handed. The name there is the
    # redaction marker, because a hyphen is not a field name; the entry a database keeps is the
    # trigger's, under `ledger_reference`, which `test_skill_store.py` holds to the recorder.
    assert [entry.action for entry in chain.entries] == [AuditAction.COMPOSE_CHANGE]
    assert chain.entries[0].details["direction"] == "attached"
    assert chain.entries[0].details["reason_code"] == ASSIGN_REASON


@pytest.mark.parametrize("approve", [None, False])
def test_a_skill_nobody_approved_or_somebody_rejected_is_never_assigned(
    approve: bool | None,
) -> None:
    """Delete this and an undecided or rejected skill reaches an agent by being assigned, which is
    the review happening after the configuration."""
    one = a_library_skill()
    if approve is not None:
        one = decided(one, reviewer=REVIEWER, approve=approve, at=NOW)
    signed, instance, record = an_install()

    with pytest.raises(SkillLibraryError, match="cannot be pinned"):
        assignment(
            one,
            record=record,
            signed=signed,
            instance=instance,
            library=(one,),
            by=reach(SKILL_AUTHORITY.value),
            recorder=a_recorder(AuditChain()),
            now=NOW,
        )


def test_the_same_bytes_twice_is_refused_and_another_version_replaces_the_first_and_says_so() -> (
    None
):
    """An agent already running these bytes is refused a second assignment; an agent running an
    older version has it detached, recorded as replaced, and the new version attached.

    Delete this and a second assignment records a change that did not happen, or an upgrade leaves
    two versions of one skill on one agent, or the ledger never says the old bytes stopped."""
    older = an_approved_skill(text_with(version="0.9.0"))
    newer = an_approved_skill()
    signed, instance, record = an_install(
        skills=(SkillRef(name="hosting-expiry", digest=older.digest),)
    )

    with pytest.raises(SkillLibraryError, match="already runs this version"):
        assignment(
            older,
            record=record,
            signed=signed,
            instance=instance,
            library=(older, newer),
            by=reach(SKILL_AUTHORITY.value),
            recorder=a_recorder(AuditChain()),
            now=NOW,
        )
    chain = AuditChain()
    made = assignment(
        newer,
        record=record,
        signed=signed,
        instance=instance,
        library=(older, newer),
        by=reach(SKILL_AUTHORITY.value),
        recorder=a_recorder(chain),
        now=NOW,
    )

    assert made.replaces_digest == older.digest
    assert made.instance.overlay[SKILLS_PATH] == [
        {"name": "hosting-expiry", "digest": newer.digest}
    ]
    assert [
        (entry.details["direction"], entry.details["reason_code"]) for entry in chain.entries
    ] == [("detached", REPLACE_REASON), ("attached", ASSIGN_REASON)]


def test_a_skill_whose_description_cannot_route_is_refused_at_assignment() -> None:
    """The router convention `register_skill` enforces is enforced here, because this is where a
    skill joins an agent's menu.

    Delete this and the assignment can go round `register_skill` to `attach_skill`, and a skill
    described by its own name is chosen by the router on the name alone."""
    weak = an_approved_skill(text_with(description="Use for hosting expiry"))
    signed, instance, record = an_install()

    with pytest.raises(AgentTabError, match="adds no word"):
        assignment(
            weak,
            record=record,
            signed=signed,
            instance=instance,
            library=(weak,),
            by=reach(SKILL_AUTHORITY.value),
            recorder=a_recorder(AuditChain()),
            now=NOW,
        )


def test_an_authority_that_moved_between_two_readings_is_what_the_assignment_refuses() -> None:
    """`moved_authority` is true for two records whose ceilings differ and false for one record
    read twice, which is the comparison an assignment makes before it returns.

    Delete this and the check can be written to compare anything, including nothing, and the one
    guard standing between a manifest path that starts carrying reach and a grant by import is a
    comparison nobody has shown can fail."""
    _, _, record = an_install()
    widened = record.model_copy(
        update={
            "authority": AgentAuthority(
                capabilities=(Capability(value="read:client.contract_value"),),
                allowed_tools=frozenset({"crm.read_client"}),
            )
        }
    )

    assert moved_authority(record, record) is False
    assert moved_authority(record, widened) is True


def test_an_assignment_is_recorded_under_the_folded_name_and_a_second_spelling_is_found() -> None:
    """The ledger reference is the name with its hyphens folded, which the ledger admits; a skill
    spelt the other way is found in the library, and a new version of the same skill is not.

    Delete this and an assignment of `hosting-expiry` is recorded as the redaction marker, or two
    skills that fold to one name share every ledger entry about either."""
    held = a_library_skill()
    same_name = a_library_skill(text_with(version="2.0.0")).imported.skill
    other_spelling = a_library_skill(
        text_with(name="hosting_expiry", description="Checks domains a second way")
    ).imported.skill
    entry = AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    ).compose_change(
        agent_id=AGENT,
        part="skills",
        reference=ledger_reference("hosting-expiry"),
        attached=True,
        reason_code=ASSIGN_REASON,
    )

    assert ledger_reference("hosting-expiry") == "hosting_expiry"
    assert entry.details["reference"] == "hosting_expiry"
    assert another_spelling(same_name, (held,)) is None
    assert another_spelling(other_spelling, (held,)) == "hosting-expiry"


def test_nothing_in_the_library_computes_a_reach() -> None:
    """There is no `intersect` call in the module; `run_reach` is the console's route into it.

    Delete this and the library grows a second implementation of the platform's central rule."""
    assert intersections_in(inspect.getsource(library_module)) == ()


def test_a_skill_carries_nothing_through_which_an_assignment_could_widen_an_agent() -> None:
    """`Skill` has no field for a capability, a scope, a grant or a leash, so the only thing an
    assignment can write is a list of names and digests.

    Delete this and a field added to `Skill` for convenience becomes a way for an imported file to
    reach the agent's ceiling through the library."""
    forbidden = {
        "capabilities",
        "capability",
        "grant",
        "grants",
        "scope",
        "scopes",
        "leash",
        "rung",
    }

    assert set(Skill.model_fields) & forbidden == set()
