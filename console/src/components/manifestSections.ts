/**
 * Reading the builder's form document, and cutting a draft to one section of it. No React.
 *
 * The split is the one `formSchema.ts` makes: this module decides what a builder form document
 * is, `ManifestForm.tsx` renders it through `SchemaForm`. The reason is the case that is always
 * wrong. Whether the console rendered the form the API sent or a form somebody wrote cannot be
 * tested through a component that mounts a form library, and it is the whole of M20.1.2.
 *
 * **The form is the API's, section by section, and the console names no field.** A section's
 * schema is cut out of the manifest's own JSON Schema by `brain.builder.form`, which is where a
 * bound tightened on the model becomes a bound on an input. This module checks that a body is
 * that document and passes each schema through untouched; there is no field name, no title and
 * no bound anywhere in it or in the component, and `tests/manifest-form.test.tsx` holds both
 * files to that by reading every string literal in them against the manifest's paths.
 *
 * **A section is shown the part of a draft it declares, and nothing else.** `authority` is
 * edited in two sections, and the form library submits whatever it was given plus whatever it
 * rendered. Handed the whole draft, the knowledge section would submit the tool lists nobody on
 * that screen was shown, and the schema's `additionalProperties: false` would then refuse its
 * own submission. `sectionData` walks the section's schema rather than a list of names, so it
 * follows the schema too.
 *
 * **A body that is not the document is a failure, never a shorter form.** A version this console
 * was not written against, a section with no name, and a section whose schema is not a form all
 * throw. A form with a section quietly missing looks exactly like a complete one, which is the
 * argument `brain.builder.form` makes about a path the schema does not describe.
 *
 * **Nothing under `/api/v1` sends this document yet.** `brain.builder.form.form_document` is the
 * body a route would answer, and the suite reads the same document from
 * `tests/fixtures/manifest-form.json`, which the Python unit suite holds equal to it.
 *
 * Task ids: M20.1.2
 */

import type { RJSFSchema } from "@rjsf/utils";

/** The version of the document this console reads: `brain.builder.form.FORM_SCHEMA`. */
export const MANIFEST_FORM_SCHEMA = "brain.builder.form.v1";

/** One section of the builder's form. */
export interface ManifestSection {
  /** The section, in the API's own word for it. The console adds nothing to it. */
  readonly section: string;
  /** The section's form, as the API cut it out of the manifest schema. Never assembled here. */
  readonly schema: RJSFSchema;
}

/** A body that was not a builder form. A bug in the console or the API, never an answer. */
export class UnreadableManifestForm extends Error {}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The sections of a builder form document, in the order the API sent them. */
export function readManifestForm(payload: unknown): readonly ManifestSection[] {
  if (!isObject(payload) || payload.schema !== MANIFEST_FORM_SCHEMA) {
    throw new UnreadableManifestForm(`A builder form body is a ${MANIFEST_FORM_SCHEMA} document.`);
  }
  if (!Array.isArray(payload.sections) || payload.sections.length === 0) {
    throw new UnreadableManifestForm("A builder form body carries its sections.");
  }

  const sections: ManifestSection[] = [];
  const seen = new Set<string>();
  for (const entry of payload.sections) {
    if (
      !isObject(entry) ||
      typeof entry.section !== "string" ||
      entry.section === "" ||
      seen.has(entry.section)
    ) {
      throw new UnreadableManifestForm("Every section of a builder form has a name of its own.");
    }
    const schema = entry.schema;
    if (!isObject(schema) || schema.type !== "object" || !isObject(schema.properties)) {
      throw new UnreadableManifestForm(`Section ${entry.section} of a builder form is not a form.`);
    }
    seen.add(entry.section);
    // A cast at the library boundary: an object with properties is what the form library needs
    // to render anything, and proving the rest of JSON Schema structurally here buys nothing the
    // library does not check again when it compiles the schema.
    sections.push({ section: entry.section, schema: schema as RJSFSchema });
  }
  return sections;
}

/**
 * The part of a draft one section's schema declares.
 *
 * Walks the schema rather than naming fields, one level into an object the section cut, so a
 * section that gains a field shows that field's value without anybody editing this.
 */
export function sectionData(schema: RJSFSchema, draft: unknown): Record<string, unknown> {
  const kept: Record<string, unknown> = {};
  if (!isObject(draft)) {
    return kept;
  }
  for (const [name, property] of Object.entries(schema.properties ?? {})) {
    if (!(name in draft)) {
      continue;
    }
    const cut = isObject(property) && property.type === "object" && isObject(property.properties);
    kept[name] = cut ? sectionData(property as RJSFSchema, draft[name]) : draft[name];
  }
  return kept;
}
