"""What stops the `full` profile being one compose file, held to the files themselves.

M0.4.2 asks for `docker-compose.full.yml`, and it is not written. Every test here is one of
the four reasons, asserted against the parsed compose files rather than against a paragraph,
so the day a reason stops being true a test fails and says which one.

The pinned sets are deliberate and they are the shape `test_connections.py` uses for the
clients that go round the pooler: a check that tolerates four findings tolerates five, and the
fifth is the one nobody reads about. That set was four when this was written and has been empty
since 2026-09-10, which is what an exact set buys over a count: the check went on working
through the fix rather than being deleted with it.

These tests are expected to fail when somebody fixes a finding, and that failure is the
notification.

Read with `yaml.safe_load` rather than grepped, in both directions: a bind mount inside a
comment is not a mount, and a service whose limit is written in a comment has no limit.

Task ids: none
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops.compose import (
    A_NAME_WITH_NO_BODY_IS_A_REFERENCE_AND_NOT_A_SECOND_DECLARATION,
    A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE,
    BASELINE_FILE,
    FULL_PROFILE_FILES,
    THE_FULL_PROFILE_IS_NOT_ONE_FILE_YET,
    TWO_DECLARATIONS_OF_ONE_SERVICE_ARE_SETTLED_BY_ARGUMENT_ORDER,
    ComposeError,
    components_with_no_service,
    databases_needed,
    databases_nothing_creates,
    declared_services,
    deployment_mib,
    described_services,
    host_mib_for,
    mounted_paths,
    relative_bind_mounts,
    services_declared_differently,
    unbudgeted_mib,
    unbudgeted_services,
    undeployed_mib,
)
from brain.ops.wiring import (
    HOST_RESERVE_MIB,
    HOST_TOTAL_MIB,
    PRODUCTION_BASELINE_MIB,
    components_for,
    wave_two_mib,
)

REPO = Path(__file__).resolve().parents[2]


def profile_files() -> dict[str, Any]:
    """The eight files a `full` install composes, parsed.

    Named by the module rather than globbed, because two of the compose files in this
    repository are deliberately not members: `docker-compose.lite.yml` is the same four
    services as the baseline and `docker-compose.staging.yml` is a different deployment of
    them, so a glob would report both as services declared twice and say nothing true.
    """
    return {
        name: yaml.safe_load((REPO / name).read_text(encoding="utf-8"))
        for name in FULL_PROFILE_FILES
    }


# --- the four reasons ------------------------------------------------------------------


def test_every_file_the_full_profile_names_exists_and_parses() -> None:
    """The list is a declaration, and a declaration naming a file nobody wrote would make
    every other test here pass over a smaller set than the profile actually runs.

    Delete this and a renamed compose file turns four findings into three, in the direction
    that reads as progress."""
    for name in FULL_PROFILE_FILES:
        assert (REPO / name).is_file(), f"{name} is named by FULL_PROFILE_FILES and is missing"

    files = profile_files()
    assert BASELINE_FILE in files
    assert len(declared_services(files)) == 19


def test_one_component_of_the_full_profile_has_no_service_anywhere() -> None:
    """**The reason `docker-compose.full.yml` cannot be written today.** An aggregate file is
    the profile in one place, and a component that is budgeted with nothing to copy leaves a
    hole that can only be filled by choosing an image, a port and a readiness probe for a
    container nobody here has run.

    Pinned as an exact set rather than as "not empty", so that writing the missing service
    fails this test and says the leaf is now available.

    Delete this and the gap becomes invisible: the profile's arithmetic keeps spending 512
    MiB on a container no deployment can start."""
    files = profile_files()
    found = components_with_no_service("full", files)

    assert {line.split("'")[1] for line in found} == {"presidio-analyzer"}, found
    assert "512 MiB" in found[0], "the finding exists to say what the hole costs"

    # The positive half, and it is what makes the assertion above mean something: every other
    # component of the profile does have a service, so the check is reading the files rather
    # than reporting whatever it cannot find.
    declared = set(declared_services(files))
    missing = {one.name for one in components_for("full")} - declared
    assert len(missing) == 1
    assert declared >= {one.name for one in components_for("full")} - missing


def test_the_object_store_is_described_once_and_named_twice() -> None:
    """**The second of the four reasons, closed on 2026-09-10 by item 43 of needs-rupash.**

    `docker-compose.langfuse.yml` names `seaweedfs` on purpose, so that a project composing it
    beside the object store gets one container rather than two. Until that decision it carried
    a second body as well, missing the `-s3.config` flag and the identities file the object
    store's copy mounts, so which of the two ran was decided by the order of the `-f` flags and
    one of the orders started an S3 gateway with no access control at all.

    It now names the service with nothing under it, which contributes nothing to the merge and
    therefore cannot win in any order. Both halves are asserted, because the empty declaration
    is the fix and its absence would look identical to a file that had simply dropped the
    dependency: the name has to still be there, and the body has to still be empty.

    Delete this and the second body comes back, and neither file is wrong on its own, which is
    why nothing else in this repository would notice."""
    files = profile_files()

    assert services_declared_differently(files) == ()
    assert "seaweedfs" in files["docker-compose.langfuse.yml"]["services"]
    assert not files["docker-compose.langfuse.yml"]["services"]["seaweedfs"]
    assert declared_services(files)["seaweedfs"] == (
        "docker-compose.langfuse.yml",
        "docker-compose.objectstore.yml",
    )
    assert described_services(files)["seaweedfs"] == ("docker-compose.objectstore.yml",)
    assert "order" in TWO_DECLARATIONS_OF_ONE_SERVICE_ARE_SETTLED_BY_ARGUMENT_ORDER
    assert "merge" in A_NAME_WITH_NO_BODY_IS_A_REFERENCE_AND_NOT_A_SECOND_DECLARATION


def test_a_second_body_for_one_service_would_still_be_reported() -> None:
    """The check has to keep working now that the tree is clean, and a check that can only be
    run against a healthy declaration cannot be shown to fail.

    Asserted on the keys that differ rather than on the count, because the count stays at one
    while the disagreement moves to something else.

    Delete this and `services_declared_differently` could return `()` unconditionally, which
    is the shape the tree would agree with."""
    described = {"image": "x", "command": ["a"]}
    found = services_declared_differently(
        {
            "a.yml": {"services": {"shared": described}},
            "b.yml": {"services": {"shared": dict(described, command=["b"])}},
        }
    )

    assert len(found) == 1, found
    assert found[0].startswith("'shared' is declared in"), found
    assert "'command'" in found[0], found


def test_two_identical_declarations_of_one_service_are_not_a_finding() -> None:
    """The positive case, and it is load-bearing rather than symmetry. Sharing a service
    between two files is the arrangement the trace ledger deliberately relies on, so a check
    that reported every overlap would refuse a design this repository chose on purpose and
    would be switched off.

    Delete this and the check can start reporting any service named twice, which turns the
    assertion above into noise on the day it would otherwise have said something."""
    body = {"image": "x", "deploy": {"resources": {"limits": {"memory": "64M"}}}}

    same = {"a.yml": {"services": {"shared": body}}, "b.yml": {"services": {"shared": body}}}
    assert services_declared_differently(same) == ()

    changed = dict(body, image="y")
    differing = {
        "a.yml": {"services": {"shared": body}},
        "b.yml": {"services": {"shared": changed}},
    }
    assert len(services_declared_differently(differing)) == 1

    # And a name with no body is not a declaration at all, in either spelling of nothing. It
    # adds nothing to the merge, so there is no order in which it could win, which is what
    # makes it a reference rather than the second copy this check exists to find.
    for empty in ({}, None):  # type: dict[str, Any] | None
        named: dict[str, Any] = {
            "a.yml": {"services": {"shared": body}},
            "b.yml": {"services": {"shared": empty}},
        }
        assert services_declared_differently(named) == ()
        assert described_services(named) == {"shared": ("a.yml",)}
        assert declared_services(named) == {"shared": ("a.yml", "b.yml")}


def test_no_mount_is_left_that_a_stored_compose_would_resolve_to_nothing() -> None:
    """**The third of the four reasons, closed on 2026-09-10 by item 43 of needs-rupash.**

    A file deployed as a stored copy has no repository beside it, so `./ops/...` named a path
    that did not exist, and Docker creates an empty directory there and starts the container
    rather than refusing. Three of the four carried the thing that makes their container safe
    or usable: ClickHouse's memory ceiling, the automation sandbox's egress allowlist and the
    object store's S3 credentials. A container missing any of them looks exactly like one that
    has them.

    All four now name an absolute path under the install's settings directory, which is what
    makes what a container reads independent of where its compose file was stored. The count
    is asserted as well as the emptiness, because a check that found nothing because it was
    looking at nothing would produce the same tuple.

    Delete this and the next `./ops/...` somebody adds is a container that starts, reports
    healthy, and is missing its configuration."""
    files = profile_files()

    assert relative_bind_mounts(files) == ()
    assert len(mounted_paths(files)) == 4, mounted_paths(files)
    assert all(source.startswith("/opt/brain/") for _, _, source in mounted_paths(files))
    assert "empty directory" in A_RELATIVE_BIND_MOUNT_IS_EMPTY_IN_A_STORED_COMPOSE


def test_a_named_volume_and_an_absolute_path_are_not_reported_as_relative_mounts() -> None:
    """The positive case. Every service in the profile mounts something, and a check that
    reported all of them would name nineteen containers and be read as noise.

    Delete this and `relative_bind_mounts` can start reporting every volume entry, which makes
    the pinned set above fail for reasons that have nothing to do with a stored compose."""
    files = {
        "a.yml": {
            "services": {
                "one": {"volumes": ["brain-db:/var/lib/postgresql", "/etc/hosts:/etc/hosts:ro"]},
                "two": {"volumes": [{"type": "bind", "source": "/srv/data", "target": "/data"}]},
                "three": {"volumes": [{"type": "bind", "source": "./ops/x.conf", "target": "/x"}]},
            }
        }
    }

    found = relative_bind_mounts(files)
    assert len(found) == 1, found
    assert "'three'" in found[0], "the long spelling of a bind mount is a bind mount"

    # `mounted_paths` is the other half of the same walk and answers the wider question: a
    # named volume is docker's to make and cannot be absent, and everything else is a path
    # somebody has to create. Both absolute mounts are here and the volume is not.
    assert {source for _, _, source in mounted_paths(files)} == {
        "/etc/hosts",
        "/srv/data",
        "./ops/x.conf",
    }


def test_the_trace_ledger_connects_to_a_database_nothing_in_the_profile_creates() -> None:
    """**The reason the profile could not come up even on a host large enough for it, and it
    is still true of these documents.** Langfuse's two services point at `db` and ask for a
    database called `langfuse`. The `db` service creates `brain` and nothing else:
    `POSTGRES_DB` creates exactly one database on an empty data directory, and there is no
    second one anywhere in these eight files.

    That is what an aggregate compose file would inherit, which is why the default answer here
    stays the unforgiving one. What changed on 2026-09-10 is the deployment rather than the
    documents: a step of the install creates it, and `created_by_the_install` is how the
    module that owns the plan asks the narrower question. See
    `test_deployment_installer.py::test_the_install_creates_exactly_the_databases_the_files_ask_for`.

    Read out of the connection strings rather than out of a note, which is the direction
    `undeclared_clients` reads in and for the same reason: a stack nobody has started is
    described by what it declares.

    Delete this and the aggregate gets written and deployed, and the first symptom is two
    containers restarting against a database that was never anybody's job to create."""
    files = profile_files()
    found = databases_nothing_creates(files)

    assert {line.split("'")[1] for line in found} == {"langfuse-web", "langfuse-worker"}, found
    assert all("'langfuse'" in line and "'db'" in line for line in found), found
    assert databases_needed(files) == (("db", "langfuse"),)


def test_a_database_the_install_creates_is_no_longer_reported_and_only_that_one() -> None:
    """The parameter is the one thing a compose file cannot say about itself, so its edges are
    asserted rather than assumed. Excusing the pair silences the finding; excusing the same
    database on a different server does not, and that is the half that matters, because a
    constant naming only the database would have excused the wrong thing.

    Delete this and `created_by_the_install` can be widened to a database name, and a service
    pointed at somebody else's server passes a check that never looked at the server."""
    files = profile_files()

    assert databases_nothing_creates(files, created_by_the_install=(("db", "langfuse"),)) == ()
    assert len(databases_nothing_creates(files, created_by_the_install=(("other", "langfuse"),)))
    assert len(databases_nothing_creates(files, created_by_the_install=(("db", "other"),)))


def test_a_service_pointed_at_a_database_its_server_creates_is_not_reported() -> None:
    """The positive case, and there are three shapes of it in these files that all have to
    come back clean: the application through the pooler, the worker straight to `db`, and
    Keycloak's JDBC URL at its own server.

    The JDBC one is the assertion with teeth. `urlsplit` reads `jdbc:` as the scheme and
    everything after it as an opaque path, so a JDBC URL has no hostname at all unless the
    prefix is stripped, and a check that never sees Keycloak would report nothing and look
    correct.

    Delete this and the check can be narrowed until it only ever sees Langfuse, which is the
    one it was written from."""
    found = databases_nothing_creates(profile_files())
    reported = {line.split("'")[1] for line in found}

    for service in ("app", "brain-worker", "brain-parse-worker", "keycloak"):
        assert service not in reported, f"{service} names a database its server creates"

    # Keycloak's is the JDBC case, asserted directly as well, because its absence above is
    # also what a check that could not parse the URL at all would produce.
    keycloak = yaml.safe_load((REPO / "docker-compose.keycloak.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    assert keycloak["keycloak"]["environment"]["KC_DB_URL"].startswith("jdbc:")
    assert keycloak["keycloak-db"]["environment"]["POSTGRES_DB"] == "keycloak"
    moved = {
        "a.yml": {
            "services": {
                "keycloak": {"environment": {"KC_DB_URL": "jdbc:postgresql://kc-db:5432/other"}},
                "kc-db": {"environment": {"POSTGRES_DB": "keycloak"}},
            }
        }
    }
    assert len(databases_nothing_creates(moved)) == 1, "the jdbc prefix has to be stripped"


def test_a_value_that_is_not_a_postgres_url_is_not_a_database() -> None:
    """A compose environment holds cache URLs, public addresses, model names, secrets with
    substitution markers in them and plain words. Anything this cannot read has to come back
    as nothing rather than as a finding or an exception.

    Delete this and a Redis URL beside a Postgres one turns into a database nobody created,
    and the pinned set above starts failing for reasons that are not about databases."""
    files = {
        "a.yml": {
            "services": {
                "one": {
                    "environment": {
                        "VALKEY_URL": "redis://cache:6379/0",
                        "PUBLIC": "https://example.invalid/path",
                        "WORD": "automation-db",
                        "BROKEN": "http://[::1:80/",
                        "NO_DATABASE": "postgresql://user@db:5432/",
                    }
                },
                "db": {"environment": {"POSTGRES_DB": "brain"}},
            }
        }
    }

    assert databases_nothing_creates(files) == ()


def test_an_environment_written_as_a_list_is_read_the_same_as_one_written_as_a_mapping() -> None:
    """Compose accepts both spellings and every file here uses the mapping, so the list branch
    is reached by no real data. A branch no data reaches has never been shown to work, and the
    day somebody writes one service the other way its connection strings stop being read at
    all: the check goes quiet rather than wrong, which is the direction nobody notices.

    Delete this and half of `_environment` can be removed with every other test green."""
    files = {
        "a.yml": {
            "services": {
                "one": {"environment": ["DATABASE_URL=postgresql://u:p@db:5432/other"]},
                "db": {"environment": ["POSTGRES_DB=brain"]},
            }
        }
    }

    found = databases_nothing_creates(files)
    assert len(found) == 1, found
    assert "'other'" in found[0] and "'brain'" in found[0]


# --- the arithmetic --------------------------------------------------------------------


def test_a_service_declared_twice_is_costed_at_the_larger_of_its_two_limits() -> None:
    """The two declarations of `seaweedfs` carry the same limit today, so the real data cannot
    tell the larger from the smaller and this is asserted on a pair that can.

    The larger is the honest figure because the flag order decides which declaration runs, so
    it is the one the host has to be able to honour. Taking the smaller would understate the
    profile by the difference, which is the affordable direction again.

    Delete this and the choice can be reversed without any test noticing, and the host
    requirement quietly becomes the best case rather than the one that has to hold."""
    files = {
        "a.yml": {
            "services": {"shared": {"deploy": {"resources": {"limits": {"memory": "256M"}}}}}
        },
        "b.yml": {
            "services": {"shared": {"deploy": {"resources": {"limits": {"memory": "512M"}}}}}
        },
    }

    assert deployment_mib(files) == 512


def test_the_deployment_and_the_budget_describe_the_same_host_once_both_gaps_are_named() -> None:
    """**The arithmetic a `docker-compose.full.yml` would have to state, and it does not
    balance until both gaps are on the table.**

    `brain.ops.wiring` sums components; the compose files reserve containers. The two disagree
    in both directions at once: 512 MiB is budgeted for a component with no service, and 576
    MiB is deployed by four containers no component budgets. Add each gap to the side that is
    missing it and the totals are equal, which is the only way to see that the budget and the
    deployment are describing one machine rather than two.

    Written as an identity rather than as two numbers, so that resizing any container fails
    here unless the other side moves with it.

    Delete this and the profile's memory figure can be quoted from either side, and the two
    answers differ by 1088 MiB with nothing saying which is right."""
    files = profile_files()

    assert deployment_mib(files) == 12096
    assert undeployed_mib("full", files) == 512
    assert unbudgeted_mib("full", files) == 576

    assert deployment_mib(files) + undeployed_mib("full", files) == (
        PRODUCTION_BASELINE_MIB + wave_two_mib("full") + unbudgeted_mib("full", files)
    )


def test_the_containers_no_budget_accounts_for_are_named_rather_than_only_counted() -> None:
    """Four containers are real memory on the host and are in no figure `brain.ops.wiring`
    produces: a realm importer, an object-store provisioner, the automation sandbox's own
    database and its egress proxy. Every one arrived beside a component and none is one.

    The baseline four are excluded because `PRODUCTION_BASELINE_MIB` already counts them, and
    that exclusion is asserted below rather than assumed: a check that reported `db` would be
    reporting the most carefully budgeted container in the repository.

    Delete this and a fifth sidecar joins the deployment with nothing naming it."""
    files = profile_files()
    found = unbudgeted_services("full", files)

    assert {line.split("'")[1] for line in found} == {
        "automation-db",
        "automation-egress",
        "keycloak-realm",
        "seaweedfs-init",
    }, found

    reported = {line.split("'")[1] for line in found}
    for service in ("app", "pgbouncer", "db", "cache"):
        assert service not in reported, "the baseline is budgeted by PRODUCTION_BASELINE_MIB"


def test_the_host_this_profile_needs_is_larger_than_the_whole_of_the_measured_machine() -> None:
    """**The honest answer to "why is there no full profile deployed", and it is not the same
    answer as the budget's.** `budget_breaches("full")` compares wave 2 against a cap measured
    on one machine, which is a fact about that machine and not about the product. This is the
    fact about the product: the profile needs 12864 MiB of reservations, and the machine the
    measurements were taken on has 11960 MiB in total, so it does not fit there with every
    neighbour removed and nothing left for the kernel.

    The positive half matters as much and is what makes the profile real rather than
    aspirational: a 16 GiB host runs it with room over, so this is a sizing requirement to
    write down rather than a design to abandon.

    Delete this and the requirement goes back to being a subtraction somebody does in their
    head, which is how "it does not fit our server" became "it cannot be built"."""
    files = profile_files()

    assert host_mib_for("full", files) == 12864
    assert host_mib_for("full", files) == (
        deployment_mib(files) + undeployed_mib("full", files) + HOST_RESERVE_MIB
    )
    assert host_mib_for("full", files) > HOST_TOTAL_MIB, (
        "the profile now fits the measured machine, so the sizing note and this test have "
        "stopped saying the same thing"
    )
    assert host_mib_for("full", files) <= 16 * 1024


def test_a_service_with_no_memory_limit_is_refused_rather_than_costed_at_nothing() -> None:
    """The failure that would matter here is in the affordable direction: eighteen of nineteen
    containers costed is a profile that looks like it fits by exactly the size of the one that
    was skipped.

    The same refusal `wiring.set_cost_mib` makes about a name nobody budgeted, and made here
    rather than reported because a total is a single number and there is nowhere in one to put
    a caveat.

    Delete this and an unlimited container makes the host requirement smaller."""
    files = {"a.yml": {"services": {"unlimited": {"image": "x"}}}}

    with pytest.raises(ComposeError, match="declares no memory limit"):
        deployment_mib(files)


def test_a_gigabyte_and_a_megabyte_are_read_as_the_same_unit() -> None:
    """Compose accepts both spellings and every file here uses `M` today, so the `G` branch is
    reached by no real data. A branch no data reaches is a branch that has never been shown to
    work, and the day somebody writes `2G` the profile silently costs two.

    Delete this and the requirement is understated by a factor of a thousand by one edit that
    looks tidier than what it replaced."""
    files = {
        "a.yml": {
            "services": {
                "big": {"deploy": {"resources": {"limits": {"memory": "1G"}}}},
                "small": {"deploy": {"resources": {"limits": {"memory": "1024M"}}}},
            }
        }
    }

    assert deployment_mib(files) == 2048


def test_the_written_reason_carries_the_figures_the_files_actually_produce() -> None:
    """A paragraph with numbers in it goes stale silently, which is what happened to
    `HOST_HEADROOM_MIB`: the justification stayed true while the figure it justified stopped
    being. The next person to ask why there is no full compose file will read the sentence
    rather than run the functions, so every number in it is compared against them.

    Delete this and the four reasons can each be fixed while the paragraph explaining them
    goes on describing the repository as it was."""
    files = profile_files()
    reason = THE_FULL_PROFILE_IS_NOT_ONE_FILE_YET

    assert f"{len(declared_services(files))} containers" in reason
    assert f"across {len(FULL_PROFILE_FILES)} compose files" in reason
    assert f"reserving {deployment_mib(files)} MiB" in reason
    assert f"{host_mib_for('full', files)} MiB to spare" in reason
    assert f"{len(relative_bind_mounts(files))} services take something" in reason
    assert f"the {len(databases_nothing_creates(files))} services connecting to a" in reason
    # The one clause with no number in it, because it is about one service either way. The
    # sentence claims it is described once, and that claim is the check rather than the count.
    assert "described once and named twice" in reason
    assert services_declared_differently(files) == ()


def test_a_document_with_no_services_block_is_read_as_empty_rather_than_refused() -> None:
    """A compose file may legitimately declare only networks or only volumes, and one under
    edit may declare nothing at all. Every function here takes the whole set, so one such file
    must not make the set unreadable.

    Delete this and adding an empty file to the profile turns four findings into a traceback,
    which reads as the checks being broken rather than the file being empty."""
    files = {"a.yml": {"networks": {"default": None}}, "b.yml": {}}

    assert declared_services(files) == {}
    assert deployment_mib(files) == 0
    assert relative_bind_mounts(files) == ()
    assert databases_nothing_creates(files) == ()


def test_a_services_block_that_is_not_a_mapping_is_refused_rather_than_skipped() -> None:
    """A YAML edit that leaves `services:` holding a list produces a document that parses and
    means nothing. Skipping it would drop every service in that file out of the union, which
    is the affordable direction again: a profile costed without one of its files.

    Delete this and a malformed file makes the deployment look smaller than it is."""
    with pytest.raises(ComposeError, match="not a mapping"):
        declared_services({"a.yml": {"services": ["app", "db"]}})
