/**
 * The builder's form: every section the API sent, each one generated from its own schema.
 *
 * **Nothing here knows what a manifest contains.** The sections, their order, their headings, their
 * fields, their labels, their bounds and their controls all come from the document
 * `manifestSections.ts` reads, and each section is rendered by `SchemaForm`, which is
 * react-jsonschema-form drawn from the kit with this console's rules about a generated form applied
 * to it. A field the model gains is a control on this screen with no edit to this file, and that is
 * the property M20.1.2 asks for.
 *
 * **Each section is headed in the API's words and saved by a button that names it.** The heading is
 * the section's `title`, the same words the draft's problems and the save confirmation use, so a
 * sentence on this page never points at a heading that is not on it. Seven Save buttons on one page
 * would be seven buttons nobody could tell apart, so each says which section it saves.
 *
 * **Each section is its own form with its own ids.** Two sections can declare an object of the
 * same name, `authority` being the one today, and the library names every control after the path
 * to it, so two forms on one page would give two inputs one id and a label would point at
 * whichever came first. Each form is prefixed with its section's name instead.
 *
 * **Nothing here saves anything.** A section's submission is handed up with the section's name and
 * heading, already cut to what that section declares; the page confirms and sends it.
 *
 * Task ids: M20.1.2
 */

import { useMemo } from "react";
import type { UiSchema } from "@rjsf/utils";
import type { ApiFailure } from "../api/errors";
import { FormSection } from "./kit/formTemplates";
import { sectionData, type ManifestSection } from "./manifestSections";
import { SchemaForm } from "./SchemaForm";
import { FailureNotice } from "../ui/FailureNotice";

/** The words on a section's own Save button. */
export function saveWords(heading: string): string {
  return `Save ${heading.slice(0, 1).toLowerCase()}${heading.slice(1)}`;
}

interface ManifestFormProps {
  /** What is being built, for a screen reader. The page's own heading already shows it. */
  readonly caption: string;
  /** The sections, from `readManifestForm`. Never assembled here. */
  readonly sections: readonly ManifestSection[];
  /** The draft so far, as a manifest document in the manifest's own nesting. */
  readonly draft?: unknown;
  /** Called with a section's name, what that section submitted, and the section's heading. */
  readonly onSubmit?: (section: string, data: unknown, heading: string) => void;
  /** The failure, in the API's own words, or null. */
  readonly failure?: ApiFailure | null;
  /** A request is in flight. Every section stays on the screen and stops accepting a submission. */
  readonly busy?: boolean;
}

export function ManifestForm({
  caption,
  sections,
  draft,
  onSubmit,
  failure = null,
  busy = false,
}: ManifestFormProps) {
  // Memoised on the sections, because `SchemaForm` rebuilds its shape and the validator recompiles
  // whenever the uiSchema's identity changes, which would be on every keystroke otherwise.
  const words = useMemo(
    () =>
      new Map<string, UiSchema>(
        sections.map((one) => [one.section, { ...one.ui, "ui:submitButtonOptions": { submitText: saveWords(one.title) } }]),
      ),
    [sections],
  );
  return (
    <div className="manifest-form" aria-label={caption} role="group">
      {sections.map((one) => (
        <FormSection key={one.section} handle={`section-${one.section}`} label={one.section} title={one.title}>
          <SchemaForm
            schema={one.schema}
            uiSchema={words.get(one.section) ?? one.ui}
            idPrefix={one.section}
            formData={sectionData(one.schema, draft)}
            busy={busy}
            onSubmit={(data) => onSubmit?.(one.section, data, one.title)}
          />
        </FormSection>
      ))}

      {failure ? <FailureNotice failure={failure} /> : null}
    </div>
  );
}
