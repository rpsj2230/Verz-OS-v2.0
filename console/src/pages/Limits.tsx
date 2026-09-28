/**
 * Rate limits: the windows requests are counted in, which of them is refusing somebody now, the
 * ceilings of the systems this install reads, and who is asking far more than usual.
 *
 * Four halves that come from different places, and the page keeps them apart because only two of
 * them are narrowed by who is asking. The windows and the ceilings are declarations every reader
 * of this screen sees whole: the windows are built by the functions the answer route calls, so
 * the thirty a minute drawn here is the thirty a person is refused at. The throttling list is
 * `brain.console.installation.throttled_now`'s answer over the windows the answer route writes,
 * at this reader's own scope, and the unusual list is `unusual_now`'s, narrowed the same way.
 *
 * **Neither narrowed list carries a count, and neither does this page.** Their rows are the ones
 * a reader's grant filters, so a number beside either would be the subtraction disclosure with
 * every figure on the page correct. The API sends no total and nothing here computes a length
 * for display. The unusual list carries a band and a sentence and never the figures behind them,
 * because a person's question count beside their name is a report about their day.
 *
 * **A department-scoped reader sees both lists empty, and that is the answer rather than a
 * fault.** `brain.ops.limits.LimitScope` has six members and none of them is a department, so
 * `brain.core.scope.Clause.matches` refuses the field and a grant narrowed to one department
 * matches no row. `brain.console.screens` takes this one screen out of a department admin's menu
 * for the same reason, which is the only entry in `NOT_AT_DEPARTMENT_SCOPE` about an install
 * screen. Nothing on this page detects that state or says anything about it: a sentence reading
 * "you may be seeing fewer rows than exist" would be the console asserting a refusal it did not
 * observe, and would tell a reader there are rows.
 *
 * **An empty list and an absent list are drawn differently, which is the point of the API
 * sending them differently.** An empty list is nobody behind a window, and the page says so. An
 * absent list is nothing on this process having looked, or the store not answering, and the page
 * says that instead, in the API's own sentence. Both draw no rows, so a page that treated them
 * alike would render the second as the first, which is the reassuring direction during an
 * incident.
 *
 * Task ids: M27.7.27, M23.1.1, M23.2.1
 */

import { useResource } from "../api/useResource";
import { Chip } from "../ui/Chip";
import { Notice } from "../ui/Notice";
import {
  CEILING_COLUMNS,
  LIMITS_API_PATH,
  readThrottled,
  readUnusual,
  THROTTLE_COLUMNS,
  UNUSUAL_COLUMNS,
  WINDOW_COLUMNS,
  wasRead,
  type Limits as LimitsBody,
} from "./installQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/** The heading over the state where nothing on this process could read the live windows. */
export const NOTHING_LOOKED = "Nothing here has looked at what is being throttled";

/** The heading over the state where nothing could count who is asking more than usual. */
export const NOTHING_COUNTED = "Nothing here has counted who is asking more than usual";

/**
 * What is said when the list came back and had nothing in it.
 *
 * A sentence rather than a blank, because a table with a caption and no rows reads as a table
 * that has not loaded. It says what is true of the rows this reader may see and does not
 * mention rows, scopes or grants: see the note at the top about what a hint here would disclose.
 */
export const NOBODY_IS_BEHIND_A_CEILING = "Nothing this screen can show is refusing a request.";

/** The same, for the unusual list. */
export const NOBODY_IS_UNUSUAL = "Nobody this screen can show is asking far more than usual.";

/*
 * Every table is a plain one rather than `DataTable`, and the reason is the bundle. The table
 * library is the second heaviest thing in this console and `App.tsx` splits the three routes
 * that mount it precisely so a person who never opens them does not download it. These rows are
 * a handful with no sorting, no paging and no filtering, so mounting the library for them would
 * put it in this route's chunk and buy nothing. `tests/bundle-split.test.ts` walks the static
 * graph from `main.tsx`.
 *
 * Every table is wrapped in `.grid__scroll`, which is not decoration: `.grid__table` sets
 * `overflow-wrap: normal` so a column of identifiers is not split mid-word, and without a
 * scrolling parent the overflow is taken by the document, which takes the navigation off the
 * side of a phone. `tests/phone-width.test.tsx` holds that.
 */

export function Limits() {
  const answer = useResource<LimitsBody>(LIMITS_API_PATH);
  const throttled = readThrottled(answer.data);
  const unusual = readUnusual(answer.data);
  const ceilings = answer.data?.ceilings ?? [];
  const windows = answer.data?.windows ?? [];
  const settled = !answer.busy && !answer.failure && answer.data !== null;

  return (
    <article className="page">
      <h1>Rate limits</h1>
      <p className="lede">
        The windows this install counts requests in, which of them is refusing somebody now, the
        ceilings of the systems it reads, and who is asking far more than usual.
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

      {windows.length > 0 ? (
        <section className="card">
          <h2>Windows</h2>
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">The windows this install counts requests in</caption>
              <thead>
                <tr>
                  {WINDOW_COLUMNS.map((column) => (
                    <th scope="col" key={column}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {windows.map((window) => (
                  <tr key={`${window.scope}:${window.applies_to}:${window.period}`}>
                    {WINDOW_COLUMNS.map((column) => (
                      <td key={column}>{String(window[column])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {settled && !wasRead(throttled) ? (
        <section className="card">
          <Notice title={NOTHING_LOOKED}>
            <p>{throttled.unread}</p>
          </Notice>
        </section>
      ) : null}

      {wasRead(throttled) ? (
        <section className="card">
          <h2>Refusing now</h2>
          {throttled.panel.length === 0 ? (
            <p className="note">{NOBODY_IS_BEHIND_A_CEILING}</p>
          ) : (
            <div className="grid__scroll">
              <table className="grid__table">
                <caption className="grid__caption">What is refusing a request now</caption>
                <thead>
                  <tr>
                    {THROTTLE_COLUMNS.map((column) => (
                      <th scope="col" key={column}>
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {throttled.panel.map((row) => (
                    <tr key={`${row.scope}:${row.subject}`}>
                      {THROTTLE_COLUMNS.map((column) => (
                        <td key={column}>
                          {column === "scope" ? <Chip label={row.scope} /> : String(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}

      {ceilings.length > 0 ? (
        <section className="card">
          <h2>Ceilings</h2>
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">The ceilings this install applies</caption>
              <thead>
                <tr>
                  {CEILING_COLUMNS.map((column) => (
                    <th scope="col" key={column}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ceilings.map((ceiling) => (
                  <tr key={ceiling.name}>
                    {CEILING_COLUMNS.map((column) => (
                      <td key={column}>{String(ceiling[column])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {settled && !wasRead(unusual) && unusual.unread ? (
        <section className="card">
          <Notice title={NOTHING_COUNTED}>
            <p>{unusual.unread}</p>
          </Notice>
        </section>
      ) : null}

      {wasRead(unusual) ? (
        <section className="card">
          <h2>Asking far more than usual</h2>
          {unusual.panel.length === 0 ? (
            <p className="note">{NOBODY_IS_UNUSUAL}</p>
          ) : (
            <div className="grid__scroll">
              <table className="grid__table">
                <caption className="grid__caption">Who is asking far more than usual</caption>
                <thead>
                  <tr>
                    {UNUSUAL_COLUMNS.map((column) => (
                      <th scope="col" key={column}>
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {unusual.panel.map((row) => (
                    <tr key={row.subject}>
                      {UNUSUAL_COLUMNS.map((column) => (
                        <td key={column}>
                          {column === "band" ? <Chip label={row.band} /> : String(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </article>
  );
}
