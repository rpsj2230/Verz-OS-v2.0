"""Client independence, held to the property that matters for the client nobody has met yet.

The premise of this system is that a client hosts it and owns what is inside it, and that
premise survives exactly as long as the repository does not quietly learn who the first client
is. Every test here is about a way it learns: a value read in a second place with a second
default, a default that is one company's, a literal that names a host, a page that fetches
from a third party on every load.

The tests are written against the shapes rather than against any name, for the same reason the
sweep is. A test asserting that "verz" does not appear is green for the second client on the
day it is written.

Task ids: M41.1.1, M41.1.2, M41.1.3, M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.3.1, M41.3.3, M41.3.4
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from brain.install import (
    A_TEMPLATE_WHOSE_DEFAULTS_ARE_ONE_CLIENTS_IS_A_COPY_OF_THAT_CLIENT,
    BY_NAME,
    INSTALL_PREFIX,
    INSTALLATION,
    Belongs,
    InstallError,
    Setting,
    belonging_to,
    missing,
    runbook,
    value_of,
)
from brain.ops.independence import (
    ALLOWED_HOSTS,
    compose_services,
    environment_reads,
    independence_gaps,
    is_reserved,
    second_readers,
    value_shaped_literals,
    vendor_hosts,
)

REPO = Path(__file__).resolve().parents[2]

#: A minimal environment supplying only what has no safe default.
SUPPLIED = {
    "INSTALL_OIDC_ISSUER": "https://id.example.com/realms/brain",
    "INSTALL_OIDC_REDIRECT_URIS": "https://brain.example.com/callback",
}


# --- the declaration is the only place a client value is read -------------------------------


def test_the_whole_tree_is_free_of_client_values_and_second_readers() -> None:
    """**The gate, run against this repository, and it is meant to stay at zero.**

    Every finding is either a value that belongs to one client sitting in a file that ships to
    all of them, or a module reading an installation setting itself. The first run of this
    found six real things, including four pages fetching a stylesheet from Google on every
    load from inside the client's own network, and a fixture address on `example.com.sg`,
    which is an ordinary registerable domain rather than a reserved one.

    Delete this and the sweep exists and never runs, which is the state
    `brain.knowledge.embed_policy.policy_gaps` was in for a fortnight: correct, argued, and
    asked by nothing."""
    assert independence_gaps(REPO) == ()


def test_a_setting_read_from_the_environment_anywhere_else_is_reported() -> None:
    """The rule that keeps one reader one reader. A second reader has a second default, and
    the wrong one is the one nobody looked at: unlike a literal it does not show up in a grep,
    and it agrees with the first on every machine where both are set, which is every machine
    except the new client's.

    All four real shapes, because a check that knows `os.environ[...]` and not
    `from os import getenv` is a check with a documented way round it.

    Delete this and `brain.install` becomes one of several places the client's name is
    decided."""
    source = "\n".join(
        [
            "import os",
            'a = os.environ["INSTALL_A"]',
            'b = os.getenv("INSTALL_B")',
            'c = env.get("INSTALL_C")',
            'd = environ["INSTALL_E"]',
        ]
    )

    assert [name for _, name in environment_reads(ast.parse(source))] == [
        "INSTALL_A",
        "INSTALL_B",
        "INSTALL_C",
        "INSTALL_E",
    ]


def test_reading_a_setting_the_correct_way_is_not_reported() -> None:
    """**Written because the first version of the check reported the right answer as wrong.**
    It flagged any literal beginning `INSTALL_`, which made `value_of("INSTALL_ACCENT_COLOUR")`
    a violation: the one correct way to read a setting was the one thing the sweep refused.

    A check that fires on the correct usage is worse than no check, because the first thing
    anybody does is switch it off, and then the real violations go with it.

    The ordinary `.get` matters too: `.get` on a dictionary is the most common call in the
    language, and a rule that could not tell it from `env.get` would be unusable.

    Delete this and the sweep can tighten back into refusing its own contract."""
    source = "\n".join(
        [
            'ok = value_of("INSTALL_ACCENT_COLOUR")',
            'also = some_dictionary.get("INSTALL_THING")',
            'name = "INSTALL_MENTIONED_IN_A_MESSAGE"',
        ]
    )

    assert list(environment_reads(ast.parse(source))) == []


def test_brain_install_is_the_module_that_reads_them() -> None:
    """The positive sibling of the rule above, without which a tree where nothing reads a
    setting at all passes: `second_readers` would be empty and the system would have no
    configuration.

    Delete this and the one reader can stop reading, and every install gets the defaults."""
    found = second_readers(REPO)
    text = (REPO / "src" / "brain" / "install.py").read_text(encoding="utf-8")

    assert found == ()
    assert INSTALL_PREFIX in text
    assert value_of("INSTALL_PRODUCT_NAME", SUPPLIED) == "Brain"


# --- what a setting has to declare -----------------------------------------------------------


def test_a_required_setting_carrying_a_default_cannot_be_constructed() -> None:
    """A setting that is both required and defaulted can never refuse: the default answers
    first and the refusal is unreachable. That is the guard-that-cannot-fire shape, on the
    values that decide which identity provider this install trusts.

    Delete this and `INSTALL_OIDC_ISSUER` can quietly acquire a default, and an install that
    forgot to set it authenticates against whatever that default names."""
    with pytest.raises(ValueError, match="never refuse"):
        Setting(
            name="INSTALL_SOMETHING",
            belongs=Belongs.IDENTITY,
            meaning="anything",
            default="a value",
            required=True,
        )


def test_an_optional_setting_with_an_empty_default_cannot_be_constructed() -> None:
    """An unset value and a value set to the empty string would then be the same thing, and
    neither would be reported. That is how `DATABASE_URL` was unset in production while the
    application reported healthy, which `brain.config` records.

    Delete this and a setting can be added that is silently absent on every install."""
    with pytest.raises(ValueError, match="neither is reported"):
        Setting(name="INSTALL_SOMETHING", belongs=Belongs.STORAGE, meaning="anything")


def test_a_setting_nobody_wrote_a_meaning_for_cannot_be_constructed() -> None:
    """The meaning is what the install runbook prints and what somebody setting the value on a
    client's server reads. A setting nobody can explain is one they will guess at, and the
    guess lands on production.

    Delete this and `runbook()` grows entries that name a variable and say nothing about
    it."""
    with pytest.raises(ValueError, match="no meaning written down"):
        Setting(name="INSTALL_SOMETHING", belongs=Belongs.BRANDING, meaning="  ", default="a value")


def test_every_declared_setting_has_a_meaning_a_group_and_a_way_to_be_absent() -> None:
    """The whole declaration, checked rather than trusted, because the constructor only sees
    each setting as it is written and this sees the set.

    The name check matters on its own: a setting not beginning `INSTALL_` is invisible to
    `second_readers`, which matches on the prefix, so it could be read anywhere with nothing
    reporting it.

    Delete this and a setting can be declared outside the namespace the sweep watches."""
    for one in INSTALLATION:
        assert one.name.startswith(INSTALL_PREFIX), one.name
        assert one.meaning.strip()
        assert isinstance(one.belongs, Belongs)
        assert bool(one.default) != one.required, one.name

    assert len(BY_NAME) == len(INSTALLATION), "two settings share a name"


def test_no_default_here_is_one_companys() -> None:
    """**The test that keeps this a template rather than a copy.** A default of "Verz Company
    Brain" would make the module a description of one deployment wearing the clothes of a
    template, and the second install would start branded as the first, which the person
    looking at it has no reason to think is wrong.

    Asserted through the sweep's own rules rather than by listing names, so it holds for a
    client nobody has met: a default may name a reserved documentation domain, a service this
    deployment's compose files declare, or a vendor a connector declares, and nothing else.

    That set is the same one the sweep uses, and it found a real defect the moment it was
    tightened: `INSTALL_MODEL_ENDPOINT` defaulted to `http://inference:8080` and the compose
    service is called `inference-server`, so the default named a host that does not exist.

    Delete this and the defaults drift towards whoever installed it most recently."""
    permitted = ALLOWED_HOSTS | compose_services(REPO) | vendor_hosts(REPO)

    for one in INSTALLATION:
        if not one.default:
            continue
        for piece in value_shaped_literals_in(one.default):
            assert piece in permitted or is_reserved(piece), f"{one.name} defaults to {piece}"

    assert "wearing the clothes of a template" in (
        A_TEMPLATE_WHOSE_DEFAULTS_ARE_ONE_CLIENTS_IS_A_COPY_OF_THAT_CLIENT
    )


def value_shaped_literals_in(text: str) -> list[str]:
    """The hosts a single string mentions, using the sweep's own patterns."""
    from brain.ops.independence import ADDRESS, URL_HOST

    return [one.group(1).split(":")[0].lower() for one in URL_HOST.finditer(text)] + [
        one.group(1).lower() for one in ADDRESS.finditer(text)
    ]


# --- reading a value, and refusing to guess one ----------------------------------------------


def test_a_setting_with_no_safe_default_refuses_rather_than_guessing() -> None:
    """An issuer guessed wrong is a sign-in page that redirects to somebody else's identity
    provider, and an empty string is a perfectly valid string, so the failure is a login screen
    that works and authenticates against nothing this install controls.

    Delete this and an install that forgot the issuer starts, serves, and is trusted."""
    with pytest.raises(InstallError, match="no safe default"):
        value_of("INSTALL_OIDC_ISSUER", {})


def test_a_setting_with_a_safe_default_takes_it_rather_than_refusing() -> None:
    """The sibling. Refusing to start over an unset logo would make the safe configuration the
    one that fails, and an install team that has to set fifteen variables to see a login page
    sets them wrong.

    Delete this and every optional setting becomes required by accident."""
    assert value_of("INSTALL_ACCENT_COLOUR", {}) == "#2563eb"
    assert value_of("INSTALL_COMPANY_NAME", {"INSTALL_COMPANY_NAME": "Acme"}) == "Acme"


def test_a_value_set_to_whitespace_is_treated_as_unset() -> None:
    """A variable set to a space in a compose file is what an install team produces when they
    mean to leave it out, and a company name of `" "` renders as a blank heading with nothing
    reporting it.

    Delete this and the empty-string failure comes back through the front door."""
    assert value_of("INSTALL_COMPANY_NAME", {"INSTALL_COMPANY_NAME": "   "}) == "Your Company"

    with pytest.raises(InstallError, match="no safe default"):
        value_of("INSTALL_OIDC_ISSUER", {"INSTALL_OIDC_ISSUER": "  "})


def test_reading_a_setting_nobody_declared_is_refused() -> None:
    """The other half of one reader. A value read through `value_of` but never declared has no
    meaning, no default and no entry in the runbook, so it is configuration only the person
    who wrote it knows about.

    Delete this and the declaration stops being the whole list, which is the one property that
    makes `runbook()` worth printing."""
    with pytest.raises(InstallError, match="not a declared installation setting"):
        value_of("INSTALL_SOMETHING_NOBODY_DECLARED", {})


def test_missing_reports_every_unsupplied_requirement_rather_than_the_first() -> None:
    """An install missing two values has two problems, and fixing one produces a configuration
    that still refuses. Matching `brain.ops.worker.preflight`, which makes the same argument.

    Delete this and installing becomes a sequence of single failures, each discovered by
    restarting."""
    assert set(missing({})) == {"INSTALL_OIDC_ISSUER", "INSTALL_OIDC_REDIRECT_URIS"}
    assert missing(SUPPLIED) == ()


def test_each_surface_can_be_asked_for_on_its_own() -> None:
    """These are handed over by different people on install day: branding by whoever owns the
    brand, identity by whoever runs the directory, storage by whoever runs the infrastructure.
    One flat map would make the runbook a list nobody owns.

    Delete this and the groups become a label with nothing reading it."""
    branding = belonging_to(Belongs.BRANDING, SUPPLIED)
    identity = belonging_to(Belongs.IDENTITY, SUPPLIED)

    assert branding["INSTALL_COMPANY_NAME"] == "Your Company"
    assert identity["INSTALL_OIDC_ISSUER"] == SUPPLIED["INSTALL_OIDC_ISSUER"]
    assert not set(branding) & set(identity)
    assert set(branding) | set(identity) <= set(BY_NAME)


def test_the_runbook_names_every_setting_and_is_generated_rather_than_written() -> None:
    """A hand-written list of environment variables is wrong the first time somebody adds one,
    and it is wrong in the direction of omitting the new one, which is the direction nobody
    notices.

    Delete this and the install runbook drifts from the declaration, and the value it omits is
    the one the install team never sets."""
    printed = runbook()

    for one in INSTALLATION:
        assert one.name in printed, one.name
        assert one.meaning.split(".")[0] in printed, one.name
    for group in Belongs:
        assert group.value in printed


def test_the_model_profile_defaults_to_reaching_nothing_outside_the_client() -> None:
    """A client who has not chosen to send their text to an external provider has not chosen
    it, and a default that reaches one makes that decision on their behalf on install day,
    silently, on a system whose whole premise is that they host it themselves.

    Delete this and `local` becomes a setting somebody has to know to look for."""
    assert value_of("INSTALL_MODEL_PROFILE", {}) == "local"
    assert value_of("INSTALL_MODEL_ENDPOINT", {}).startswith("http://inference")


# --- the repository is the template ----------------------------------------------------------


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


# --- the sweep's own rules ---------------------------------------------------------------------


def test_a_vendor_host_is_derived_from_the_connectors_rather_than_listed() -> None:
    """**A hand-written allowlist of vendor hosts needs editing the day somebody adds a
    connector, which is the day nobody is thinking about client independence.** `api.xero.com`
    is where Xero is for every client this system will ever have, so it belongs to the product
    and the product already says so, at the top of the connector.

    Both areas, because a channel adapter reaches a vendor for the same reason a connector
    does and `BOT_FRAMEWORK_ISSUER` lives in `channels/`.

    Delete this and either the allowlist rots or somebody widens the sweep until it passes."""
    found = vendor_hosts(REPO)

    assert "api.xero.com" in found
    assert "api.botframework.com" in found
    assert not any(" " in one for one in found), "a sentence is not a host"


def test_the_pages_the_application_serves_are_swept_as_well_as_the_source() -> None:
    """**A survivor found this, and it was the mutation worth writing.** Removing `docs` from
    the searched areas left every other test green: nothing asserted that the pages served at
    `/build` are read at all.

    M41.1.1 names src, migrations, console and compose, and not these. They belong anyway: the
    running application serves them, so they are as deployed as anything in `src`, and leaving
    them out is exactly how the first version of this sweep came back green while four of them
    fetched a stylesheet from Google on every load from inside the client's network.

    Asserted by planting a host in a real docs page rather than by checking the constant, so
    the claim is that they are read rather than that they are listed.

    Delete this and `docs` can be dropped from the sweep and nothing says so."""
    from brain.ops.independence import SEARCHED

    assert "docs" in SEARCHED

    page = REPO / "docs" / "_temporary_independence_probe.html"
    page.write_text(
        '<link rel="stylesheet" href="https://cdn.acme-corporation.invalid-tld/a.css">\n',
        encoding="utf-8",
        newline="\n",
    )
    try:
        found = value_shaped_literals(REPO)
    finally:
        page.unlink(missing_ok=True)

    assert any("cdn.acme-corporation.invalid-tld" in one for one in found), found


def test_a_reserved_domain_is_recognised_by_its_suffix_and_an_ordinary_one_is_not() -> None:
    """RFC 2606 and RFC 6761 reserve these precisely so documentation can use them, and
    matching by suffix is the difference between allowing `acme.example` and having to list it.

    The negative case is the one that found a real defect: `example.com.sg` reads like a
    reserved domain, is an ordinary registerable one, and was a fixture address in this
    repository until this rule refused it.

    Delete this and a fixture address on a domain somebody could buy ships in the product."""
    assert is_reserved("acme.example")
    assert is_reserved("example.com")
    assert is_reserved("localhost")

    assert not is_reserved("example.com.sg")
    assert not is_reserved("acme.co")


def test_a_client_host_in_a_literal_is_reported_and_a_docstring_is_not() -> None:
    """The two halves that let this be a hard gate. A URL in a literal is a value the running
    system uses; the same words in a docstring are prose about where a measurement was taken,
    and stripping the place would make the sentence a claim about nothing.

    Written against a temporary file rather than against the tree, so it tests the rule rather
    than today's contents, which are green.

    Delete this and either the gate stops catching a hardcoded host, or it starts refusing
    every module docstring that mentions a company, at which point somebody switches it off."""
    scratch = REPO / "src" / "brain" / "_temporary_independence_probe.py"
    scratch.write_text(
        '"""A probe written and removed by test_independence.\n\n'
        "Prose mentioning https://acme-corporation.example-not-reserved.com is not a value.\n\n"
        'Task ids: none\n"""\n\n'
        'ENDPOINT = "https://records.acme-corporation.invalid-tld"\n',
        encoding="utf-8",
        newline="\n",
    )
    try:
        found = value_shaped_literals(REPO)
    finally:
        scratch.unlink(missing_ok=True)

    assert any("records.acme-corporation.invalid-tld" in one for one in found), found
    assert not any("example-not-reserved.com" in one for one in found), found
