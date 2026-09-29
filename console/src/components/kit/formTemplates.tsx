/**
 * A generated form drawn from the kit: every field, list, choice and button `SchemaForm` renders is
 * one of these, so a form assembled from a schema looks and behaves like a page somebody laid out.
 *
 * **Why these exist: the library's own parts are Bootstrap 3, and this console has no Bootstrap.**
 * `@rjsf/core` draws a list's Add button as `btn btn-info btn-add` holding an empty glyph icon. Under
 * the kit's reset that is a button with no padding, no border and no text, 0 by 0 pixels: on
 * 2026-09-29 the owner could not add a tool, a connector or a test question to an agent, and with no
 * tool allowed the Procedure step had nothing to draw. The same was true of every list in every
 * generated form. So the library is handed the console's own templates and widgets, and every
 * control it draws is a kit `Button`, `Input` or `Textarea` with words on it.
 *
 * **Rejected: styling the library's class names.** A rule for `.btn-add` and `.glyphicon-plus`
 * would paint Bootstrap's markup from this console's tokens, which is a second design system kept
 * alive one selector at a time, and it would still be a button whose only content is an icon: its
 * name would be the library's `title` attribute ("Add Item"), the same on every list on the page.
 * Rejected also: a theme package (`@rjsf/shadcn` and friends), for the reason `SchemaForm.tsx` gives.
 *
 * **Every button says what it does, and says which list.** An Add button carries the words the API
 * sent for its list (`ui:options.addLabel`, "Add a tool it may use"), because a page holds nine
 * lists and nine buttons all called Add cannot be told apart by anybody, least of all by a screen
 * reader listing buttons. A Remove button shows "Remove" and is named for its entry ("Remove tool
 * 2"). A list's entries are numbered in their labels for the same reason.
 *
 * **A field says what it accepts before anything is submitted.** Under each label: the API's
 * sentence (`ui:description`) and the bounds the schema holds, read by `boundsSentence`, so the
 * person reads "Up to 120 characters." before typing the hundred and twenty-first.
 *
 * **Not exported from the kit's index**, so a page that imports the kit does not download the form
 * library with it: only `SchemaForm`, which is loaded on demand, imports this file.
 *
 * Task ids: M20.1.2, M27.10.2, M32.5.2.2
 */

import {
  ariaDescribedByIds,
  descriptionId,
  enumOptionSelectedValue,
  enumOptionValueDecoder,
  enumOptionValueEncoder,
  errorId,
  getInputProps,
  getOptionValueFormat,
  getSubmitButtonOptions,
  getUiOptions,
  schemaRequiresTrueValue,
  titleId,
} from "@rjsf/utils";
import type {
  ArrayFieldItemTemplateProps,
  ArrayFieldTemplateProps,
  BaseInputTemplateProps,
  DescriptionFieldProps,
  FieldErrorProps,
  FieldPathId,
  FieldProps,
  FieldTemplateProps,
  IconButtonProps,
  MultiSchemaFieldTemplateProps,
  ObjectFieldTemplateProps,
  RegistryWidgetsType,
  RJSFSchema,
  SubmitButtonProps,
  TemplatesType,
  TitleFieldProps,
  WidgetProps,
} from "@rjsf/utils";
import { ArrowDown, ArrowUp, Copy, Plus, X } from "lucide-react";
import type { ChangeEvent, FocusEvent, ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Lock } from "../../ui/Lock";
import { ADD, CHOOSE_ONE, COPY, MOVE_DOWN, MOVE_UP, REMOVE, REQUIRED_MARK, SAVE, boundsSentence } from "../formWords";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

const LABEL = "text-sm font-medium text-ink";
const HINT = "m-0 text-[12px] leading-snug text-dim";
const CONTROL = "min-h-11 sm:min-h-9";

function lowerFirst(words: string): string {
  return words.slice(0, 1).toLowerCase() + words.slice(1);
}

/** The position of a list entry, from the last step of its path, or null for anything else. */
function entryIndex(fieldPathId: FieldPathId | undefined): number | null {
  const last = fieldPathId?.path[fieldPathId.path.length - 1];
  return typeof last === "number" ? last : null;
}

/**
 * A label with an entry's number on it: "Tool 2". The library numbers an unlabelled entry itself
 * ("Allowed Tools-2"), and that suffix is replaced rather than numbered twice.
 */
export function numbered(label: string, index: number | null): string {
  if (index === null) {
    return label;
  }
  const position = String(index + 1);
  const bare = label.endsWith(`-${position}`) ? label.slice(0, -position.length - 1) : label;
  return `${bare} ${position}`;
}

/** The sentence under a label: the API's words for the field, then its bounds from the schema. */
function hintFor(description: string | undefined, schema: RJSFSchema): string {
  return [description?.trim() ?? "", boundsSentence(schema)].filter((one) => one !== "").join(" ");
}

function Hint({ id, text }: { readonly id: string; readonly text: string }) {
  if (text === "") {
    return null;
  }
  return (
    <p id={id} data-slot="form-hint" className={HINT}>
      {text}
    </p>
  );
}

// ------------------------------------------------------------------------ fields
function FieldTemplate({
  id,
  label,
  children,
  errors,
  help,
  rawDescription,
  hidden,
  required,
  displayLabel,
  schema,
  fieldPathId,
}: FieldTemplateProps) {
  if (hidden) {
    return <div className="hidden">{children}</div>;
  }
  const index = entryIndex(fieldPathId);
  return (
    <div data-slot="form-field" className="flex min-w-0 flex-col gap-1.5">
      {displayLabel ? (
        <label htmlFor={id} className={LABEL}>
          {numbered(label, index)}
          {required && index === null ? <span className="font-normal text-dim"> {REQUIRED_MARK}</span> : null}
        </label>
      ) : null}
      {displayLabel ? <Hint id={descriptionId(id)} text={hintFor(rawDescription, schema)} /> : null}
      {children}
      {errors}
      {help}
    </div>
  );
}

/** A group's heading: a list's or a part's name, and whether it must be answered. */
function Legend({ id, title, required }: { readonly id: string; readonly title: string; readonly required: boolean }) {
  return (
    <legend id={id} className={cn(LABEL, "mb-1.5 p-0")}>
      {title}
      {required ? <span className="font-normal text-dim"> {REQUIRED_MARK}</span> : null}
    </legend>
  );
}

function TitleField({ id, title, required }: TitleFieldProps) {
  return <Legend id={id} title={title} required={required === true} />;
}

function DescriptionField({ id, description }: DescriptionFieldProps) {
  if (typeof description !== "string") {
    return description === undefined ? null : <div id={id}>{description}</div>;
  }
  return <Hint id={id} text={description} />;
}

function ObjectFieldTemplate({ title, description, properties, fieldPathId, schema, required }: ObjectFieldTemplateProps) {
  const index = entryIndex(fieldPathId);
  const nested = fieldPathId.path.length > 0 && index === null && Boolean(title);
  const text = hintFor(typeof description === "string" ? description : undefined, schema);
  return (
    <fieldset
      id={fieldPathId.$id}
      data-slot="form-group"
      className={cn("m-0 flex min-w-0 flex-col gap-4 border-0 p-0", nested && "border-l-2 border-solid border-line pl-3")}
    >
      {title ? <Legend id={titleId(fieldPathId)} title={numbered(title, index)} required={required === true && index === null} /> : null}
      {typeof description === "string" || description === undefined ? (
        <Hint id={descriptionId(fieldPathId)} text={text} />
      ) : (
        description
      )}
      {properties.map((one) =>
        // A hidden field is still carried, as the library's hidden input, so it is drawn bare.
        one.hidden ? (
          <div key={one.name} className="hidden">
            {one.content}
          </div>
        ) : (
          <div key={one.name} className="min-w-0">
            {one.content}
          </div>
        ),
      )}
    </fieldset>
  );
}

// ------------------------------------------------------------------------ lists
/** What a list's Add button says: the API's words, or "Add" and the name of one entry. */
function addWordsFor(options: Readonly<Record<string, unknown>>, itemTitle: string | undefined): string {
  const given = options["addLabel"];
  if (typeof given === "string" && given.trim() !== "") {
    return given;
  }
  return itemTitle === undefined || itemTitle === "" ? ADD : `${ADD} ${lowerFirst(itemTitle)}`;
}

function itemTitleOf(uiSchema: ArrayFieldTemplateProps["uiSchema"], schema: RJSFSchema): string | undefined {
  const items = uiSchema?.items;
  const fromUi = typeof items === "object" && items !== null && !Array.isArray(items) ? getUiOptions(items).title : undefined;
  if (typeof fromUi === "string" && fromUi !== "") {
    return fromUi;
  }
  const entry = schema.items;
  return typeof entry === "object" && entry !== null && !Array.isArray(entry) && typeof entry.title === "string" ? entry.title : undefined;
}

function ArrayFieldTemplate({
  canAdd,
  disabled,
  readonly,
  fieldPathId,
  items,
  onAddClick,
  required,
  schema,
  title,
  uiSchema,
}: ArrayFieldTemplateProps) {
  const options = getUiOptions(uiSchema);
  const heading = typeof options.title === "string" && options.title !== "" ? options.title : title;
  const described = typeof options.description === "string" ? options.description : schema.description;
  const index = entryIndex(fieldPathId);
  return (
    <fieldset id={fieldPathId.$id} data-slot="form-list" className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
      {!heading || options.label === false ? null : (
        <Legend id={titleId(fieldPathId)} title={numbered(heading, index)} required={required === true && index === null} />
      )}
      <Hint id={descriptionId(fieldPathId)} text={hintFor(described, schema)} />
      {items.length === 0 ? null : <div className="flex min-w-0 flex-col gap-2">{items}</div>}
      {canAdd ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(CONTROL, "w-fit max-w-full whitespace-normal")}
          disabled={disabled === true || readonly === true}
          onClick={onAddClick}
        >
          <Plus aria-hidden />
          {addWordsFor(options, itemTitleOf(uiSchema, schema))}
        </Button>
      ) : null}
    </fieldset>
  );
}

function ArrayFieldItemTemplate({ children, buttonsProps, hasToolbar, index, schema, uiSchema }: ArrayFieldItemTemplateProps) {
  const own = getUiOptions(uiSchema).title;
  const noun = numbered(typeof own === "string" && own !== "" ? own : typeof schema.title === "string" ? schema.title : "entry", index);
  const whole = schema.type === "object";
  const { disabled, readonly, hasMoveUp, hasMoveDown, hasCopy, hasRemove, onMoveUpItem, onMoveDownItem, onCopyItem, onRemoveItem } =
    buttonsProps;
  const off = disabled === true || readonly === true;
  const toolbar = hasToolbar ? (
    <div className="flex shrink-0 flex-wrap gap-1.5">
      {hasMoveUp || hasMoveDown ? (
        <>
          <Button type="button" variant="ghost" size="sm" className={CONTROL} disabled={off || !hasMoveUp} onClick={onMoveUpItem} aria-label={`${MOVE_UP} ${lowerFirst(noun)}`}>
            <ArrowUp aria-hidden />
            {MOVE_UP}
          </Button>
          <Button type="button" variant="ghost" size="sm" className={CONTROL} disabled={off || !hasMoveDown} onClick={onMoveDownItem} aria-label={`${MOVE_DOWN} ${lowerFirst(noun)}`}>
            <ArrowDown aria-hidden />
            {MOVE_DOWN}
          </Button>
        </>
      ) : null}
      {hasCopy ? (
        <Button type="button" variant="ghost" size="sm" className={CONTROL} disabled={off} onClick={onCopyItem} aria-label={`${COPY} ${lowerFirst(noun)}`}>
          <Copy aria-hidden />
          {COPY}
        </Button>
      ) : null}
      {hasRemove ? (
        <Button type="button" variant="outline" size="sm" className={CONTROL} disabled={off} onClick={onRemoveItem} aria-label={`${REMOVE} ${lowerFirst(noun)}`}>
          <X aria-hidden />
          {REMOVE}
        </Button>
      ) : null}
    </div>
  ) : null;
  return (
    <div
      data-slot="form-list-item"
      className={cn(
        "flex min-w-0 gap-2",
        whole ? "flex-col rounded-md border border-line bg-panel p-3" : "flex-col sm:flex-row sm:items-end",
      )}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {toolbar}
    </div>
  );
}

function MultiSchemaFieldTemplate({ selector, optionSchemaField }: MultiSchemaFieldTemplateProps) {
  return (
    <div data-slot="form-shapes" className="flex min-w-0 flex-col gap-2">
      {selector}
      {optionSchemaField}
    </div>
  );
}

// ------------------------------------------------------------------------ buttons
/**
 * The submit button, in the kit's primary style, with the caller's words or "Save".
 *
 * The library's `props` object is read for its words and nothing else: it can carry a `className`
 * and a `style`, which is a route from a payload to a colour on the screen.
 */
function SubmitButton({ uiSchema }: SubmitButtonProps) {
  const { norender } = getSubmitButtonOptions(uiSchema);
  if (norender) {
    return null;
  }
  // The library hands this button `{"ui:options": {"submitButtonOptions": ...}}`, holding the
  // caller's words and, while the form is busy, `props.disabled`. Both are read; nothing else is.
  const given = getUiOptions(uiSchema)["submitButtonOptions"] as
    | { readonly submitText?: unknown; readonly props?: { readonly disabled?: unknown } }
    | undefined;
  const words = typeof given?.submitText === "string" && given.submitText.trim() !== "" ? given.submitText : SAVE;
  return (
    <div data-slot="form-actions" className="flex flex-wrap gap-2 pt-1">
      <Button type="submit" className={cn(CONTROL, "w-fit")} disabled={given?.props?.disabled === true}>
        {words}
      </Button>
    </div>
  );
}

/** One of the library's own item buttons, drawn as a kit button with its words showing. */
function wordedButton(words: string, icon: ReactNode) {
  return function WordedButton({ onClick, disabled, id }: IconButtonProps) {
    return (
      <Button type="button" id={id} variant="outline" size="sm" className={CONTROL} disabled={disabled} onClick={onClick}>
        {icon}
        {words}
      </Button>
    );
  };
}

// ------------------------------------------------------------------------ widgets
/**
 * `aria-invalid` on a control whose field has a sentence under it, from the library's own list of
 * that field's errors, so it is set in the same render as the sentence rather than after it.
 */
function invalidity(rawErrors: readonly string[] | undefined): { readonly "aria-invalid"?: true } {
  return rawErrors !== undefined && rawErrors.some((one) => one !== "") ? { "aria-invalid": true } : {};
}

function BaseInputTemplate({
  id,
  htmlName,
  value,
  readonly,
  disabled,
  autofocus,
  onBlur,
  onFocus,
  onChange,
  onChangeOverride,
  options,
  schema,
  type,
  placeholder,
  required,
  rawErrors,
}: BaseInputTemplateProps) {
  const shaped = getInputProps(schema, type, options);
  const shown = shaped.type === "number" || shaped.type === "integer" ? (value || value === 0 ? value : "") : (value ?? "");
  return (
    <Input
      id={id}
      name={htmlName || id}
      className="text-base md:text-sm"
      readOnly={readonly}
      disabled={disabled}
      autoFocus={autofocus}
      placeholder={placeholder}
      required={required}
      {...shaped}
      value={shown as string | number}
      {...invalidity(rawErrors)}
      onChange={
        onChangeOverride ??
        ((event: ChangeEvent<HTMLInputElement>) => {
          onChange(event.target.value === "" ? options.emptyValue : event.target.value);
        })
      }
      onBlur={(event: FocusEvent<HTMLInputElement>) => {
        onBlur(id, event.target.value);
      }}
      onFocus={(event: FocusEvent<HTMLInputElement>) => {
        onFocus(id, event.target.value);
      }}
      aria-describedby={ariaDescribedByIds(id)}
    />
  );
}

function TextareaWidget({ id, htmlName, value, readonly, disabled, autofocus, onBlur, onFocus, onChange, options, placeholder, required, rawErrors }: WidgetProps) {
  return (
    <Textarea
      id={id}
      name={htmlName || id}
      // An unbroken value from the API wraps inside the box rather than widening it on a phone.
      className="min-h-28 text-base whitespace-pre-wrap [overflow-wrap:anywhere] md:text-sm"
      value={typeof value === "string" ? value : ""}
      placeholder={placeholder}
      required={required}
      disabled={disabled}
      readOnly={readonly}
      autoFocus={autofocus}
      rows={typeof options.rows === "number" ? options.rows : 5}
      {...invalidity(rawErrors)}
      onChange={(event) => {
        onChange(event.target.value === "" ? options.emptyValue : event.target.value);
      }}
      onBlur={(event) => {
        onBlur(id, event.target.value);
      }}
      onFocus={(event) => {
        onFocus(id, event.target.value);
      }}
      aria-describedby={ariaDescribedByIds(id)}
    />
  );
}

/**
 * A choice, as the platform's own select in the kit's box. Native rather than the kit's Radix
 * select: a generated form may hold a choice anywhere, a list entry included, and the platform's
 * control is the one every phone already draws as a picker.
 */
function SelectWidget({ schema, id, htmlName, options, value, required, disabled, readonly, autofocus, onChange, onBlur, onFocus, placeholder, rawErrors }: WidgetProps) {
  const { enumOptions, enumDisabled, emptyValue } = options;
  const format = getOptionValueFormat(options);
  const decode = (raw: string): unknown => enumOptionValueDecoder(raw, enumOptions, format, emptyValue);
  const selected = enumOptionSelectedValue(value, enumOptions, false, format, "");
  return (
    <select
      id={id}
      name={htmlName || id}
      data-slot="form-select"
      className="h-11 w-full min-w-0 rounded-md border border-input bg-background px-2.5 text-base text-foreground shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive sm:h-9 md:text-sm"
      value={typeof selected === "string" ? selected : ""}
      {...invalidity(rawErrors)}
      required={required}
      disabled={disabled || readonly}
      autoFocus={autofocus}
      onChange={(event) => {
        onChange(decode(event.target.value));
      }}
      onBlur={(event) => {
        onBlur(id, decode(event.target.value));
      }}
      onFocus={(event) => {
        onFocus(id, decode(event.target.value));
      }}
      aria-describedby={ariaDescribedByIds(id)}
    >
      {schema.default === undefined ? <option value="">{placeholder || CHOOSE_ONE}</option> : null}
      {(enumOptions ?? []).map((one, at) => (
        <option key={String(one.value)} value={enumOptionValueEncoder(one.value, at, format)} disabled={enumDisabled?.includes(one.value) === true}>
          {one.label}
        </option>
      ))}
    </select>
  );
}

function CheckboxWidget({ schema, options, id, htmlName, value, disabled, readonly, label, hideLabel, autofocus, onBlur, onFocus, onChange }: WidgetProps) {
  const text = hintFor(typeof options.description === "string" ? options.description : schema.description, schema);
  return (
    <div data-slot="form-check" className="flex min-w-0 flex-col gap-1">
      <label className="flex min-h-11 items-center gap-2 text-sm text-ink sm:min-h-8">
        <input
          type="checkbox"
          id={id}
          name={htmlName || id}
          className="size-4 shrink-0 accent-primary"
          checked={value === true}
          required={schemaRequiresTrueValue(schema)}
          disabled={disabled || readonly}
          autoFocus={autofocus}
          onChange={(event) => {
            onChange(event.target.checked);
          }}
          onBlur={(event) => {
            onBlur(id, event.target.checked);
          }}
          onFocus={(event) => {
            onFocus(id, event.target.checked);
          }}
          aria-describedby={ariaDescribedByIds(id)}
        />
        {hideLabel === true ? null : <span>{label}</span>}
      </label>
      {hideLabel === true ? null : <Hint id={descriptionId(id)} text={text} />}
    </div>
  );
}

/**
 * The sentences under one field, as a plain list.
 *
 * The id is the library's own `errorId`, which each widget's `aria-describedby` already names, so a
 * screen reader reads the sentence with the input and `SchemaForm` marks that input invalid. No
 * colour, for the reason `ui/Notice.tsx` has none: the words say what to change. The class
 * `field-problems` is what `SchemaForm` and the tests find the list by.
 */
export function FieldErrors({ errors = [], fieldPathId }: FieldErrorProps) {
  const shown = errors.filter((one) => one !== "");
  if (shown.length === 0) {
    return null;
  }
  return (
    <ul id={errorId(fieldPathId)} className="field-problems m-0 flex list-none flex-col gap-0.5 p-0 text-[12.5px] font-medium text-ink">
      {shown.map((one, at) => (
        <li key={at}>{one}</li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------------ the lock
/**
 * A field this caller may not see: its title and the lock, and nothing else.
 *
 * It takes the library's `FieldProps` and reads two things out of it, neither of them a value.
 * The title is a `span` rather than a `label`: a label with no control points at nothing, and giving
 * it a control to point at is the disabled input `SchemaForm.tsx` exists to refuse. The lock's slot
 * keeps the class `form-withheld`, which the tests find it by.
 */
export function WithheldField({ schema, name }: FieldProps) {
  const title = typeof schema.title === "string" && schema.title !== "" ? schema.title : name;
  return (
    <div data-slot="form-field" className="flex min-w-0 flex-col gap-1.5">
      <span className={LABEL}>{title}</span>
      <div className="form-withheld py-2">
        <Lock />
      </div>
    </div>
  );
}

/** The templates a generated form is drawn with. The error list and field errors are `SchemaForm`'s. */
export const KIT_TEMPLATES: Partial<Omit<TemplatesType, "ButtonTemplates">> & { ButtonTemplates: Partial<TemplatesType["ButtonTemplates"]> } = {
  FieldTemplate,
  ObjectFieldTemplate,
  ArrayFieldTemplate,
  ArrayFieldItemTemplate,
  MultiSchemaFieldTemplate,
  TitleFieldTemplate: TitleField,
  DescriptionFieldTemplate: DescriptionField,
  BaseInputTemplate,
  ButtonTemplates: {
    SubmitButton,
    AddButton: wordedButton(ADD, <Plus aria-hidden />),
    RemoveButton: wordedButton(REMOVE, <X aria-hidden />),
    MoveUpButton: wordedButton(MOVE_UP, <ArrowUp aria-hidden />),
    MoveDownButton: wordedButton(MOVE_DOWN, <ArrowDown aria-hidden />),
    CopyButton: wordedButton(COPY, <Copy aria-hidden />),
    ClearButton: wordedButton("Clear", <X aria-hidden />),
  },
};

/** The widgets a generated form is drawn with. A text box is `BaseInputTemplate` above. */
export const KIT_WIDGETS: RegistryWidgetsType = {
  TextareaWidget,
  SelectWidget,
  CheckboxWidget,
};

/**
 * One section of a form made of several: a heading and what goes under it. `ManifestForm` draws each
 * of the builder's sections in one, so the Write step reads as one page of headed parts.
 */
export function FormSection({
  title,
  label,
  children,
  handle,
}: {
  readonly title: string;
  readonly label: string;
  readonly children: ReactNode;
  /** A name for tests and anchors, never shown. */
  readonly handle: string;
}) {
  const headingId = `${handle}-heading`;
  return (
    <section
      id={handle}
      data-slot="form-section"
      data-section={label}
      aria-labelledby={headingId}
      className="flex min-w-0 scroll-mt-4 flex-col gap-3 border-t border-line pt-4 first:border-t-0 first:pt-0"
    >
      <h3 id={headingId} className="m-0 text-[15px] font-semibold text-ink">
        {title}
      </h3>
      {children}
    </section>
  );
}
