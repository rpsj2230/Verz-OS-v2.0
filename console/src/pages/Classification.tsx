/**
 * One table's column classification, the editor for one column of it, and the upload that
 * makes a price list a classified table.
 *
 * `brain.knowledge.columns` says why this screen exists: "A price list carries the sell
 * price everybody needs beside the cost and margin almost nobody may see, and the obvious
 * move is to restrict the document and keep a second, safer copy for the rest of the
 * company. Within a year there are three near-identical price lists and two of them are
 * stale." The rules that avoid that were legible only to whoever had the source tree open,
 * which is the population that already knows them.
 *
 * **This is an administrative screen and it is the one place in this console where a
 * mistake widens what other people may see.** Everything it can do is guarded by
 * `admin:field_classification`, which `gate.admission.CHANNEL_VERBS` withholds from a
 * service-account token and `ASSURANCE_VERBS` withholds from a one-factor session. Nothing
 * here checks either. The API does, on every request, and this file draws or does not draw a
 * control according to a flag on the response. See
 * `AN_EDITOR_DRAWN_OR_HIDDEN_ASKS_THE_SAME_QUESTION`.
 *
 * **A built-in classification saves nothing, and it says so on the screen rather than in a
 * comment.** The shipped price list is a constant compiled into the API's process, so
 * applying a change to it is a source edit and a deploy, and `THERE_IS_NO_SAVE` is rendered
 * wherever a person could otherwise conclude there was one.
 *
 * **An uploaded table is marked and applied (M7.5.3, M7.7.3).** An administrator uploads a
 * CSV or an XLSX price list under a name, it becomes a classified table, and each column is
 * marked open, restricted or derived. A mark is reviewed first and the review's verdict is
 * shown; only then is it applied, as its own request, and the answer says it was applied and
 * shows the policy epoch before and after. See `A_MARK_IS_APPLIED_AND_LEDGERED`.
 *
 * **The judgement about a change comes back from the API and is never made here.** Which
 * columns a rule affects, whether the change widens, and which other columns a caller short
 * of one column would newly reach are all answered by
 * `POST /api/v1/classifications/{entity}/columns/{column}/review`, which runs the same
 * closure that withholds a column at request time. A copy of that arithmetic in a browser
 * would be a second answer to what a person may see. See
 * `A_WIDENING_IS_NAMED_BY_THE_API_AND_NEVER_WORKED_OUT_HERE`.
 *
 * **A widening is named, never counted, and never softened.** When the API says a proposal
 * widens, this screen lists the columns it said would be exposed, in the API's own words,
 * under a sentence saying what that means. The exposed columns are named because naming is
 * what the reader has to act on; nothing anywhere on this screen is counted, which is the
 * rule `paging.ts` states as `A_PAGE_NEVER_CARRIES_A_COUNT` and this file keeps for
 * everything outside the table.
 *
 * **The address is the whole of the state.** `/classification` is the form,
 * `/classification/{entity}` is one classification, and `/classification/{entity}/{column}`
 * is that classification with one column's editor open, so a person can send a colleague the
 * exact rule they are arguing about. Holding either in component state would make the screen
 * unlinkable and would put the back button somewhere it does not belong.
 *
 * **This console does not know which entities are classified and does not ask.** There is no
 * route that lists them and there must not be one, so somebody types a name. See
 * `THE_CONSOLE_DOES_NOT_KNOW_WHAT_IS_CLASSIFIED`; it is the records screen's rule, one level
 * up, and the cost is the same: a person has to know the name.
 *
 * **The form library is the records screen's, so this route is code-split too.**
 * `@rjsf/core` with the ajv validator is the largest thing in this console by a wide margin,
 * and a third eager import of it would put it back in the entry chunk for everybody. Its
 * ajv validator also needs `unsafe-eval`, which `SchemaForm` records as a live conflict with
 * the proposed Content-Security-Policy; that is unresolved and is not resolved here.
 *
 * Task ids: M7.5.3, M7.7.3
 */

import { useCallback, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { DataTable } from "../components/DataTable";
import { SchemaForm } from "../components/SchemaForm";
import { Notice } from "../ui/Notice";
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
} from "./classificationQuery";

/**
 * What is shown when no entity has been named.
 *
 * It names no entity, for the reason `Records.tsx` gives about its own: "try price_list"
 * would be this console publishing a guess at what the company keeps, to everybody who can
 * open the page, before anybody asked the API anything.
 */
const NOTHING_ASKED_FOR = "Name a document above to see how its columns are classified.";

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
    <section className="card">
      <SchemaForm
        caption={stored ? `The mark for ${row.column}` : `The rule for ${row.column}`}
        schema={schema}
        uiSchema={stored ? COLUMN_MARK_UI : COLUMN_EDIT_UI}
        formData={defaults}
        failure={failure}
        busy={busy}
        onSubmit={ask}
      />
      <p className="note">{stored ? REVIEW_BEFORE_APPLYING : THERE_IS_NO_SAVE}</p>
      {reviewed === null ? null : <ReviewNotice review={reviewed.review} applying={stored} />}
      {reviewed !== null && reviewed.mark !== null && reviewed.review.wouldNotLoad === "" ? (
        <div className="form-actions">
          <button type="button" className="button" disabled={busy} onClick={apply}>
            Apply this mark
          </button>
        </div>
      ) : null}
    </section>
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

/**
 * The upload: a name, a title, the key column's heading and the file.
 *
 * Plain inputs rather than `SchemaForm`, because a file is not a JSON value a schema can
 * describe; the bytes are read in the browser and sent as base64, which is the one encoding
 * `brain.classification_routes.TableUpload` takes. A refusal is the API's sentence, shown as
 * it arrived, and a table that was stored is opened at its own address.
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
      // Said rather than silently ignored: a form sent with a field missing tells the person
      // what to fill in, before anything reaches the API.
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
    <section className="card" aria-labelledby="classification-upload">
      <h2 id="classification-upload">{UPLOAD_HEADING}</h2>
      <p className="note">{UPLOAD_LEDE}</p>
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
        <p className="note" role="alert">
          {AN_UPLOAD_NEEDS}
        </p>
      ) : null}
      <form className="form" aria-label={UPLOAD_HEADING} onSubmit={(event) => void onSubmit(event)}>
        <label className="control-label" htmlFor="classification-entity">
          Table name
        </label>
        <input
          id="classification-entity"
          className="form-control"
          name="entity"
          value={entity}
          onChange={(event) => setEntity(event.target.value)}
        />
        <label className="control-label" htmlFor="classification-title">
          Title
        </label>
        <input
          id="classification-title"
          className="form-control"
          name="title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <label className="control-label" htmlFor="classification-key">
          Heading a question names a row by
        </label>
        <input
          id="classification-key"
          className="form-control"
          name="key_column"
          value={keyColumn}
          onChange={(event) => setKeyColumn(event.target.value)}
        />
        <label className="control-label" htmlFor="classification-file">
          File
        </label>
        <input
          id="classification-file"
          className="form-control"
          type="file"
          name="filename"
          accept={TABLE_FILE_ACCEPT}
          onChange={(event) => void onChoose(event)}
        />
        <div className="form-actions">
          <button
            type="submit"
            className="button"
            disabled={busy || body === null || entity.trim() === ""}
          >
            Upload
          </button>
        </div>
      </form>
    </section>
  );
}

/**
 * One classification, and the editor when a column is open.
 *
 * A separate component because a hook cannot be called conditionally and there is no request
 * to make until an entity has been named. Merging the two would mean asking the API for the
 * classification of the empty string every time somebody opened the screen.
 */
function ClassifiedColumns({
  entity,
  openColumn,
}: {
  readonly entity: string;
  readonly openColumn: string | undefined;
}) {
  // Bumped when a mark is applied, so the grid is read again from the API rather than patched
  // from the apply's answer: the classification on the screen is always one the API sent.
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(classificationApiPath(entity), version);
  const page = useMemo(() => readClassification(answer.data), [answer.data]);
  // Kept with the column it was applied to, so opening another column does not show a notice
  // about the one before.
  const [applied, setApplied] = useState<{ column: string; answer: Applied } | null>(null);
  const reload = useCallback(
    (answer: Applied) => {
      setApplied({ column: openColumn ?? "", answer });
      if (answer.applied) {
        setVersion((current) => current + 1);
      }
    },
    [openColumn],
  );

  const columns = useMemo(
    () =>
      classificationColumns(page.editable, (column) => (
        <Link to={columnAddress(entity, column)}>Edit</Link>
      )),
    [page.editable, entity],
  );

  const open = openColumn === undefined ? null : columnByName(page.columns, openColumn);
  const options = useMemo(
    () => (open === null ? [] : derivationOptions(page.columns, open.column)),
    [page.columns, open],
  );

  return (
    <>
      <DataTable
        caption={`How the columns of ${entity} are classified`}
        columns={columns}
        rows={page.columns}
        rowId={(row) => row.column}
        failure={answer.failure}
        busy={answer.busy}
      />

      {/*
       * The editor appears when a column is open and this caller may have a change
       * reviewed. When they may not, nothing is rendered and nothing is said: a sentence
       * explaining that they cannot would be this console describing a refusal the API never
       * made, and the API's refusal, when a review is attempted, is the same one it gives
       * somebody who cannot read the classification at all.
       */}
      {page.stored ? (
        <p className="note">
          {page.title} Key column <code>{page.keyColumn}</code>. Policy epoch{" "}
          <code>{short(page.epoch)}</code>.
        </p>
      ) : null}

      {open !== null && page.editable ? (
        <ColumnEditor
          entity={entity}
          row={open}
          options={options}
          stored={page.stored}
          onApplied={reload}
        />
      ) : null}
      {applied === null || applied.column !== openColumn ? null : (
        <AppliedNotice applied={applied.answer} />
      )}

      {openColumn !== undefined && open === null && !answer.busy && answer.failure === null ? (
        <p className="note">{NO_SUCH_COLUMN}</p>
      ) : null}
    </>
  );
}

export function Classification() {
  const { entity, column } = useParams();
  const navigate = useNavigate();

  // Memoised on the address rather than rebuilt each render, so the form is not handed a new
  // object while somebody is typing into it.
  const asked = useMemo(() => ({ [ENTITY_FIELD]: entity ?? "" }), [entity]);

  return (
    <article className="page">
      <h1>Classification</h1>
      <p className="lede">
        Which columns of a document are confidential, what it takes to see each, and which
        ones can be worked out from the others.
      </p>

      <section className="card">
        <SchemaForm
          caption="Which document"
          schema={CLASSIFICATION_QUERY_SCHEMA}
          uiSchema={CLASSIFICATION_QUERY_UI}
          formData={asked}
          onSubmit={(submitted) => {
            const named = submittedEntity(submitted);
            if (named === null) {
              // Not a question this screen recognises. An address assembled out of a value
              // nobody read is a request nobody meant to make.
              return;
            }
            void navigate(classificationAddress(named));
          }}
        />
      </section>

      {entity === undefined ? (
        <>
          <p className="note">{NOTHING_ASKED_FOR}</p>
          {/*
           * The upload sits where a person starts, before any table is named, and not beside
           * one: an upload names its own table, and a form under another table's grid would
           * read as uploading into that one.
           */}
          <UploadTable />
        </>
      ) : (
        // Keyed by the entity, so opening a different document starts from a fresh request
        // and a fresh editor rather than showing the previous classification's columns while
        // the new answer is in flight.
        <ClassifiedColumns key={entity} entity={entity} openColumn={column} />
      )}
    </article>
  );
}

/**
 * The sentences this page adds to what the API said, exported so a test can assert on them
 * rather than on a copy. None carries a number and none explains a refusal.
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
