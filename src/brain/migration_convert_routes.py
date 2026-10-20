"""What a person pastes from the old system is checked by the migration package before anything
is done with it: skills, the exported items, the memory files and the agents' availability.

`brain.migration` is a package of refusals and its first three modules were given a database and a
route (`brain.migration_routes`). The other four each held functions nobody called:
`skills.proposed_description`, `router_descriptions`, `unproven` and `to_retire`;
`carry.reparse_plan`, `carried_vectors`, `export_gaps`, `seed_gaps` and `archive`;
`learning.re_derive` and `learning_note`; and `rebuild.audience_for`. This is their call site, as
four POST routes that **read what they are given, say what the package says about it, and keep
nothing**.

**Nothing here imports, approves, retires, ingests, seeds or files anything.** That is not a gap in
the routes, it is what each package is. A skill still arrives unreviewed through the ordinary
skills route (`brain.migration.skills.IT_WORKED_OVER_THERE_IS_A_STATEMENT_ABOUT_A_DIFFERENT_SYSTEM`
says why),
a re-parse is queued by the knowledge pipeline from the original bytes and not from this answer, a
derived preference becomes a proposal only when a person files it, and an agent is rebuilt from a
template by the gallery's install route. What an administrator gets is the list the package would
have refused, before any of those acts, in the package's own words. A route that also did the act
would be a second way to do it, and the second way is the one that skips the review.

**The register is the one the migration route keeps.** The carry route compares the export with the
newest saved register, and says so when there is none or it is not agreed yet, because an export
checked against a register nobody agreed is checked against nothing
(`brain.migration.inventory.A_MIGRATION_AGREED_IN_PIECES_IS_AGREED_BY_NOBODY`). The parts that need
no register (the re-parse plan, the vectors discarded, the seed findings) are answered either way.

**A derivation that is refused does not stop the others.** A memory file the person drew five
conclusions from, one of which would widen who may see what, returns four derivations and one
refusal in the package's words. Refusing the whole paste for the one would teach people to paste
one at a time.

**One authority, held over everything** (`admin:install_setting`) and the `migration_workspace`
switch, the same as the migration route. Refused before the database to anyone without the
authority.

Task ids: M37.1.2.1, M37.1.2.2, M37.1.2.3, M37.1.2.4, M37.2.2.2, M37.2.2.4, M37.2.2.5, M37.2.3.4,
M37.2.4.2, M37.2.4.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.knowledge.visibility import Visibility
from brain.memory.tiers import Change
from brain.migration import carry, learning, rebuild, skills
from brain.migration.inventory import MigrationError, agree
from brain.migration_routes import (
    RegisterAsked,
    _not_answerable,
    _refused_because,
    _require_sessions,
    _switched_on,
    may_run_a_migration,
    register_of,
)
from brain.ops import migration_record_store
from brain.tables.migration_record import RecordKind

log = structlog.get_logger()

Name = Annotated[str, Field(min_length=1, max_length=240)]

MOST: int = 5000


# ------------------------------------------------------------------------------- skills
class PastedForeignSkillAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Name
    description: Annotated[str, Field(min_length=1, max_length=4000)]
    last_invoked_at: datetime | None = None


class PastedBehaviourCheckAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    skill_name: Name
    task: Name
    same_answer: bool
    checked_by: Name


class PastedSkillsAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    skills: list[PastedForeignSkillAsked] = Field(max_length=MOST)
    checks: list[PastedBehaviourCheckAsked] = Field(default_factory=list, max_length=MOST)
    #: The instant the ninety days are counted back from. Defaults to the request's own.
    now: datetime | None = None


class PastedSkillConversionView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    proposed_description: str


class PastedSkillsConvertedView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    descriptions: list[PastedSkillConversionView]
    #: Skills whose description is still written at a router, named in the package's words.
    still_written_at_a_router: list[str]
    #: Skills to leave behind, not invoked inside the window or never recorded as invoked.
    to_retire: list[str]
    #: Skills no real task has been run through, and ones whose answer changed.
    unproven: list[str]
    nothing_was_imported: bool = True


# ------------------------------------------------------------------------------- carrying
class PastedExportAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: Name
    content_digest: Name
    vector_count: int = Field(default=0, ge=0)
    vector_width: int | None = Field(default=None, ge=1)
    embedded_by: str = ""


class PastedSeedAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    external_id: Name
    name: Name
    source_record: Name


class PastedConversationKeptAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: Name
    because: Name
    stated_by: Name


class PastedCarryAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exports: list[PastedExportAsked] = Field(default_factory=list, max_length=MOST)
    seeds: list[PastedSeedAsked] = Field(default_factory=list, max_length=MOST)
    conversations_kept: list[PastedConversationKeptAsked] = Field(
        default_factory=list, max_length=MOST
    )


class PastedReparseView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    content_digest: str


class PastedArchiveView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    archived: list[str]
    kept_as_artefacts: list[str]
    searchable: list[str]


class PastedCarryView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Every export, to be read again from its original bytes. There is no field for a vector.
    reparse: list[PastedReparseView]
    vectors_discarded: list[str]
    seed_findings: list[str]
    #: Whether a saved register that is agreed was found to compare the export and the
    #: conversations with. When it was not, the two parts that need one are empty and `why` says so.
    register_agreed: bool
    export_gaps: list[str]
    archive: PastedArchiveView | None
    why: str


# ------------------------------------------------------------------------------- learning
class PastedMemoryAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_file: Name
    text: Annotated[str, Field(min_length=1, max_length=20000)]
    written_at: datetime | None = None


class PastedDerivationAsked(BaseModel):
    """One conclusion a person drew from one old memory file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_file: Name
    change: str
    subject: Name
    derived_by: Name
    because: Name


class PastedLearningAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    memories: list[PastedMemoryAsked] = Field(max_length=MOST)
    derivations: list[PastedDerivationAsked] = Field(default_factory=list, max_length=MOST)


class PastedDerivedView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_file: str
    change: str
    derived_by: str


class PastedRefusedView(BaseModel):
    """One thing the package refused, named by the file or the agent it was about."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    because: str


class PastedLearningView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    derived: list[PastedDerivedView]
    refused: list[PastedRefusedView]
    derived_twice: list[str]
    note: str
    files_read: int
    readers: list[str]
    #: True while nothing here files a derivation as a proposal. A field, so the sentence leaves
    #: the page in the commit that makes it false.
    nothing_was_filed: bool = True


# ------------------------------------------------------------------------------- audience
class PastedForeignAgentAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Name
    availability: Name
    tools: list[str] = Field(default_factory=list, max_length=200)


class PastedAudienceAsked(BaseModel):
    """The agents, what each availability means here, and whose agents they will be."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agents: list[PastedForeignAgentAsked] = Field(max_length=MOST)
    #: Their availability word to one of this system's audience levels. Decided per company.
    mapping: dict[str, Visibility]
    owner_id: Name
    department: str = ""


class PastedAudienceView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    level: str


class PastedAudiencesView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    audiences: list[PastedAudienceView]
    #: Agents whose availability nobody mapped, in the package's words. Never defaulted.
    unmapped: list[PastedRefusedView]
    #: What this does not decide: what each agent may reach, which is its authority.
    authority_is_not_decided_here: bool = True


router = APIRouter(prefix=API_PREFIX, tags=["migration"])


async def _begin(request: Request, asked: Asked) -> None:
    """Authority first, then the database, then the switch: the migration route's own order."""
    if not may_run_a_migration(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)


@router.post(
    "/migration/skills/convert",
    response_model=PastedSkillsConvertedView,
    responses=COMMON_RESPONSES,
)
async def convert_skills(
    request: Request, body: PastedSkillsAsked, asked: Asked
) -> PastedSkillsConvertedView:
    """Say what the package would do with these skills: a description to read, what is still
    written at a router, what to leave behind and what nobody has run a real task through."""
    await _begin(request, asked)
    try:
        foreign = [
            skills.ForeignSkill(
                name=one.name, description=one.description, last_invoked_at=one.last_invoked_at
            )
            for one in body.skills
        ]
        checks = [
            skills.BehaviourCheck(
                skill_name=one.skill_name,
                task=one.task,
                same_answer=one.same_answer,
                checked_by=one.checked_by,
            )
            for one in body.checks
        ]
        return PastedSkillsConvertedView(
            descriptions=[
                PastedSkillConversionView(
                    name=one.name, proposed_description=skills.proposed_description(one)
                )
                for one in foreign
            ],
            still_written_at_a_router=list(skills.router_descriptions(foreign)),
            to_retire=list(skills.to_retire(foreign, now=body.now or asked.now)),
            unproven=list(skills.unproven(foreign, checks)),
        )
    except (MigrationError, ValueError) as refused:
        raise _refused_because(str(refused)) from None


@router.post("/migration/carry", response_model=PastedCarryView, responses=COMMON_RESPONSES)
async def check_carry(request: Request, body: PastedCarryAsked, asked: Asked) -> PastedCarryView:
    """Say what must be re-read, which vectors are discarded, which seeds a person must look at, and
    where the export and the agreed register disagree."""
    await _begin(request, asked)
    try:
        exports = [
            carry.Export(
                item_id=one.item_id,
                content_digest=one.content_digest,
                vector_count=one.vector_count,
                vector_width=one.vector_width,
                embedded_by=one.embedded_by,
            )
            for one in body.exports
        ]
        seeds = [
            carry.EntitySeed(
                external_id=one.external_id, name=one.name, source_record=one.source_record
            )
            for one in body.seeds
        ]
        kept = [
            carry.ConversationImport(
                item_id=one.item_id, because=one.because, stated_by=one.stated_by
            )
            for one in body.conversations_kept
        ]
    except (MigrationError, ValueError) as refused:
        raise _refused_because(str(refused)) from None

    async with _require_sessions(request)() as session:
        saved = await migration_record_store.newest(session, RecordKind.REGISTER)
    agreed = None
    why = ""
    if saved is None:
        why = (
            "no register has been saved, so the export and the conversations are not compared "
            "with one"
        )
    else:
        try:
            catalogue, decisions, mappings = register_of(RegisterAsked.model_validate(saved.body))
            agreed = agree(catalogue, decisions, mappings)
        except MigrationError as outstanding:
            why = (
                "the saved register is not agreed yet, so nothing is compared with it: "
                f"{outstanding}"
            )
        except ValueError:
            why = "the saved register does not read, so nothing is compared with it"
    gaps: list[str] = []
    archived: PastedArchiveView | None = None
    if agreed is not None:
        gaps = list(carry.export_gaps(agreed, exports))
        try:
            made = carry.archive(agreed, kept)
        except MigrationError as refused:
            raise _refused_because(str(refused)) from None
        archived = PastedArchiveView(
            archived=list(made.archived),
            kept_as_artefacts=[one.item_id for one in made.imported],
            searchable=list(made.searchable),
        )
    return PastedCarryView(
        reparse=[
            PastedReparseView(item_id=one.item_id, content_digest=one.content_digest)
            for one in carry.reparse_plan(exports)
        ],
        vectors_discarded=list(carry.carried_vectors(exports)),
        seed_findings=list(carry.seed_gaps(seeds)),
        register_agreed=agreed is not None,
        export_gaps=gaps,
        archive=archived,
        why=why,
    )


@router.post("/migration/learning", response_model=PastedLearningView, responses=COMMON_RESPONSES)
async def check_learning(
    request: Request, body: PastedLearningAsked, asked: Asked
) -> PastedLearningView:
    """Re-derive each conclusion the ordinary way, refuse the ones that would widen a scope, and
    write the handover note from what was derived."""
    await _begin(request, asked)
    try:
        memories = [
            learning.ForeignMemory(
                source_file=one.source_file, text=one.text, written_at=one.written_at
            )
            for one in body.memories
        ]
    except (MigrationError, ValueError) as refused:
        raise _refused_because(str(refused)) from None
    by_file = {one.source_file: one for one in memories}
    derived: list[learning.Derivation] = []
    refused_ones: list[PastedRefusedView] = []
    for one in body.derivations:
        memory = by_file.get(one.source_file)
        if memory is None:
            refused_ones.append(
                PastedRefusedView(
                    subject=one.source_file,
                    because=(
                        "it is not among the memory files handed over, so there is nothing it "
                        "was derived from"
                    ),
                )
            )
            continue
        try:
            derived.append(
                learning.re_derive(
                    memory,
                    change=Change(one.change),
                    subject=one.subject,
                    derived_by=one.derived_by,
                    because=one.because,
                )
            )
        except (MigrationError, ValueError) as refused:
            refused_ones.append(PastedRefusedView(subject=one.source_file, because=str(refused)))
    note = learning.learning_note(derived, memories)
    return PastedLearningView(
        derived=[
            PastedDerivedView(
                source_file=one.source_file,
                change=one.proposal.change.value,
                derived_by=one.derived_by,
            )
            for one in derived
        ],
        refused=refused_ones,
        derived_twice=list(learning.derived_twice(derived)),
        note=note.sentence,
        files_read=note.files_read,
        readers=list(note.readers),
    )


@router.post("/migration/audience", response_model=PastedAudiencesView, responses=COMMON_RESPONSES)
async def map_audience(
    request: Request, body: PastedAudienceAsked, asked: Asked
) -> PastedAudiencesView:
    """Map each agent's availability over there onto who may see it here, from the mapping given,
    and name the agents whose availability the mapping does not cover. Never a default."""
    await _begin(request, asked)
    audiences: list[PastedAudienceView] = []
    unmapped: list[PastedRefusedView] = []
    try:
        for one in body.agents:
            foreign = rebuild.ForeignAgent(
                name=one.name, availability=one.availability, tools=tuple(one.tools)
            )
            try:
                made = rebuild.audience_for(
                    foreign,
                    mapping=body.mapping,
                    owner_id=body.owner_id,
                    department=body.department,
                )
            except rebuild.RebuildError as refused:
                unmapped.append(PastedRefusedView(subject=one.name, because=str(refused)))
                continue
            audiences.append(PastedAudienceView(name=one.name, level=made.level.value))
    except (MigrationError, ValueError) as refused:
        raise _refused_because(str(refused)) from None
    return PastedAudiencesView(audiences=audiences, unmapped=unmapped)
