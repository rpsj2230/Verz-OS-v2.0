"""Each install profile starts exactly the services it promises, the worker included.

Until 2026-09-22 the worker, the parse worker, their session pooler, the inference server and
the matcher carried a compose `profiles:` key, and nothing the installer, the update script or
the rollback script runs passes `--profile` or sets `COMPOSE_PROFILES`. So every standard and
full install came up with no worker, and no scheduled control ever ran; the owner's staging
install hit the same. These tests read the committed scripts, take the exact compose flags each
profile arm passes, and ask what `docker compose config --services` would list for them.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.deployment.requirements import files_for, profiles_composing
from brain.ops.compose import declared_services, profile_gated_services, services_started
from brain.ops.wiring import COMPONENTS, PROFILES, components_for

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = ("ops/install/install.sh", "ops/update/update.sh", "ops/update/rollback.sh")

#: The scheduled controls run here; a profile promising them and not starting them is the bug.
WORKERS = ("brain-worker", "brain-parse-worker", "pgbouncer-session")


def _arm(script: str, profile: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The compose files and active profiles this script's arm for `profile` passes."""
    text = (REPO / script).read_text(encoding="utf-8")
    line = next(one for one in text.splitlines() if one.startswith(f"  {profile}) "))
    match = re.search(r'BRAIN_COMPOSE_FILES="([^"]*)"', line)
    assert match, f"{script} has no compose file list for {profile}"
    words = shlex.split(match.group(1))
    files = tuple(Path(words[i + 1]).name for i, one in enumerate(words) if one == "-f")
    active = [words[i + 1] for i, one in enumerate(words) if one == "--profile"]
    # An environment-wide selection would count too, so it is read rather than assumed absent.
    active += re.findall(r"COMPOSE_PROFILES=\"?([\w,-]+)", text)
    return files, tuple(p for one in active for p in one.split(","))


def _documents(names: tuple[str, ...]) -> dict[str, Any]:
    return {name: yaml.safe_load((REPO / name).read_text(encoding="utf-8")) for name in names}


@pytest.mark.parametrize("script", SCRIPTS)
@pytest.mark.parametrize("profile", PROFILES)
def test_the_scripts_compose_invocation_starts_every_service_the_profile_promises(
    script: str, profile: str
) -> None:
    """The promise is the profile's file list (`BRAIN_SERVICES` counts it) and the wiring's
    components for that profile. Delete this and a `profiles:` key, or a file list that drifts
    from the table, can leave an install running without its worker again."""
    files, active = _arm(script, profile)
    assert files == files_for(profile)
    documents = _documents(files)

    started = set(services_started(documents, active))
    promised = set(declared_services(documents))
    assert started == promised, f"{script} {profile}: not started {sorted(promised - started)}"

    component_names = {one.name for one in COMPONENTS}
    budgeted = {one.name for one in components_for(profile)}
    assert (budgeted & promised) <= started
    assert started & component_names <= budgeted, "a component starts where nothing budgets it"
    if profile in {"standard", "full"}:
        assert set(WORKERS) <= started
        assert "inference-server" in started
    if profile == "full":
        assert "record-matcher" in started
    if profile == "lite":
        assert not set(WORKERS) & started


@pytest.mark.parametrize("profile", PROFILES)
def test_the_install_scripts_service_count_is_the_set_it_starts(profile: str) -> None:
    """Step 20 skips `up -d` once this many services run, so a count above what starts would
    re-run it for ever, and one below would stop before the worker is up."""
    text = (REPO / "ops/install/install.sh").read_text(encoding="utf-8")
    line = next(one for one in text.splitlines() if one.startswith(f"  {profile}) "))
    count = re.search(r'BRAIN_SERVICES="(\d+)"', line)
    assert count
    files, active = _arm("ops/install/install.sh", profile)
    assert int(count.group(1)) == len(services_started(_documents(files), active))


def test_no_product_compose_file_gates_a_service_behind_a_profile() -> None:
    """The file list is the one selection. Delete this and a key reappears in a file no
    profile arm test happens to compose, such as an overlay."""
    names = tuple(sorted(p.name for p in REPO.glob("docker-compose*.yml")))
    gated = profile_gated_services(_documents(names))
    assert gated == ()


def test_a_keyed_service_is_what_the_simulation_leaves_out() -> None:
    """The check is only worth something if it can fail: a keyed worker is not started without
    its profile, is with it, and is reported as a blocker."""
    documents = _documents(files_for("standard"))
    documents["docker-compose.worker.yml"]["services"]["brain-worker"]["profiles"] = ["standard"]

    assert "brain-worker" not in services_started(documents)
    assert "brain-worker" in services_started(documents, ("standard",))
    assert any("'brain-worker'" in one for one in profile_gated_services(documents))


def test_each_workers_file_is_composed_on_exactly_the_profiles_that_budget_it() -> None:
    """Both directions, now that the file list is the only selection."""
    for name, service in (
        ("docker-compose.worker.yml", "brain-worker"),
        ("docker-compose.parse-worker.yml", "brain-parse-worker"),
        ("docker-compose.inference.yml", "inference-server"),
        ("docker-compose.matcher.yml", "record-matcher"),
    ):
        wanted = {p for p in PROFILES if service in {c.name for c in components_for(p)}}
        assert profiles_composing(name) == wanted, name
