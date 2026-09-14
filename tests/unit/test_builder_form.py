"""The builder's form is the manifest's own JSON Schema, cut into the seven sections.

M20.1.2 is "forms generated from the manifest JSON Schema via react-jsonschema-form". The
library half is the console's and is held by `console/tests/manifest-form.test.tsx`; this is
the half that decides what "generated from the manifest JSON Schema" means, and the test that
matters most is the one that hands `section_schema` a schema that has changed. A form that
follows the schema it was given is generated; a form that renders the same whatever the schema
says was written by somebody.

The oracle throughout is `TemplateManifest.model_json_schema()` read directly, and the bounds
are checked against `brain.agents.model`'s constants rather than against this module's output
compared with itself.

The two halves meet at `console/tests/fixtures/manifest-form.json`, which the console suite
renders and the last tests here hold equal to `form_document()`.

Task ids: M20.1.2
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from brain.agents.model import DISPLAY_NAME_CHARS, PERSONA_CHARS
from brain.agents.template import MANIFEST_PATHS, TemplateManifest
from brain.builder.compose import SECTION_OF_PATH, BuilderError, Section
from brain.builder.form import form_document, main, section_schema

REPO = Path(__file__).resolve().parents[2]
CONSOLE_FIXTURE = REPO / "console" / "tests" / "fixtures" / "manifest-form.json"
REGENERATE = "uv run python -m brain.builder.form console/tests/fixtures/manifest-form.json"


def manifest() -> dict[str, Any]:
    return TemplateManifest.model_json_schema()


def field_on(form: dict[str, Any], path: str) -> Any:
    """One manifest path's field on a section form, found the way the form nests it."""
    head, _, tail = path.partition(".")
    top = form["properties"][head]
    return top["properties"][tail] if tail else top


def the_models_own(path: str) -> Any:
    """One manifest path's schema, read straight off the model by resolving its head."""
    root = manifest()
    head, _, tail = path.partition(".")
    top = root["properties"][head]
    if not tail:
        return top
    definition = root["$defs"][top["$ref"].rsplit("/", 1)[-1]]
    return definition["properties"][tail]


def keys_in(value: object) -> Iterator[str]:
    """Every key of every object anywhere inside a JSON value."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from keys_in(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from keys_in(inner)


def references_in(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, inner in value.items():
            if key == "$ref" and isinstance(inner, str):
                yield inner
            yield from references_in(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from references_in(inner)


def test_every_field_on_a_section_form_is_the_manifests_own_schema_for_its_path() -> None:
    """**M20.1.2.** The leaf's own claim, path by path: the field a section form carries is the
    model's schema for that path, copied rather than described, in the section
    `compose.SECTION_OF_PATH` files it under.

    Deleting this lets a section form carry a hand-written description of a field, which is
    correct until the model changes and then wrong with nothing failing.
    """
    for path in MANIFEST_PATHS:
        form = section_schema(SECTION_OF_PATH[path])
        expected = {
            key: value for key, value in the_models_own(path).items() if key != "description"
        }
        assert field_on(form, path) == expected, path


def test_a_bound_on_the_model_is_the_bound_on_the_form() -> None:
    """**M20.1.2.** Checked against `brain.agents.model`'s own constants, so this is the model's
    bound arriving at the form rather than the form agreeing with itself.

    Deleting this lets a form offer a name longer than the model will store, which is a person
    typing an answer that fails only when it is saved.
    """
    identity = section_schema(Section.IDENTITY)
    persona = section_schema(Section.PERSONA)

    assert field_on(identity, "identity.display_name")["maxLength"] == DISPLAY_NAME_CHARS
    assert field_on(persona, "persona")["maxLength"] == PERSONA_CHARS


def test_a_schema_that_changes_changes_the_form_with_no_edit_here() -> None:
    """**M20.1.2.** What "generated" has to mean. A schema with a tighter bound gives a form with
    a tighter bound, and a property the sectioning does not name is not given a field, so the
    form is the schema cut by the sections and nothing else.

    Deleting this lets the form pass every test above as a constant that happens to match
    today's model.
    """
    changed = manifest()
    identity_fields = changed["$defs"]["ManifestIdentity"]["properties"]
    identity_fields["display_name"]["maxLength"] = 7
    identity_fields["nickname"] = {"type": "string", "title": "Nickname"}

    form = section_schema(Section.IDENTITY, changed)

    assert field_on(form, "identity.display_name")["maxLength"] == 7
    assert "nickname" not in form["properties"]["identity"]["properties"]


def test_every_manifest_path_is_a_field_on_exactly_one_section_form() -> None:
    """**M20.1.2.** The seven forms together are the whole manifest, once, in the order the
    builder lists its sections. A path on no form is a field nobody can set, and a path on
    two is a field whose value depends on which form was saved last.

    Deleting this lets a section form quietly drop a field the sectioning gave it.
    """
    document = form_document()
    found: list[str] = []
    for entry in document["sections"]:
        for head, fragment in entry["schema"]["properties"].items():
            if "properties" in fragment:
                found.extend(f"{head}.{tail}" for tail in fragment["properties"])
            else:
                found.append(head)

    assert sorted(found) == sorted(MANIFEST_PATHS)
    assert len(found) == len(set(found))
    assert [entry["section"] for entry in document["sections"]] == [one.value for one in Section]


def test_a_path_the_schema_does_not_describe_is_refused_rather_than_left_out() -> None:
    """**M20.1.2.** A shorter form looks exactly like a complete one, so a path missing from the
    schema stops the form, whether it is missing at the top or inside a holder.

    Deleting this lets a model refactor remove a field from the builder with every test green.
    """
    no_persona = manifest()
    del no_persona["properties"]["persona"]
    no_summary = manifest()
    del no_summary["$defs"]["ManifestIdentity"]["properties"]["summary"]

    with pytest.raises(BuilderError, match="'persona'"):
        section_schema(Section.PERSONA, no_persona)
    with pytest.raises(BuilderError, match=r"'identity\.summary'"):
        section_schema(Section.IDENTITY, no_summary)
    assert field_on(section_schema(Section.PERSONA), "persona")["type"] == "string"


def test_every_reference_on_a_section_form_resolves_inside_that_form() -> None:
    """**M20.1.2.** A field left as a `$ref` is resolved by the form library against the
    definitions the form carries, so every one has to be there or the field renders as nothing.

    Deleting this lets a section form reach the browser with a scope or a leash rung it cannot
    draw.
    """
    for entry in form_document()["sections"]:
        schema = entry["schema"]
        for reference in references_in(schema["properties"]):
            assert reference.removeprefix("#/$defs/") in schema["$defs"], (
                entry["section"],
                reference,
            )


def test_no_docstring_reaches_somebody_building_an_agent() -> None:
    """**M20.1.2.** The model's docstrings are in its schema and are written for engineers, so
    they are removed. The sibling assertions are the point of the pair: the model really does
    carry them, so this is not passing because there was nothing to remove, and the titles a
    person does need are still there.

    Deleting this puts module paths and work breakdown ids under the fields of a product form.
    """
    assert "description" in manifest()["$defs"]["Scope"]
    assert "description" not in set(keys_in(form_document()))

    identity = section_schema(Section.IDENTITY)
    assert field_on(identity, "identity.display_name")["title"] == "Display Name"


def test_the_prose_is_removed_and_a_field_or_a_value_with_the_same_name_is_not() -> None:
    """**M20.1.2.** Removing descriptions is a rule about a keyword, and two things share its
    name without being one: a field called `description` and a default value holding that key.
    And prose inside a list of schemas, which is where `anyOf` keeps its alternatives, is still
    prose; no manifest field carries one today, so the case is built rather than found.

    Deleting this lets the prose filter delete a real field the day a model grows one, or miss
    a docstring the day a field becomes a union.
    """
    changed = manifest()
    changed["properties"]["persona"]["default"] = {"description": "a value somebody set"}
    changed["$defs"]["Placeholder"]["properties"]["description"] = {
        "type": "string",
        "description": "prose",
    }
    changed["$defs"]["Clause"]["properties"]["value"]["anyOf"][0]["description"] = "prose"

    form = section_schema(Section.PERSONA, changed)

    assert form["properties"]["persona"]["default"] == {"description": "a value somebody set"}
    assert form["$defs"]["Placeholder"]["properties"]["description"] == {"type": "string"}
    assert "description" not in form["$defs"]["Placeholder"]
    assert form["$defs"]["Clause"]["properties"]["value"]["anyOf"][0] == {"type": "string"}


def test_a_holder_split_across_sections_carries_its_own_fields_requirements_and_no_default() -> (
    None
):
    """**M20.1.2.** `authority` is edited in two sections. Each carries only its own fields and
    only the requirements the model makes of those, and neither carries the model's default
    for the whole object, which names every field and would submit the other section's values
    from this one.

    Deleting this lets saving the knowledge section write the tool lists nobody on that screen
    was shown.
    """
    knowledge = section_schema(Section.KNOWLEDGE)["properties"]["authority"]
    tools = section_schema(Section.TOOLS)["properties"]["authority"]

    assert list(knowledge["properties"]) == ["scope"]
    assert sorted(tools["properties"]) == ["allowed_tools", "capabilities", "required_tools"]
    assert "default" not in knowledge
    assert "default" not in tools
    assert knowledge["additionalProperties"] is False

    identity_form = section_schema(Section.IDENTITY)
    identity = identity_form["properties"]["identity"]
    assert sorted(identity["required"]) == sorted(
        manifest()["$defs"]["ManifestIdentity"]["required"]
    )
    assert identity_form["required"] == ["identity"]
    assert "required" not in section_schema(Section.PERSONA)


def test_the_console_renders_exactly_the_document_this_module_produces() -> None:
    """**M20.1.2.** The console's suite renders `console/tests/fixtures/manifest-form.json`, so
    that file has to be this module's output today. If it fails, the model changed: regenerate
    the file with the command in `REGENERATE` and let the console suite judge the new form.

    Deleting this lets the console go on proving a form generated from a manifest that no
    longer exists.
    """
    fixture = json.loads(CONSOLE_FIXTURE.read_text(encoding="utf-8"))
    assert fixture == form_document(), f"the console fixture is stale; run {REGENERATE}"


def test_the_document_is_written_to_the_one_path_it_is_given(tmp_path: Path) -> None:
    """**M20.1.2.** Regenerating the fixture is how a model change reaches the console suite, so
    the command has to write this document, with LF endings on a machine that writes CRLF by
    default, and has to refuse to guess a path.

    Deleting this lets the regeneration step write something the drift test then rejects, or
    a file that dirties a clean tree.
    """
    target = tmp_path / "form.json"

    assert main([str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8")) == form_document()
    assert b"\r\n" not in target.read_bytes()
    assert main([]) == 2
