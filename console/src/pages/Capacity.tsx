/**
 * Capacity: connections, memory and pool sizes against what is deployed.
 *
 * `brain.ops.connections` holds the connection arithmetic, `brain.ops.wiring` costs the
 * components a profile declares and `brain.ops.compose` costs what the compose files reserve.
 * This shows all three and computes none of them.
 *
 * **Two memory figures, never one, and the second is absent rather than filled in.**
 * `brain.console.installation.WHAT_A_PROFILE_DECLARES_AND_WHAT_THE_COMPOSE_FILES_RESERVE_ARE_
 * TWO_FIGURES` is the argument, and the gap between them is a real finding rather than
 * rounding. This container mounts no compose file, so `deployed_mib` arrives null and the row
 * is left out rather than drawn empty or drawn as a copy of the declared figure: two numbers
 * equal by construction read as agreement between independent measurements, and agreement is
 * exactly what somebody opens this screen to check.
 *
 * **The budget findings are drawn in the API's own words.** `budget_breaches` and
 * `unbudgeted_services` produce sentences, and rewording them here would put the arithmetic's
 * conclusion in two places. They are drawn as a list rather than as a count, which is this
 * console's rule everywhere and is right here for a second reason: the useful thing about a
 * breach is which component it is about.
 *
 * **Nothing on this page is a headroom indicator.** `headroom` is a number the API computed and
 * it is drawn as that number. A bar, a percentage or a colour would be this console deciding
 * what counts as close to the ceiling, which is a judgement about a deployment it knows
 * nothing else about.
 *
 * Task ids: M27.7.27
 */

import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import { CAPACITY_API_PATH, CONNECTION_COLUMNS, type Capacity as CapacityBody } from "./installQuery";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = "That did not work";

/** The heading over the budget findings, when there are any. */
export const WHAT_DOES_NOT_ADD_UP = "What does not add up";

export function Capacity() {
  const answer = useResource<CapacityBody>(CAPACITY_API_PATH);
  const body = answer.data;
  const findings = [...(body?.memory.breaches ?? []), ...(body?.memory.unbudgeted ?? [])];

  return (
    <article className="page">
      <h1>Capacity</h1>
      <p className="lede">
        What this profile wants against what the host has, and what each database will admit.
      </p>

      {answer.failure ? (
        <section className="card">
          <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
            <p>{answer.failure.message}</p>
          </Notice>
        </section>
      ) : null}

      {answer.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : null}

      {body ? (
        <>
          <section className="card">
            <h2>Memory</h2>
            <dl className="fields" aria-label="Memory">
              <div className="fields__row">
                <dt>profile</dt>
                <dd>{body.memory.profile}</dd>
              </div>
              <div className="fields__row">
                <dt>host total</dt>
                <dd>{`${String(body.memory.host_total_mib)} MiB`}</dd>
              </div>
              <div className="fields__row">
                <dt>declared by this profile</dt>
                <dd>{`${String(body.memory.declared_mib)} MiB`}</dd>
              </div>
              {/*
               * Absent stays absent, which is `Overview.tsx`'s rule and matters more here: a
               * row saying "deployed: 0 MiB" would be read as a deployment reserving nothing,
               * and a row saying "deployed: the declared figure" would be read as two numbers
               * agreeing. Neither was measured.
               */}
              {body.memory.deployed_mib === null || body.memory.deployed_mib === undefined ? null : (
                <div className="fields__row">
                  <dt>reserved by the compose files</dt>
                  <dd>{`${String(body.memory.deployed_mib)} MiB`}</dd>
                </div>
              )}
            </dl>
          </section>

          {findings.length > 0 ? (
            <section className="card">
              <Notice title={WHAT_DOES_NOT_ADD_UP}>
                <ul>
                  {findings.map((finding) => (
                    <li key={finding}>{finding}</li>
                  ))}
                </ul>
              </Notice>
            </section>
          ) : null}

          <section className="card">
            <h2>Connections</h2>
            {/*
             * `.grid__scroll` around the table for the reason `Limits.tsx` gives: `.grid__table`
             * does not break inside a word, so without a scrolling parent the document takes the
             * overflow and the navigation goes off the side of a phone.
             */}
            <div className="grid__scroll">
              <table className="grid__table">
                <caption className="grid__caption">
                  What each database will admit, what the declared clients want, and what is left
                </caption>
                <thead>
                  <tr>
                    {CONNECTION_COLUMNS.map((column) => (
                      <th scope="col" key={column}>
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.connections.map((one) => (
                    <tr key={one.database}>
                      {CONNECTION_COLUMNS.map((column) => (
                        <td key={column}>{String(one[column])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </article>
  );
}
