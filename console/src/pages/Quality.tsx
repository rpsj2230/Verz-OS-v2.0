/**
 * Quality and canaries: when the permission canaries last ran and how that run ended, and what an
 * install cannot say about quality.
 *
 * `docs/screens.html` names this screen "Quality & canaries" under Report on the company overview,
 * draws the permission canaries as a card on the people screen, and repeats the canary line in the
 * overview's "Needs you". This page is that card, with the design's rows in the design's order,
 * followed by the two things the screen registry says the screen is for and an install does not
 * hold: how the golden corpus scored, and what regressed since the last release. Each row the API
 * cannot fill is a sentence where the design draws a figure. `qualityQuery.ts` says why a finished
 * run is never drawn as green.
 *
 * **Four states, four sentences.** Loading says so; an unreachable API and a failed request have
 * different headings; and no run to show is one sentence, true both on an install where the
 * canaries have never run and for a reader who may not see a run, because the API sends one body.
 *
 * **Nothing here decides who may see anything.** The request is identical for every caller, and
 * no canary content reaches this page: the API sends when and how a run ended, and nothing else.
 *
 * Imported statically rather than split, for `Roles.tsx`' reason.
 *
 * Task ids: M27.7.19
 */

import { useResource } from "../api/useResource";
import { FailureNotice } from "./reportFailure";
import { QUALITY_API_PATH, cadence, readQuality, runLine } from "./qualityQuery";

/** The design's own label for this screen, which the navigation and this heading share. */
export const QUALITY_HEADING = "Quality and canaries";

/** Under the heading, in the screen registry's own words. */
export const QUALITY_LEDE =
  "How the golden corpus scored, what the permission canaries found, and what regressed since " +
  "the last release.";

/** The design's card heading, and its own sentence about what a canary is. */
export const CANARIES_HEADING = "Permission canaries";
export const WHAT_A_CANARY_IS =
  "Each canary asks a question whose correct answer is a refusal. A permission bug that returns " +
  "data is caught by a test that expected nothing.";

/** No run to show, whichever of the reasons there is none. */
export const NO_RUN = "There is no canary run to show here.";

/** Why a finished run is not a green one. */
export const FINDINGS_ARE_NOT_RECORDED =
  "Not recorded. A run that finished is not a run that passed: what a run found is not kept, so " +
  "this screen cannot say whether it was green.";

/** When nothing starts the canaries, with the cadence they would keep. */
export function notStarted(interval: number): string {
  return (
    "Nothing on this install starts the permission canaries yet. When something does, they are " +
    `due ${cadence(interval)}.`
  );
}

/** What the design's synthetic users and assertions rows become. */
export const NOT_ON_AN_INSTALL =
  "Not on this install. The synthetic users and the values the canaries look for belong to the " +
  "product's own test suite, which is not shipped to an install.";

/** What the design's "on a red canary" row becomes. */
export const NOTHING_ACTS_ON_A_RESULT =
  "Nothing on this install acts on a canary result, because no result is recorded for anything " +
  "to act on.";

/** The golden corpus and the regression, in place of figures an install does not hold. */
export const GOLDEN_HEADING = "Golden questions";
export const GOLDEN_NOT_ON_AN_INSTALL =
  "Not on this install. The golden questions are part of the product's own test suite, which is " +
  "not shipped to an install, so how they scored cannot be shown here.";
export const REGRESSION_HEADING = "Since the last release";
export const NO_EVALUATION_RUN =
  "Nothing on this install records an evaluation run, so there is no earlier score to compare " +
  "with and no regression can be shown.";

function QualityAnswerView() {
  const answer = useResource<unknown>(QUALITY_API_PATH);

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
  const body = readQuality(answer.data);
  if (body === null) {
    return <p className="note">{NO_RUN}</p>;
  }

  return (
    <>
      <section className="card">
        <h2>{CANARIES_HEADING}</h2>
        <dl className="fields" aria-label={CANARIES_HEADING}>
          <div className="fields__row">
            <dt>Synthetic users under test</dt>
            <dd>
              <p className="note">{NOT_ON_AN_INSTALL}</p>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Assertions per run</dt>
            <dd>
              <p className="note">{NOT_ON_AN_INSTALL}</p>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Last run</dt>
            <dd>
              {body.last_canary_run === null ? (
                <p className="note">{NO_RUN}</p>
              ) : (
                <span>{runLine(body.last_canary_run)}</span>
              )}
            </dd>
          </div>
          <div className="fields__row">
            <dt>What it found</dt>
            <dd>
              {body.findings_are_recorded ? null : (
                <p className="note">{FINDINGS_ARE_NOT_RECORDED}</p>
              )}
            </dd>
          </div>
          <div className="fields__row">
            <dt>Runs</dt>
            <dd>
              {body.canaries_started ? (
                <span>{cadence(body.canary_interval_seconds)}</span>
              ) : (
                <p className="note">{notStarted(body.canary_interval_seconds)}</p>
              )}
            </dd>
          </div>
          <div className="fields__row">
            <dt>On a red canary</dt>
            <dd>
              {body.findings_are_recorded ? null : (
                <p className="note">{NOTHING_ACTS_ON_A_RESULT}</p>
              )}
            </dd>
          </div>
        </dl>
        <p className="note">{WHAT_A_CANARY_IS}</p>
      </section>

      <section className="card">
        <h2>{GOLDEN_HEADING}</h2>
        {body.evaluation_runs_are_recorded ? null : (
          <p className="note">{GOLDEN_NOT_ON_AN_INSTALL}</p>
        )}
      </section>

      <section className="card">
        <h2>{REGRESSION_HEADING}</h2>
        {body.evaluation_runs_are_recorded ? null : <p className="note">{NO_EVALUATION_RUN}</p>}
      </section>
    </>
  );
}

export function Quality() {
  return (
    <article className="page">
      <h1>{QUALITY_HEADING}</h1>
      <p className="lede">{QUALITY_LEDE}</p>
      <QualityAnswerView />
    </article>
  );
}
