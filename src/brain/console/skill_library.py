"""The skill library: adding a skill, deciding about it, and assigning it without widening anybody.

`brain.tools.skills` decided what an imported skill is and what may be done with one, and
`brain.console.agent_tabs.register_skill` decided how an approved one joins an agent. What was
missing was a library to hold one between those two points, so every decision that needs a stored
skill was answered "not recorded" on the Skills screen. This module is the half of the library that
decides, and `brain.ops.skill_store` is the half that stores; neither does the other's job.

**Adding a skill parses it and never runs it.** A package is a `SKILL.md`, pasted or uploaded, or a
zip holding one. It is read in memory, its archive members are held to
`brain.tools.skills.safe_archive_members` and to a regular-file rule, the text goes through
`brain.tools.skills.skill_from_markdown`, and nothing in it is interpreted beyond that parser. What
comes out is an `ImportedSkill` in the imported state, and there is no parameter anywhere on the
path that could carry an approval, which is `brain.migration.skills.arriving`'s construction for
the same reason. See `ADDING_A_SKILL_READS_IT_AND_RUNS_NOTHING`.

**A skill that declares scripts is refused at the door, and that is a decision about the digest.**
`brain.tools.skills.Skill.digest` covers a script's name and not its bytes, so an approval of a
skill with scripts would survive an edit to the one part of it that is code. Nothing on an install
runs a script yet either (`brain.tools.run_skill` has no runner), so accepting one would store code
nobody can review by digest and nothing can execute. See
`A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED`.

**Nobody decides about a skill they added.** A review is the second pair of eyes, and a decision by
the importer is one pair of eyes wearing two hats. `decided` refuses it before `ImportedSkill`'s own
refusals run, and `agent.skill_review` refuses it again in its table definition, so a statement that
never came through this module is refused too. See `NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED`.

**What a skill is trusted to reach is its tools' requirements, read off the registry.** A skill
declares no reach of its own; `trusted_reach` names each tool the `SKILL.md` lists, the capability
the registered tool requires, and the tools no tool of that name is registered for. Through one
agent for one caller it is `brain.tools.skills.skill_reach` at `E_run(caller, agent)`, which
`reach_through` asks with `brain.console.workspace_capabilities.run_reach` and the agent's
`tool_ceiling`, so there is no intersection in this module.

**An assignment changes the agent's skills and nothing else, and says so by checking.** It is
`register_skill`, which pins only an approved skill whose bytes have not moved, followed by
`brain.agents.template.set_field` on the `skills` path. A skill has no field that could carry a
capability, so the agent's authority cannot change, and `assignment` compares the authority before
and after anyway and refuses a difference, because the cost of the check is one comparison and the
failure it names is the one this platform exists to prevent. See
`A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER`.

Scope: domain logic. Nothing here opens a connection or reads a clock; rows, the registry and the
instant arrive as arguments.

Task ids: M42.6.4
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from pydantic import JsonValue

from brain.agents.model import AgentRecord, tool_ceiling
from brain.agents.template import SignedManifest, TemplateInstance, materialise, set_field
from brain.audit.record import AuditRecorder
from brain.console.agent_tabs import SKILL_CAPABILITY, SKILL_SCREEN, detach, register_skill
from brain.console.govern import NOWHERE, Placed, _in_reach
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.workspace import Attachment, Composition, Part
from brain.console.workspace_capabilities import run_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.catalogue import EmptyCatalogueError
from brain.tools.extract import MAX_MEMBERS, _is_regular
from brain.tools.registry import ToolRegistry
from brain.tools.review import QueueEntry, pending
from brain.tools.skills import (
    SKILL_FILE,
    ImportedSkill,
    Skill,
    SkillError,
    SkillSource,
    SkillState,
    SourceKind,
    required_capabilities,
    safe_archive_member,
    safe_archive_members,
    skill_from_markdown,
    skill_reach,
    unknown_tools,
)

# ------------------------------------------------------------------ written-down reasons
#: Why adding a skill reads it and runs nothing.
ADDING_A_SKILL_READS_IT_AND_RUNS_NOTHING: Final = (
    "A package arrives from outside the company, so the path it takes is a parser and nothing "
    "else: the archive is opened in memory and never extracted to a disk, its member names and "
    "modes are held to the archive rules before any member is read, the SKILL.md goes through "
    "the frontmatter parser that refuses a declared reach by name, and what comes out is an "
    "imported skill in the imported state. Nothing on the path could carry an approval, and "
    "nothing on it executes, renders or fetches what the package says."
)

#: Why a skill with scripts is refused rather than stored.
A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED: Final = (
    "Skill.digest covers each script's name and not its bytes, so an approval of a skill with "
    "scripts is an approval that survives an edit to the one part of the skill that is code. "
    "No install runs a script yet either, because brain.tools.run_skill has no runner. So a "
    "package that declares scripts, or carries any file beside its SKILL.md, is refused at the "
    "door with a sentence saying so, rather than stored where a reviewer would approve prose "
    "and a digest would stand for code nobody read."
)

#: Why the importer may not decide.
NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED: Final = (
    "A review is a second person reading what the first person wants every agent that carries it "
    "to follow. A decision by whoever added the skill is one person with two roles, and an "
    "approval they granted themselves is exactly the approval the review exists to replace. So "
    "the importer is refused whatever they hold, and the decision table refuses the same row in "
    "its own definition for a statement that never came through the console."
)

#: Why an assignment checks the authority it cannot change.
A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER: Final = (
    "E_run(caller, agent) = E(caller) intersect agent_ceiling, and a skill is neither term: it "
    "names tools, and what those tools reach for a caller is decided by the catalogue at run "
    "time. An assignment writes the skills path and no other, so the agent's authority cannot "
    "move, and the assignment compares it before and after anyway. A difference is refused "
    "rather than written, because the day a manifest path starts carrying reach is the day this "
    "comparison is the only thing standing between an import and a grant."
)

#: Why the ledger names a skill by its folded name.
A_SKILL_IS_RECORDED_UNDER_THE_NAME_A_READER_FOLDS_IT_TO: Final = (
    "brain.tools.skills.SKILL_NAME_RE folds a hyphen and an underscore together, so hosting-expiry "
    "and hosting_expiry are one name to a reader. The ledger admits a detail value only when it "
    "is a field name, and a hyphen is not in that grammar, so an assignment's reference is the "
    "folded name: recorded rather than stored as the redaction marker, and the same entry for "
    "either spelling. The library refuses a second spelling of a name it already holds, so the "
    "folded name names one skill."
)

#: Why a refusal to add a skill says what to do.
A_PACKAGE_REFUSAL_SAYS_WHAT_TO_CHANGE: Final = (
    "The person adding a skill holds the authority to add it and is looking at the package, so "
    "nothing about the install is disclosed by telling them what is wrong with the file. Every "
    "refusal names the rule the package broke in words they can act on."
)


class SkillLibraryError(Exception):
    """A skill could not be added, decided about or assigned, in words its caller can act on.

    Outside `brain.core.errors` for `brain.console.agent_tabs.AgentTabError`'s reason: it is a
    refusal to configure something, read by somebody who holds the authority to configure it.
    """


# ------------------------------------------------------------------------- the authorities
#: Adds a skill to the library, held over everything; assigns an approved one, in a scope
#: admitting the agent. See `may_add` and `may_assign`.
SKILL_AUTHORITY: Final = Capability(value="admin:skill")

#: Approves or rejects a skill somebody else added, held over everything.
REVIEW_AUTHORITY: Final = Capability(value="admin:skill_review")

#: The manifest path an agent's skills are. `brain.agents.template.MANIFEST_PATHS` holds it.
SKILLS_PATH: Final = "skills"

#: Why an assignment reached the ledger, as `AuditRecorder.compose_change` records a reason.
ASSIGN_REASON: Final = "skill_assign"
REPLACE_REASON: Final = "skill_replace"

#: The largest package, in bytes, arrived or unpacked. A skill is a page of instructions.
MAX_PACKAGE_BYTES: Final = 256 * 1024

#: The two file shapes a package may take.
MARKDOWN_SUFFIX: Final = ".md"
ARCHIVE_SUFFIX: Final = ".zip"


def _library_screen_read(reach: EntitlementSet, now: datetime | None) -> bool:
    """The Skills screen's own question: its capability and the configuration plane together."""
    return permitted(screen(SKILL_SCREEN).read, reach, now)


def may_read_library(reach: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether the library's rows may be listed to this reader.

    The screen's read held over everything, which is the narrowing
    `brain.console.govern_estate.skill_queue` applies to a submission placed at `NOWHERE`: a skill
    belongs to no department, so a reader granted the screen in one department reaches no row of
    the library and no row of the queue, and the two agree by being one question.
    """
    return _library_screen_read(reach, now) and _in_reach(reach, SKILL_CAPABILITY, NOWHERE, now)


def may_add(reach: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may add a skill: the screen, and the skill authority over everything.

    Over everything because a skill in the library is offered to every agent, so a department's
    administrator adding one would be adding a procedure to every department's review queue.
    """
    return _library_screen_read(reach, now) and _in_reach(reach, SKILL_AUTHORITY, NOWHERE, now)


def may_review(reach: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may decide about a skill, before asking who added it."""
    return _library_screen_read(reach, now) and _in_reach(reach, REVIEW_AUTHORITY, NOWHERE, now)


def may_assign(
    reach: EntitlementSet, where: Mapping[str, str], now: datetime | None = None
) -> bool:
    """Whether this reader may assign a skill to the agent `where` describes.

    The skill authority in a scope admitting the agent's row, which is
    `brain.prompt_routes.may_edit`'s construction for an agent's instructions: a department's
    administrator may be granted their department's agents and no others.
    """
    return _library_screen_read(reach, now) and _in_reach(reach, SKILL_AUTHORITY, where, now)


# ------------------------------------------------------------------------- one stored skill
@dataclass(frozen=True)
class LibrarySkill:
    """One skill in the library: what arrived, who added it and when, and any decision.

    `digest` is the key it is stored under, carried beside the skill rather than recomputed,
    because the difference between the two is the signal: a row whose fields were edited in place
    no longer digests to its key, and `ImportedSkill.is_executable` compares the approval, which is
    the key, against the bytes, which are the fields.
    """

    imported: ImportedSkill
    digest: str
    submitted_by: str
    submitted_at: datetime

    @property
    def name(self) -> str:
        return self.imported.skill.name

    @property
    def moved(self) -> bool:
        """The stored fields no longer digest to the key they were stored under."""
        return self.imported.skill.digest() != self.digest


# ------------------------------------------------------------------- adding a skill (import)
def ledger_reference(name: str) -> str:
    """The name an assignment of this skill is recorded under. See
    `A_SKILL_IS_RECORDED_UNDER_THE_NAME_A_READER_FOLDS_IT_TO`."""
    return name.replace("-", "_")


def another_spelling(skill: Skill, library: Iterable[LibrarySkill]) -> str | None:
    """A skill already in the library whose name folds to this one's and is spelt differently.

    None when there is none. A new version of the same skill has the same spelling and is not
    another spelling; `hosting_expiry` beside `hosting-expiry` is.

    **Asked of what the route read, which is a bounded reading and not a key.** Two people adding
    the two spellings at the same moment, or a library larger than one reading, can each get past
    it, and the ledger then records two skills under one reference. A unique index on the folded
    name was rejected because every version of a skill shares its name, so the rule a key could
    state is "one spelling per folded name across versions", which PostgreSQL cannot express as a
    unique constraint and would need an exclusion constraint over an extension this install does
    not load.
    """
    folded = ledger_reference(skill.name)
    for one in library:
        if one.name != skill.name and ledger_reference(one.name) == folded:
            return one.name
    return None


@dataclass(frozen=True)
class Package:
    """A package that parsed: the skill and where its bytes came from."""

    skill: Skill
    source: SkillSource


def _refused(reason: str) -> SkillLibraryError:
    return SkillLibraryError(f"this skill was not added: {reason}")


def _markdown_text(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _refused(
            f"the {SKILL_FILE} is not UTF-8 text; save it as UTF-8 and add it again"
        ) from None
    # One procedure whichever editor saved it. The bytes that arrived are still what the source's
    # digest covers, so nothing about the upload is lost by reading its line endings as one.
    return text.replace("\r\n", "\n")


def _from_archive(content: bytes) -> str:
    """The one `SKILL.md` a zip holds, read in memory, or a refusal.

    The rules `brain.tools.extract.extract_zip` applies before it writes anything, applied before
    anything is read, and no member is ever written anywhere. Any member but the `SKILL.md` is
    refused rather than skipped, for `safe_archive_members`' reason about an archive with one
    hostile name and for `A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED`.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise _refused("the file is not a zip archive; add the SKILL.md itself instead") from None
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise _refused(f"the archive holds {len(infos)} files, over the {MAX_MEMBERS} limit")
        declared = sum(info.file_size for info in infos)
        if declared > MAX_PACKAGE_BYTES:
            raise _refused(
                f"the archive unpacks to {declared} bytes, over the {MAX_PACKAGE_BYTES} limit"
            )
        try:
            names = safe_archive_members(info.filename for info in infos)
        except SkillError as refused:
            raise _refused(str(refused)) from None
        others = sorted(name for name in names if name.rsplit("/", 1)[-1] != SKILL_FILE)
        if others:
            raise _refused(
                f"the archive holds {others} beside its {SKILL_FILE}. "
                f"{A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED}"
            )
        (manifest,) = infos
        mode = manifest.external_attr >> 16
        if mode and not _is_regular(mode):
            raise _refused(f"{manifest.filename!r} in the archive is not a regular file")
        if manifest.flag_bits & 0x1:
            raise _refused("the archive is encrypted; add the SKILL.md itself instead")
        with archive.open(manifest) as source:
            raw = source.read(MAX_PACKAGE_BYTES + 1)
    if len(raw) > MAX_PACKAGE_BYTES:
        raise _refused("the archive is larger than it declared")
    return _markdown_text(raw)


def read_package(file_name: str, content: bytes) -> Package:
    """Parse a package into a skill and its source, or refuse it in words to act on.

    See `ADDING_A_SKILL_READS_IT_AND_RUNS_NOTHING` and `A_PACKAGE_REFUSAL_SAYS_WHAT_TO_CHANGE`.
    The source is an upload whatever the browser did, a paste included, because the bytes arrived
    in a request and the digest over them is the only thing a later fetch could be compared with.
    """
    if not content:
        raise _refused("the package is empty; paste the SKILL.md or choose the file again")
    if len(content) > MAX_PACKAGE_BYTES:
        raise _refused(f"the package is {len(content)} bytes, over the {MAX_PACKAGE_BYTES} limit")
    try:
        safe_archive_member(file_name)
    except SkillError:
        raise _refused(
            f"the file name {file_name!r} is not one this install keeps; rename it to letters, "
            "digits, dots, hyphens and underscores"
        ) from None
    lowered = file_name.lower()
    if lowered.endswith(ARCHIVE_SUFFIX):
        text = _from_archive(content)
    elif lowered.endswith(MARKDOWN_SUFFIX):
        text = _markdown_text(content)
    else:
        raise _refused(f"a package is a {SKILL_FILE} or a .zip holding one, and this is neither")

    try:
        skill = skill_from_markdown(text)
    except SkillError as refused:
        raise _refused(str(refused)) from None
    if skill.scripts:
        raise _refused(
            f"it declares scripts {list(skill.scripts)}. "
            f"{A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED}"
        )
    if not skill.version.isascii():
        raise _refused(f"its version {skill.version!r} is not written in the digits 0 to 9")
    source = SkillSource(
        kind=SourceKind.UPLOAD,
        location=file_name,
        content_digest=hashlib.sha256(content).hexdigest(),
    )
    return Package(skill=skill, source=source)


def added(package: Package, *, by: str, at: datetime) -> LibrarySkill:
    """The skill as the library holds it once added: imported, by this person, and undecided.

    There is no parameter for a state, a reviewer or an approved digest, so nothing that adds a
    skill can add one already approved. See `ADDING_A_SKILL_READS_IT_AND_RUNS_NOTHING`.
    """
    if not by.strip():
        raise SkillLibraryError("a skill is added by a named person, never by an empty string")
    if at.tzinfo is None:
        raise SkillLibraryError("the time a skill was added must be timezone-aware")
    imported = ImportedSkill(skill=package.skill, source=package.source)
    return LibrarySkill(
        imported=imported, digest=package.skill.digest(), submitted_by=by, submitted_at=at
    )


# ------------------------------------------------------------------------- deciding about one
def decided(one: LibrarySkill, *, reviewer: str, approve: bool, at: datetime) -> LibrarySkill:
    """The skill with a decision on it, by somebody who did not add it, or a refusal.

    The importer first, whatever else is true, so the answer to a person reviewing their own
    import never depends on the state the skill is in. See
    `NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED`. Then bytes that no longer digest to their key,
    because an approval is recorded against the key and would approve something nobody read. The
    second-decision refusal and the named-person refusal are `ImportedSkill`'s own.
    """
    if reviewer == one.submitted_by:
        raise SkillLibraryError(
            f"nothing was decided: {one.name!r} was added by you. "
            f"{NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED}"
        )
    if one.moved:
        raise SkillLibraryError(
            f"nothing was decided: the stored text of {one.name!r} no longer matches the version "
            "it was added as, so an approval would be of words nobody added; add it again"
        )
    try:
        imported = (
            one.imported.approved_by(reviewer, at)
            if approve
            else one.imported.rejected_by(reviewer, at)
        )
    except SkillError as refused:
        raise SkillLibraryError(f"nothing was decided: {refused}") from None
    return LibrarySkill(
        imported=imported,
        digest=one.digest,
        submitted_by=one.submitted_by,
        submitted_at=one.submitted_at,
    )


def queue_entries(library: Sequence[LibrarySkill], now: datetime) -> tuple[Placed[QueueEntry], ...]:
    """Every skill waiting for a decision, oldest first, placed nowhere.

    `brain.tools.review.pending` builds each entry, so what counts as waiting and what counts as an
    edit are that module's answers; it is asked one skill at a time because it keys a submission
    time by name, and two waiting versions of one skill would otherwise share one. An edit is
    diffed against the newest approved version of the same name. Placed at `NOWHERE`, because a
    skill belongs to no department. See `may_read_library`.
    """
    approved: dict[str, LibrarySkill] = {}
    for one in sorted(library, key=lambda item: item.submitted_at):
        if one.imported.state is SkillState.APPROVED:
            approved[one.name] = one
    entries: list[QueueEntry] = []
    for one in library:
        previous = approved.get(one.name)
        entries.extend(
            pending(
                (one.imported,),
                previous={} if previous is None else {one.name: previous.imported.skill},
                submitted_at={one.name: one.submitted_at},
                now=now,
            )
        )
    return tuple(
        Placed(record=entry, where=NOWHERE)
        for entry in sorted(entries, key=lambda entry: entry.waiting_since)
    )


# ------------------------------------------------------------------ what a skill may reach
@dataclass(frozen=True)
class ToolReach:
    """One tool a skill names, and the capability the registered tool requires, if one is."""

    name: str
    #: None when no tool of this name is registered on this install.
    capability: str | None


@dataclass(frozen=True)
class SkillReach:
    """What a skill is trusted to reach: its tools' requirements, and nothing of its own."""

    tools: tuple[ToolReach, ...]
    #: The union of what the registered tools require, sorted. `required_capabilities`' answer.
    capabilities: tuple[str, ...]
    #: Tools the skill names that nothing on this install registers. `unknown_tools`' answer.
    unknown: tuple[str, ...]


def trusted_reach(skill: Skill, registry: ToolRegistry) -> SkillReach:
    """What this skill would reach for somebody holding everything its tools need.

    Read off the registry and never off the skill, because the skill has nothing to say about
    reach: `brain.tools.skills.required_capabilities` and `unknown_tools` are the two answers, and
    each tool's own capability is the registry's. An unregistered tool reaches nothing and is
    listed as unregistered rather than as unconstrained, for `unknown_tools`' reason.
    """
    return SkillReach(
        tools=tuple(
            ToolReach(
                name=name,
                capability=registry.get(name).capability.value if registry.has(name) else None,
            )
            for name in skill.tools
        ),
        capabilities=tuple(one.value for one in required_capabilities(skill, registry)),
        unknown=unknown_tools(skill, registry),
    )


def reach_through(
    skill: Skill,
    registry: ToolRegistry,
    caller: EntitlementSet,
    record: AgentRecord,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """The tools this skill can use when this caller runs this agent: never more than either.

    `brain.tools.skills.skill_reach` at `E_run(caller, agent)`, with the agent's tool ceiling,
    which is the reach `brain.gate.invoke` projects a catalogue at. An agent whose required tools
    do not resolve for this caller cannot run for them at all, and the answer is then no tool.
    """
    try:
        return skill_reach(
            skill, registry, run_reach(caller, record), tool_ceiling(record), now=now
        )
    except EmptyCatalogueError:
        return ()


# ------------------------------------------------------------------------ assigning a skill
@dataclass(frozen=True)
class Assignment:
    """One approved skill on one agent: the install to write and the entries that record it.

    The ledger entries are not here. `register_skill` writes them to the recorder it is handed,
    which the route holds in memory, and the entries a deployed database keeps are `0056`'s
    trigger's on the assignment row, under `ledger_reference`: a row written and an entry left
    out cannot happen, because the entry is the row's.
    """

    agent_id: str
    skill_name: str
    digest: str
    replaces_digest: str | None
    assigned_by: str
    instance: TemplateInstance
    effective_document: Mapping[str, JsonValue]
    effective_hash: str


def pins_on(signed: SignedManifest, instance: TemplateInstance, record: AgentRecord) -> Composition:
    """The skills this agent carries, as a composition of attachments pinned by digest."""
    effective = materialise(signed, instance, audience=record.audience)
    return Composition(
        agent_id=instance.instance_id,
        attachments=tuple(
            Attachment(part=Part.SKILLS, ref=pin.skill_name, version=pin.digest)
            for pin in effective.skill_pins
        ),
    )


def _alongside(composition: Composition, library: Iterable[LibrarySkill]) -> tuple[Skill, ...]:
    """The library's copies of the skills already on this agent, for the router's collision check.

    A pin whose bytes the library does not hold, a template's own skill for instance, has no text
    to compare a description with and is left out: the check can only refuse on what it can read.
    """
    held = {(one.ref, one.version) for one in composition.attached_to(Part.SKILLS)}
    return tuple(one.imported.skill for one in library if (one.name, one.digest) in held)


def moved_authority(before: AgentRecord, after: AgentRecord) -> bool:
    """Whether anything that decides what an agent may reach differs between two readings of it.

    The authority, which is the scope, the capabilities, the tools and the side-effect ceiling the
    catalogue and `entitlement_ceiling` read. A function of its own so the refusal it guards can be
    tested with two records that differ, which an assignment can never produce. See
    `A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER`.
    """
    return after.authority != before.authority


def assignment(
    one: LibrarySkill,
    *,
    record: AgentRecord,
    signed: SignedManifest,
    instance: TemplateInstance,
    library: Sequence[LibrarySkill],
    by: EntitlementSet,
    recorder: AuditRecorder,
    now: datetime,
) -> Assignment:
    """Assign one approved skill to one agent through `register_skill`, or refuse.

    The composition is the agent's current pins. The same bytes already there is refused, because
    an assignment that changes nothing would record a change. Another version of the same skill is
    detached first, which is the only way `Composition` admits a second version, and is recorded as
    a replacement. Then `register_skill`: the description convention, the router collision against
    the library's copies of what the agent carries, and `attach_skill`, whose `pin_skill` refuses a
    skill that is not approved by a named person and unchanged since.

    The install is `set_field` on `skills` and nothing else, materialised again, and the authority
    before and after is compared. See `A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER`.
    """
    before = materialise(signed, instance, audience=record.audience)
    composition = pins_on(signed, instance, record)
    same = [pin for pin in composition.attached_to(Part.SKILLS) if pin.ref == one.name]
    if any(pin.version == one.digest for pin in same):
        raise SkillLibraryError(
            f"nothing was assigned: {record.agent_id!r} already runs this version of {one.name!r}"
        )
    replaces: str | None = None
    if same:
        replaces = same[0].version
        detached = detach(
            composition, Part.SKILLS, one.name, recorder=recorder, reason_code=REPLACE_REASON
        )
        composition = detached.composition
    try:
        composed = register_skill(
            composition,
            one.imported,
            alongside=_alongside(composition, library),
            by=by,
            recorder=recorder,
            reason_code=ASSIGN_REASON,
            now=now,
        )
    except SkillError as refused:
        raise SkillLibraryError(f"nothing was assigned: {refused}") from None

    skills: list[JsonValue] = [
        {"name": pin.ref, "digest": pin.version}
        for pin in sorted(
            composed.composition.attached_to(Part.SKILLS), key=lambda pin: (pin.ref, pin.version)
        )
    ]
    changed = set_field(instance, SKILLS_PATH, skills, by=by.principal_id, at=now)
    after = materialise(signed, changed, audience=record.audience)
    if moved_authority(before.record, after.record):
        raise SkillLibraryError(
            f"nothing was assigned: {A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER}"
        )
    return Assignment(
        agent_id=record.agent_id,
        skill_name=one.name,
        digest=one.digest,
        replaces_digest=replaces,
        assigned_by=by.principal_id,
        instance=changed,
        effective_document=dict(after.document),
        effective_hash=after.config_hash,
    )
