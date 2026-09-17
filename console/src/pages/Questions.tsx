/**
 * Questions and gaps: what the system cannot answer on this install because nothing it reads
 * covers the subject, and why the rest of what the design lists cannot be shown.
 *
 * `docs/screens.html` names this screen "Questions & gaps" under Report on the company overview
 * and draws its content on the department console as the card "Questions nobody could answer",
 * with a table of question shape, how often asked, why it failed and the fix, and an Export link.
 * This page is that card. When nothing is connected at all it draws the design's "no source" row,
 * with the design's own words for why it failed and a link to where the fix is made. Otherwise it
 * draws a line per department and source for every question no connected source covered, with how
 * often it was asked and the same fix. `questionsQuery.ts` says why the question shape column and
 * the "no knowledge" and "field missing" rows are absent, and the page says it too.
 *
 * **Four states, four sentences.** Loading says so; an unreachable API and a failed request have
 * different headings; and a screen with no gap line says so in a sentence that is true both for an
 * install with none and for a reader who may not see one, because the API sends one body.
 *
 * **Nothing here decides who may see anything.** The request is identical for every caller, and a
 * source the API sends as null is drawn as one the reader is not told, in the same words every
 * time.
 *
 * Imported statically rather than split, for `Roles.tsx`' reason.
 *
 * Task ids: M27.7.18
 */

import { Link } from "react-router-dom";
import { useResource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import { CONNECTORS_PATH, QUESTIONS_API_PATH, USAGE_PATH, readQuestions } from "./questionsQuery";

/** The design's own label for this screen, which the navigation and this heading share. */
export const QUESTIONS_HEADING = "Questions and gaps";

/** Under the heading, in the screen registry's own words. */
export const QUESTIONS_LEDE =
  "What people asked and what the system could not answer. The gaps are the roadmap.";

/** The design's card heading. */
export const UNANSWERED_HEADING = "Questions nobody could answer";

/** A body the page cannot read. */
export const NO_GAP = "There is no gap to show here.";

/** No line to show, whichever of the reasons there is none: none recorded, or none this reader sees. */
export const NO_MISSING_SOURCE =
  "No question in this period matched a rule for a source this install does not read.";

/** The design's words for the row an install can know about everybody. */
export const NO_SOURCE = "no source";
export const CONNECT_A_SOURCE = "Connect a source";

/** What a line whose source this reader may not be told says in the source column. */
export const SOURCE_NOT_NAMED = "a source you are not shown";

/** Why only one kind of unanswered question is listed. */
export const ONLY_MISSING_SOURCES_ARE_RECORDED =
  "Only a question whose shape matches a rule for a source this install does not read is " +
  "recorded, by the department it was asked in and the source that would have answered. Nothing " +
  "else about an unanswered question is kept, so no other kind can be listed here.";

/** Why the words people typed are not listed. */
export const WORDS_ARE_NOT_KEPT =
  "The words people typed and who typed them are not kept for this screen. A list of them would " +
  "be a record of what each person was trying to find out, readable by whoever opens this page.";

/** The accessible names of the two tables. */
export const GAPS_CAPTION = "Why questions could not be answered";
export const MISSING_SOURCES_CAPTION = "Questions no connected source covered";

/** Why the not-found answer is never counted, with the sentence askers receive. */
export function notFoundIsNotAGap(sentence: string): string {
  return (
    `"${sentence}" is never counted as a gap. It is said in the same words when nothing exists ` +
    "and when the person asking may not see what does, so counting it would count refusals."
  );
}

/** The window the lines cover, in the API's own instants. */
export function since(start: string): string {
  return `Since ${start}.`;
}

/** What is said in place of the design's Export link. */
export const EXPORT_NOT_OFFERED =
  "There is no Export control: everything recorded about unanswered questions is on this page.";

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
      ) : null}
      {body.gaps.length > 0 ? (
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{MISSING_SOURCES_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Department</th>
                <th scope="col">Source that would have answered</th>
                <th scope="col">Asked</th>
                <th scope="col">Fix</th>
              </tr>
            </thead>
            <tbody>
              {body.gaps.map((line) => (
                <tr key={`${line.department}|${line.source ?? ""}`}>
                  <th scope="row">{line.department}</th>
                  <td>{line.source ?? SOURCE_NOT_NAMED}</td>
                  <td>{String(line.asked)}</td>
                  <td>
                    <Link to={CONNECTORS_PATH}>{CONNECT_A_SOURCE}</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {body.gaps.length === 0 ? <p className="note">{NO_MISSING_SOURCE}</p> : null}
      <p className="note">{since(body.start)}</p>
      {body.unanswered_are_recorded ? null : (
        <p className="note">{ONLY_MISSING_SOURCES_ARE_RECORDED}</p>
      )}
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
