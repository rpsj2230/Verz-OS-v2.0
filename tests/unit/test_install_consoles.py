"""The administrative console decision, held where an operator setting up a server reads it.

**M37.6.1.3** asks for a decision on the administrative consoles to be made and written down,
with its reasons. It was made on Needs Rupash item 61: the consoles stay on public addresses,
each behind a second factor and an IP allowlist. It is written in `docs/install/network.md`,
and what can be held of it is held here: the four consoles it covers, that no row goes without
either protection, the options that were rejected, the allowlist the panel's proxy template
carries, and whether the vault's interface is served at all.

Every refusal is produced by breaking the real page or the real template one cell or one key
at a time, so the check that passes them and the checks that refuse them are about the same
documents.

Whether a console's second factor is switched on is not here and cannot be: it is a setting on
each account inside each console, on each server.

Task ids: M37.6.1.3
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops.install_docs import (
    A_PUBLIC_CONSOLE_NEEDS_A_SECOND_FACTOR_AND_AN_ALLOWLIST,
    ALLOWLIST_MIDDLEWARE,
    REJECTED_CONSOLE_OPTIONS,
    InstallDocsError,
    console_gaps,
    panel_allowlist_gaps,
    vault_interface_served,
)

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs" / "install" / "network.md"
TEMPLATE = REPO / "ops" / "vps" / "traefik-coolify-panel.yaml"
VAULT = REPO / "ops" / "openbao" / "compose.yml"


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def template() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    return parsed


def vault() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(VAULT.read_text(encoding="utf-8"))
    return parsed


def served() -> bool:
    return vault_interface_served(vault())


def _row_index(lines: list[str], first: str) -> int:
    hits = [index for index, line in enumerate(lines) if line.startswith(f"| `{first}` |")]
    assert len(hits) == 1, f"the page has {len(hits)} row(s) for {first!r}"
    return hits[0]


def with_cell(text: str, first: str, index: int, value: str) -> str:
    """The page with one cell of one row replaced."""
    lines = text.splitlines(keepends=True)
    at = _row_index(lines, first)
    cells = lines[at].strip().strip("|").split("|")
    cells[index] = f" {value} "
    lines[at] = "|" + "|".join(cells) + "|\n"
    return "".join(lines)


def without_row(text: str, first: str) -> str:
    lines = text.splitlines(keepends=True)
    del lines[_row_index(lines, first)]
    return "".join(lines)


def with_row_after(text: str, first: str, row: str) -> str:
    lines = text.splitlines(keepends=True)
    lines.insert(_row_index(lines, first) + 1, row + "\n")
    return "".join(lines)


# ======================================================================== the page as written
def test_the_network_page_records_the_console_decision() -> None:
    """**M37.6.1.3.** The decision is on the page an operator reads while putting a proxy in front
    of the server, with every console, both protections for each, and what was rejected.

    Delete this and the page can lose a console or a protection while reading as complete, and
    the decision becomes whatever the page happens to say."""
    assert console_gaps(page(), vault_served=served()) == ()


def test_the_decision_names_both_protections_and_the_option_it_rejected() -> None:
    """The reason constant is what survives the person who wrote the page, so it has to state the
    rule rather than gesture at it: two protections, and the tunnel it was chosen over.

    Delete this and the constant can be shortened to a sentence that no longer says why one of
    the two is not enough."""
    reason = A_PUBLIC_CONSOLE_NEEDS_A_SECOND_FACTOR_AND_AN_ALLOWLIST
    assert "second factor" in reason
    assert "IP allowlist" in reason
    assert "SSH tunnel" in reason
    assert any("SSH tunnel" in option for option in REJECTED_CONSOLE_OPTIONS)


# ============================================================================ page refusals
def test_a_console_the_page_does_not_list_is_a_finding() -> None:
    """The direction a reader notices, eventually. Delete this and the trace ledger's dashboard can
    fall off the page and be put on a public address with a password alone."""
    broken = without_row(page(), "trace ledger dashboard")

    assert console_gaps(broken, vault_served=served()) == (
        "'trace ledger dashboard': a console the decision covers and the page does not list",
    )


def test_a_console_the_decision_does_not_cover_is_a_finding() -> None:
    """The direction nobody notices: a row reads as coverage. Delete this and a renamed console
    leaves its old row behind looking protected."""
    extra = "| `old panel` | everything | yes | yes | nothing |"
    broken = with_row_after(page(), "trace ledger dashboard", extra)

    assert console_gaps(broken, vault_served=served()) == (
        "'old panel': a console the page lists and the decision does not cover, which reads as "
        "coverage",
    )


@pytest.mark.parametrize("absent", ["", "none", "No", "nothing", "n/a"])
def test_a_console_with_no_second_factor_is_a_finding(absent: str) -> None:
    """The decision is two protections, and a row that states only one is the design that was
    not chosen. Delete this and a row can say "none" in the second factor column and pass."""
    broken = with_cell(page(), "identity provider admin console", 2, absent)

    assert console_gaps(broken, vault_served=served()) == (
        "identity provider admin console: no second factor, and the decision requires one",
    )


def test_a_console_with_no_allowlist_is_a_finding() -> None:
    """The sibling of the second factor refusal, for the other protection. Delete this and the
    allowlist column can be emptied for the dashboard nobody thinks of as administrative."""
    broken = with_cell(page(), "trace ledger dashboard", 3, "none")

    assert console_gaps(broken, vault_served=served()) == (
        "trace ledger dashboard: no IP allowlist, and the decision requires one",
    )


def test_the_panels_allowlist_must_be_the_middleware_its_template_defines() -> None:
    """The one row whose allowlist this repository carries as configuration, so the page names
    it by the name the template gives it. Delete this and the page and the template can drift
    apart, with a reader configuring a middleware nothing defines."""
    broken = with_cell(page(), "deployment panel", 3, "an allowlist on the proxy")

    assert console_gaps(broken, vault_served=served()) == (
        f"deployment panel: the allowlist cell does not name `{ALLOWLIST_MIDDLEWARE}`, the "
        "middleware its proxy template defines",
    )


def test_the_vaults_row_must_agree_with_whether_its_interface_is_served() -> None:
    """Both directions. A page saying the interface is not served while the compose file switches
    it on tells an operator there is nothing to protect; a page saying it is served while it is
    off sends somebody looking for a sign-in page that does not exist.

    Delete this and `ui = true` can ship with the page still reading "Not served"."""
    assert console_gaps(page(), vault_served=True) == (
        "secrets vault interface: the vault's compose file switches its interface on and the "
        "page says otherwise",
    )
    broken = with_cell(page(), "secrets vault interface", 4, "Served on its own address")
    assert console_gaps(broken, vault_served=False) == (
        "secrets vault interface: the vault's compose file switches its interface off and the "
        "page says otherwise",
    )
    assert console_gaps(broken, vault_served=True) == ()


def test_a_console_row_with_too_few_cells_is_a_finding_rather_than_an_error() -> None:
    """A row that lost its cells cannot be read for either protection, and an IndexError would
    report a broken check rather than a broken page. Delete this and a truncated row crashes the
    test that should have named it."""
    lines = page().splitlines(keepends=True)
    at = _row_index(lines, "deployment panel")
    lines[at] = "| `deployment panel` | everything |\n"
    broken = "".join(lines)

    found = console_gaps(broken, vault_served=served())

    assert found[0].startswith("a row with 2 cell(s)")
    assert found[1:] == (
        "'deployment panel': a console the decision covers and the page does not list",
    )


def test_a_rejected_option_the_page_does_not_record_is_a_finding() -> None:
    """A decision written without its alternatives is reopened by the next reader, because the
    argument against them is the half that gets lost. Delete this and the tunnel's row can be
    removed and the decision reads as though nobody weighed it."""
    broken = without_row(page(), "an SSH tunnel on every install")

    assert console_gaps(broken, vault_served=served()) == (
        "'an SSH tunnel on every install': an option that was rejected and the page does not "
        "record",
    )


def test_a_rejected_option_nobody_considered_is_a_finding() -> None:
    """The other direction: a straw alternative added to make the choice look weighed. Delete this
    and the table can grow options the decision never saw."""
    broken = with_row_after(page(), "a choice made per client", "| `a VPN` | too much work |")

    assert console_gaps(broken, vault_served=served()) == (
        "'a VPN': a rejected option the decision never considered",
    )


def test_a_rejected_option_with_no_reason_is_a_finding() -> None:
    """An option named with no reason is the half of the record that matters, missing. Delete this
    and the reason column can be emptied with every name still in place."""
    broken = with_cell(page(), "a choice made per client", 1, "")

    found = console_gaps(broken, vault_served=served())

    assert found[0].startswith("a rejected option reads")
    assert found[1:] == (
        "'a choice made per client': an option that was rejected and the page does not record",
    )


# ================================================================ the panel's proxy template
def test_the_panel_template_passes_every_router_through_the_allowlist_first() -> None:
    """The half of the decision this repository can carry as configuration. Delete this and the
    template can lose the middleware from one router, which is a panel reachable from every
    address on that route with the page still describing an allowlist."""
    assert panel_allowlist_gaps(template()) == ()


def test_a_router_without_the_allowlist_is_a_finding() -> None:
    """Delete this and the HTTPS router, the one a browser actually signs in through, can drop the
    middleware while the redirect router keeps it."""
    route = copy.deepcopy(template())
    del route["http"]["routers"]["coolify-panel-https"]["middlewares"]

    assert panel_allowlist_gaps(route) == (
        f"coolify-panel-https: answers before {ALLOWLIST_MIDDLEWARE} is consulted, so the panel "
        "is reachable from any address on this route",
    )


def test_a_router_that_consults_the_allowlist_second_is_a_finding() -> None:
    """First, not merely present: a middleware ahead of it answers an address the allowlist would
    refuse. Delete this and the redirect can be moved in front of it."""
    route = copy.deepcopy(template())
    chain = route["http"]["routers"]["coolify-panel-http"]["middlewares"]
    chain.reverse()

    assert panel_allowlist_gaps(route) == (
        f"coolify-panel-http: answers before {ALLOWLIST_MIDDLEWARE} is consulted, so the panel "
        "is reachable from any address on this route",
    )


def test_a_router_that_is_not_a_mapping_is_a_finding() -> None:
    """Delete this and a router written as a bare string reads as having no middleware to check
    and raises instead of being named."""
    route = copy.deepcopy(template())
    route["http"]["routers"]["coolify-panel-http"] = "Host(`x`)"

    assert panel_allowlist_gaps(route) == (
        f"coolify-panel-http: answers before {ALLOWLIST_MIDDLEWARE} is consulted, so the panel "
        "is reachable from any address on this route",
    )


@pytest.mark.parametrize(
    "damage",
    ["missing", "not_an_allowlist", "no_range", "not_a_mapping"],
)
def test_an_allowlist_that_restricts_nothing_is_a_finding(damage: str) -> None:
    """A router naming a middleware that is absent, is not an allowlist, or lists no range has an
    allowlist in name only. The not-an-allowlist case is the indentation slip that writes the
    range one level too high, which carries a `sourceRange` and no middleware type at all.
    Delete this and `sourceRange` can be emptied with every router still naming the
    middleware."""
    route = copy.deepcopy(template())
    middlewares = route["http"]["middlewares"]
    if damage == "missing":
        del middlewares[ALLOWLIST_MIDDLEWARE]
    elif damage == "not_an_allowlist":
        middlewares[ALLOWLIST_MIDDLEWARE] = {"sourceRange": ["<admin-source-range>"]}
    elif damage == "no_range":
        middlewares[ALLOWLIST_MIDDLEWARE]["ipAllowList"]["sourceRange"] = []
    else:
        middlewares[ALLOWLIST_MIDDLEWARE] = "admin-allowlist"

    assert panel_allowlist_gaps(route) == (
        f"{ALLOWLIST_MIDDLEWARE}: not defined as an ipAllowList with a sourceRange, so a router "
        "naming it restricts nothing",
    )


def test_a_template_with_no_router_is_a_finding() -> None:
    """An allowlist nothing routes through guards nothing, and an empty router table would
    otherwise pass by having no router to fail. Delete this and that is a clean result."""
    route = copy.deepcopy(template())
    route["http"]["routers"] = {}

    assert panel_allowlist_gaps(route) == (
        "the panel template defines no router, so the allowlist guards nothing",
    )


def test_a_template_with_no_http_section_is_refused() -> None:
    """Refused rather than reported as clean, because no routers at all would otherwise read as no
    routers that skip the allowlist. Delete this and a template rewritten under another key
    passes."""
    with pytest.raises(InstallDocsError):
        panel_allowlist_gaps({"tcp": {}})


# =========================================================================== the vault's switch
def test_the_vault_interface_is_off_as_shipped() -> None:
    """What the page's "Not served" row rests on. Delete this and the row is checked against a
    reading nobody pinned."""
    assert served() is False


def test_the_vault_interface_is_read_as_on_when_the_configuration_switches_it_on() -> None:
    """The positive sibling. A reader that always answered "off" would pass the test above and
    agree with the page for ever. Delete this and it can."""
    switched_on = copy.deepcopy(vault())
    environment = switched_on["services"]["vault"]["environment"]
    environment["BAO_LOCAL_CONFIG"] = environment["BAO_LOCAL_CONFIG"].replace(
        "ui = false", "ui = true"
    )

    assert vault_interface_served(switched_on) is True


def test_a_configuration_that_sets_no_interface_leaves_it_off() -> None:
    """The server's default is off, and a configuration without the line is read that way rather
    than as an error. Delete this and removing the line looks like a way to switch it on."""
    assert (
        vault_interface_served(
            {"services": {"vault": {"environment": {"BAO_LOCAL_CONFIG": 'storage "file" {}\n'}}}}
        )
        is False
    )


@pytest.mark.parametrize(
    "compose",
    [
        {"services": {}},
        {"services": {"vault": {"environment": ["BAO_LOCAL_CONFIG=ui = true"]}}},
        {"services": {"vault": {"environment": {"BAO_LOCAL_CONFIG": 1}}}},
    ],
)
def test_a_vault_configuration_that_cannot_be_read_is_refused(compose: dict[str, Any]) -> None:
    """Answering "off" for a compose file whose configuration moved would be the check agreeing
    with the page about a setting it never read. Delete this and it does."""
    with pytest.raises(InstallDocsError):
        vault_interface_served(compose)
