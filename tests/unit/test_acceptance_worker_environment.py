"""The worker that runs the acceptance checks is given every installation value a check reads.

**Found while scoping the Wave 2 acceptance checks on 2026-09-29.** The skill import check reads
`INSTALL_ACCEPTANCE_SKILL_SOURCE`, and runs on the worker's schedule after each deploy. Only the
application was given that value in the compose files, so on every install the worker read the
declared default, `unset`, and recorded the import as not run whatever the install had named. It is
the shape `tests/unit/test_compose_cache_address.py` records for the cache on 2026-09-28: a value
the application is given and the process running the check is not, which nothing reports because
"not run" is a correct answer to the question the worker was able to ask.

**The rule is about what a check reads, not about one variable.** The values are the installation
settings `brain.console.configuration.READ_BY` names an acceptance check module as reading, so a
check that starts reading another is held to it the day `READ_BY` says so. They are judged on every
composition the product runs in which the scheduling worker is one of our processes, and the worker
must be given each with the application's own expression, so the two read one value.

**And the staff sync's accounts step, since the same day.** It runs in the same worker and reads
the install's sign-in issuer to know which realm to manage, and only the application was given it,
so every run would have said the issuer was unset. A setting the screen saves in `ops.setting`
reaches the worker from the database and is left out: `EDITABLE_SETTINGS` is that list.

**What this does not see.** A deployment panel's stored copy of the files keeps the missing line
until somebody pastes the change in (`docs/install/coolify.md`, Updating).

Task ids: none. This is a finding about the acceptance run's reach rather than a leaf.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from brain.console.configuration import EDITABLE_SETTINGS, READ_BY
from brain.ops.acceptance import check_modules
from tests.unit.test_compose_cache_address import APPLICATION, ours_with_a_database
from tests.unit.test_compose_networks import compositions, load

#: The one worker that ticks the schedule, and so the one that runs the acceptance checks.
SCHEDULING_WORKER: Final = "brain-worker"


#: The other runs the scheduling worker makes that read an installation value from its environment.
WORKER_RUNS: Final = ("brain.ops.staff_accounts_run",)


def read_by_a_check() -> tuple[str, ...]:
    """Every installation setting an acceptance check module is named as reading."""
    return tuple(
        sorted(name for name, readers in READ_BY.items() if set(readers) & set(check_modules()))
    )


def read_in_the_worker() -> tuple[str, ...]:
    """Every setting a check or another worker run reads, less those the worker reads saved."""
    runs = set(check_modules()) | set(WORKER_RUNS)
    return tuple(
        sorted(
            name
            for name, readers in READ_BY.items()
            if set(readers) & runs and name not in EDITABLE_SETTINGS
        )
    )


def worker_gaps(documents: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    """Every setting a check reads that the scheduling worker is not given as the application is."""
    processes = ours_with_a_database(documents)
    worker = processes.get(SCHEDULING_WORKER)
    if worker is None:
        return ()
    application = processes.get(APPLICATION, {})
    return tuple(
        f"{SCHEDULING_WORKER} is not given {name} as {APPLICATION} is"
        for name in read_in_the_worker()
        if name not in worker or worker[name] != application.get(name, worker[name])
    )


def test_the_scheduling_worker_is_given_every_setting_an_acceptance_check_reads() -> None:
    """**The property the finding broke**, over every composition the product runs. Delete this
    and a check reading an installation value can be run by a worker that was never given it,
    and report itself not run on every install for a reason nobody reads."""
    found = {
        name: gaps
        for name, files in compositions().items()
        if (gaps := worker_gaps({one: load(one) for one in files}))
    }
    assert found == {}, found


def test_the_rule_reads_the_skill_source_and_finds_the_worker_where_it_runs() -> None:
    """The rule is only as good as its reading: the skill source is among the values a check reads,
    and the standard profile's worker is found and given it. Delete this and a reading that found
    no setting, or no worker, passes the property above for every file there is."""
    assert "INSTALL_ACCEPTANCE_SKILL_SOURCE" in read_by_a_check()
    standard = compositions()["standard"]
    processes = ours_with_a_database({one: load(one) for one in standard})
    assert "INSTALL_ACCEPTANCE_SKILL_SOURCE" in processes[SCHEDULING_WORKER]


def test_a_worker_left_without_the_setting_is_reported() -> None:
    """The reporting half, against the layout that shipped: the application given the value and
    the worker not. Delete this and the property can pass by never reporting anything."""
    from brain.ops.compose import FULL_PROFILE_FILE

    document = load(FULL_PROFILE_FILE)
    worker = document["services"][SCHEDULING_WORKER]["environment"]
    assert worker_gaps({FULL_PROFILE_FILE: document}) == ()
    worker.pop("INSTALL_ACCEPTANCE_SKILL_SOURCE")
    assert worker_gaps({FULL_PROFILE_FILE: document}) == (
        f"{SCHEDULING_WORKER} is not given INSTALL_ACCEPTANCE_SKILL_SOURCE as {APPLICATION} is",
    )


def test_the_staff_accounts_run_is_given_the_sign_in_issuer_and_not_what_the_screen_saves() -> None:
    """The accounts step's reading: the issuer is among the values the worker must be given, and the
    employment types, which the Settings screen saves, are not. Delete this and the worker can lose
    the issuer with the property above still green because it stopped asking, or be required to
    carry a value the screen owns."""
    assert "INSTALL_OIDC_ISSUER" in read_in_the_worker()
    assert "INSTALL_ACCOUNT_EMPLOYMENT_TYPES" not in read_in_the_worker()
    assert set(read_by_a_check()) <= set(read_in_the_worker())
