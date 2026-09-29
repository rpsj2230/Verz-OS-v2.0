"""Skill packages: a script's bytes in the digest, example tasks rehearsed before approval, and an
approved skill exported to land undecided on another install.

Six parts. The digest and `verified_script`, pure. `plan_run` and the execution tool refusing a
changed script before a spec exists. Packages read, refused, edited, rehearsed and exported through
`brain.console.skill_library`, with real archives built in memory. `0164` rendered and held to the
models and the recorder, with no server. The store and the tables against a scratch PostgreSQL at
head, as the application role, including **a second scratch install the exported package lands on
undecided**, which is how needs-rupash 103 has M12.3.1 proved: a scratch install, never the
company's. And the routes, through the real application with `tests/unit/test_skill_routes.py`'s
stub store. The database half **skips without a server**.

**Every refusal has a sibling proving the permitted case**, which is CLAUDE.md's rule about a guard
tested only by its refusals.

Task ids: M12.4.11, M12.3.4, M12.3.1
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.schema import CreateTable

from brain.agents.template import GOLDEN_CHARS
from brain.audit.ledger import DIGEST, IDENTIFIER, AuditAction, AuditChain
from brain.audit.record import AuditRecorder, RehearsalOutcome, SkillChange
from brain.console import skill_library as library_module
from brain.console.skill_library import (
    A_PACKAGE_KEEPS_ONLY_WHAT_ITS_DIGEST_COVERS,
    A_VERSION_WITH_EXAMPLES_IS_APPROVED_ONLY_AFTER_THEY_ARE_REHEARSED,
    AN_EXPORTED_PACKAGE_LANDS_UNREVIEWED_AND_ONLY_IF_ITS_BYTES_MATCH_ITS_DIGEST,
    EXAMPLES_FILE,
    MANIFEST_FILE,
    MAX_PACKAGE_BYTES,
    ONLY_AN_APPROVED_VERSION_IS_EXPORTED,
    PACKAGE_FORMAT,
    LibrarySkill,
    Rehearsal,
    SkillLibraryError,
    added,
    awaits_rehearsal,
    decided,
    edited,
    exported,
    read_package,
    rehearsal,
)
from brain.db import metadata
from brain.ops.skill_store import StoredSkills
from brain.session import make_session_factory
from brain.tables import skill as table_module
from brain.tools import skills as skills_module
from brain.tools.review import content_diff
from brain.tools.run_skill import (
    SKILL_NOT_AVAILABLE,
    ScriptLeash,
    ScriptRequest,
    SkillScriptError,
    plan_run,
)
from brain.tools.skills import (
    A_SCRIPT_CHANGED_AFTER_APPROVAL_IS_REFUSED_BEFORE_IT_RUNS,
    MAX_EXAMPLES,
    MAX_MEMBER_LENGTH,
    ScriptFile,
    Skill,
    SkillError,
    SkillExample,
    SkillState,
    script_sha256,
    verified_script,
)
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine, as_app
from tests.unit.test_run_skill import _entitlements, _outcome, _pin, _Runner, _tool
from tests.unit.test_run_skill import _Library as RunLibrary
from tests.unit.test_skill_library import IMPORTER, NOW, REVIEWER
from tests.unit.test_skill_routes import (
    DIALECT,
    SKILLS,
    Stored,
    get,
    post,
    screen_refusal,
)
from tests.unit.test_skill_routes import client as client  # the fixture, re-exported
from tests.unit.test_skill_routes import stored as stored  # the fixture, re-exported
from tests.unit.test_skill_store import entries
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0164_skill_scripts_examples_and_rehearsals.py"
TABLES = ("agent.skill_script", "agent.skill_example", "agent.skill_rehearsal")

SCRIPT_PATH = "scripts/check.py"
SCRIPT = b"print('3 accounts expire this month')\n"
CHANGED = SCRIPT + b"print('and one more thing')\n"

EXAMPLES = (
    {"task": "A client asks when their domain expires", "expected": "Names the expiry date"},
    {"task": "A client asks twice in a day", "expected": "Answers the same way twice"},
)


def skill_md(
    *, name: str = "hosting-expiry", version: str = "1.0.0", scripts: bool = True, body: str = ""
) -> str:
    """A `SKILL.md` declaring the one script, or none."""
    lines = [
        "---",
        f"name: {name}",
        "description: Use when a client asks whether their domain is close to renewal",
        f"version: {version}",
        "tools: [crm.read_client]",
    ]
    if scripts:
        lines.append(f"scripts: [{SCRIPT_PATH}]")
    lines += ["---", body or "Run the check, then open a ticket.", ""]
    return "\n".join(lines)


def a_zip(members: Mapping[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)
    return out.getvalue()


def members_of(archive: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        return {info.filename: opened.read(info) for info in opened.infolist()}


def a_package_zip(
    *, script: bytes | None = SCRIPT, examples: bool = True, folder: str = "hosting-expiry/"
) -> bytes:
    members = {f"{folder}SKILL.md": skill_md(scripts=script is not None).encode("utf-8")}
    if script is not None:
        members[f"{folder}{SCRIPT_PATH}"] = script
    if examples:
        members[f"{folder}{EXAMPLES_FILE}"] = json.dumps(list(EXAMPLES)).encode("utf-8")
    return a_zip(members)


def a_packaged_skill(**package: Any) -> LibrarySkill:
    return added(read_package("hosting-expiry.zip", a_package_zip(**package)), by=IMPORTER, at=NOW)


def passing(one: LibrarySkill, *, by: str = REVIEWER) -> Rehearsal:
    return rehearsal(one, [True] * len(one.imported.skill.examples), by=by, at=NOW)


def an_approved_package(**package: Any) -> LibrarySkill:
    one = a_packaged_skill(**package)
    return decided(one, reviewer=REVIEWER, approve=True, at=NOW, rehearsal=passing(one))


def plain(**fields: Any) -> Skill:
    base: dict[str, Any] = {
        "name": "hosting-expiry",
        "description": "Use when a client asks",
        "version": "1.0.0",
        "tools": ("crm.read_client",),
        "body": "Run the check.",
    }
    base.update(fields)
    return Skill(**base)


def with_script(content: bytes = SCRIPT, path: str = SCRIPT_PATH, **fields: Any) -> Skill:
    return plain(
        scripts=(path,),
        script_files=(ScriptFile(path=path, sha256=script_sha256(content)),),
        **fields,
    )


# ============================================================================ the digest
def test_a_skill_with_no_scripts_and_no_examples_digests_exactly_as_before_either_existed() -> None:
    """**The property that keeps every approval already granted.** The digest of a skill with
    neither is the length-prefixed sha256 the library has always stored as its key, computed here
    from the literal schema word rather than from the module's constant, so a change to either
    the constant or the formula shows.

    Delete this and appending the contents section unconditionally ships green, and every skill
    on every install reads as changed since approval the moment the release lands."""
    skill = plain()
    parts = [
        "brain.skill.v1",
        skill.name,
        skill.version,
        skill.description,
        skill.body,
        *skill.tools,
    ]
    before = hashlib.sha256("".join(f"{len(p)}:{p}" for p in parts).encode("utf-8")).hexdigest()

    assert skill.digest() == before
    named_only = plain(scripts=(SCRIPT_PATH,))
    parts_named = [*parts, SCRIPT_PATH]
    assert (
        named_only.digest()
        == hashlib.sha256("".join(f"{len(p)}:{p}" for p in parts_named).encode()).hexdigest()
    )


def test_a_script_s_bytes_and_its_path_are_each_in_the_digest() -> None:
    """**M12.4.11.** One byte of a script changed, the same bytes under another path, and the
    bytes recorded or not: each is a different digest, so each needs a review of its own.

    Delete this and an approval survives an edit to the one part of a skill that is code."""
    approved = with_script()

    assert with_script(CHANGED).digest() != approved.digest()
    assert with_script(path="scripts/other.py").digest() != approved.digest()
    assert plain(scripts=(SCRIPT_PATH,)).digest() != approved.digest()
    assert with_script().digest() == approved.digest()


def test_an_example_s_task_and_its_expectation_are_each_in_the_digest() -> None:
    """**M12.3.4.** An example reworded, an expectation reworded, one removed and two reordered
    are each a different version, so a rehearsal recorded against one never covers another.

    Delete this and an example can be edited after its rehearsal without the rehearsal noticing."""
    one = SkillExample(task="Asks when it expires", expected="Names the date")
    two = SkillExample(task="Asks twice", expected="Answers the same way")
    base = plain(examples=(one, two)).digest()

    assert plain(examples=(one.model_copy(update={"task": "Asks"}), two)).digest() != base
    assert plain(examples=(one.model_copy(update={"expected": "Names"}), two)).digest() != base
    assert plain(examples=(one,)).digest() != base
    assert plain(examples=(two, one)).digest() != base
    assert plain(examples=(one, two)).digest() == base


def test_a_script_counted_in_the_contents_section_is_never_read_as_an_example() -> None:
    """The section counts each list before its items, so a script's path and sha256 cannot be the
    same digest as an example with those words. Delete this and the counts can be dropped with
    every other test here green."""
    sha = script_sha256(SCRIPT)
    scripted = with_script()
    exemplified = plain(
        scripts=(SCRIPT_PATH,), examples=(SkillExample(task=SCRIPT_PATH, expected=sha),)
    )

    assert scripted.digest() != exemplified.digest()


def test_a_skill_records_the_bytes_of_every_declared_script_or_of_none() -> None:
    """A partial set is a script nobody read, a file never declared is a file nobody listed, and
    two sha256 for one path would be a guess; none recorded is a `SKILL.md` read on its own.

    Delete this and a skill can be approved with one of its two scripts' bytes covered."""
    first = ScriptFile(path="a.py", sha256=script_sha256(b"a"))
    second = ScriptFile(path="b.py", sha256=script_sha256(b"b"))

    with pytest.raises(ValueError, match="every declared script is recorded"):
        plain(scripts=("a.py", "b.py"), script_files=(first,))
    with pytest.raises(ValueError, match="every declared script is recorded"):
        plain(scripts=("a.py",), script_files=(first, second))
    with pytest.raises(ValueError, match="one sha256 per script"):
        plain(scripts=("a.py",), script_files=(first, first))
    with pytest.raises(ValueError, match="not a sha256"):
        ScriptFile(path="a.py", sha256="not-a-digest")
    with pytest.raises(SkillError, match="segment"):
        ScriptFile(path="../a.py", sha256=script_sha256(b"a"))
    assert plain(scripts=("b.py", "a.py"), script_files=(second, first)).script_files == (
        first,
        second,
    )
    assert plain(scripts=("a.py",)).script_files == ()


def test_the_example_bounds_are_the_golden_question_s_and_a_skill_carries_at_most_twenty() -> None:
    """Held to `brain.agents.template.GOLDEN_CHARS`, the same kind of sentence for an agent, and to
    the table's copies. Delete this and the one can widen without the other, and an example the
    domain admits is refused by the column after the press."""
    assert skills_module.EXAMPLE_CHARS == GOLDEN_CHARS == table_module.EXAMPLE_CHARS
    assert MAX_EXAMPLES == table_module.MAX_EXAMPLES == 20
    with pytest.raises(ValueError):
        SkillExample(task="x" * (GOLDEN_CHARS + 1), expected="y")
    with pytest.raises(ValueError):
        SkillExample(task="   ", expected="y")
    one = SkillExample(task="x", expected="y")
    with pytest.raises(ValueError):
        plain(examples=(one,) * (MAX_EXAMPLES + 1))
    assert len(plain(examples=(one,) * MAX_EXAMPLES).examples) == MAX_EXAMPLES


def test_a_review_diff_shows_a_changed_script_and_a_reworded_example() -> None:
    """The review pane names a script whose sha256 moved and an example whose words did, beside
    the body lines. Delete this and a reviewer is shown an edit that changed a script as one that
    changed nothing."""
    before = with_script(examples=(SkillExample(task="Asks", expected="Answers"),))
    after = with_script(CHANGED, examples=(SkillExample(task="Asks", expected="Replies"),))

    fields = {one.field: (one.before, one.after) for one in content_diff(before, after).fields}

    assert fields["script_files"] == (
        f"{SCRIPT_PATH} ({script_sha256(SCRIPT)})",
        f"{SCRIPT_PATH} ({script_sha256(CHANGED)})",
    )
    assert fields["examples"] == ("Asks -> Answers", "Asks -> Replies")


# ======================================================================= before a run
def test_the_approved_bytes_of_a_declared_script_pass_and_nothing_else_does() -> None:
    """`verified_script` is the one comparison of a script's bytes with the approval. The approved
    bytes come back unchanged; a changed byte, an undeclared path and a declared script with no
    recorded sha256 are each refused, and no refusal quotes the bytes.

    Delete this and the comparison can be reduced to a membership test, and a changed script
    passes as the approved one."""
    skill = with_script()

    assert verified_script(skill, SCRIPT_PATH, SCRIPT) == SCRIPT
    with pytest.raises(SkillError) as changed:
        verified_script(skill, SCRIPT_PATH, CHANGED)
    assert A_SCRIPT_CHANGED_AFTER_APPROVAL_IS_REFUSED_BEFORE_IT_RUNS in str(changed.value)
    assert "one more thing" not in str(changed.value)
    with pytest.raises(SkillError, match="declares no script"):
        verified_script(skill, "scripts/other.py", SCRIPT)
    with pytest.raises(SkillError, match="records no sha256"):
        verified_script(plain(scripts=(SCRIPT_PATH,)), SCRIPT_PATH, SCRIPT)


def test_a_changed_script_is_refused_in_planning_and_the_runner_is_never_handed_it() -> None:
    """**M12.4.11 at the door to a run.** `plan_run` refuses bytes that are not the approved ones
    before a spec exists, and the execution tool hands its runner nothing; the approved bytes are
    planned and travel in the spec, so a runner never reads a file somebody could have changed.

    Delete this and `plan_run` can drop the comparison, or the spec stop carrying the bytes, with
    every test of the sandbox's other properties green."""
    skill = with_script()
    request = ScriptRequest(skill=skill.name, script=SCRIPT_PATH)

    spec = plan_run(
        skill, request, content=SCRIPT, leash=ScriptLeash(), environment={}, reach_hash=""
    )
    assert spec.content == SCRIPT and spec.digest == skill.digest()
    with pytest.raises(SkillScriptError, match="not the one that was approved"):
        plan_run(
            skill, request, content=CHANGED, leash=ScriptLeash(), environment={}, reach_hash=""
        )

    imported = a_packaged_skill(examples=False).imported.approved_by(REVIEWER, NOW)
    ceiling = _entitlements("agent", "invoke:skill.script")
    caller = _entitlements("u_caller", "invoke:skill.script")
    entries_ = {("ops_agent", imported.skill.name): (_pin(imported.skill), imported)}
    for held, expected in ((CHANGED, None), (SCRIPT, SCRIPT)):
        runner = _Runner(_outcome())
        tool = _tool(RunLibrary(entries_, {SCRIPT_PATH: held}), runner)
        run_request = ScriptRequest(skill=imported.skill.name, script=SCRIPT_PATH)
        if expected is None:
            with pytest.raises(SkillScriptError):
                tool.handler()(
                    run_request, agent_id="ops_agent", entitlement=caller, agent_ceiling=ceiling
                )
            assert runner.specs == []
        else:
            tool.handler()(
                run_request, agent_id="ops_agent", entitlement=caller, agent_ceiling=ceiling
            )
            assert [one.content for one in runner.specs] == [expected]


def test_a_script_the_library_holds_no_bytes_for_is_not_available_to_the_agent() -> None:
    """A pinned, approved skill whose script the library cannot produce is refused with the one
    sentence a model is ever shown, and nothing runs. Delete this and a missing file becomes an
    empty script run under the approval of the one that was there."""
    imported = a_packaged_skill(examples=False).imported.approved_by(REVIEWER, NOW)
    runner = _Runner(_outcome())
    tool = _tool(
        RunLibrary({("ops_agent", imported.skill.name): (_pin(imported.skill), imported)}, {}),
        runner,
    )

    with pytest.raises(SkillScriptError, match=SKILL_NOT_AVAILABLE):
        tool.handler()(
            ScriptRequest(skill=imported.skill.name, script=SCRIPT_PATH),
            agent_id="ops_agent",
            entitlement=_entitlements("u_caller", "invoke:skill.script"),
            agent_ceiling=_entitlements("agent", "invoke:skill.script"),
        )
    assert runner.specs == []


# ============================================================================ packages
def test_a_zip_carrying_its_script_and_examples_is_read_with_their_sha256_and_order() -> None:
    """**The positive case for every package refusal below.** The script's bytes arrive beside the
    skill, their sha256 is recorded, the examples read back in order, and the folder the zip was
    made from is not part of any path.

    Delete this and every refusal here is satisfied by a reader that refuses every zip."""
    package = read_package("hosting-expiry.zip", a_package_zip())

    assert package.skill.script_files == (
        ScriptFile(path=SCRIPT_PATH, sha256=script_sha256(SCRIPT)),
    )
    assert [e.model_dump() for e in package.skill.examples] == list(EXAMPLES)
    assert package.scripts == {SCRIPT_PATH: SCRIPT}
    assert package.exported_as is None
    at_the_top = read_package("hosting-expiry.zip", a_package_zip(folder=""))
    assert at_the_top.skill == package.skill


@pytest.mark.parametrize(
    ("content", "said"),
    [
        (b"not json", "not JSON"),
        (b'{"task": "a", "expected": "b"}', "not a list"),
        (b'[{"task": "a"}]', "exactly a task"),
        (b'[{"task": "a", "expected": "b", "score": 1}]', "exactly a task"),
        (b'[{"task": " ", "expected": "b"}]', "each some words"),
        (b'[{"task": 3, "expected": "b"}]', "each some words"),
        (json.dumps([{"task": "a", "expected": "b"}] * 21).encode(), "over the 20 limit"),
    ],
)
def test_an_examples_file_that_is_not_a_list_of_tasks_is_refused_saying_so(
    content: bytes, said: str
) -> None:
    """Every shape that is not a short list of task and expectation pairs is refused in words, and
    an unknown key is refused rather than ignored. Delete this and a malformed file lands as a
    skill with no examples, which is a skill approved without a rehearsal it was meant to need."""
    archive = a_zip({"SKILL.md": skill_md(scripts=False).encode("utf-8"), EXAMPLES_FILE: content})

    with pytest.raises(SkillLibraryError, match=said):
        read_package("hosting-expiry.zip", archive)


def test_a_package_that_carries_what_it_does_not_declare_or_reaches_outside_is_refused() -> None:
    """A file nobody declared, a script named like a package's own file, and a member outside the
    `SKILL.md`'s folder are each refused, naming the file. Delete this and a byte the digest does
    not cover rides into the library, or a script called examples.json is read as the examples."""
    stray = a_zip(
        {
            "SKILL.md": skill_md(scripts=False).encode("utf-8"),
            "notes/run.py": b"print('undeclared')",
        }
    )
    clashing = a_zip(
        {
            "SKILL.md": skill_md(scripts=False)
            .replace("tools:", "scripts: [examples.json]\ntools:")
            .encode("utf-8"),
            EXAMPLES_FILE: b"[]",
        }
    )
    outside = a_zip(
        {"skill/SKILL.md": skill_md().encode("utf-8"), SCRIPT_PATH: SCRIPT},
    )

    with pytest.raises(SkillLibraryError) as refused:
        read_package("a.zip", stray)
    assert "notes/run.py" in str(refused.value)
    assert A_PACKAGE_KEEPS_ONLY_WHAT_ITS_DIGEST_COVERS in str(refused.value)
    with pytest.raises(SkillLibraryError, match="a file every package carries"):
        read_package("a.zip", clashing)
    with pytest.raises(SkillLibraryError, match="outside the folder"):
        read_package("a.zip", outside)


# ========================================================================= rehearsing
def test_a_version_with_examples_is_approved_only_once_every_example_behaved() -> None:
    """**M12.3.4.** No rehearsal, a rehearsal where one misbehaved, and a passing rehearsal of
    other bytes are each refused with the reason; a passing rehearsal of these bytes approves; a
    rejection needs none; and a version with no examples is approved as it always was.

    Delete this and `decided` can drop the gate, or accept a rehearsal of the version before."""
    one = a_packaged_skill()
    other = a_packaged_skill(script=CHANGED)

    for newest in (
        None,
        rehearsal(one, [True, False], by=REVIEWER, at=NOW),
        passing(other),
    ):
        with pytest.raises(SkillLibraryError) as refused:
            decided(one, reviewer=REVIEWER, approve=True, at=NOW, rehearsal=newest)
        assert A_VERSION_WITH_EXAMPLES_IS_APPROVED_ONLY_AFTER_THEY_ARE_REHEARSED in str(
            refused.value
        )

    approved = decided(one, reviewer=REVIEWER, approve=True, at=NOW, rehearsal=passing(one))
    assert approved.imported.is_executable()
    rejected = decided(one, reviewer=REVIEWER, approve=False, at=NOW)
    assert rejected.imported.state is SkillState.REJECTED
    no_examples = a_packaged_skill(examples=False)
    assert decided(no_examples, reviewer=REVIEWER, approve=True, at=NOW).imported.is_executable()


def test_a_rehearsal_is_one_verdict_per_example_of_an_undecided_version_that_has_some() -> None:
    """A version with no examples has nothing to rehearse, a decided one nothing a rehearsal could
    change, and a verdict count that is not one per example leaves one unrehearsed or rehearses
    one that does not exist; each is refused. The positive case records who, when and each verdict.

    Delete this and a rehearsal of one example can let a version of two through."""
    one = a_packaged_skill()

    with pytest.raises(SkillLibraryError, match="no example tasks"):
        rehearsal(a_packaged_skill(examples=False), [True], by=REVIEWER, at=NOW)
    with pytest.raises(SkillLibraryError, match="already approved"):
        rehearsal(an_approved_package(), [True, True], by=REVIEWER, at=NOW)
    for count in (1, 3):
        with pytest.raises(SkillLibraryError, match="carries 2 example tasks"):
            rehearsal(one, [True] * count, by=REVIEWER, at=NOW)
    with pytest.raises(SkillLibraryError, match="named person"):
        rehearsal(one, [True, True], by=" ", at=NOW)
    done = rehearsal(one, [True, True], by=REVIEWER, at=NOW)
    assert (done.digest, done.behaved, done.rehearsed_by, done.passed) == (
        one.digest,
        (True, True),
        REVIEWER,
        True,
    )
    assert Rehearsal(digest=one.digest, behaved=(), rehearsed_by=REVIEWER, at=NOW).passed is False


def test_waiting_for_a_rehearsal_asks_the_newest_one_of_exactly_these_bytes() -> None:
    """Delete this and a stale pass stands after a later failure, or a pass recorded with fewer
    verdicts than the version has examples approves it."""
    one = a_packaged_skill()

    assert awaits_rehearsal(one, None)
    assert not awaits_rehearsal(one, passing(one))
    assert awaits_rehearsal(one, rehearsal(one, [False, True], by=REVIEWER, at=NOW))
    short = Rehearsal(digest=one.digest, behaved=(True,), rehearsed_by=REVIEWER, at=NOW)
    assert awaits_rehearsal(one, short)
    assert not awaits_rehearsal(a_packaged_skill(examples=False), None)


# ============================================================================== editing
def test_an_edit_carries_the_scripts_and_examples_and_waits_for_its_own_rehearsal() -> None:
    """**M12.3.2 with a package.** An edit of the `SKILL.md` keeps the scripts' bytes and the
    examples of the version edited, is a new digest, and the rehearsal of the old version does not
    let it through. Delete this and an edit drops the scripts it cannot see, or rides on the
    rehearsal of words it changed."""
    one = an_approved_package()
    text = skill_md(version="1.1.0", body="Run the check twice, then open a ticket.")

    edit = edited(one, text, by=IMPORTER, at=NOW, library=(one,), scripts={SCRIPT_PATH: SCRIPT})

    assert edit.imported.skill.script_files == one.imported.skill.script_files
    assert edit.imported.skill.examples == one.imported.skill.examples
    assert edit.scripts == {SCRIPT_PATH: SCRIPT}
    assert edit.digest != one.digest and edit.edited_from == one.digest
    of_the_old = Rehearsal(digest=one.digest, behaved=(True, True), rehearsed_by=REVIEWER, at=NOW)
    assert awaits_rehearsal(edit, of_the_old)
    assert not awaits_rehearsal(edit, passing(edit))


def test_an_edit_is_refused_when_a_stored_script_changed_or_its_scripts_do() -> None:
    """The bytes carried over are held to the sha256 the version was added as, and an edit that
    declares other scripts is refused, because a script is changed by a package a reviewer is
    shown. Delete this and an edit is the way a changed script enters the library."""
    one = an_approved_package()
    text = skill_md(version="1.1.0", body="Run the check twice.")

    for held in ({SCRIPT_PATH: CHANGED}, {}):
        with pytest.raises(SkillLibraryError, match="no longer matches"):
            edited(one, text, by=IMPORTER, at=NOW, library=(one,), scripts=held)
    with pytest.raises(SkillLibraryError, match="keeps the scripts"):
        edited(
            one,
            skill_md(version="1.1.0", scripts=False),
            by=IMPORTER,
            at=NOW,
            library=(one,),
            scripts={SCRIPT_PATH: SCRIPT},
        )


# ============================================================================ exporting
def test_only_an_approved_version_whose_stored_scripts_are_the_approved_ones_is_exported() -> None:
    """Undecided, rejected and changed-since versions have no approved digest to carry, and a
    stored script that is not the approved one is not written into a package. Delete this and an
    export carries a digest nobody approved, or a script under an approval it does not have."""
    waiting = a_packaged_skill()
    rejected = decided(waiting, reviewer=REVIEWER, approve=False, at=NOW)
    approved = an_approved_package()

    for one in (waiting, rejected):
        with pytest.raises(SkillLibraryError) as refused:
            exported(one, {SCRIPT_PATH: SCRIPT})
        assert ONLY_AN_APPROVED_VERSION_IS_EXPORTED in str(refused.value)
    with pytest.raises(SkillLibraryError, match="not the one that was approved"):
        exported(approved, {SCRIPT_PATH: CHANGED})
    assert exported(approved, {SCRIPT_PATH: SCRIPT}).digest == approved.digest


def test_an_exported_package_reads_back_as_its_version_and_lands_undecided() -> None:
    """**M12.3.1.** The zip holds the `SKILL.md`, the script, the examples and a manifest naming
    the format, name, version and digest; two exports are the same bytes; read by another
    install's `read_package` it is the same digest, marked as the version it was exported as, and
    added it is undecided, because an approval does not travel with the file.

    Delete this and an export can lose a file, or land approved on an install where nobody
    reviewed it."""
    approved = an_approved_package()

    out = exported(approved, {SCRIPT_PATH: SCRIPT})
    members = members_of(out.content)

    assert out.file_name == "hosting-expiry-1.0.0.zip"
    assert set(members) == {"SKILL.md", SCRIPT_PATH, EXAMPLES_FILE, MANIFEST_FILE}
    assert members[SCRIPT_PATH] == SCRIPT
    assert json.loads(members[MANIFEST_FILE]) == {
        "format": PACKAGE_FORMAT,
        "name": "hosting-expiry",
        "version": "1.0.0",
        "digest": approved.digest,
    }
    assert exported(approved, {SCRIPT_PATH: SCRIPT}).content == out.content
    back = read_package(out.file_name, out.content)
    assert back.skill == approved.imported.skill
    assert back.exported_as == approved.digest
    landed = added(back, by="u_elsewhere", at=NOW)
    assert landed.imported.state is SkillState.IMPORTED
    assert not landed.imported.is_executable() and landed.imported.reviewer == ""


@pytest.mark.parametrize(
    "change",
    ["script", "body", "example", "digest", "version", "format", "extra key", "no manifest key"],
)
def test_a_package_changed_after_its_export_is_refused_whichever_file_changed(
    change: str,
) -> None:
    """Every file of an exported package is covered: a changed script, instructions or example
    digests differently from the manifest, and a manifest altered or of another shape is refused.
    Delete this and a package edited in transit lands as the version it claims to be."""
    approved = an_approved_package()
    members = members_of(exported(approved, {SCRIPT_PATH: SCRIPT}).content)
    manifest = json.loads(members[MANIFEST_FILE])
    if change == "script":
        members[SCRIPT_PATH] = CHANGED
    elif change == "body":
        members["SKILL.md"] = members["SKILL.md"].replace(b"open a ticket", b"close the ticket")
    elif change == "example":
        members[EXAMPLES_FILE] = members[EXAMPLES_FILE].replace(b"twice", b"thrice")
    elif change == "digest":
        members[MANIFEST_FILE] = json.dumps({**manifest, "digest": "f" * 64}).encode()
    elif change == "version":
        members[MANIFEST_FILE] = json.dumps({**manifest, "version": "9.9.9"}).encode()
    elif change == "format":
        members[MANIFEST_FILE] = json.dumps({**manifest, "format": "other.v1"}).encode()
    elif change == "extra key":
        members[MANIFEST_FILE] = json.dumps({**manifest, "approved_by": "u_x"}).encode()
    else:
        del manifest["digest"]
        members[MANIFEST_FILE] = json.dumps(manifest).encode()

    with pytest.raises(SkillLibraryError):
        read_package("hosting-expiry-1.0.0.zip", a_zip(members))
    if change in ("script", "body", "example", "digest", "version"):
        with pytest.raises(SkillLibraryError) as refused:
            read_package("hosting-expiry-1.0.0.zip", a_zip(members))
        assert AN_EXPORTED_PACKAGE_LANDS_UNREVIEWED_AND_ONLY_IF_ITS_BYTES_MATCH_ITS_DIGEST in str(
            refused.value
        )


def test_a_package_too_large_to_import_elsewhere_is_not_exported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an export succeeds on this install and is refused on every other."""
    approved = an_approved_package()
    monkeypatch.setattr(library_module, "MAX_PACKAGE_BYTES", 64)

    with pytest.raises(SkillLibraryError, match="byte limit"):
        exported(approved, {SCRIPT_PATH: SCRIPT})
    assert MAX_PACKAGE_BYTES == table_module.MAX_SCRIPT_BYTES


# ============================================================================== 0164
def test_0164_copies_the_grammars_and_figures_the_models_the_domain_and_the_recorder_hold() -> None:
    """Delete this and one side can change alone: a script path the table refuses after the
    press, a rule the model states and the migration does not, or an outcome word the trigger
    writes that `AuditRecorder` no longer spells."""
    migration = migration_module(MIGRATION)

    assert migration.TABLES == TABLES
    assert migration.down_revision == "0152"
    assert (migration.IDENTIFIER, migration.DIGEST) == (IDENTIFIER, DIGEST)
    assert migration.SCRIPT_PATH_PATTERN == table_module.SCRIPT_PATH_PATTERN
    assert migration.SCRIPT_PATH_CHARS == table_module.SCRIPT_PATH_CHARS == MAX_MEMBER_LENGTH
    assert migration.MAX_SCRIPT_BYTES == table_module.MAX_SCRIPT_BYTES == MAX_PACKAGE_BYTES
    assert migration.MAX_EXAMPLES == MAX_EXAMPLES
    assert migration.EXAMPLE_CHARS == GOLDEN_CHARS
    assert migration.SCRIPT_SHA256_IS_OF_ITS_CONTENT == table_module.SCRIPT_SHA256_IS_OF_ITS_CONTENT
    assert migration.PASSED_WHEN_NO_EXAMPLE_FAILED == table_module.PASSED_WHEN_NO_EXAMPLE_FAILED
    assert (
        RehearsalOutcome.PASSED.value,
        RehearsalOutcome.FAILED.value,
    ) == (migration.PASSED, migration.FAILED)
    body = " ".join(migration.SKILL_REHEARSAL_TRIGGER_FUNCTION.split())
    assert "'outcome', CASE WHEN NEW.passed THEN 'passed' ELSE 'failed' END" in body
    assert "'change', 'rehearsed', 'digest', NEW.digest" in body
    assert "v_seq, v_at, NEW.rehearsed_by, 'skill', v_subject" in body
    for path in ("run.py", SCRIPT_PATH, "a.b-c_d/e/f.sh"):
        assert skills_module.safe_archive_member(path) == path
        assert re.match(table_module.SCRIPT_PATH_PATTERN, path)


@pytest.mark.parametrize("qualified", TABLES)
def test_0164_builds_each_table_exactly_as_the_model_declares_it(qualified: str) -> None:
    """Compared as rendered DDL, for `test_tables`' reason. Delete this and the model can lose the
    check holding a script's sha256 to its bytes, with the database built the old way."""
    expected = squash(str(CreateTable(metadata.tables[qualified]).compile(dialect=DIALECT)))

    assert expected in squash(rendered("upgrade", MIGRATION))


def test_0164_reads_and_writes_in_the_session_s_name_and_never_edits_or_removes() -> None:
    """Row-level security on all three, SELECT and INSERT only, each insert in the session's own
    name, a trigger after every rehearsal, and a downgrade that drops what the upgrade made.

    Delete this and an UPDATE grant ships, which is a script's bytes changed under its approval."""
    emitted = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))
    principal = "current_setting('app.principal_id', true)"

    for qualified, column in (
        ("agent.skill_script", "submitted_by"),
        ("agent.skill_example", "submitted_by"),
        ("agent.skill_rehearsal", "rehearsed_by"),
    ):
        assert f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY" in emitted
        assert f"GRANT SELECT, INSERT ON {qualified} TO brain_app" in emitted
        assert f"UPDATE ON {qualified}" not in emitted
        assert f"DELETE ON {qualified}" not in emitted
        assert f"FOR INSERT TO brain_app WITH CHECK ({column} = {principal})" in emitted
        assert f"DROP TABLE {qualified}" in down
    assert (
        "CREATE TRIGGER skill_rehearsal_is_audited AFTER INSERT ON agent.skill_rehearsal "
        "FOR EACH ROW EXECUTE FUNCTION agent.record_skill_rehearsal()"
    ) in emitted
    assert "DROP FUNCTION agent.record_skill_rehearsal()" in down


def test_a_rehearsal_s_entry_is_the_recorder_s() -> None:
    """Delete this and `AuditRecorder.skill` and the trigger can spell a rehearsal differently, and
    the audit screen's search for one finds half of them."""
    recorder = AuditRecorder(
        AuditChain(), actor_id=REVIEWER, ent_hash="0" * 32, trace_id="t", clock=lambda: NOW
    )
    one = a_packaged_skill()

    entry = recorder.skill(
        name=one.name,
        digest=one.digest,
        change=SkillChange.REHEARSED,
        outcome=RehearsalOutcome.PASSED,
    )

    assert entry.action is AuditAction.SKILL
    assert dict(entry.details) == {"change": "rehearsed", "digest": one.digest, "outcome": "passed"}


# =========================================================================== the database
@contextmanager
def head(database: str) -> Iterator[str]:
    """A scratch database at head, or a skip without a server or pgvector."""
    with at_head(database) as url:
        yield url


def stored_through(url: str, *writes: Any) -> Any:
    """Run these store calls as the application role, in order, and answer the last."""

    async def go() -> Any:
        engine = app_engine(url)
        try:
            store = StoredSkills(make_session_factory(engine))
            answer: Any = None
            for write in writes:
                answer = await write(store)
            return answer
        finally:
            await engine.dispose()

    return run(go)


def test_a_package_s_scripts_examples_and_rehearsals_are_stored_beside_it_and_read_back() -> None:
    """**M12.4.11 and M12.3.4 through the store, as the application role.** A skill added with a
    script and two examples reads back with the script's sha256 and the examples in order, and the
    bytes are read for its digest alone; a failing and then a passing rehearsal are each a row and a
    `skill` entry the recorder's way, the newest decides, and the approval stands on it; the chain
    verifies. **Skips without a server.**"""
    one = a_packaged_skill()

    with head("brain_skill_packages") as url:
        done: dict[str, Any] = {}

        async def add(store: StoredSkills) -> Any:
            return await store.add(one, ent_hash="a" * 32, trace_id="t-add")

        async def rehearse(store: StoredSkills) -> Any:
            for verdicts in ((True, False), (True, True)):
                await store.rehearse(
                    rehearsal(one, verdicts, by=IMPORTER, at=NOW),
                    ent_hash="b" * 32,
                    trace_id="t-rehearse",
                )
            done["newest"] = (await store.rehearsals([one.digest]))[one.digest]
            done["kept"] = await store.skill(one.digest)
            done["scripts"] = await store.scripts(one.digest)
            approved = decided(
                done["kept"], reviewer=IMPORTER, approve=True, at=NOW, rehearsal=done["newest"]
            )
            return await store.decide(approved, ent_hash="c" * 32, trace_id="t-decide")

        assert stored_through(url, add) is True
        assert stored_through(url, rehearse) is True
        library = stored_through(url, lambda store: store.library())
        chain = entries(url)

    kept = done["kept"]
    assert kept.imported.skill == one.imported.skill and kept.digest == one.digest
    assert done["scripts"] == {SCRIPT_PATH: SCRIPT}
    assert done["newest"].behaved == (True, True)
    assert [one_.imported.is_executable() for one_ in library] == [True]
    said = [
        (entry.actor_id, entry.details.get("change"), entry.details.get("outcome"))
        for entry in chain
        if entry.action is AuditAction.SKILL
    ]
    assert said == [
        (IMPORTER, "imported", None),
        (IMPORTER, "rehearsed", "failed"),
        (IMPORTER, "rehearsed", "passed"),
        (IMPORTER, "self_approved", None),
    ]
    assert AuditChain(chain).verify() is None


def test_the_tables_refuse_a_changed_script_a_lying_sha256_and_a_lying_rehearsal() -> None:
    """Measured as the application role with the session naming the actor, so the policy admits
    the row and what refuses is the rule asked about: an update of a script's bytes has no grant, a
    sha256 that is not of the bytes breaks its check, and a rehearsal claiming to pass with a
    verdict that did not breaks its own; a script in somebody else's name breaks the policy.

    Delete this and each rule is a claim about a table definition nobody has run. **Skips without
    a server.**"""
    one = a_packaged_skill()

    with head("brain_skill_package_refusals") as url:

        async def add(store: StoredSkills) -> Any:
            return await store.add(one, ent_hash="a" * 32, trace_id="t")

        stored_through(url, add)
        failures: dict[str, str] = {}
        statements = {
            "update": (
                "UPDATE agent.skill_script SET content = %s, content_sha256 = %s",
                (CHANGED, script_sha256(CHANGED)),
            ),
            "sha": (
                "INSERT INTO agent.skill_script (skill_digest, path, content, content_sha256,"
                " submitted_by) VALUES (%s, 'scripts/other.py', %s, %s, %s)",
                (one.digest, CHANGED, script_sha256(SCRIPT), IMPORTER),
            ),
            "rehearsal": (
                "INSERT INTO agent.skill_rehearsal (digest, behaved, passed, rehearsed_by)"
                " VALUES (%s, '[true, false]'::jsonb, true, %s)",
                (one.digest, IMPORTER),
            ),
            "somebody else": (
                "INSERT INTO agent.skill_example (skill_digest, ordinal, task, expected,"
                " submitted_by) VALUES (%s, 3, 'a', 'b', %s)",
                (one.digest, IMPORTER),
            ),
        }
        for name, (statement, params) in statements.items():
            actor = "u_other" if name == "somebody else" else IMPORTER
            with as_app(url, ("app.principal_id", actor)) as conn:
                try:
                    conn.execute(statement, params)
                except psycopg.Error as refused:
                    failures[name] = (
                        f"{refused.sqlstate} {getattr(refused.diag, 'constraint_name', '')}"
                    )
        passing_row = sql(url, "SELECT count(*) FROM agent.skill_script")

    assert failures["update"].startswith("42501")
    assert failures["sha"] == "23514 ck_skill_script_content_sha256_is_of_its_content"
    assert failures["rehearsal"] == "23514 ck_skill_rehearsal_passed_when_no_example_failed"
    assert failures["somebody else"].startswith("42501")
    assert passing_row == [(1,)]


def test_an_exported_package_lands_undecided_on_a_second_install_built_from_empty() -> None:
    """**M12.3.1 on a second install, as needs-rupash 103 has it proved: a scratch database built
    to head, never the company's.** A skill with a script and examples is added, rehearsed,
    approved and exported on one install; the package is added on a second install built from
    empty through the same migrations, where it has the same digest, its script's bytes and its
    examples, and lands undecided: not executable, no reviewer, and its approval there waits for a
    rehearsal of its own, because nothing of the first install's review travelled with it.

    Delete this and the landing an export exists for is a claim nobody has run on a database the
    exporting install never touched. **Skips without a server.**"""
    one = a_packaged_skill()
    done: dict[str, Any] = {}

    with head("brain_skill_export_first") as first:

        async def approve_and_export(store: StoredSkills) -> Any:
            await store.add(one, ent_hash="a" * 32, trace_id="t")
            await store.rehearse(passing(one, by=IMPORTER), ent_hash="a" * 32, trace_id="t")
            newest = (await store.rehearsals([one.digest]))[one.digest]
            kept = await store.skill(one.digest)
            assert kept is not None
            approved = decided(kept, reviewer=IMPORTER, approve=True, at=NOW, rehearsal=newest)
            await store.decide(approved, ent_hash="a" * 32, trace_id="t")
            again = await store.skill(one.digest)
            assert again is not None
            return exported(again, await store.scripts(one.digest))

        package = stored_through(first, approve_and_export)

    with head("brain_skill_export_second") as second:
        assert sql(second, "SELECT count(*) FROM agent.skill") == [(0,)]
        arriving = added(read_package(package.file_name, package.content), by="u_other", at=NOW)

        async def land(store: StoredSkills) -> Any:
            assert await store.add(arriving, ent_hash="d" * 32, trace_id="t-land")
            done["landed"] = await store.skill(arriving.digest)
            done["scripts"] = await store.scripts(arriving.digest)
            done["rehearsals"] = await store.rehearsals([arriving.digest])
            return None

        stored_through(second, land)
        imported_entries = [
            (entry.actor_id, dict(entry.details))
            for entry in entries(second)
            if entry.action is AuditAction.SKILL
        ]

    landed = done["landed"]
    assert package.digest == one.digest == landed.digest
    assert landed.imported.skill == one.imported.skill
    assert done["scripts"] == {SCRIPT_PATH: SCRIPT}
    assert landed.imported.state is SkillState.IMPORTED and not landed.imported.is_executable()
    assert landed.imported.reviewer == "" and done["rehearsals"] == {}
    assert imported_entries == [
        ("u_other", {"change": "imported", "digest": one.digest, "source": "upload"})
    ]
    with pytest.raises(SkillLibraryError, match="has not been rehearsed"):
        decided(landed, reviewer="u_other", approve=True, at=NOW, rehearsal=None)


# ============================================================================== the routes
def a_zip_body(archive: bytes, file_name: str = "hosting-expiry.zip") -> dict[str, str]:
    return {
        "file_name": file_name,
        "content": base64.b64encode(archive).decode("ascii"),
        "encoding": "base64",
    }


def library_row(c: TestClient, pid: str, digest: str) -> dict[str, Any]:
    rows = get(c, pid).json()["library"]
    return next(one for one in rows if one["digest"] == digest)


def test_a_version_with_examples_is_rehearsed_then_approved_through_the_routes(
    client: TestClient, stored: Stored
) -> None:
    """**M12.3.4 end to end.** A zip with a script and two examples is added; its row shows the
    examples, the script's sha256 and, while it waits, its text, and says it awaits a rehearsal;
    approving it is refused in words; a caller who may neither add nor review is refused a
    rehearsal with the screen's one sentence; a rehearsal where one misbehaved leaves it waiting,
    and one where both behaved lets the approval through.

    Delete this and the review route can skip the rehearsal it has to pass to `decided`."""
    added_ = post(client, "u_admin", SKILLS, a_zip_body(a_package_zip()))
    assert added_.status_code == 201, added_.text
    digest = added_.json()["digest"]
    row = library_row(client, "u_admin", digest)
    assert [{"task": one["task"], "expected": one["expected"]} for one in row["examples"]] == list(
        EXAMPLES
    )
    assert row["scripts"] == [
        {
            "path": SCRIPT_PATH,
            "sha256": script_sha256(SCRIPT),
            "text": SCRIPT.decode(),
            "is_text": True,
        }
    ]
    assert (row["awaits_rehearsal"], row["rehearsable"]) == (True, True)
    # A reader of the library who may neither add nor review is shown which script and which
    # bytes, and never its text, its examples or a rehearsal.
    narrow = library_row(client, "u_narrow", digest)
    assert narrow["examples"] == [] and narrow["rehearsal"] is None
    assert narrow["scripts"] == [
        {"path": SCRIPT_PATH, "sha256": script_sha256(SCRIPT), "text": None, "is_text": True}
    ]
    assert narrow["rehearsable"] is False

    early = post(client, "u_admin", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    assert early.status_code == 404 and "rehearsed" in early.json()["message"]
    refused = post(client, "u_narrow", f"{SKILLS}/{digest}/rehearsals", {"behaved": [True, True]})
    assert refused.json()["message"] == screen_refusal(client)

    failing = post(client, "u_wide", f"{SKILLS}/{digest}/rehearsals", {"behaved": [True, False]})
    assert failing.status_code == 201, failing.text
    assert failing.json()["awaits_rehearsal"] is True
    assert failing.json()["rehearsal"]["passed"] is False
    wrong = post(client, "u_wide", f"{SKILLS}/{digest}/rehearsals", {"behaved": [True]})
    assert wrong.status_code == 404 and "carries 2 example tasks" in wrong.json()["message"]
    good = post(client, "u_wide", f"{SKILLS}/{digest}/rehearsals", {"behaved": [True, True]})
    assert good.json()["awaits_rehearsal"] is False
    approved = post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["review"] == "approved"
    assert [one.behaved for one in stored.library.rehearsed] == [(True, False), (True, True)]


def test_an_approved_skill_is_exported_through_the_route_and_reads_back_as_that_version(
    client: TestClient, stored: Stored
) -> None:
    """**M12.3.1 through the application.** Exporting a waiting version is refused in words; a
    caller without the skill authority is refused with the screen's one sentence before the digest
    is looked up; the approved version is answered as a base64 zip whose manifest names its digest,
    which `POST /skills` on another install would add undecided. Nothing is written.

    Delete this and the export route can answer a version nobody approved, or answer anybody."""
    digest = post(client, "u_admin", SKILLS, a_zip_body(a_package_zip())).json()["digest"]
    waiting = post(client, "u_admin", f"{SKILLS}/{digest}/exports", {})
    assert waiting.status_code == 404 and "approved" in waiting.json()["message"]
    post(client, "u_admin", f"{SKILLS}/{digest}/rehearsals", {"behaved": [True, True]})
    post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    assert library_row(client, "u_admin", digest)["exportable"] is True
    calls_before = [one for one in stored.library.calls if one in ("add", "decide", "rehearse")]

    for pid in ("u_narrow", "u_wide"):
        refused = post(client, pid, f"{SKILLS}/{digest}/exports", {})
        assert refused.json()["message"] == screen_refusal(client)
    answered = post(client, "u_admin", f"{SKILLS}/{digest}/exports", {})

    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert (body["name"], body["version"], body["digest"], body["encoding"]) == (
        "hosting-expiry",
        "1.0.0",
        digest,
        "base64",
    )
    back = read_package(body["file_name"], base64.b64decode(body["content"]))
    assert back.skill.digest() == digest and back.exported_as == digest
    assert [one for one in stored.library.calls if one in ("add", "decide", "rehearse")] == (
        calls_before
    )


def test_an_edit_through_the_route_carries_the_stored_scripts_over(
    client: TestClient, stored: Stored
) -> None:
    """The edit route reads the version's scripts from the store and hands them to `edited`, so
    the new version holds the same bytes and waits for its own rehearsal. Delete this and an edit
    of a skill with a script is refused for want of bytes the route never read."""
    digest = post(client, "u_admin", SKILLS, a_zip_body(a_package_zip())).json()["digest"]
    text = skill_md(version="1.1.0", body="Run the check twice, then open a ticket.")

    answered = post(client, "u_admin", f"{SKILLS}/{digest}/versions", {"content": text})

    assert answered.status_code == 201, answered.text
    new = answered.json()
    assert new["edited_from"] == digest and new["awaits_rehearsal"] is True
    assert stored.library.script_bytes[new["digest"]] == {SCRIPT_PATH: SCRIPT}
