/**
 * Adoption: how much each department this reader may see asked, and how many people asked.
 *
 * `brain.console.adoption_view` has decided since M37.3.2.4 which departments one reader may be
 * shown, and nothing rendered it: `brain.ops.console_screens` reported it as declaring no
 * screen key at all. This is the screen, and the citation in `adoptionQuery.ts` is what binds
 * the two.
 *
 * **Every line the API sent is drawn, including the ones whose figures are zero.** That is the
 * one rule this page exists to keep. A department with nothing recorded has a line because the
 * reader may see that department, and hiding it would turn the page into a report on who has
 * stopped using the system. See `A_ZERO_IS_A_LINE_AND_NOT_AN_ABSENCE` in `adoptionQuery.ts`.
 *
 * **Nothing here decides what may be seen and nothing is totalled.** A reader whose grant names
 * one department is drawn one line, with no note and no gap where the others would be, and
 * there is no sum across the departments on the page: the API holds no total over them, and a
 * total drawn here would be the only figure on the screen nobody stands behind.
 *
 * **`truncated` is a sentence with no number in it.** It says there are more departments than
 * this page shows, which is a fact about the page rather than a count of anything.
 *
 * Imported statically rather than split, for `Agents`' reason: neither heavy library, no
 * stylesheet of its own.
 *
 * Task ids: M27.7.17, M27.8.6
 */

import { useState } from "react";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import {
  ADOPTION_API_PATH,
  ADOPTION_DAYS,
  ADOPTION_FILTERS,
  ADOPTION_PERIODS,
  ADOPTION_SORTS,
  DAYS_PARAMETER,
  periodWords,
  readAdoptionPage,
  type AdoptionLineRow,
} from "./adoptionQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The page's heading. */
export const ADOPTION_HEADING = "Adoption";

/** Under the heading. Names the window, because both figures on every row are over it. */
export const ADOPTION_LEDE =
  "How many questions each department you can see asked over the period chosen, and how many " +
  "people asked them.";

export const FILTERS_LABEL = "Narrow the departments";
export const PERIOD_LABEL = "Period";
export const NONE_MATCH = NOTHING_MATCHES;

/** The table's accessible name. */
export const ADOPTION_CAPTION = "Questions and people by department";

/** A page with no lines, whichever of the reasons it has none. */
export const NO_ADOPTION = "There is nothing to show here.";

/** A page that came back full. A fact about there being more, and never a figure. */
export const MORE_DEPARTMENTS = "There are more departments than this page shows.";

function AdoptionView() {
  const [days, setDays] = useState(ADOPTION_DAYS);
  const listing = useListing<AdoptionLineRow>(ADOPTION_API_PATH, {
    choices: ADOPTION_FILTERS,
    extra: { [DAYS_PARAMETER]: String(days) },
  });
  const controls = (
    <>
      <ListControls label={FILTERS_LABEL} listing={listing} choices={ADOPTION_FILTERS} sorts={ADOPTION_SORTS} />
      <form className="form" aria-label={PERIOD_LABEL} onSubmit={(event) => event.preventDefault()}>
        <label className="control-label">
          {PERIOD_LABEL}{" "}
          <select
            className="form-control"
            value={String(days)}
            onChange={(event) => {
              setDays(Number(event.target.value));
            }}
          >
            {ADOPTION_PERIODS.map((one) => (
              <option key={one} value={String(one)}>
                {periodWords(one)}
              </option>
            ))}
          </select>
        </label>
      </form>
    </>
  );

  if (listing.failure) {
    return (
      <>
        {controls}
        <FailureNotice failure={listing.failure} />
      </>
    );
  }
  if (listing.busy) {
    return (
      <>
        {controls}
        <p className="note" role="status">
          Loading.
        </p>
      </>
    );
  }
  const page = readAdoptionPage(listing.body);
  if (page.lines.length === 0) {
    return (
      <>
        {controls}
        <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_ADOPTION}</p>
      </>
    );
  }
  return (
    <>
      {controls}
      <div className="grid">
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{ADOPTION_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">department</th>
                <th scope="col">questions</th>
                <th scope="col">people</th>
              </tr>
            </thead>
            <tbody>
              {page.lines.map((line) => (
                <tr key={line.department}>
                  <th scope="row">{line.department}</th>
                  <td>{line.questions}</td>
                  <td>{line.people}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <ShowMore listing={listing} />
      {page.truncated ? <p className="note">{MORE_DEPARTMENTS}</p> : null}
    </>
  );
}

export function Adoption() {
  return (
    <article className="page">
      <h1>{ADOPTION_HEADING}</h1>
      <p className="lede">{ADOPTION_LEDE}</p>
      <AdoptionView />
    </article>
  );
}
