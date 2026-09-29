/**
 * Fields and records on the shared page kit: open a classified table by its name, upload a price
 * list as one, and read and change how each of a table's columns is classified.
 *
 * `brain.knowledge.columns` says why this screen exists: a price list carries the sell price
 * everybody needs beside the cost and margin almost nobody may see, and the obvious move, a second
 * safer copy, makes three near-identical price lists within a year. The rules that avoid that are
 * the columns' classification, and this is where a person reads and changes it.
 *
 * **This console does not know which tables are classified and does not ask**
 * (`classificationQuery.THE_CONSOLE_DOES_NOT_KNOW_WHAT_IS_CLASSIFIED`). So the module's first page
 * is a name form and the upload rather than a list, and a table's own page is reached by its name.
 *
 * **A table's page is the kit's**: its title, whether it was uploaded or is built in, the columns'
 * table, and one column's editor at the column's own address, with no count of anything. The
 * name of the table, its key column and its policy epoch are in Advanced. The review and apply
 * behaviour is `A_MARK_IS_APPLIED_AND_LEDGERED`'s and is unchanged: a mark is reviewed first and
 * only the mark that was reviewed is applied, and the judgement about a change comes back from the
 * API (`A_WIDENING_IS_NAMED_BY_THE_API_AND_NEVER_WORKED_OUT_HERE`).
 *
 * **Guarded by the API alone.** Everything here needs `admin:field_classification`; this page
 * draws the editor or not by a flag on the answer, and nothing here decides it.
 *
 * Loaded on demand from the route file: `SchemaForm` carries the form library, the largest thing in
 * this console.
 *
 * Task ids: M7.5.3, M7.7.3, M27.15.41, M27.16.1
 */

import { useCallback, useMemo, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  DetailHeader,
  DetailPage,
  Fact,
  FactList,
  Note,
  PageHeader,
  SectionCard,
} from "../../components/kit";
import { DataTable } from "../../components/DataTable";
import { SchemaForm } from "../../components/SchemaForm";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Notice } from "../../ui/Notice";
import {
  CLASSIFICATION_QUERY_SCHEMA,
  CLASSIFICATION_QUERY_UI,
  COLUMN_EDIT_UI,
  COLUMN_MARK_UI,
  TABLE_FILE_ACCEPT,
  classificationAddress,
  classificationApiPath,
  classificationColumns,
  columnAddress,
  columnByName,
  columnEditSchema,
  columnMarkSchema,
  derivationOptions,
  editableDefaults,
  ENTITY_FIELD,
  markApiPath,
  markDefaults,
  markReviewApiPath,
  readApplied,
  readClassification,
  readReview,
  readUploaded,
  reviewApiPath,
  submittedEdit,
  submittedEntity,
  submittedMark,
  tableApiPath,
  uploadBody,
  type Applied,
  type ColumnMark,
  type ColumnRow,
  type Review,
} from "../classificationQuery";

export const CLASSIFICATION_HEADING = "Fields and records";
export const CLASSIFICATION_LEDE = "Which columns of a table are confidential, what it takes to see each, and which can be worked out from the others.";
export const OPEN_HEADING = "Open a classified table";
export const READING_CLASSIFICATION = "Reading the classification.";

/**
 * What is shown when no entity has been named.
 *
 * It names no entity, for the reason `Records.tsx` gives about its own: "try price_list"
 * would be this console publishing a guess at what the company keeps, to everybody who can
 * open the page, before anybody asked the API anything.
 */
const NOTHING_ASKED_FOR = "Name a table above to see how its columns are classified.";

/**
 * The sentence that stops this screen reading as an editor that saves.
 *
 * Rendered beside the form rather than once at the top, because the place a person concludes
 * they have saved something is the place they pressed a button. It carries no number and
 * offers no action, because there is no action to offer.
 */
const THERE_IS_NO_SAVE =
  "Nothing here changes what anybody may see. A review says what a proposed rule would do; " +
  "applying it to this classification is a change to the source and a deploy, and no record " +
  "of a review is kept.";

/** The heading and the explanation over the upload. */
const UPLOAD_HEADING = "Upload a price list";
const UPLOAD_LEDE =
  "A CSV or XLSX file whose first row is its headings. It becomes a classified table under " +
  "the name you give it: every column starts restricted unless it is a price list column the " +
  "product already classifies, and uploading the same name again replaces its rows and keeps " +
  "the marks you applied.";

/** What is said when the upload is sent with something it needs missing. */
const AN_UPLOAD_NEEDS =
  "Name the table, give it a title and choose a CSV or XLSX file before uploading.";

/** The heading over a refused upload, whose body is the API's own sentence. */
const IT_WAS_NOT_UPLOADED = "The file was not uploaded";

/** What the mark editor says before anything is applied. */
const REVIEW_BEFORE_APPLYING =
  "Review a mark to see what it would change. Apply appears once the review has come back, " +
  "and applies exactly the mark that was reviewed.";

/** The heading over a mark that was applied, and over one that was not. */
const IT_WAS_APPLIED = "Applied: this is now the rule for the column";
const IT_WAS_NOT_APPLIED = "Nothing was applied";

/** What the policy epoch is, where it is shown. */
const WHAT_THE_EPOCH_IS =
  "The policy epoch is the digest answers are cached under. It moves whenever a rule moves, a " +
  "derivation included, so an answer given under the old rule is never served again.";

/** What is said when the address names a column this classification does not carry. */
const NO_SUCH_COLUMN = "No column of this classification has that name.";

/** The heading over a proposal the API said would not load at all. */
const IT_WOULD_NOT_LOAD = "This rule would not load";

/** The heading over a proposal the API called a widening. */
const IT_WIDENS = "This would let more people see more";

/**
 * What a widening means, in the console's own words rather than the API's.
 *
 * Safe to write here because it is a statement about the screen and about the mechanism,
 * not about anybody's data and not an explanation of a refusal. It says what the API's
 * `exposed` list is, which is the one thing a reader has to understand before acting on it:
 * those columns are not the ones being edited.
 */
const WHAT_A_WIDENING_MEANS =
  "The columns below would be reachable by people who cannot reach them today. They are " +
  "not necessarily the column being edited: withholding one column is often what keeps " +
  "another from being worked out.";

/** The heading over a proposal the API said changes nothing that widens. */
const IT_DOES_NOT_WIDEN = "This would not widen anything";

/** What is said when the proposed rule is the one that already stands. */
const NOTHING_WOULD_CHANGE = "This is the rule that already stands.";

/**
 * What one review said, rendered.
 *
 * A separate component so that the branch structure of a verdict is one thing to read. Every
 * word of substance in it came from the API: the changes are its vocabulary, the exposed
 * columns are its list, and the sentence explaining a failure to load is its own. What this
 * console adds are the four headings above, each of which is about this screen.
 */
function ReviewNotice({
  review,
  applying = false,
}: {
  readonly review: Review;
  readonly applying?: boolean;
}) {
  if (review.wouldNotLoad !== "") {
    return (
      <Notice title={IT_WOULD_NOT_LOAD}>
        <p>{review.wouldNotLoad}</p>
      </Notice>
    );
  }
  if (review.widens) {
    return (
      <Notice title={IT_WIDENS}>
        <p>{WHAT_A_WIDENING_MEANS}</p>
        <ul className="review__exposed">
          {review.exposed.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
        <p className="review__changes">{review.changes.join(" ")}</p>
        {applying ? null : <p>{THERE_IS_NO_SAVE}</p>}
      </Notice>
    );
  }
  return (
    <Notice title={IT_DOES_NOT_WIDEN}>
      {review.changes.length === 0 ? (
        <p>{NOTHING_WOULD_CHANGE}</p>
      ) : (
        <p className="review__changes">{review.changes.join(" ")}</p>
      )}
      {applying ? null : <p>{THERE_IS_NO_SAVE}</p>}
    </Notice>
  );
}

/** An epoch shown as the digest it is, shortened so a person can compare two by eye. */
function short(epoch: string): string {
  return epoch.slice(0, 12);
}

/**
 * One column's editor: a rule for a built-in classification, a mark for an uploaded table.
 *
 * One form in both cases, because it is one question, "what should this column's rule be",
 * asked in the vocabulary the classification was written in. A built-in classification is
 * proposed a rule and reviewed, and `THERE_IS_NO_SAVE` stands under it. An uploaded table is
 * proposed a mark and reviewed, and then Apply appears and sends exactly the mark that was
 * reviewed, so a person always reads the verdict before the change is made.
 *
 * A separate component because it holds the state of one review in flight and the
 * classification does not, which is `Matrix.tsx`'s reason for splitting its own editor out.
 * A returned review replaces the previous one and a refusal replaces both, so the screen
 * never shows a verdict about a rule that is no longer in the form.
 */
function ColumnEditor({
  entity,
  row,
  options,
  stored,
  onApplied,
}: {
  readonly entity: string;
  readonly row: ColumnRow;
  readonly options: readonly string[];
  readonly stored: boolean;
  readonly onApplied: (applied: Applied) => void;
}) {
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [reviewed, setReviewed] = useState<{ mark: ColumnMark | null; review: Review } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  // Memoised on the options rather than rebuilt each render, because `SchemaForm` memoises
  // on the schema's identity and the ajv validator recompiles whenever it changes.
  const schema = useMemo(
    () => (stored ? columnMarkSchema(options) : columnEditSchema(options)),
    [options, stored],
  );
  const defaults = useMemo(() => (stored ? markDefaults(row) : editableDefaults(row)), [row, stored]);

  const ask = useCallback(
    (submitted: unknown) => {
      const mark = stored ? submittedMark(submitted) : null;
      const edit = stored ? null : submittedEdit(submitted);
      if (mark === null && edit === null) {
        // Not a rule or a mark this screen recognises. Doing nothing is the answer: a
        // proposal assembled out of values nobody read is a question nobody meant to ask, and
        // the answer to it would be a verdict about who may see what.
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(
          mark === null ? reviewApiPath(entity, row.column) : markReviewApiPath(entity, row.column),
          { method: "POST", body: mark ?? edit },
        );
        setBusy(false);
        if (!result.ok) {
          setReviewed(null);
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setReviewed({ mark, review: readReview(result.data) });
      })();
    },
    [entity, row.column, stored],
  );

  const apply = useCallback(() => {
    const mark = reviewed?.mark ?? null;
    if (mark === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(markApiPath(entity, row.column), {
        method: "PUT",
        body: mark,
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setReviewed(null);
      onApplied(readApplied(result.data));
    })();
  }, [entity, row.column, reviewed, onApplied]);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <SchemaForm
        caption={stored ? `The mark for ${row.column}` : `The rule for ${row.column}`}
        schema={schema}
        uiSchema={stored ? COLUMN_MARK_UI : COLUMN_EDIT_UI}
        formData={defaults}
        failure={failure}
        busy={busy}
        onSubmit={ask}
      />
      <Note>{stored ? REVIEW_BEFORE_APPLYING : THERE_IS_NO_SAVE}</Note>
      {reviewed === null ? null : <ReviewNotice review={reviewed.review} applying={stored} />}
      {reviewed !== null && reviewed.mark !== null && reviewed.review.wouldNotLoad === "" ? (
        <div>
          <Button className="min-h-11 sm:min-h-9" disabled={busy} onClick={apply}>
            Apply this mark
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * What applying a mark did. Held by the classification rather than by the editor, because the
 * grid is read again after an apply and the editor is mounted afresh for the new answer.
 */
function AppliedNotice({ applied }: { readonly applied: Applied }) {
  return (
    <Notice title={applied.applied ? IT_WAS_APPLIED : IT_WAS_NOT_APPLIED}>
      {applied.review.wouldNotLoad === "" ? null : <p>{applied.review.wouldNotLoad}</p>}
      {applied.review.widens ? (
        <>
          <p>{WHAT_A_WIDENING_MEANS}</p>
          <ul className="review__exposed">
            {applied.review.exposed.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="review__epochs">
        Policy epoch <code>{short(applied.review.epochNow)}</code> to{" "}
        <code>{short(applied.review.epochAfter)}</code>
      </p>
      <p>{WHAT_THE_EPOCH_IS}</p>
    </Notice>
  );
}

/** What each field of the upload takes, said before anything is sent. */
export const UPLOAD_HINTS = Object.freeze({
  entity: "The table's name: lower-case letters, digits and underscores, starting with a letter, for example price_list.",
  title: "What people call it, such as Price list 2026.",
  keyColumn: "The heading a question names a row by, exactly as the file's first row writes it, such as SKU.",
  file: "A CSV or XLSX file whose first row is its headings.",
});

function UploadField({ id, label, hint, children }: { readonly id: string; readonly label: string; readonly hint: string; readonly children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      <p id={`${id}-hint`} className="m-0 text-[12px] leading-snug text-dim">
        {hint}
      </p>
      {children}
    </div>
  );
}

/**
 * The upload: a name, a title, the key column's heading and the file, each saying what it takes.
 *
 * Plain inputs rather than `SchemaForm`, because a file is not a JSON value a schema can describe;
 * the bytes are read in the browser and sent as base64, which is the one encoding
 * `brain.classification_routes.TableUpload` takes. A refusal is the API's sentence, and a table
 * that was stored is opened at its own address.
 */
function UploadTable() {
  const navigate = useNavigate();
  const [entity, setEntity] = useState("");
  const [title, setTitle] = useState("");
  const [keyColumn, setKeyColumn] = useState("");
  const [file, setFile] = useState<{ name: string; bytes: Uint8Array } | null>(null);
  const [refused, setRefused] = useState("");
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const [incomplete, setIncomplete] = useState(false);
  const body = uploadBody(title, file?.name ?? "", file?.bytes ?? null, keyColumn);

  async function onChoose(event: ChangeEvent<HTMLInputElement>) {
    const one = event.target.files?.[0];
    if (one === undefined) {
      setFile(null);
      return;
    }
    setFile({ name: one.name, bytes: new Uint8Array(await one.arrayBuffer()) });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (body === null || entity.trim() === "") {
      // Said rather than silently ignored: a form sent with a field missing says what to fill in.
      setIncomplete(true);
      return;
    }
    setIncomplete(false);
    setBusy(true);
    setFailure(null);
    setRefused("");
    const named = entity.trim();
    const result = await request<unknown>(tableApiPath(named), { method: "PUT", body });
    setBusy(false);
    if (!result.ok) {
      setFailure(result.failure);
      return;
    }
    const answer = readUploaded(result.data);
    if (answer.page === null) {
      setRefused(answer.refused);
      return;
    }
    void navigate(classificationAddress(answer.page.entity));
  }

  return (
    <SectionCard title={UPLOAD_HEADING} lede={UPLOAD_LEDE}>
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : (
          <Notice title={IT_WAS_NOT_UPLOADED} traceId={failure.traceId}>
            <p>{failure.message}</p>
          </Notice>
        )}
        {refused === "" ? null : (
          <Notice title={IT_WAS_NOT_UPLOADED}>
            <p>{refused}</p>
          </Notice>
        )}
        {incomplete ? (
          <p className="m-0 text-[12.5px] text-crit" role="alert">
            {AN_UPLOAD_NEEDS}
          </p>
        ) : null}
        <form aria-label={UPLOAD_HEADING} className="[display:grid] min-w-0 grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={(event) => void onSubmit(event)}>
          <UploadField id="classification-entity" label="Table name" hint={UPLOAD_HINTS.entity}>
            <Input id="classification-entity" name="entity" aria-describedby="classification-entity-hint" value={entity} onChange={(event) => setEntity(event.target.value)} />
          </UploadField>
          <UploadField id="classification-title" label="Title" hint={UPLOAD_HINTS.title}>
            <Input id="classification-title" name="title" aria-describedby="classification-title-hint" value={title} onChange={(event) => setTitle(event.target.value)} />
          </UploadField>
          <UploadField id="classification-key" label="Heading a question names a row by" hint={UPLOAD_HINTS.keyColumn}>
            <Input id="classification-key" name="key_column" aria-describedby="classification-key-hint" value={keyColumn} onChange={(event) => setKeyColumn(event.target.value)} />
          </UploadField>
          <UploadField id="classification-file" label="File" hint={UPLOAD_HINTS.file}>
            <Input id="classification-file" type="file" name="filename" accept={TABLE_FILE_ACCEPT} aria-describedby="classification-file-hint" onChange={(event) => void onChoose(event)} />
          </UploadField>
          <div className="sm:col-span-2">
            <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy || body === null || entity.trim() === ""}>
              Upload
            </Button>
          </div>
        </form>
      </div>
    </SectionCard>
  );
}

/** The form that opens a table by its name, which is the only way in: nothing lists them. */
function OpenTable({ title }: { readonly title: string }) {
  const navigate = useNavigate();
  // Memoised on the address rather than rebuilt each render, so the form is not handed a new
  // object while somebody is typing into it.
  const asked = useMemo(() => ({ [ENTITY_FIELD]: "" }), []);
  return (
    <SectionCard title={title}>
      <SchemaForm
        caption="Which table"
        schema={CLASSIFICATION_QUERY_SCHEMA}
        uiSchema={CLASSIFICATION_QUERY_UI}
        formData={asked}
        onSubmit={(submitted) => {
          const named = submittedEntity(submitted);
          if (named === null) {
            // Not a question this screen recognises: an address from a value nobody read.
            return;
          }
          void navigate(classificationAddress(named));
        }}
      />
    </SectionCard>
  );
}

/**
 * One classified table's page, and the editor when a column is open. Keyed by the table in the
 * route, so opening another starts from a fresh request and a fresh editor.
 */
function ClassifiedTable({ entity, openColumn }: { readonly entity: string; readonly openColumn: string | undefined }) {
  // Bumped when a mark is applied, so the grid is read again from the API rather than patched
  // from the apply's answer: the classification on the screen is always one the API sent.
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(classificationApiPath(entity), version);
  const page = useMemo(() => readClassification(answer.data), [answer.data]);
  // Kept with the column it was applied to, so opening another column shows no notice about it.
  const [applied, setApplied] = useState<{ column: string; answer: Applied } | null>(null);
  const reload = useCallback(
    (one: Applied) => {
      setApplied({ column: openColumn ?? "", answer: one });
      if (one.applied) {
        setVersion((current) => current + 1);
      }
    },
    [openColumn],
  );
  const columns = useMemo(
    () => classificationColumns(page.editable, (column) => <Link to={columnAddress(entity, column)}>Edit</Link>),
    [page.editable, entity],
  );
  const open = openColumn === undefined ? null : columnByName(page.columns, openColumn);
  const options = useMemo(() => (open === null ? [] : derivationOptions(page.columns, open.column)), [page.columns, open]);
  const name = page.stored && page.title !== "" ? page.title : entity;

  // The trail is the same with a column open or not, so opening a column the reader may not
  // propose a change to adds nothing to the page at all.
  return (
    <DetailPage
      crumbs={[{ label: CLASSIFICATION_HEADING, to: "/classification" }, { label: name }]}
      header={<DetailHeader name={name} headingId={`classification-${entity}`} pills={<KindPill stored={page.stored} />} />}
    >
      <div className="flex min-w-0 flex-col gap-4">
        <SectionCard title="Columns">
          <DataTable
            caption={`How the columns of ${entity} are classified`}
            columns={columns}
            rows={page.columns}
            rowId={(row) => row.column}
            failure={answer.failure}
            busy={answer.busy}
          />
        </SectionCard>
        {/*
         * The editor appears when a column is open and this caller may have a change reviewed.
         * When they may not, nothing is rendered and nothing is said: a sentence explaining that
         * they cannot would be this console describing a refusal the API never made.
         */}
        {open !== null && page.editable ? (
          <SectionCard title={page.stored ? `The mark for ${open.column}` : `The rule for ${open.column}`}>
            <ColumnEditor entity={entity} row={open} options={options} stored={page.stored} onApplied={reload} />
          </SectionCard>
        ) : null}
        {applied === null || applied.column !== openColumn ? null : <AppliedNotice applied={applied.answer} />}
        {openColumn !== undefined && open === null && !answer.busy && answer.failure === null ? <Note>{NO_SUCH_COLUMN}</Note> : null}
        {page.stored ? (
          <Advanced>
            <FactList>
              <Fact label="Table">
                <code>{entity}</code>
              </Fact>
              <Fact label="Key column">
                <code>{page.keyColumn}</code>
              </Fact>
              <Fact label="Policy epoch">
                <code>{short(page.epoch)}</code>
              </Fact>
            </FactList>
          </Advanced>
        ) : null}
      </div>
    </DetailPage>
  );
}

function KindPill({ stored }: { readonly stored: boolean }) {
  return (
    <span className="inline-block rounded-[2px] bg-sunk px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-body">
      {stored ? "Uploaded table" : "Built in"}
    </span>
  );
}

export function ClassificationPage({ entity, column }: { readonly entity: string | undefined; readonly column: string | undefined }) {
  if (entity !== undefined) {
    return <ClassifiedTable key={entity} entity={entity} openColumn={column} />;
  }
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: CLASSIFICATION_HEADING }]} title={CLASSIFICATION_HEADING} lede={CLASSIFICATION_LEDE} />
      <OpenTable title={OPEN_HEADING} />
      <Note>{NOTHING_ASKED_FOR}</Note>
      {/*
       * The upload sits where a person starts, before any table is named, and not beside one: an
       * upload names its own table, and a form under another table's grid would read as uploading
       * into that one.
       */}
      <UploadTable />
    </div>
  );
}

/**
 * The sentences this page adds to what the API said, exported so a test can assert on them rather
 * than on a copy. None carries a number and none explains a refusal.
 */
export {
  AN_UPLOAD_NEEDS,
  IT_DOES_NOT_WIDEN,
  IT_WAS_APPLIED,
  IT_WAS_NOT_APPLIED,
  IT_WAS_NOT_UPLOADED,
  IT_WIDENS,
  IT_WOULD_NOT_LOAD,
  NOTHING_ASKED_FOR,
  NOTHING_WOULD_CHANGE,
  NO_SUCH_COLUMN,
  REVIEW_BEFORE_APPLYING,
  THERE_IS_NO_SAVE,
  UPLOAD_HEADING,
  UPLOAD_LEDE,
  WHAT_A_WIDENING_MEANS,
  WHAT_THE_EPOCH_IS,
};
