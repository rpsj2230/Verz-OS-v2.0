"""The install documentation, held to the registers it describes.

Four documents under `docs/install/` state something a machine can check, and this is the check.
Delete this file and every one of them goes on looking complete while the product moves
underneath it: a variable added to the template, a step appended to the installer, a port opened
by a new service, a connector installed or removed. None of those would fail anything else here,
because nothing else in this repository reads a document and compares it to a declaration.

**Every refusal is exercised against a guide built to fail as well as against the real one.**
That is `brain.ops.wiring.trace_stack_gaps`' argument restated: a check that can only ever be
run against the real document has no test for the case it exists to find, and this repository
has shipped three checks whose bodies could be replaced with `return ()` without a test
noticing. So each finding below has a test that produces it and a sibling proving the real
document does not.

The registers are read here rather than inside the module, in the split `brain.ops.compose` and
`brain.deployment.requirements` both keep: `yaml.safe_load` and `Path.read_text` belong in the
test, so what is checked is the deployment rather than a second copy of it kept in Python.

Task ids: M42.2.3, M42.2.4, M42.2.5, M42.2.6, M42.2.8
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.connectors.contract import AccessMode, CredentialBinding
from brain.connectors.freshdesk import manifest as freshdesk_manifest
from brain.connectors.google_drive import DriveConnection
from brain.connectors.google_drive import manifest as drive_manifest
from brain.connectors.hubspot import HubSpotConnection, hubspot_manifest
from brain.connectors.laravel import LaravelConnection, ReadBounds, laravel_manifest
from brain.connectors.lark_base import FieldBinding, FieldKind, LarkBaseTable
from brain.connectors.lark_base import manifest as lark_base_manifest
from brain.connectors.lark_wiki import SpaceDeclaration
from brain.connectors.lark_wiki import manifest as lark_wiki_manifest
from brain.connectors.manifest import ConnectorManifest, FieldShape, HotUse, PermissionSync
from brain.connectors.xero import XeroConnection, xero_manifest
from brain.core.scope import Clause, Op, Scope
from brain.deployment.installer import PLAN, render
from brain.deployment.installer import Step as InstallStep
from brain.deployment.release import included_by, refused_by
from brain.deployment.requirements import (
    COMPOSE_FILES_FOR,
    RUNTIME_REQUIREMENTS,
    exposed_ports,
    files_for,
    spec_for,
)
from brain.deployment.variables import parse_env
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.controls import control
from brain.ops.install_docs import (
    A_BLANK_DEFAULT_AND_AN_EMPTY_ONE_ARE_THE_SAME_LINE_ON_A_SERVER,
    CHECKLIST_SECTIONS,
    CONNECTORS_MARKER,
    HIDDEN_LINKS,
    LINKS_MARKER,
    MANIFEST_BUILDER,
    MECHANISMS_MARKER,
    NO_CEILING,
    OPTIONAL_STEP,
    PORTS_MARKER,
    QUEUE_STEPS_MARKER,
    REQUIRED_STEP,
    STEPS_MARKER,
    THE_REGISTER_IS_MORE_THAN_THE_TEMPLATE,
    TIMERS_MARKER,
    TOOL_NAMES_ARE_NOT_A_PROPERTY_OF_EVERY_CONNECTOR,
    TROUBLESHOOTING_CLOSING,
    UPDATE_SCRIPTS_HOME,
    UPDATE_SCRIPTS_MARKER,
    VALUES_MARKER,
    WHAT_TO_DO,
    InstallDocsError,
    Provenance,
    Variable,
    bare,
    ceiling_cell,
    checklist_gaps,
    configuration_gaps,
    connector_gaps,
    connector_modules,
    default_cell,
    integration_gaps,
    interpolations,
    mechanism_gaps,
    minted_variables,
    port_gaps,
    profiles_cell,
    queue_step_gaps,
    scheduled_job_gaps,
    script_variables,
    sections,
    step_gaps,
    table_after,
    troubleshooting_gaps,
    update_script_gaps,
    variables,
    wizard_settings,
)
from brain.ops.limits import FRESHDESK_SEARCH_MAX_RECORDS
from brain.ops.queue import DeployStep, StepKind
from brain.ops.secrets import SecretRef, VaultRole
from brain.ops.wiring import PROFILES, WiringError
from brain.setup_wizard import WIZARD

REPO = Path(__file__).resolve().parents[2]
GUIDES = REPO / "docs" / "install"
CONNECTOR_PACKAGE = REPO / "src" / "brain" / "connectors"


# ------------------------------------------------------------------------------ the registers
def parsed(names: tuple[str, ...]) -> dict[str, Any]:
    """The named compose files, parsed. See the module docstring for why this is here."""
    return {name: yaml.safe_load((REPO / name).read_text(encoding="utf-8")) for name in names}


def template() -> dict[str, str]:
    return parse_env((REPO / ".env.example").read_text(encoding="utf-8"))


def compose_by_profile() -> dict[str, dict[str, Any]]:
    return {profile: parsed(files_for(profile)) for profile in COMPOSE_FILES_FOR}


def rendered_installer() -> str:
    """The installer as it is written for the smallest profile, with its real figures.

    The real figures rather than placeholders, so that the script the register is read out of
    is one a client could run rather than one this test invented.
    """
    files = parsed(files_for("lite"))
    spec = spec_for("lite", files)
    return render("lite", services=spec.containers, memory_mib=spec.memory_mib)


def register() -> tuple[Variable, ...]:
    return variables(
        template=template(),
        minted=minted_variables(PLAN),
        wizard=wizard_settings(WIZARD),
        compose=compose_by_profile(),
        script=script_variables(rendered_installer()),
    )


def guide(name: str) -> str:
    return (GUIDES / name).read_text(encoding="utf-8")


def every_compose_file() -> dict[str, Any]:
    """Every file any declared profile composes, so a port in any of them is covered."""
    return parsed(
        tuple(sorted({one for profile in COMPOSE_FILES_FOR for one in files_for(profile)}))
    )


# ------------------------------------------------------------------- the connector manifests
def ref(path: str) -> SecretRef:
    return SecretRef(path=path, role=VaultRole.APPLICATION)


#: A visibility predicate with no person in it, for the connectors whose manifest needs one.
#: Departments rather than principals, because a predicate enumerating principals is refused.
VISIBILITY = Scope(clauses=(Clause(field="department", op=Op.IN, value=("one", "two")),))

#: One projected field, which is the least a Lark Base manifest can be built with.
BINDINGS = (
    FieldBinding(
        target="client",
        base_field="Client",
        kind=FieldKind.TEXT,
        uses=(HotUse.JOIN,),
        shape=FieldShape.JOIN_KEY,
    ),
)


def lark_base_for(entity: str) -> ConnectorManifest:
    """One Lark Base manifest, for a named entity.

    Parameterised because the entity is what makes its tool names differ between installs,
    which is the property `TOOL_NAMES_ARE_NOT_A_PROPERTY_OF_EVERY_CONNECTOR` states.
    """
    return lark_base_manifest(
        LarkBaseTable(
            base_id="bascnCMII2ORej2RItqpZZUNMIe",
            table_id="tblsRc9GRRXKqhvW",
            entity=entity,
            bindings=BINDINGS,
        ),
        host="open.larksuite.com",
        credential=CredentialBinding(ref=ref("connectors/creds/lark_base")),
        visibility=VISIBILITY,
    )


def manifests() -> tuple[ConnectorManifest, ...]:
    """Every connector's manifest, built with placeholder deployment values.

    Placeholders rather than any install's real ones, and it costs nothing: every field this
    guide states is a property of the connector rather than of the deployment, so the selectors
    below could be anything a scope accepts.
    """
    return (
        freshdesk_manifest(
            domain="helpdesk.example.invalid",
            credential=CredentialBinding(ref=ref("connectors/creds/freshdesk")),
            visibility=VISIBILITY,
        ),
        drive_manifest(
            DriveConnection(
                folder_id="fld0447AbC-_x",
                domain="example.invalid",
                department="one",
                steward_id="u_one",
            ),
            ref=ref("connectors/creds/google_drive"),
        ),
        hubspot_manifest(
            HubSpotConnection(portal_id="12345678"), ref=ref("connectors/creds/hubspot")
        ),
        laravel_manifest(
            LaravelConnection(
                schema="portal", bounds=ReadBounds(max_rows=200, timeout_seconds=5.0)
            ),
            ref=ref("connectors/creds/laravel_readonly"),
            visibility={"client": VISIBILITY, "user": VISIBILITY},
        ),
        lark_base_for("maintenance"),
        lark_wiki_manifest(
            spaces=(
                SpaceDeclaration(
                    space_id="spcOne",
                    visibility=KnowledgeVisibility.of_department("one", owner_id="u_one"),
                    owner_id="u_one",
                ),
            ),
            credential=CredentialBinding(ref=ref("connectors/creds/lark_wiki")),
        ),
        xero_manifest(
            XeroConnection(tenant_id="11111111-2222-3333-4444-555555555555"),
            ref=ref("connectors/creds/xero"),
        ),
    )


# --------------------------------------------------------------------- small guides to fail on
def a_table(marker: str, header: str, *rows: str) -> str:
    """A document carrying one marked table, for exercising a refusal."""
    columns = header.count("|") - 1
    rule = "| " + " | ".join("---" for _ in range(columns)) + " |"
    return "\n".join(("# a guide", "", marker, "", header, rule, *rows, "", "the end")) + "\n"


VALUES_HEADER = "| Variable | Profiles | Comes from | Default | What it is for |"
PORTS_HEADER = "| Service | Port | Who may reach it |"
MECHANISMS_HEADER = "| Mechanism | What it would guard | Started by |"
STEPS_HEADER = "| Step | What it does | If it fails |"
CONNECTORS_HEADER = "| Connector | Transport | Pinned to | Access | Enforces | Ceiling |"
QUEUE_STEPS_HEADER = "| Step | What it does | Skippable |"


def a_variable(name: str, **overrides: Any) -> Variable:
    settings: dict[str, Any] = {
        "name": name,
        "comes_from": Provenance.YOU,
        "has_default": True,
        "profiles": PROFILES,
    }
    settings.update(overrides)
    return Variable(**settings)


def a_connector_guide(*rows: str, sections: tuple[str, ...] = ("freshdesk",)) -> str:
    body = a_table(CONNECTORS_MARKER, CONNECTORS_HEADER, *rows)
    return body + "\n" + "\n".join(f"## `{one}`\n\nprose\n" for one in sections)


# ============================================================================= table_after
def test_a_guide_with_no_marker_is_refused_rather_than_read_as_having_no_findings() -> None:
    """Delete this and a document whose marker somebody renamed comes back with no rows, so
    every check over it reports one finding per declared thing and reads as a formatting
    mistake rather than as a guide that no longer contains the table being checked."""
    with pytest.raises(InstallDocsError, match="carries no"):
        table_after("# a guide\n\nnothing here\n", VALUES_MARKER)


def test_a_marker_with_no_table_after_it_is_refused() -> None:
    """Delete this and a marker left behind after somebody removed the table it marked reads
    as a table with nothing in it, which is the state that must never be silent."""
    with pytest.raises(InstallDocsError, match="row"):
        table_after(f"{VALUES_MARKER}\n\njust prose\n", VALUES_MARKER)


def test_a_table_of_only_a_header_and_a_rule_is_refused() -> None:
    """Delete this and a table emptied of its rows passes as a table, because the header and
    the rule are two rows and a length check on 'any rows at all' would accept them."""
    with pytest.raises(InstallDocsError, match="2 row"):
        table_after(a_table(PORTS_MARKER, PORTS_HEADER), PORTS_MARKER)


def test_the_header_and_the_rule_are_not_returned_as_data() -> None:
    """Delete this and the word 'Service' is compared against the compose files as though it
    were a service name, so every real row is reported as extra and the header as missing."""
    rows = table_after(
        a_table(PORTS_MARKER, PORTS_HEADER, "| `db` | `5432` | nobody |"), PORTS_MARKER
    )
    assert rows == (("`db`", "`5432`", "nobody"),)


def test_a_table_ends_at_the_first_line_that_is_not_a_row() -> None:
    """Delete this and a second table further down the page is read as a continuation of the
    first, so rows from an unrelated table are checked against this register."""
    text = (
        f"{PORTS_MARKER}\n\n{PORTS_HEADER}\n| --- | --- | --- |\n| `db` | `5432` | nobody |\n"
        "\nprose in between\n\n| Other | Table |\n| --- | --- |\n| `x` | `y` |\n"
    )
    assert table_after(text, PORTS_MARKER) == (("`db`", "`5432`", "nobody"),)


def test_prose_between_the_marker_and_the_table_is_skipped() -> None:
    """Delete this and a marker cannot be followed by a sentence introducing its own table,
    which is how every one of these guides is actually written."""
    text = (
        f"{PORTS_MARKER}\n\nA sentence.\n\n{PORTS_HEADER}\n| --- | --- | --- |\n"
        "| `db` | `5432` | nobody |\n"
    )
    assert table_after(text, PORTS_MARKER) == (("`db`", "`5432`", "nobody"),)


def test_a_cell_is_compared_without_its_code_span() -> None:
    """Delete this and a table has to choose between being readable and being checkable: every
    name in these guides is written in a code span and the registers hold bare strings."""
    assert bare("` db `") == "db"
    assert bare("db") == "db"


# ======================================================================== the minted register
def test_the_installer_writes_five_values_and_the_register_reads_them_off_the_plan() -> None:
    """The fifth is `APP_IMAGE`, since 2026-09-15. Needs Rupash item 51 made the compose files
    require it, so the install writes it from the tag it unpacked and the guide's provenance
    column says the installer supplies it rather than asking a client to type it.

    Delete this and a sixth value added to the plan is a value every install has and no guide
    mentions, which is the exact failure a hand-kept list produces."""
    assert minted_variables(PLAN) == frozenset(
        {
            "POSTGRES_PASSWORD",
            "APP_ROLE_PASSWORD",
            "BRAIN_SETUP_SECRET",
            "BRAIN_SETUP_ISSUED_AT",
            "APP_IMAGE",
        }
    )


def test_a_step_that_writes_nothing_cannot_mint_a_value() -> None:
    """Delete this and the plan's last step, which prints the setup code and changes nothing,
    is read as minting one, so a value that is only ever displayed is documented as generated."""
    printing = InstallStep(
        name="show it",
        run='printf "POSTGRES_PASSWORD=%s\\n" "$value"',
        why="it prints",
        on_failure="read the file",
        changes=False,
        presents_once=True,
    )
    assert minted_variables((printing,)) == frozenset()


def test_the_wizard_register_names_only_the_settings_a_screen_stores() -> None:
    """Delete this and every wizard answer is read as a setting, including the setup code and
    the provider key, so two secrets appear in a guide as values a person types into a file."""
    assert wizard_settings(WIZARD) == frozenset(
        {
            "INSTALL_COMPANY_NAME",
            "INSTALL_PRODUCT_NAME",
            "INSTALL_LOGO_URL",
            "INSTALL_MODEL_PROFILE",
            "INSTALL_STAFF_SOURCE",
            "INSTALL_STAFF_SOURCE_LOCATION",
        }
    )


# ================================================================ compose interpolations
def test_a_bare_interpolation_supplies_no_default() -> None:
    """Delete this and `${POSTGRES_PASSWORD}` is documented as having a default, so a reader
    leaves it unset, the container starts with an empty password and the failure is reported
    as an authentication problem."""
    assert interpolations({"environment": {"P": "${POSTGRES_PASSWORD}"}}) == {
        "POSTGRES_PASSWORD": False
    }


def test_an_empty_dash_default_supplies_no_default_either() -> None:
    """Delete this and `${APP_ROLE_PASSWORD:-}` reads as supplied, which is the same wrong
    answer arriving through the one form that looks deliberate."""
    assert interpolations({"e": "${APP_ROLE_PASSWORD:-}"}) == {"APP_ROLE_PASSWORD": False}
    assert "empty" in A_BLANK_DEFAULT_AND_AN_EMPTY_ONE_ARE_THE_SAME_LINE_ON_A_SERVER


def test_a_required_interpolation_supplies_no_default() -> None:
    """Delete this and `${INFERENCE_IMAGE:?...}`, which exists precisely to stop the stack
    starting without a value, is documented as one a client can leave alone."""
    assert interpolations({"image": "${INFERENCE_IMAGE:?set it}"}) == {"INFERENCE_IMAGE": False}


def test_a_dash_default_with_a_value_supplies_one() -> None:
    """Delete this and every variable in the deployment reads as required, so a client is sent
    to set forty values of which twenty already work."""
    assert interpolations({"image": "${APP_IMAGE:-somewhere/an-image:1.2}"}) == {"APP_IMAGE": True}


def test_a_default_anywhere_counts_as_a_default_everywhere() -> None:
    """Delete this and a variable written with a default in one compose file and bare in
    another is reported according to whichever file was walked last, which is a finding that
    changes when somebody reorders a file list."""
    assert interpolations(["${A:-x}", "${A}"]) == {"A": True}
    assert interpolations(["${A}", "${A:-x}"]) == {"A": True}


def test_interpolations_are_found_inside_lists_and_mapping_keys() -> None:
    """Delete this and a variable used in a `command:` list or as a key is invisible to the
    register, so it is a value a client must set that no guide can be failed for omitting."""
    document = {"services": {"a": {"command": ["-c", "x=${IN_A_LIST}"], "${A_KEY}": 1}}}
    assert interpolations(document) == {"IN_A_LIST": False, "A_KEY": False}


def test_a_value_that_is_not_text_carries_no_interpolation() -> None:
    """Delete this and the walk has to be shown to handle a number, a boolean and a null, all
    three of which a compose file is full of; without it the first `mem_limit: 1024` raises."""
    assert interpolations({"a": 1, "b": True, "c": None}) == {}


# ============================================================================== the register
def test_a_value_the_installer_mints_is_in_the_register_and_not_in_the_template() -> None:
    """The property `THE_REGISTER_IS_MORE_THAN_THE_TEMPLATE` states. Delete this and a guide
    checked against the template alone passes while omitting the database password, which is
    set on every install."""
    assert "POSTGRES_PASSWORD" not in template()
    assert "POSTGRES_PASSWORD" in {one.name for one in register()}
    assert "POSTGRES_PASSWORD" in THE_REGISTER_IS_MORE_THAN_THE_TEMPLATE


def test_a_template_variable_belongs_to_every_profile() -> None:
    """Delete this and a value the application reads whatever is deployed beside it is
    documented as belonging to one profile, so a client on another profile skips it."""
    found = variables(template={"A": "x"}, minted=(), wizard=(), compose={})
    assert found == (a_variable("A"),)


def test_a_compose_variable_belongs_to_the_profiles_whose_files_name_it() -> None:
    """Delete this and every compose variable reads as belonging to every profile, so a client
    running the smallest one is sent to set twenty values for containers they do not have."""
    found = variables(
        template={},
        minted=(),
        wizard=(),
        compose={"lite": {}, "full": {"f.yml": {"image": "${ONLY_FULL:-x}"}}},
    )
    assert found == (a_variable("ONLY_FULL", profiles=("full",)),)


def test_the_register_refuses_a_profile_nobody_declared() -> None:
    """Delete this and a typo in a profile name silently contributes a set of variables to a
    profile that does not exist, and the guide is failed for not naming it."""
    with pytest.raises(WiringError, match="unknown profile"):
        variables(template={}, minted=(), wizard=(), compose={"lyte": {}})


def test_a_minted_value_is_attributed_to_the_installer_and_never_to_the_person() -> None:
    """Delete this and a guide can tell somebody to set a value the installer already minted,
    which on a second run writes a new database password beside the old volume."""
    found = variables(template={"S": ""}, minted=("S",), wizard=(), compose={})
    assert found[0].comes_from is Provenance.INSTALLER


def test_a_wizard_answer_is_attributed_to_the_wizard() -> None:
    """Delete this and a value a numbered screen asks for is documented as one to type into a
    file before starting, which is work nobody needed to do."""
    found = variables(template={"W": "x"}, minted=(), wizard=("W",), compose={})
    assert found[0].comes_from is Provenance.WIZARD


def test_the_installer_wins_over_the_wizard_when_a_value_is_in_both() -> None:
    """Delete this and a credential that some screen also collects is documented as typed,
    which is the direction that puts a minted secret in front of a person."""
    found = variables(template={"B": "x"}, minted=("B",), wizard=("B",), compose={})
    assert found[0].comes_from is Provenance.INSTALLER


def test_a_value_nothing_mints_and_no_screen_asks_for_is_the_persons_own() -> None:
    """Delete this and the residue disappears: every value would have to be minted or asked
    for, and the ones a person genuinely has to know about would have no honest label."""
    found = variables(template={"Y": "x"}, minted=(), wizard=(), compose={})
    assert found[0].comes_from is Provenance.YOU


def test_the_register_is_sorted_by_name() -> None:
    """Delete this and the table's order follows whatever order the compose files happen to be
    composed in, so a reader looking a variable up scans fifty-seven rows."""
    found = variables(template={"B": "x", "A": "x"}, minted=(), wizard=(), compose={})
    assert [one.name for one in found] == ["A", "B"]


def test_a_template_default_survives_a_compose_file_naming_the_same_variable_bare() -> None:
    """Delete this and a value the template supplies is reported as having none the moment a
    compose file interpolates it without a default of its own, which is most of them: compose
    reads the install's own environment file, so the template's value is what resolves."""
    found = variables(
        template={"A": "supplied"},
        minted=(),
        wizard=(),
        compose={"lite": {"f.yml": {"environment": {"A": "${A}"}}}},
    )
    assert found == (a_variable("A"),)


def test_an_empty_template_value_is_no_default() -> None:
    """Delete this and every blank line in the template reads as a supplied value, so the
    column that tells a client which values stop the install says the opposite."""
    found = variables(template={"E": "   "}, minted=(), wizard=(), compose={})
    assert found[0].has_default is False


def test_every_profile_is_rendered_as_a_phrase_and_a_subset_as_a_list() -> None:
    """Delete this and the guide either lists three profile names on forty rows, which nobody
    reads, or the check accepts both spellings and the column stops meaning anything."""
    assert profiles_cell(a_variable("A")) == "every profile"
    assert profiles_cell(a_variable("A", profiles=("standard", "full"))) == "standard, full"


def test_a_default_is_rendered_as_yes_or_none() -> None:
    """Delete this and the default column can be written any way at all, so a cell reading
    'blank' is accepted for a value that has no default and one that has an empty one."""
    assert default_cell(a_variable("A")) == "yes"
    assert default_cell(a_variable("A", has_default=False)) == "none"


# =================================================================== configuration_gaps
def test_the_configuration_guide_covers_every_value_a_client_must_set() -> None:
    """The leaf. Delete this and a variable added to the template, to the installer's mint step
    or to any profile's compose files is a value a client sets by reading a compose file, and
    the guide goes on looking complete."""
    assert configuration_gaps(guide("configuration.md"), register=register()) == ()


def test_a_variable_with_no_row_is_a_finding() -> None:
    """Delete this and the check is one-directional, which is the direction that lets the
    product grow past the guide without anything saying so."""
    found = configuration_gaps(
        a_table(VALUES_MARKER, VALUES_HEADER, "| `A` | every profile | you | yes | prose |"),
        register=(a_variable("A"), a_variable("B")),
    )
    assert found == ("B: no row, so a client sets it by reading a compose file or does not set it",)


def test_a_row_for_a_variable_no_register_declares_is_a_finding() -> None:
    """Delete this and a variable removed from the deployment stays in the guide for ever,
    which is worse than a missing row because it looks like work that was done."""
    found = configuration_gaps(
        a_table(
            VALUES_MARKER,
            VALUES_HEADER,
            "| `A` | every profile | you | yes | prose |",
            "| `GONE` | every profile | you | yes | prose |",
        ),
        register=(a_variable("A"),),
    )
    assert len(found) == 1
    assert found[0].startswith("GONE: a row for a variable no register declares")


def test_two_rows_for_one_variable_are_a_finding() -> None:
    """Delete this and a duplicated row is silently deduplicated, so two rows disagreeing about
    a default both pass and whichever a reader finds first is the one they act on."""
    found = configuration_gaps(
        a_table(
            VALUES_MARKER,
            VALUES_HEADER,
            "| `A` | every profile | you | yes | prose |",
            "| `A` | every profile | you | none | prose |",
        ),
        register=(a_variable("A"),),
    )
    assert found == ("A: two rows, and whichever a reader finds first is the one they act on",)


def test_a_row_with_too_few_cells_is_a_finding_rather_than_an_error() -> None:
    """Delete this and a row somebody left a column off raises an IndexError inside the check,
    so a formatting slip reads as a broken test rather than as a row to fix."""
    found = configuration_gaps(
        a_table(VALUES_MARKER, VALUES_HEADER, "| `A` | every profile |"),
        register=(a_variable("A"),),
    )
    assert any("cell(s)" in one for one in found)


def test_the_profile_column_is_checked_against_the_compose_files() -> None:
    """Delete this and a value belonging to one profile can be documented as belonging to all
    three, which sends a client hunting for a container they do not run."""
    found = configuration_gaps(
        a_table(VALUES_MARKER, VALUES_HEADER, "| `A` | full | you | yes | prose |"),
        register=(a_variable("A"),),
    )
    assert found == (
        "A: the profiles that read it reads 'full' and the registers say 'every profile'",
    )


def test_the_provenance_column_is_checked_against_the_plan_and_the_wizard() -> None:
    """Delete this and the column somebody most wants to be right can say anything, so a guide
    can tell a person to type a value the installer minted on their server."""
    found = configuration_gaps(
        a_table(VALUES_MARKER, VALUES_HEADER, "| `A` | every profile | installer | yes | prose |"),
        register=(a_variable("A"),),
    )
    assert found == ("A: where it comes from reads 'installer' and the registers say 'you'",)


def test_the_default_column_is_checked_against_the_template_and_the_compose_files() -> None:
    """Delete this and a value nothing supplies is documented as having a default, so it is
    left unset and the container starts with an empty string in place of a password."""
    found = configuration_gaps(
        a_table(VALUES_MARKER, VALUES_HEADER, "| `A` | every profile | you | none | prose |"),
        register=(a_variable("A"),),
    )
    assert found == ("A: whether it has a default reads 'none' and the registers say 'yes'",)


def test_a_row_wrong_about_two_things_reports_both() -> None:
    """Delete this and a check stopping at the first wrong cell makes fixing one row a sequence
    of test runs, which is the argument every other check in this repository makes."""
    found = configuration_gaps(
        a_table(VALUES_MARKER, VALUES_HEADER, "| `A` | full | installer | none | prose |"),
        register=(a_variable("A"),),
    )
    assert len(found) == 3


# ========================================================================= step_gaps
def test_the_written_install_lists_every_step_the_installer_runs() -> None:
    """The leaf. Delete this and a step appended to the installer leaves somebody following the
    written sequence one step short of a working install, with the guide reading as complete."""
    assert step_gaps(guide("install.md"), plan=PLAN) == ()


def test_a_step_the_guide_does_not_list_is_a_finding() -> None:
    """Delete this and the install plan can grow past the page that describes it, which is the
    drift that leaves a person's install broken in a way the page cannot explain."""
    found = step_gaps(
        a_table(STEPS_MARKER, STEPS_HEADER, f"| `{PLAN[0].name}` | does | read it |"), plan=PLAN
    )
    assert len(found) == len(PLAN) - 1
    assert all("the installer runs this step" in one for one in found)


def test_a_step_the_installer_does_not_run_is_a_finding() -> None:
    """Delete this and a step removed from the installer stays on the page, so somebody runs a
    command that is no longer part of the install and reads its failure as their own mistake."""
    rows = [f"| `{one.name}` | does | read it |" for one in PLAN]
    rows.append("| `sacrifice a goat` | does | read it |")
    found = step_gaps(a_table(STEPS_MARKER, STEPS_HEADER, *rows), plan=PLAN)
    assert found == ("'sacrifice a goat': the guide lists a step the installer does not run",)


def test_the_steps_are_checked_in_the_order_they_run() -> None:
    """Delete this and a page naming every step in the wrong order passes, which is a page
    telling somebody to mint credentials before the environment file they go into exists."""
    rows = [f"| `{one.name}` | does | read it |" for one in reversed(PLAN)]
    found = step_gaps(a_table(STEPS_MARKER, STEPS_HEADER, *rows), plan=PLAN)
    assert len(found) == 1
    assert found[0].startswith("the guide names every step and not in the order they run")


def test_the_order_is_not_reported_when_a_step_is_already_missing() -> None:
    """Delete this and a page with one step missing reports both that and an order finding
    listing all twelve, which buries the one line somebody can act on."""
    found = step_gaps(
        a_table(STEPS_MARKER, STEPS_HEADER, f"| `{PLAN[0].name}` | does | read it |"), plan=PLAN
    )
    assert not any("in the order they run" in one for one in found)


def test_a_step_row_with_too_few_cells_is_a_finding() -> None:
    """Delete this and a row missing its failure column raises inside the check rather than
    naming the row, so a formatting slip presents as a broken test."""
    found = step_gaps(a_table(STEPS_MARKER, STEPS_HEADER, "| `x` |"), plan=())
    assert found == (
        "a row with 1 cell(s) reads ('`x`',); every row states the step, what it does and "
        "what to do when it fails",
    )


# ========================================================================== port_gaps
def test_the_network_guide_accounts_for_every_port_this_deployment_opens() -> None:
    """The leaf. Delete this and a service added to a compose file with a port on it is a port
    nobody decided about, which is how a database ends up answering on an interface somebody
    assumed was internal."""
    assert port_gaps(guide("network.md"), exposed=exposed_ports(every_compose_file())) == ()


def test_a_service_that_opens_a_port_and_has_no_row_is_a_finding() -> None:
    """Delete this and the guide stops being a decision about reachability and becomes a list
    of the services that happened to exist when somebody wrote it."""
    found = port_gaps(
        a_table(PORTS_MARKER, PORTS_HEADER, "| `db` | `5432` | nobody |"),
        exposed={"db": ("5432",), "cache": ("6379",)},
    )
    assert found == (
        "cache: opens 6379 and the guide does not say who may reach it, so nobody decided "
        "whether the proxy or the firewall should",
    )


def test_a_row_for_a_service_that_opens_no_port_is_a_finding() -> None:
    """Delete this and a firewall decision about a service that no longer exists stays on the
    page, reading as a rule somebody is still keeping."""
    found = port_gaps(
        a_table(PORTS_MARKER, PORTS_HEADER, "| `gone` | `1234` | nobody |"), exposed={}
    )
    assert found == (
        "gone: a row for a service that opens no port, which reads as a decision somebody is "
        "still keeping",
    )


def test_a_port_number_that_does_not_match_the_compose_file_is_a_finding() -> None:
    """Delete this and a proxy or a firewall rule is written against a number somebody typed,
    which is the one thing on that page a person copies without checking."""
    found = port_gaps(
        a_table(PORTS_MARKER, PORTS_HEADER, "| `db` | `5433` | nobody |"), exposed={"db": ("5432",)}
    )
    assert found == ("db: the guide says port '5433' and the compose files open '5432'",)


def test_a_port_row_with_too_few_cells_is_a_finding() -> None:
    """Delete this and a row with no reachability column raises rather than reporting, so the
    one column that carries the decision can be dropped and read as a broken test."""
    found = port_gaps(a_table(PORTS_MARKER, PORTS_HEADER, "| `db` |"), exposed={})
    assert found == (
        "a row with 1 cell(s) reads ('`db`',); every row states the service, the port and "
        "who may reach it",
    )


# =================================================================== connector discovery
def test_the_seven_connectors_are_discovered_from_the_package() -> None:
    """Delete this and the guide is held to whatever list somebody handed the check, so a
    connector added tomorrow is not a finding but a gap nobody notices."""
    assert connector_modules(CONNECTOR_PACKAGE) == (
        "freshdesk",
        "google_drive",
        "hubspot",
        "laravel",
        "lark_base",
        "lark_wiki",
        "xero",
    )


def test_a_module_with_no_manifest_builder_is_not_a_connector(tmp_path: Path) -> None:
    """Delete this and every module in the package counts, so `throttle`, `registry` and
    `manifest` are each reported as a connector with no section in the guide."""
    (tmp_path / "helper.py").write_text("def thing() -> int:\n    return 1\n", newline="\n")
    assert connector_modules(tmp_path) == ()


def test_the_package_initialiser_is_never_a_connector(tmp_path: Path) -> None:
    """Delete this and a package whose `__init__` re-exports a builder is itself reported as a
    connector, and the guide is failed for having no section called `__init__`."""
    body = f"def manifest() -> {MANIFEST_BUILDER}:\n    return 1\n"
    (tmp_path / "__init__.py").write_text(body, newline="\n")
    assert connector_modules(tmp_path) == ()


def test_a_builder_nested_inside_a_function_is_not_a_connector(tmp_path: Path) -> None:
    """Delete this and a helper that builds a manifest inside another function makes its module
    a connector, which is how a fixture becomes a source the guide has to describe."""
    body = f"def outer() -> None:\n    def manifest() -> {MANIFEST_BUILDER}:\n        return 1\n"
    (tmp_path / "nested.py").write_text(body, newline="\n")
    assert connector_modules(tmp_path) == ()


def test_a_builder_is_recognised_by_what_it_returns_and_not_by_its_name(tmp_path: Path) -> None:
    """Delete this and a scan by function name finds the four connectors that call theirs
    `manifest` and reports the three that call theirs `<name>_manifest` as absent."""
    body = f"def anything_at_all() -> {MANIFEST_BUILDER}:\n    return 1\n"
    (tmp_path / "odd.py").write_text(body, newline="\n")
    assert connector_modules(tmp_path) == ("odd",)


def test_the_check_is_told_about_every_connector_the_package_declares() -> None:
    """Delete this and the integration guide can be held to a subset of the connectors, so
    every claim it makes is about a set nobody was told was partial."""
    assert connector_gaps(connector_modules(CONNECTOR_PACKAGE), manifests()) == ()


def test_a_connector_with_no_manifest_handed_to_the_check_is_a_finding() -> None:
    """Delete this and adding a connector module without adding it here silently narrows what
    the guide is checked against, which is the quietest way for this whole file to stop
    meaning anything."""
    found = connector_gaps((*connector_modules(CONNECTOR_PACKAGE), "brand_new"), manifests())
    assert len(found) == 1
    assert found[0].startswith("brand_new: the package declares a manifest builder")


def test_a_manifest_for_a_module_that_does_not_exist_is_a_finding() -> None:
    """Delete this and a connector deleted from the package leaves its fixture behind, so the
    guide keeps a section for a source nobody can install."""
    found = connector_gaps((), (manifests()[0],))
    assert found == ("freshdesk: a manifest for a connector this package has no module for",)


# ==================================================================== integration_gaps
def test_the_integration_guide_describes_every_connector_from_its_own_manifest() -> None:
    """The leaf. Delete this and the sentence saying what a source is trusted to read is prose
    beside the declaration rather than a claim checked against it, which is the failure that
    puts a console, or a page, saying a source is permission-aware when it is not."""
    assert integration_gaps(guide("integrations.md"), manifests=manifests()) == ()


def test_a_connector_with_no_row_is_a_finding() -> None:
    """Delete this and a connector added to the product ships with nothing anywhere saying what
    it may read, which is the one question an install has to answer about a source."""
    found = integration_gaps(
        a_connector_guide("| `freshdesk` | `rest` | `helpdesk` | `read_only` | `none` | `x` |"),
        manifests=(manifests()[0], manifests()[2]),
    )
    assert any(one.startswith("hubspot: no row in the table") for one in found)


def test_a_row_for_a_connector_that_does_not_exist_is_a_finding() -> None:
    """Delete this and a removed connector keeps its row, which reads as coverage: the reader
    stops looking, and the guide is longer than the product."""
    found = integration_gaps(
        a_connector_guide(
            "| `freshdesk` | `rest` | `helpdesk` | `read_only` | `none` | `freshdesk` |",
            "| `myspace` | `rest` | `wall` | `read_only` | `none` | `x` |",
        ),
        manifests=(manifests()[0],),
    )
    assert any(one.startswith("myspace: a row for a connector") for one in found)


def test_a_connector_with_a_row_and_no_section_is_a_finding() -> None:
    """Delete this and the table can name a source the guide never says how to install, so a
    completeness check is satisfied by a line in a table."""
    found = integration_gaps(
        a_connector_guide(
            "| `freshdesk` | `rest` | `helpdesk` | `read_only` | `none` | `freshdesk` |",
            sections=(),
        ),
        manifests=(manifests()[0],),
    )
    assert found == (
        "freshdesk: no section of its own, so the table names a connector the guide never "
        "says how to install",
    )


def test_a_section_for_a_connector_that_does_not_exist_is_a_finding() -> None:
    """Delete this and a page of installation instructions for a source nobody has stays in the
    guide, which is the reads-as-coverage failure arriving through a heading instead of a
    row."""
    found = integration_gaps(
        a_connector_guide(
            "| `freshdesk` | `rest` | `helpdesk` | `read_only` | `none` | `freshdesk` |",
            sections=("freshdesk", "myspace"),
        ),
        manifests=(manifests()[0],),
    )
    assert any(one.startswith("myspace: a section for a connector") for one in found)


@pytest.mark.parametrize(
    ("index", "wrong", "column"),
    [
        (1, "`database`", "the transport"),
        (2, "`the whole account`", "what it is pinned to at connect"),
        (3, "`write`", "the access it is bound with"),
        (4, "`delegated`", "what the source enforces"),
        (5, "`none measured`", "the rate ceiling"),
    ],
)
def test_every_checked_cell_is_read_off_the_manifest(index: int, wrong: str, column: str) -> None:
    """Five separate claims a client acts on, and each has to be able to fail on its own.
    Delete this and any one of them can be written freely: the worst is the permission column,
    where overstating it tells a reader the source is applying its own rules to the person
    asking when nothing is."""
    cells = ["`freshdesk`", "`rest`", "`helpdesk`", "`read_only`", "`none`", "`freshdesk`"]
    cells[index] = wrong
    found = integration_gaps(
        a_connector_guide("| " + " | ".join(cells) + " |"), manifests=(manifests()[0],)
    )
    assert len(found) == 1
    assert found[0].startswith(f"freshdesk: {column} reads")


def test_a_connector_row_with_too_few_cells_is_a_finding() -> None:
    """Delete this and a row missing its last columns raises rather than reporting, so the
    permission column can be dropped from the table and read as a broken test."""
    found = integration_gaps(
        a_connector_guide("| `freshdesk` | `rest` |", sections=()), manifests=()
    )
    assert found == (
        "a row with 2 cell(s) reads ('`freshdesk`', '`rest`'); every row states the connector, "
        "the transport, what it is pinned to, the access, what the source enforces and the "
        "rate ceiling",
    )


def test_a_connector_with_no_verified_ceiling_says_so_rather_than_leaving_a_cell_blank() -> None:
    """Delete this and two of the seven have an empty cell in the ceiling column, which reads
    as a cell somebody did not fill in rather than as a statement that nothing has measured
    one."""
    drive = manifests()[1]
    assert drive.ceiling == ""
    # The literal rather than NO_CEILING, which the guide's own cell is compared against: a
    # test asserting the constant against itself is green for every value it could hold.
    assert ceiling_cell(drive) == "none measured"
    assert NO_CEILING == "none measured"
    assert ceiling_cell(manifests()[0]) == "freshdesk"


# ================================================= the properties the guide's own claims rest on
def test_every_connector_shipping_today_is_bound_read_only_and_claims_no_source_enforcement() -> (
    None
):
    """The guide states both as facts about all seven. Delete this and a connector shipped with
    a write binding, or claiming its source applies the asker's own permissions, changes what a
    client should grant and the page goes on saying otherwise. The row check would catch it as
    a cell mismatch; this says which direction the whole table is expected to point."""
    for one in manifests():
        assert one.credential.mode is AccessMode.READ_ONLY, one.name
        assert one.permission_sync is PermissionSync.NONE, one.name


def test_one_connectors_tool_names_change_with_how_it_is_configured() -> None:
    """The property `TOOL_NAMES_ARE_NOT_A_PROPERTY_OF_EVERY_CONNECTOR` states, and the reason
    the table names no tools. Delete this and somebody adds a tools column, checks it against a
    fixture's entity, and the guide agrees with the test rather than with the product."""
    assert lark_base_for("maintenance").tool_names() != lark_base_for("orders").tool_names()
    assert "entity" in TOOL_NAMES_ARE_NOT_A_PROPERTY_OF_EVERY_CONNECTOR


def test_the_documents_the_checks_read_are_all_present() -> None:
    """Delete this and a guide deleted or renamed makes its own check fail with a missing file
    rather than with a finding, and the twelve-page set can lose a page silently."""
    expected = {
        "README.md",
        "install.md",
        "windows.md",
        "network.md",
        "configuration.md",
        "integrations.md",
        "authentication.md",
        "operations.md",
        "troubleshooting.md",
        "update-and-rollback.md",
        "restore-drill.md",
        "checklist.md",
        "coolify.md",
        "scaling.md",
    }
    assert {one.name for one in GUIDES.glob("*.md")} == expected


# ==================================================================== mechanism_gaps
def test_the_operations_chapter_names_every_scheduled_mechanism_and_what_starts_it() -> None:
    """**M42.2.8. The leaf asks for backup, monitoring, logging and health-check
    configuration, and the part of it a document can get wrong on its own is the list.**

    This section was wrong when the check was written. It read "the twelve mechanisms nothing
    runs" and eleven was already true, because one had acquired a caller that morning and the
    heading, the table and a later paragraph were three hand-kept copies of a fact the registry
    holds. A client reads a chapter like that once and does not re-read it on the day the
    twelfth is switched on.

    Delete this and the chapter goes back to being prose about a register, which is the
    arrangement `brain.launch` refuses for the handover pack and for the same reason."""
    assert mechanism_gaps(guide("operations.md")) == ()


def test_a_mechanism_the_chapter_does_not_name_is_a_finding() -> None:
    """A mechanism this install carries and the client was never told about. It is the
    direction that matters most, because the chapter reads as complete either way.

    Delete this and a control added later is invisible to every client who installed before
    it."""
    found = mechanism_gaps(
        a_table(
            MECHANISMS_MARKER,
            MECHANISMS_HEADER,
            "| `canary_run` | that the gate still refuses what it refused | `nothing` |",
        ),
        controls=(control("canary_run"), control("restore_drill")),
    )

    assert found == (
        "restore_drill: a mechanism this install carries and the operations chapter does not "
        "name, so the client was never told it exists",
    )


def test_a_row_for_a_mechanism_this_install_does_not_carry_is_a_finding() -> None:
    """The other direction: a client planning around something that is not here. Quieter than
    the first, because it reads as coverage rather than as a gap.

    Delete this and a mechanism removed from the product stays in the chapter for ever."""
    found = mechanism_gaps(
        a_table(
            MECHANISMS_MARKER,
            MECHANISMS_HEADER,
            "| `canary_run` | that the gate still refuses what it refused | `nothing` |",
            "| `gone_away` | something that was removed | `nothing` |",
        ),
        controls=(control("canary_run"),),
    )

    assert found == (
        "gone_away: a row for a mechanism this install does not carry, so the client is "
        "planning around something that is not here",
    )


def test_a_row_that_disagrees_about_what_starts_a_mechanism_is_a_finding() -> None:
    """**The column somebody acts on.** A mechanism recorded as running that nothing calls is
    the sentence `handover_lines` refuses to let a handover pack print, and here it would be
    printed in a chapter the client keeps.

    Delete this and the membership can be right while every answer in the last column is
    wrong, which is the state a table like this reaches first."""
    found = mechanism_gaps(
        a_table(
            MECHANISMS_MARKER,
            MECHANISMS_HEADER,
            "| `canary_run` | that the gate still refuses what it refused | `on_a_route` |",
        ),
        controls=(control("canary_run"),),
    )

    assert found == (
        "canary_run: the chapter says it is started by 'on_a_route' and the registry says "
        "'nothing', which is the column somebody acts on",
    )


def test_a_mechanism_row_with_too_few_cells_is_a_finding() -> None:
    """A two-column row states a mechanism and no answer about what starts it, and the check
    above would read the second cell as the answer.

    Delete this and a malformed row is read as a claim about the wrong column."""
    found = mechanism_gaps(
        a_table(MECHANISMS_MARKER, MECHANISMS_HEADER, "| `canary_run` | only two |"),
        controls=(control("canary_run"),),
    )

    assert any("every row states the mechanism" in one for one in found)


# ---------------------------------------------------- the queue install steps (M32.4.1.1)


def a_deploy_step(kind: str, *, order: int = 1, optional: bool = False) -> DeployStep:
    """One step of the queue's deploy plan, for exercising a refusal against a built plan."""
    return DeployStep(
        order=order,
        kind=StepKind(kind),
        what=f"the {kind} step",
        why=f"because the {kind} step is needed",
        optional=optional,
    )


def test_the_operations_chapter_names_every_step_that_installs_the_queue() -> None:
    """**The chapter said nothing about the queue at all, and `--deploy-plan` printed a plan
    nobody was told to run.**

    The queue's tables are the driver's and are created by DDL it ships, so they are outside
    `alembic upgrade` and an operator has to apply them. Until the last of those steps has run,
    `brain.ops.sweeps rls` is red on tables that arrived with row-level security off, and a red
    sweep with no remedy written down is a sweep somebody switches off.

    Held against `brain.ops.queue.DEPLOY_PLAN` rather than written out, for the reason
    `step_gaps` gives about the installer's plan: a hand-typed list of steps is a second plan,
    and the second one goes stale because nothing imports it.

    Delete this and the chapter drifts back to being silent about the queue, which is the state
    it was in on 2026-09-11 with the driver already shipped."""
    assert queue_step_gaps(guide("operations.md")) == ()


def test_a_queue_step_the_chapter_does_not_list_leaves_the_queue_half_installed() -> None:
    """The direction that costs an operator an outage rather than a puzzle: they follow the
    chapter to the end, the worker starts, and it drains nothing.

    Delete this and a step appended to the plan is invisible to every operator following the
    chapter."""
    found = queue_step_gaps(
        a_table(
            QUEUE_STEPS_MARKER,
            QUEUE_STEPS_HEADER,
            "| `dependency` | the driver is in the lock file | required |",
        ),
        plan=(a_deploy_step("dependency"), a_deploy_step("tables", order=2)),
    )

    assert found == (
        "'tables': the queue install runs this step and the chapter does not list it, so an "
        "operator following the chapter leaves the queue half installed",
    )


def test_a_row_for_a_queue_step_the_install_does_not_run_is_a_finding() -> None:
    """The quieter direction. A step removed from the plan and left in the chapter reads as
    coverage, so nobody looks for it, and the operator runs a command that no longer applies.

    Delete this and the chapter is longer than the install for ever."""
    found = queue_step_gaps(
        a_table(
            QUEUE_STEPS_MARKER,
            QUEUE_STEPS_HEADER,
            "| `dependency` | the driver is in the lock file | required |",
            "| `vacuum` | something nobody runs any more | required |",
        ),
        plan=(a_deploy_step("dependency"),),
    )

    assert found == ("'vacuum': the chapter lists a queue step the install does not run",)


def test_a_step_the_chapter_says_may_be_skipped_and_the_plan_requires_is_a_finding() -> None:
    """**The column an operator acts on, and the one where both mistakes are expensive.** A
    required step described as optional is a queue that is never finished installing. An
    optional step described as required is an operator running the driver's schema command a
    second time, which raises `DuplicateObject` because it is not idempotent, against a
    database that was already correct.

    Asserted with the plan's own flag rather than the word typed here, so the two cannot agree
    with each other while both disagreeing with the plan.

    Delete this and the chapter can call anything skippable and the check still passes."""
    found = queue_step_gaps(
        a_table(
            QUEUE_STEPS_MARKER,
            QUEUE_STEPS_HEADER,
            f"| `tables` | applies the driver's schema manager | {OPTIONAL_STEP} |",
        ),
        plan=(a_deploy_step("tables", optional=False),),
    )

    assert found == (
        f"'tables': the chapter calls it {OPTIONAL_STEP!r} and the plan says "
        f"{REQUIRED_STEP!r}, which is the column that decides whether somebody runs it",
    )


def test_the_queue_steps_are_checked_in_the_order_the_install_runs_them() -> None:
    """Row-level security is enabled over the tables the previous step created, so a chapter
    naming that step first is a chapter whose reader secures nothing and sees no error.

    Reported only when nothing is missing or extra, for the reason `step_gaps` gives: a list
    with a step missing is out of order by arithmetic, and saying so twice buries the finding
    somebody can act on.

    Delete this and every step can be present and the sequence useless."""
    found = queue_step_gaps(
        a_table(
            QUEUE_STEPS_MARKER,
            QUEUE_STEPS_HEADER,
            "| `row_level_security` | enables it on what was created | required |",
            "| `tables` | creates them | required |",
        ),
        plan=(
            a_deploy_step("tables", order=1),
            a_deploy_step("row_level_security", order=2),
        ),
    )

    assert found == (
        "the chapter names every queue step and not in the order they run: it reads "
        "['row_level_security', 'tables'] and the install runs ['tables', "
        "'row_level_security']",
    )


def test_a_queue_step_row_missing_a_cell_is_reported_rather_than_read() -> None:
    """A three-column table with a two-column row is a formatting slip, and reading it anyway
    would take the row's second cell as its skippability: a step would silently be declared
    optional because somebody dropped a pipe.

    Delete this and a malformed row either crashes on an index or, worse, answers.
    """
    found = queue_step_gaps(
        a_table(QUEUE_STEPS_MARKER, QUEUE_STEPS_HEADER, "| `tables` | creates them |"),
        plan=(),
    )

    assert found == (
        "a row with 2 cell(s) reads ('`tables`', 'creates them'); every row states the step, "
        "what it does and whether an install may skip it",
    )


# ==================================================================== troubleshooting_gaps
def an_entry(heading: str, body: str) -> str:
    return f"## {heading}\n\n{body}\n\n"


def test_every_troubleshooting_entry_says_what_is_happening_and_then_what_to_do() -> None:
    """**M42.2.9.** The guide is built from failures actually hit, symptom first, and until
    2026-09-14 nothing held any of it: the README listed the whole page as kept by hand.

    Delete this and an entry that lost its remedy, or grew one with nothing above it, reads
    exactly like every other entry on the page."""
    page = guide("troubleshooting.md")

    assert troubleshooting_gaps(page) == ()
    assert [h for h, _ in sections(page) if h not in TROUBLESHOOTING_CLOSING]


def test_an_entry_that_never_says_what_to_do_is_a_finding() -> None:
    """Delete this and the check can pass a page of stories."""
    page = an_entry("A thing happens", "It is this.")

    assert troubleshooting_gaps(page) == (
        "'A thing happens': says what is happening and never what to do about it",
    )


def test_an_entry_that_opens_with_what_to_do_is_a_finding() -> None:
    """The reader knows the symptom and not the name, so an entry with nothing above its remedy
    cannot be recognised. Delete this and the order the leaf asks for is unchecked."""
    page = an_entry("A thing happens", f"{WHAT_TO_DO} Restart it.")

    assert troubleshooting_gaps(page) == (
        "'A thing happens': opens with what to do, so a reader who knows only the symptom has "
        "nothing to recognise it by",
    )


def test_an_entry_below_the_closing_sections_is_a_finding() -> None:
    """Delete this and an entry appended to the end of the file lands under the section a reader
    stops at, where nobody looking for a symptom arrives."""
    page = (
        an_entry("A thing happens", f"It is this.\n\n{WHAT_TO_DO} Restart it.")
        + an_entry(TROUBLESHOOTING_CLOSING[0], "Stories.")
        + an_entry("Another thing happens", f"It is that.\n\n{WHAT_TO_DO} Wait.")
    )

    assert troubleshooting_gaps(page) == (
        "'Another thing happens': an entry after the closing sections, where nobody reading for "
        "a symptom still is",
    )


def test_a_guide_with_no_entries_is_refused_rather_than_read_as_having_no_findings() -> None:
    """Delete this and a guide emptied of every entry passes a check that finds nothing wrong
    with any of them."""
    assert troubleshooting_gaps(an_entry("Task ids", "M0.0.0")) == (
        "the guide carries no entries, so there is nothing a reader can look a symptom up in",
    )


def test_a_level_three_heading_is_part_of_its_section_and_not_a_section() -> None:
    """Delete this and a `###` inside an entry splits it, so its remedy is found in a section
    that is not the entry."""
    page = "## One\n\ntext\n\n### Inner\n\nmore\n\n## Two\n\nend\n"

    assert [heading for heading, _ in sections(page)] == ["One", "Two"]
    assert "### Inner" in dict(sections(page))["One"]


def test_the_figures_the_troubleshooting_guide_quotes_are_the_ones_the_code_holds() -> None:
    """Two entries quote a number a reader acts on: the helpdesk search ceiling and the Compose
    version below which every memory limit is ignored. Both are held to the code.

    Delete this and a ceiling or a minimum that moves in the code leaves the guide telling a
    reader to trust a count, or a tool, that is no longer the one that matters."""
    entries = dict(sections(guide("troubleshooting.md")))
    ceiling = next(body for heading, body in entries.items() if "round number" in heading)
    unlimited = next(body for heading, body in entries.items() if "no memory limit" in heading)
    compose = next(one for one in RUNTIME_REQUIREMENTS if one.what.startswith("Docker Compose v2"))

    assert FRESHDESK_SEARCH_MAX_RECORDS == 300
    assert "three hundred" in ceiling
    assert f"print {compose.minimum} or newer" in unlimited


# ==================================================================== checklist_gaps
def a_checklist(
    names: tuple[str, ...] = CHECKLIST_SECTIONS,
    links: tuple[str, ...] = HIDDEN_LINKS,
    empty: tuple[str, ...] = (),
) -> str:
    body = "".join(
        f"## {name}\n\n" + ("" if name in empty else "- [ ] do the thing\n\n") for name in names
    )
    rows = "".join(f"| `{link}` | somewhere | cut it |\n" for link in links)
    header = "| Link | Where it hides | What to do |\n| --- | --- | --- |\n"
    return f"{LINKS_MARKER}\n\n{header}{rows}\n{body}"


def timer_units() -> frozenset[str]:
    return frozenset(one.name for one in (REPO / "ops").rglob("*.timer"))


def test_the_deployment_checklist_has_its_ten_sections_and_names_the_four_links() -> None:
    """**M42.3.7, M34.3.3.1 and M30.2.8.** The first asks for ten named sections, the second
    for the four hidden production links, and the third names the four.

    Delete this and a section can go, or a link row, and the page still reads as a complete
    checklist."""
    assert checklist_gaps(guide("checklist.md")) == ()


def test_the_four_links_are_the_four_the_work_breakdown_names() -> None:
    """The constant is held against the leaf sentences rather than against itself.

    Delete this and a fifth link, or a renamed one, changes what the checklist is checked for
    while the page and the constant agree with each other and not with what was asked."""
    texts = {
        leaf: text
        for module in json.loads((REPO / "docs" / "wbs.json").read_text(encoding="utf-8"))[
            "modules"
        ]
        for leaf, text in zip(module["leaf_ids"], module["leaf_texts"], strict=True)
    }

    assert "four hidden production links" in texts["M34.3.3.1"]
    assert len(HIDDEN_LINKS) == 4
    assert all(link.lower() in texts["M30.2.8"].lower() for link in HIDDEN_LINKS)


def test_a_complete_checklist_raises_nothing() -> None:
    """The positive sibling. Delete this and a check refusing every checklist passes the
    refusal tests below."""
    assert checklist_gaps(a_checklist()) == ()


def test_a_missing_section_and_an_undeclared_one_are_both_findings() -> None:
    """Both directions. Delete this and a renamed section is invisible, because a section under
    the new name reads as coverage."""
    renamed = tuple("Launch" if name == "Go-live" else name for name in CHECKLIST_SECTIONS)

    assert checklist_gaps(a_checklist(names=renamed)) == (
        "'Go-live': the checklist has no section for it",
        "'Launch': a section the checklist does not declare, which reads as coverage",
    )


def test_sections_out_of_order_are_a_finding() -> None:
    """Delete this and testing can come after go-live on the page a person follows in order."""
    swapped = (
        *CHECKLIST_SECTIONS[:7],
        CHECKLIST_SECTIONS[8],
        CHECKLIST_SECTIONS[7],
        CHECKLIST_SECTIONS[9],
    )

    found = checklist_gaps(a_checklist(names=swapped))

    assert len(found) == 1
    assert found[0].startswith("the sections are not in the order the work happens")


def test_a_section_with_nothing_to_tick_is_a_finding() -> None:
    """Delete this and a heading with no items under it is read as a section that is done."""
    assert checklist_gaps(a_checklist(empty=("Security",))) == (
        "'Security': a section with nothing to tick, which reads as done",
    )


def test_a_missing_link_and_a_fifth_one_are_both_findings() -> None:
    """Delete this and the one hiding place a checklist stops naming is the one nobody checks."""
    links = (*HIDDEN_LINKS[:3], "browser cookies")

    assert checklist_gaps(a_checklist(links=links)) == (
        "'scheduled jobs': a copied install carries this link and the checklist does not name it",
        "'browser cookies': a link the checklist names that is not one of the four",
    )


def test_every_timer_this_repository_installs_is_on_the_checklist() -> None:
    """Delete this and a timer added under `ops/` survives a copied disk with nobody told to
    look for it. The set is asserted non-empty, because a glob that stops matching makes the
    check pass over nothing."""
    timers = timer_units()

    assert timers
    assert scheduled_job_gaps(guide("checklist.md"), timers=timers) == ()


def test_a_timer_the_checklist_misses_and_one_that_is_gone_are_both_findings() -> None:
    """Both directions. Delete this and a row for a deleted timer reads as coverage."""
    page = (
        f"{TIMERS_MARKER}\n\n| Timer | Installed by | What it does |\n| --- | --- | --- |\n"
        "| `old.timer` | a script | a job |\n| `short.timer` | a script |\n"
    )

    assert scheduled_job_gaps(page, timers={"new.timer"}) == (
        "a row with 2 cell(s) reads ('`short.timer`', 'a script'); every row states the timer, "
        "what installs it and what it does",
        "new.timer: this repository installs the timer and the checklist does not name it",
        "old.timer: the checklist names a timer this repository does not install",
    )


def test_what_the_checklist_says_about_the_archive_is_what_the_archive_does() -> None:
    """The git remotes row says the archive carries no `.git`, the temporary state row that no
    install's `.env` travels, and the page is only useful on a server if it ships. Delete this
    and any of the three can stop being true while the page goes on saying it."""
    assert refused_by(".git/config")
    assert refused_by(".env")
    assert included_by("docs/install/checklist.md")


# ==================================================================== update_script_gaps
def script_units() -> frozenset[str]:
    return frozenset(one.name for one in (REPO / "ops" / "update").glob("*.sh"))


def test_the_update_page_names_every_script_the_release_carries_and_how_to_run_it() -> None:
    """**M34.3.3.3.** The procedure is prose and says so; the table of what to run is the part
    somebody copies at the worst moment of their week, and it is held to the scripts.

    Delete this and a renamed script leaves the page pointing at a file that is not there."""
    scripts = script_units()

    assert scripts
    assert all(included_by(f"ops/update/{name}") for name in scripts)
    assert update_script_gaps(guide("update-and-rollback.md"), scripts=scripts) == ()


def test_a_wrong_command_a_missing_script_and_an_extra_one_are_all_findings() -> None:
    """Delete this and the check can compare names and never the command a person types."""
    page = (
        f"{UPDATE_SCRIPTS_MARKER}\n\n| Script | You run | It needs |\n| --- | --- | --- |\n"
        f"| `update.sh` | `sh /tmp/update.sh <profile>` | nothing |\n"
        f"| `gone.sh` | `sh {UPDATE_SCRIPTS_HOME}/gone.sh` | nothing |\n"
        "| `short.sh` | nothing |\n"
    )

    assert update_script_gaps(page, scripts={"update.sh", "rollback.sh"}) == (
        f"update.sh: the page says to run 'sh /tmp/update.sh <profile>', and the release "
        f"unpacks the script at {UPDATE_SCRIPTS_HOME}/update.sh",
        "a row with 2 cell(s) reads ('`short.sh`', 'nothing'); every row states the script, the "
        "command and what it needs",
        "rollback.sh: the release carries this script and the page does not say how to run it",
        "gone.sh: the page names a script the release does not carry",
    )


def test_a_command_that_is_the_script_path_with_arguments_is_accepted() -> None:
    """The positive sibling, and the prefix is matched on a word boundary: `update.sh.bak` is
    not `update.sh`. Delete this and a check refusing every command passes the test above."""
    good = (
        f"{UPDATE_SCRIPTS_MARKER}\n\n| Script | You run | It needs |\n| --- | --- | --- |\n"
        f"| `update.sh` | `sh {UPDATE_SCRIPTS_HOME}/update.sh <profile> <tag>` | a URL |\n"
    )
    near = good.replace("update.sh <profile>", "update.sh.bak <profile>")

    assert update_script_gaps(good, scripts={"update.sh"}) == ()
    assert update_script_gaps(near, scripts={"update.sh"}) != ()


# ================================================================= database_command_gaps
DATABASE_HEADER = "| Command | How to run it | What it does, and what it refuses |"


def _database_rows(*names: str, module: str = "brain.deployment.database") -> list[str]:
    return [f"| `{name}` | `python -m {module} {name}` | does it |" for name in names]


def test_the_operations_page_says_how_to_run_every_database_command() -> None:
    """M42.3.3's documentation half. Delete this and a command added to, renamed in or removed
    from `brain.deployment.database` leaves the page telling somebody to run one that is not
    there, during an install."""
    from brain.deployment import database
    from brain.ops.install_docs import database_command_gaps

    found = database_command_gaps(
        guide("operations.md"), commands=database.COMMANDS, module=database.__name__
    )
    assert found == ()


def test_a_database_command_the_page_omits_or_invents_is_a_finding() -> None:
    """Both directions, against a page built to fail. Delete this and the check can pass a page
    missing `seed` and naming a `build` nobody wrote."""
    from brain.ops.install_docs import DATABASE_COMMANDS_MARKER, database_command_gaps

    page = a_table(DATABASE_COMMANDS_MARKER, DATABASE_HEADER, *_database_rows("create", "build"))
    found = database_command_gaps(
        page, commands=("create", "migrate", "seed"), module="brain.deployment.database"
    )

    assert found == (
        "migrate: this command exists and the page does not say how to run it",
        "seed: this command exists and the page does not say how to run it",
        "build: the page names a database command that does not exist",
    )


def test_a_database_command_written_with_the_wrong_invocation_is_a_finding() -> None:
    """The command column is checked as a value. Delete this and a row naming the right command
    and the module's old path passes, which is the runbook line that fails with no module named."""
    from brain.ops.install_docs import DATABASE_COMMANDS_MARKER, database_command_gaps

    rows = [*_database_rows("create", "migrate"), "| `seed` | `python -m brain.seed` | does it |"]
    page = a_table(DATABASE_COMMANDS_MARKER, DATABASE_HEADER, *rows)
    found = database_command_gaps(
        page, commands=("create", "migrate", "seed"), module="brain.deployment.database"
    )

    assert found == (
        "seed: the page says to run 'python -m brain.seed', and the command is "
        "'python -m brain.deployment.database seed'",
    )


def test_a_database_command_row_with_too_few_cells_is_a_finding() -> None:
    """Delete this and a row missing its columns raises inside the check rather than naming it."""
    from brain.ops.install_docs import DATABASE_COMMANDS_MARKER, database_command_gaps

    page = a_table(DATABASE_COMMANDS_MARKER, DATABASE_HEADER, "| `create` |")
    found = database_command_gaps(page, commands=(), module="brain.deployment.database")

    assert found == (
        "a row with 1 cell(s) reads ('`create`',); every row states the command, how to run it "
        "and what it does",
    )
