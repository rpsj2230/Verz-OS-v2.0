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

**A skill arrives three ways, and each is read, never run (M12.2.2, M12.2.3, M12.2.4).** A package
pasted or uploaded (`read_package`); a repository at a full commit sha (`read_github`), whose
tarball is inflated in memory under a ceiling and from which exactly one member is read, the
`SKILL.md` at the path asked for; and an https address on `brain.tools.fetch.SKILL_SOURCE_HOSTS`
(`read_url`), whose answer is a `SKILL.md` or a zip holding one. Each comes out as the same
imported skill with a different `SkillSource`, so the review and everything after it cannot tell
how it arrived except by reading the source. The fetch is `brain.tools.fetch`'s and happens before
this module is called; nothing here opens a connection. **Only the `SKILL.md` is taken from a
repository folder.** A zip holding anything else is refused, for
`A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED`; a repository folder commonly holds
a licence or a readme beside its `SKILL.md`, and refusing those would refuse most repositories, so
they are left where they are and never stored, which is the same outcome by a gentler route: no
byte the digest does not cover is kept. A `SKILL.md` that declares scripts is still refused.

**An administrator may approve a skill they imported, and the ledger says it was their own (D4,
M12.4.6).** Until 2026-09-28 `decided` refused the importer whatever they held, and the table
refused the row. The owner decided otherwise on 2026-09-18: the two-person rule stays for
irreversible actions, and a skill is not one, since an approved skill reaches nothing until it is
assigned and an assignment can be undone. So whoever holds the review authority may decide about
any skill, their own included, and `0121`'s trigger records such a decision as `self_approved` or
`self_rejected`, which is a word the audit screen's search finds. Somebody who may add and may not
review still needs somebody else to decide. See
`AN_ADMINISTRATOR_MAY_APPROVE_WHAT_THEY_IMPORTED_AND_THE_LEDGER_SAYS_SO`.

**An edit is a new version, and nothing that was pinned moves (M12.3.2).** `edited` parses the
edited `SKILL.md` exactly as an import does, refuses a rename, an edit that changes nothing, and a
version that is not later than the one edited or is already held, and returns a new library entry
in the imported state carrying `edited_from`. The old row is never touched, because no row here is
ever updated, so it stays readable; an agent is pinned to a digest, so every agent keeps the bytes
it was pinned to until somebody assigns the new ones. See
`AN_EDIT_IS_A_NEW_VERSION_AND_MOVES_NO_PIN`.

**A reviewer is shown the words that changed.** `compared_with` names the version an entry is
diffed against, the newest approved version of the same name added before it and otherwise the
version it was edited from, and `brain.tools.review.content_diff` is the diff.

**Categories are labels an administrator sets on a skill's name, and every version shares them
(M12.4.13).** They are not part of the digest, because a label is not a procedure and changing one
must not send a skill back to review. `categories_from` folds and refuses them; `chips` draws the
filter from the skills a reader was already shown and from nothing else.

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

**A version is retired, and a skill detached, by adding a row (W2.8, M27.15.55, M27.15.56).**
`retiring` refuses a retirement that would change nothing, and a retired version is refused a new
assignment while every agent running it keeps it and is listed (`holding`) for somebody to detach.
`detachment` is `assignment`'s mirror: the agent's skills written without the skill, through
`brain.console.agent_tabs.detach`, with the authority compared before and after. What is assigned
now is derived, never stored: `current_assignments` over the assignment and detachment rows. See
`A_RETIRED_VERSION_IS_KEPT_AND_ONLY_REFUSED_TO_NEW_AGENTS` and
`A_DETACHMENT_IS_A_ROW_AND_THE_CURRENT_ASSIGNMENTS_ARE_WHAT_NO_ROW_ENDED`.

Scope: domain logic. Nothing here opens a connection or reads a clock; rows, the registry and the
instant arrive as arguments.

Task ids: M42.6.4, M12.2.2, M12.2.3, M12.2.4, M12.2.6, M12.3.2, M12.4.6, M12.4.13, M27.15.55
"""

from __future__ import annotations

import hashlib
import io
import re
import tarfile
import zipfile
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
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
    SkillPin,
    SkillSource,
    SourceKind,
    required_capabilities,
    safe_archive_member,
    safe_archive_members,
    skill_from_markdown,
    skill_reach,
    unknown_tools,
    version_key,
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

#: Why the importer may decide, and what is recorded when they do (D4).
AN_ADMINISTRATOR_MAY_APPROVE_WHAT_THEY_IMPORTED_AND_THE_LEDGER_SAYS_SO: Final = (
    "The owner decided on 2026-09-18 that the two-person rule stays for irreversible actions and "
    "that an administrator may approve a skill they imported, with that approval recorded. An "
    "approved skill reaches no agent until somebody assigns it, and an assignment is undone by "
    "assigning another version, so approving is not irreversible. Whoever holds the review "
    "authority may therefore decide about any skill, their own included, and the ledger records a "
    "decision by the person who added the skill as self_approved or self_rejected, which the audit "
    "screen finds by that word. Somebody who may add skills and may not review them still needs "
    "somebody else to decide."
)

#: Why an edit is a new row and never a change to the old one.
AN_EDIT_IS_A_NEW_VERSION_AND_MOVES_NO_PIN: Final = (
    "An edit is parsed as an import is, and saved as a new version, undecided, beside the one it "
    "was edited from, which is never changed and stays readable. An agent is pinned to a digest, "
    "so every agent keeps the version it was pinned to until somebody assigns the new one, and the "
    "new one cannot be assigned until it is approved. The version number has to be later than the "
    "one edited and not already held, so two readings of one number are never two procedures."
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

#: Why retiring a version refuses new agents and touches none it is already on (M27.15.56).
A_RETIRED_VERSION_IS_KEPT_AND_ONLY_REFUSED_TO_NEW_AGENTS: Final = (
    "Retiring a version adds a row saying so and changes nothing else. The version stays in the "
    "library with its words readable, every agent already running it keeps running it, and only a "
    "new assignment of it is refused. The agents still holding it are listed to the person who "
    "retired it, to detach one at a time, because taking a skill off a live agent as a side effect "
    "of a library act would be a change to that agent nobody decided. Reinstating is a later row, "
    "and the newest row for a version is its state."
)

#: Why a detachment is a row beside the manifest change, and what is current (M27.15.55).
A_DETACHMENT_IS_A_ROW_AND_THE_CURRENT_ASSIGNMENTS_ARE_WHAT_NO_ROW_ENDED: Final = (
    "Detaching writes the agent's skills without the skill, which is what a run reads, and adds a "
    "row naming the assignment it ended, in one transaction. No assignment row is ever changed: "
    "the current assignments are those no detachment names and no later assignment of the same "
    "skill to the same agent replaced, so the history of who ran what, and when it stopped, is "
    "every row there is."
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
DETACH_REASON: Final = "skill_detach"

#: The largest package, in bytes, arrived or unpacked. A skill is a page of instructions.
MAX_PACKAGE_BYTES: Final = 256 * 1024

#: The two file shapes a package may take.
MARKDOWN_SUFFIX: Final = ".md"
ARCHIVE_SUFFIX: Final = ".zip"

#: The first bytes of a zip, which is how a URL's answer is told from a `SKILL.md`: an address
#: names no file type anybody can trust, and the bytes do.
ZIP_MAGIC: Final = b"PK\x03\x04"

#: The first bytes of a gzip stream, which a URL answering with a repository tarball sends.
GZIP_MAGIC: Final = b"\x1f\x8b"

#: The most a repository tarball may inflate to. A skill repository is a few folders of text;
#: a tarball that inflates past this is a bomb or not a skill repository, and either way it is
#: refused before a member is listed.
MAX_UNPACKED_BYTES: Final = 64 * 1024 * 1024

#: The most members a repository tarball may list.
MAX_TARBALL_MEMBERS: Final = 20_000

#: A category: lower-case letters, digits and hyphens, at most 40. Folded from what was typed.
CATEGORY_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

#: The longest address a URL import may name: `brain.tools.skills.SkillSource.location`'s bound,
#: which a test holds this to, so an address the source would refuse is refused before the fetch.
MAX_ADDRESS_CHARS: Final = 400

#: The most categories one skill carries. Enough to file a skill several ways; a skill in every
#: category is in none.
MAX_CATEGORIES: Final = 8


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
    #: The digest of the version this one was edited from, when it is an edit (M12.3.2).
    edited_from: str | None = None

    @property
    def name(self) -> str:
        return self.imported.skill.name

    @property
    def self_decided(self) -> bool:
        """Decided by the person who added it. See
        `AN_ADMINISTRATOR_MAY_APPROVE_WHAT_THEY_IMPORTED_AND_THE_LEDGER_SAYS_SO`."""
        return bool(self.imported.reviewer) and self.imported.reviewer == self.submitted_by

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


def _not_saved(reason: str) -> SkillLibraryError:
    return SkillLibraryError(f"nothing was saved: {reason}")


Refusal = Callable[[str], SkillLibraryError]


def _markdown_text(raw: bytes, refuse: Refusal = _refused) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise refuse(
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


def _skill_of(text: str, refuse: Refusal = _refused) -> Skill:
    """The skill a `SKILL.md` declares, held to every rule a package is held to, or a refusal.

    The one parser, `skill_from_markdown`, and then the two refusals the library adds: a skill
    declaring scripts, for `A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED`, and a
    version in digits other than 0 to 9, which the table's check would refuse after the press.
    """
    try:
        skill = skill_from_markdown(text)
    except SkillError as refused:
        raise refuse(str(refused)) from None
    if skill.scripts:
        raise refuse(
            f"it declares scripts {list(skill.scripts)}. "
            f"{A_SCRIPT_THE_DIGEST_DOES_NOT_COVER_IS_A_SCRIPT_NOBODY_APPROVED}"
        )
    if not skill.version.isascii():
        raise refuse(f"its version {skill.version!r} is not written in the digits 0 to 9")
    return skill


def read_package(file_name: str, content: bytes) -> Package:
    """Parse a package into a skill and its source, or refuse it in words to act on (M12.2.4).

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
    source = SkillSource(
        kind=SourceKind.UPLOAD,
        location=file_name,
        content_digest=hashlib.sha256(content).hexdigest(),
    )
    return Package(skill=_skill_of(text), source=source)


# ------------------------------------------------------------------- from a URL (M12.2.3)
def url_source_problem(url: str) -> str | None:
    """Why this address cannot be a skill's source, before anything is fetched, or None.

    The shape only: https, and short enough for the column the source is kept in. Where it may be
    fetched from is `brain.tools.fetch`'s decision, made on every hop when the fetch runs.
    """
    if not url.startswith("https://"):
        return "a skill is imported from an https address"
    if len(url) > MAX_ADDRESS_CHARS:
        return (
            f"the address is {len(url)} characters, over the {MAX_ADDRESS_CHARS} this install keeps"
        )
    return None


def read_url(url: str, content: bytes) -> Package:
    """What an address answered, as a package, pinned by the digest of those bytes (M12.2.3).

    A `SKILL.md` or a zip holding one, told apart by the bytes: an address names no file type
    that can be trusted. A gzip stream is refused with the way to import it, because a repository
    tarball needs a commit to pin and a folder to read, which an address does not carry.
    """
    problem = url_source_problem(url)
    if problem is not None:
        raise _refused(problem)
    if not content:
        raise _refused("the address answered with nothing")
    if len(content) > MAX_PACKAGE_BYTES:
        raise _refused(
            f"the address answered {len(content)} bytes, over the {MAX_PACKAGE_BYTES} limit"
        )
    if content.startswith(GZIP_MAGIC):
        raise _refused(
            "the address answered with a compressed archive; import a repository by its name "
            "and a commit instead"
        )
    text = _from_archive(content) if content.startswith(ZIP_MAGIC) else _markdown_text(content)
    source = SkillSource(
        kind=SourceKind.URL, location=url, content_digest=hashlib.sha256(content).hexdigest()
    )
    return Package(skill=_skill_of(text), source=source)


# ------------------------------------------------------ from a repository commit (M12.2.2)
def github_source(repository: str, commit: str, path: str) -> SkillSource:
    """The source a repository import names, checked before anything is fetched.

    `SkillSource` refuses a repository that is not `owner/repo`, a commit that is not a full sha,
    and a path with a segment that names no folder; its words are the refusal. A trailing or
    leading slash on the path is taken off, because it is how a folder is commonly copied.
    """
    try:
        return SkillSource(
            kind=SourceKind.GITHUB,
            location=repository.strip(),
            commit=commit.strip().lower(),
            path=path.strip().strip("/"),
        )
    except ValueError as refused:
        raise _refused(_first_error(refused)) from None


def _first_error(refused: ValueError) -> str:
    """The sentence a validator wrote, without pydantic's framing around it."""
    errors = getattr(refused, "errors", None)
    if callable(errors):
        found = errors()
        if found:
            return str(found[0].get("msg", refused)).removeprefix("Value error, ")
    return str(refused)


def _inflated(tarball: bytes) -> bytes:
    """A gzip stream inflated in memory, to one byte past the ceiling and no further."""
    inflater = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        data = inflater.decompress(tarball, MAX_UNPACKED_BYTES + 1)
    except zlib.error:
        raise _refused("the repository archive is not a gzip stream") from None
    if len(data) > MAX_UNPACKED_BYTES or inflater.unconsumed_tail:
        raise _refused(
            f"the repository archive inflates past {MAX_UNPACKED_BYTES} bytes; import a smaller "
            "repository"
        )
    return data


def _from_tarball(tarball: bytes, path: str) -> bytes:
    """The bytes of the one `SKILL.md` at `path` in a repository tarball, or a refusal.

    GitHub's tarball holds one top folder, named for the repository and the commit, and the tree
    under it. Nothing is extracted: the members are listed from memory, exactly one is read, and
    it must be a regular file, because a symlink named `SKILL.md` has an ordinary name and points
    wherever its author chose. Every other member is left unread, which is why its name is held
    to no rule here: nothing is written anywhere, so no name can be a path to anything.
    """
    data = _inflated(tarball)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            return _manifest_in(archive, path)
    except tarfile.TarError:
        raise _refused("the repository archive is not a tar archive") from None


def _manifest_in(archive: tarfile.TarFile, path: str) -> bytes:
    """The one `SKILL.md` at `path` under the archive's one top folder. See `_from_tarball`."""
    members: list[tarfile.TarInfo] = []
    for member in archive:
        members.append(member)
        if len(members) > MAX_TARBALL_MEMBERS:
            raise _refused(f"the repository archive lists more than {MAX_TARBALL_MEMBERS} files")
    tops = {member.name.split("/", 1)[0] for member in members}
    if len(tops) != 1:
        raise _refused("the repository archive is not one folder, as a commit's archive is")
    (top,) = tops
    wanted = "/".join(part for part in (top, path, SKILL_FILE) if part)
    found = [member for member in members if member.name == wanted]
    where = f"the folder {path!r}" if path else "the repository's top folder"
    if not found:
        raise _refused(f"there is no {SKILL_FILE} in {where} at that commit")
    if len(found) > 1:
        raise _refused(f"the archive lists {SKILL_FILE} in {where} more than once")
    (manifest,) = found
    if not manifest.isreg():
        raise _refused(f"the {SKILL_FILE} in {where} is not a regular file")
    if manifest.size > MAX_PACKAGE_BYTES:
        raise _refused(
            f"the {SKILL_FILE} is {manifest.size} bytes, over the {MAX_PACKAGE_BYTES} limit"
        )
    handle = archive.extractfile(manifest)
    if handle is None:
        raise _refused(f"the {SKILL_FILE} in {where} could not be read")
    with handle:
        return handle.read(MAX_PACKAGE_BYTES + 1)


def read_github(source: SkillSource, tarball: bytes) -> Package:
    """The skill at one folder of one commit, from the tarball of that commit (M12.2.2).

    The source keeps the repository, the commit and the folder, which is what fetching it again
    needs, and a digest over the `SKILL.md` it read, which the commit fixes.
    """
    if source.kind is not SourceKind.GITHUB:
        raise _refused("a repository import is read from a repository source")
    raw = _from_tarball(tarball, source.path)
    text = _markdown_text(raw)
    pinned = source.model_copy(update={"content_digest": hashlib.sha256(raw).hexdigest()})
    return Package(skill=_skill_of(text), source=pinned)


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


# --------------------------------------------------------------------- editing one (M12.3.2)
def edited(
    one: LibrarySkill,
    text: str,
    *,
    by: str,
    at: datetime,
    library: Iterable[LibrarySkill],
) -> LibrarySkill:
    """The edited `SKILL.md` as a new version of `one`, undecided, or a refusal saying why.

    See `AN_EDIT_IS_A_NEW_VERSION_AND_MOVES_NO_PIN`. Parsed by the parser an import uses, so an
    edit is held to every rule an import is. The rename refusal is `ImportedSkill.with_content`'s.
    The source is the text as it arrived, which is what `SourceKind` records for anything with no
    address to fetch again, so an edit of a skill that came from a commit no longer claims that
    commit.
    """
    if not by.strip():
        raise SkillLibraryError("a skill is edited by a named person, never by an empty string")
    if at.tzinfo is None:
        raise SkillLibraryError("the time a skill was edited must be timezone-aware")
    if one.moved:
        raise _not_saved(
            f"the stored text of {one.name!r} no longer matches the version it was added as, so "
            "an edit would start from words nobody added"
        )
    raw = text.replace("\r\n", "\n").encode("utf-8")
    if len(raw) > MAX_PACKAGE_BYTES:
        raise _not_saved(f"the edit is {len(raw)} bytes, over the {MAX_PACKAGE_BYTES} limit")
    skill = _skill_of(raw.decode("utf-8"), _not_saved)
    try:
        imported = one.imported.with_content(skill)
    except SkillError as refused:
        raise _not_saved(str(refused)) from None
    if skill.digest() == one.digest:
        raise _not_saved(f"the edit is the same as {one.name!r} {one.imported.skill.version}")
    if version_key(skill.version) <= version_key(one.imported.skill.version):
        raise _not_saved(
            f"give the edit a version later than {one.imported.skill.version}. "
            f"{AN_EDIT_IS_A_NEW_VERSION_AND_MOVES_NO_PIN}"
        )
    if any(
        other.name == skill.name and other.imported.skill.version == skill.version
        for other in library
    ):
        raise _not_saved(
            f"the library already holds {skill.name!r} {skill.version}; give the edit a version "
            "of its own"
        )
    source = SkillSource(
        kind=SourceKind.UPLOAD, location=SKILL_FILE, content_digest=hashlib.sha256(raw).hexdigest()
    )
    return LibrarySkill(
        imported=ImportedSkill(skill=imported.skill, source=source),
        digest=skill.digest(),
        submitted_by=by,
        submitted_at=at,
        edited_from=one.digest,
    )


def compared_with(one: LibrarySkill, library: Iterable[LibrarySkill]) -> LibrarySkill | None:
    """The version a reviewer is shown `one`'s words against, or None for a first version.

    The newest approved version of the same name added before it, because that is what an agent
    would be moved off; otherwise the version it was edited from. A version is never compared with
    itself, and a version added later is never the baseline for an earlier one.
    """
    same = [
        other
        for other in library
        if other.name == one.name
        and other.digest != one.digest
        and other.submitted_at <= one.submitted_at
    ]
    approved = [other for other in same if other.imported.is_executable()]
    if approved:
        return max(approved, key=lambda other: (other.submitted_at, other.digest))
    if one.edited_from is not None:
        return next((other for other in same if other.digest == one.edited_from), None)
    return None


# ------------------------------------------------------------------------- deciding about one
def decided(one: LibrarySkill, *, reviewer: str, approve: bool, at: datetime) -> LibrarySkill:
    """The skill with a decision on it, or a refusal (M12.4.6).

    The person who added it may decide too; see
    `AN_ADMINISTRATOR_MAY_APPROVE_WHAT_THEY_IMPORTED_AND_THE_LEDGER_SAYS_SO`, and `self_decided`
    on the answer. Bytes that no longer digest to their key are refused first, because an approval
    is recorded against the key and would approve something nobody read. The second-decision
    refusal and the named-person refusal are `ImportedSkill`'s own.
    """
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
        edited_from=one.edited_from,
    )


# ------------------------------------------------------------------ categories (M12.4.13)
def categories_from(typed: Iterable[str]) -> tuple[str, ...]:
    """Categories as an administrator typed them, folded, deduplicated and sorted, or a refusal.

    Folded to lower case with runs of spaces as one hyphen, so "Web maintenance" and
    "web-maintenance" are one chip. An empty entry is dropped rather than refused, because a
    trailing comma is how a list is commonly typed. An empty answer clears the skill's categories.
    """
    folded: set[str] = set()
    for one in typed:
        name = "-".join(one.strip().lower().split())
        if not name:
            continue
        if not CATEGORY_RE.match(name):
            raise SkillLibraryError(
                f"nothing was saved: the category {one.strip()!r} is not one this install keeps; "
                "use letters, digits and hyphens, at most 40"
            )
        folded.add(name)
    if len(folded) > MAX_CATEGORIES:
        raise SkillLibraryError(
            f"nothing was saved: a skill carries at most {MAX_CATEGORIES} categories"
        )
    return tuple(sorted(folded))


def chips(categories: Mapping[str, Sequence[str]], shown: Iterable[str]) -> tuple[str, ...]:
    """The categories to offer as filters: those of the skills this reader was shown, and no other.

    Asked of the names on the page rather than of the table, so a category that only a skill the
    reader may not see carries is never a chip, which would name that skill's filing to them.
    """
    return tuple(sorted({category for name in set(shown) for category in categories.get(name, ())}))


def queue_entries(library: Sequence[LibrarySkill], now: datetime) -> tuple[Placed[QueueEntry], ...]:
    """Every skill waiting for a decision, oldest first, placed nowhere.

    `brain.tools.review.pending` builds each entry, so what counts as waiting and what counts as an
    edit are that module's answers; it is asked one skill at a time because it keys a submission
    time by name, and two waiting versions of one skill would otherwise share one. An entry is
    diffed against `compared_with`, the version its reviewer is shown it against: the newest
    approved one added before it, and otherwise the version it was edited from. Until 2026-09-28
    only an approved version was a baseline, so an edit of a version still waiting read as a first
    submission and the queue said "0 of them edits" beside one. Placed at `NOWHERE`, because a
    skill belongs to no department. See `may_read_library`.
    """
    entries: list[QueueEntry] = []
    for one in library:
        previous = compared_with(one, library)
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


# --------------------------------------------------------- retiring a version (M27.15.56)
@dataclass(frozen=True)
class Retirement:
    """Whether one version is retired now, and who said so when. The newest row for its digest."""

    digest: str
    retired: bool
    set_by: str
    at: datetime


def retired_digests(retirements: Mapping[str, Retirement]) -> frozenset[str]:
    """The versions retired now: those whose newest row says so. A version with no row is not."""
    return frozenset(digest for digest, one in retirements.items() if one.retired)


def retiring(one: LibrarySkill, *, retire: bool, current: Retirement | None) -> None:
    """Refuse a retirement that would change nothing, saying why; otherwise return.

    Retiring a retired version, or reinstating one that is not retired, would add a row and a
    ledger entry saying something happened that did not. See
    `A_RETIRED_VERSION_IS_KEPT_AND_ONLY_REFUSED_TO_NEW_AGENTS`.
    """
    retired = current is not None and current.retired
    if retire and retired:
        raise SkillLibraryError(f"nothing was retired: {one.name} {one.imported.skill.version} is")
    if not retire and not retired:
        raise SkillLibraryError(
            f"nothing was reinstated: {one.name} {one.imported.skill.version} is not retired"
        )


def holding(digest: str, pins: Iterable[SkillPin]) -> tuple[str, ...]:
    """The agents among these pins still running these bytes, in id order, each once.

    Asked of the pins of agents the reader may already see and nothing wider, so a retirement's
    answer never names an agent the roster would not list, and never counts the rest.
    """
    return tuple(sorted({pin.agent_id for pin in pins if pin.digest == digest}))


# ------------------------------------------------------- current assignments (M27.15.55)
@dataclass(frozen=True)
class AssignmentRecord:
    """One assignment row, as the history holds it."""

    assignment_id: str
    agent_id: str
    skill_name: str
    digest: str
    assigned_by: str
    at: datetime


@dataclass(frozen=True)
class DetachmentRecord:
    """One detachment row: the assignment it ended, when there was one."""

    assignment_id: str | None
    agent_id: str
    skill_name: str
    digest: str
    detached_by: str
    at: datetime


def current_assignments(
    assignments: Iterable[AssignmentRecord], detachments: Iterable[DetachmentRecord]
) -> tuple[AssignmentRecord, ...]:
    """The assignments still in force: no detachment names them and none later replaced them.

    Per agent and skill name the newest assignment is the only candidate, because a later one of
    the same skill to the same agent is a replacement, `0056`'s `replaces_digest`; it is current
    unless a detachment names it. Derived from the rows and never stored, so no row is updated to
    say an assignment ended. See
    `A_DETACHMENT_IS_A_ROW_AND_THE_CURRENT_ASSIGNMENTS_ARE_WHAT_NO_ROW_ENDED`.
    """
    ended = {one.assignment_id for one in detachments if one.assignment_id is not None}
    newest: dict[tuple[str, str], AssignmentRecord] = {}
    for one in sorted(assignments, key=lambda row: (row.at, row.assignment_id)):
        newest[(one.agent_id, one.skill_name)] = one
    return tuple(one for _key, one in sorted(newest.items()) if one.assignment_id not in ended)


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


# ---------------------------------------------------------------------- detaching a skill
@dataclass(frozen=True)
class Detachment:
    """One skill off one agent: the install to write, and what the row records."""

    agent_id: str
    skill_name: str
    #: The bytes the agent ran, which the row records.
    digest: str
    detached_by: str
    instance: TemplateInstance
    effective_document: Mapping[str, JsonValue]
    effective_hash: str


def detachment(
    one: LibrarySkill,
    *,
    record: AgentRecord,
    signed: SignedManifest,
    instance: TemplateInstance,
    by: EntitlementSet,
    recorder: AuditRecorder,
    now: datetime,
) -> Detachment:
    """Take one skill off one agent through `detach`, or refuse saying why.

    The version asked for must be the one the agent runs: detaching bytes an agent does not run
    would record a change that did not happen, and an agent running another version of the skill is
    told so rather than having that other version removed. Then the install is `set_field` on
    `skills` with the skill left out, materialised again, and the authority compared before and
    after, `assignment`'s check, for its reason. See
    `A_DETACHMENT_IS_A_ROW_AND_THE_CURRENT_ASSIGNMENTS_ARE_WHAT_NO_ROW_ENDED`.
    """
    before = materialise(signed, instance, audience=record.audience)
    composition = pins_on(signed, instance, record)
    same = [pin for pin in composition.attached_to(Part.SKILLS) if pin.ref == one.name]
    if not same:
        raise SkillLibraryError(
            f"nothing was detached: {record.display_name} does not run {one.name}"
        )
    if all(pin.version != one.digest for pin in same):
        raise SkillLibraryError(
            f"nothing was detached: {record.display_name} runs another version of {one.name}"
        )
    detached = detach(
        composition, Part.SKILLS, one.name, recorder=recorder, reason_code=DETACH_REASON
    )
    skills: list[JsonValue] = [
        {"name": pin.ref, "digest": pin.version}
        for pin in sorted(
            detached.composition.attached_to(Part.SKILLS), key=lambda pin: (pin.ref, pin.version)
        )
    ]
    changed = set_field(instance, SKILLS_PATH, skills, by=by.principal_id, at=now)
    after = materialise(signed, changed, audience=record.audience)
    if moved_authority(before.record, after.record):
        raise SkillLibraryError(
            f"nothing was detached: {A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER}"
        )
    return Detachment(
        agent_id=record.agent_id,
        skill_name=one.name,
        digest=one.digest,
        detached_by=by.principal_id,
        instance=changed,
        effective_document=dict(after.document),
        effective_hash=after.config_hash,
    )
