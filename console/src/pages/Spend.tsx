/**
 * Spend: what each department this reader may see has cost, and how old the figures are.
 *
 * `brain.console.spend_report_view` has decided since M36.1.3 what one reader may be shown of
 * the materialised report, and nothing rendered it. This is the screen.
 *
 * **Nothing here decides what may be seen, and nothing here adds anything up.** The lines are
 * the ones the API sent, the total is the field it sent beside them, and a reader whose grant
 * names one department is drawn one line and a total of exactly that line. See
 * `A_TOTAL_IS_READ_AND_NEVER_ADDED_UP_HERE` in `spendQuery.ts`.
 *
 * **There is no count on this page and nowhere for one.** No number of departments, no share
 * of a company figure, no "and others". The page draws the lines it was sent and the total the
 * API stands behind, and a reader holding one department and a reader holding all of them see
 * pages that differ only in how many rows are on them.
 *
 * **The age of the figures is beside the figures.** A materialised report is right as of an
 * instant and wrong in an unknown direction afterwards, so the freshness is drawn under the
 * heading rather than in a corner: it is the qualifier on every number below it.
 *
 * **Whether automation was counted is on the page in words.** The request excludes it, the
 * response says so, and the sentence is drawn from the response rather than from what this
 * file asked for, so a change to the default cannot leave the page describing the old one.
 *
 * Imported statically rather than split, for `Agents`' reason: it mounts neither heavy library
 * and imports no stylesheet of its own. The table uses the grid's own classes rather than
 * `DataTable`, which would put the table library back in the entry chunk for everybody.
 *
 * Task ids: M27.7.15
 */

import { useResource } from "../api/useResource";
import { freshnessLine, majorUnits, readSpendReport, spendApiPath } from "./spendQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The page's heading. */
export const SPEND_HEADING = "Spend";

/** Under the heading. Names the dimension, because every key below is one of its values. */
export const SPEND_LEDE = "What each department you can see has cost, summed by day.";

/** The table's accessible name. */
export const SPEND_CAPTION = "Spend by department";

/** A breakdown with no lines, whichever of the reasons it has none. */
export const NO_SPEND = "There is nothing to show here.";

/**
 * What is said when the view has never been rebuilt.
 *
 * About the report and not about spending, which is the whole of what this sentence has to get
 * right: a report nobody has built says nothing about what anything cost, and the screen must
 * not let it read as zero. See `AN_UNBUILT_REPORT_IS_NOT_A_ZERO`.
 */
export const NOT_BUILT_YET =
  "This report has not been built yet, so there are no figures to show.";

/** The qualifier every figure on the page carries, in the two shapes it has. */
export const WITHOUT_AUTOMATION = "Automated traffic is not counted.";
export const WITH_AUTOMATION = "Automated traffic is counted.";

/** The label the total is drawn under. A word, because the figure is the API's. */
export const TOTAL_LABEL = "total";

function SpendView() {
  const answer = useResource<unknown>(spendApiPath());

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
  const report = readSpendReport(answer.data);
  if (report === null) {
    return null;
  }
  if (!report.built) {
    return <p className="note">{NOT_BUILT_YET}</p>;
  }
  return (
    <>
      <p className="note">{freshnessLine(report)}</p>
      <p className="note">
        {report.machine_included ? WITH_AUTOMATION : WITHOUT_AUTOMATION}
      </p>
      {report.lines.length === 0 ? (
        <p className="note">{NO_SPEND}</p>
      ) : (
        <div className="grid">
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">{SPEND_CAPTION}</caption>
              <thead>
                <tr>
                  <th scope="col">{report.dimension}</th>
                  <th scope="col">cost</th>
                </tr>
              </thead>
              <tbody>
                {report.lines.map((line) => (
                  <tr key={line.key}>
                    <th scope="row">{line.key}</th>
                    <td>{majorUnits(line.cost_minor)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row">{TOTAL_LABEL}</th>
                  {/*
                   * The API's own total, printed. It is the sum of the rows above it because
                   * the read module asserts that it is, and not because this loop added them.
                   */}
                  <td>{report.total_minor === null ? "" : majorUnits(report.total_minor)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

export function Spend() {
  return (
    <article className="page">
      <h1>{SPEND_HEADING}</h1>
      <p className="lede">{SPEND_LEDE}</p>
      <SpendView />
    </article>
  );
}
