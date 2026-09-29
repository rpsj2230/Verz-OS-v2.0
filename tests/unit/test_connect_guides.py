"""Every connector's connect flow: the shared step shape, and each source's own steps.

The owner asked on 2026-09-29 for every connector to be connected one screen at a time with a
picture per step. The steps live in each connector's declaration (`guide`), and these tests hold
the three things that go wrong quietly: a connector shipping with no steps, steps that ask for
something other than what the source's form takes, and a picture pointing at an element it does
not draw.

Task ids: M11.9.4, M27.11.9
"""

from __future__ import annotations

import pytest

from brain.connectors.declaration import (
    CREDENTIAL_ASK,
    ConnectorDeclaration,
    CredentialShape,
    DeclarationError,
    Recorded,
    shipped,
)
from brain.console.connector_detail import LARK_SOURCES
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.connectable import CONNECTABLE, NOT_FROM_THE_CONSOLE
from brain.ops.connector_slots import SLOT_SCOPES

#: A picture that draws what it marks, for the refusals below to vary one field of.
SKETCH = Sketch(
    place="Vendor console",
    heading="Settings",
    menu=("Keys", "Scopes"),
    menu_mark="Scopes",
    lines=(SketchLine(LineKind.ITEM, "read", mark=True),),
    button="Save",
)


def step(key: str = "one", **over: object) -> GuideStep:
    fields: dict[str, object] = {
        "key": key,
        "title": "Do it",
        "text": "Press Save.",
        "sketch": SKETCH,
    }
    fields.update(over)
    return GuideStep(**fields)  # type: ignore[arg-type]


# ------------------------------------------------------------------ the step shape


def test_a_picture_marks_only_what_it_draws_and_says_it_in_order() -> None:
    """A marked menu item or tab that is not drawn points a person at nothing, so it is refused;
    the marks come back in reading order, which is the order the console numbers them. Delete
    this and a renamed menu item leaves a picture numbering an element that is not there."""
    assert SKETCH.marks() == ("Scopes", "read", "Save")
    with pytest.raises(ValueError, match="not in its menu"):
        Sketch(place="x", heading="y", menu=("Keys",), menu_mark="Scopes")
    with pytest.raises(ValueError, match="not drawn"):
        Sketch(place="x", heading="y", tabs=("One",), tab_mark="Two")
    with pytest.raises(ValueError, match="sentence"):
        SketchLine(LineKind.TEXT, "x" * 49)


def test_a_step_links_only_to_https_and_says_what_its_link_opens() -> None:
    """Delete this and a step can link to a plain http page or show a bare address as a button."""
    assert step(link="https://vendor.example/keys", link_label="Open the keys").link
    with pytest.raises(ValueError, match="https"):
        step(link="http://vendor.example/keys", link_label="Open the keys")
    with pytest.raises(ValueError, match="what its link opens"):
        step(link="https://vendor.example/keys")
    with pytest.raises(ValueError, match="what its link opens"):
        step(link_label="Open nothing")


def test_two_steps_may_not_share_a_key() -> None:
    """A test sends a person back to a step by its key. Delete this and two steps answer to one
    key, and the flow opens whichever it finds first."""
    assert [one.key for one in keyed((step("a"), step("b")))] == ["a", "b"]
    with pytest.raises(ValueError, match="share a key"):
        keyed((step("a"), step("a")))


# ------------------------------------------------------------------ each source's steps


def test_every_connector_not_connected_through_lark_declares_its_steps() -> None:
    """The owner asked for every connector as a flow. Lark's two sources are connected through
    Connect Lark's own flow and declare none here. Delete this and a connector ships with a
    Connect button that opens a form and no steps."""
    for name, declared in shipped().items():
        if name in LARK_SOURCES:
            assert declared.guide == (), name
        else:
            assert len(declared.guide) >= 3, name


def test_a_console_source_ends_with_its_form_and_a_server_source_asks_for_nothing() -> None:
    """The last screen of a console source asks for exactly its form's settings and its key, and
    the last screen of a server source asks for nothing. Delete this and a setting added to a
    form has no step saying where to find it, or a server source draws a form nobody can send."""
    for name, kind in CONNECTABLE.items():
        # A source that takes no key (M11.7.4) asks for its settings alone.
        key = () if kind.credential_shape is CredentialShape.NONE else (CREDENTIAL_ASK,)
        assert kind.guide[-1].asks == (*(one.name for one in kind.settings), *key), name
        assert all(one.asks == () for one in kind.guide[:-1]), name
    for name, server in NOT_FROM_THE_CONSOLE.items():
        assert all(one.asks == () for one in server.guide), name


def test_a_guide_that_asks_for_something_the_form_does_not_take_is_refused_at_start_up() -> None:
    """The positive case is every shipped connector loading above; this is the refusal. Delete it
    and a declaration whose last step names a setting the form does not have loads silently."""
    xero = shipped()["xero"]
    with pytest.raises(DeclarationError, match="ends its guide"):
        ConnectorDeclaration(
            name="xero",
            label="Xero",
            console=xero.console,
            read_back=xero.read_back,
            recorded=Recorded(tested=True),
            guide=(step("connect", asks=("organisation", CREDENTIAL_ASK)),),
        )
    with pytest.raises(DeclarationError, match="ends its guide"):
        ConnectorDeclaration(
            name="laravel",
            label="Laravel",
            not_from_the_console="Connected at the server.",
            read_back=shipped()["laravel"].read_back,
            recorded=Recorded(tested=True),
            guide=(step("at_the_server", asks=(CREDENTIAL_ASK,)),),
        )


def test_the_steps_name_every_scope_the_sources_vault_slot_asks_the_vendor_for() -> None:
    """Xero's and HubSpot's slots name the exact scopes to ask for; the steps must name each one,
    so an administrator following the flow asks for what the slot was defined with. Delete this
    and the steps and the vault can disagree about what the key may do."""
    for name in ("xero", "hubspot"):
        text = " ".join(one.text for one in shipped()[name].guide)
        for scope in SLOT_SCOPES[name].request:
            assert scope in text, (name, scope)


def test_a_server_source_says_why_in_its_declarations_own_words() -> None:
    """The hand-over step quotes the reason the Connectors screen shows, not a second copy of it.
    Delete this and the step and the screen can give two different reasons."""
    for name, kind in NOT_FROM_THE_CONSOLE.items():
        if name in LARK_SOURCES:
            continue
        assert kind.why in kind.guide[-1].text, name
