"""The skill library: a skill added from a package, a decision about it, and its assignments.

`brain.tools.skills` has held every rule about an imported skill since M12.2, and nothing stored
one: `brain.skill_routes` said so on every answer, because a screen offering to approve or assign
a skill with nowhere for the approval to live would be an approval granted by whoever typed a
digest. `migrations/versions/0056_skill_library.py` holds the argument for the policies and the
triggers; what is here is the model that mirrors it.

**Three tables, each written once and never edited.** A skill as it arrived, a decision about
exactly those bytes, and an assignment of those bytes to an agent. Each is a fact about a moment,
so the application role is granted SELECT and INSERT and nothing else, which is `0052`'s argument
about a review decision: a row rewritten would be a decision whose author changed afterwards.

**The digest is the key, and it is not trusted on the way back out.** `brain.tools.skills.Skill.
digest` is over every field a reviewer read, so two imports of the same bytes are one row and a
second one is refused by the key rather than by a read first. The fields are stored beside it and
the digest is recomputed when a row is read: a body edited in place by an operator no longer
digests to its key, `ImportedSkill.is_executable` goes false, and nothing can attach it.

**Nobody decides about a skill they added, and the database says so as well as the domain.** A
decision row carries the importer's id as well as the decider's, a composite key holds that copy
to the skill row it names, and `nobody_decides_their_own_import` refuses the two being one person.
A key rather than a trigger reading the other table, so the rule is a declaration a reviewer can
read in the table's definition, which is the reason `brain.tables.template` gives for a seal being
a check constraint rather than a validator.

**Only an approved skill can be assigned, and that too is a key.** An assignment carries the word
`approved` in a column that may hold nothing else, and its key into the decision table is the
digest and that word together, so an assignment of bytes nobody approved, or bytes somebody
rejected, names no decision row and is refused. Its key into the skill table is the digest and the
name together, so the name the ledger entry records is the name of the skill that was assigned.

**No `updated_at`, no `deleted_at`, and no key into `auth.principal`**, for the reasons
`brain.tables.credential` gives: nothing here is updated, nothing is retired, and an actor is a
value so the record outlives the person.

**`0121` widens three things and adds a fourth table** (M12.2.2, M12.2.3, M12.3.2, M12.4.6,
M12.4.13). A skill may come from a repository commit or an https address as well as an upload, and a
repository source names its commit, and its folder when that is not the top one. An edit is a new
row naming the version it was edited from, which the key holds to a row that exists. A decision by
the person who added the skill is admitted, and only as a row that says so in `self_decided`: the
check that refused it keeps its name and now reads "nobody decides their own import unless the row
says it is their own", so a self-approval can never be written as an ordinary one. Categories are a
fourth table, `agent.skill_category`, one row per change and the newest per name the one that
applies, because a label is not part of the procedure and changing one must not send a skill back
to review. Every constraint `0121` adds binds only a column it added, for
`brain.deployment.compatibility`'s reason about the release still running during a deploy.

**`0164` adds three tables and touches none** (M12.4.11, M12.3.4). A skill's scripts, one row per
script holding its bytes and the sha256 of them, which a check holds equal, so a row cannot say
one thing and hold another; its example tasks, one row per example in the order a reviewer read
them; and a rehearsal of a version's examples, one row per rehearsal, whose `passed` a check holds
to the verdicts it records. The scripts and the examples are keyed to the skill row by its digest
and its importer together, as a decision is, so they are written by the person who added the
skill and belong to exactly those bytes. **They are separate tables rather than columns on
`agent.skill`** so the release running during a deploy writes skill rows it has always written;
that release reads a skill with scripts or examples without them, digests it differently from
its key, and treats it as changed since approval, which is the safe direction.

Task ids: M42.6.4, M12.2.2, M12.2.3, M12.3.2, M12.4.6, M12.4.13, M12.4.11, M12.3.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import DIGEST, IDENTIFIER
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: Widths, named once so the model, the migration and the store agree.
DIGEST_CHARS: Final = 64
#: `brain.tools.skills.Skill.name`'s own bound.
NAME_CHARS: Final = 80
#: `brain.tools.skills.Skill.description`'s own bound.
DESCRIPTION_CHARS: Final = 400
VERSION_CHARS: Final = 32
#: `brain.tools.skills.SkillSource.location`'s own bound.
LOCATION_CHARS: Final = 400
AGENT_ID_CHARS: Final = 128
DECISION_CHARS: Final = 16
SOURCE_KIND_CHARS: Final = 16
#: A full git commit sha. `brain.tools.skills.COMMIT_RE`'s width.
COMMIT_CHARS: Final = 40
#: `brain.tools.skills.SkillSource.path`'s own bound.
PATH_CHARS: Final = 200

#: `brain.tools.skills.SKILL_NAME_RE`, restated because this package sits underneath the tools
#: layer's callers; a test holds the two equal.
SKILL_NAME_PATTERN: Final = r"^[a-z][a-z0-9_-]{0,79}$"

#: `brain.tools.skills.VERSION_RE` in ASCII digits. The domain's `\d` also admits digits from
#: other scripts, which `brain.console.skill_library` refuses before a row is written, so the two
#: admit the same versions for everything that reaches this table.
VERSION_PATTERN: Final = r"^[0-9]+[.][0-9]+[.][0-9]+$"

#: The sources a skill is taken from: `0056`'s upload, and `0121`'s repository commit and address.
UPLOAD: Final = "upload"
GITHUB: Final = "github"
URL: Final = "url"
SOURCE_KINDS: Final[tuple[str, ...]] = (GITHUB, UPLOAD, URL)

#: `brain.tools.skills.COMMIT_RE`, restated for the reason `SKILL_NAME_PATTERN` gives.
COMMIT_PATTERN: Final = r"^[0-9a-f]{40}$"

#: A repository folder: names of letters, digits, dot, underscore and hyphen, joined by slashes.
#: Looser than the domain, which also refuses `.` and `..`; a check refusing those needs a
#: lookahead, and the domain refuses them before a row is written.
PATH_PATTERN: Final = r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$"

#: `brain.console.skill_library.MAX_CATEGORIES`, restated for the same reason.
MAX_CATEGORIES: Final = 8

#: `brain.tools.skills.MAX_MEMBER_LENGTH`, the longest path a script may have. `0164`.
SCRIPT_PATH_CHARS: Final = 200

#: A script's path inside its skill's folder: segments of the archive member grammar joined by
#: slashes, `brain.tools.skills.ARCHIVE_SEGMENT_RE` without its length, which the width holds.
SCRIPT_PATH_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$"

#: `brain.console.skill_library.MAX_PACKAGE_BYTES`, the most one script may hold. `0164`.
MAX_SCRIPT_BYTES: Final = 256 * 1024

#: `brain.tools.skills.MAX_EXAMPLES` and `EXAMPLE_CHARS`, restated for the same reason. `0164`.
MAX_EXAMPLES: Final = 20
EXAMPLE_CHARS: Final = 500

#: A script row holds the bytes its sha256 names, and nothing else. `0164`.
SCRIPT_SHA256_IS_OF_ITS_CONTENT: Final = "content_sha256 = encode(sha256(content), 'hex')"

#: A rehearsal passed exactly when no example in it failed to behave. `0164`.
PASSED_WHEN_NO_EXAMPLE_FAILED: Final = "passed = (NOT (behaved @> '[false]'::jsonb))"

#: The source rule `0121` widened, under the name `0056` gave it.
SOURCE_KIND_CHECK: Final = f"source_kind IN ('{GITHUB}', '{UPLOAD}', '{URL}')"

#: The decider rule `0121` widened, under the name `0056` gave it: nobody decides their own import
#: unless the row says it is their own. Written with the operands of `0056`'s the other way round,
#: so the old predicate is not a substring of the new one and a supersession can be told apart.
NOBODY_DECIDES_THEIR_OWN_UNLESS_SAID: Final = "self_decided OR submitted_by <> decided_by"

#: The two decisions, as `brain.tools.skills.SkillState` spells the states they lead to.
APPROVED: Final = "approved"
REJECTED: Final = "rejected"


class SkillRow(Base):
    """`agent.skill`. One skill as it arrived, keyed by the digest of what a reviewer reads."""

    __tablename__ = "skill"

    digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    version: Mapped[str] = mapped_column(String(VERSION_CHARS), nullable=False)
    description: Mapped[str] = mapped_column(String(DESCRIPTION_CHARS), nullable=False)
    #: The instructions. Read by a reviewer on the Skills screen and by nobody else before a
    #: decision; `brain.tools.skills.body_of` refuses it to an agent until then.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: The tool names the `SKILL.md` declares, sorted. Names and never capabilities.
    tools: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(SOURCE_KIND_CHARS), nullable=False)
    source_location: Mapped[str] = mapped_column(String(LOCATION_CHARS), nullable=False)
    #: A sha256 over the bytes that arrived, which is `SkillSource.content_digest`.
    source_content_digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    #: Who added it. The ledger entry's actor, read off this column by the trigger.
    submitted_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: A repository source's full commit, and nothing on any other source. `0121`.
    source_commit: Mapped[str | None] = mapped_column(String(COMMIT_CHARS), nullable=True)
    #: A repository source's folder, when the `SKILL.md` is not at its top. `0121`.
    source_path: Mapped[str | None] = mapped_column(String(PATH_CHARS), nullable=True)
    #: The version this one was edited from, when it is an edit. `0121`.
    edited_from: Mapped[str | None] = mapped_column(
        String(DIGEST_CHARS), ForeignKey("agent.skill.digest"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"digest ~ '{DIGEST}'", name="digest_shape"),
        CheckConstraint(f"name ~ '{SKILL_NAME_PATTERN}'", name="name_shape"),
        CheckConstraint(f"version ~ '{VERSION_PATTERN}'", name="version_shape"),
        CheckConstraint("length(btrim(description)) > 0", name="description_present"),
        CheckConstraint("jsonb_typeof(tools) = 'array'", name="tools_are_a_list"),
        # `0056`'s name, and `0121`'s wider predicate; see the module docstring.
        CheckConstraint(SOURCE_KIND_CHECK, name="source_is_an_upload"),
        CheckConstraint("length(btrim(source_location)) > 0", name="source_location_present"),
        CheckConstraint(f"source_content_digest ~ '{DIGEST}'", name="source_digest_shape"),
        CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_is_an_identifier"),
        # `uq_`, because `brain.db.NAMING_CONVENTION` has no `constraint_name` token for a unique
        # constraint, so a name given here is used verbatim. Both exist to be pointed at.
        UniqueConstraint("digest", "submitted_by", name="uq_skill_digest_submitted_by"),
        UniqueConstraint("digest", "name", name="uq_skill_digest_name"),
        CheckConstraint(
            f"source_commit IS NULL OR source_commit ~ '{COMMIT_PATTERN}'",
            name="source_commit_shape",
        ),
        CheckConstraint(
            f"(source_kind = '{GITHUB}') = (source_commit IS NOT NULL)",
            name="a_repository_source_names_its_commit",
        ),
        CheckConstraint(
            f"source_path IS NULL OR (source_kind = '{GITHUB}' AND source_path ~ '{PATH_PATTERN}')",
            name="source_path_on_a_repository_source",
        ),
        CheckConstraint(
            f"edited_from IS NULL OR (edited_from ~ '{DIGEST}' AND edited_from <> digest)",
            name="edited_from_another_version",
        ),
        {"schema": "agent"},
    )


class SkillReviewRow(Base):
    """`agent.skill_review`. One decision about one skill's bytes, by somebody else."""

    __tablename__ = "skill_review"

    digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), primary_key=True)
    #: The importer, copied and held to the skill row by the composite key.
    submitted_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    decision: Mapped[str] = mapped_column(String(DECISION_CHARS), nullable=False)
    #: Who decided. The ledger entry's actor, read off this column by the trigger.
    decided_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: Decided by the person who added the skill, which only such a row may say. `0121`.
    self_decided: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    __table_args__ = (
        CheckConstraint(
            f"decision IN ('{APPROVED}', '{REJECTED}')", name="decision_is_approved_or_rejected"
        ),
        CheckConstraint(f"decided_by ~ '{IDENTIFIER}'", name="decided_by_is_an_identifier"),
        # `0056`'s name, and `0121`'s wider predicate; see the module docstring.
        CheckConstraint(
            NOBODY_DECIDES_THEIR_OWN_UNLESS_SAID, name="nobody_decides_their_own_import"
        ),
        UniqueConstraint("digest", "decision", name="uq_skill_review_digest_decision"),
        ForeignKeyConstraint(
            ["digest", "submitted_by"],
            ["agent.skill.digest", "agent.skill.submitted_by"],
        ),
        CheckConstraint(
            "NOT self_decided OR decided_by = submitted_by",
            name="self_decided_only_by_the_importer",
        ),
        {"schema": "agent"},
    )


class SkillAssignmentRow(Base):
    """`agent.skill_assignment`. One approved skill pinned to one agent, by one person."""

    __tablename__ = "skill_assignment"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    #: Always `approved`, and the second half of the key into the decision table.
    approval: Mapped[str] = mapped_column(
        String(DECISION_CHARS), nullable=False, server_default=text(f"'{APPROVED}'")
    )
    #: The digest of the same skill this agent was pinned to before, when this replaced one.
    replaces_digest: Mapped[str | None] = mapped_column(String(DIGEST_CHARS), nullable=True)
    #: Who assigned it. The ledger entry's actor, read off this column by the trigger.
    assigned_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        CheckConstraint(f"approval = '{APPROVED}'", name="only_an_approved_skill_is_assigned"),
        CheckConstraint(
            f"replaces_digest IS NULL OR (replaces_digest ~ '{DIGEST}' "
            "AND replaces_digest <> digest)",
            name="replaces_another_version",
        ),
        CheckConstraint(f"assigned_by ~ '{IDENTIFIER}'", name="assigned_by_is_an_identifier"),
        ForeignKeyConstraint(
            ["digest", "approval"],
            ["agent.skill_review.digest", "agent.skill_review.decision"],
        ),
        ForeignKeyConstraint(
            ["digest", "skill_name"],
            ["agent.skill.digest", "agent.skill.name"],
        ),
        {"schema": "agent"},
    )


class SkillCategoryRow(Base):
    """`agent.skill_category`. The categories an administrator set on a skill's name, once.

    Appended and never edited: the newest row for a name is the categories that apply, and the rows
    before it are what they were. Keyed by name rather than by digest, because every version of a
    skill shares its filing, and not held to `agent.skill` by a key, because a name is not unique
    there; the route sets categories only on a name it read from the library. `0121`.
    """

    __tablename__ = "skill_category"

    #: The order rows were written in, which is what "newest" means here.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    skill_name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    #: Folded category names, sorted. Never a capability; a label a reader filters by.
    categories: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    #: Who set them. The ledger entry's actor, read off this column by the trigger.
    set_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"skill_name ~ '{SKILL_NAME_PATTERN}'", name="skill_name_shape"),
        CheckConstraint(
            "CASE WHEN jsonb_typeof(categories) = 'array' "
            f"THEN jsonb_array_length(categories) <= {MAX_CATEGORIES} ELSE false END",
            name="categories_are_a_short_list",
        ),
        CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        {"schema": "agent"},
    )


class SkillRetirementRow(Base):
    """`agent.skill_retirement`. A version retired, or reinstated, once per row. `0139`.

    The newest row for a digest is its state and the rows before it are what it was, the shape
    `SkillCategoryRow` has; a digest with no row was never retired. Keyed to `agent.skill` by the
    digest, because retiring bytes nobody added would be a statement about nothing. A retired
    version stays in the library and on every agent already running it: only a new assignment is
    refused (M27.15.56).
    """

    __tablename__ = "skill_retirement"

    #: The order rows were written in, which is what "newest" means here.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    digest: Mapped[str] = mapped_column(
        String(DIGEST_CHARS), ForeignKey("agent.skill.digest"), nullable=False
    )
    #: True from this row on the version is retired; false, it is reinstated.
    retired: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Who retired or reinstated it. The ledger entry's actor, read off this column by the trigger.
    set_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"set_by ~ '{IDENTIFIER}'", name="set_by_is_an_identifier"),
        {"schema": "agent"},
    )


class SkillDetachmentRow(Base):
    """`agent.skill_detachment`. One skill taken off one agent, by one person. `0139`.

    Names the assignment it ends when the skill got there by one, held by a key and unique, so an
    assignment is ended at most once; a skill the template pinned has no assignment and the column
    is empty. The current assignments are those no detachment names and no later assignment of the
    same skill to the same agent replaced, so nothing is ever updated to say one ended (M27.15.55).
    """

    __tablename__ = "skill_detachment"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent.skill_assignment.id"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    #: The bytes the agent ran when it was detached.
    digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    #: Who detached it. The ledger entry's actor, read off this column by the trigger.
    detached_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        CheckConstraint(f"skill_name ~ '{SKILL_NAME_PATTERN}'", name="skill_name_shape"),
        CheckConstraint(f"digest ~ '{DIGEST}'", name="digest_shape"),
        CheckConstraint(f"detached_by ~ '{IDENTIFIER}'", name="detached_by_is_an_identifier"),
        UniqueConstraint("assignment_id", name="uq_skill_detachment_assignment_id"),
        {"schema": "agent"},
    )


class SkillScriptRow(Base):
    """`agent.skill_script`. One declared script of one skill: its bytes and their sha256. `0164`.

    Keyed by the skill's digest and the script's path, so a script is held once per version, and
    held to `agent.skill` by the digest and the importer together, so its bytes were written by the
    person who added those bytes. The check holds the sha256 to the bytes, and the application may
    insert and read and never update, so a script's bytes cannot be changed under the digest a
    reviewer approved (M12.4.11).
    """

    __tablename__ = "skill_script"

    skill_digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), primary_key=True)
    path: Mapped[str] = mapped_column(String(SCRIPT_PATH_CHARS), primary_key=True)
    #: The script as it arrived. Read to run it or export it and never to list the library.
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    #: `brain.tools.skills.ScriptFile.sha256`, which the skill's digest covers.
    content_sha256: Mapped[str] = mapped_column(String(DIGEST_CHARS), nullable=False)
    #: The importer, copied and held to the skill row by the composite key.
    submitted_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"skill_digest ~ '{DIGEST}'", name="skill_digest_shape"),
        CheckConstraint(f"path ~ '{SCRIPT_PATH_PATTERN}'", name="path_shape"),
        CheckConstraint(f"content_sha256 ~ '{DIGEST}'", name="content_sha256_shape"),
        CheckConstraint(SCRIPT_SHA256_IS_OF_ITS_CONTENT, name="content_sha256_is_of_its_content"),
        CheckConstraint(f"octet_length(content) <= {MAX_SCRIPT_BYTES}", name="content_is_a_script"),
        CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_is_an_identifier"),
        ForeignKeyConstraint(
            ["skill_digest", "submitted_by"],
            ["agent.skill.digest", "agent.skill.submitted_by"],
        ),
        {"schema": "agent"},
    )


class SkillExampleRow(Base):
    """`agent.skill_example`. One example task of one skill and the behaviour expected. `0164`.

    Keyed by the skill's digest and the example's ordinal, from one, so the examples read back in
    the order a reviewer read them, and held to `agent.skill` as a script is (M12.3.4).
    """

    __tablename__ = "skill_example"

    skill_digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), primary_key=True)
    ordinal: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    task: Mapped[str] = mapped_column(String(EXAMPLE_CHARS), nullable=False)
    expected: Mapped[str] = mapped_column(String(EXAMPLE_CHARS), nullable=False)
    #: The importer, copied and held to the skill row by the composite key.
    submitted_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(f"skill_digest ~ '{DIGEST}'", name="skill_digest_shape"),
        CheckConstraint(
            f"ordinal BETWEEN 1 AND {MAX_EXAMPLES}", name="ordinal_is_one_of_the_examples"
        ),
        CheckConstraint("length(btrim(task)) > 0", name="task_present"),
        CheckConstraint("length(btrim(expected)) > 0", name="expected_present"),
        CheckConstraint(f"submitted_by ~ '{IDENTIFIER}'", name="submitted_by_is_an_identifier"),
        ForeignKeyConstraint(
            ["skill_digest", "submitted_by"],
            ["agent.skill.digest", "agent.skill.submitted_by"],
        ),
        {"schema": "agent"},
    )


class SkillRehearsalRow(Base):
    """`agent.skill_rehearsal`. One rehearsal of one version's example tasks. `0164`.

    Appended and never edited: the newest row for a digest is the rehearsal that decides whether
    the version may be approved, and the rows before it are what earlier rehearsals found, the
    shape `SkillRetirementRow` has. `behaved` is a verdict per example in order, and the check
    holds `passed` to it, so a row cannot say it passed while recording an example that did not
    behave (M12.3.4).
    """

    __tablename__ = "skill_rehearsal"

    #: The order rows were written in, which is what "newest" means here.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    digest: Mapped[str] = mapped_column(
        String(DIGEST_CHARS), ForeignKey("agent.skill.digest"), nullable=False
    )
    #: Whether each example behaved as expected, as a JSON list of booleans in example order.
    behaved: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Who rehearsed it. The ledger entry's actor, read off this column by the trigger.
    rehearsed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "CASE WHEN jsonb_typeof(behaved) = 'array' "
            f"THEN jsonb_array_length(behaved) BETWEEN 1 AND {MAX_EXAMPLES} ELSE false END",
            name="behaved_is_a_verdict_per_example",
        ),
        CheckConstraint(PASSED_WHEN_NO_EXAMPLE_FAILED, name="passed_when_no_example_failed"),
        CheckConstraint(f"rehearsed_by ~ '{IDENTIFIER}'", name="rehearsed_by_is_an_identifier"),
        {"schema": "agent"},
    )
