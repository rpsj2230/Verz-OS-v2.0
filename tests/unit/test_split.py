"""The two-host split: which host runs what, what crosses between them, and that nothing else
changes (M36.1.4.1, M36.1.4.2).

The positive cases read the real profile files and the real overlays. Every refusal is built
from those same documents with one thing changed.

Task ids: M36.1.4.1, M36.1.4.2
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.requirements import COMPOSE_FILES_FOR, files_for
from brain.ops.split import (
    A_PORT_WITH_NO_ADDRESS_IS_PUBLISHED_ON_EVERY_INTERFACE,
    ADDRESS,
    ADDRESS_VARIABLE,
    BASE_OVERLAY,
    DATA_TIER,
    OBJECT_STORE_OVERLAY,
    PUBLISHED,
    THE_DATA_HOST_PUBLISHES_POOLERS_AND_NEVER_THE_DATABASE,
    THE_OVERLAY_CHANGES_ADDRESSES_AND_NOTHING_THE_IMAGE_READS,
    WORKERS_OVERLAY,
    address_refusals,
    application_change_gaps,
    host_services,
    main,
    overlays_for,
    published_port_gaps,
    split_gaps,
)

REPO = Path(__file__).resolve().parents[2]

#: The unspecified address, which is every interface, built rather than typed.
EVERY_INTERFACE = str(ipaddress.IPv4Address(0))


def load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((REPO / name).read_text(encoding="utf-8")) or {}
    return loaded


def profile(name: str) -> dict[str, Any]:
    return {one: load(one) for one in files_for(name)}


def overlays(name: str) -> dict[str, Any]:
    return {one: load(one) for one in overlays_for(files_for(name))}


# ====================================================================== the real overlays
@pytest.mark.parametrize("name", ["lite", "standard"])
def test_the_profiles_the_split_covers_have_nothing_left_naming_the_other_host(name: str) -> None:
    """The positive case, over what each profile actually composes. Delete this and every
    refusal below can pass against a check that refuses the real overlays too."""
    assert split_gaps(profile(name), overlays(name)) == ()


def test_the_full_profile_is_not_split_and_the_reason_is_computed() -> None:
    """The trace ledger connects straight to `db` and to the object store by service name, and no
    overlay rewrites it. Pinned as the exact set so the day an overlay covers it this fails and
    the docstring in `brain.ops.split` is corrected, rather than the gap closing unannounced.

    Delete this and the scaling guide can go on saying `full` is not covered after it is, or
    stop saying so while it still is not."""
    found = split_gaps(profile("full"), overlays("full"))

    named = {(line.split("'")[1], line.split("'")[2].split()[0]) for line in found}
    assert named == {
        ("langfuse-web", "DATABASE_URL"),
        ("langfuse-web", "LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT"),
        ("langfuse-worker", "DATABASE_URL"),
        ("langfuse-worker", "LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT"),
    }, found


def test_each_host_starts_its_own_tier_and_together_they_start_everything_once() -> None:
    """The service lists the guide tells an operator to pass. Delete this and a service can fall
    between the two hosts, or run on both, with the overlays themselves still correct."""
    for name in COMPOSE_FILES_FOR:
        files = profile(name)
        application = set(host_services(files, "application"))
        data = set(host_services(files, "data"))
        every = {service for doc in files.values() for service in (doc.get("services") or {})}

        assert application | data == every, name
        assert not application & data, name
        assert data <= DATA_TIER, name
        assert "app" in application and "db" in data, name

    assert host_services(profile("lite"), "data") == ("db", "pgbouncer")
    assert host_services(profile("lite"), "application") == ("app", "cache")


def test_an_unknown_host_is_refused_rather_than_answered_with_everything() -> None:
    """Delete this and a typo in the host name starts the whole profile on one machine."""
    with pytest.raises(ValueError, match="no host named"):
        host_services(profile("lite"), "database")


def test_the_overlays_a_profile_needs_follow_the_files_it_composes() -> None:
    """Delete this and `lite` can be handed the worker overlay, which gives compose a worker with
    no image, or `standard` can be split with its workers still pointed at `pgbouncer-session`."""
    assert overlays_for(files_for("lite")) == (BASE_OVERLAY,)
    assert overlays_for(files_for("standard")) == (
        BASE_OVERLAY,
        WORKERS_OVERLAY,
        OBJECT_STORE_OVERLAY,
    )


def test_the_published_ports_are_the_poolers_and_the_store_on_the_required_address() -> None:
    """Read off the files, against the table and the variable. Delete this and the ports in the
    overlays and the ports the guide tells somebody to allow can drift apart."""
    published = {
        service: [str(one) for one in body["ports"]]
        for name in (BASE_OVERLAY, WORKERS_OVERLAY, OBJECT_STORE_OVERLAY)
        for service, body in (load(name).get("services") or {}).items()
        if "ports" in body
    }

    assert set(published) == set(PUBLISHED)
    for service, (host, container) in PUBLISHED.items():
        assert published[service] == [f"{ADDRESS}:{host}:{container}"]
    assert "db" not in published
    assert ADDRESS.startswith("${" + ADDRESS_VARIABLE + ":?")


# ============================================================================ the refusals
def test_a_port_published_with_no_address_is_refused() -> None:
    """The one that publishes the database's pooler to the internet. Delete this and the address
    can be dropped from an entry, which compose accepts and binds on every interface."""
    documents = overlays("lite")
    documents[BASE_OVERLAY]["services"]["pgbouncer"]["ports"] = ["6432:5432"]

    found = published_port_gaps(documents)
    assert any(A_PORT_WITH_NO_ADDRESS_IS_PUBLISHED_ON_EVERY_INTERFACE in one for one in found)


@pytest.mark.parametrize(
    "entry",
    [
        "${BRAIN_DATA_HOST_ADDRESS}:6432:5432",
        "${BRAIN_DATA_HOST_ADDRESS:-0.0.0.0}:6432:5432",
        "${SOMETHING_ELSE:?set it}:6432:5432",
        "0.0.0.0:6432:5432",
    ],
)
def test_an_address_that_can_be_unset_or_is_not_the_split_variable_is_refused(entry: str) -> None:
    """A bare variable nobody set, a default, another variable and the unspecified address all
    publish more widely than the private link. Delete this and any of them passes as an address."""
    documents = overlays("lite")
    documents[BASE_OVERLAY]["services"]["pgbouncer"]["ports"] = [entry]

    assert published_port_gaps(documents), entry


def test_publishing_the_database_itself_is_refused() -> None:
    """Delete this and `db` can be published beside its pooler, which puts the superuser login
    on the private network."""
    documents = overlays("lite")
    documents[BASE_OVERLAY]["services"]["db"] = {"ports": [f"{ADDRESS}:5432:5432"]}

    found = published_port_gaps(documents)
    assert any(THE_DATA_HOST_PUBLISHES_POOLERS_AND_NEVER_THE_DATABASE in one for one in found)


def test_a_pooler_published_on_the_other_poolers_port_is_refused() -> None:
    """Across two hosts the difference between the session and the transaction pooler is a port
    number. Delete this and the two can be swapped in the overlay while the workers still point
    at the old numbers."""
    documents = overlays("standard")
    documents[WORKERS_OVERLAY]["services"]["pgbouncer-session"]["ports"] = [f"{ADDRESS}:6432:5432"]

    assert any("expects 6433:5432" in one for one in published_port_gaps(documents))


def test_a_queue_sent_to_the_transaction_poolers_port_is_refused() -> None:
    """The failure with no error: a LISTEN across the split lands on transaction pooling. Delete
    this and 6433 can become 6432 in one worker's URL."""
    documents = overlays("standard")
    environment = documents[WORKERS_OVERLAY]["services"]["brain-worker"]["environment"]
    environment["QUEUE_URL"] = environment["QUEUE_URL"].replace(":6433/", ":6432/")

    found = split_gaps(profile("standard"), documents)
    assert any("'brain-worker' QUEUE_URL used to reach 'pgbouncer-session'" in one for one in found)


def test_an_application_service_still_naming_a_data_host_service_is_refused() -> None:
    """Delete this and the workers' overlay can be left out of a `standard` split, which leaves
    both workers resolving `pgbouncer-session` on a host that does not run it."""
    documents = overlays("standard")
    del documents[WORKERS_OVERLAY]

    found = split_gaps(profile("standard"), documents)
    assert any("still names ['pgbouncer-session']" in one for one in found), found
    assert any("needs the overlays" in one for one in found), found


def test_a_rewritten_address_that_changes_the_database_is_refused() -> None:
    """Moving host is the split; moving database is a different install. Delete this and a URL
    can point at the right pooler and the wrong database."""
    documents = overlays("lite")
    environment = documents[BASE_OVERLAY]["services"]["app"]["environment"]
    environment["DATABASE_URL"] = environment["DATABASE_URL"].replace("/brain", "/other")

    assert any("changed database" in one for one in split_gaps(profile("lite"), documents))


@pytest.mark.parametrize(
    ("service", "key", "value"),
    [
        ("app", "image", "somebody/else:1"),
        ("app", "command", ["python", "-m", "something"]),
        ("pgbouncer", "environment", {"POOL_MODE": "session"}),
    ],
)
def test_an_overlay_that_changes_anything_but_an_address_is_an_application_change(
    service: str, key: str, value: object
) -> None:
    """The M36.1.4.2 property as a refusal. Delete this and the split can quietly carry a change
    to how the application runs, and the claim that it needs none stops being checked."""
    documents = overlays("lite")
    documents[BASE_OVERLAY]["services"].setdefault(service, {})[key] = value

    found = application_change_gaps(documents)
    assert any(THE_OVERLAY_CHANGES_ADDRESSES_AND_NOTHING_THE_IMAGE_READS in one for one in found)


def test_the_real_overlays_change_only_addresses() -> None:
    """The positive half of the property above. Delete this and a refusal that fired on every
    overlay would pass the test above."""
    for name in COMPOSE_FILES_FOR:
        assert application_change_gaps(overlays(name)) == ()


# ===================================================================== the address check
@pytest.mark.parametrize("address", ["10.8.0.2", "192.168.50.3", "172.16.4.1", "100.64.7.9"])
def test_a_private_ipv4_address_can_be_the_data_hosts(address: str) -> None:
    """WireGuard, a private range and a tailnet all qualify. Delete this and a check refusing
    every address passes every test below."""
    assert address_refusals(address) == ()


@pytest.mark.parametrize(
    ("address", "said"),
    [
        (EVERY_INTERFACE, "every interface"),
        ("127.0.0.1", "loopback"),
        ("8.8.8.8", "public address"),
        ("169.254.10.1", "not an address one host gives another"),
        ("fd00::2", "IPv6"),
        ("db.internal", "not an IP address"),
    ],
)
def test_an_address_that_would_publish_widely_or_cannot_be_bound_is_refused(
    address: str, said: str
) -> None:
    """Each is a real mistake: the unspecified address publishes everywhere, loopback is
    unreachable from the other host, a public address answers the internet, and a name is not
    something a ports entry binds. Delete this and the operator's check says yes to all of them."""
    found = address_refusals(address)
    assert found and said in found[0], found


def test_the_command_exits_non_zero_on_a_refused_address(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """What an operator runs in the guide. Delete this and a refusal can print and exit 0, which a
    script reads as yes."""
    assert main(["--check-address", EVERY_INTERFACE]) == 1
    assert main(["--check-address", "10.8.0.2"]) == 0
    assert main(["--services", "lite", "data", "--in", str(REPO)]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "db pgbouncer"
