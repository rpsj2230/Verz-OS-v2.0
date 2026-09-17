/**
 * Every generated form in this console. One schema in, one submission out.
 *
 * **The form is assembled from a document rather than written by anybody.** That is the
 * reason to use a form library at all and it is also the reason this file is careful:
 * nobody looks at a generated screen before it renders, so anything that must not reach a
 * person has to be a property of the assembly. `formSchema.ts` holds those properties and
 * this renders what it decided; the argument for the split, and for each rule, is there.
 *
 * **A withheld field renders `ui/Lock.tsx` through `WithheldField` below, and the field is
 * replaced whole.** Not the widget: replacing only the widget leaves the library's field
 * template wrapped around it, and that template is where a description, a help block, an
 * error slot and an `aria-describedby` come from. Each of those is a place the reason a
 * field was withheld could be shown beside the lock by somebody being helpful, and the
 * reason is the part that discloses. Replacing the field means the slots do not exist.
 *
 * **Rejected: `readonly` or `disabled` on a locked field.** Both are one word, both are what
 * a form library offers for exactly this, and both are wrong here. A disabled input is a
 * control in the tab order that says "you could have this" and carries the field's current
 * value in the DOM, which for a withheld field is a value that must not be in the browser at
 * all. A read-only input renders the value. The lock renders no value because it is given
 * none.
 *
 * **Rejected: a theme package.** `@rjsf/core` is the plain-HTML theme and emits `.rjsf-field`,
 * `.control-label` and `.form-control`, which `styles/app.css` paints from tokens. A
 * Bootstrap, MUI or Ant theme would bring a second design system with its own palette, its
 * own dark-mode story and its own opinion about what a validation error looks like, and this
 * console's whole theme is one file of tokens. The two templates overridden below are the
 * ones whose default markup carries an opinion this console does not share: the submit button
 * is styled `btn btn-info`, and the error list is a red panel, which is a severity variant of
 * the thing `ui/Notice.tsx` has exactly one of.
 *
 * **The validator compiles schemas with `new Function`, so it needs `unsafe-eval`.** That is
 * `@rjsf/validator-ajv8` reaching ajv, at `ajv/dist/compile/index.js:89`, and it is a real
 * conflict with the Content-Security-Policy the README proposes: under that policy the call
 * throws and the form stops validating. Ajv's standalone mode precompiles validators and
 * cannot help, because the schema arrives at run time. The README sets out the four ways out
 * and does not choose between them, because the choice belongs with whoever writes the policy
 * and mounts the first form. The one worth knowing is that the cheapest answer is to drop
 * client-side validation entirely: the console is not a trust boundary, the API validates
 * what it is sent whatever this form believed, and what is lost is a round trip rather than a
 * check.
 *
 * **Nothing here fetches and nothing here decides.** The schema, the record and the locked
 * fields all arrive from the API. There is no route that sends any of them yet: see the
 * README for what that leaves unverified.
 *
 * **A refused submission is drawn on the fields the API named.** The failure's problems go to
 * the library as `extraErrors`, which draws each under its own field through the one error
 * slot every widget's `aria-describedby` already names, and the input is marked `aria-invalid`.
 * A problem the form has no input for is listed under the failure notice instead, by
 * `ui/FailureNotice.tsx`. Two things are kept out on purpose. The list at the top, "Check these
 * answers", stays about what was typed into this screen: the library merges `extraErrors` into
 * it, so the API's sentences are filtered back out there, because a refusal is the API's and
 * already has a notice with its reference. And the error slot is this console's own plain list
 * rather than the library's, whose markup carries a `text-danger` class that is a severity
 * variant of the thing `ui/Notice.tsx` has exactly one of.
 *
 * Task ids: M32.5.2.2, M27.8.5
 */

import Form from "@rjsf/core";
import { errorId, getSubmitButtonOptions } from "@rjsf/utils";
import type {
  ErrorListProps,
  FieldErrorProps,
  FieldProps,
  RegistryFieldsType,
  RJSFSchema,
  SubmitButtonProps,
  UiSchema,
} from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import { useEffect, useMemo, useRef } from "react";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { Lock } from "../ui/Lock";
import { Notice } from "../ui/Notice";
import { formShape, LOCK_FIELD, problemsOnFields, withoutWithheld } from "./formSchema";
import { FailureNotice } from "../ui/FailureNotice";

/** The one heading over any failure a form reports. The API's own sentence goes underneath. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/** The heading over the form's own validation messages. About this screen, never about data. */
export const CHECK_THESE_ANSWERS = "Check these answers";

/**
 * A field this caller may not see.
 *
 * It renders the property's own title, which the API disclosed by sending the property, and
 * the lock, which says the same thing to everybody. It takes the whole `FieldProps` object
 * because that is the library's signature and reads two things out of it, neither of which is
 * a value: `Lock` is called with nothing, in the shape `render_lock` has on the Python side.
 *
 * The title is a `span` rather than a `label`. A label with no control is a label pointing at
 * nothing, and giving it a control to point at is the disabled input this file exists to
 * refuse.
 */
function WithheldField({ schema, name }: FieldProps) {
  const title = typeof schema.title === "string" && schema.title !== "" ? schema.title : name;
  return (
    <div className="rjsf-field form-group">
      <span className="control-label">{title}</span>
      <div className="form-withheld">
        <Lock />
      </div>
    </div>
  );
}

/**
 * The fields this console registers. Exactly one, and it is the lock.
 *
 * Declared at module level rather than inside the component, so the object identity is stable
 * across renders and the library is not handed a new registry every time a key is pressed.
 */
const FIELDS: RegistryFieldsType = { [LOCK_FIELD]: WithheldField };

/**
 * The submit button, in the console's own button style rather than the library's.
 *
 * The library's own version renders `btn btn-info`, which is a Bootstrap 3 class this project
 * has no stylesheet for, and it also spreads a caller-supplied props object onto the button.
 * That object can carry a `className` and a `style`, which is a route from a payload to a
 * colour on the screen, so it is read for its text and for nothing else.
 */
function SubmitButton({ uiSchema }: SubmitButtonProps) {
  const { submitText, norender } = getSubmitButtonOptions(uiSchema);
  if (norender) {
    return null;
  }
  return (
    <div className="form-actions">
      <button type="submit" className="button">
        {submitText}
      </button>
    </div>
  );
}

/**
 * The form's own validation messages, in the one notice this console has.
 *
 * These are about what somebody typed into this screen and never about what the API decided,
 * which is why showing them at all is safe. A locked field cannot appear here: it is not
 * required and has no widget to validate. `Notice` has one appearance and no severity
 * variants, for the reason its own file gives.
 */
function ErrorList({ errors, registry }: ErrorListProps) {
  // The API's sentences are merged into `errors` by the library and are taken back out here: they
  // are drawn beside their fields and belong to the failure notice, which carries the reference.
  const fromTheApi = apiProblemsOf(registry.formContext);
  const typed = errors.filter(
    (error) => !fromTheApi.some((one) => `.${one.field}` === error.property && one.message === error.message),
  );
  if (typed.length === 0) {
    return null;
  }
  return (
    <Notice title={CHECK_THESE_ANSWERS}>
      <ul>
        {typed.map((error) => (
          <li key={`${error.property ?? ""} ${error.message ?? ""}`}>{error.stack}</li>
        ))}
      </ul>
    </Notice>
  );
}

/**
 * The sentences under one field, in the one plain list every problem in this console is drawn as.
 *
 * The id is the library's own `errorId`, which is the id each widget's `aria-describedby` already
 * names, so a screen reader reads the sentence with the input without anything else wiring it.
 */
function FieldErrors({ errors = [], fieldPathId }: FieldErrorProps) {
  const shown = errors.filter((one) => one !== "");
  if (shown.length === 0) {
    return null;
  }
  return (
    <ul id={errorId(fieldPathId)} className="field-description field-problems">
      {shown.map((one, at) => (
        <li key={at}>{one}</li>
      ))}
    </ul>
  );
}

/** What this console passes the library as `formContext`: the API's problems, and nothing else. */
interface Context {
  readonly apiProblems: readonly FieldProblem[];
}

function apiProblemsOf(context: unknown): readonly FieldProblem[] {
  // A cast at the library boundary: `formContext` is typed `any` by the library, and the only value
  // this console ever passes is `Context`, read back through an `Array.isArray` check.
  const listed = (context as Partial<Context> | undefined)?.apiProblems;
  return Array.isArray(listed) ? listed : [];
}

const TEMPLATES = {
  ButtonTemplates: { SubmitButton },
  ErrorListTemplate: ErrorList,
  FieldErrorTemplate: FieldErrors,
};

const NO_PROBLEMS: readonly FieldProblem[] = Object.freeze([]);

interface SchemaFormProps {
  /** What the form is, for a screen reader and for anybody reading it. */
  readonly caption: string;
  /** The schema, as the API sent it. Never assembled here. */
  readonly schema: RJSFSchema;
  /** Presentation hints from the caller. Locked fields are added to this, never taken from it. */
  readonly uiSchema?: UiSchema;
  /** The record being edited, already through the redactor. */
  readonly formData?: unknown;
  /**
   * The names of fields the API withheld, from `lockedFieldsFor`. A set of names and nothing
   * else: there is no reason in it, because `LockedField` carries none.
   */
  readonly locked?: ReadonlySet<string>;
  /** Called with the submitted record, already stripped of every field it may not send. */
  readonly onSubmit?: (data: unknown) => void;
  /** The failure, in the API's own words, or null. */
  readonly failure?: ApiFailure | null;
  /** A request is in flight. The form stays on the screen and stops accepting a submission. */
  readonly busy?: boolean;
  /**
   * What every control id on this form begins with. The library's own default when unset.
   *
   * A form alone on a page never needs it. Two generated forms on one page do, when their
   * schemas share a property name: the library names each control after the path to it, so
   * both would build the same id and a label would point at whichever came first.
   */
  readonly idPrefix?: string;
}

const NO_LOCKS: ReadonlySet<string> = new Set();

export function SchemaForm({
  caption,
  schema,
  uiSchema = {},
  formData,
  locked = NO_LOCKS,
  onSubmit,
  failure = null,
  busy = false,
  idPrefix = "root",
}: SchemaFormProps) {
  // Memoised because the schema is recompiled by the validator whenever its identity changes,
  // and because handing the library a new schema object on every keystroke is how a generated
  // form becomes slow enough that somebody switches the validation off.
  const shape = useMemo(() => formShape(schema, locked, uiSchema), [schema, locked, uiSchema]);
  const problems = failure?.problems ?? NO_PROBLEMS;
  // Memoised on the failure, because the library re-merges `extraErrors` whenever its identity
  // changes, and a new object on every render would put a refusal back after it was corrected.
  const placed = useMemo(() => problemsOnFields(shape, problems), [shape, problems]);
  const context = useMemo<Context>(() => ({ apiProblems: problems }), [problems]);
  const form = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // `aria-invalid` on each control whose described-by list names a drawn problem. The core
    // widgets write their own `aria-describedby` and take no `aria-invalid`, so it is set here,
    // after the library has drawn the lists, rather than by replacing every widget it ships.
    const root = form.current;
    if (root === null) {
      return;
    }
    for (const control of root.querySelectorAll("input, select, textarea")) {
      const named = (control.getAttribute("aria-describedby") ?? "")
        .split(" ")
        .some((id) => id !== "" && root.ownerDocument.getElementById(id)?.classList.contains("field-problems") === true);
      if (named) {
        control.setAttribute("aria-invalid", "true");
      } else {
        control.removeAttribute("aria-invalid");
      }
    }
  });

  return (
    <div className="form" ref={form}>
      <p className="form__caption">{caption}</p>

      <Form
        idPrefix={idPrefix}
        schema={shape.schema}
        uiSchema={shape.uiSchema}
        formData={formData}
        validator={validator}
        fields={FIELDS}
        templates={TEMPLATES}
        extraErrors={placed.errors}
        formContext={context}
        disabled={busy}
        // The library's own HTML5 validation would put the browser's wording on the screen in
        // the browser's own language, next to this console's. One source of sentences.
        noHtml5Validate
        onSubmit={(submitted) => {
          onSubmit?.(withoutWithheld(submitted.formData, shape.withheld));
        }}
      />

      {failure ? <FailureNotice failure={failure} fields={placed.placed} /> : null}
    </div>
  );
}
