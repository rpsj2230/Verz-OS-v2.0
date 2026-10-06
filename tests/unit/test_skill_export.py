"""An approved skill exported as a package another install imports, undecided (M12.3.1).

The first half is the package itself: an approved version, scripts included, exported and read
back by the library's own reader as the same skill; the same version exported twice is the same
bytes; an unapproved or moved version is refused; and a package changed after it was exported is
refused by the import saying so, while one with no manifest is any other package. The second half
is the route, through the application: who may export, the one 404 for a version the reader cannot
see, the answer another install's `POST /skills` takes as it is, landing there undecided, and the
export recorded. The third builds PostgreSQL to head: the row, its ledger entry, and a row in
somebody else's name refused.

Task ids: M12.3.1
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import zipfile
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from brain.console.skill_library import (
    EXPORT_MANIFEST,
    EXPORT_SCHEMA,
    LibrarySkill,
    SkillLibraryError,
    added,
    decided,
    exported,
    read_package,
)
from brain.tools.skills import SkillState
from tests.unit.test_skill_library import SKILL_MD, a_zip, text_with
from tests.unit.test_skill_routes import SKILLS, Stored, a_package, post, scripted_package
from tests.unit.test_skill_routes import client as client
from tests.unit.test_skill_routes import stored as stored

#: Far outside any plausible wall clock. See CLAUDE.md on a fixture with a date in it.
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
SCRIPT = b"print('renewal due')\n"


def approved(text: str = SKILL_MD, scripts: dict[str, bytes] | None = None) -> LibrarySkill:
    """One version as the library holds it once a second person approved it."""
    content = (
        a_zip({"SKILL.md": text.encode("utf-8"), **(scripts or {})})
        if scripts
        else text.encode("utf-8")
    )
    package = read_package("skill.zip" if scripts else "SKILL.md", content)
    return decided(added(package, by="u_admin", at=NOW), reviewer="u_wide", approve=True, at=NOW)


def members(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {one.filename: archive.read(one) for one in archive.infolist()}


def rezipped(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


# ------------------------------------------------------------------ the package


def test_an_approved_version_reads_back_on_another_install_as_itself_and_undecided() -> None:
    """**The round trip.** An approved version with a script is exported and read back by the
    library's own reader as the same skill, digest and script bytes included, and once added it is
    undecided there with nobody's review on it. The manifest names it, its version and its digest.
    Delete this and an export can carry a skill that imports as something else, or as approved."""
    one = approved(text_with(scripts="[scripts/check.py]"), {"scripts/check.py": SCRIPT})

    package = exported(one, {"scripts/check.py": SCRIPT})
    back = read_package(package.file_name, package.content)
    there = added(back, by="u_other_admin", at=NOW)

    held = members(package.content)
    assert sorted(held) == sorted(
        f"hosting-expiry/{path}" for path in ("SKILL.md", "scripts/check.py", EXPORT_MANIFEST)
    )
    assert json.loads(held[f"hosting-expiry/{EXPORT_MANIFEST}"]) == {
        "schema": EXPORT_SCHEMA,
        "name": "hosting-expiry",
        "version": one.imported.skill.version,
        "digest": one.digest,
    }
    assert back.skill.digest() == one.digest
    assert dict(back.scripts) == {"scripts/check.py": SCRIPT}
    assert (there.imported.state, there.imported.reviewer) == (SkillState.IMPORTED, "")
    assert not there.imported.is_executable()
    assert package.file_name == f"hosting-expiry-{one.imported.skill.version}.zip"


def test_one_version_always_exports_the_same_bytes() -> None:
    """Every member is written in a fixed order at a fixed instant. Delete this and two exports of
    one version cannot be matched by their hash, so a recipient cannot tell whether a second copy
    is the same skill."""
    one = approved()

    assert exported(one, {}).content == exported(one, {}).content


def test_only_an_approved_unchanged_version_leaves_the_install() -> None:
    """**AN_EXPORT_IS_OF_AN_APPROVED_VERSION_AND_LANDS_UNREVIEWED.** An undecided version and a
    rejected one are refused, and so is an approved one whose script bytes no longer match its
    digest. Delete this and a draft nobody reviewed can be shared as a package."""
    undecided = added(read_package("SKILL.md", SKILL_MD.encode("utf-8")), by="u_admin", at=NOW)
    rejected = decided(undecided, reviewer="u_wide", approve=False, at=NOW)
    scripted = approved(text_with(scripts="[scripts/check.py]"), {"scripts/check.py": SCRIPT})

    for refused in (undecided, rejected):
        with pytest.raises(SkillLibraryError, match="only a version a named person approved"):
            exported(refused, {})
    with pytest.raises(SkillLibraryError, match="no longer match its digest"):
        exported(scripted, {"scripts/check.py": b"print('something else')\n"})
    with pytest.raises(SkillLibraryError, match="no longer match its digest"):
        exported(scripted, {})


def test_a_package_changed_after_it_was_exported_is_refused_by_the_import() -> None:
    """**AN_EXPORT_SAYS_WHAT_IT_HOLDS_AND_AN_IMPORT_CHECKS_IT.** The body edited, or a script's
    bytes changed, with the manifest left as it was, and the import refuses it saying it was
    changed after it was exported; a manifest of another shape is refused too. The positive case:
    the same files with no manifest are any other package and are read. Delete this and a package
    altered in transit imports as the version it claims to be."""
    one = approved(text_with(scripts="[scripts/check.py]"), {"scripts/check.py": SCRIPT})
    held = members(exported(one, {"scripts/check.py": SCRIPT}).content)
    skill_md = "hosting-expiry/SKILL.md"
    script = "hosting-expiry/scripts/check.py"
    manifest = f"hosting-expiry/{EXPORT_MANIFEST}"

    edited = {**held, skill_md: held[skill_md] + b"\nAnd one more step nobody reviewed.\n"}
    assert edited[skill_md] != held[skill_md]
    changed = {**held, script: b"print('something else')\n"}
    for tampered in (edited, changed):
        with pytest.raises(SkillLibraryError, match="changed after it was exported"):
            read_package("skill.zip", rezipped(tampered))

    said = json.loads(held[manifest])
    for other in ({"schema": "elsewhere.v9"}, {**said, "schema": "elsewhere.v9"}):
        other_shape = {**held, manifest: json.dumps(other).encode("utf-8")}
        with pytest.raises(SkillLibraryError, match="not one this install writes"):
            read_package("skill.zip", rezipped(other_shape))

    plain = {path: content for path, content in edited.items() if path != manifest}
    assert read_package("skill.zip", rezipped(plain)).skill.name == "hosting-expiry"


def test_exporting_needs_the_authority_to_add_and_the_library_to_read() -> None:
    """**Both halves, each on its own.** A reader who may add skills and whose read of the screen
    is scoped to one department cannot read the library, so cannot export from it; a reader who
    reads the library and may not add cannot export either; holding both, they may. Delete this
    and either half can be dropped from the route with its tests still green, because every
    reader they build holds both or neither."""
    from brain.console.reads import Plane, plane_capability
    from brain.console.screens import screen
    from brain.console.skill_library import SKILL_AUTHORITY, may_export
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope

    read = screen("skills").read.requires
    plane = plane_capability(Plane.CONFIGURATION)

    def holding(*grants: tuple[object, Scope]) -> EntitlementSet:
        return EntitlementSet(
            principal_id="u_reader",
            grants=tuple(Grant(capability=one, scope=scope) for one, scope in grants),  # type: ignore[arg-type]
        )

    everywhere = Scope.unrestricted()
    both = holding((read, everywhere), (plane, everywhere), (SKILL_AUTHORITY, everywhere))
    adds_without_the_library = holding(
        (read, Scope.department("finance")), (plane, everywhere), (SKILL_AUTHORITY, everywhere)
    )
    reads_without_adding = holding((read, everywhere), (plane, everywhere))

    assert may_export(both, NOW)
    assert not may_export(adds_without_the_library, NOW)
    assert not may_export(reads_without_adding, NOW)


# ------------------------------------------------------------------ the route


def approved_in(client: TestClient, package: dict[str, str]) -> str:
    """Add a package as the administrator, approve it as the reviewer, and say its digest."""
    added_skill = post(client, "u_admin", SKILLS, package)
    assert added_skill.status_code == 201, added_skill.text
    digest = str(added_skill.json()["digest"])
    reviewed = post(client, "u_wide", f"{SKILLS}/{digest}/review", {"decision": "approve"})
    assert reviewed.status_code == 200, reviewed.text
    return digest


def test_an_administrator_exports_an_approved_version_and_another_install_takes_it_undecided(
    client: TestClient, stored: Stored
) -> None:
    """**M12.3.1 through the application.** The administrator exports the approved version and is
    answered with a package whose name, version and digest are the version's; the export is
    recorded in their name; and the answer's own three fields, posted to another install's
    library, are added there undecided with the same digest. Delete this and the export can answer
    something another install cannot take, or record nothing."""
    client.app.state.sandbox_address = "http://script-sandbox:3100"  # type: ignore[attr-defined]
    digest = approved_in(client, scripted_package())

    answered = post(client, "u_admin", f"{SKILLS}/{digest}/export", {})

    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert (body["name"], body["digest"], body["encoding"]) == ("hosting-expiry", digest, "base64")
    assert stored.library.exported == [(digest, "u_admin")]
    handed = {key: body[key] for key in ("file_name", "content", "encoding")}

    # Another install: the same application over a library of its own, which holds nothing.
    elsewhere = Stored()
    client.app.state.skill_library = elsewhere.library  # type: ignore[attr-defined]
    taken = post(client, "u_admin", SKILLS, handed)
    client.app.state.skill_library = stored.library  # type: ignore[attr-defined]
    assert taken.status_code == 201, taken.text
    assert list(elsewhere.library.skills) == [digest]
    assert (taken.json()["digest"], taken.json()["review"]) == (digest, "pending")
    assert (
        base64.b64decode(body["content"])
        == exported(
            stored.library.skills[digest],
            {"scripts/check.py": b"print('renewal due')\n"},
        ).content
    )


def test_a_version_the_reader_may_not_export_or_cannot_see_is_the_one_404(
    client: TestClient, stored: Stored
) -> None:
    """A reviewer who may not add, a reader holding only the screen, a version that does not
    exist, and an undecided version: the first three are the same refusal, naming the screen and
    nothing else, and the last says why in words; nothing is recorded for any. Delete this and an
    export can be taken by somebody who may not add skills, or say which digests exist."""
    approved_digest = approved_in(client, a_package())
    waiting = post(client, "u_admin", SKILLS, a_package(text_with(name="quote-format")))
    pending = str(waiting.json()["digest"])

    reviewer = post(client, "u_wide", f"{SKILLS}/{approved_digest}/export", {})
    reader = post(client, "u_narrow", f"{SKILLS}/{approved_digest}/export", {})
    nothing = post(client, "u_admin", f"{SKILLS}/{'f' * 64}/export", {})
    undecided = post(client, "u_admin", f"{SKILLS}/{pending}/export", {})

    assert {one.status_code for one in (reviewer, reader, nothing, undecided)} == {404}
    assert reviewer.json()["message"] == reader.json()["message"] == nothing.json()["message"]
    assert "only a version a named person approved" in undecided.json()["message"]
    assert stored.library.exported == []


# ------------------------------------------------------------------ on PostgreSQL


@pytest.mark.needs_db
def test_on_a_real_database_an_export_is_a_row_and_a_ledger_entry_in_the_exporters_name() -> None:
    """The export as the application role: one row, and one `skill` entry with the change
    `exported`, the digest and the exporter; a row naming somebody other than the session is
    refused by the policy. Delete this and an export can be recorded in somebody else's name, or
    not reach the ledger at all."""
    import psycopg

    from brain.ops.skill_store import StoredSkills
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head
    from tests.unit.test_suspension_store import app_engine

    one = approved()
    with at_head("brain_skill_export") as url:

        async def work() -> None:
            engine = app_engine(url)
            try:
                store = StoredSkills(make_session_factory(engine))
                waiting = added(
                    read_package("SKILL.md", SKILL_MD.encode("utf-8")), by="u_admin", at=NOW
                )
                await store.add(waiting, ent_hash="0" * 32, trace_id="t-add")
                await store.decide(one, ent_hash="0" * 32, trace_id="t-review")
                await store.export(one.digest, by="u_admin", ent_hash="1" * 32, trace_id="t-out")
            finally:
                await engine.dispose()

        asyncio.run(work())
        rows = sql(url, "SELECT digest, exported_by FROM agent.skill_export")
        entries = sql(
            url,
            "SELECT actor_id, subject, details, trace_id FROM obs.audit_entry "
            "WHERE action = 'skill' AND details->>'change' = 'exported'",
        )
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET ROLE brain_app")
            conn.execute("SELECT set_config('app.principal_id', 'u_admin', false)")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO agent.skill_export (digest, exported_by) VALUES (%s, 'u_other')",
                    (one.digest,),
                )

    assert rows == [(one.digest, "u_admin")]
    ((actor, subject, details, trace),) = entries
    assert (actor, subject, trace) == ("u_admin", "skill:hosting-expiry", "t-out")
    assert details == {"change": "exported", "digest": one.digest}


def test_the_export_button_is_offered_only_on_an_approved_version_to_a_reader_who_may_export(
    client: TestClient, stored: Stored
) -> None:
    """The version's `exportable` is true for the administrator on the approved version, and false
    for the reviewer who may not add, and on a version still waiting. Delete this and the page can
    draw an Export button the route refuses on every press."""
    approved_digest = approved_in(client, a_package())
    post(client, "u_admin", SKILLS, a_package(text_with(name="quote-format")))

    def offered(pid: str) -> dict[str, bool]:
        page = client.get(SKILLS, headers=_headers(pid)).json()
        return {one["digest"]: one["exportable"] for one in page["library"]}

    admin, reviewer = offered("u_admin"), offered("u_wide")
    assert admin[approved_digest] is True
    assert [flag for digest, flag in admin.items() if digest != approved_digest] == [False]
    assert set(reviewer.values()) == {False}


def _headers(pid: str) -> dict[str, str]:
    from tests.unit.test_api_routes import token_for
    from tests.unit.test_skill_routes import SECOND_FACTOR

    return {"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}
