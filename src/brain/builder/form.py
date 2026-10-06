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
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
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

#: Why a field's label comes from a table here rather than from the model's own title.
A_PERSON_READS_WORDS_NOT_FIELD_NAMES: Final = (
    "pydantic titles a field by title-casing its Python name and a model by its class name, so "
    "the schema alone labels a form 'ManifestIdentity', 'Display Name' and 'SideEffect'. The "
    "words a person reads are written once here, per manifest path and per field of each part, "
    "and travel beside the schema as its uiSchema, so the schema stays the model's own and a "
    "field the model gains still renders, under its pydantic title, until a test here asks for "
    "its words."
)

#: Which version of this document the console reads. A console meeting another version
#: refuses it rather than rendering a form from a shape it was not written against. Version 2
#: added each section's title and its uiSchema of plain words (2026-09-29).
FORM_SCHEMA: Final = "brain.builder.form.v2"

#: The keyword a docstring arrives under.
PROSE: Final = "description"

#: Keywords whose value maps a name to a schema, so the names inside are not keywords: a
#: field called `description` is a field and is kept.
SCHEMA_MAPS: Final[frozenset[str]] = frozenset({"properties", "$defs"})

#: Keywords whose value is data rather than schema, copied untouched: a default that happens
#: to hold a key called `description` is a value somebody set.
DATA_KEYWORDS: Final[frozenset[str]] = frozenset({"default", "enum", "const", "examples"})


# ------------------------------------------------------------------------ the plain words
@dataclass(frozen=True)
class Words:
    """What a person reads for one field.

    `help` says what the field is for and, where the model holds it to a grammar, the grammar in
    words, so the format is known before anything is submitted. A length or a lower bound is not
    written here: the console states those from the schema's own keywords, so a bound tightened
    on the model is a sentence changed with no edit to this table.
    """

    title: str
    help: str = ""
    #: For a list: what one entry is called, and the words on the button that adds one.
    item: str = ""
    add: str = ""
    #: For a field that is one of several shapes (`anyOf`): the words for each shape, in order.
    shapes: tuple[Words, ...] = ()
    #: A longer text box rather than one line, for prose.
    long: bool = False
    #: Carried by the form and not drawn: the server sets it when the draft is published, so a
    #: box to type into would be a control that changes nothing (2026-09-29).
    set_by_the_server: bool = False


#: What each section is called on the Write step. The console's confirmations and the draft's
#: problems name a section in these words too, so a sentence never points at a heading that is
#: not on the screen.
SECTION_TITLES: Final[Mapping[Section, str]] = MappingProxyType(
    {
        Section.IDENTITY: "Name and summary",
        Section.PERSONA: "Instructions",
        Section.KNOWLEDGE: "Knowledge",
        Section.SKILLS: "Skills",
        Section.TOOLS: "Tools and permissions",
        Section.CONNECTORS: "Connected sources",
        Section.LEASH: "Supervision",
        Section.TESTS: "Test questions",
    }
)

SET_AT_PUBLISH: Final = "Set by the server when the draft is published."

#: The words for every manifest path, exhaustive over `MANIFEST_PATHS` (the unit suite checks).
FIELD_WORDS: Final[Mapping[str, Words]] = MappingProxyType(
    {
        "identity.display_name": Words(
            "Display name", "The name people see in the agent list and in a conversation."
        ),
        "identity.summary": Words("Summary", "One or two sentences on what it is for."),
        "identity.template_id": Words("Address", SET_AT_PUBLISH, set_by_the_server=True),
        "identity.version": Words("Version", SET_AT_PUBLISH, set_by_the_server=True),
        "identity.published_by": Words("Published by", SET_AT_PUBLISH, set_by_the_server=True),
        "persona": Words(
            "Instructions",
            "What the agent is for and how it answers, in plain sentences. Nothing written here "
            "can widen what it may read.",
            long=True,
        ),
        "tier": Words("Model size", "How much thinking it does. Main suits most agents."),
        "placeholders": Words(
            "Questions for whoever installs it",
            "What each company must answer when it installs this agent, such as where its price "
            "list is kept.",
            item="Question",
            add="Add a question",
        ),
        "authority.scope": Words(
            "Records it may read",
            "Conditions every record must meet. With none it narrows nothing, and it never reads "
            "more than the person using it may.",
        ),
        "connectors": Words(
            "Connectors",
            "The systems it needs connected before it can be switched on, each by the "
            "connector's name: helpdesk.",
            item="Connector",
            add="Add a connector",
        ),
        "skills": Words(
            "Skills",
            "Reviewed procedures it follows, each pinned to the version that was reviewed.",
            item="Skill",
            add="Add a skill",
        ),
        "authority.allowed_tools": Words(
            "Tools it may use",
            "Each by the tool's name: helpdesk.read_ticket. Only these can be called, or drawn "
            "in a procedure.",
            item="Tool",
            add="Add a tool it may use",
        ),
        "authority.capabilities": Words(
            "Permissions",
            "What it may do, each written as a verb, a colon and a thing, with a field after a "
            "dot if you need one: read:invoice.total. The verbs are read, write, invoke, approve "
            "and admin.",
            item="Permission",
            add="Add a permission",
        ),
        "authority.required_tools": Words(
            "Tools it cannot work without",
            "Tools this install must have before it can be switched on, each by the tool's name.",
            item="Tool",
            add="Add a tool it cannot work without",
        ),
        "guardrails.max_side_effect": Words(
            "The most it may do", "The strongest effect any one of its actions may have."
        ),
        "guardrails.leash": Words(
            "Approval settings",
            "How much a person is involved before an action. Every action starts at Shadow, and "
            "a setting is raised later from the agent's own runs.",
            item="Approval setting",
            add="Add an approval setting",
        ),
        "golden_set": Words(
            "Test questions",
            "Questions it must still answer well once installed, each with what a good answer "
            "says.",
            item="Test question",
            add="Add a test question",
        ),
    }
)

#: The words for every field of every part a section form reaches through a `$ref`, keyed by
#: the part's definition name and the field. Exhaustive over what the sections reach.
PART_WORDS: Final[Mapping[tuple[str, str], Words]] = MappingProxyType(
    {
        ("Placeholder", "key"): Words(
            "Short name",
            "Lower-case letters, digits and underscores, starting with a letter: price_list.",
        ),
        ("Placeholder", "prompt"): Words("Question", "What the person installing it is asked."),
        ("Placeholder", "required"): Words("It must be answered"),
        ("Scope", "clauses"): Words(
            "Conditions",
            "Every condition must hold for a record to count.",
            item="Condition",
            add="Add a condition",
        ),
        ("Clause", "field"): Words(
            "Field",
            "The record's field: lower-case letters, digits, underscores and dots, starting "
            "with a letter: department.",
        ),
        ("Clause", "op"): Words("Test"),
        ("Clause", "value"): Words(
            "Value",
            "One value for is and starts with, a list for is one of, and none for any value.",
            shapes=(
                Words("One value"),
                Words("A list of values", item="Value", add="Add a value"),
                Words("No value"),
            ),
        ),
        ("SkillRef", "name"): Words(
            "Skill name",
            "As the Skills page shows it: lower-case letters, digits, hyphens and underscores, "
            "starting with a letter.",
        ),
        ("SkillRef", "digest"): Words(
            "Fingerprint",
            "The reviewed version's fingerprint: 64 characters, digits and the letters a to f.",
        ),
        ("Capability", "value"): Words("Permission", "Such as read:invoice.total."),
        ("LeashRung", "target"): Words(
            "Action",
            "A kind of record, or one action on it after a dot: invoice, or "
            "ticket.update_status. Lower-case letters, digits and underscores.",
        ),
        ("LeashRung", "scope"): Words(
            "Records it applies to", "With no conditions it applies to every record."
        ),
        ("LeashRung", "rung"): Words("Setting"),
        ("GoldenCase", "question"): Words("Question", long=True),
        ("GoldenCase", "expectation"): Words(
            "What a good answer says",
            "In words rather than an exact answer: it is judged, not matched.",
            long=True,
        ),
    }
)

#: What each choice of every choice-list a section form reaches is called, by the definition's
#: name and the choice's value. The rung words are `console/src/pages/agents/agentActions.ts`'s.
CHOICE_WORDS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "Tier": {"none": "No model", "small": "Small", "main": "Main", "heavy": "Heavy"},
        "SideEffect": {
            "none": "Nothing: it only reads",
            "draft": "Drafts for a person to send",
            "write": "Changes records",
            "send": "Sends messages",
            "money": "Moves money",
        },
        "Op": {"eq": "is", "in": "is one of", "prefix": "starts with", "any": "any value"},
        "AutonomyTier": {"0": "Shadow", "1": "Assisted", "2": "Autonomous"},
    }
)

#: The uiSchema key for a label, a help sentence, a control, and a list of choices' names.
UI_TITLE: Final = "ui:title"
UI_HELP: Final = "ui:description"
UI_WIDGET: Final = "ui:widget"
UI_CHOICES: Final = "ui:enumNames"
UI_OPTIONS: Final = "ui:options"
#: A holder object's own heading is not drawn: its fields sit directly under the section's.
UI_LABEL: Final = "ui:label"


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


def definition_named(fragment: Mapping[str, Any]) -> str | None:
    """The definition a `$ref` names, by name, or None when the fragment names none."""
    reference = fragment.get("$ref")
    return reference.rsplit("/", 1)[-1] if isinstance(reference, str) else None


def _ui_for(
    fragment: Mapping[str, Any],
    definitions: Mapping[str, Any],
    words: Words | None,
    within: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """The uiSchema for one field, following it into a part's fields and a list's entries.

    A field with no words gets none, so it renders under the schema's own title rather than not
    at all; `tests/unit/test_builder_form.py` is where a missing entry is caught. A part that
    names itself again below is not followed a second time, because a definition that recurs
    would otherwise have no end.
    """
    ui: dict[str, Any] = {}
    if words is not None:
        ui[UI_TITLE] = words.title
        if words.help:
            ui[UI_HELP] = words.help
        if words.long:
            ui[UI_WIDGET] = "textarea"
        if words.set_by_the_server:
            ui[UI_WIDGET] = "hidden"
    named = definition_named(fragment)
    if named is not None and named in CHOICE_WORDS:
        ui[UI_CHOICES] = dict(CHOICE_WORDS[named])
    if named is not None and named in within:
        return ui
    inside = within if named is None else within | {named}
    resolved = _resolved(fragment, definitions)
    shapes = resolved.get("anyOf")
    if words is not None and words.shapes and isinstance(shapes, list):
        ui["anyOf"] = [
            _ui_for(shape, definitions, said, inside)
            for shape, said in zip(shapes, words.shapes, strict=False)
        ]
    if resolved.get("type") == "object":
        for name, inner in resolved.get("properties", {}).items():
            part = None if named is None else PART_WORDS.get((named, name))
            ui[name] = _ui_for(inner, definitions, part, inside)
    elif resolved.get("type") == "array":
        entry = None if words is None or not words.item else Words(words.item)
        ui["items"] = _ui_for(resolved.get("items", {}), definitions, entry, inside)
        options: dict[str, Any] = {"orderable": False}
        if words is not None and words.add:
            options["addLabel"] = words.add
        ui[UI_OPTIONS] = options
    return ui


def section_ui(section: Section, form: Mapping[str, Any]) -> dict[str, Any]:
    """The plain words for one section's form, as a uiSchema in the form's own nesting.

    `form` is `section_schema(section)`. A field at the top of the manifest is labelled by its
    path; a holder cut to this section (`identity`, `authority`, `guardrails`) draws no heading
    of its own and its fields are labelled by their dotted paths. See
    `A_PERSON_READS_WORDS_NOT_FIELD_NAMES`.
    """
    definitions: Mapping[str, Any] = form.get("$defs", {})
    own = set(paths_in(section))
    ui: dict[str, Any] = {}
    for head, fragment in form.get("properties", {}).items():
        if head in own:
            ui[head] = _ui_for(fragment, definitions, FIELD_WORDS.get(head))
            continue
        holder: dict[str, Any] = {UI_LABEL: False}
        for tail, inner in fragment.get("properties", {}).items():
            holder[tail] = _ui_for(inner, definitions, FIELD_WORDS.get(f"{head}.{tail}"))
        ui[head] = holder
    return ui


def form_document(schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Every section's form, in the order `compose.Section` lists them (M20.1.2).

    This is the body the route answers and the document the console's fixture holds: each
    section's name, its title on the Write step, its schema, and its words as a uiSchema.
    """
    manifest: Mapping[str, Any] = TemplateManifest.model_json_schema() if schema is None else schema
    sections: list[dict[str, Any]] = []
    for one in Section:
        form = section_schema(one, manifest)
        sections.append(
            {
                "section": one.value,
                "title": SECTION_TITLES[one],
                "schema": form,
                "ui": section_ui(one, form),
            }
        )
    return {"schema": FORM_SCHEMA, "sections": sections}


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
