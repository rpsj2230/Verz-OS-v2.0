/**
 * The words a generated form says in its own voice: what a field accepts, what went wrong with an
 * answer, and the library's own few strings. No React.
 *
 * **A generated form speaks in the words of the schema it was given, and the library's words are
 * not those.** Left alone, `@rjsf/core` says "must have required property 'Display Name'", "must
 * NOT have more than 120 characters" and "Submit": ajv's messages, with the field's name pasted
 * in, and a button nobody chose the words of. The owner met exactly those on the agent builder on
 * 2026-09-29. So every message is rewritten here from its keyword, into a sentence that tells a
 * person what to do ("Enter the display name."), and the library's strings are replaced whole.
 *
 * **A field's bounds are stated before anything is submitted, and they are read from the schema.**
 * `boundsSentence` turns `maxLength`, `minLength`, `minimum` and `maximum` into one sentence under
 * the field, so nobody learns the limit from a refusal. The API writes what a grammar means in words
 * (a pattern cannot be read aloud), and the bound comes from the schema itself rather than from a
 * sentence somebody typed, so a bound tightened on the model changes this sentence with no edit.
 *
 * **The label a message names is the label on the screen.** A message is placed under its field
 * already; the list at the top of the form ("Check these answers") needs the field named, and it
 * is named by the same `ui:title` the field is drawn with, found by walking the uiSchema down the
 * error's path, so the two cannot disagree.
 *
 * Rejected: passing ajv a localiser (`ajv-i18n`). It translates the same sentences into another
 * language and keeps their shape, so "must NOT have fewer than 1 characters" becomes the same
 * sentence in English with the same missing verb.
 *
 * Task ids: M20.1.2, M32.5.2.2
 */

import { TranslatableString, replaceStringParameters } from "@rjsf/utils";
import type { RJSFSchema, RJSFValidationError, UiSchema } from "@rjsf/utils";

/** The submit button's words when a caller names none. The library's own is "Submit". */
export const SAVE = "Save";

/** What an item's remove button says, beside the item's own name for a screen reader. */
export const REMOVE = "Remove";
export const MOVE_UP = "Move up";
export const MOVE_DOWN = "Move down";
export const COPY = "Copy";
export const ADD = "Add";

/** Said after a label whose field must be answered. */
export const REQUIRED_MARK = "(required)";

/** The placeholder option on a choice with no default: nothing is chosen until somebody chooses. */
export const CHOOSE_ONE = "Choose one";

/** The library's own strings, in this console's words. A string not listed keeps its English. */
const LIBRARY_WORDS: Partial<Record<TranslatableString, string>> = {
  [TranslatableString.ArrayItemTitle]: "Entry",
  [TranslatableString.EmptyArray]: "None yet.",
  [TranslatableString.AddButton]: ADD,
  [TranslatableString.AddItemButton]: ADD,
  [TranslatableString.CopyButton]: COPY,
  [TranslatableString.MoveDownButton]: MOVE_DOWN,
  [TranslatableString.MoveUpButton]: MOVE_UP,
  [TranslatableString.RemoveButton]: REMOVE,
  [TranslatableString.ClearButton]: "Clear",
  [TranslatableString.NewStringDefault]: "",
  [TranslatableString.OptionPrefix]: "Choice %1",
  [TranslatableString.TitleOptionPrefix]: "%1, choice %2",
  [TranslatableString.KeyLabel]: "%1 name",
  [TranslatableString.UnknownFieldType]: "This answer cannot be edited here.",
  [TranslatableString.UnsupportedField]: "This answer cannot be edited here.",
  [TranslatableString.UnsupportedFieldWithId]: "This answer cannot be edited here.",
  [TranslatableString.UnsupportedFieldWithReason]: "This answer cannot be edited here.",
  [TranslatableString.UnsupportedFieldWithIdAndReason]: "This answer cannot be edited here.",
  [TranslatableString.InvalidObjectField]: "This answer cannot be edited here.",
};

/** The form library's `translateString`: this console's words, the library's where it has none. */
export function libraryWords(key: TranslatableString, params?: string[]): string {
  return replaceStringParameters(LIBRARY_WORDS[key] ?? key, params);
}

// ------------------------------------------------------------------------ reading a schema
type Loose = Readonly<Record<string, unknown>>;

function isLoose(value: unknown): value is Loose {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberAt(schema: Loose, key: string): number | undefined {
  const value = schema[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** A fragment with its `$ref` followed into the root's definitions, siblings winning. */
function resolved(fragment: Loose, root: Loose): Loose {
  const reference = fragment["$ref"];
  if (typeof reference !== "string") {
    return fragment;
  }
  const named = reference.split("/").pop() ?? "";
  const definitions = isLoose(root["$defs"]) ? root["$defs"] : isLoose(root["definitions"]) ? root["definitions"] : {};
  const found = definitions[named];
  if (!isLoose(found)) {
    return fragment;
  }
  const { $ref: _dropped, ...siblings } = fragment;
  return { ...resolved(found, root), ...siblings };
}

/** The path of an error, as the names and indices it walks: `.a.0.b` is `["a", "0", "b"]`. */
function stepsOf(property: string | undefined): string[] {
  return (property ?? "").split(".").filter((one) => one !== "");
}

/** The schema at a path, following objects, list entries and references, or null. */
function schemaAt(root: Loose, steps: readonly string[]): Loose | null {
  let here: Loose = resolved(root, root);
  for (const step of steps) {
    const properties = here["properties"];
    const items = here["items"];
    if (/^\d+$/.test(step) && isLoose(items)) {
      here = resolved(items, root);
    } else if (isLoose(properties) && isLoose(properties[step])) {
      here = resolved(properties[step], root);
    } else {
      return null;
    }
  }
  return here;
}

/** The uiSchema at a path: a list entry's words sit under `items`, not under its index. */
function uiAt(ui: UiSchema | undefined, steps: readonly string[]): Loose | null {
  let here: unknown = ui;
  for (const step of steps) {
    if (!isLoose(here)) {
      return null;
    }
    here = /^\d+$/.test(step) ? here["items"] : here[step];
  }
  return isLoose(here) ? here : null;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function lowerFirst(words: string): string {
  return words.slice(0, 1).toLowerCase() + words.slice(1);
}

/**
 * One sentence stating a field's bounds, from the schema's own keywords, or "".
 *
 * Only the bounds a person can meet by typing: a length, a lowest and a highest number. A pattern
 * is said in words by whoever wrote the schema's uiSchema, because a regular expression is not a
 * sentence.
 */
export function boundsSentence(schema: RJSFSchema | undefined): string {
  // A choice says its bounds by offering only what is inside them.
  if (!isLoose(schema) || Array.isArray(schema["enum"]) || schema["const"] !== undefined) {
    return "";
  }
  const type = schema["type"];
  if (type === "string") {
    const shortest = numberAt(schema, "minLength");
    const longest = numberAt(schema, "maxLength");
    const least = shortest !== undefined && shortest > 1 ? shortest : undefined;
    if (least !== undefined && longest !== undefined) {
      return `Between ${String(least)} and ${String(longest)} characters.`;
    }
    if (longest !== undefined) {
      return `Up to ${String(longest)} characters.`;
    }
    if (least !== undefined) {
      return `At least ${String(least)} characters.`;
    }
    return "";
  }
  if (type === "integer" || type === "number") {
    const kind = type === "integer" ? "A whole number" : "A number";
    const lowest = numberAt(schema, "minimum");
    const highest = numberAt(schema, "maximum");
    if (lowest !== undefined && highest !== undefined) {
      return `${kind} from ${String(lowest)} to ${String(highest)}.`;
    }
    if (lowest !== undefined) {
      return `${kind}, ${String(lowest)} or more.`;
    }
    if (highest !== undefined) {
      return `${kind}, ${String(highest)} or less.`;
    }
    return `${kind}.`;
  }
  return "";
}

// ------------------------------------------------------------------------ the messages
/** What a field is called at a path: its label on the screen, then the schema's title. */
function labelAt(root: Loose, ui: UiSchema | undefined, steps: readonly string[], fallback: string | undefined): string {
  const words = said(uiAt(ui, steps)?.["ui:title"]) ?? said(schemaAt(root, steps)?.["title"]) ?? said(fallback);
  return words ?? "This answer";
}

/** A field the library draws as a choice rather than a box to type in. */
function isChoice(schema: Loose | null): boolean {
  return schema !== null && (Array.isArray(schema["enum"]) || schema["const"] !== undefined || schema["type"] === "boolean");
}

/** What to do about one refusal, as a sentence about the field it sits under. */
function sentenceFor(error: RJSFValidationError, root: Loose, ui: UiSchema | undefined): string {
  const steps = stepsOf(error.property);
  const field = schemaAt(root, steps);
  const label = labelAt(root, ui, steps, error.title);
  const params = isLoose(error.params) ? error.params : {};
  const limit = typeof params["limit"] === "number" ? String(params["limit"]) : "";
  const enter = isChoice(field) ? `Choose the ${lowerFirst(label)}.` : `Enter the ${lowerFirst(label)}.`;
  switch (error.name) {
    case "required":
      return enter;
    case "minLength":
      return Number(limit) <= 1 ? enter : `Use at least ${limit} characters.`;
    case "maxLength":
      return `Use at most ${limit} characters.`;
    case "pattern":
    case "format":
      return said(uiAt(ui, steps)?.["ui:description"]) === undefined
        ? "This is not in a form it accepts."
        : "This is not in the form described above.";
    case "minimum":
      return `Enter ${limit} or more.`;
    case "exclusiveMinimum":
      return `Enter more than ${limit}.`;
    case "maximum":
      return `Enter ${limit} or less.`;
    case "exclusiveMaximum":
      return `Enter less than ${limit}.`;
    case "type": {
      const wanted = params["type"];
      if (wanted === "integer") {
        return "Enter a whole number.";
      }
      if (wanted === "number") {
        return "Enter a number.";
      }
      return /^\d+$/.test(steps[steps.length - 1] ?? "") ? `${enter.slice(0, -1)}, or remove it.` : enter;
    }
    case "enum":
    case "const":
      return "Choose one of the options.";
    case "minItems":
      return `Add at least ${limit}.`;
    case "maxItems":
      return `Add no more than ${limit}.`;
    case "uniqueItems":
      return "Each entry must be different.";
    case "anyOf":
    case "oneOf":
      return "Fill this in one of the ways described.";
    case "additionalProperties":
      return "This form cannot keep that answer.";
    default:
      return "Check this answer.";
  }
}

/**
 * The form library's `transformErrors`: every refusal the validator made, in words a person acts on.
 *
 * `message` is the sentence drawn under the field. `stack` is the line in the list at the top of
 * the form, which is not beside anything, so it names the field too unless the sentence already
 * does.
 */
export function plainErrors(errors: RJSFValidationError[], ui: UiSchema | undefined, schema: RJSFSchema): RJSFValidationError[] {
  const root: Loose = isLoose(schema) ? schema : {};
  return errors.map((error) => {
    const message = sentenceFor(error, root, ui);
    const label = labelAt(root, ui, stepsOf(error.property), error.title);
    const named = message.toLowerCase().includes(label.toLowerCase());
    return { ...error, message, stack: named ? message : `${label}: ${message}` };
  });
}
