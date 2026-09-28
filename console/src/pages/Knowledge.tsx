/**
 * Knowledge: every document the system can draw on, in every department this reader reaches,
 * with how widely each one reaches.
 *
 * SCREEN 7 of `docs/screens.html` is the design of record: Govern section, four figures across
 * the top, a coverage card beside a card about what the company view adds over a department's,
 * and the library table. This is that layout in that order, one column on a phone, with each
 * part drawn from what the API sends and each missing fact said in a sentence where the design
 * draws it. `knowledgeQuery.A_COLUMN_NOTHING_SENDS_IS_A_SENTENCE_AND_NEVER_A_BLANK_COLUMN` is the
 * rule.
 *
 * **What is drawn and what is not.** The library table has the design's Item, Type and Visible to
 * columns, which are the three facts `brain.console.govern_estate.library_rows` puts on a row; an
 * item added before kinds were recorded says so in its Type cell rather than drawing it blank. The
 * Items and Company-wide figures are counts of those rows. The coverage card lists the
 * departments the rows may be grouped by when `departments_represented` allows it and says why
 * it does not when it does not. The Fresh and Never retrieved figures, the coverage bars, and the
 * Dept, Type, Owner, Verified, Review due and Used 30d columns are each a sentence, because
 * `brain.estate_routes` says nothing on this install measures them.
 *
 * **Upload is the Add a document card** (M7.6.3). It asks the API what this person may add and
 * where, and draws a form only from that answer: the kinds they may choose, the departments they
 * may add to, whether their own level is offered, and the types and sizes the door takes. A file is
 * judged against those before it is sent, sent raw with its name in a header, and the answer is the
 * API's own sentence, whether it was added or why it was not, parse failures included (M7.2.5).
 * Somebody who may add nothing is told so in one sentence and shown no form.
 *
 * **Two controls from the design are absent and say so.** Export inventory is a write nothing on
 * the server offers, and the Review due chip filters on a date the API does not send. The search, the level filter, the order and "Show more" are requests the route answers over
 * the items this reader may know exist, without narrowing what it loads, so its truncation flag
 * stays a fact about the install rather than a count of what matched.
 *
 * **Nothing here decides who may see anything.** The request is identical for every caller. A
 * failure is the API's own sentence and the trace id, including a 404, which here means the
 * caller may not open this screen and is not explained further.
 *
 * Imported statically rather than split, which is `Roles.tsx`' rule: it mounts neither heavy
 * library and imports no stylesheet of its own.
 *
 * Task ids: M27.7.20, M27.8.6, M7.6.3, M7.6.1, M7.2.5
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { Chip } from "../ui/Chip";
import {
  acceptOf,
  addedSentence,
  atLevel,
  KNOWLEDGE_API_PATH,
  kindWord,
  LIBRARY_FILTERS,
  LIBRARY_SORTS,
  readKnowledgePage,
  readUploaded,
  readUploadOptions,
  typeOf,
  UPLOAD_OPTIONS_API_PATH,
  uploadPath,
  type LibraryRow,
  type Level,
  type UploadLevel,
  type UploadOptions,
} from "./knowledgeQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { KnowledgeIntake } from "./KnowledgeIntake";

/** The design's own label for this screen, which the navigation and this heading share. */
export const KNOWLEDGE_HEADING = "Knowledge";

/** Under the heading. SCREEN 7's own account of what the screen is for, kept in its words. */
export const KNOWLEDGE_LEDE =
  "Everything uploaded by any department becomes company knowledge, but bounded knowledge: each " +
  "item carries the scope it is visible in. A department admin sees only their own rows; a " +
  "reader holding the library for the whole company sees every row, which is the only place " +
  "coverage across departments can be judged.";

/** An empty library, whichever of the reasons it is empty. */
export const NO_ITEMS = "There are no knowledge items to show.";

/** A search or a filter matched nothing the reader may know exists. About the question. */
export const NO_MATCH = NOTHING_MATCHES;

/** A load that came back full. A fact about there being more, and never a figure. */
export const MORE_ITEMS =
  "The library holds more items than one reading covers, so this list, its search and its filter " +
  "cover the first part of it by reference.";

/** What the controls act on. Said once, beside them, so nobody reads a match as more than it is. */
export const NARROWS_THIS_PAGE =
  "Search, filter and order ask for the items you may know exist; Show more asks for the next ones.";

/** What the design's Fresh and Never retrieved figures and the coverage bars become. */
export const NOT_MEASURED =
  "Not measured on this install. How fresh an item is is judged over whole documents, and the " +
  "library record holds no document text; how often an item is retrieved is recorded nowhere.";

/** What is said in place of the Dept, Type, Owner, Verified, Review due and Used 30d columns. */
export const ONLY_EXISTENCE_AND_REACH =
  "This screen shows that an item exists, what kind it is and how widely it reaches, and nothing " +
  "more. The department and the owner are the two halves of an item's visibility rule, which this " +
  "screen does not show on a row; the title and who verified it say more than that an item exists; " +
  "and no retrieval count is recorded. So the design's Dept, Owner, Verified, Review due and Used " +
  "30d columns are not drawn.";

/** What is said in place of the grouping, when this reader may not be shown it. */
export const GROUPING_WITHHELD =
  "Grouping by department is shown to a reader who holds the Scopes and departments screen for " +
  "the whole company, because the list of departments that hold documents is that screen's to " +
  "show.";

/** A grouping that is allowed and holds no department. */
export const NO_DEPARTMENTS = "No item on this page sits in a department.";

/** What is said in place of the Export inventory and Review due controls. */
export const CONTROLS_NOT_OFFERED =
  "There is no Export inventory control: an export is recorded on the Exports screen, and " +
  "nothing here writes that record. There is no Review due filter: the review date is not sent " +
  "to this screen.";

// ------------------------------------------------------------------ adding a document (M7.6.3)

/** The card's heading and its form's accessible name. */
export const ADD_HEADING = "Add a document";

/** Under the heading: what adding does, and what it never does. */
export const ADD_LEDE =
  "A plain text, Markdown, PDF or Word document is read here and answered from straight away. It " +
  "is added to one department or to you only; making it company-wide is a promotion somebody " +
  "approves, and this form never does it.";

/** What somebody who may add nothing is told. About their own reach, and nobody else's. */
export const ADD_NOT_OFFERED = "Adding documents is not offered to you.";

/** A body the console could not read as the options. */
export const ADD_UNREADABLE = "The API did not say what may be added, so no form is drawn.";

/** What the page says while the options are being asked for. */
export const ASKING_WHAT_MAY_BE_ADDED = "Asking what you may add.";

/** What the press says while the file is on its way. */
export const ADDING = "Adding the document.";

export const ADD_LABEL = "Add to knowledge";
export const FILE_LABEL = "Document";
export const KIND_LABEL = "Kind";
export const LEVEL_LABEL = "Visible to";
export const DEPARTMENT_LABEL = "Department";
export const ONE_DEPARTMENT = "One department";
export const ONLY_ME = "You only";

/** Said beside a field left empty, or a file this form can already tell will be refused. */
export const ADD_PROBLEMS = {
  file: "Choose the document to add.",
  type: "Choose a plain text, Markdown, PDF or Word document; this file is none of those.",
  size: "This file is larger than this install accepts for its type.",
  kind: "Choose what kind of document this is.",
  department: "Choose the department it is for.",
} as const;
type AddProblem = keyof typeof ADD_PROBLEMS;

/** The inputs the API may name a problem against, so a refusal is not listed twice. */
const ADD_FIELDS = ["file", "kind", "level", "department"];

export interface AddDraft {
  readonly file: File | null;
  readonly kind: string;
  readonly level: UploadLevel;
  readonly department: string;
}

/** What is wrong with a draft before it is sent, judged against what the API offered. */
export function addProblems(draft: AddDraft, options: UploadOptions): AddProblem[] {
  const found: AddProblem[] = [];
  if (draft.file === null) {
    found.push("file");
  } else {
    const type = typeOf(draft.file.name, options.types);
    if (type === null) {
      found.push("type");
    } else if (draft.file.size > type.maxBytes) {
      found.push("size");
    }
  }
  if (draft.kind === "") {
    found.push("kind");
  }
  if (draft.level === "department" && draft.department === "") {
    found.push("department");
  }
  return found;
}

function AddForm({ options, onAdded }: { readonly options: UploadOptions; readonly onAdded: () => void }) {
  const levels: UploadLevel[] = [
    ...(options.departments.length > 0 ? (["department"] as const) : []),
    ...(options.personal ? (["personal"] as const) : []),
  ];
  const [draft, setDraft] = useState<AddDraft>({
    file: null,
    kind: "",
    level: levels[0] ?? "department",
    department: options.departments.length === 1 ? (options.departments[0] ?? "") : "",
  });
  const [problems, setProblems] = useState<readonly AddProblem[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState("");

  if (levels.length === 0) {
    return <p className="note">{ADD_NOT_OFFERED}</p>;
  }

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = addProblems(draft, options);
    setProblems(found);
    setSaid("");
    const file = draft.file;
    const type = file === null ? null : typeOf(file.name, options.types);
    if (found.length > 0 || file === null || type === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(uploadPath(draft.kind, draft.level, draft.department), {
        method: "POST",
        file: { body: file, type: type.mediaType, name: file.name },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      const added = readUploaded(result.data);
      setSaid(added === null ? "" : addedSentence(added));
      onAdded();
    })();
  };

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} fields={ADD_FIELDS} />}
      {said === "" ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      {busy ? (
        <p className="note" role="status">
          {ADDING}
        </p>
      ) : null}
      <form className="form" aria-label={ADD_HEADING} onSubmit={onSubmit} noValidate>
        <label className="control-label">
          {FILE_LABEL}{" "}
          <input
            className="form-control"
            type="file"
            name="file"
            accept={acceptOf(options.types)}
            onChange={(event) => setDraft({ ...draft, file: event.target.files?.[0] ?? null })}
          />
        </label>
        {(["file", "type", "size"] as const).map((one) =>
          problems.includes(one) ? (
            <p key={one} className="note">
              {ADD_PROBLEMS[one]}
            </p>
          ) : null,
        )}
        <label className="control-label">
          {KIND_LABEL}{" "}
          <select
            className="form-control"
            name="kind"
            value={draft.kind}
            onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
          >
            <option value="">Choose one</option>
            {options.kinds.map((one) => (
              <option key={one.value} value={one.value}>
                {one.label}
              </option>
            ))}
          </select>
        </label>
        {problems.includes("kind") ? <p className="note">{ADD_PROBLEMS.kind}</p> : null}
        <label className="control-label">
          {LEVEL_LABEL}{" "}
          <select
            className="form-control"
            name="level"
            value={draft.level}
            onChange={(event) =>
              setDraft({ ...draft, level: event.target.value === "personal" ? "personal" : "department" })
            }
          >
            {levels.map((one) => (
              <option key={one} value={one}>
                {one === "department" ? ONE_DEPARTMENT : ONLY_ME}
              </option>
            ))}
          </select>
        </label>
        {draft.level === "department" ? (
          <label className="control-label">
            {DEPARTMENT_LABEL}{" "}
            <select
              className="form-control"
              name="department"
              value={draft.department}
              onChange={(event) => setDraft({ ...draft, department: event.target.value })}
            >
              <option value="">Choose one</option>
              {options.departments.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {problems.includes("department") ? <p className="note">{ADD_PROBLEMS.department}</p> : null}
        <p className="note">
          Found by {options.foundBy}. Checked before it is read by the {options.checkedBy}.
        </p>
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {ADD_LABEL}
          </button>
        </div>
      </form>
    </>
  );
}

function AddDocument({ onAdded }: { readonly onAdded: () => void }) {
  const offered = useResource<unknown>(UPLOAD_OPTIONS_API_PATH);
  let inside;
  if (offered.busy) {
    inside = (
      <p className="note" role="status">
        {ASKING_WHAT_MAY_BE_ADDED}
      </p>
    );
  } else if (offered.failure !== null) {
    // A 404 is the answer for somebody who may add nothing, and it is theirs to be told plainly;
    // a session missing a second factor is told so by the notice, which offers the way out.
    inside =
      offered.failure.status === 404 && !offered.failure.secondFactorNeeded ? (
        <p className="note">{ADD_NOT_OFFERED}</p>
      ) : (
        <FailureNotice failure={offered.failure} />
      );
  } else {
    const options = readUploadOptions(offered.data);
    inside =
      options === null ? <p className="note">{ADD_UNREADABLE}</p> : <AddForm options={options} onAdded={onAdded} />;
  }
  return (
    <section className="card">
      <h2>{ADD_HEADING}</h2>
      <p className="note">{ADD_LEDE}</p>
      {inside}
    </section>
  );
}

/** What the company view adds over a department's, as the design lists it, in true sentences. */
export const DEPARTMENT_ADMIN_SEES = "Only the items in their own scope.";
export const PROMOTION_NOT_HERE =
  "Not offered here. Promoting an item to the whole company is a change a person decides, and " +
  "this screen records no decision.";
export const CONTENTS_NOT_OPENED =
  "Not opened from this screen. It says an item exists and how widely it reaches, never what " +
  "the item says.";
export const DUPLICATES_NOT_COUNTED = "Not counted here.";

/** The design's word for each level, so the table and the filter use one vocabulary. */
export const LEVEL_WORDS: Readonly<Record<Level, string>> = {
  company: "company",
  department: "department",
  personal: "personal",
};

/** The accessible names of the lists and the table. */
export const DEPARTMENTS_LABEL = "Departments with items you may know exist";
export const LIBRARY_CAPTION = "Items you may know exist";

function Figures({
  shown,
  companyWide,
  departments,
}: {
  readonly shown: number;
  readonly companyWide: number;
  readonly departments: readonly string[] | null;
}) {
  return (
    <section className="card">
      <h2>At a glance</h2>
      <dl className="fields" aria-label="Knowledge at a glance">
        <div className="fields__row">
          <dt>Items listed</dt>
          <dd>
            <span>{String(shown)}</span>
            <p className="note">
              {departments === null
                ? "items listed below"
                : `items listed below, from ${String(departments.length)} departments you can see`}
            </p>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Fresh</dt>
          <dd>
            <p className="note">{NOT_MEASURED}</p>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Never retrieved</dt>
          <dd>
            <p className="note">{NOT_MEASURED}</p>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Company-wide</dt>
          <dd>
            <span>{String(companyWide)}</span>
            <p className="note">listed below and visible to everyone</p>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function KnowledgeAnswerView({ version }: { readonly version: number }) {
  const listing = useListing<LibraryRow>(KNOWLEDGE_API_PATH, { choices: LIBRARY_FILTERS, version });

  if (listing.body === null) {
    if (listing.failure) {
      return <FailureNotice failure={listing.failure} />;
    }
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const page = readKnowledgePage(listing.body);
  const rows = page.items;
  const choices = LIBRARY_FILTERS.map((choice) =>
    choice.describe === undefined
      ? { ...choice, describe: (value: string) => LEVEL_WORDS[value as Level] ?? value }
      : choice,
  );

  return (
    <>
      {page.staleness === null ? null : <p className="note">{page.staleness}</p>}

      <Figures
        shown={page.items.length}
        companyWide={atLevel(page.items, "company")}
        departments={page.departments}
      />

      <section className="card">
        <h2>Coverage by department</h2>
        {page.departments === null ? (
          <p className="note">{GROUPING_WITHHELD}</p>
        ) : page.departments.length === 0 ? (
          <p className="note">{NO_DEPARTMENTS}</p>
        ) : (
          <ul aria-label={DEPARTMENTS_LABEL}>
            {page.departments.map((name) => (
              <li key={name}>
                <Chip label={name} />
              </li>
            ))}
          </ul>
        )}
        {page.freshnessAndUseAreNotMeasured ? <p className="note">{NOT_MEASURED}</p> : null}
      </section>

      <section className="card">
        <h2>What the company view adds over a department view</h2>
        <dl className="fields" aria-label="What the company view adds">
          <div className="fields__row">
            <dt>Grouped by department</dt>
            <dd>
              {page.departments === null ? (
                <p className="note">{GROUPING_WITHHELD}</p>
              ) : (
                <span>Yes</span>
              )}
            </dd>
          </div>
          <div className="fields__row">
            <dt>A department admin sees</dt>
            <dd>
              <span>{DEPARTMENT_ADMIN_SEES}</span>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Cross-department duplicates</dt>
            <dd>
              <span>{DUPLICATES_NOT_COUNTED}</span>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Promote to company-wide</dt>
            <dd>
              <p className="note">{PROMOTION_NOT_HERE}</p>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Contents read by an administrator</dt>
            <dd>
              <p className="note">{CONTENTS_NOT_OPENED}</p>
            </dd>
          </div>
        </dl>
      </section>

      <section className="card">
        <h2>Library</h2>
        {page.onlyExistenceAndReachAreShown ? (
          <p className="note">{ONLY_EXISTENCE_AND_REACH}</p>
        ) : null}

        <p className="note">{NARROWS_THIS_PAGE}</p>
        <ListControls label="Find an item" listing={listing} choices={choices} sorts={LIBRARY_SORTS} />

        {listing.failure ? (
          <FailureNotice failure={listing.failure} />
        ) : listing.busy ? (
          <p className="note" role="status">
            Loading.
          </p>
        ) : rows.length === 0 ? (
          <p className="note">{narrows(listing.question) ? NO_MATCH : NO_ITEMS}</p>
        ) : (
          <>
            {/*
             * `.grid__scroll`, for `Connectors.tsx`' reason: an item reference is an identifier
             * with no break in it, and without a scrolling parent it takes a phone's page wide.
             */}
            <div className="grid__scroll">
              <table className="grid__table">
                <caption className="grid__caption">{LIBRARY_CAPTION}</caption>
                <thead>
                  <tr>
                    <th scope="col">Item</th>
                    <th scope="col">Type</th>
                    <th scope="col">Visible to</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.item_id}>
                      <td>
                        <code>{row.item_id}</code>
                      </td>
                      <td>{kindWord(row.kind)}</td>
                      <td>
                        <code>{LEVEL_WORDS[row.level as Level]}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ShowMore listing={listing} />
          </>
        )}

        {page.truncated ? <p className="note">{MORE_ITEMS}</p> : null}
        <p className="note">{CONTROLS_NOT_OFFERED}</p>
      </section>
    </>
  );
}

export function Knowledge() {
  // Moved after a document is added, so the library asks again and shows it.
  const [version, setVersion] = useState(0);
  return (
    <article className="page">
      <h1>{KNOWLEDGE_HEADING}</h1>
      <p className="lede">{KNOWLEDGE_LEDE}</p>
      <AddDocument onAdded={() => setVersion((was) => was + 1)} />
      <KnowledgeIntake onAdded={() => setVersion((was) => was + 1)} />
      <KnowledgeAnswerView version={version} />
    </article>
  );
}
