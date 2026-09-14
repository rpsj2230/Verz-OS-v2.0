"""The builder's form, generated one section at a time from the manifest's own JSON Schema.

`brain.builder.compose` decides which section each manifest path is edited in, and builds no
form. M20.1.2 is the form: generated from the manifest JSON Schema and rendered by
react-jsonschema-form. `console/src/components/ManifestForm.tsx` renders it, and this module
is what it renders from, which is one JSON Schema per section cut out of
`TemplateManifest.model_json_schema()`.

**Generated means a change to the model is a change to the form, with no edit here or in the
console.** Every field a section form carries is the model's own schema for its path, copied
rather than described, so a bound tightened on `ManifestIdentity` tightens the input, a field
that changes type changes the control, and an enum that gains a member gains an option.
`brain.agents.install.StepField` makes the same argument for the install wizard, and it is the
reason to use a form library at all: a hand-written field is a second description of the
manifest, and the second description is the one that goes stale without failing anything.

**A section form keeps the manifest's nesting rather than flattening its paths.** The install
wizard flattens, one field per dotted path with references resolved into it, because each of
its screens lists fields one at a time. A generated form wants the other shape:
`identity.summary` sits under an `identity` object, so what the form submits is a piece of a
manifest document in the manifest's own shape, and a `$ref` left in a field resolves against
the `$defs` the section carries, which is how the form library reads references. **Rejected:
dotted property names.** They look like the flat map `TemplateManifest.document` produces, and
the form library would submit exactly that: a map keyed by strings with dots in, which is a
third spelling of a manifest beside the model and the flat document, for one screen.

**A holder is cut to its section, and so is what it requires.** `authority` is split between
two sections, its scope edited under knowledge and its tool lists under tools, for the reason
`compose.SECTION_OF_PATH` records. Each section's `authority` object therefore declares only
its own fields, requires only those of them the model requires, and **does not carry the
model's default for the whole object**, because that default names every field and a form in
one section would submit the other section's values as though somebody had typed them there.
`additionalProperties: false` is kept, so a submission cannot carry a field the section does
not show.

**The prose pydantic copies out of a docstring does not reach a person.** A model's docstring
is written for the next engineer, pydantic puts it into the schema as a `description`, and the
form library renders a description under its field. Left in, somebody building an agent would
read module paths and work breakdown ids. Descriptions are removed on the way out and nothing
else is: titles, bounds, patterns, enums and defaults are the model's own statements about a
field. See `THE_ENGINEERS_PROSE_IS_NOT_THE_AUTHORS_HELP`.

**A path the schema does not describe is refused rather than left out.** A path `paths_in`
names and the schema does not carry would be a field this form silently skips, which is
`compose.A_PATH_IN_NO_SECTION_IS_A_FIELD_NOBODY_EDITS_AND_NOBODY_REVIEWS` arriving through the
schema rather than through the sectioning.

**How the console gets it: it does not yet.** Nothing under `/api/v1` answers this document,
and `form_document` is what that route would answer. The console's suite renders the same
document from `console/tests/fixtures/manifest-form.json`, which
`tests/unit/test_builder_form.py` holds equal to `form_document()`, so a fixture gone stale
fails the unit suite rather than testing a form the model no longer describes, and
`python -m brain.builder.form <path>` rewrites it. **Rejected: shipping the document inside
the console's bundle.** A console would then render the manifest of the release it was built
from rather than of the server it is talking to, and those are the same only for as long as
nobody deploys the two separately.

Scope: domain logic. Nothing here opens a connection or renders anything; `main` writes the
one file it is told to.

Task ids: M20.1.2
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from brain.agents.template import TemplateManifest
from brain.builder.compose import BuilderError, Section, paths_in

# ------------------------------------------------------------------ written-down reasons
#: Why a docstring pydantic copied into the schema is removed from a form.
THE_ENGINEERS_PROSE_IS_NOT_THE_AUTHORS_HELP: Final = (
    "pydantic copies a model's docstring into its JSON Schema as a description, and the form "
    "library renders a description under the field it belongs to. A docstring is written for "
    "the next engineer, so rendered it would put module paths and work breakdown ids in front "
    "of somebody building an agent. Descriptions are removed from a section form and nothing "
    "else is, because every other keyword is the model's own statement about the field."
)

#: Why a path missing from the schema stops the form rather than shortening it.
A_FIELD_THE_SCHEMA_DOES_NOT_DESCRIBE_IS_NOT_SKIPPED: Final = (
    "Every manifest path is edited in a section, so a path the schema does not carry is a "
    "field the generated form would silently leave out: nobody is asked about it and nobody "
    "reviewing the agent sees it. The form is refused instead, because a shorter form looks "
    "exactly like a complete one."
)

#: Which version of this document the console reads. A console meeting another version
#: refuses it rather than rendering a form from a shape it was not written against.
FORM_SCHEMA: Final = "brain.builder.form.v1"

#: The keyword a docstring arrives under.
PROSE: Final = "description"

#: Keywords whose value maps a name to a schema, so the names inside are not keywords: a
#: field called `description` is a field and is kept.
SCHEMA_MAPS: Final[frozenset[str]] = frozenset({"properties", "$defs"})

#: Keywords whose value is data rather than schema, copied untouched: a default that happens
#: to hold a key called `description` is a value somebody set.
DATA_KEYWORDS: Final[frozenset[str]] = frozenset({"default", "enum", "const", "examples"})


def _without_prose(schema: object) -> Any:
    """A copy of a schema with every docstring removed and nothing else changed."""
    if isinstance(schema, list):
        return [_without_prose(one) for one in schema]
    if not isinstance(schema, Mapping):
        return schema
    kept: dict[str, Any] = {}
    for key, value in schema.items():
        if key == PROSE:
            continue
        if key in DATA_KEYWORDS:
            kept[key] = value
        elif key in SCHEMA_MAPS and isinstance(value, Mapping):
            kept[key] = {name: _without_prose(one) for name, one in value.items()}
        else:
            kept[key] = _without_prose(value)
    return kept


def _resolved(fragment: Mapping[str, Any], definitions: Mapping[str, Any]) -> Mapping[str, Any]:
    """The definition a `$ref` names, or the fragment itself when it names none."""
    reference = fragment.get("$ref")
    if not isinstance(reference, str):
        return fragment
    resolved: Mapping[str, Any] = definitions[reference.rsplit("/", 1)[-1]]
    return resolved


def _undescribed(path: str) -> BuilderError:
    return BuilderError(
        f"the manifest schema does not describe {path!r}, so the form would leave it out. "
        f"{A_FIELD_THE_SCHEMA_DOES_NOT_DESCRIBE_IS_NOT_SKIPPED}"
    )


def section_schema(section: Section, schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One section's form, as a JSON Schema cut out of the manifest's own (M20.1.2).

    `schema` is the manifest JSON Schema and defaults to the model's, so a test can hand in a
    schema that has changed and watch the form follow it. Without that parameter the only way
    to show the form is generated would be to edit the model, which is a mutation rather than a
    test.
    """
    manifest: Mapping[str, Any] = TemplateManifest.model_json_schema() if schema is None else schema
    declared: Mapping[str, Any] = manifest.get("properties", {})
    definitions: Mapping[str, Any] = manifest.get("$defs", {})

    properties: dict[str, Any] = {}
    for path in paths_in(section):
        head, _, tail = path.partition(".")
        if head not in declared:
            raise _undescribed(path)
        if not tail:
            properties[head] = declared[head]
            continue
        holder = _resolved(declared[head], definitions)
        fields: Mapping[str, Any] = holder.get("properties", {})
        if tail not in fields:
            raise _undescribed(path)
        cut = properties.setdefault(
            head,
            {
                "type": "object",
                "title": holder.get("title", head),
                "additionalProperties": False,
                "properties": {},
            },
        )
        cut["properties"][tail] = fields[tail]
        if tail in holder.get("required", ()):
            cut.setdefault("required", []).append(tail)

    form: dict[str, Any] = {"type": "object", "properties": properties, "$defs": definitions}
    required = [head for head in properties if head in manifest.get("required", ())]
    if required:
        form["required"] = required
    cleaned: dict[str, Any] = _without_prose(form)
    return cleaned


def form_document(schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Every section's form, in the order `compose.Section` lists them (M20.1.2).

    This is the body a route would answer and the document the console's fixture holds.
    """
    manifest: Mapping[str, Any] = TemplateManifest.model_json_schema() if schema is None else schema
    return {
        "schema": FORM_SCHEMA,
        "sections": [
            {"section": one.value, "schema": section_schema(one, manifest)} for one in Section
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Write the form document to one path, with LF line endings on every platform."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print(
            "usage: python -m brain.builder.form <path to write the document to>", file=sys.stderr
        )
        return 2
    text = json.dumps(form_document(), indent=2, ensure_ascii=False) + "\n"
    Path(arguments[0]).write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
