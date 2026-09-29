"""The install acceptance checks for skill packages: scripts, example tasks, and exports.

Each check drives the functions `brain.skill_routes` calls, in the order it calls them, against the
install's own database, as `brain.ops.acceptance_checks_skills` does for the library it extends:
`brain.console.skill_library` decides, `brain.ops.skill_store` writes through the harness's
sessions, and every row, policy, check constraint, trigger and ledger entry is the install's and
all of it is rolled back. The three checks split where the leaves split.

**A script is proved refused at the one door to a run, because there is no run.** Nothing on an
install executes a skill's script yet (`brain.tools.run_skill` has no runner, and says why), so
the check asks `plan_run`, the planning step every run has to pass and the one that holds the
bytes to the approved sha256, and asks the table whether the application could change an approved
script's bytes in place. See `A_SCRIPT_IS_REFUSED_WHERE_EVERY_RUN_WOULD_START`.

**A rehearsal is a person's verdict, and the check records it as one.** No model carries out a
skill on an install yet, so the rehearsal the check records is a reserved principal's verdict per
example, exactly as the Skills screen records a person's; see
`brain.console.skill_library.A_REHEARSAL_IS_A_PERSON_S_VERDICT_UNTIL_A_MODEL_ANSWERS`.

**The landing on a second install is not proved here.** One install cannot hold a version twice,
because the digest is the key, and the owner decided that a second install is a scratch one built
in CI rather than a second company server (needs-rupash 103). So the export check proves the
package, its manifest and the refusal of a changed one on this install, and
`tests/unit/test_skill_packages.py` builds a second scratch database at head and lands the package
there undecided. See `A_SECOND_INSTALL_IS_A_SCRATCH_DATABASE_BUILT_IN_CI`.

Every name the checks write is the run's: skills are `acceptance_<run>_...`, placed in no
department because a skill belongs to none, and written by reserved principals of acceptance_a.

Task ids: M12.4.11, M12.3.4, M12.3.1
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text, update
from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_skills import (
    _administrator,
    _changes,
    _named,
    _skill_md,
    _store,
)
from brain.ops.acceptance_run import Harness
from brain.ops.automation_owner_store import PRINCIPAL_SETTING

if TYPE_CHECKING:
    from brain.console.skill_library import LibrarySkill, Package

# ------------------------------------------------------------------ written-down reasons
#: Why the script check asks the planning step and the table rather than a run.
A_SCRIPT_IS_REFUSED_WHERE_EVERY_RUN_WOULD_START: Final = (
    "No install runs a skill's script yet, because no sandbox is built. What stands between a "
    "changed script and a run is brain.tools.run_skill.plan_run, which every run has to pass and "
    "which holds the bytes to the sha256 the approval covers, and the table, which the "
    "application may add to and never update. The check asks both: the approved bytes are "
    "planned, a changed byte is refused, and an update of the stored bytes is refused."
)

#: Why the landing on another install is proved by a test rather than by this check.
A_SECOND_INSTALL_IS_A_SCRATCH_DATABASE_BUILT_IN_CI: Final = (
    "An install holds a version once, keyed by its digest, so an exported package cannot land "
    "undecided on the install it came from. The owner decided a second install is a scratch one "
    "built in CI (needs-rupash 103), and tests/unit/test_skill_packages.py builds that database "
    "at head and lands the package there; this check proves everything up to the landing."
)

# ------------------------------------------------------------------------ the figures
#: The script every check's skill carries, one line of code that prints a sentence.
SCRIPT_PATH: Final = "scripts/check.py"
SCRIPT: Final = b"print('the acceptance check ran')\n"

#: The two example tasks a rehearsed skill carries, each with the behaviour expected of it.
EXAMPLES: Final = (
    {"task": "An acceptance check asks for its skill", "expected": "Answers from the check"},
    {"task": "An acceptance check asks twice", "expected": "Answers the same way twice"},
)


# ------------------------------------------------------------------------ the helpers
def _package_zip(name: str, *, script: bytes | None = SCRIPT, examples: bool = False) -> bytes:
    """A zip an administrator would upload: the `SKILL.md`, its script and its examples."""
    extra = (f"scripts: [{SCRIPT_PATH}]",) if script is not None else ()
    members: dict[str, bytes] = {"SKILL.md": _skill_md(name, extra=extra)}
    if script is not None:
        members[SCRIPT_PATH] = script
    if examples:
        members["examples.json"] = json.dumps(list(EXAMPLES)).encode("utf-8")
    return _zipped(members)


def _zipped(members: Mapping[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)
    return out.getvalue()


def _members(archive: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        return {info.filename: opened.read(info) for info in opened.infolist()}


def _read(file_name: str, content: bytes) -> Package | None:
    """What `read_package`, which the add route calls first, makes of this package, or None."""
    from brain.console.skill_library import SkillLibraryError, read_package

    try:
        return read_package(file_name, content)
    except SkillLibraryError:
        return None


async def _approved(h: Harness, admin: str, one: LibrarySkill) -> LibrarySkill:
    """The review route's approval of `one`, by the person who added it, read back as stored."""
    from brain.console.skill_library import SkillLibraryError, decided
    from brain.ops.skill_store import StoredSkills

    store = StoredSkills(h.sessions)
    reach = await h.reach(admin)
    newest = (await store.rehearsals([one.digest])).get(one.digest)
    try:
        own = decided(one, reviewer=admin, approve=True, at=h.now, rehearsal=newest)
    except SkillLibraryError:
        raise CheckFailedError("a well-formed skill could not be approved") from None
    if not await store.decide(own, ent_hash=reach.ent_hash(), trace_id=h.trace_id):
        raise CheckFailedError("an approval of a skill named for this run was refused")
    kept = await store.skill(one.digest)
    if kept is None or not kept.imported.is_executable():
        raise CheckFailedError("an approved skill did not read back as executable")
    return kept


#: The SQLSTATE PostgreSQL answers a statement the role holds no grant for with.
INSUFFICIENT_PRIVILEGE: Final = "42501"


async def _refusal(h: Harness, actor: str, statement: Any) -> tuple[str, str] | None:
    """The SQLSTATE and constraint the database refuses this statement with, as the application
    role acting as `actor`, or None when it was accepted.

    In a session of its own, whose savepoint is rolled back either way so the check's transaction
    carries on, as `brain.ops.acceptance_checks_tools` does. The actor is set first, so a refusal
    is the rule being asked about and not the row-level policy refusing a row in nobody's name.
    """
    async with h.sessions() as session:
        try:
            # The session's principal, which `0164`'s insert policies read, as the store sets it.
            await session.execute(
                text("SELECT set_config(:name, :value, true)").bindparams(
                    name=PRINCIPAL_SETTING, value=actor
                )
            )
            await session.execute(statement)
        except DBAPIError as refused:
            await session.rollback()
            diagnosis = getattr(refused.orig, "diag", None)
            return (
                str(getattr(refused.orig, "sqlstate", "") or ""),
                str(getattr(diagnosis, "constraint_name", "") or ""),
            )
        await session.rollback()
    return None


# ------------------------------------------------------ 1. a script's bytes (M12.4.11)
@check(
    leaves=("M12.4.11",),
    sentence=(
        "A skill uploaded with a script is approved and its digest covers the script's sha256; "
        "the stored bytes are planned to run and the same script with one line changed is refused "
        "before a run exists; the application cannot update the stored bytes, and the changed "
        "package is a new version waiting for review."
    ),
)
async def a_script_changed_after_approval_is_refused_before_it_runs(h: Harness) -> None:
    from brain.console.skill_library import added
    from brain.ops.skill_store import StoredSkills
    from brain.tables.skill import SkillScriptRow
    from brain.tools.run_skill import ScriptLeash, ScriptRequest, SkillScriptError, plan_run
    from brain.tools.skills import script_sha256

    name = _named(h, "scripted")
    package = _read(f"{name}.zip", _package_zip(name))
    if package is None:
        raise CheckFailedError("a skill carrying the script it declares was refused")
    recorded = package.skill.recorded(SCRIPT_PATH)
    if recorded is None or recorded.sha256 != script_sha256(SCRIPT):
        raise CheckFailedError("the skill did not record the sha256 of its script's bytes")
    changed = SCRIPT + b"print('and then something else')\n"
    moved = _read(f"{name}.zip", _package_zip(name, script=changed))
    if moved is None or moved.skill.digest() == package.skill.digest():
        raise CheckFailedError("changing a script's bytes did not change the skill's digest")

    await h.found_departments()
    admin = await _administrator(h, "scripts")
    reach = await h.reach(admin)
    one = added(package, by=admin, at=h.now)
    await _store(h, one, reach)
    store = StoredSkills(h.sessions)
    kept = await _approved(h, admin, one)
    stored = await store.scripts(kept.digest)
    if stored != {SCRIPT_PATH: SCRIPT}:
        raise CheckFailedError("the library did not keep the script's bytes beside the skill")

    request = ScriptRequest(skill=name, script=SCRIPT_PATH)
    planned = plan_run(
        kept.imported.skill,
        request,
        content=stored[SCRIPT_PATH],
        leash=ScriptLeash(),
        environment={},
        reach_hash=reach.ent_hash(),
    )
    if planned.content != SCRIPT or planned.digest != kept.digest:
        raise CheckFailedError("the approved script was not planned with the bytes approved")
    try:
        plan_run(
            kept.imported.skill,
            request,
            content=changed,
            leash=ScriptLeash(),
            environment={},
            reach_hash=reach.ent_hash(),
        )
    except SkillScriptError:
        pass
    else:
        raise CheckFailedError("a script whose bytes changed after approval was planned to run")

    rewrite = (
        update(SkillScriptRow)
        .where(SkillScriptRow.skill_digest == kept.digest)
        .values(content=changed, content_sha256=script_sha256(changed))
    )
    rewritten = await _refusal(h, admin, rewrite)
    if rewritten is None or rewritten[0] != INSUFFICIENT_PRIVILEGE:
        raise CheckFailedError("the application could change an approved script's bytes in place")
    lying = insert(SkillScriptRow).values(
        skill_digest=kept.digest,
        path="scripts/other.py",
        content=changed,
        content_sha256=script_sha256(SCRIPT),
        submitted_by=admin,
    )
    lied = await _refusal(h, admin, lying)
    if lied is None or not lied[1].endswith("content_sha256_is_of_its_content"):
        raise CheckFailedError("the table kept a script whose sha256 is not of its bytes")
    if await store.scripts(kept.digest) != {SCRIPT_PATH: SCRIPT}:
        raise CheckFailedError("the approved script's bytes changed in the library")

    again = added(moved, by=admin, at=h.now)
    await _store(h, again, reach)
    waiting = await store.skill(again.digest)
    if waiting is None or waiting.imported.is_executable() or waiting.imported.reviewer:
        raise CheckFailedError("a package with a changed script arrived without a review")


# --------------------------------------------------- 2. examples rehearsed (M12.3.4)
@check(
    leaves=("M12.3.4",),
    sentence=(
        "A skill uploaded with two example tasks is refused approval unrehearsed and after a "
        "rehearsal in which one misbehaved, then approved once every example behaved; the ledger "
        "records both rehearsals, and an edit carries the examples and waits for its own."
    ),
)
async def a_version_with_examples_is_approved_only_once_rehearsed(h: Harness) -> None:
    from brain.audit.record import RehearsalOutcome
    from brain.console.skill_library import (
        SkillLibraryError,
        added,
        decided,
        edited,
        may_rehearse,
        rehearsal,
    )
    from brain.ops.skill_store import StoredSkills

    name = _named(h, "rehearsed")
    package = _read(f"{name}.zip", _package_zip(name, script=None, examples=True))
    if package is None:
        raise CheckFailedError("a skill carrying example tasks was refused")
    await h.found_departments()
    admin = await _administrator(h, "rehearsals")
    reach = await h.reach(admin)
    if not may_rehearse(reach, h.now):
        raise CheckFailedError("a person who may review skills may not record a rehearsal")
    one = added(package, by=admin, at=h.now)
    await _store(h, one, reach)
    store = StoredSkills(h.sessions)
    kept = await store.skill(one.digest)
    if kept is None or [
        {"task": item.task, "expected": item.expected} for item in kept.imported.skill.examples
    ] != list(EXAMPLES):
        raise CheckFailedError("the example tasks did not read back in the order they were added")

    def refused(candidate: LibrarySkill, newest: Any) -> bool:
        try:
            decided(candidate, reviewer=admin, approve=True, at=h.now, rehearsal=newest)
        except SkillLibraryError:
            return True
        return False

    if not refused(kept, None):
        raise CheckFailedError("a version with example tasks was approved before it was rehearsed")
    for verdicts in ((True, False), (True, True)):
        done = rehearsal(kept, verdicts, by=admin, at=h.now)
        await store.rehearse(done, ent_hash=reach.ent_hash(), trace_id=h.trace_id)
        newest = (await store.rehearsals([kept.digest])).get(kept.digest)
        if newest is None or newest.behaved != verdicts:
            raise CheckFailedError("a rehearsal did not read back as the newest one recorded")
        if verdicts == (True, False) and not refused(kept, newest):
            raise CheckFailedError("a version was approved on a rehearsal where one misbehaved")
    approved = await _approved(h, admin, kept)

    said = [
        (actor, d.get("change"), d.get("outcome"))
        for actor, d in await _changes(h, f"skill:{name}")
    ]
    if said != [
        (admin, "imported", None),
        (admin, "rehearsed", RehearsalOutcome.FAILED.value),
        (admin, "rehearsed", RehearsalOutcome.PASSED.value),
        (admin, "self_approved", None),
    ]:
        raise CheckFailedError("the ledger did not record each rehearsal and then the approval")

    text = _skill_md(name, version="1.1.0", body=("Read the question twice.",)).decode("utf-8")
    try:
        edit = edited(approved, text, by=admin, at=h.now, library=await store.library())
    except SkillLibraryError:
        raise CheckFailedError("an edit of a version with example tasks was refused") from None
    if edit.imported.skill.examples != approved.imported.skill.examples:
        raise CheckFailedError("an edit did not carry the example tasks of the version it edited")
    await _store(h, edit, reach)
    newest = (await store.rehearsals([edit.digest])).get(edit.digest)
    if not refused(edit, newest):
        raise CheckFailedError("an edit was approved on the rehearsal of the version before it")


# ------------------------------------------------------------- 3. exported (M12.3.1)
@check(
    leaves=("M12.3.1",),
    sentence=(
        "An approved skill with a script and examples is exported as a zip whose manifest names "
        "its version and digest and which reads back as that version, undecided; an unapproved "
        "version is not exported, and a package with a changed script or manifest is refused. The "
        "landing on a second install is proved in CI."
    ),
)
async def an_approved_skill_is_exported_and_a_changed_package_is_refused(h: Harness) -> None:
    from brain.console.skill_library import (
        MANIFEST_FILE,
        PACKAGE_FORMAT,
        SkillLibraryError,
        added,
        exported,
        may_export,
        rehearsal,
    )
    from brain.ops.skill_store import StoredSkills
    from brain.tools.skills import SkillState

    name = _named(h, "exported")
    package = _read(f"{name}.zip", _package_zip(name, examples=True))
    if package is None:
        raise CheckFailedError("a skill carrying a script and example tasks was refused")
    await h.found_departments()
    admin = await _administrator(h, "exports")
    reach = await h.reach(admin)
    if not may_export(reach, h.now):
        raise CheckFailedError(
            "a person holding the skill authority over everything may not export"
        )
    one = added(package, by=admin, at=h.now)
    await _store(h, one, reach)
    store = StoredSkills(h.sessions)
    waiting = await store.skill(one.digest)
    if waiting is None:
        raise CheckFailedError("a skill added for this run was not in the library")
    try:
        exported(waiting, await store.scripts(waiting.digest))
    except SkillLibraryError:
        pass
    else:
        raise CheckFailedError("a version nobody had approved was exported")
    done = rehearsal(waiting, (True, True), by=admin, at=h.now)
    await store.rehearse(done, ent_hash=reach.ent_hash(), trace_id=h.trace_id)
    approved = await _approved(h, admin, waiting)

    try:
        out = exported(approved, await store.scripts(approved.digest))
    except SkillLibraryError:
        raise CheckFailedError("an approved version could not be exported") from None
    members = _members(out.content)
    manifest = json.loads(members.get(MANIFEST_FILE, b"{}"))
    if manifest != {
        "format": PACKAGE_FORMAT,
        "name": name,
        "version": approved.imported.skill.version,
        "digest": approved.digest,
    }:
        raise CheckFailedError("an exported package's manifest did not name its version and digest")
    if members.get(SCRIPT_PATH) != SCRIPT:
        raise CheckFailedError("an exported package did not carry the approved script's bytes")
    back = _read(out.file_name, out.content)
    if back is None or back.skill.digest() != approved.digest or back.exported_as != out.digest:
        raise CheckFailedError("an exported package did not read back as the version exported")
    landing = added(back, by=admin, at=h.now)
    if landing.imported.state is not SkillState.IMPORTED or landing.imported.is_executable():
        raise CheckFailedError("an exported package arrived already approved")

    for member, content in (
        (SCRIPT_PATH, SCRIPT + b"print('changed after the export')\n"),
        (MANIFEST_FILE, json.dumps({**manifest, "version": "9.9.9"}).encode("utf-8")),
    ):
        tampered = _zipped({**members, member: content})
        if _read(out.file_name, tampered) is not None:
            raise CheckFailedError("a package changed after it was exported was accepted")
