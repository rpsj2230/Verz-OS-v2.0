/**
 * Questions and gaps: what the system cannot answer on this install, and why the rest of what the
 * design lists cannot be shown.
 *
 * `docs/screens.html` names this screen "Questions & gaps" under Report on the company overview
 * and draws its content on the department console as the card "Questions nobody could answer",
 * with a table of question shape, how often asked, why it failed and the fix, and an Export link.
 * This page is that card. Its one row is the design's "no source" row, drawn when the API says
 * every question is being answered with nothing connected, with the design's own words for why it
 * failed and a link to where the fix is made. `questionsQuery.ts` says why the shape and count
 * columns and the "no knowledge" and "field missing" rows are absent, and the page says it too.
 *
 * **Four states, four sentences.** Loading says so; an unreachable API and a failed request have
 * different headings; and a screen with no gap to show says so in a sentence that is true both for
 * a connected install and for a reader who may not be told, because the API sends one body.
 *
 * **Nothing here decides who may see anything.** The request is identical for every caller.
 *
 * Imported statically rather than split, for `Roles.tsx`' reason.
 *
 * Task ids: M27.7.18
 */

import { Link } from "react-router-dom";
import { useResource } from "../api/useResource";
import { FailureNotice } from "./reportFailure";
import { CONNECTORS_PATH, QUESTIONS_API_PATH, USAGE_PATH, readQuestions } from "./questionsQuery";

/** The design's own label for this screen, which the navigation and this heading share. */
export const QUESTIONS_HEADING = "Questions and gaps";

/** Under the heading, in the screen registry's own words. */
export const QUESTIONS_LEDE =
  "What people asked and what the system could not answer. The gaps are the roadmap.";

/** The design's card heading. */
export const UNANSWERED_HEADING = "Questions nobody could answer";

/** No gap to show, whichever of the reasons there is none. */
export const NO_GAP = "There is no gap to show here.";

/** The design's words for the one row an install can know. */
export const NO_SOURCE = "no source";
export const CONNECT_A_SOURCE = "Connect a source";

/** Why the shape and count columns are absent. */
export const UNANSWERED_ARE_NOT_RECORDED =
  "Nothing on this install records a question that went unanswered, so the questions, how often " +
  "each was asked and why each failed cannot be listed here.";

/** Why the words people typed are not listed. */
export const WORDS_ARE_NOT_KEPT =
  "The words people typed are not kept for this screen. A list of them would be a record of what " +
  "each person was trying to find out, readable by whoever opens this page.";

/** The accessible name of the table. */
export const GAPS_CAPTION = "Why questions could not be answered";

/** Why the not-found answer is never counted, with the sentence askers receive. */
export function notFoundIsNotAGap(sentence: string): string {
  return (
    `"${sentence}" is never counted as a gap. It is said in the same words when nothing exists ` +
    "and when the person asking may not see what does, so counting it would count refusals."
  );
}

/** What is said in place of the design's Export link. */
export const EXPORT_NOT_OFFERED =
  "There is no Export control: nothing about unanswered questions is recorded that could be " +
  "exported.";

function QuestionsAnswerView() {
  const answer = useResource<unknown>(QUESTIONS_API_PATH);

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
  const body = readQuestions(answer.data);
  if (body === null) {
    return <p className="note">{NO_GAP}</p>;
  }

  return (
    <section className="card">
      <h2>{UNANSWERED_HEADING}</h2>
      {body.nothing_connected ? (
        // `.grid__scroll`, for `Connectors.tsx`' reason, although nothing here is an identifier:
        // the quoted sentence is the longest cell and a phone should scroll the table, not the page.
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{GAPS_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Why it failed</th>
                <th scope="col">What every asker is told</th>
                <th scope="col">Fix</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">{NO_SOURCE}</th>
                <td>{body.answered_when_nothing_connected}</td>
                <td>
                  <Link to={CONNECTORS_PATH}>{CONNECT_A_SOURCE}</Link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <p className="note">{NO_GAP}</p>
      )}
      {body.unanswered_are_recorded ? null : <p className="note">{UNANSWERED_ARE_NOT_RECORDED}</p>}
      <p className="note">{notFoundIsNotAGap(body.answered_when_nothing_found)}</p>
      <p className="note">{WORDS_ARE_NOT_KEPT}</p>
      <p className="note">
        How many questions were asked, by department and by person, is on{" "}
        <Link to={USAGE_PATH}>Usage and cost</Link>.
      </p>
      <p className="note">{EXPORT_NOT_OFFERED}</p>
    </section>
  );
}

export function Questions() {
  return (
    <article className="page">
      <h1>{QUESTIONS_HEADING}</h1>
      <p className="lede">{QUESTIONS_LEDE}</p>
      <QuestionsAnswerView />
    </article>
  );
}
