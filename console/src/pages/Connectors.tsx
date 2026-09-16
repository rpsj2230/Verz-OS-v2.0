/**
 * Connectors: every source this install reads, what each is trusted to read, and what
 * connecting one involves.
 *
 * `docs/screens.html` SCREEN 9 is the design of record and this is it as far as the data allows.
 * The table is the design's table in the design's column order. The two cards under it are the
 * design's two cards: one is the copy policy, served whole by the API, and the other is what has
 * to happen for a source to be connected, which stands where the design's per-source explanation
 * and its "Add connector" action are.
 *
 * **Three things the design asks for are not on this screen and the screen says so rather than
 * drawing them from nothing.** There is no bar of today's calls against each ceiling, because
 * nothing on the server can count today's calls. There is no last-read time, because nothing
 * records one and the probe's time is a different fact under a different heading. There is no
 * "Add connector" control, because nothing in this system writes a credential into the vault at
 * runtime and a control that refuses reads as a permission problem with whoever pressed it.
 *
 * **No credential field anywhere on this page.** Not disabled, not hidden: absent. The screen
 * tells whoever holds the authority to install what to do at the server instead, in the API's
 * own sentence. See `connectorsQuery.ts`' `NOTHING_HERE_ASKS_FOR_A_CREDENTIAL`.
 *
 * **An empty table and an absent one are drawn differently**, which is the point of the API
 * sending them differently. An empty table is a reader who may be told of no source. An absent
 * one is nothing on the server having looked, and it is drawn as a notice in the API's own
 * words, because an empty table here reads as a system that reads no outside data.
 *
 * A failure is the API's own sentence and the trace id. Including a 404, which here means the
 * caller may not read this screen: saying so would be the console explaining a refusal it did
 * not observe and cannot tell apart from an absence.
 *
 * Task ids: M42.6.5
 */

import { useResource } from "../api/useResource";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import { Status } from "../ui/Status";
import {
  CONNECTORS_API_PATH,
  CONNECTORS_LABEL,
  readConnectors,
  stateOf,
  TRUST_COLUMNS,
  TRUST_DETAIL,
  wasRead,
  type Connectors as ConnectorsBody,
  type Trust,
} from "./connectorsQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/** The heading over the state where nothing on the server holds a record of what is installed. */
export const NOTHING_LOOKED = "Nothing here knows which sources are installed";

/** The copy policy card's heading, in `docs/screens.html` SCREEN 9's own words. */
export const WHAT_WE_COPY = "What we copy, and what we never copy";

/** The heading over what has to happen for a source to be connected. */
export const CONNECTING_A_SOURCE = "Connecting a source";

/**
 * What is said when the list came back and had nothing in it.
 *
 * A sentence rather than a blank, because a table with a caption and no rows reads as a table
 * that has not loaded. It says what is true of the rows this reader may see and mentions no
 * rows, scopes or grants: a hint that there might be more would tell them there are.
 */
export const NO_SOURCE_TO_SHOW = "There is no source this screen can show you.";

/** One cell, with the two columns that are not plain text drawn as themselves. */
function cell(row: Trust, field: keyof Trust) {
  if (field === "health") {
    return <Status state={stateOf(row)} />;
  }
  if (field === "wiring") {
    return <Chip label={row.wiring} />;
  }
  if (field === "projected_fields") {
    // The design's own wording, "9 fields". A bare figure in a column beside rates and times
    // reads as a count of something else.
    return `${row.projected_fields} fields`;
  }
  const value = row[field];
  return value === null ? "" : String(value);
}

export function Connectors() {
  const answer = useResource<ConnectorsBody>(CONNECTORS_API_PATH);
  const list = readConnectors(answer.data);
  const policy = answer.data?.copy_policy ?? [];

  return (
    <article className="page">
      <h1>{CONNECTORS_LABEL}</h1>
      <p className="lede">
        Every outside system this install reads, what each one was connected to, and what it is
        allowed to do there.
      </p>

      {answer.failure ? (
        <section className="card">
          <FailureNotice failure={answer.failure} />
        </section>
      ) : null}

      {answer.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : null}

      {!answer.busy && !answer.failure && !wasRead(list) ? (
        <section className="card">
          <Notice title={NOTHING_LOOKED}>
            <p>{list.unread}</p>
          </Notice>
        </section>
      ) : null}

      {wasRead(list) ? (
        <section className="card">
          <h2>Sources</h2>
          {list.rows.length === 0 ? (
            <p className="note">{NO_SOURCE_TO_SHOW}</p>
          ) : (
            <>
              {/*
               * A plain table rather than `DataTable`, for `Limits.tsx`' reason: the table
               * library is the second heaviest thing in this console and `App.tsx` splits the
               * routes that mount it. These rows are a handful of sources with no sorting, no
               * paging and no filtering.
               *
               * Wrapped in `.grid__scroll`, which is not decoration: `.grid__table` sets
               * `overflow-wrap: normal` so a column of identifiers is not split mid-word, and
               * without a scrolling parent the overflow is taken by the document, which takes
               * the navigation off the side of a phone.
               */}
              <div className="grid__scroll">
                <table className="grid__table">
                  <caption className="grid__caption">
                    Every source this screen can show you
                  </caption>
                  <thead>
                    <tr>
                      {TRUST_COLUMNS.map((column) => (
                        <th scope="col" key={column.field}>
                          {column.header}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {list.rows.map((row) => (
                      <tr key={row.name}>
                        {TRUST_COLUMNS.map((column) => (
                          <td key={column.field}>{cell(row, column.field)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="note">{answer.data?.budget_unread}</p>
            </>
          )}
        </section>
      ) : null}

      {/*
       * What each source is trusted to read, as sentences under its own heading rather than as
       * more columns. They are paragraphs and a table of paragraphs is unreadable at any width;
       * they are also the part of this screen somebody reads once, carefully, before deciding
       * whether a source is safe to leave connected.
       */}
      {wasRead(list)
        ? list.rows.map((row) => (
            <section className="card" key={`trust-${row.name}`}>
              <h2>{row.name}</h2>
              <dl className="fields" aria-label={`What ${row.name} is trusted to read`}>
                {TRUST_DETAIL.map((one) => (
                  <div className="fields__row" key={one.field}>
                    <dt>{one.label}</dt>
                    <dd>
                      <span>{String(row[one.field])}</span>
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))
        : null}

      {policy.length > 0 ? (
        <section className="card">
          <h2>{WHAT_WE_COPY}</h2>
          <dl className="fields" aria-label={WHAT_WE_COPY}>
            {policy.map((line) => (
              <div className="fields__row" key={line.what}>
                <dt>{line.what}</dt>
                <dd>
                  <Chip label={line.verdict} />
                  <p className="note">{line.why}</p>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {answer.data ? (
        <section className="card">
          <h2>{CONNECTING_A_SOURCE}</h2>
          {/*
           * No form and no button. The sentence is the API's, and it is shown to everybody who
           * may open this screen rather than only to whoever holds the authority to install:
           * somebody who cannot do it still has to know what to ask for.
           */}
          <p>{answer.data.connecting}</p>
          {answer.data.may_connect ? (
            <p className="note">
              You hold the authority to install a connector on this system. That is done at the
              server; there is nothing on this page that can do it.
            </p>
          ) : null}
        </section>
      ) : null}
    </article>
  );
}
