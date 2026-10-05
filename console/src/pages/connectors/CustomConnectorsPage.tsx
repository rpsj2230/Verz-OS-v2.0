/**
 * Add an API: submit a connector for an API this release does not ship, and review one somebody
 * else submitted (M11.7.8).
 *
 * **Submit.** Paste the API's OpenAPI document; the operations it declares are offered to pick from,
 * read from the pasted text in the browser so a person sees what they are choosing. Each entity
 * names its list operation, its one-record operation, where its id is, and every field it maps, with
 * the field's classification and whether it is kept in the index or read live. The vendor's ceiling
 * and the page stating it are required, and the key scheme is one of the three the API offers. The
 * API judges everything and every problem is drawn beside its field; nothing is kept until it is
 * whole, and then it waits.
 *
 * **Review.** Every definition is listed with its state. To a reader who may connect it, the whole
 * definition is shown, document included, and to a reader who did not submit this revision, Approve
 * and Reject, each confirmed, naming the revision read. A submitter is never offered their own, and
 * the API refuses it in words if asked anyway.
 *
 * **Then the normal Connect flow.** An approved API is on the Connectors screen with its form, and
 * its key is kept like any other source's. This page connects nothing.
 *
 * Task ids: M11.7.8
 */

import { CircleCheck, CircleX, Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { unmatchedProblems } from "../../api/problems";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  EmptyState,
  FailureState,
  Fact,
  FactList,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { FieldProblems } from "../../ui/FieldProblems";

export const CUSTOM_HEADING = "Add an API";
export const CUSTOM_LEDE =
  "Connect a system this release does not ship by its specification and a field mapping. A second person who may connect it reviews it, and it is offered on the Connectors screen once approved, with no update.";
export const DEFINITIONS_API_PATH = "/custom-connectors";
export const SUBMIT_LABEL = "Submit for review";
export const APPROVE_LABEL = "Approve";
export const REJECT_LABEL = "Reject";
const FORM = "custom-connector";

export type Classification = "public" | "internal" | "confidential" | "restricted";
export type Shape = "identifier" | "join_key" | "status" | "timestamp" | "label";
export type Scheme = "bearer" | "basic_key_as_user" | "none";
export type ReviewState = "unreviewed" | "approved" | "rejected";

export interface FieldBody {
  target: string;
  source_path: string;
  classification: Classification;
  kept: Shape | null;
}

export interface EntityBody {
  entity: string;
  list_operation: string;
  one_operation: string | null;
  id_path: string;
  named_by: string;
  description: string;
  fields: FieldBody[];
}

export interface Definition {
  readonly name: string;
  readonly label: string;
  readonly state: ReviewState;
  readonly revision: number;
  readonly department: string;
  readonly key_scheme: Scheme;
  readonly ceiling_per_minute: number;
  readonly ceiling_per_day: number | null;
  readonly ceiling_cited: string;
  readonly entities: readonly EntityBody[];
  readonly document: Record<string, unknown> | null;
  readonly submitted_by: string;
  readonly submitted_at: string;
  readonly reviewed_by: string | null;
  readonly reviewable: boolean;
  readonly offered: boolean;
}

export interface DefinitionsPage {
  readonly definitions: readonly Definition[];
  readonly classifications: readonly Classification[];
  readonly shapes: readonly Shape[];
  readonly schemes: readonly Scheme[];
  readonly review: string;
}

/** The words for each choice, so no internal value is shown as if it were a name. */
export const SCHEME_WORDS: Readonly<Record<Scheme, string>> = {
  bearer: "A key sent as a bearer token",
  basic_key_as_user: "A key sent as the user name of HTTP Basic",
  none: "No key: the API answers anybody",
};
export const SHAPE_WORDS: Readonly<Record<Shape | "live", string>> = {
  live: "Read live, never kept",
  identifier: "Kept: an identifier",
  join_key: "Kept: a key to another record",
  status: "Kept: a status",
  timestamp: "Kept: a date and time",
  label: "Kept: the name a person knows it by",
};
export const STATE_WORDS: Readonly<Record<ReviewState, string>> = {
  unreviewed: "Waiting for review",
  approved: "Approved",
  rejected: "Rejected",
};

/** Every GET operation a pasted document declares, by id, or none when it is not JSON yet. */
export function readOperations(text: string): string[] {
  try {
    const parsed: unknown = JSON.parse(text);
    const paths = (parsed as { paths?: unknown }).paths;
    if (typeof paths !== "object" || paths === null) {
      return [];
    }
    const found: string[] = [];
    for (const methods of Object.values(paths as Record<string, unknown>)) {
      const get = (methods as { get?: { operationId?: unknown } } | null)?.get;
      if (typeof get?.operationId === "string") {
        found.push(get.operationId);
      }
    }
    return found.sort();
  } catch {
    return [];
  }
}

function blankField(): FieldBody {
  return { target: "", source_path: "", classification: "internal", kept: null };
}

function blankEntity(): EntityBody {
  return {
    entity: "",
    list_operation: "",
    one_operation: null,
    id_path: "id",
    named_by: "",
    description: "",
    fields: [blankField()],
  };
}

const SELECT_CLASS =
  "h-11 w-full min-w-0 rounded-md border border-input bg-background px-2.5 text-base text-foreground shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive sm:h-9 md:text-sm";

function Field({
  id,
  label,
  problems,
  names,
  children,
}: {
  readonly id: string;
  readonly label: string;
  readonly problems: readonly FieldProblem[];
  readonly names: string | readonly string[];
  readonly children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      <FieldProblems problems={problems} form={FORM} names={names} />
    </div>
  );
}

/** The submit form. `page` supplies the choices the API offers. */
export function SubmitForm({ page, onKept }: { readonly page: DefinitionsPage; readonly onKept: (told: string) => void }) {
  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [department, setDepartment] = useState("");
  const [document, setDocument] = useState("");
  const [scheme, setScheme] = useState<Scheme>("bearer");
  const [perMinute, setPerMinute] = useState("");
  const [perDay, setPerDay] = useState("");
  const [cited, setCited] = useState("");
  const [pageParameter, setPageParameter] = useState("");
  const [pageSize, setPageSize] = useState("");
  const [entities, setEntities] = useState<EntityBody[]>([blankEntity()]);
  const [problems, setProblems] = useState<readonly FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const operations = useMemo(() => readOperations(document), [document]);

  function changeEntity(at: number, change: Partial<EntityBody>): void {
    setEntities((all) => all.map((one, index) => (index === at ? { ...one, ...change } : one)));
  }

  function changeField(at: number, fieldAt: number, change: Partial<FieldBody>): void {
    setEntities((all) =>
      all.map((one, index) =>
        index === at
          ? { ...one, fields: one.fields.map((field, f) => (f === fieldAt ? { ...field, ...change } : field)) }
          : one,
      ),
    );
  }

  function submit(): void {
    setBusy(true);
    setFailure(null);
    setProblems([]);
    const whole = (value: string): number | null => (value.trim() === "" ? null : Number(value));
    void (async () => {
      const result = await request<{ told: string }>(DEFINITIONS_API_PATH, {
        method: "POST",
        body: {
          name,
          label,
          document,
          department,
          key_scheme: scheme,
          ceiling_per_minute: whole(perMinute),
          ceiling_per_day: whole(perDay),
          ceiling_cited: cited,
          page_parameter: pageParameter.trim() === "" ? null : pageParameter,
          page_size: whole(pageSize),
          entities,
        },
      });
      setBusy(false);
      if (!result.ok) {
        setProblems(result.failure.problems);
        setFailure(result.failure.problems.length > 0 ? null : result.failure);
        return;
      }
      onKept(result.data.told);
    })();
  }

  const named = ["name", "label", "department", "document", "key_scheme", "ceiling", "paging", "entities"];
  const loose = unmatchedProblems(
    problems,
    [...named, ...entities.map((_, at) => `entities.${String(at)}`)],
  );

  return (
    <SectionCard title="Submit an API" lede="Everything here is reviewed by a second person before anything is read.">
      <form
        className="grid gap-4"
        aria-label="Submit an API"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id={`${FORM}-name`} label="Short name" problems={problems} names="name">
            <Input id={`${FORM}-name`} value={name} onChange={(e) => { setName(e.target.value); }} />
          </Field>
          <Field id={`${FORM}-label`} label="Name people see" problems={problems} names="label">
            <Input id={`${FORM}-label`} value={label} onChange={(e) => { setLabel(e.target.value); }} />
          </Field>
          <Field id={`${FORM}-department`} label="Department whose people may be granted its records" problems={problems} names="department">
            <Input id={`${FORM}-department`} value={department} onChange={(e) => { setDepartment(e.target.value); }} />
          </Field>
          <Field id={`${FORM}-scheme`} label="How its key is sent" problems={problems} names="key_scheme">
            <select
              id={`${FORM}-scheme`}
              className={SELECT_CLASS}
              value={scheme}
              onChange={(e) => { setScheme(e.target.value as Scheme); }}
            >
              {page.schemes.map((one) => (
                <option key={one} value={one}>{SCHEME_WORDS[one]}</option>
              ))}
            </select>
          </Field>
        </div>
        <Field id={`${FORM}-document`} label="The API's OpenAPI document, as JSON" problems={problems} names="document">
          <Textarea
            id={`${FORM}-document`}
            rows={8}
            className="font-mono text-xs"
            value={document}
            onChange={(e) => { setDocument(e.target.value); }}
          />
        </Field>
        <Note>Only references inside the document are read. Nothing is fetched from anywhere else.</Note>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field id={`${FORM}-minute`} label="Calls a minute the vendor allows" problems={problems} names="ceiling">
            <Input id={`${FORM}-minute`} inputMode="numeric" value={perMinute} onChange={(e) => { setPerMinute(e.target.value); }} />
          </Field>
          <Field id={`${FORM}-day`} label="Calls a day, if it states one" problems={problems} names={[]}>
            <Input id={`${FORM}-day`} inputMode="numeric" value={perDay} onChange={(e) => { setPerDay(e.target.value); }} />
          </Field>
          <Field id={`${FORM}-cited`} label="The vendor's page that says so" problems={problems} names={[]}>
            <Input id={`${FORM}-cited`} value={cited} onChange={(e) => { setCited(e.target.value); }} />
          </Field>
          <Field id={`${FORM}-page`} label="Page parameter, if it pages" problems={problems} names="paging">
            <Input id={`${FORM}-page`} value={pageParameter} onChange={(e) => { setPageParameter(e.target.value); }} />
          </Field>
          <Field id={`${FORM}-size`} label="Records on a full page" problems={problems} names={[]}>
            <Input id={`${FORM}-size`} inputMode="numeric" value={pageSize} onChange={(e) => { setPageSize(e.target.value); }} />
          </Field>
        </div>
        {entities.map((one, at) => (
          <EntityFields
            key={at}
            at={at}
            entity={one}
            operations={operations}
            page={page}
            problems={problems}
            onChange={(change) => { changeEntity(at, change); }}
            onField={(fieldAt, change) => { changeField(at, fieldAt, change); }}
          />
        ))}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 sm:min-h-8"
            onClick={() => { setEntities((all) => [...all, blankEntity()]); }}
          >
            <Plus aria-hidden />
            Add an entity
          </Button>
          <Button type="submit" className="min-h-11 sm:min-h-8" disabled={busy}>
            {SUBMIT_LABEL}
          </Button>
        </div>
        {loose.length === 0 ? null : (
          <ul role="alert" className="text-sm text-crit">
            {loose.map((one, at) => <li key={`${String(at)} ${one.message}`}>{one.message}</li>)}
          </ul>
        )}
        {failure === null ? null : <FailureState failure={failure} />}
      </form>
    </SectionCard>
  );
}

function EntityFields({
  at,
  entity,
  operations,
  page,
  problems,
  onChange,
  onField,
}: {
  readonly at: number;
  readonly entity: EntityBody;
  readonly operations: readonly string[];
  readonly page: DefinitionsPage;
  readonly problems: readonly FieldProblem[];
  readonly onChange: (change: Partial<EntityBody>) => void;
  readonly onField: (fieldAt: number, change: Partial<FieldBody>) => void;
}) {
  const id = `${FORM}-entity-${String(at)}`;
  return (
    <fieldset className="grid gap-3 rounded-md border border-border p-3">
      <legend className="px-1 text-sm font-medium">Entity {at + 1}</legend>
      <FieldProblems problems={problems} form={FORM} names={`entities.${String(at)}`} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id={`${id}-name`} label="What a record is called" problems={[]} names={[]}>
          <Input id={`${id}-name`} value={entity.entity} onChange={(e) => { onChange({ entity: e.target.value }); }} />
        </Field>
        <Field id={`${id}-words`} label="What an agent is told it holds" problems={[]} names={[]}>
          <Input id={`${id}-words`} value={entity.description} onChange={(e) => { onChange({ description: e.target.value }); }} />
        </Field>
        <Field id={`${id}-list`} label="The operation that lists them" problems={[]} names={[]}>
          <select id={`${id}-list`} className={SELECT_CLASS} value={entity.list_operation} onChange={(e) => { onChange({ list_operation: e.target.value }); }}>
            <option value="">Choose an operation</option>
            {operations.map((one) => <option key={one} value={one}>{one}</option>)}
          </select>
        </Field>
        <Field id={`${id}-one`} label="The operation that reads one, if there is one" problems={[]} names={[]}>
          <select
            id={`${id}-one`}
            className={SELECT_CLASS}
            value={entity.one_operation ?? ""}
            onChange={(e) => { onChange({ one_operation: e.target.value === "" ? null : e.target.value }); }}
          >
            <option value="">None</option>
            {operations.map((one) => <option key={one} value={one}>{one}</option>)}
          </select>
        </Field>
        <Field id={`${id}-id`} label="Where a record's id is" problems={[]} names={[]}>
          <Input id={`${id}-id`} value={entity.id_path} onChange={(e) => { onChange({ id_path: e.target.value }); }} />
        </Field>
        <Field id={`${id}-named`} label="The field a person names a record by" problems={[]} names={[]}>
          <select id={`${id}-named`} className={SELECT_CLASS} value={entity.named_by} onChange={(e) => { onChange({ named_by: e.target.value }); }}>
            <option value="">Choose a kept field</option>
            {entity.fields.filter((one) => one.kept !== null && one.target !== "").map((one) => (
              <option key={one.target} value={one.target}>{one.target}</option>
            ))}
          </select>
        </Field>
      </div>
      <table className="w-full text-sm">
        <caption className="text-left text-dim">Fields, each with who may see it and whether it is kept</caption>
        <thead>
          <tr className="text-left">
            <th scope="col">Our name</th>
            <th scope="col">Where it is in the API's record</th>
            <th scope="col">Classification</th>
            <th scope="col">Kept or read live</th>
            <th scope="col"><span className="sr-only">Remove</span></th>
          </tr>
        </thead>
        <tbody>
          {entity.fields.map((one, fieldAt) => (
            <tr key={fieldAt}>
              <td><Input aria-label={`Field ${String(fieldAt + 1)} name`} value={one.target} onChange={(e) => { onField(fieldAt, { target: e.target.value }); }} /></td>
              <td><Input aria-label={`Field ${String(fieldAt + 1)} path`} value={one.source_path} onChange={(e) => { onField(fieldAt, { source_path: e.target.value }); }} /></td>
              <td>
                <select aria-label={`Field ${String(fieldAt + 1)} classification`} className={SELECT_CLASS} value={one.classification} onChange={(e) => { onField(fieldAt, { classification: e.target.value as Classification }); }}>
                  {page.classifications.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </td>
              <td>
                <select
                  aria-label={`Field ${String(fieldAt + 1)} kept`}
                  className={SELECT_CLASS}
                  value={one.kept ?? "live"}
                  onChange={(e) => { onField(fieldAt, { kept: e.target.value === "live" ? null : (e.target.value as Shape) }); }}
                >
                  <option value="live">{SHAPE_WORDS.live}</option>
                  {page.shapes.map((s) => <option key={s} value={s}>{SHAPE_WORDS[s]}</option>)}
                </select>
              </td>
              <td>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove field ${String(fieldAt + 1)}`}
                  disabled={entity.fields.length === 1}
                  onClick={() => { onChange({ fields: entity.fields.filter((_, f) => f !== fieldAt) }); }}
                >
                  <Trash2 aria-hidden />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div>
        <Button type="button" variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={() => { onChange({ fields: [...entity.fields, blankField()] }); }}>
          <Plus aria-hidden />
          Add a field
        </Button>
      </div>
    </fieldset>
  );
}

/** One definition on the review list, with Approve and Reject for a reader who may decide it. */
export function DefinitionCard({ one, review, onDecided }: { readonly one: Definition; readonly review: string; readonly onDecided: (told: string) => void }) {
  const [asking, setAsking] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<readonly FieldProblem[]>([]);

  function decide(approve: boolean): void {
    setBusy(true);
    void (async () => {
      const result = await request<{ told: string }>(`${DEFINITIONS_API_PATH}/${one.name}/review`, {
        method: "POST",
        body: { approve, revision: one.revision },
      });
      setBusy(false);
      setAsking(null);
      if (!result.ok) {
        setProblems(result.failure.problems.length > 0 ? result.failure.problems : [{ field: "review", code: "", message: result.failure.message }]);
        return;
      }
      onDecided(result.data.told);
    })();
  }

  return (
    <SectionCard
      title={one.label}
      headingLevel="h3"
      lede={`${STATE_WORDS[one.state]}, revision ${String(one.revision)}${one.offered ? ", offered on the Connectors screen" : ""}`}
      action={
        one.reviewable ? (
          <div className="flex gap-2">
            <Button size="sm" className="min-h-11 sm:min-h-8" disabled={busy} onClick={() => { setAsking(true); }}>
              <CircleCheck aria-hidden />
              {APPROVE_LABEL}
            </Button>
            <Button size="sm" variant="outline" className="min-h-11 sm:min-h-8" disabled={busy} onClick={() => { setAsking(false); }}>
              <CircleX aria-hidden />
              {REJECT_LABEL}
            </Button>
          </div>
        ) : undefined
      }
    >
      <FactList>
        <Fact label="Department">{one.department}</Fact>
        <Fact label="Key">{SCHEME_WORDS[one.key_scheme]}</Fact>
        <Fact label="Ceiling">
          {`${String(one.ceiling_per_minute)} a minute${one.ceiling_per_day === null ? "" : `, ${String(one.ceiling_per_day)} a day`}, as `}
          <a href={one.ceiling_cited} rel="noreferrer" target="_blank">the vendor states</a>
        </Fact>
      </FactList>
      {one.entities.map((entity) => (
        <div key={entity.entity} className="mt-3">
          <p className="m-0 text-sm font-medium">{`${entity.entity}: listed by ${entity.list_operation}${entity.one_operation === null ? "" : `, one read by ${entity.one_operation}`}`}</p>
          <ul className="m-0 text-sm">
            {entity.fields.map((field) => (
              <li key={field.target}>{`${field.target} (${field.source_path}): ${field.classification}, ${SHAPE_WORDS[field.kept ?? "live"]}`}</li>
            ))}
          </ul>
        </div>
      ))}
      {one.document === null ? null : (
        <details className="mt-3">
          <summary className="text-sm">The specification as submitted</summary>
          <pre className="max-h-64 overflow-auto text-xs">{JSON.stringify(one.document, null, 2)}</pre>
        </details>
      )}
      <FieldProblems problems={problems} form={`${FORM}-${one.name}`} names="review" />
      <ConfirmDialog
        open={asking !== null}
        question={asking === true ? `Approve ${one.label}?` : `Reject ${one.label}?`}
        consequence={review}
        confirmLabel={asking === true ? APPROVE_LABEL : REJECT_LABEL}
        cancelLabel="Not now"
        busy={busy}
        danger={asking === false}
        onConfirm={() => { decide(asking === true); }}
        onCancel={() => { setAsking(null); }}
      />
    </SectionCard>
  );
}

export function CustomConnectorsPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<DefinitionsPage>(DEFINITIONS_API_PATH, version);

  function after(words: string): void {
    setTold(words);
    setVersion((count) => count + 1);
  }

  return (
    <div className="grid gap-4">
      <PageHeader
        crumbs={[{ label: "Connectors", to: "/connectors" }, { label: CUSTOM_HEADING }]}
        title={CUSTOM_HEADING}
        lede={CUSTOM_LEDE}
        actions={
          <Button asChild variant="outline" size="sm" className="min-h-11 sm:min-h-8">
            <Link to="/connectors">Back to Connectors</Link>
          </Button>
        }
      />
      {told === null ? null : <div role="status"><Note kind="done">{told}</Note></div>}
      {answer.failure !== null ? (
        <FailureState failure={answer.failure} />
      ) : answer.data === null ? (
        <LoadingState label="Loading the APIs added here." />
      ) : (
        <>
          <SubmitForm page={answer.data} onKept={after} />
          <SectionCard title="Added APIs" lede={answer.data.review}>
            {answer.data.definitions.length === 0 ? (
              <EmptyState title="No API has been added" description="One submitted here is listed for review." />
            ) : (
              <div className="grid gap-3">
                {answer.data.definitions.map((one) => (
                  <DefinitionCard key={one.name} one={one} review={answer.data?.review ?? ""} onDecided={after} />
                ))}
              </div>
            )}
          </SectionCard>
        </>
      )}
    </div>
  );
}
