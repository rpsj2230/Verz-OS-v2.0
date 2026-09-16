/**
 * Elevation requests: who asked for more, what they were given, and when it lapses.
 *
 * `docs/screens.html` draws no elevation screen of its own; SCREEN 10 is where the design talks
 * about reach being a set of grants that "can be audited and reduced", and this page takes that
 * screen's layout: the crumb, cards of labelled facts, and the hint under them. It sits in Govern
 * beside People and grants.
 *
 * **What it shows is the landing and the rules, because that is all an install records.**
 * `brain.console.elevation` decides what somebody arriving at a break-glass screen is told, and the
 * API sends it: whether this account holds standing access of its own, and the sentence for that.
 * The rules a session is held to are product constants, and the API sends those too. No session is
 * stored and none can be opened, so there is no list, no approve or deny control and no control to
 * end one early, and the API's sentence says exactly that where the list would be.
 *
 * **Nothing lists what a session could confer.** That is the catalogue handed to somebody holding
 * nothing, which `brain.console.elevation.A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_CATALOGUE`
 * refuses, and the response has no field one could arrive in.
 *
 * Task ids: M27.7.8
 */

import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import { ELEVATION_API_PATH, readElevation, reasonWords } from "./governPeopleQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const ELEVATION_HEADING = "Elevation requests";
export const ELEVATION_CRUMB = "Govern › Elevation requests";
export const ELEVATION_LEDE =
  "Who asked for more access than they hold, what they were given, and when it lapses. Where this " +
  "install records none of that, this page says so.";

export const READING_ELEVATION = "Reading what this install records about elevations.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
/** A body that is not the landing. The fourth state, and a different sentence from the other three. */
export const NOT_A_LANDING = "The answer about elevations could not be read.";
export const YOU_HOLD_THE_AUTHORITY = "You hold that authority.";

function Failure({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}

function Landing() {
  const answer = useResource<unknown>(ELEVATION_API_PATH);

  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_ELEVATION}
      </p>
    );
  }
  const landing = readElevation(answer.data);
  if (landing === null) {
    return <p className="note">{NOT_A_LANDING}</p>;
  }

  return (
    <>
      <section className="card" aria-labelledby="elevation-standing">
        <h2 id="elevation-standing">Your standing</h2>
        <p>{landing.prompt}</p>
      </section>

      <section className="card" aria-labelledby="elevation-requests">
        <h2 id="elevation-requests">Requests</h2>
        <p>{landing.recorded}</p>
      </section>

      <section className="card" aria-labelledby="elevation-rules">
        <h2 id="elevation-rules">What an elevation is</h2>
        <p>{landing.what}</p>
        <dl className="fields" aria-label="The rules an elevation is held to">
          <div className="fields__row">
            <dt>Reasons it may be opened for</dt>
            <dd>{landing.reasons.map(reasonWords).join(", ")}</dd>
          </div>
          <div className="fields__row">
            <dt>Longest it may run</dt>
            <dd>{`${String(landing.longest_hours)} hours`}</dd>
          </div>
        </dl>
        <p className="note">
          {landing.authorising}
          {landing.may_authorise ? ` ${YOU_HOLD_THE_AUTHORITY}` : ""}
        </p>
      </section>
    </>
  );
}

export function Elevation() {
  return (
    <article className="page">
      <p className="note">{ELEVATION_CRUMB}</p>
      <h1>{ELEVATION_HEADING}</h1>
      <p className="lede">{ELEVATION_LEDE}</p>
      <Landing />
    </article>
  );
}
