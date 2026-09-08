"""The install screens held to the rule that a field nobody measured is not shown as measured.

Every test below hands over a manifest, a revision chain, a profile or a limiter state and
asks what the screen says. The rule they all serve is one: an install screen is read by
somebody deciding whether to stop investigating, so a value inferred from the source tree and
rendered like a measurement is not a small inaccuracy, it is the input to that decision.

The release is unknown outside a built image rather than falling back to something plausible,
the migration level is declared until somebody has asked the database and has no head at all
when the history has branched, and the profile's features come from the modules that already
decide them (M27.6.1). What is currently throttled is filtered by the limits screen's own
grant, because a rate limit's subject is often a person (M27.6.3). Capacity carries the
declared figure and the deployed one as two numbers and never derives one from the other
(M27.6.4).

The backup and recovery screen is not built and the last two tests are why: nothing in this
repository defines a function or a class for restoring anything, so a panel headed "last
verified restore" would be a reassurance nobody measured. Those tests fail on the day a
restore verifier lands, which is the day the screen should be written.

Task ids: M27.6.1, M27.6.3, M27.6.4
"""

from __future__ import annotations

import ast
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from brain.console.installation import (
    RECOVERY_NEEDS,
    ConnectionCapacity,
    Fact,
    InstallationError,
    MemoryCapacity,
    MigrationLevel,
    Source,
    ThrottleRow,
    connection_capacity,
    features_of,
    install_facts,
    installation_gaps,
    level_of,
    memory_capacity,
    recovery_gaps,
    throttled_now,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.install import INSTALLATION, Belongs
from brain.ops.compose import deployment_mib
from brain.ops.connections import DATABASES, demand_on, headroom_on
from brain.ops.inference import runs_inference_server
from brain.ops.install_from_empty import Revision, read_plan
from brain.ops.limits import Limit, LimiterState, LimitScope
from brain.ops.release_manifest import ReleaseManifest
from brain.ops.wiring import (
    HOST_TOTAL_MIB,
    PROFILES,
    WiringError,
    budget_breaches,
    components_for,
    runs_trace_ledger,
    wave_two_mib,
)

NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)
READER = "u_reader"

#: The limits screen's own requirement, read off the registry rather than spelled again.
LIMIT_READ = screen("limits").read.requires.value

#: An environment with nothing set, so `value_of` falls back to the product's neutral
#: defaults rather than to whatever this machine happens to export.
NOTHING_SET: dict[str, str] = {}


def holding(
    *capabilities: str,
    scope: Scope | None = None,
    planes: tuple[Plane, ...] = (Plane.CONFIGURATION,),
) -> EntitlementSet:
    """A reader holding these capabilities in one scope, plus the plane grants named."""
    where = scope if scope is not None else Scope(clauses=())
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id=READER, grants=tuple(grants))


def a_chain(*names: str) -> tuple[Revision, ...]:
    """A linear revision chain, each one pointing at the last."""
    made: list[Revision] = []
    parent: str | None = None
    for name in names:
        made.append(Revision(name=f"{name}_something", revision=name, down_revision=parent))
        parent = name
    return tuple(made)


def a_manifest() -> ReleaseManifest:
    return ReleaseManifest(commit="a" * 40, built_at=NOW, task_ids=("M27.6.1",))


# --------------------------------------------------------------- how a fact is known
def test_a_fact_nothing_knows_carries_no_value_a_renderer_could_show():
    """Deleting this lets an unknown fact arrive with a plausible string in it, which a
    renderer will show. Every convention for marking such a value as uncertain is one
    somebody has to keep, and the field is read by somebody about to stop investigating."""
    with pytest.raises(InstallationError, match="unknown and carries"):
        Fact(name="release", source=Source.UNKNOWN, value="probably HEAD", because="nothing")


def test_a_fact_nothing_knows_still_says_what_would_have_told_it():
    """Deleting this leaves a blank field with the word unknown beside it, which sends the
    reader looking for a setting that would not have helped."""
    with pytest.raises(InstallationError, match="does not say why"):
        Fact(name="release", source=Source.UNKNOWN)

    assert Fact(name="release", source=Source.UNKNOWN, because="no manifest in this image")


def test_a_fact_claiming_to_be_measured_carries_something_measured():
    """Deleting this lets an empty value wear a confident label, which is an unknown fact
    that a renderer draws as a measurement with nothing in it."""
    with pytest.raises(InstallationError, match="carries no value"):
        Fact(name="release", source=Source.MEASURED, value="   ")


def test_a_fact_with_no_name_is_refused_rather_than_rendered_under_a_blank_heading():
    """**Written because a mutation of `Fact`'s name check survived the whole file.** Every
    fact this suite built carried a name, so the refusal could be deleted and nothing would
    have said so.

    A nameless fact is a value on an install screen with no heading over it, read by somebody
    deciding whether to worry, and it is worse than that downstream: `installation_gaps`
    counts facts by name, so two of them collapse into one entry and are reported as a single
    heading appearing twice rather than as two facts nobody can identify.

    The blank case is separate from the empty one because a name arriving from a form is
    whitespace far more often than it is empty, and a bare falsiness check passes it.

    Delete this and a renderer draws a value in a column with nothing naming it."""
    with pytest.raises(InstallationError, match="a fact about nothing"):
        Fact(name="", source=Source.DECLARED, value="lite")

    with pytest.raises(InstallationError, match="a fact about nothing"):
        Fact(name="   ", source=Source.DECLARED, value="lite")

    assert Fact(name="profile", source=Source.DECLARED, value="lite").name == "profile"


# ------------------------------------------------------------- this install (M27.6.1)
def test_the_release_is_unknown_outside_a_built_image_rather_than_something_plausible():
    """Deleting this lets the console fall back to whatever commit is nearest, so the screen
    shows a developer's working tree on one machine and the image's stamp on another, under
    one heading. The reader has no way to tell which they are looking at."""
    facts = install_facts(profile="lite", manifest=None, revisions=a_chain("0001"), env=NOTHING_SET)

    release = next(one for one in facts if one.name == "release")
    assert release.source is Source.UNKNOWN
    assert release.value == ""
    assert "manifest" in release.because


def test_the_release_is_the_commit_stamped_into_the_image_when_there_is_one():
    """Deleting this leaves a guard satisfied by a screen that never shows a release at all.
    Every refusal test needs a sibling proving the thing still works."""
    facts = install_facts(
        profile="lite", manifest=a_manifest(), revisions=a_chain("0001"), env=NOTHING_SET
    )

    release = next(one for one in facts if one.name == "release")
    assert release.source is Source.MEASURED
    assert release.value == "a" * 40


def test_the_migration_level_is_declared_until_somebody_has_asked_the_database():
    """Deleting this prints the head the source tree carries under a heading reading
    migration level. That is right on every machine except one where somebody is looking,
    and they are looking because that machine is behind."""
    level = level_of(a_chain("0001", "0002", "0003"))

    assert level == MigrationLevel(revision="", head="0003", source=Source.DECLARED, pending=0)


def test_the_migration_level_is_measured_once_the_pending_list_has_been_read():
    """Deleting this leaves the screen unable to report the applied revision even when
    somebody did open a connection and ask, so the one measurement available is discarded."""
    level = level_of(a_chain("0001", "0002", "0003"), pending=["0003"])

    assert level.source is Source.MEASURED
    assert level.revision == "0002"
    assert level.head == "0003"
    assert level.pending == 1


def test_a_database_on_the_head_reports_the_head_as_applied():
    """Deleting this leaves the measured branch tested only by the behind case, which is
    satisfied by a function that always reports the previous revision."""
    level = level_of(a_chain("0001", "0002"), pending=[])

    assert level.revision == "0002"
    assert level.pending == 0


def test_a_branched_history_has_no_migration_level_and_no_head():
    """Deleting this makes the screen pick one of two heads, which is a coin toss shown
    without qualification. Two revisions sharing a parent is an alembic history somebody
    merged badly, and the honest answer is that there is no single one."""
    branched = (
        Revision(name="a", revision="0001", down_revision=None),
        Revision(name="b", revision="0002", down_revision="0001"),
        Revision(name="c", revision="0003", down_revision="0001"),
    )

    level = level_of(branched)

    assert level.source is Source.UNKNOWN
    assert level.head == ""
    assert level.revision == ""


def test_the_repositorys_own_migration_chain_is_a_single_line():
    """Deleting this lets the branched case above pass while the real chain is branched too,
    so the screen would report unknown on every install and nobody would know why."""
    level = level_of(read_plan().revisions)

    assert level.source is Source.DECLARED
    assert level.head


def test_a_branched_history_reaches_the_install_screen_as_an_unknown_that_says_why():
    """**Written because a mutation of the unknown branch inside `install_facts` survived.**
    The test above covers `level_of`, and nothing in this file called `install_facts` with a
    branched chain, so the branch that turns that verdict into a row could be deleted with
    every test still green.

    What the deletion produces is not a missing row. The level falls through to the measured
    branch and is built as a measured migration level carrying the empty revision, which is
    the shape `Fact` refuses, so the install screen raises on a merged alembic history rather
    than saying there is no single head. The three source values are the whole of this screen's
    honesty and the unknown one is the only one that shows nothing.

    Delete this and a branched history is either an exception on the screen somebody opened
    because something is wrong, or a blank measurement once somebody removes the refusal that
    is currently catching it."""
    branched = (
        Revision(name="a", revision="0001", down_revision=None),
        Revision(name="b", revision="0002", down_revision="0001"),
        Revision(name="c", revision="0003", down_revision="0001"),
    )

    facts = install_facts(profile="lite", manifest=None, revisions=branched, env=NOTHING_SET)

    level = next(one for one in facts if one.name == "migration level")
    assert level.source is Source.UNKNOWN
    assert level.value == ""
    assert "more than one head" in level.because


def test_a_single_line_history_reaches_the_install_screen_labelled_by_what_measured_it():
    """The sibling of the test above, and it covers the other two branches: a refusal test on
    its own is satisfied by a screen that reports every history as unknown.

    Declared without a pending list and measured with one, which is the same distinction
    `level_of` makes, asserted here through the screen rather than through the function so
    that the label a reader actually sees is the one under test.

    Delete this and `install_facts` can answer unknown for every install, which reads as a
    broken deployment on a machine that is fine."""
    declared = install_facts(
        profile="lite", manifest=None, revisions=a_chain("0001", "0002"), env=NOTHING_SET
    )
    measured = install_facts(
        profile="lite",
        manifest=None,
        revisions=a_chain("0001", "0002"),
        pending=["0002"],
        env=NOTHING_SET,
    )

    on_declared = next(one for one in declared if one.name == "migration level")
    assert on_declared.source is Source.DECLARED
    assert on_declared.value == "0002"
    assert on_declared.because

    on_measured = next(one for one in measured if one.name == "migration level")
    assert on_measured.source is Source.MEASURED
    assert on_measured.value == "0001"


def test_the_install_screen_names_no_identity_setting():
    """Deleting this puts the issuer and the redirect URIs on a screen. They have no safe
    default precisely because a wrong one signs people in against somewhere this install does
    not own, and reading them makes the screen raise on the half-configured install it is
    most often opened on."""
    identity = {one.name for one in INSTALLATION if one.belongs is Belongs.IDENTITY}
    facts = install_facts(profile="lite", manifest=None, revisions=a_chain("0001"), env=NOTHING_SET)

    assert identity
    assert not {one.name for one in facts} & identity

    smuggled = Fact(name=sorted(identity)[0], source=Source.DECLARED, value="https://example")
    assert any("identity setting" in one for one in installation_gaps(facts=[smuggled]))


def test_the_install_values_come_from_the_one_reader_and_not_from_the_environment():
    """Deleting this lets a second module resolve an installation value with its own default,
    and the wrong one is the one nobody looked at. Passing two different environments and
    getting two different answers is what proves the value is read through `value_of`."""
    neutral = install_facts(
        profile="lite", manifest=None, revisions=a_chain("0001"), env=NOTHING_SET
    )
    theirs = install_facts(
        profile="lite",
        manifest=None,
        revisions=a_chain("0001"),
        env={"INSTALL_COMPANY_NAME": "A Different Client"},
    )

    named = {one.name: one.value for one in neutral}
    changed = {one.name: one.value for one in theirs}
    assert named["INSTALL_COMPANY_NAME"] != changed["INSTALL_COMPANY_NAME"]
    assert changed["INSTALL_COMPANY_NAME"] == "A Different Client"


def test_a_fact_appearing_twice_is_reported():
    """Deleting this lets one heading carry two values, and which one the reader believes
    depends on which row they read first."""
    twice = [
        Fact(name="profile", source=Source.DECLARED, value="lite"),
        Fact(name="profile", source=Source.DECLARED, value="full"),
    ]

    assert any(
        "appears on the install screen 2 times" in one for one in installation_gaps(facts=twice)
    )
    assert installation_gaps(facts=twice[:1]) == ()


# --------------------------------------------------- what a profile turns on (M27.6.1)
def test_a_profile_turns_on_what_the_wiring_register_gives_it():
    """Deleting this lets the feature list be written by hand, which is a list that is right
    on the day it is written. The two functions that already decide these are called rather
    than restated, because each carries an argument about what lite does without."""
    for profile in PROFILES:
        found = {one.name: one.on for one in features_of(profile)}
        assert found["trace ledger"] is runs_trace_ledger(profile)
        assert found["local inference"] is runs_inference_server(profile)

    running = {one.name for one in components_for("full")}
    inference = next(one for one in features_of("full") if one.name == "local inference")
    assert set(inference.components) <= running


def test_an_unknown_profile_is_refused_rather_than_reported_as_nothing_switched_on():
    """Deleting this lets a mistyped profile render as an install with every feature off,
    which reads as a broken deployment rather than as a broken argument, and sends whoever is
    on call looking at the wrong thing.

    The install screen is the one of the three that has to check for itself: it puts the
    profile in front of a reader and calls nothing that would refuse an unknown one, so
    without its own check the screen becomes the thing confirming the typo."""
    with pytest.raises(WiringError):
        features_of("liet")

    with pytest.raises(WiringError):
        memory_capacity("liet")

    with pytest.raises(WiringError):
        install_facts(profile="liet", manifest=None, revisions=a_chain("0001"), env=NOTHING_SET)


# -------------------------------------------------------------- capacity (M27.6.4)
def a_compose_file(name: str, mib: int) -> dict[str, dict[str, object]]:
    return {
        "one.yml": {
            "services": {
                name: {"deploy": {"resources": {"limits": {"memory": f"{mib}M"}}}},
            }
        }
    }


def test_the_capacity_screen_does_not_report_the_declared_figure_as_the_deployed_one():
    """Deleting this lets a deployed figure be defaulted to the declared one, so two numbers
    agree by construction. Agreement between them is exactly what somebody opens this screen
    to check, and a copy would tell them what they were hoping to hear."""
    found = memory_capacity("full")

    assert found.deployed_mib is None
    assert found.declared_mib == wave_two_mib("full")
    assert found.host_total_mib == HOST_TOTAL_MIB


def test_the_declared_and_deployed_figures_are_two_independent_numbers():
    """Deleting this leaves the deployed figure untested, so nothing would notice it being
    computed from the component register rather than from the compose files, which is the
    disagreement the screen exists to show."""
    files = a_compose_file("something-nobody-budgeted", 640)

    found = memory_capacity("full", files)

    assert found.deployed_mib == deployment_mib(files)
    assert found.deployed_mib != found.declared_mib
    assert found.unbudgeted


def test_a_profile_over_its_memory_budget_is_reported_in_the_arithmetics_own_words():
    """Deleting this lets the console reword a budget finding, which puts the arithmetic's
    conclusion in two places and leaves the second to drift."""
    assert memory_capacity("full").breaches == budget_breaches("full")
    assert memory_capacity("full").breaches
    assert memory_capacity("lite").breaches == ()


def test_the_capacity_screen_reads_the_connection_arithmetic_rather_than_repeating_it():
    """Deleting this lets the console compute headroom itself, which is a second answer to
    how close this deployment is to running out of connections, and the optimistic copy is
    the one somebody quotes."""
    found = connection_capacity()

    assert [one.database for one in found] == [one.name for one in DATABASES]
    for row, declared in zip(found, DATABASES, strict=True):
        assert row == ConnectionCapacity(
            database=declared.name,
            admissible=declared.admissible(),
            demand=demand_on(declared.name),
            headroom=headroom_on(declared.name),
        )


def test_no_capacity_row_says_how_much_was_withheld():
    """Deleting this lets a total or a hidden count onto an install row. These screens are
    about the machine rather than about people, and that is precisely why nobody would think
    to look."""
    for record in (MemoryCapacity, ConnectionCapacity, Fact, MigrationLevel, ThrottleRow):
        assert not {one.name for one in fields(record)} & {"total", "hidden", "of_total"}


# ------------------------------------------------- rate limits and throttling (M27.6.3)
def a_limit(subject: str, *, scope: LimitScope = LimitScope.PRINCIPAL, cap: int = 2) -> Limit:
    return Limit(scope=scope, subject=subject, period="minute", limit=cap, window_seconds=60.0)


def at_its_ceiling(one: Limit) -> LimiterState:
    """A window with exactly as many hits in it as the limit allows."""
    state = LimiterState()
    for _ in range(one.limit):
        state = state.record(NOW, [one])
    return state


def test_a_ceiling_that_is_not_refusing_is_not_on_the_throttling_list():
    """Deleting this puts every configured limit on a screen headed what is being throttled,
    which is a list of ceilings rather than of anything happening now, and an operator reads
    it as an incident."""
    quiet = a_limit(READER)

    assert throttled_now([quiet], LimiterState(), holding(LIMIT_READ), now=NOW) == ()


def test_a_ceiling_that_is_refusing_is_on_the_list_with_the_wait_it_imposes():
    """Deleting this leaves a filter satisfied by an empty screen, which reports nothing
    whatever is being refused and passes every test that only checks what it hides."""
    busy = a_limit(READER)

    found = throttled_now([busy], at_its_ceiling(busy), holding(LIMIT_READ), now=NOW)

    assert len(found) == 1
    assert found[0].subject == READER
    assert found[0].limit == busy.limit
    assert found[0].retry_after_seconds > 0


def test_a_throttled_subject_outside_the_readers_reach_is_absent():
    """Deleting this turns the throttling list into a directory of who is busy, with a number
    beside each name. This is the one screen in the install group whose rows are about people
    rather than about the machine."""
    mine = a_limit(READER)
    theirs = a_limit("u_colleague")
    state = at_its_ceiling(mine)
    for _ in range(theirs.limit):
        state = state.record(NOW, [theirs])
    narrow = holding(
        LIMIT_READ, scope=Scope(clauses=(Clause(field="subject", op=Op.EQ, value=READER),))
    )

    found = throttled_now([mine, theirs], state, narrow, now=NOW)

    assert [one.subject for one in found] == [READER]
    assert "u_colleague" not in repr(found)


def test_a_reader_with_no_rate_limit_grant_is_shown_no_throttling_at_all():
    """Deleting this shows the throttling list to anybody who can reach the address, which
    is the same disclosure with the menu bypassed."""
    busy = a_limit(READER)

    assert throttled_now([busy], at_its_ceiling(busy), holding(), now=NOW) == ()


def test_a_throttle_row_carries_no_count_of_refused_requests():
    """Deleting this puts a refusal count beside somebody's name, which is a number about
    their afternoon on a screen about the machine."""
    assert {one.name for one in fields(ThrottleRow)} == {
        "scope",
        "subject",
        "limit",
        "retry_after_seconds",
    }


# ------------------------------------------ the screen that is not built (the finding)
def test_nothing_in_this_repository_restores_anything():
    """**This test is the finding.** The backup and recovery screen asks for the last
    verified restore, and no function or class in `src/brain` restores anything: there is a
    bucket declaration, a lifecycle rule, a retention number derived from it and a guard that
    refuses an install step naming somebody else's dump. A panel built on those would show a
    reassurance nobody measured, to the one reader who acts on it.

    Deleting this loses the record that the leaf was examined rather than missed. It fails on
    the day a restore verifier lands, which is the day the screen should be written."""
    found: list[str] = []
    for path in sorted(Path("src/brain").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend(
            f"{path.as_posix()}::{node.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and "restore" in node.name.lower()
        )

    assert found == []


def test_the_recovery_screen_says_what_would_have_to_exist_before_it_is_built():
    """Deleting this leaves the decision as a sentence in a commit message nobody re-reads,
    and the next person concludes the screen was forgotten. Four findings rather than one
    summary, so the day two of them exist the list gets shorter and says which two."""
    found = recovery_gaps()

    assert len(found) == len(RECOVERY_NEEDS) == 4
    assert any("restores the newest backup" in one for one in found)
    assert all("nothing in this repository does it" in one for one in found)


# ------------------------------------------------------------------ module properties
def test_nothing_in_this_module_intersects_two_entitlement_sets():
    """Deleting this lets a copy of the platform's central rule land on an install screen.
    The console's routes into it are `reads.audience` and `workspace_capabilities.run_reach`,
    and a third would be the one nobody reviews because these screens look like plumbing."""
    source = Path("src/brain/console/installation.py").read_text(encoding="utf-8")

    assert intersections_in(source) == ()
