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
 * **What is drawn and what is not.** The library table has the design's Item and Visible to
 * columns, which are the two facts `brain.console.govern_estate.library_rows` puts on a row. The
 * Items and Company-wide figures are counts of those rows. The coverage card lists the
 * departments the rows may be grouped by when `departments_represented` allows it and says why
 * it does not when it does not. The Fresh and Never retrieved figures, the coverage bars, and the
 * Dept, Type, Owner, Verified, Review due and Used 30d columns are each a sentence, because
 * `brain.estate_routes` says nothing on this install measures them.
 *
 * **Three controls from the design are absent and say so.** Upload and Export inventory are
 * writes nothing on the server offers, and the Review due chip filters on a date the API does not
 * send. The search, the level filter and the sort narrow the rows this page already holds, which
 * the page says beside them, because the route declares no filter a server could apply without
 * its truncation flag becoming a count.
 *
 * **Nothing here decides who may see anything.** The request is identical for every caller. A
 * failure is the API's own sentence and the trace id, including a 404, which here means the
 * caller may not open this screen and is not explained further.
 *
 * Imported statically rather than split, which is `Roles.tsx`' rule: it mounts neither heavy
 * library and imports no stylesheet of its own.
 *
 * Task ids: M27.7.20
 */

import { useState } from "react";
import { useResource } from "../api/useResource";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import {
  EVERY_ROW,
  LEVELS,
  atLevel,
  knowledgeApiPath,
  narrowed,
  readKnowledgePage,
  type Level,
  type LibraryView,
} from "./knowledgeQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

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

/** The page holds rows and none of them matches the view. Says nothing about rows not held. */
export const NO_MATCH = "No item on this page matches.";

/** A load that came back full. A fact about there being more, and never a figure. */
export const MORE_ITEMS =
  "This page came back full, so there are more items than it holds, and the search and filters " +
  "below narrow only the items it holds.";

/** What the controls act on. Said once, beside them, so nobody reads a match as a search. */
export const NARROWS_THIS_PAGE = "Search, filter and sort work on the items this page holds.";

/** What the design's Fresh and Never retrieved figures and the coverage bars become. */
export const NOT_MEASURED =
  "Not measured on this install. How fresh an item is is judged over whole documents, and the " +
  "library record holds no document text; how often an item is retrieved is recorded nowhere.";

/** What is said in place of the Dept, Type, Owner, Verified, Review due and Used 30d columns. */
export const ONLY_EXISTENCE_AND_REACH =
  "This screen shows that an item exists and how widely it reaches, and nothing more. The " +
  "department and the owner are the two halves of an item's visibility rule, which this screen " +
  "does not show on a row; the title and who verified it say more than that an item exists; and " +
  "no document type or retrieval count is recorded. So the design's Dept, Type, Owner, Verified, " +
  "Review due and Used 30d columns are not drawn.";

/** What is said in place of the grouping, when this reader may not be shown it. */
export const GROUPING_WITHHELD =
  "Grouping by department is shown to a reader who holds the Scopes and departments screen for " +
  "the whole company, because the list of departments that hold documents is that screen's to " +
  "show.";

/** A grouping that is allowed and holds no department. */
export const NO_DEPARTMENTS = "No item on this page sits in a department.";

/** What is said in place of the Upload, Export inventory and Review due controls. */
export const CONTROLS_NOT_OFFERED =
  "There is no Upload control: nothing on this install accepts a document from the console yet. " +
  "There is no Export inventory control: an export is recorded on the Exports screen, and " +
  "nothing here writes that record. There is no Review due filter: the review date is not sent " +
  "to this screen.";

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
export const DEPARTMENTS_LABEL = "Departments with items on this page";
export const LIBRARY_CAPTION = "Items this page holds";

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
          <dt>Items</dt>
          <dd>
            <span>{String(shown)}</span>
            <p className="note">
              {departments === null
                ? "items you can see"
                : `items you can see, across ${String(departments.length)} departments`}
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
            <p className="note">visible to everyone</p>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function KnowledgeAnswerView() {
  const answer = useResource<unknown>(knowledgeApiPath());
  const [view, setView] = useState<LibraryView>(EVERY_ROW);

  if (answer.failure) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
        <p>{answer.failure.message}</p>
      </Notice>
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const page = readKnowledgePage(answer.data);
  const rows = narrowed(page.items, view);

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

        {page.items.length === 0 ? (
          <p className="note">{NO_ITEMS}</p>
        ) : (
          <>
            <div className="form">
              <p className="note">{NARROWS_THIS_PAGE}</p>
              <label className="control-label" htmlFor="knowledge-search">
                Find an item by its reference
              </label>
              <input
                id="knowledge-search"
                className="form-control"
                type="search"
                value={view.search}
                onChange={(event) => {
                  setView({ ...view, search: event.target.value });
                }}
              />
              <label className="control-label" htmlFor="knowledge-level">
                Visible to
              </label>
              <select
                id="knowledge-level"
                className="form-control"
                value={view.level}
                onChange={(event) => {
                  setView({ ...view, level: event.target.value as Level | "" });
                }}
              >
                <option value="">Every level</option>
                {LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {LEVEL_WORDS[level]}
                  </option>
                ))}
              </select>
              <label className="control-label" htmlFor="knowledge-sort">
                Order
              </label>
              <select
                id="knowledge-sort"
                className="form-control"
                value={view.sort}
                onChange={(event) => {
                  setView({ ...view, sort: event.target.value === "level" ? "level" : "item" });
                }}
              >
                <option value="item">By reference</option>
                <option value="level">Widest first</option>
              </select>
            </div>

            {rows.length === 0 ? (
              <p className="note">{NO_MATCH}</p>
            ) : (
              // `.grid__scroll`, for `Connectors.tsx`' reason: an item reference is an identifier
              // with no break in it, and without a scrolling parent it takes a phone's page wide.
              <div className="grid__scroll">
                <table className="grid__table">
                  <caption className="grid__caption">{LIBRARY_CAPTION}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Item</th>
                      <th scope="col">Visible to</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.item_id}>
                        <td>
                          <code>{row.item_id}</code>
                        </td>
                        <td>
                          <code>{LEVEL_WORDS[row.level as Level]}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {page.truncated ? <p className="note">{MORE_ITEMS}</p> : null}
        <p className="note">{CONTROLS_NOT_OFFERED}</p>
      </section>
    </>
  );
}

export function Knowledge() {
  return (
    <article className="page">
      <h1>{KNOWLEDGE_HEADING}</h1>
      <p className="lede">{KNOWLEDGE_LEDE}</p>
      <KnowledgeAnswerView />
    </article>
  );
}
