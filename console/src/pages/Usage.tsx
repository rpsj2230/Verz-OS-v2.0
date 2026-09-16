/**
 * Usage and cost: how many questions were asked, by department and by person, the tokens their
 * model calls consumed by every axis the reader may have, and where the cost of them is shown.
 *
 * `docs/screens.html` names this screen under Report on the company overview, as "Usage & cost",
 * and on the department console as "Usage". It draws no mockup of the screen itself, so the
 * layout is the design's report shape: a period filter in the top bar as the overview draws one,
 * the figures across the top as its figure row, then one card per breakdown. What each part shows
 * is decided by `brain.console.usage_screen`, and `usageQuery.ts` says how much of the design an
 * install can support.
 *
 * **What is drawn and what is not.** Questions by department with the people who asked, and
 * questions by person, are drawn. Tokens are one table per breakdown the API sends, by person,
 * department, model or agent, each with a totals row that is the API's and never a sum made here,
 * and the at-a-glance figure is the first breakdown's totals, because every breakdown groups one
 * row set and a sum across them would count each token once per axis. A measure the API still
 * names as not measured is a sentence instead. Cost is a link to the Spend screen, which already
 * draws it from the same grant. The overview's count of automated questions is not drawn, because
 * it is a count of what was excluded; the page says automation is not counted instead.
 *
 * **The person table is searched, ordered and paged in the browser**, over every line the API
 * sent. The total above it is the API's, and it is the total of the whole list whatever page is
 * open, so no page is ever a list the total fails to describe.
 *
 * **Four states, four sentences.** Loading says so; a request that never reached the API and one
 * the API answered with a fault have different headings, from `ui/FailureNotice.tsx`; and a reader
 * shown no table is told there is nothing to show here, which is the same sentence whether they
 * hold no usage grant or the install has no directory, because the API sends the same body.
 *
 * **Nothing here decides who may see anything.** The request is identical for every caller.
 *
 * Imported statically rather than split, for `Roles.tsx`' reason: it mounts neither heavy library
 * and imports no stylesheet of its own.
 *
 * Task ids: M27.7.14
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import {
  EVERYBODY,
  NO_MODEL_CALL,
  PERIODS,
  RUNS_HEADING,
  glanceTokens,
  glanceTokensLine,
  notMeasuredSentence,
  peoplePage,
  periodLabel,
  readUsage,
  tokensHeading,
  tokensKeyHeading,
  usageApiPath,
  type Period,
  type PeopleView,
  type TokenBreakdown,
  type UsageBody,
} from "./usageQuery";

/** The design's own label for this screen, which the navigation and this heading share. */
export const USAGE_HEADING = "Usage and cost";

/** Under the heading. */
export const USAGE_LEDE =
  "How many questions people asked, by department and by person, over the period you choose. " +
  "What those questions cost is on the Spend screen.";

/** A reader shown no table, whichever of the reasons there is none. */
export const NOTHING_TO_SHOW = "There is nothing to show here.";

/** A reader shown tables for a period in which nobody asked anything. */
export const NOBODY_ASKED = "Nobody asked a question in this period.";

/** The search matched no line the page holds. Says nothing about lines not held. */
export const NO_PERSON_MATCHES = "No person in this list matches.";

/** The qualifier on every figure, in the two shapes it has, drawn from the response. */
export const WITHOUT_AUTOMATION = "Automated traffic is not counted.";
export const WITH_AUTOMATION = "Automated traffic is counted.";

/** Where cost is shown, said beside the figure the design draws it with. */
export const COST_IS_ON_SPEND = "What each department's questions cost, from the same grant.";

/** What the person table's controls act on. */
export const NARROWS_THIS_LIST = "Search, order and pages work on the people listed here.";

/** The accessible names of the tables. */
export const DEPARTMENTS_CAPTION = "Questions by department";
export const PEOPLE_CAPTION = "Questions by person";

/** Under the at-a-glance tokens, saying which requests they are over. */
export const TOKENS_ARE_OVER_MODEL_CALLS = "consumed by the questions above that called a model";

function Glance({ body }: { readonly body: UsageBody }) {
  const unmeasured = body.not_measured.includes("tokens");
  const tokens = glanceTokens(body.tokens);
  return (
    <section className="card">
      <h2>At a glance</h2>
      <dl className="fields" aria-label="Usage at a glance">
        {body.questions === null ? null : (
          <>
            <div className="fields__row">
              <dt>Questions</dt>
              <dd>
                <span>{String(body.questions)}</span>
                <p className="note">{body.machine_included ? WITH_AUTOMATION : WITHOUT_AUTOMATION}</p>
              </dd>
            </div>
            <div className="fields__row">
              <dt>People</dt>
              <dd>
                <span>{String(body.people?.length ?? 0)}</span>
                <p className="note">who asked at least one question</p>
              </dd>
            </div>
          </>
        )}
        {tokens !== null ? (
          <div className="fields__row">
            <dt>Tokens</dt>
            <dd>
              <span>{glanceTokensLine(tokens.tokensIn, tokens.tokensOut)}</span>
              <p className="note">{TOKENS_ARE_OVER_MODEL_CALLS}</p>
            </dd>
          </div>
        ) : unmeasured ? (
          <div className="fields__row">
            <dt>Tokens</dt>
            <dd>
              <p className="note">{notMeasuredSentence("tokens")}</p>
            </dd>
          </div>
        ) : null}
        <div className="fields__row">
          <dt>Cost</dt>
          <dd>
            <Link to="/spend">Spend</Link>
            <p className="note">{COST_IS_ON_SPEND}</p>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function People({ lines }: { readonly lines: NonNullable<UsageBody["people"]> }) {
  const [view, setView] = useState<PeopleView>(EVERYBODY);
  const shown = peoplePage(lines, view);

  if (lines.length === 0) {
    return <p className="note">{NOBODY_ASKED}</p>;
  }
  return (
    <>
      <div className="form">
        <p className="note">{NARROWS_THIS_LIST}</p>
        <label className="control-label" htmlFor="usage-person-search">
          Find a person by their reference
        </label>
        <input
          id="usage-person-search"
          className="form-control"
          type="search"
          value={view.search}
          onChange={(event) => {
            setView({ ...view, search: event.target.value, page: 1 });
          }}
        />
        <label className="control-label" htmlFor="usage-person-sort">
          Order
        </label>
        <select
          id="usage-person-sort"
          className="form-control"
          value={view.sort}
          onChange={(event) => {
            setView({
              ...view,
              sort: event.target.value === "person" ? "person" : "questions",
              page: 1,
            });
          }}
        >
          <option value="questions">Most questions first</option>
          <option value="person">By reference</option>
        </select>
      </div>
      {shown.rows.length === 0 ? (
        <p className="note">{NO_PERSON_MATCHES}</p>
      ) : (
        // `.grid__scroll`, for `Connectors.tsx`' reason: a person's reference is an identifier with
        // no break in it, and without a scrolling parent it takes a phone's page wide.
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{PEOPLE_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Person</th>
                <th scope="col">Questions</th>
              </tr>
            </thead>
            <tbody>
              {shown.rows.map((line) => (
                <tr key={line.person}>
                  <th scope="row">
                    <code>{line.person}</code>
                  </th>
                  <td>{String(line.questions)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="grid__pager">
        <button
          type="button"
          className="button"
          disabled={!shown.hasPrevious}
          onClick={() => {
            setView({ ...view, page: shown.page - 1 });
          }}
        >
          Previous
        </button>
        <button
          type="button"
          className="button"
          disabled={!shown.hasNext}
          onClick={() => {
            setView({ ...view, page: shown.page + 1 });
          }}
        >
          Next
        </button>
      </div>
      <p className="note" aria-live="polite">
        Page {String(shown.page)}
      </p>
    </>
  );
}

/**
 * One token breakdown as a table, with the API's totals under its lines.
 *
 * Every line is drawn, unpaged, for the reason the department table is: the totals row describes
 * the whole list, so a page of it would be a list its own totals fail to describe.
 */
function Tokens({ breakdown }: { readonly breakdown: TokenBreakdown }) {
  const heading = tokensHeading(breakdown.axis);
  return (
    <section className="card">
      <h2>{heading}</h2>
      {breakdown.lines.length === 0 ? (
        <p className="note">{NO_MODEL_CALL}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{heading}</caption>
            <thead>
              <tr>
                <th scope="col">{tokensKeyHeading(breakdown.axis)}</th>
                <th scope="col">{RUNS_HEADING}</th>
                <th scope="col">Tokens in</th>
                <th scope="col">Tokens out</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.lines.map((line) => (
                <tr key={line.key}>
                  <th scope="row">
                    <code>{line.key}</code>
                  </th>
                  <td>{String(line.runs)}</td>
                  <td>{String(line.tokens_in)}</td>
                  <td>{String(line.tokens_out)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                <td>{String(breakdown.total_runs)}</td>
                <td>{String(breakdown.total_tokens_in)}</td>
                <td>{String(breakdown.total_tokens_out)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}

function UsageAnswerView({ period }: { readonly period: Period }) {
  const answer = useResource<unknown>(usageApiPath(period));

  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  const body = readUsage(answer.data);
  if (body === null || (body.departments === null && body.people === null && body.tokens.length === 0)) {
    return <p className="note">{NOTHING_TO_SHOW}</p>;
  }

  return (
    <>
      <Glance body={body} />

      {body.departments === null ? null : (
        <section className="card">
          <h2>By department</h2>
          {body.departments.length === 0 ? (
            <p className="note">{NOBODY_ASKED}</p>
          ) : (
            <div className="grid__scroll">
              <table className="grid__table">
                <caption className="grid__caption">{DEPARTMENTS_CAPTION}</caption>
                <thead>
                  <tr>
                    <th scope="col">Department</th>
                    <th scope="col">Questions</th>
                    <th scope="col">People</th>
                  </tr>
                </thead>
                <tbody>
                  {body.departments.map((line) => (
                    <tr key={line.department}>
                      <th scope="row">{line.department}</th>
                      <td>{String(line.questions)}</td>
                      <td>{String(line.people)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {body.people === null ? null : (
        <section className="card">
          <h2>By person</h2>
          {/* Keyed by period, so a new window starts from the first page and no search. */}
          <People key={period} lines={body.people} />
        </section>
      )}

      {body.tokens.map((breakdown) => (
        <Tokens key={breakdown.axis} breakdown={breakdown} />
      ))}

      {body.not_measured.includes("model") ? (
        <section className="card">
          <h2>By model</h2>
          <p className="note">{notMeasuredSentence("model")}</p>
        </section>
      ) : null}

      {body.not_measured.includes("agent") ? (
        <section className="card">
          <h2>By agent</h2>
          <p className="note">{notMeasuredSentence("agent")}</p>
        </section>
      ) : null}
    </>
  );
}

export function Usage() {
  const [period, setPeriod] = useState<Period>(PERIODS[0]);

  return (
    <article className="page">
      <h1>{USAGE_HEADING}</h1>
      <p className="lede">{USAGE_LEDE}</p>
      <div className="form">
        <label className="control-label" htmlFor="usage-period">
          Period
        </label>
        <select
          id="usage-period"
          className="form-control"
          value={String(period)}
          onChange={(event) => {
            const chosen = PERIODS.find((one) => String(one) === event.target.value);
            setPeriod(chosen ?? PERIODS[0]);
          }}
        >
          {PERIODS.map((days) => (
            <option key={days} value={String(days)}>
              {periodLabel(days)}
            </option>
          ))}
        </select>
      </div>
      <UsageAnswerView period={period} />
    </article>
  );
}
