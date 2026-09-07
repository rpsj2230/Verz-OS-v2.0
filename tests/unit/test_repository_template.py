"""The repository is the template, and Verz is one deployment of it.

Three claims that are about this checkout rather than about the running system: the
environment file is the declaration's printout, the product is named by the installation
rather than by a literal, and the map of what an install touches agrees with the tree.

They live apart from `test_independence.py` because that file is about the sweep, which is a
rule applied to source, and these are about documents. The practical reason is smaller and
worth recording: a single `Task ids:` line naming all twelve leaves is 105 characters, and the
line may not wrap, so the split was going to happen somewhere.

Task ids: M41.3.1 M41.3.3 M41.3.4
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_environment_example_is_the_declarations_printout() -> None:
    """**A hand-kept list of environment variables is wrong the first time somebody adds one,
    and it is wrong by omitting the new one**, which is the direction nobody notices: the
    install team sets the fourteen that are written down and the fifteenth quietly takes its
    default on a client's server.

    So `.env.example` carries a generated block and this compares it against the declaration.
    Editing a value in the file is expected, because it is an example; editing a name or a
    meaning, or adding a setting and forgetting the file, fails here.

    Delete this and a client install is a release tag plus an environment file that does not
    mention everything the release reads."""
    from brain.install import ENV_BLOCK_END, ENV_BLOCK_START, env_example

    text = (REPO / ".env.example").read_text(encoding="utf-8")

    assert ENV_BLOCK_START in text and ENV_BLOCK_END in text
    start = text.index(ENV_BLOCK_START)
    end = text.index(ENV_BLOCK_END) + len(ENV_BLOCK_END)
    assert text[start:end].strip() == env_example().strip()


def test_the_product_is_named_by_the_installation_and_not_by_a_literal() -> None:
    """**The first thing an API consumer sees and the first thing on every build page.** The
    FastAPI schema title and the two page titles all read "Verz Company Brain" until today,
    which is a product wearing one deployment's name in the three most visible places it has.

    A shape-based sweep cannot catch this: a company name has no shape, unlike an address or a
    host. So it is asserted from the other end, by configuring a different company and
    checking the rendered output changes, which is a property no literal can satisfy.

    Delete this and the name goes back to a constant, and the second client's staff read
    somebody else's company name on every page."""
    from fastapi.testclient import TestClient

    from brain.app import create_app
    from brain.install import installed_name

    assert installed_name({"INSTALL_COMPANY_NAME": "Acme"}) == "Acme Brain"
    assert (
        installed_name({"INSTALL_PRODUCT_NAME": "Knowledge Desk"}) == "Your Company Knowledge Desk"
    )

    client = TestClient(create_app())
    assert installed_name() in client.get("/build").text


def test_the_repository_map_names_every_top_level_entry_and_invents_none() -> None:
    """`docs/repository-map.md` is what tells a reader which parts of this tree an install
    touches, and the answer is none of them. A map that has drifted is worse than none: it
    describes a repository that no longer exists, and the entry it is missing is the new one,
    which is exactly the one somebody is looking up.

    Both directions, because a map naming a directory that was deleted misleads as reliably as
    one missing a directory that was added.

    Delete this and the map rots the first time anybody adds a compose file."""
    raw = (REPO / "docs" / "repository-map.md").read_text(encoding="utf-8")
    # Whitespace collapsed before any phrase is looked for. The document is wrapped at ninety
    # columns, so "a release tag plus one environment file" is split across two lines and a
    # plain substring check fails on a document that says exactly what it should. That is the
    # substring trap CLAUDE.md records, in the direction that produces a false alarm.
    text = " ".join(raw.split())

    # Dot-entries are tooling and caches rather than repository structure, and a map that
    # listed `.mypy_cache` would be describing this laptop rather than the product. `.env.example`
    # is the exception and is asserted separately below, because it is the one file an install
    # copies.
    def family(name: str) -> str:
        """The compose files are one family in the map, matching how they are read."""
        return "docker-compose" if name.startswith("docker-compose") else name

    # Matched against the table's own rows rather than against the document, and a mutation
    # found the difference: deleting the `migrations/` row left the word elsewhere in the
    # prose, so a bare substring check passed on a map that had lost an entry. That is the
    # substring trap CLAUDE.md records, in the direction that produces a false pass.
    named: set[str] = set()
    for line in raw.splitlines():
        if not line.startswith("|"):
            continue
        # Every backticked token in the first cell, because a row legitimately covers several
        # files: `pyproject.toml`, `uv.lock` is one row and two entries.
        for token in re.findall(r"`([^`]+)`", line.split("|")[1]):
            named.add(family(token.strip().rstrip("/").replace("*.yml", "")))
    present = {family(one.name) for one in REPO.iterdir() if not one.name.startswith(".")}
    missing = sorted(present - named)
    assert missing == [], f"the map does not mention {missing}"
    assert ".env.example" in text
    assert "a release tag plus one environment file" in text
