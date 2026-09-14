/**
 * The builder's form: every section the API sent, each one generated from its own schema.
 *
 * **Nothing here knows what a manifest contains.** The sections, their order, their fields,
 * their titles, their bounds and their controls all come from the document `manifestSections.ts`
 * reads, and each section is rendered by `SchemaForm`, which is react-jsonschema-form with this
 * console's rules about a generated form applied to it. A field the model gains is a control on
 * this screen with no edit to this file, and that is the property M20.1.2 asks for.
 *
 * **Each section is its own form with its own ids.** Two sections can declare an object of the
 * same name, `authority` being the one today, and the library names every control after the path
 * to it, so two forms on one page would give two inputs one id and a label would point at
 * whichever came first. Each form is prefixed with its section's name instead.
 *
 * **Nothing here saves anything.** A section's submission is handed up with the section's name,
 * already cut to what that section declares. Keeping a draft, versioning it and publishing it are
 * M20.1.4 and the publish gate, and no route accepts any of them yet.
 *
 * Task ids: M20.1.2
 */

import type { ApiFailure } from "../api/errors";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./DataTable";
import { sectionData, type ManifestSection } from "./manifestSections";
import { SchemaForm } from "./SchemaForm";

interface ManifestFormProps {
  /** What is being built, for a screen reader and for anybody reading it. */
  readonly caption: string;
  /** The sections, from `readManifestForm`. Never assembled here. */
  readonly sections: readonly ManifestSection[];
  /** The draft so far, as a manifest document in the manifest's own nesting. */
  readonly draft?: unknown;
  /** Called with a section's name and what that section submitted. */
  readonly onSubmit?: (section: string, data: unknown) => void;
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
  return (
    <div className="manifest-form">
      <p className="manifest-form__caption">{caption}</p>

      {sections.map((one) => (
        <section key={one.section} className="manifest-form__section" aria-label={one.section}>
          <SchemaForm
            caption={one.section}
            schema={one.schema}
            idPrefix={one.section}
            formData={sectionData(one.schema, draft)}
            busy={busy}
            onSubmit={(data) => onSubmit?.(one.section, data)}
          />
        </section>
      ))}

      {failure ? (
        <Notice title={SOMETHING_DID_NOT_WORK} traceId={failure.traceId}>
          <p>{failure.message}</p>
        </Notice>
      ) : null}
    </div>
  );
}
