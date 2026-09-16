/**
 * Service levels: what each lane promised, what it measured, and where the gap is.
 *
 * `brain.console.service_level_view` has decided since M30.5.3 what one reader may be shown of
 * a reading, and nothing rendered it: `brain.ops.console_screens` counted that as a screen
 * nobody has. This is the screen.
 *
 * **Nothing here decides what may be seen.** The request goes out identically for every
 * caller, the API narrows it, and a reading with no lanes is drawn as a reading with no lanes.
 * See `A_READING_WITH_NO_LANES_IS_NOT_EXPLAINED` in `serviceLevelsQuery.ts`: the two reasons a
 * reader gets one must stay indistinguishable, so the page says there is nothing to show and
 * says nothing about why.
 *
 * **Every figure is the API's.** The objective and the measurement sit in the same row so the
 * gap is read off the screen rather than worked out by it, and whether a lane met what it
 * promised is the API's own boolean. See `A_MEASUREMENT_IS_NEVER_RECOMPUTED_IN_A_BROWSER`.
 *
 * **The shortfalls are printed in the reliability module's own words.** They are sentences
 * about this install's own lanes, they name no department and no person, and a console
 * rewording them would be a second vocabulary for a fact that already has one.
 *
 * Imported statically rather than split. It mounts neither heavy library and imports no
 * stylesheet of its own, which is `App.tsx`'s rule for a page that reaches nothing the shell
 * does not already reach: a chunk for it would buy a round trip and save no bytes. The table
 * is written out with the grid's own classes rather than through `DataTable`, because that
 * component mounts the table library and would put it back in the entry chunk for everybody.
 *
 * Task ids: M27.7.16
 */

import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  milliseconds,
  ratePercent,
  readServiceLevels,
  serviceLevelsApiPath,
  type LaneReadingRow,
} from "./serviceLevelsQuery";

/** The page's heading. */
export const SERVICE_LEVELS_HEADING = "Service levels";

/** Under the heading. Says what the window is, because every figure on the page is over it. */
export const SERVICE_LEVELS_LEDE =
  "What each lane promised and what it measured over the last day.";

/** The table's accessible name. */
export const SERVICE_LEVELS_CAPTION = "Each lane's measured attainment against its objective";

/**
 * A reading with no lanes, whichever of the two reasons it has none.
 *
 * One sentence for both, with nothing in it about grants, scopes or narrowing. See
 * `A_READING_WITH_NO_LANES_IS_NOT_EXPLAINED`.
 */
export const NO_LANES = "There is nothing to show here.";

/** What a lane that met its objective is called, and what one that did not is called. */
export const MET = "met";
export const MISSED = "missed";

function LaneRow({ lane }: { readonly lane: LaneReadingRow }) {
  return (
    <tr>
      <th scope="row">{lane.lane}</th>
      <td>{lane.met ? MET : MISSED}</td>
      <td>{milliseconds(lane.p95_ms)}</td>
      <td>{lane.objective_p95_ms === null ? "" : milliseconds(lane.objective_p95_ms)}</td>
      <td>{ratePercent(lane.success_rate)}</td>
      <td>{ratePercent(lane.objective_success_rate)}</td>
      <td>{lane.requests}</td>
      <td>
        {lane.shortfalls.map((shortfall) => (
          <p key={shortfall}>{shortfall}</p>
        ))}
      </td>
    </tr>
  );
}

function ReadingView() {
  const answer = useResource<unknown>(serviceLevelsApiPath());

  if (answer.failure) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
        <p>{answer.failure.message}</p>
      </Notice>
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  const reading = readServiceLevels(answer.data);
  if (reading === null) {
    return null;
  }
  if (reading.lanes.length === 0) {
    return <p className="note">{NO_LANES}</p>;
  }
  return (
    <div className="grid">
      <div className="grid__scroll">
        <table className="grid__table">
          <caption className="grid__caption">{SERVICE_LEVELS_CAPTION}</caption>
          <thead>
            <tr>
              <th scope="col">lane</th>
              <th scope="col">outcome</th>
              <th scope="col">p95</th>
              <th scope="col">p95 promised</th>
              <th scope="col">success rate</th>
              <th scope="col">success rate promised</th>
              <th scope="col">requests</th>
              <th scope="col">shortfalls</th>
            </tr>
          </thead>
          <tbody>
            {reading.lanes.map((lane) => (
              <LaneRow key={lane.lane} lane={lane} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ServiceLevels() {
  return (
    <article className="page">
      <h1>{SERVICE_LEVELS_HEADING}</h1>
      <p className="lede">{SERVICE_LEVELS_LEDE}</p>
      <ReadingView />
    </article>
  );
}
