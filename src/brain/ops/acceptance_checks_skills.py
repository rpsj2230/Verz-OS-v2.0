"""The install acceptance checks for the skill library: arriving, waiting, being edited and filed.

Each check drives the functions `brain.skill_routes` calls, in the order it calls them, against the
install's own database: `brain.console.skill_library` decides and `brain.ops.skill_store` writes,
through the harness's sessions, so every row, policy, trigger and ledger entry is the install's and
all of it is rolled back. Nothing signs in and nothing writes the vault. The four checks split
where the leaves split: a package pasted or uploaded, a package fetched from GitHub, an edit and
its review against an agent's pin, and categories with the chips drawn from them.

**The skill authorities are held over everything, by reserved principals and nobody else.** A
skill belongs to no department, so the product asks for `admin:skill` and `admin:skill_review`
over every row, and a grant scoped to acceptance_a would prove only that the Skills screen refuses
it. See `THE_SKILL_AUTHORITY_IS_HELD_OVER_EVERYTHING_BY_A_RESERVED_PRINCIPAL_ONLY`. Rejected: a
department-scoped administrator, which exercises none of the writes the leaves name.

**The import from GitHub fetches before it writes anything.** A check holds the install's write
locks from its first audited write to its rollback, and a fetch can take the transport's whole
timeout, so both fetches finish before the first row is written. A fetch that never reached GitHub
is not a verdict on the product. See `AN_IMPORT_THAT_CANNOT_REACH_GITHUB_IS_NOT_RUN`.

**What it fetches is the install's to name, in `INSTALL_ACCEPTANCE_SKILL_SOURCE`, and unnamed it
fetches nothing.** A repository, a commit and a folder, then the address of a second `SKILL.md`,
public and at a full commit so the bytes cannot move under the check. Rejected: a repository
compiled in here, which is one address every install would reach whether its owner chose it or
not, and the reason the client-independence sweep refuses a host in the source. Rejected too: a
repository the check owns, which would put this product's own account into every install's
acceptance run. See `AN_IMPORT_NOBODY_NAMED_IS_NOT_RUN`.

**Every name the checks write is the run's.** Skills are `acceptance_<run>_...`, the agent is
`acceptance_<run>`, placed in acceptance_a, and categories carry a word nothing else holds. The two
skills fetched from GitHub keep their public names, because renaming them would change the bytes
the import pins; if the install's library already holds either, the check says not run rather than
asking an import the library would refuse for a reason that is not the product's.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import secrets
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.models.routing import DEFAULT_TIER, Tier
from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.connectors.registry import ConnectorRegistry
    from brain.console.skill_library import Assignment, LibrarySkill
    from brain.core.entitlement import EntitlementSet
    from brain.tools.fetch import FetchedBytes, Fetcher, Resolver
    from brain.tools.registry import ToolRegistry

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 40

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a reserved principal holds the skill authorities unrestricted.
THE_SKILL_AUTHORITY_IS_HELD_OVER_EVERYTHING_BY_A_RESERVED_PRINCIPAL_ONLY: Final = (
    "A skill belongs to no department, so adding, reviewing and filing one asks for the skill "
    "authorities over everything. The checks grant them unrestricted to reserved principals of "
    "acceptance_a, uncommitted and lapsing within the hour, and every skill, agent and category "
    "they write is named for the run, so no real screen or question can meet one."
)

#: Why an import that never reached GitHub is not run rather than failed.
AN_IMPORT_THAT_CANNOT_REACH_GITHUB_IS_NOT_RUN: Final = (
    "Importing from a repository or an address needs this server to reach GitHub. A name that "
    "does not resolve, or a host that refuses or does not answer, means the product was never "
    "asked, so the check is not run. When GitHub answered and the product refused what it sent, "
    "the check failed."
)

#: Why the import check fetches only what the install names.
AN_IMPORT_NOBODY_NAMED_IS_NOT_RUN: Final = (
    "Which public skills this server fetches from GitHub is the install's to decide, so the "
    "repository, commit, folder and address are read from INSTALL_ACCEPTANCE_SKILL_SOURCE, and "
    "while it is unset nothing is fetched and the check is not run. A value that does not name a "
    "repository at a full commit and an https address is not run either: it is the install's "
    "setting that is wrong, and the product was never asked."
)

# ------------------------------------------------------------------------ the figures
#: The installation setting naming what the import check fetches. See `brain.install`.
SKILL_SOURCE_SETTING: Final = "INSTALL_ACCEPTANCE_SKILL_SOURCE"

#: An address on no host a skill is fetched from. `.invalid` is reserved and resolves nowhere.
OFF_THE_LIST: Final = "https://skills.example.invalid/SKILL.md"

#: The instructions every skill the checks write carries, one line each.
BODY: Final = ("Read the question.", "Answer it from the acceptance check.")


# ------------------------------------------------------------------------ the helpers
@dataclass(frozen=True)
class PublicSkills:
    """What `INSTALL_ACCEPTANCE_SKILL_SOURCE` names: a repository's folder at a commit, and an
    address. Only its shape is read here; whether the commit is a full one and the address is on
    an allowed host is the product's own rule, asked by the check."""

    repository: str
    commit: str
    folder: str
    address: str


def public_skills(value: str) -> PublicSkills | None:
    """The four parts of `owner/repository@commit:folder,address`, or None for anything else.

    `unset`, the declared default, is None like any other value without the four parts; the check
    tells the two apart by the value, so an unnamed source and a mistyped one say different things.
    """
    pinned, comma, address = value.strip().partition(",")
    repository, at, located = pinned.strip().partition("@")
    commit, colon, folder = located.partition(":")
    parts = (repository.strip(), commit.strip(), folder.strip(), address.strip())
    if not (comma and at and colon) or not all(parts) or "," in address:
        return None
    return PublicSkills(*parts)


def _fetchable(address: str) -> bool:
    """Whether the import's own rules would fetch this address: its shape, then its host."""
    from brain.console.skill_library import url_source_problem
    from brain.tools.fetch import SKILL_SOURCE_HOSTS, UnsafeAddressError, assert_on_the_list

    if url_source_problem(address) is not None:
        return False
    try:
        assert_on_the_list(address, SKILL_SOURCE_HOSTS)
    except UnsafeAddressError:
        return False
    return True


def _named(h: Harness, what: str) -> str:
    """A skill name nothing on the install holds: the run's, and what the check calls it."""
    return f"acceptance_{h.run}_{what}"


def _skill_md(
    name: str,
    *,
    description: str = "Use when an acceptance check asks for a skill it wrote",
    version: str = "1.0.0",
    body: Sequence[str] = BODY,
    extra: Sequence[str] = (),
) -> bytes:
    """A `SKILL.md` naming no tools, with any `extra` frontmatter lines."""
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"version: {version}",
        *extra,
        "---",
        *body,
        "",
    ]
    return chr(10).join(lines).encode("utf-8")


def _zip(member: str, content: bytes) -> bytes:
    """A zip holding one member, as an administrator's upload would."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(member, content)
    return out.getvalue()


def _refuses(file_name: str, content: bytes) -> bool:
    """Whether `read_package`, which the add route calls first, refuses this package."""
    from brain.console.skill_library import SkillLibraryError, read_package

    try:
        read_package(file_name, content)
    except SkillLibraryError:
        return True
    return False


def _everywhere(*capabilities: str) -> tuple[tuple[str, Scope], ...]:
    return tuple((one, Scope.unrestricted()) for one in capabilities)


def _screen() -> tuple[str, str]:
    """The Skills screen's read and the configuration plane, which every reader here needs."""
    from brain.console.reads import Plane, plane_capability
    from brain.console.screens import screen

    return screen("skills").read.requires.value, plane_capability(Plane.CONFIGURATION).value


async def _administrator(h: Harness, role: str, *, reviews: bool = True) -> str:
    """A reserved principal of acceptance_a holding the skill authority, and the review one if
    `reviews`. See `THE_SKILL_AUTHORITY_IS_HELD_OVER_EVERYTHING_BY_A_RESERVED_PRINCIPAL_ONLY`."""
    from brain.console.skill_library import REVIEW_AUTHORITY, SKILL_AUTHORITY

    held = [*_screen(), SKILL_AUTHORITY.value]
    if reviews:
        held.append(REVIEW_AUTHORITY.value)
    made = h.principal(A, role)
    await h.person(made, department=A, grants=_everywhere(*held))
    return made


async def _store(
    h: Harness, one: LibrarySkill, reach: EntitlementSet, *, fetched: bool = False
) -> None:
    """The add route's refusals and write: another spelling, then the insert on the digest."""
    from brain.console.skill_library import another_spelling
    from brain.ops.skill_store import StoredSkills

    store = StoredSkills(h.sessions)
    spelt = another_spelling(one.imported.skill, await store.library())
    written = spelt is None and await store.add(one, ent_hash=reach.ent_hash(), trace_id=h.trace_id)
    if written:
        return
    if fetched:
        raise CheckNotRunError(
            "this install's library already holds a public skill the check imports, so its "
            "import cannot be asked again"
        )
    raise CheckFailedError("the library refused a skill named for this run")


async def _changes(
    h: Harness, subject: str, action: str | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """The actor and details of every ledger entry about `subject` in the check's transaction.

    `action` narrows to one ledger action. An agent's subject is shared: since `0137` inserting
    the agent writes a `created` entry too, so a check about what was attached to it asks for the
    `compose_change` entries and no others.
    """
    statement = "SELECT actor_id, details FROM obs.audit_entry WHERE subject = :subject"
    if action is not None:
        statement += " AND action = :action"
    bound = text(f"{statement} ORDER BY seq").bindparams(subject=subject)
    if action is not None:
        bound = bound.bindparams(action=action)
    rows = (await h.execute(bound)).all()
    return [
        (str(actor), details if isinstance(details, dict) else json.loads(details))
        for actor, details in rows
    ]


# ------------------------------------------------------ 1. a paste or an upload (M12.2.1)
@check(
    leaves=("M12.2.1", "M12.2.4", "M12.2.5", "M12.4.12"),
    sentence=(
        "A SKILL.md pasted and one uploaded in a zip land in the library and the review queue "
        "undecided, their instructions withheld from every agent and no pin possible; a SKILL.md "
        "whose description does not open by saying when to use it, one declaring a reach, one with "
        "no frontmatter and a zip reaching outside its folder are refused."
    ),
)
async def a_pasted_or_uploaded_skill_waits_undecided_and_unread(h: Harness) -> None:
    from brain.console.skill_library import (
        SkillLibraryError,
        added,
        may_add,
        queue_entries,
        read_package,
    )
    from brain.ops.skill_store import StoredSkills
    from brain.tools.skills import (
        SkillError,
        SkillState,
        SourceKind,
        body_of,
        offered_cards,
        pin_skill,
    )

    pasted_name, uploaded_name = _named(h, "pasted"), _named(h, "uploaded")
    if not _refuses("SKILL.md", _skill_md(pasted_name, description="Checks a pasted skill")):
        raise CheckFailedError(
            "a SKILL.md whose description does not say when to use the skill was accepted"
        )
    if not _refuses("SKILL.md", _skill_md(pasted_name, extra=("capabilities: [admin:skill]",))):
        raise CheckFailedError("a SKILL.md declaring a reach of its own was accepted")
    if not _refuses("SKILL.md", chr(10).join(BODY).encode("utf-8")):
        raise CheckFailedError("a SKILL.md with no frontmatter was accepted")
    if not _refuses(f"{uploaded_name}.zip", _zip("../SKILL.md", _skill_md(uploaded_name))):
        raise CheckFailedError("a zip whose SKILL.md sits outside its own folder was accepted")
    try:
        packages = (
            read_package("SKILL.md", _skill_md(pasted_name)),
            read_package(
                f"{uploaded_name}.zip", _zip(f"{uploaded_name}/SKILL.md", _skill_md(uploaded_name))
            ),
        )
    except SkillLibraryError:
        raise CheckFailedError(
            "a well-formed SKILL.md, pasted or uploaded in a zip, was refused"
        ) from None

    await h.found_departments()
    admin = await _administrator(h, "skills")
    reach = await h.reach(admin)
    if not may_add(reach, h.now):
        raise CheckFailedError("a person holding the skill authority over everything may not add")
    ours = [added(package, by=admin, at=h.now) for package in packages]
    for one in ours:
        await _store(h, one, reach)
    library = await StoredSkills(h.sessions).library()
    stored = {one.digest: one for one in library}
    for one, location in zip(ours, ("SKILL.md", f"{uploaded_name}.zip"), strict=True):
        kept = stored.get(one.digest)
        if kept is None or kept.imported != one.imported or kept.submitted_by != admin:
            raise CheckFailedError("a skill added by paste or upload did not read back as added")
        source = kept.imported.source
        if source.kind is not SourceKind.UPLOAD or source.location != location:
            raise CheckFailedError("a pasted or uploaded skill did not keep where it came from")
        if kept.imported.state is not SkillState.IMPORTED or kept.imported.is_executable():
            raise CheckFailedError("a skill nobody has reviewed was executable")
        if offered_cards([kept.imported]):
            raise CheckFailedError("an undecided skill was offered to an agent as a card")
        for withheld in (body_of, partial(pin_skill, A)):
            try:
                withheld(kept.imported)
            except SkillError:
                continue
            raise CheckFailedError("an undecided skill's body was read or it was pinned")
        entries = await _changes(h, f"skill:{kept.name}")
        if [(actor, d.get("change"), d.get("source")) for actor, d in entries] != [
            (admin, "imported", "upload")
        ]:
            raise CheckFailedError("adding a skill did not reach the ledger once, as an import")
    waiting = {placed.record.skill.skill.digest() for placed in queue_entries(library, h.now)}
    if not {one.digest for one in ours} <= waiting:
        raise CheckFailedError("a skill added undecided was not waiting in the review queue")


# ------------------------------------------------ 2. from a repository or an address
@dataclass
class _Watched:
    """The install's fetcher and resolver, noting whether anything was asked and GitHub reached.

    Only the transport's own failures mark it unreached: a name that resolves to nothing, and a
    hop the fetcher could not complete. A refusal by `brain.tools.fetch`'s rules is the product's
    answer and is left to fail the check. See `AN_IMPORT_THAT_CANNOT_REACH_GITHUB_IS_NOT_RUN`.
    """

    fetcher: Fetcher
    resolver: Resolver
    asked: int = 0
    unreached: bool = False

    def resolve(self, host: str) -> Sequence[str]:
        self.asked += 1
        answers = self.resolver.resolve(host)
        if not answers:
            self.unreached = True
        return answers

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        from brain.tools.skills import SkillError

        self.asked += 1
        try:
            return self.fetcher.get_once(url, address=address, max_bytes=max_bytes)
        except SkillError:
            self.unreached = True
            raise


def _transport() -> tuple[Fetcher, Resolver]:
    """The transport `brain.skill_routes` hands the fetch on every install, and nothing else."""
    from brain.ops.skill_fetch import HttpsFetcher, SystemResolver

    return HttpsFetcher(), SystemResolver()


@check(
    leaves=("M12.2.2", "M12.2.3"),
    sentence=(
        "A public skill fetched by the install's own transport from a GitHub repository at a full "
        "commit, and another from a raw address, both land undecided, keeping the commit and "
        "folder and the digest of the bytes; a branch instead of a commit, a plain http address "
        "and an address on no allowed host are refused before anything connects."
    ),
)
async def a_skill_is_imported_from_a_github_commit_and_from_an_address(h: Harness) -> None:
    from brain.console.skill_library import (
        SkillLibraryError,
        added,
        github_source,
        read_github,
        read_url,
        url_source_problem,
    )
    from brain.install import BY_NAME, value_of
    from brain.ops.skill_store import StoredSkills
    from brain.tools.fetch import UnsafeAddressError, fetch_skill_source, fetch_skill_url
    from brain.tools.skills import SkillError, SkillState, SourceKind

    named = value_of(SKILL_SOURCE_SETTING)
    public = public_skills(named)
    if public is None and named.strip() in ("", BY_NAME[SKILL_SOURCE_SETTING].default):
        raise CheckNotRunError(
            "this install names no public skill to import, so no import from GitHub was asked"
        )
    if public is None or not _fetchable(public.address):
        raise CheckNotRunError(
            "the public skill this install names is not a repository folder at a commit and an "
            "https address on an allowed host"
        )
    try:
        source = github_source(public.repository, public.commit, public.folder)
    except SkillLibraryError:
        raise CheckNotRunError(
            "the public skill this install names is not a repository folder at a full commit"
        ) from None

    watched = _Watched(*_transport())
    try:
        github_source(public.repository, "main", public.folder)
    except SkillLibraryError:
        pass
    else:
        raise CheckFailedError("a repository import naming a branch rather than a commit was taken")
    if url_source_problem(public.address.replace("https://", "http://", 1)) is None:
        raise CheckFailedError("an import from a plain http address was taken")
    try:
        fetch_skill_url(OFF_THE_LIST, fetcher=watched, resolver=watched)
    except UnsafeAddressError:
        pass
    else:
        raise CheckFailedError("an address on no allowed host was fetched")
    if watched.asked:
        raise CheckFailedError("an address on no allowed host was looked up or connected to")

    # Both fetches before any write: see the module docstring.
    try:
        tarball = await asyncio.to_thread(
            fetch_skill_source, source, fetcher=watched, resolver=watched
        )
        answered = await asyncio.to_thread(
            fetch_skill_url, public.address, fetcher=watched, resolver=watched
        )
    except SkillError:
        if watched.unreached:
            raise CheckNotRunError(
                "GitHub did not answer this server, so no import from it could be asked"
            ) from None
        raise CheckFailedError("GitHub answered and the import's own rules refused it") from None
    try:
        from_commit = read_github(source, tarball)
        from_address = read_url(public.address, answered)
    except SkillLibraryError:
        raise CheckFailedError("a public SKILL.md fetched from GitHub could not be read") from None

    await h.found_departments()
    admin = await _administrator(h, "importer", reviews=False)
    reach = await h.reach(admin)
    ours = [added(package, by=admin, at=h.now) for package in (from_commit, from_address)]
    for one in ours:
        await _store(h, one, reach, fetched=True)
    store = StoredSkills(h.sessions)
    commit_kept, address_kept = [await store.skill(one.digest) for one in ours]
    if commit_kept is None or address_kept is None:
        raise CheckFailedError("a skill imported from GitHub was not in the library")
    for kept in (commit_kept, address_kept):
        if kept.imported.state is not SkillState.IMPORTED or kept.imported.is_executable():
            raise CheckFailedError("a skill imported from GitHub was executable before review")
    pinned = commit_kept.imported.source
    if (pinned.kind, pinned.location, pinned.commit, pinned.path) != (
        SourceKind.GITHUB,
        public.repository,
        public.commit,
        public.folder,
    ):
        raise CheckFailedError("a repository import did not keep its commit and folder")
    addressed = address_kept.imported.source
    if (addressed.kind, addressed.location, addressed.content_digest) != (
        SourceKind.URL,
        public.address,
        hashlib.sha256(answered).hexdigest(),
    ):
        raise CheckFailedError("an address import did not keep the digest of what it answered")
    for kept, kind in ((commit_kept, "github"), (address_kept, "url")):
        said = [
            (actor, d.get("change"), d.get("source"))
            for actor, d in await _changes(h, f"skill:{kept.name}")
            if d.get("digest") == kept.digest
        ]
        if said != [(admin, "imported", kind)]:
            raise CheckFailedError("an import from GitHub did not reach the ledger with its source")


# --------------------------------------------- 3. an edit, its review and an agent's pin
async def _an_agent(
    h: Harness,
    owner: str,
    *,
    tier: Tier = DEFAULT_TIER,
    capabilities: Sequence[str] = (),
    named: str = "",
    scope: Scope | None = None,
    connectors: Sequence[str] = (),
    settled: tuple[ConnectorRegistry, ToolRegistry] | None = None,
) -> str:
    """An agent of acceptance_a installed from a template signed with a key made for this check.

    The three rows `brain.agents.install_store.finish` writes, from its own row builders where it
    has them. The instance row is written field by field because that module builds it from a
    wizard's `Installation`, which a check with no connectors and no tools does not have.
    `tier` and `capabilities` are the template's, for a check asking through the agent: its model
    level, and the ceiling its runs are narrowed to, over acceptance_a, or over `scope` when one
    is given. `named` follows the run's id, for a check holding two agents at once.

    `connectors` are the sources the template names, and `settled` the install's connector and
    tool registries: with them the agent is finished by `brain.agents.install.settle`, as an
    install is, so an agent naming a source the install does not serve is refused here rather
    than stored disabled and asked as if it could answer.
    """
    from brain.agents.install import settle
    from brain.agents.install_store import agent_values, version_values
    from brain.agents.model import AgentAudience
    from brain.agents.template import (
        ManifestAuthority,
        ManifestIdentity,
        TemplateManifest,
        install,
        materialise,
        publish,
    )
    from brain.core.entitlement import Capability
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    agent_id, key = f"acceptance_{h.run}{named}", secrets.token_hex(32)
    signed = publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id=agent_id,
                version=1,
                published_by=owner,
                display_name="Acceptance check agent",
            ),
            persona="Answers an install acceptance check and nobody else.",
            tier=tier,
            authority=ManifestAuthority(
                scope=Scope.department(A) if scope is None else scope,
                capabilities=tuple(Capability(value=one) for one in capabilities),
            ),
            connectors=tuple(connectors),
        ),
        key=key,
        signed_by=owner,
        at=h.now,
    )
    instance = install(signed, key=key, instance_id=agent_id, created_by=owner, at=h.now)
    audience = AgentAudience(level=Visibility.DEPARTMENT, owner_id=owner, department=A)
    if settled is None:
        effective = materialise(signed, instance, audience=audience)
        record = effective.record
    else:
        connected, tools = settled
        finished = settle(
            signed,
            instance,
            audience=audience,
            unanswered=(),
            registry=connected,
            tools=tools,
            at=h.now,
        )
        if not finished.completeness.is_ready:
            raise CheckFailedError("an agent naming a source this install serves was not ready")
        effective, record = finished.effective, finished.record
    await h.execute(
        *h.attributed(owner),
        insert(TemplateVersionRow).values(**version_values(signed)),
        insert(TemplateInstanceRow).values(
            id=agent_id,
            template_id=instance.template_id,
            template_version=instance.template_version,
            content_digest=instance.content_digest,
            overlay=dict(instance.overlay),
            field_owners={
                path: owned.model_dump(mode="json")
                for path, owned in instance.overlay_owners.items()
            },
            effective_document=dict(effective.document),
            effective_hash=effective.config_hash,
            created_by=owner,
        ),
        insert(AgentRow).values(**agent_values(record)),
    )
    return agent_id


async def _assign(h: Harness, digest: str, agent_id: str, reach: EntitlementSet) -> Assignment:
    """The assign route's sequence: the agent and its install read, the skill looked up by its
    digest, decided, then written."""
    from brain.audit.ledger import AuditChain
    from brain.audit.record import AuditRecorder
    from brain.console.skill_library import assignment, may_assign
    from brain.ops.skill_store import StoredSkills
    from brain.prompt_routes import agent_scope_row
    from brain.skill_routes import StoredAgentInstalls

    found = await StoredAgentInstalls(h.sessions).agent(agent_id)
    if found is None or found.install is None or found.effective_hash is None:
        raise CheckFailedError("the check's agent did not read back with an install")
    if not may_assign(reach, agent_scope_row(found.record), h.now):
        raise CheckFailedError("a skills administrator over everything may not assign to an agent")
    now = h.now
    signed, instance = found.install
    store = StoredSkills(h.sessions)
    one = await store.skill(digest)
    if one is None:
        raise CheckFailedError("a skill the check added was not in the library to assign")
    made = assignment(
        one,
        record=found.record,
        signed=signed,
        instance=instance,
        library=await store.library(),
        by=reach,
        recorder=AuditRecorder(
            AuditChain(),
            actor_id=reach.principal_id,
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
            clock=lambda: now,
        ),
        now=now,
    )
    if not await store.assign(
        made, expected_hash=found.effective_hash, ent_hash=reach.ent_hash(), trace_id=h.trace_id
    ):
        raise CheckFailedError("an assignment was refused as if the agent had changed since")
    return made


async def _pins(h: Harness, agent_id: str) -> dict[str, str]:
    """The skills the Skills screen reads this agent as pinned to, by name."""
    from brain.skill_routes import StoredAgentInstalls, installs_of, pins_of

    found = await StoredAgentInstalls(h.sessions).agent(agent_id)
    if found is None:
        raise CheckFailedError("the check's agent did not read back")
    async with h.sessions() as session:
        pairs = (await session.execute(installs_of([agent_id]))).all()
    return {
        pin.skill_name: pin.digest
        for instance_row, version_row in pairs
        for pin in pins_of(instance_row, version_row, found.record)
    }


@check(
    leaves=("M12.2.6", "M12.3.2", "M12.4.6"),
    sentence=(
        "An administrator approves a skill they imported and the ledger says self_approved; an "
        "edit by somebody who may not review is a new undecided version beside the old one, which "
        "stays readable; the review shows the changed description and body lines; an agent in "
        "acceptance_a keeps the old version until it is reassigned."
    ),
)
async def an_edit_is_a_new_version_and_moves_no_agent_until_reassigned(h: Harness) -> None:
    from brain.agents.template import TemplateError
    from brain.audit.ledger import AuditAction
    from brain.console.agent_tabs import AgentTabError
    from brain.console.skill_library import (
        SkillLibraryError,
        SkillReach,
        added,
        compared_with,
        decided,
        edited,
        may_add,
        may_review,
        queue_entries,
        read_package,
    )
    from brain.ops.skill_store import StoredSkills
    from brain.skill_routes import library_view
    from brain.tools.skills import SkillState, body_of

    await h.found_departments()
    admin = await _administrator(h, "skills")
    editor = await _administrator(h, "editor", reviews=False)
    admin_reach, editor_reach = await h.reach(admin), await h.reach(editor)
    if not may_add(editor_reach, h.now) or may_review(editor_reach, h.now):
        raise CheckFailedError("somebody who may add and not review skills was not held to that")
    if not may_review(admin_reach, h.now):
        raise CheckFailedError("a person holding the review authority over everything may not")
    store = StoredSkills(h.sessions)
    name = _named(h, "edited")
    first = added(read_package("SKILL.md", _skill_md(name)), by=admin, at=h.now)
    await _store(h, first, admin_reach)
    own = decided(first, reviewer=admin, approve=True, at=h.now)
    if not own.self_decided or not await store.decide(
        own, ent_hash=admin_reach.ent_hash(), trace_id=h.trace_id
    ):
        raise CheckFailedError("an administrator could not approve a skill they imported")

    agent_id = await _an_agent(h, admin)
    await _assign(h, first.digest, agent_id, admin_reach)
    if await _pins(h, agent_id) != {name: first.digest}:
        raise CheckFailedError("assigning an approved skill did not pin the agent to it")

    approved_first = await store.skill(first.digest)
    if approved_first is None or not approved_first.imported.is_executable():
        raise CheckFailedError("an approved skill did not read back as executable")
    changed_line = "Answer it from the edited acceptance check."
    try:
        second = edited(
            approved_first,
            _skill_md(
                name,
                description="Use when an acceptance check asks for the edited version",
                version="1.1.0",
                body=(BODY[0], changed_line),
            ).decode("utf-8"),
            by=editor,
            at=h.now,
            library=await store.library(),
        )
    except SkillLibraryError:
        raise CheckFailedError(
            "an edit that changes the words and the version was refused"
        ) from None
    await _store(h, second, editor_reach)
    library = await store.library()
    stored = {one.digest: one for one in library}
    old, new = stored.get(first.digest), stored.get(second.digest)
    if old is None or new is None or new.edited_from != first.digest:
        raise CheckFailedError("an edit was not saved as a new version beside the one it edited")
    if new.imported.state is not SkillState.IMPORTED or new.imported.is_executable():
        raise CheckFailedError("an edit was executable before anybody reviewed it")
    if not old.imported.is_executable() or body_of(old.imported) != first.imported.skill.body:
        raise CheckFailedError("the version an edit came from did not stay readable as approved")

    against = compared_with(new, library)
    if against is None or against.digest != first.digest:
        raise CheckFailedError("the review compared an edit with something other than its original")
    view = library_view(
        new,
        SkillReach(tools=(), capabilities=(), unknown=()),
        discloses_body=True,
        reviews=True,
        assigns=False,
        edits=True,
        against=against,
    )
    diff = view.diff
    fields = {} if diff is None else {one.field: (one.before, one.after) for one in diff.fields}
    lines = set() if diff is None else {(one.change, one.text) for one in diff.body}
    if fields.get("description") != (
        first.imported.skill.description,
        new.imported.skill.description,
    ):
        raise CheckFailedError("the review did not show the description before and after")
    if not {("removed", BODY[1]), ("added", changed_line), ("kept", BODY[0])} <= lines:
        raise CheckFailedError("the review did not show which body lines the edit changed")
    unread = library_view(
        new,
        SkillReach(tools=(), capabilities=(), unknown=()),
        discloses_body=False,
        reviews=False,
        assigns=False,
        against=against,
    )
    if unread.diff is not None or unread.body is not None:
        raise CheckFailedError("a reader who may not add or review was shown a skill's words")
    queued = [
        placed.record
        for placed in queue_entries(library, h.now)
        if placed.record.skill.skill.digest() == second.digest
    ]
    if len(queued) != 1 or not {"body", "description", "version"} <= set(queued[0].changed):
        raise CheckFailedError("the review queue did not list the edit with the fields it changed")

    if await _pins(h, agent_id) != {name: first.digest}:
        raise CheckFailedError("saving an edit moved an agent off the version it was pinned to")
    try:
        await _assign(h, second.digest, agent_id, admin_reach)
    except (SkillLibraryError, AgentTabError, TemplateError):
        pass
    else:
        raise CheckFailedError("an edit nobody had reviewed was assigned to an agent")
    reviewed = decided(new, reviewer=admin, approve=True, at=h.now)
    if reviewed.self_decided or not await store.decide(
        reviewed, ent_hash=admin_reach.ent_hash(), trace_id=h.trace_id
    ):
        raise CheckFailedError("an edit by somebody else could not be approved by a reviewer")
    if await _pins(h, agent_id) != {name: first.digest}:
        raise CheckFailedError("approving an edit moved an agent off the version it was pinned to")
    moved = await _assign(h, second.digest, agent_id, admin_reach)
    if moved.replaces_digest != first.digest or await _pins(h, agent_id) != {name: second.digest}:
        raise CheckFailedError("reassigning the approved edit did not move the agent onto it")

    said = [(actor, d.get("change")) for actor, d in await _changes(h, f"skill:{name}")]
    if said != [
        (admin, "imported"),
        (admin, "self_approved"),
        (editor, "edited"),
        (admin, "approved"),
    ]:
        raise CheckFailedError("the ledger did not record the self-approval, the edit and review")
    attached = await _changes(h, f"agent:{agent_id}", action=AuditAction.COMPOSE_CHANGE.value)
    directions = [d.get("direction") for _, d in attached]
    if directions != ["attached", "detached", "attached"]:
        raise CheckFailedError("the ledger did not record the agent's skill attached and replaced")


# ------------------------------------------------------------------ 4. categories (M12.4.13)
@check(
    leaves=("M12.4.13",),
    sentence=(
        "An administrator files two skills named for the run under categories kept in "
        "agent.skill_category, one of them twice so the newest applies, and the filter chips are "
        "drawn from the skills each reader was shown: both for the administrator, only the shown "
        "skill's for a narrower page, none for a reader who may not open the library."
    ),
)
async def categories_are_kept_and_offered_from_what_a_reader_was_shown(h: Harness) -> None:
    from brain.console.skill_library import (
        added,
        categories_from,
        chips,
        may_add,
        may_read_library,
        read_package,
    )
    from brain.ops.skill_store import StoredSkills

    await h.found_departments()
    admin = await _administrator(h, "skills")
    reader = h.principal(B, "reader")
    await h.person(
        reader, department=B, grants=tuple((one, Scope.department(B)) for one in _screen())
    )
    admin_reach, reader_reach = await h.reach(admin), await h.reach(reader)
    if may_read_library(reader_reach, h.now) or may_add(reader_reach, h.now):
        raise CheckFailedError(
            "a reader granted the Skills screen in one department reached the library"
        )
    store = StoredSkills(h.sessions)
    shown_skill, other_skill = _named(h, "filed"), _named(h, "hidden")
    for name in (shown_skill, other_skill):
        await _store(
            h, added(read_package("SKILL.md", _skill_md(name)), by=admin, at=h.now), admin_reach
        )

    word = h.word().lower()
    filed_as = categories_from([f"  Acceptance  {word.upper()} "])
    if filed_as != (f"acceptance-{word}",):
        raise CheckFailedError("a category was not folded to the one form every chip uses")
    interim, hidden = (f"interim-{word}",), (f"hidden-{word}",)
    for name, categories in (
        (shown_skill, interim),
        (shown_skill, filed_as),
        (other_skill, hidden),
    ):
        await store.categorise(
            name, categories, by=admin, ent_hash=admin_reach.ent_hash(), trace_id=h.trace_id
        )
    filed = await store.categories([shown_skill, other_skill])
    if dict(filed) != {shown_skill: filed_as, other_skill: hidden}:
        raise CheckFailedError("the categories read back were not the newest set on each skill")
    kept = (
        await h.execute(
            text("SELECT count(*) FROM agent.skill_category WHERE skill_name = :name").bindparams(
                name=shown_skill
            )
        )
    ).scalar_one()
    if kept != 2:
        raise CheckFailedError("agent.skill_category did not keep one row per change of categories")
    said = [(actor, d.get("change")) for actor, d in await _changes(h, f"skill:{shown_skill}")]
    if said != [(admin, "imported"), (admin, "categorised"), (admin, "categorised")]:
        raise CheckFailedError("setting a skill's categories did not reach the ledger each time")

    ours = {*filed_as, *hidden, *interim}
    for reach, expected in ((admin_reach, {*filed_as, *hidden}), (reader_reach, set())):
        library = await store.library() if may_read_library(reach, h.now) else ()
        # The route's `shown` is the library read plus the names the reader's agents pin, and no
        # agent pins a skill named for this run.
        shown = {one.name for one in library}
        offered = set(chips(await store.categories(sorted(shown)), shown)) & ours
        if offered != expected:
            raise CheckFailedError("the chips offered were not those of the skills the reader saw")
    if set(chips(filed, {shown_skill})) != set(filed_as):
        raise CheckFailedError("a category only a skill not on the page carries was offered")
