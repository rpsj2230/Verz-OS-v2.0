"""Every third-party image the product pins is one somebody looked up, and the page says so.

The automation canvas's egress proxy was pinned to `ubuntu/squid:6.10-24.04_edge`, a tag Docker
Hub does not publish. Nothing failed anywhere in this repository: the compose file parsed, the
deployment test compared its memory limit, and the first server to run `docker compose up` on it
found `tag not found` at the pull. A unit test cannot ask a registry (this one makes no network
call, on purpose, because a test that needs the internet is a test that fails for a reason that
is not the code), so what it can hold the files to is a record: `docs/install/images.md` lists
each pinned image with the day the registry was asked, and a tag that is not on that page fails
here, as does a row on the page that nothing pins any more.

**The register is read, never generated from the files.** A page produced by the files agrees with
them by construction and so says nothing about whether anybody looked a tag up. Rejected: a script
that writes the page from the compose files, for exactly that reason; and a CI step that asks each
registry, which is the right check and a slow, network-dependent one that belongs beside the
release rather than in a unit suite.

Task ids: M32.6.1.1, M42.2.3
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.browsing.sandbox import EGRESS_IMAGE
from brain.ops.dependency_policy import images_in

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs" / "install" / "images.md"

#: Folders that hold no file of this product's.
SKIPPED_PARTS = frozenset({"node_modules", ".venv", ".git", ".scratch", "__pycache__"})

#: A row of the register: the image in backticks, then the used-by cell, the date and the method.
ROW = re.compile(
    r"^\|\s*`(?P<image>[^`]+)`\s*\|\s*(?P<used>[^|]+?)\s*\|\s*(?P<date>[^|]+?)\s*\|\s*(?P<how>[^|]+?)\s*\|\s*$"
)


def register(text: str) -> dict[str, tuple[str, str, str]]:
    """The page's rows: image reference to (used by, date checked, how)."""
    return {
        found["image"]: (found["used"], found["date"], found["how"])
        for line in text.splitlines()
        if (found := ROW.match(line)) is not None
    }


def compose_images(root: Path) -> set[str]:
    """Every literal image a compose file under `root` names, wherever the file lives.

    Read from parsed YAML rather than a pattern over the text, so an image named in a comment, which
    a pattern would count, is not one. A reference holding `$` is a variable: the product's own
    image, built here, which is not a tag anybody looks up in a registry.
    """
    found: set[str] = set()
    for path in sorted([*root.rglob("*.yml"), *root.rglob("*.yaml")]):
        if SKIPPED_PARTS & set(path.relative_to(root).parts):
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        services = document.get("services") if isinstance(document, dict) else None
        if not isinstance(services, dict):
            continue
        for body in services.values():
            image = body.get("image") if isinstance(body, dict) else None
            if isinstance(image, str) and "$" not in image:
                found.add(image)
    return found


def pinned_images() -> set[str]:
    """Every third-party image the repository pins: compose files, Dockerfiles, and one in code."""
    found = compose_images(REPO)
    found |= {one.version for one in images_in(REPO)}
    found.add(EGRESS_IMAGE)
    return found


def is_floating(reference: str) -> bool:
    """Whether a reference names no fixed build: no tag at all, or the tag `latest`."""
    if "@sha256:" in reference:
        return False
    last = reference.rsplit("/", 1)[-1]
    return ":" not in last or last.endswith(":latest")


def unregistered(images: Iterable[str], rows: Mapping[str, Any]) -> list[str]:
    """The images that carry no digest and have no row, sorted."""
    return sorted(one for one in images if "@sha256:" not in one and one not in rows)


def unused(images: Iterable[str], rows: Mapping[str, Any]) -> list[str]:
    """The rows nothing pins, sorted: a row for a thing that is gone reads as coverage."""
    wanted = set(images)
    return sorted(one for one in rows if one not in wanted)


def test_every_image_the_files_pin_is_listed_on_the_page_that_records_it_was_looked_up() -> None:
    """The compose files, the Dockerfiles and the browser sandbox's constant are read from the
    repository and compared with the page. Delete this and a tag nobody looked up (the squid one
    was never published) reaches a server as a failed pull."""
    rows = register(PAGE.read_text(encoding="utf-8"))
    images = pinned_images()

    assert images, "no image was read from any file, so this compared nothing"
    assert unregistered(images, rows) == []


def test_a_row_on_the_page_for_an_image_nothing_pins_is_refused() -> None:
    """A tag that was changed in the files and left on the page keeps the old row looking like
    coverage for the new one. Delete this and the page drifts from the files in the direction that
    is never noticed."""
    rows = register(PAGE.read_text(encoding="utf-8"))

    assert unused(pinned_images(), rows) == []


def test_every_row_says_when_the_tag_was_looked_up_and_how() -> None:
    """A row with no date is a claim nobody can age, and one with no method cannot be repeated.
    Delete this and the page can list a tag without saying anybody asked the registry."""
    rows = register(PAGE.read_text(encoding="utf-8"))

    assert rows
    for image, (_, date, how) in rows.items():
        assert re.fullmatch(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]", date), image
        assert how, image


def test_no_pinned_image_floats() -> None:
    """A tag of `latest`, or none, is not a pin: the next pull changes what runs with nobody having
    decided. Delete this and a floating reference passes because the register only asks that a row
    exist for it."""
    assert [one for one in sorted(pinned_images()) if is_floating(one)] == []


def test_the_canvas_proxy_is_the_tag_that_exists_and_not_the_one_that_does_not() -> None:
    """The defect this file was written for, pinned by name so a revert is a failure whatever the
    register says: the 24.04 line of squid stops at 6.6 on the registry, and 6.10 exists only for
    24.10. Delete this and a well-meant bump back to the newer number passes with a row added.

    The expected tag is a fact about the registry, read on 2026-10-13 (Docker Hub answered 200 for
    `6.6-24.04_edge` and 404 for `6.10-24.04_edge`), so it is written here rather than imported."""
    automation = yaml.safe_load(
        (REPO / "docker-compose.automation.yml").read_text(encoding="utf-8")
    )

    assert automation["services"]["automation-egress"]["image"] == "ubuntu/squid:6.6-24.04_edge"
    assert "ubuntu/squid:6.10-24.04_edge" not in pinned_images()


# ---------------------------------------------------------- the checks, on cases built to fail
@pytest.mark.parametrize(
    ("reference", "floats"),
    [
        ("ubuntu/squid:6.6-24.04_edge", False),
        ("registry.example:5000/team/app:1.2", False),
        ("alpine@sha256:" + "a" * 64, False),
        ("postgres", True),
        ("postgres:latest", True),
        ("registry.example:5000/team/app", True),
    ],
)
def test_a_reference_with_no_fixed_tag_floats_and_a_port_is_not_a_tag(
    reference: str, floats: bool
) -> None:
    """The positive and the negative of `is_floating`, including a registry port that a naive check
    for a colon would read as a tag. Delete this and a guard that refuses everything, or nothing,
    passes the real files."""
    assert is_floating(reference) is floats


def test_the_checks_find_an_image_with_no_row_and_a_row_with_no_image() -> None:
    """Both halves of the comparison run against rows and images built to disagree, with a digest
    pinned image that needs no row. Delete this and the two real-file tests above can be satisfied
    by comparisons that never report anything."""
    rows = {"a:1": ("x", "2026-01-01", "y"), "gone:2": ("x", "2026-01-01", "y")}
    images = ["a:1", "b:3", "c@sha256:" + "b" * 64]

    assert unregistered(images, rows) == ["b:3"]
    assert unused(images, rows) == ["gone:2"]
    assert unregistered(["a:1"], {"a:1": ()}) == []


def test_the_page_is_read_as_rows_and_prose_that_names_an_image_is_not_a_row() -> None:
    """The sentence under the table quotes the tag that does not exist, and a reader of the page by
    pattern would count it. Delete this and the bad tag, mentioned in the explanation of why it is
    bad, becomes a row that makes the register pass for it."""
    text = PAGE.read_text(encoding="utf-8")

    assert "`6.10-24.04_edge`" in text
    assert "ubuntu/squid:6.10-24.04_edge" not in register(text)
    assert "ubuntu/squid:6.6-24.04_edge" in register(text)
