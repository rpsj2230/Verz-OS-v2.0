"""Client independence, held to the property that matters for the client nobody has met yet.

The premise of this system is that a client hosts it and owns what is inside it, and that
premise survives exactly as long as the repository does not quietly learn who the first client
is. Every test here is about a way it learns: a value read in a second place with a second
default, a default that is one company's, a literal that names a host, a page that fetches
from a third party on every load.

The tests are written against the shapes rather than against any name, for the same reason the
sweep is. A test asserting that "verz" does not appear is green for the second client on the
day it is written.

Task ids: M41.1.1 M41.1.2 M41.1.3 M41.1.4 M41.1.5 M41.1.6 M41.1.7 M41.1.8 M41.1.9
"""

from __future__ import annotations

import ast
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
    DOCS_SUFFIXES,
    READ_SUFFIXES,
    SEARCHED,
    compose_services,
    environment_reads,
    independence_gaps,
    is_reserved,
    is_reserved_range,
    searched_files,
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


def test_the_pages_the_application_serves_are_read_as_markdown_as_well_as_html() -> None:
    """**The hole this closed had one deployment's address in a page every client would serve.**

    `docs/needs-rupash.md` is copied into the image by `COPY docs /app/docs` and rendered at
    `/build/needs-rupash`, so it is as deployed as the HTML next to it. Until 2026-09-09 the
    sweep read `docs` for code suffixes only, and that file held fourteen client values: a
    host, an address, a Coolify panel and a service identifier.

    Asserted as a property of the mapping rather than by running the sweep, because the sweep
    passing proves the tree is clean and not that this area is being read at all. That is the
    same distinction `brain.ops.controls` draws between a mechanism existing and a mechanism
    running.

    Delete this and dropping `.md` back out of the mapping is a green change."""
    docs, src = SEARCHED["docs"], SEARCHED["src"]

    assert docs is not None and ".md" in docs
    assert src is not None and ".md" not in src, "Markdown under src is a file nothing renders"
    assert DOCS_SUFFIXES > READ_SUFFIXES, "the docs set is the code set and more"


def test_a_client_value_in_a_served_markdown_page_is_reported() -> None:
    """The other half, and a check that can only be run against a clean tree cannot be shown to
    fail.

    Written against a temporary tree rather than by dirtying this one, because the sweep is a
    hard gate here and a test that leaves a finding behind would be a test that has to clean up
    correctly to keep the gate honest.

    Delete this and the suffix could be present while the matcher never reaches the file."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "docs").mkdir()
        (repo / "docs" / "page.md").write_text(
            "The console answers on https://brain.198.51.100.7.example.net today.\n",
            encoding="utf-8",
        )

        found = value_shaped_literals(repo)

    assert found, "a host and an address in a served page are two findings"
    assert any("page.md" in one for one in found)


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


def test_the_sweep_is_registered_and_runs_on_every_commit() -> None:
    """M41.1.8 asks for this on every commit, and the reason is in the leaf's own wording: so
    the final audit before a second client verifies a gate that has been green all along
    rather than cleaning a year of drift.

    Both halves, because either alone is useless. A sweep registered in `SWEEPS` and absent
    from the workflow runs nowhere; a workflow step naming a sweep that is not registered
    fails CI with a usage message, which is loud but is not the check running.

    Delete this and the step can be dropped from the workflow in a tidy-up, and the only
    symptom is that a client value stops being refused."""
    from brain.ops.sweeps import SWEEPS

    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "client_independence" in SWEEPS
    assert "brain.ops.sweeps client_independence" in workflow


def test_the_sweep_raises_on_a_finding_rather_than_only_printing_it() -> None:
    """**A survivor found this.** `test_sweeps.py` checks that every registered sweep exits
    zero on this tree, which a sweep that can never fail satisfies perfectly: it is green
    today, green on a tree full of client values, and green for ever.

    So the raising half is asserted directly, by planting a value-shaped literal in a real
    file and asking the sweep. The alternative, asserting that the function contains a
    `raise`, is the shape this repository has been caught by twice.

    Delete this and `client_independence` can be reduced to a print, and every other test
    about it still passes."""
    from brain.ops.sweeps import SweepFailure, sweep_client_independence

    scratch = REPO / "src" / "brain" / "_temporary_sweep_probe.py"
    scratch.write_text(
        '"""A probe written and removed by test_independence. Task ids: none"""\n\n'
        'ENDPOINT = "https://records.acme-corporation.invalid-tld"\n',
        encoding="utf-8",
        newline="\n",
    )
    try:
        with pytest.raises(SweepFailure) as raised:
            sweep_client_independence()
    finally:
        scratch.unlink(missing_ok=True)

    assert any("acme-corporation" in one for one in raised.value.findings), raised.value.findings

    sweep_client_independence()


def test_the_application_answers_configured_as_a_company_that_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The end-to-end form of everything above, and the one M41 actually asks for.** Every
    other test here checks a rule. This configures the system as a company nobody has heard of,
    with nothing from any real deployment set, and asks it to serve.

    The point is what must *not* appear. A page rendered under this environment must carry the
    fictitious company's name, and must carry none of the strings this deployment happens to
    use, because a value that survives configuration is a value the second client inherits.
    The check is on the rendered bytes rather than on a function's return, since the failure
    mode is a template that interpolates one thing and hard-codes another beside it.

    `monkeypatch.setenv` rather than a passed environment, because `value_of` reads the real
    environment when nothing is handed to it and that is the path the running application
    takes. Passing a dictionary would test the parameter and leave the default untested.

    Delete this and every rule above can hold while the pages still say somebody else's name,
    which is the state this repository was in until today."""
    from fastapi.testclient import TestClient

    from brain.app import create_app

    for one in INSTALLATION:
        monkeypatch.delenv(one.name, raising=False)
    monkeypatch.setenv("INSTALL_COMPANY_NAME", "Meridian Freight")
    monkeypatch.setenv("INSTALL_PRODUCT_NAME", "Desk")
    monkeypatch.setenv("INSTALL_ACCENT_COLOUR", "#7a4fbe")

    client = TestClient(create_app())
    page = client.get("/build")
    schema = client.get("/openapi.json")

    assert page.status_code == 200
    assert "Meridian Freight Desk" in page.text
    assert "#7a4fbe" in page.text
    assert schema.json()["info"]["title"] == "Meridian Freight Desk"

    for leaked in ("Verz", "verz", "F47936", "2563eb"):
        assert leaked not in page.text, f"{leaked!r} survived being configured away"


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


# --- the areas a client value actually lands in -------------------------------------------


def _a_repository(root: Path) -> Path:
    """A tree with one file in each place the sweep decides about.

    Built rather than probed against this repository, because what is being tested is the
    rule and this checkout is deliberately green. Every host below is on a domain nobody can
    register, so a test here can never be answered by something real.
    """
    (root / "ops" / "deploy").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "src").mkdir()

    (root / ".env.example").write_text(
        "DEPLOY_URL=https://brain.first-client.invalid-tld\n", encoding="utf-8", newline="\n"
    )
    (root / "ops" / "runbook.md").write_text(
        "Open https://panel.first-client.invalid-tld and paste the token.\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "ops" / "deploy" / "brain-deploy").write_text(
        '#!/bin/sh\ncurl "https://api.first-client.invalid-tld/deploy"\n',
        encoding="utf-8",
        newline="\n",
    )
    (root / "docs" / "log.md").write_text(
        "Measured against https://notes.first-client.invalid-tld on Tuesday.\n",
        encoding="utf-8",
        newline="\n",
    )
    return root


def test_the_environment_file_an_install_copies_is_swept(tmp_path: Path) -> None:
    """**The one artefact handed to a client was the one artefact not checked.**
    `brain.deployment.installer.PLAN` copies `.env.example` to `/opt/brain/.env` on their
    server, and it carried this deployment's host, its Coolify identifier and its address
    until 2026-09-09. It is a file rather than an area, which is why it needed
    `SEARCHED_FILES`: sweeping the repository root instead would read `uv.lock` and every
    generated artefact beside it.

    Delete this and the file the installer hands over goes back to being unread, which is a
    gate that is green about everywhere except where the values are."""
    found = value_shaped_literals(_a_repository(tmp_path))

    assert any(".env.example" in one and "brain.first-client" in one for one in found), found


def test_the_operational_files_are_swept_whatever_they_are_called(tmp_path: Path) -> None:
    """**`ops` reads every file, and an allowlist of suffixes is what went wrong.** The values
    were in a realm export, a Markdown runbook and shell scripts with no suffix at all, and
    those were exactly the file types nobody had thought to name. So the rule is the area and
    not the extension: nothing in `ops` is neither shipped into the image nor followed by a
    person on a server.

    The extensionless script is the case worth asserting, because it is the one a suffix list
    cannot express and the one `ops/deploy/` is full of.

    Delete this and `ops` can be narrowed back to a list of extensions, which passes on the
    day it is written and misses the next file type somebody adds."""
    found = value_shaped_literals(_a_repository(tmp_path))

    assert any("ops/runbook.md" in one for one in found), found
    assert any("ops/deploy/brain-deploy" in one for one in found), found


def test_the_markdown_the_build_serves_is_read_now_and_the_gap_it_recorded_is_closed(
    tmp_path: Path,
) -> None:
    """**This test used to assert the opposite, and that is what it was for.**

    It read "the markdown the build serves is a known gap and not an accident" until
    2026-09-09, and it said in words why: `docs/needs-rupash.md` is served at
    `/build/needs-rupash`, it held fourteen client values, and widening `docs` in the same
    change that widened `ops` would have taken a green gate red on a file nobody had fixed
    yet, which is the state in which a gate gets switched off.

    The page is fixed, so the line went in. Every value in it is now either a description of
    what the reader should look at on their own screen or a command that derives it from the
    server it runs on, which is also the better instruction: a command reading
    `/data/coolify/services` is right on every server and an identifier typed into a page is
    right on exactly one.

    A gap deliberately left, written down with the condition for closing it, and closed on the
    day that condition was met. Worth keeping as a shape rather than only as a result.

    Delete this and the widening can be reverted with the suite green."""
    found = value_shaped_literals(_a_repository(tmp_path))

    assert any("docs/log.md" in one for one in found), found
    assert SEARCHED["docs"] is not None and ".md" in SEARCHED["docs"]


def test_the_sweep_can_say_what_it_read(tmp_path: Path) -> None:
    """A check that cannot name what it looked at has a green meaning "nothing was found
    somewhere", and this one was green over `ops` and `.env.example` for as long as it
    existed because nobody could ask.

    Delete this and `brain.deployment.audit` loses the only way it has of proving it is not a
    second opinion about a file the gate already reads."""
    root = _a_repository(tmp_path)
    read = {one.relative_to(root).as_posix() for one in searched_files(root)}

    assert ".env.example" in read
    assert "ops/deploy/brain-deploy" in read
    assert "docs/log.md" in read, "served Markdown joined on 2026-09-09; see the test above"


def test_this_products_build_provenance_is_allowed_and_is_not_a_name_to_pass_a_check() -> None:
    """**The two allowlist entries added on 2026-09-09, held to their reason.**
    `A_BLOCKLIST_OF_ONE_CLIENTS_NAMES_PASSES_FOR_EVERY_OTHER_CLIENT` argues against solving
    this with a list, and the argument applies just as hard to widening one: an entry added
    because it made the sweep pass is how the check stops working.

    So each is tied to the thing that needs it rather than to itself. A Sigstore verification
    is an assertion about two fixed strings, the workflow identity and the issuer that minted
    the certificate, and both are read out of the scripts that verify rather than repeated
    here. Neither can become a client's, exactly as `ghcr.io` beside them cannot.

    Delete this and either entry can stay in the list after the check that needed it is gone,
    which is an allowlist entry with no reason and the beginning of a longer one."""
    verifying = "\n".join(
        (REPO / "ops" / one).read_text(encoding="utf-8")
        for one in ("deploy.sh", "watch-and-deploy.sh")
    )

    assert "--certificate-identity-regexp" in verifying
    assert "https://github.com/" in verifying
    assert "https://token.actions.githubusercontent.com" in verifying

    assert {"github.com", "token.actions.githubusercontent.com"} <= ALLOWED_HOSTS


def test_a_private_range_is_allowed_and_a_private_address_is_not() -> None:
    """**The distinction is the prefix length and nothing else.**
    `ops/automation/egress.conf` says `acl sandbox src 172.16.0.0/12`, which is the sandbox
    network on every install and names nobody. `10.4.0.17` on its own is the shape of a
    client's own directory or database host, and that is the value an implementer hardcodes
    because it is the only one they can see.

    Strict, so an address written with a mask is still an address, and more than one address,
    so a `/32` host cannot be spelled as a range.

    Delete this and the rule can be widened to "any private address", which waves through the
    one thing it exists to catch."""
    assert is_reserved_range("10.0.0.0/8")
    assert is_reserved_range("172.16.0.0/12 is the sandbox")

    assert not is_reserved_range("10.4.0.17")
    assert not is_reserved_range("10.4.0.17/8"), "host bits set: that is an address and a mask"
    assert not is_reserved_range("203.0.113.9/32"), "one address is a host, not a range"
    assert not is_reserved_range("198.51.100.7/24"), "not a private range"
