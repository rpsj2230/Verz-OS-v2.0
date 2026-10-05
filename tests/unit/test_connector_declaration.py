"""A connector declares itself once, and every table that used to list connectors is read off it.

`brain.connectors.declaration` replaced four hand-kept lists with one declaration per connector
module. The failures worth testing are the ones a list used to hide: a connector that declares
itself wrongly and is skipped rather than refused, a table that goes on being typed by hand beside
the declarations, and a declaration that states a combination nothing could act on. Each refusal
has a sibling that is accepted.

Task ids: M11.1.1, M11.1.6
"""

from __future__ import annotations

import importlib
import pkgutil
import textwrap
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

import brain.connectors
from brain.connectors import hubspot, xero
from brain.connectors.declaration import (
    A_READING_NEEDS_A_CONNECTION_TO_READ,
    KEEPS_A_MINIMAL_INDEX,
    ConnectorDeclaration,
    ConsoleForm,
    DeclarationError,
    declaration_gaps,
    discover,
    read_backs,
    shipped,
)
from brain.connectors.write_verification import builds_a_manifest
from brain.ops.connectable import (
    CONNECTABLE,
    DECLARED_FORMS,
    NOT_FROM_THE_CONSOLE,
    THIS_INSTALL_CANNOT_READ_IT_YET,
    reads,
)
from brain.ops.connector_recordings import RECORDINGS
from brain.ops.connector_sync import READINGS

#: The docstring a well-behaved fake connector module carries.
SAYS_IT: str = f'"""A connector that {KEEPS_A_MINIMAL_INDEX}."""'


def a_package(root: Path, name: str, modules: dict[str, str]) -> ModuleType:
    """A package of this test's own under `root`, holding these modules, imported fresh."""
    package = root / name
    package.mkdir()
    (package / "__init__.py").write_text('"""A package of fakes."""\n', encoding="utf-8")
    for module, source in modules.items():
        (package / f"{module}.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return importlib.import_module(name)


# ------------------------------------------------------------------ what ships


def test_every_connector_that_ships_declares_itself_under_its_own_module_name() -> None:
    """Every connector this release ships, each found by the `CONNECTOR` its module states, and
    the modules that build a manifest read off the package independently of `shipped`, so the two
    reads of the package have to agree. Each name is compared with the module's own constant rather
    than with the key it was found under for the two named, and Xero, HubSpot and Lark Wiki are
    anchors so an empty discovery cannot pass.

    Read off the package rather than typed since 2026-10-05: a typed list was a line every connector
    PR edited, and two open at once conflicted in it.

    Delete this and a connector that stops declaring itself leaves the screen, the worker and the
    read-back table at once, with nothing saying so."""
    found = shipped()
    builders = {
        info.name
        for info in pkgutil.iter_modules(brain.connectors.__path__)
        if builds_a_manifest(importlib.import_module(f"brain.connectors.{info.name}"))
    }

    assert set(found) == builders
    assert {"xero", "hubspot", "lark_wiki"} <= set(found)
    assert found["xero"] is xero.CONNECTOR and found["xero"].name == xero.CONNECTOR_NAME
    assert found["hubspot"] is hubspot.CONNECTOR
    assert declaration_gaps() == ()


def test_every_registry_that_used_to_be_a_list_is_read_off_the_declarations() -> None:
    """The console's two lists, the worker's readings, the screen's recordings and the read-back
    table are each the declarations seen from one side, so none can name a connector the others
    do not.

    Delete this and one of them can be typed by hand again beside the declarations, and the first
    connector added after that is missing from whichever list nobody remembered."""
    declared = shipped()

    assert set(DECLARED_FORMS) == {name for name, one in declared.items() if one.console}
    assert set(CONNECTABLE) == {name for name in DECLARED_FORMS if reads(declared[name])}
    assert set(NOT_FROM_THE_CONSOLE) == set(declared) - set(CONNECTABLE)
    assert {name: kind.label for name, kind in CONNECTABLE.items()} == {
        name: declared[name].label for name in CONNECTABLE
    }
    # A source with no form says why in its own declaration's words; a form not offered yet says
    # this install cannot read it (`brain.ops.connectable.THIS_INSTALL_CANNOT_READ_IT_YET`).
    assert {name: one.why for name, one in NOT_FROM_THE_CONSOLE.items()} == {
        name: declared[name].not_from_the_console or THIS_INSTALL_CANNOT_READ_IT_YET
        for name in NOT_FROM_THE_CONSOLE
    }
    assert dict(READINGS) == {
        name: one.reading for name, one in declared.items() if one.reading is not None
    }
    assert dict(RECORDINGS) == {name: one.recorded for name, one in declared.items()}
    assert dict(read_backs()) == {name: one.read_back for name, one in declared.items()}
    # The anchor: Xero is read on a schedule, and Lark's two, connected through Connect Lark, are
    # not, so a discovery that found nothing, or everything, fails here.
    assert "xero" in READINGS and not {"lark_base", "lark_wiki"} & set(READINGS)


def test_every_declared_form_carries_the_example_a_test_and_a_check_connect_it_with() -> None:
    """`A_CONNECTOR_IS_ITS_OWN_MODULE_AND_ITS_OWN_FIXTURES`. Every form's example gives exactly the
    settings the form asks for, in its order; what an acceptance check connects it with is made up
    afresh on every call and takes its departments from the ones the check may write in; and the
    edit a person would make changes the value. Xero and Laravel are anchors, so a discovery that
    found no form fails.

    Delete this and a form can be added with no example, so the unit tests connect it with nothing
    and the acceptance checks raise on the owner's install, or an example's departments can name
    one the check may not write grants in."""
    departments = ("check_one", "check_two")
    forms = {name: one.console for name, one in shipped().items() if one.console is not None}

    assert {"xero", "laravel"} <= set(forms)
    for name, form in forms.items():
        example = form.example
        assert example is not None, name
        asked = [one.name for one in form.settings]
        fresh = example.fresh(departments)
        assert list(example.settings) == asked, name
        assert list(fresh) == asked, name
        assert fresh != example.fresh(departments), name
        assert fresh.get("department", departments[0]) in departments, name
        assert example.edited() != example.settings[example.edit], name


def test_an_example_naming_other_settings_than_its_form_is_refused() -> None:
    """A form's example is held to the form when it is declared. Delete this and an example can
    give settings the form no longer asks for, and every test built from it connects the source
    with a setting the console would never send."""
    form = xero.CONNECTOR.console
    assert form is not None and form.example is not None
    wrong = replace(form.example, settings={"region": "x"}, edit="region")

    with pytest.raises(DeclarationError, match="its example gives"):
        replace(form, example=wrong)
    assert replace(form, example=form.example).example == form.example


# ------------------------------------------------------------------ discovery


def test_a_module_that_declares_itself_is_found_and_one_that_does_not_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive case for discovery, beside the framework module that declares nothing.

    Delete this and a discovery that found nothing, or found everything, would pass the refusals
    below."""
    monkeypatch.syspath_prepend(str(tmp_path))
    package = a_package(
        tmp_path,
        "fakes_found",
        {
            "good": f"""
                {SAYS_IT}
                from dataclasses import replace
                from brain.connectors.xero import CONNECTOR as XERO
                CONNECTOR = replace(XERO, name="good")
            """,
            "framework": '"""Holds nothing a platform lists."""\n',
        },
    )

    found = discover(package)

    assert list(found) == ["good"]
    assert found["good"].label == xero.CONNECTOR.label


def test_a_declaration_that_is_not_one_stops_discovery_rather_than_being_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `CONNECTOR` of the wrong type is refused at start-up. Delete this and a connector declared
    as a dict is silently absent from the screen, which reads exactly like one nobody shipped."""
    monkeypatch.syspath_prepend(str(tmp_path))
    package = a_package(
        tmp_path, "fakes_mistyped", {"odd": f'{SAYS_IT}\nCONNECTOR = {{"name": "odd"}}\n'}
    )

    with pytest.raises(DeclarationError, match="not a ConnectorDeclaration"):
        discover(package)


def test_a_declaration_filed_under_another_module_name_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cassette file, the key slot and the screen all find a connector by its module's name.
    Delete this and a module can declare itself as another connector and take its place."""
    monkeypatch.syspath_prepend(str(tmp_path))
    package = a_package(
        tmp_path,
        "fakes_misnamed",
        {
            "impostor": f"""
                {SAYS_IT}
                from brain.connectors.xero import CONNECTOR
            """
        },
    )

    with pytest.raises(DeclarationError, match="declares itself as 'xero'"):
        discover(package)


def test_the_gaps_name_a_manifest_nobody_declared_and_a_declaration_that_says_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three findings, each in a module of its own, and a clean module beside them that yields
    none. Delete this and `declaration_gaps` could return nothing for any package, and the
    invariant holding the real one would be green by construction."""
    monkeypatch.syspath_prepend(str(tmp_path))
    package = a_package(
        tmp_path,
        "fakes_gaps",
        {
            "undeclared": """
                \"\"\"Builds a manifest and says nothing about itself.\"\"\"
                from __future__ import annotations
                from brain.connectors.manifest import ConnectorManifest
                def manifest() -> ConnectorManifest:
                    raise NotImplementedError
            """,
            "quiet": """
                \"\"\"A connector that forgot the owner's rule.\"\"\"
                from dataclasses import replace
                from brain.connectors.xero import CONNECTOR as XERO
                CONNECTOR = replace(XERO, name="quiet")
            """,
            "clean": f"""
                {SAYS_IT}
                from __future__ import annotations
                from dataclasses import replace
                from brain.connectors.manifest import ConnectorManifest
                from brain.connectors.xero import CONNECTOR as XERO
                CONNECTOR = replace(XERO, name="clean")
                def manifest() -> ConnectorManifest:
                    raise NotImplementedError
            """,
        },
    )

    gaps = declaration_gaps(package)

    assert len(gaps) == 3
    assert any("fakes_gaps.undeclared builds a manifest and declares no" in one for one in gaps)
    assert any("fakes_gaps.quiet declares CONNECTOR and builds no manifest" in one for one in gaps)
    assert any(
        f"fakes_gaps.quiet's docstring does not say it {KEEPS_A_MINIMAL_INDEX}" in one
        for one in gaps
    )
    assert not any("fakes_gaps.clean" in one for one in gaps)


# ------------------------------------------------------------------ what a declaration may say


def test_a_declaration_gives_a_console_form_or_a_reason_and_never_both_or_neither() -> None:
    """A source is either offered on the screen or explained there. Delete this and a source can
    be offered with a reason it cannot be, or listed with neither, which draws a blank row."""
    declared = xero.CONNECTOR

    with pytest.raises(DeclarationError, match="both or neither"):
        replace(declared, not_from_the_console="Connected at the server.")
    with pytest.raises(DeclarationError, match="both or neither"):
        replace(declared, console=None, reading=None)
    explained = replace(
        declared, console=None, reading=None, live=None, guide=(), not_from_the_console="Not yet."
    )
    assert explained.console is None and explained.not_from_the_console == "Not yet."


def test_a_live_lookup_needs_the_reading_it_reads_through() -> None:
    """A record read live is read through the reading's operation and interpretation (M11.9.2).
    Delete this and a connector can declare how to read one record with nothing to read it through,
    and every live read of it fails at question time instead of the build failing at start-up."""
    with pytest.raises(DeclarationError, match="live lookup and no reading"):
        replace(xero.CONNECTOR, reading=None)
    assert replace(xero.CONNECTOR, reading=None, live=None).live is None
    assert xero.CONNECTOR.live is not None and xero.CONNECTOR.reading is not None


def test_a_reading_needs_a_source_the_console_can_connect() -> None:
    """The worker reads a source from the connection row an administrator made. Delete this and
    a reading can be declared for a source nothing can ever start reading."""
    with pytest.raises(DeclarationError) as refused:
        replace(xero.CONNECTOR, console=None, not_from_the_console="Connected at the server.")
    assert A_READING_NEEDS_A_CONNECTION_TO_READ in str(refused.value)


def test_a_declaration_must_be_named_and_labelled() -> None:
    """The name is how everything finds it and the label is what a person reads. Delete this and
    a declaration named with a space, or labelled with nothing, reaches the screen."""
    with pytest.raises(DeclarationError, match="is not a name"):
        replace(xero.CONNECTOR, name="Xero Two")
    with pytest.raises(DeclarationError, match="no label"):
        replace(xero.CONNECTOR, label="  ")
    assert isinstance(replace(xero.CONNECTOR, label="Xero ledger"), ConnectorDeclaration)


def test_a_console_form_asks_for_a_setting_and_says_which_key_it_takes() -> None:
    """A form asking for no identifier builds a manifest scoped by whatever the key reaches.
    Delete this and a source can be connected to everything its key can see."""
    form = xero.CONNECTOR.console
    assert form is not None

    with pytest.raises(DeclarationError, match="asks for no setting"):
        replace(form, settings=())
    with pytest.raises(DeclarationError, match="which key"):
        replace(form, credential_hint=" ")
    assert isinstance(replace(form, credential_label="The Xero key"), ConsoleForm)
