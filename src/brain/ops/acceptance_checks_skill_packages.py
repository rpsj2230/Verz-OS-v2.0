"""The install acceptance checks for skill packages: rehearsed examples, exports, and scripts.

Three leaves that were built and wired with nothing on an install showing that they still hold.
**M12.3.4**: a skill carries example tasks, and a version is not approved until a rehearsal of
that exact version has passed every one. **M12.3.1**: an approved version is exported as a package
that says what it holds, and a package changed afterwards is refused. **M12.4.11**: a script's
sha256 is inside the approval's digest, so a script changed after approval is refused before it
runs. Each check is the route the Skills screen calls, asked as the reader the page serves, with
the refusal asked beside every answer.

**The routes are called, not the functions under them**, for the reason
`brain.ops.acceptance_skill_console` gives for the same screen: a screen is done when its answer
is right on the install's own schema and grants, and the page tests in CI prove only what a page
draws from an answer. A package is added through `POST /skills`, a version rehearsed through
`POST /skills/{digest}/rehearsals`, approved through `POST /skills/{digest}/review` and exported
through `POST /skills/{digest}/export`. Each check reads back what a route wrote from the
library's own store, so an answer saying "approved" over a row that is not approved fails.

**The rehearsal is a rehearsal of reach, and the check says no more than that.** What a rehearsal
runs today is the run's reach, with no model
(`brain.tools.skill_examples.A_REACH_REHEARSAL_JUDGES_WHAT_IS_REACHABLE_AND_NOT_THE_ANSWER`), so
the check rehearses an example expecting a real tool through an agent that cannot reach it, which
fails, and through one that can, which passes. It does not claim a skill's answers were judged.

**What a version with no examples does is not asked here.** That rule is needs-rupash item 161,
which the owner has not answered, and a check pinning today's answer would turn red on the day he
chooses the other. Every skill these checks approve is approved either after a passing rehearsal
of its examples, or through the library's store where the check is about something else, as
`brain.ops.acceptance_checks_skills` approves.

**A script is refused at the runner, and the runner is constructed here as the sandbox tool would
construct it.** `brain.ops.sandbox_client.SandboxRunner` recomputes every script's sha256 from the
bytes it is handed and compares them with the hashes the approval covers, before it sends the
sandbox anything. Nothing in the application constructs one yet, so no run exists on an install to
be refused; the check builds the runner over a stand-in transport that records what it is sent and
asks it twice: the approved bytes are sent, and bytes changed since are refused with nothing sent.
The table is asked as well: the application role may add a script's bytes and never update them,
and a row whose hash is not its bytes' is refused by the database. See
`THE_RUNNER_IS_ASKED_OVER_A_TRANSPORT_THAT_RECORDS_WHAT_IT_IS_SENT`.

**An install with no sandbox is asked in what it can answer.** The add route refuses a package
declaring scripts where `INSTALL_SERVICES` does not name the sandbox, so there the check asks the
route and requires that refusal, and writes the skill through the library's own store, the route's
second half, to ask the runner and the table about it. Where the sandbox is switched on the route
itself adds it. Rejected: ending the script check as not run on an install with no sandbox, which
would throw away what it proves about the digest, the runner and the table without one. What
needs the sandbox itself is the sandbox's own second check of the bytes, which
`brain.ops.acceptance_checks_services` asks of a switched-on sandbox.

**Not proved here: the landing on a second install.** One install holds a version once, keyed by
its digest, so a package cannot land undecided on the install it came from, and the owner decided
that a second install is a scratch one built in CI (needs-rupash 103). The export check proves the
package, its manifest and the refusal of a changed one here, and that the package reads back as an
undecided submission; the landing is `tests/unit/test_skill_export.py`'s.

Every name the checks write is the run's: skills are `acceptance_<run>_...`, written by reserved
principals of acceptance_a, and all of it rolls back with the check.

Task ids: M12.3.4, M12.3.1, M12.4.11
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from collections.abc import Mapping
from functools import partial
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from brain.core.scope import Scope
from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from fastapi import FastAPI

    from brain.console.skill_library import LibrarySkill

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 454

# ------------------------------------------------------------------ written-down reasons
#: Why the runner is asked over a transport of the check's own.
THE_RUNNER_IS_ASKED_OVER_A_TRANSPORT_THAT_RECORDS_WHAT_IT_IS_SENT: Final = (
    "The runner is asked over a stand-in transport that answers a run and keeps every request it "
    "is sent. That is the question: whether anything is sent at all once a script's bytes no "
    "longer match the approval. A real sandbox could only say it refused, and a refusal from "
    "beyond the runner would hide a runner that sent the changed bytes."
)

# ------------------------------------------------------------------------ the figures
#: The script the script check's skill carries, and the same script with a line added.
SCRIPT_PATH: Final = "scripts/check.py"
SCRIPT: Final = b"print('the acceptance check ran')\n"
CHANGED_SCRIPT: Final = b"print('the acceptance check ran')\nprint('and then something else')\n"

#: The SQLSTATE PostgreSQL answers a statement the role holds no grant for with.
INSUFFICIENT_PRIVILEGE: Final = "42501"


# ------------------------------------------------------------------------ the helpers
def _zip_of(members: Mapping[str, bytes]) -> bytes:
    """A zip as an administrator would upload it: the members in the order given."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)
    return out.getvalue()


def _members_of(archive: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        return {info.filename: opened.read(info) for info in opened.infolist()}


def _package_asked(file_name: str, content: bytes) -> Any:
    """The body the add route takes for a file: its name and its bytes in base64."""
    from brain.skill_routes import SkillPackageAsked

    return SkillPackageAsked(
        file_name=file_name,
        content=base64.b64encode(content).decode("ascii"),
        encoding="base64",
    )


async def _added(h: Harness, app: FastAPI, admin: str, file_name: str, content: bytes) -> str:
    """The add route's answer for this package, as the digest it was stored under."""
    from brain.ops.acceptance_skill_console import _asking, _body, _request
    from brain.skill_routes import add_skill

    answered = await add_skill(
        _request(app), _package_asked(file_name, content), await _asking(h, admin)
    )
    if answered.status_code != 201:
        raise CheckFailedError("the add route did not answer a well-formed package with a 201")
    return str(_body(answered).get("digest", ""))


async def _refused(call: Awaitable[Any]) -> str | None:
    """What a route refused with, in its own words, or None when it answered."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent as refused:
        return str(refused.public_message)
    return None


async def _waiting(h: Harness, digest: str) -> LibrarySkill:
    """The stored version, which must still be waiting for its review."""
    from brain.ops.skill_store import StoredSkills

    kept = await StoredSkills(h.sessions).skill(digest)
    if kept is None:
        raise CheckFailedError("a version the library accepted was not in the library")
    if kept.imported.reviewer or kept.imported.is_executable():
        raise CheckFailedError("a version was decided, though nobody's review had decided it")
    return kept


async def _approved_in_store(h: Harness, admin: str, digest: str) -> LibrarySkill:
    """The version approved through the library's store, as `acceptance_checks_skills` does it,
    for the checks whose subject is not the review route's rehearsal rule."""
    from brain.console.skill_library import decided
    from brain.ops.skill_store import StoredSkills

    store = StoredSkills(h.sessions)
    one = await store.skill(digest)
    if one is None:
        raise CheckFailedError("a version the library accepted was not in the library")
    reach = await h.reach(admin)
    if not await store.decide(
        decided(one, reviewer=admin, approve=True, at=h.now),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an approval of a skill named for this run was refused")
    kept = await store.skill(digest)
    if kept is None or not kept.imported.is_executable():
        raise CheckFailedError("an approved skill did not read back as approved and unchanged")
    return kept


def _held(files: Mapping[str, bytes], _digest: str) -> Mapping[str, bytes]:
    """What the runner's reading of a stored skill's scripts answers: `files`, for any digest."""
    return files


async def _counted(h: Harness, table: Any, *where: Any) -> int:
    async with h.sessions() as session:
        counted = select(func.count()).select_from(table).where(*where)
        return int((await session.execute(counted)).scalar_one())


async def _statement_refusal(h: Harness, actor: str, statement: Any) -> tuple[str, str] | None:
    """The SQLSTATE and constraint the database refuses this statement with, as the application
    role acting as `actor`, or None when it was accepted.

    In a session of its own whose work is rolled back either way, so the check's transaction
    carries on, as `brain.ops.acceptance_checks_tools` does. The actor is set first, so a refusal
    is the rule being asked about and not the row-level policy refusing a row in nobody's name.
    """
    from brain.ops.automation_owner_store import PRINCIPAL_SETTING

    async with h.sessions() as session:
        try:
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


# ------------------------------------------------ 1. examples rehearsed first (M12.3.4)
@check(
    leaves=("M12.3.4",),
    sentence=(
        "A skill carrying two example tasks is refused approval before it is rehearsed and after "
        "a rehearsal through an agent that cannot reach what an example expects, and is approved "
        "once a rehearsal through an agent that can passes every example; the ledger records both "
        "rehearsals, and a second version with different examples is not approved on the first's."
    ),
)
async def a_version_with_examples_is_approved_only_once_rehearsed(h: Harness) -> None:
    import structlog

    from brain.ops.acceptance_checks_skills import (
        BODY,
        _administrator,
        _changes,
        _named,
        _skill_md,
    )
    from brain.ops.acceptance_skill_console import _asking, _body, _console, _request
    from brain.ops.acceptance_workspace import LOCAL_READ, LOCAL_TOOL, installed_agent
    from brain.ops.skill_store import StoredSkills
    from brain.skill_routes import RehearseAsked, ReviewAsked, rehearse_skill, review_skill

    await h.found_departments()
    admin = await _administrator(h, "rehearsals")
    await h.grant(admin, LOCAL_READ, Scope.unrestricted())
    reaching = await installed_agent(
        h, admin, capabilities=(LOCAL_READ,), allowed_tools=(LOCAL_TOOL,), suffix="_reaches"
    )
    bare = await installed_agent(h, admin, suffix="_bare")
    app = _console(h)
    name = _named(h, "rehearsed")

    def package(version: str, last: str) -> bytes:
        return _skill_md(
            name,
            version=version,
            extra=(f"tools: [{LOCAL_TOOL}]",),
            body=(
                *BODY,
                "",
                "## Examples",
                f"- Look up the price list => {LOCAL_TOOL}",
                f"- {last} => none",
            ),
        )

    async def approve(digest: str) -> str | None:
        asked = await _asking(h, admin)
        return await _refused(
            review_skill(_request(app), digest, ReviewAsked(decision="approve"), asked)
        )

    async def rehearse(digest: str, agent: str) -> bool:
        answered = await rehearse_skill(
            _request(app), digest, RehearseAsked(agent_id=agent), await _asking(h, admin)
        )
        if answered.status_code != 201:
            raise CheckFailedError("the rehearse route did not record a rehearsal it was asked for")
        return bool(_body(answered).get("passed"))

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        first = await _added(h, app, admin, "SKILL.md", package("1.0.0", "Say hello"))
        await _waiting(h, first)
        if await approve(first) is None:
            raise CheckFailedError("a version with example tasks was approved before a rehearsal")
        await _waiting(h, first)

        if await rehearse(first, bare):
            raise CheckFailedError("a rehearsal passed through an agent that cannot reach the tool")
        if await approve(first) is None:
            raise CheckFailedError("a version was approved on a rehearsal in which one failed")
        await _waiting(h, first)

        if not await rehearse(first, reaching):
            raise CheckFailedError("a rehearsal through an agent that reaches the tool failed")
        if await approve(first) is not None:
            raise CheckFailedError("a version whose rehearsal passed every example was refused")
        kept = await StoredSkills(h.sessions).skill(first)
        if kept is None or kept.imported.reviewer != admin or not kept.imported.is_executable():
            raise CheckFailedError("an approval the route answered was not stored as an approval")

        second = await _added(h, app, admin, "SKILL.md", package("1.1.0", "Say goodbye"))
        if second == first:
            raise CheckFailedError("a version with other examples kept the first version's digest")
        if await approve(second) is None:
            raise CheckFailedError("a version was approved on the rehearsal of another version")
        await _waiting(h, second)

    said = [
        (actor, d.get("change"), d.get("passed")) for actor, d in await _changes(h, f"skill:{name}")
    ]
    if said != [
        (admin, "imported", None),
        (admin, "rehearsed", False),
        (admin, "rehearsed", True),
        (admin, "self_approved", None),
        (admin, "imported", None),
    ]:
        raise CheckFailedError("the ledger did not record each rehearsal, then the one approval")


# ------------------------------------------------------------- 2. exported (M12.3.1)
@check(
    leaves=("M12.3.1",),
    sentence=(
        "An approved version is exported as a zip whose manifest names its version and digest, "
        "which reads back as that version waiting undecided, and the export is a row and a ledger "
        "entry; a version nobody approved is not exported; a package whose text, manifest or "
        "script was changed after export is refused. The landing on a second install is proved "
        "in CI."
    ),
)
async def an_approved_skill_is_exported_and_a_changed_package_is_refused(h: Harness) -> None:
    import structlog

    from brain.console.skill_library import (
        EXPORT_MANIFEST,
        EXPORT_SCHEMA,
        SkillLibraryError,
        added,
        decided,
        exported,
        read_package,
    )
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _changes,
        _named,
        _skill_md,
    )
    from brain.ops.acceptance_skill_console import _asking, _console, _request
    from brain.skill_routes import export_skill
    from brain.tables.skill import SkillExportRow

    await h.found_departments()
    admin = await _administrator(h, "export")
    app = _console(h)
    name = _named(h, "exported")
    first = await _added(h, app, admin, "SKILL.md", _skill_md(name))
    second = await _added(h, app, admin, "SKILL.md", _skill_md(name, version="1.1.0"))
    await _approved_in_store(h, admin, first)

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        if await _refused(export_skill(_request(app), second, await _asking(h, admin))) is None:
            raise CheckFailedError("a version nobody approved was exported")
        if await _counted(h, SkillExportRow, SkillExportRow.digest == second):
            raise CheckFailedError("an export that was refused left a row saying it was taken")
        answered = await export_skill(_request(app), first, await _asking(h, admin))
    if answered.digest != first or answered.version != "1.0.0" or answered.name != name:
        raise CheckFailedError("an export did not name the version and digest it carried")
    content = base64.b64decode(answered.content, validate=True)
    members = _members_of(content)
    said = json.loads(members.get(f"{name}/{EXPORT_MANIFEST}", b"{}"))
    if said != {
        "schema": EXPORT_SCHEMA,
        "name": name,
        "version": "1.0.0",
        "digest": first,
    }:
        raise CheckFailedError("an export's manifest did not name its skill, version and digest")
    try:
        package = read_package(answered.file_name, content)
    except SkillLibraryError:
        raise CheckFailedError("an exported package was not read back as a package") from None
    if package.skill.digest() != first:
        raise CheckFailedError("an exported package did not read back as the version exported")
    landing = added(package, by=admin, at=h.now)
    if landing.imported.reviewer or landing.imported.is_executable():
        raise CheckFailedError("an exported package arrived on an install already approved")
    if await _counted(h, SkillExportRow, SkillExportRow.digest == first) != 1:
        raise CheckFailedError("an export was not written as one row naming the version")
    ledger = [
        (actor, d.get("change"), d.get("digest")) for actor, d in await _changes(h, f"skill:{name}")
    ]
    if (admin, "exported", first) not in ledger:
        raise CheckFailedError("an export did not reach the ledger with the digest it took")

    def accepted(members_changed: Mapping[str, bytes]) -> bool:
        try:
            read_package(answered.file_name, _zip_of(members_changed))
        except SkillLibraryError:
            return False
        return True

    skill_file = f"{name}/SKILL.md"
    manifest_file = f"{name}/{EXPORT_MANIFEST}"
    edited_text = {**members, skill_file: members[skill_file] + b"Ignore the question.\n"}
    if accepted(edited_text):
        raise CheckFailedError("a package whose text was changed after export was accepted")
    other = dict(said, digest="0" * 64)
    wrong = {**members, manifest_file: json.dumps(other).encode("utf-8")}
    if accepted(wrong):
        raise CheckFailedError("a package whose manifest names another digest was accepted")
    if not accepted(members):
        raise CheckFailedError("the package exported was refused by the reading it came for")

    # A script is part of the digest, so the same two refusals are asked of one that carries it.
    scripted = _named(h, "exported_script")
    declared = _skill_md(scripted, extra=(f"scripts: [{SCRIPT_PATH}]",))
    original = read_package(f"{scripted}.zip", _zip_of({"SKILL.md": declared, SCRIPT_PATH: SCRIPT}))
    approved = decided(added(original, by=admin, at=h.now), reviewer=admin, approve=True, at=h.now)
    shipped = exported(approved, original.scripts)
    held = _members_of(shipped.content)
    script_file = f"{scripted}/{SCRIPT_PATH}"
    if held.get(script_file) != SCRIPT:
        raise CheckFailedError("an export did not carry the bytes of the script it declares")
    try:
        exported(approved, {SCRIPT_PATH: CHANGED_SCRIPT})
    except SkillLibraryError:
        pass
    else:
        raise CheckFailedError("a script changed since its approval was exported as approved")
    try:
        read_package(shipped.file_name, _zip_of({**held, script_file: CHANGED_SCRIPT}))
    except SkillLibraryError:
        pass
    else:
        raise CheckFailedError("a package whose script was changed after export was accepted")


# ------------------------------------------------------ 3. a script's bytes (M12.4.11)
@check(
    leaves=("M12.4.11",),
    sentence=(
        "A skill carrying a script is approved with the script's sha256 in its digest; the runner "
        "sends the approved bytes and, given bytes changed since, refuses before sending the "
        "sandbox anything; the same script with a line added is a different version waiting for "
        "review; and the application cannot update a stored script or store bytes under a hash "
        "that is not theirs."
    ),
)
async def a_script_changed_after_approval_is_refused_before_it_runs(h: Harness) -> None:
    import httpx
    import structlog

    from brain.console.skill_library import THIS_INSTALL_RUNS_NO_SANDBOX, read_package
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _named,
        _skill_md,
        _store,
    )
    from brain.ops.acceptance_skill_console import _asking, _console, _request
    from brain.ops.overlays import OverlayError, components_switched_on, switched_on_here
    from brain.ops.sandbox import AnswerStatus, RunAnswer, sandbox_address
    from brain.ops.sandbox_client import SandboxRunner
    from brain.ops.skill_store import StoredSkills
    from brain.skill_routes import add_skill
    from brain.tables.skill import SkillScriptRow
    from brain.tools.run_skill import (
        SCRIPT_CHANGED_SINCE_APPROVAL,
        ScriptLeash,
        ScriptRequest,
        SkillScriptError,
        plan_run,
    )
    from brain.tools.skills import script_sha256_of

    name = _named(h, "scripted")
    declared = _skill_md(name, extra=(f"scripts: [{SCRIPT_PATH}]",))
    package_bytes = _zip_of({"SKILL.md": declared, SCRIPT_PATH: SCRIPT})
    package = read_package(f"{name}.zip", package_bytes)
    recorded = dict(package.skill.script_sha256)
    if recorded != {SCRIPT_PATH: script_sha256_of(SCRIPT)}:
        raise CheckFailedError("a skill's digest did not carry the sha256 of its script's bytes")
    changed = read_package(
        f"{name}.zip", _zip_of({"SKILL.md": declared, SCRIPT_PATH: CHANGED_SCRIPT})
    )
    if changed.skill.digest() == package.skill.digest():
        raise CheckFailedError("changing a script's bytes did not change the skill's digest")

    await h.found_departments()
    admin = await _administrator(h, "scripts")
    reach = await h.reach(admin)
    app = _console(h)
    try:
        address = sandbox_address(
            h.settings.sandbox_url, components_switched_on(switched_on_here())
        )
    except OverlayError:
        address = None
    app.state.sandbox_address = address
    store = StoredSkills(h.sessions)

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        if address is not None:
            digest = await _added(h, app, admin, f"{name}.zip", package_bytes)
        else:
            refused = await _refused(
                add_skill(
                    _request(app),
                    _package_asked(f"{name}.zip", package_bytes),
                    await _asking(h, admin),
                )
            )
            if refused is None or THIS_INSTALL_RUNS_NO_SANDBOX not in refused:
                raise CheckFailedError("a script was accepted where the install runs no sandbox")
            from brain.console.skill_library import added

            await _store(h, added(package, by=admin, at=h.now), reach)
            digest = package.skill.digest()
    waiting = await _waiting(h, digest)
    if dict(waiting.imported.skill.script_sha256) != recorded:
        raise CheckFailedError("a stored skill did not keep the sha256 its digest covers")
    kept = await _approved_in_store(h, admin, digest)
    stored = await store.script_bytes(digest)
    if stored != {SCRIPT_PATH: SCRIPT}:
        raise CheckFailedError("the library did not keep the script's bytes beside the skill")

    sent: list[httpx.Request] = []

    def sandbox(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json=RunAnswer(
                run_id=str(body["run_id"]),
                status=AnswerStatus.COMPLETED,
                exit_code=0,
                output="ran",
                elapsed_seconds=0.01,
            ).to_json(),
        )

    client = httpx.Client(transport=httpx.MockTransport(sandbox))
    spec = plan_run(
        kept.imported.skill,
        ScriptRequest(skill=name, script=SCRIPT_PATH),
        leash=ScriptLeash(),
        environment={},
        reach_hash=reach.ent_hash(),
    )
    try:
        SandboxRunner("http://sandbox.invalid:3100", client, partial(_held, stored)).run(spec)
        if len(sent) != 1 or json.loads(sent[0].content)["digest"] != digest:
            raise CheckFailedError("the approved script was not sent as the version approved")
        for altered in (
            {SCRIPT_PATH: CHANGED_SCRIPT},
            {SCRIPT_PATH: SCRIPT, "scripts/other.py": SCRIPT},
            {},
        ):
            sent.clear()
            reading = SandboxRunner("http://sandbox.invalid:3100", client, partial(_held, altered))
            try:
                reading.run(spec)
            except SkillScriptError as refused:
                if str(refused) != SCRIPT_CHANGED_SINCE_APPROVAL:
                    raise CheckFailedError(
                        "a changed script was refused without saying why"
                    ) from None
            else:
                raise CheckFailedError("a script changed after approval was run")
            if sent:
                raise CheckFailedError("a script changed after approval reached the sandbox")
    finally:
        client.close()

    rewrite = (
        update(SkillScriptRow)
        .where(SkillScriptRow.digest == digest)
        .values(content=CHANGED_SCRIPT, sha256=script_sha256_of(CHANGED_SCRIPT))
    )
    rewritten = await _statement_refusal(h, admin, rewrite)
    if rewritten is None or rewritten[0] != INSUFFICIENT_PRIVILEGE:
        raise CheckFailedError("the application could change an approved script's bytes in place")
    lying = insert(SkillScriptRow).values(
        digest=digest,
        path="scripts/other.py",
        content=CHANGED_SCRIPT,
        sha256=script_sha256_of(SCRIPT),
    )
    lied = await _statement_refusal(h, admin, lying)
    if lied is None or not lied[1].endswith("sha256_is_the_contents"):
        raise CheckFailedError("the table kept a script whose sha256 is not of its bytes")
    if await store.script_bytes(digest) != {SCRIPT_PATH: SCRIPT}:
        raise CheckFailedError("the approved script's bytes changed in the library")

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        if address is not None:
            moved = _zip_of({"SKILL.md": declared, SCRIPT_PATH: CHANGED_SCRIPT})
            again = await _added(h, app, admin, f"{name}.zip", moved)
        else:
            from brain.console.skill_library import added

            await _store(h, added(changed, by=admin, at=h.now), reach)
            again = changed.skill.digest()
    waiting_again = await _waiting(h, again)
    if again == digest or waiting_again.imported.is_executable():
        raise CheckFailedError("a package with a changed script arrived already approved")
