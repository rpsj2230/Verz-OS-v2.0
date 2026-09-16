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
 * Task ids: M27.7.17
 */

import { useResource } from "../api/useResource";
import { adoptionApiPath, readAdoptionPage } from "./adoptionQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The page's heading. */
export const ADOPTION_HEADING = "Adoption";

/** Under the heading. Names the window, because both figures on every row are over it. */
export const ADOPTION_LEDE =
  "How many questions each department you can see asked over the last thirty days, and how " +
  "many people asked them.";

/** The table's accessible name. */
export const ADOPTION_CAPTION = "Questions and people by department";

/** A page with no lines, whichever of the reasons it has none. */
export const NO_ADOPTION = "There is nothing to show here.";

/** A page that came back full. A fact about there being more, and never a figure. */
export const MORE_DEPARTMENTS = "There are more departments than this page shows.";

function AdoptionView() {
  const answer = useResource<unknown>(adoptionApiPath());

  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  const page = readAdoptionPage(answer.data);
  if (page.lines.length === 0) {
    return <p className="note">{NO_ADOPTION}</p>;
  }
  return (
    <>
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
