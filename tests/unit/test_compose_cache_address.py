"""Every process of ours that is given the database is given the cache, and the same cache.

**Found on the owner's install on 2026-09-28.** The acceptance suite, which the worker runs once
per deploy, reported its rate-limit check "not run: this install names no cache". The same
suite run by hand inside the application's container passed. The application was given
`VALKEY_URL` in `docker-compose.yml`, and neither worker was given it in its own file, so
everything the worker keeps in the cache was off on every install built from these files:
the denial digest refused every run for want of somewhere to keep an alert, and the limit
check reported itself not run. Neither is an error anybody reads.

**The rule is about a process and not about a file,** and it is judged on each composition
the product runs as well as on each file alone. A worker's file declares no `cache`, because
the cache belongs to the base file every profile composes first, so a rule asked of the
worker's file on its own is never asked. The compositions are the ones
`test_compose_networks.compositions` lists, which a second test there holds to every file.

**"Ours" is the application's image,** the same reading `test_compose_networks.OURS` makes.
The trace ledger's two services are given a `DATABASE_URL` too, for their own database, and
keep their own cache; they are not this product's code and the rule has nothing to say to them.

**The same address, not only an address.** The digest keeps its alerts where the console reads
them, so a worker pointed at a different cache would raise alerts nobody is shown, which is
the same silence arrived at another way.

**What this does not see.** It reads the files, not a deployment panel's stored copy of them.
An install whose panel keeps its own compose file keeps the missing line until somebody pastes
the change in, which is `docs/install/coolify.md`, Updating.

Task ids: none. This is a finding on an install rather than a leaf; the commit that adds it
carries `Found-on: staging`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from brain.deployment.app_environment import environment_of
from brain.deployment.requirements import files_for
from tests.unit.test_compose_networks import OURS, compositions, load

REPO = Path(__file__).resolve().parents[2]

#: The service the base files declare the cache as, and the application that names it.
CACHE: Final = "cache"
APPLICATION: Final = "app"
CACHE_ADDRESS: Final = "VALKEY_URL"
DATABASE_ADDRESS: Final = "DATABASE_URL"


def cases() -> dict[str, tuple[str, ...]]:
    """Every compose file on its own, and every composition the product runs."""
    found: dict[str, tuple[str, ...]] = {
        path.name: (path.name,) for path in sorted(REPO.glob("docker-compose*.yml"))
    }
    found.update(compositions())
    return found


def ours_with_a_database(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Every service running the application's image and given a database, with its merged
    environment, in a composition that declares the cache. Empty when it declares none.

    Merged as Compose merges `-f` files: the later file's image wins, and environments are
    joined key by key with the later file winning, so an overlay that rewrites one address
    keeps every other variable the base file gave.
    """
    images: dict[str, str] = {}
    environments: dict[str, dict[str, str]] = {}
    declared: set[str] = set()
    for document in documents.values():
        for service, body in (document.get("services") or {}).items():
            declared.add(str(service))
            if isinstance(body, Mapping) and body.get("image"):
                images[str(service)] = str(body["image"])
            environments.setdefault(str(service), {}).update(
                environment_of(document, str(service)) or {}
            )
    if CACHE not in declared:
        return {}
    return {
        service: environment
        for service, environment in environments.items()
        if OURS.match(images.get(service, "")) and environment.get(DATABASE_ADDRESS)
    }


def cache_address_gaps(documents: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    """Every process of ours given a database and not the cache the application is given."""
    processes = ours_with_a_database(documents)
    expected = processes.get(APPLICATION, {}).get(CACHE_ADDRESS, "")
    gaps = []
    for service, environment in sorted(processes.items()):
        address = environment.get(CACHE_ADDRESS, "")
        if not address:
            gaps.append(f"{service} is given {DATABASE_ADDRESS} and no {CACHE_ADDRESS}")
        elif expected and address != expected:
            gaps.append(f"{service} names the cache {address!r} and {APPLICATION} {expected!r}")
    return tuple(gaps)


def test_every_process_of_ours_given_a_database_is_given_the_cache_the_application_is() -> None:
    """**The property the 2026-09-28 finding broke.** Read from the parsed files for every file
    alone and every composition, so a new overlay or profile is checked the day it is named.

    Delete this and the next process that runs the application's image, or the next overlay
    that rewrites a worker's environment, can start with no cache address, and everything it
    keeps there is skipped with no error: the finding it was written after went unnoticed until
    an acceptance check happened to name it."""
    found = {
        name: gaps
        for name, files in cases().items()
        if (gaps := cache_address_gaps({one: load(one) for one in files}))
    }
    assert found == {}, found


def test_both_workers_are_among_the_processes_the_rule_reads() -> None:
    """The rule is only as good as its reading of the files, and a reading that found nobody
    would pass for every file there is. So the two workers, which are what the finding was
    about, have to be read as processes of ours with a database wherever they run, beside the
    application.

    Delete this and a change to how the image is recognised, or to how an environment is
    merged across files, turns the property above into a check of nothing that stays green."""
    for profile in ("standard", "full"):
        documents = {one: load(one) for one in files_for(profile)}
        assert {APPLICATION, "brain-worker", "brain-parse-worker"} <= set(
            ours_with_a_database(documents)
        ), profile


def test_a_worker_with_no_cache_address_or_another_cache_is_reported_and_nothing_else() -> None:
    """The shape the install had, built as a base file and a worker's overlay, is reported,
    and so is a worker pointed at a cache the application does not use. A service that is not
    ours, and a composition with no cache at all, are not.

    Delete this and the reporting half of the rule is untested against the one layout that
    actually shipped wrong: a cache declared in one file and the worker in another."""
    image = "${APP_IMAGE:?set APP_IMAGE}"
    base = {
        "services": {
            APPLICATION: {
                "image": image,
                "environment": {DATABASE_ADDRESS: "postgresql://db", CACHE_ADDRESS: "redis://c/0"},
            },
            CACHE: {"image": "valkey/valkey:8-alpine"},
            "ledger": {"image": "langfuse/langfuse:3", "environment": [f"{DATABASE_ADDRESS}=x"]},
        }
    }
    missing = {
        "services": {"brain-worker": {"image": image, "environment": {DATABASE_ADDRESS: "x"}}}
    }
    other = {
        "services": {
            "brain-worker": {
                "image": image,
                "environment": {DATABASE_ADDRESS: "x", CACHE_ADDRESS: "redis://elsewhere/0"},
            }
        }
    }
    matching = {
        "services": {
            "brain-worker": {
                "image": image,
                "environment": {DATABASE_ADDRESS: "x", CACHE_ADDRESS: "redis://c/0"},
            }
        }
    }

    assert cache_address_gaps({"base": base, "worker": missing}) == (
        f"brain-worker is given {DATABASE_ADDRESS} and no {CACHE_ADDRESS}",
    )
    assert cache_address_gaps({"base": base, "worker": other}) == (
        f"brain-worker names the cache 'redis://elsewhere/0' and {APPLICATION} 'redis://c/0'",
    )
    assert cache_address_gaps({"base": base, "worker": matching}) == ()
    assert cache_address_gaps({"worker": missing}) == ()
